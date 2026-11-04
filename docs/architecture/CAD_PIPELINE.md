# CAD pipeline

Goal: process each unique CAD content as few times as possible, outside the web process, safely.

```
upload (POST /api/listings/{id}/cad)                  web process, ~0.1 s
  ├─ size cap 20 MB, extension .stl/.3mf, content must match (ZIP ⇔ 3MF)
  ├─ app/mesh.py load_mesh: bounded numpy parse → dimensions (mm)        ── 422 on anything invalid
  ├─ SHA-256 → cad/<sha256[:48]>.<fmt>, written once (link, never replace)
  ├─ cad_assets (one row per content) + cad_files (one row per stored name)
  ├─ schedule: queue 'analyze' if this content has no analysis at the current version,
  │            queue 'render'  if this content has no ready preview at all
  └─ listing.cad_path / cad_dimensions; response says what is queued
                    │
                    ▼  cad_jobs (PostgreSQL), claimed FOR UPDATE SKIP LOCKED
worker container (python -m app.cad_worker), one job at a time, no network
  ├─ analyze  mesh.analyze → cad_assets.analysis (JSON)                  0.03–1 s
  └─ render   numpy triangles → Blender studio scene → .work-<id>/ → renders/<id>/ (atomic rename)
              render.webp (1200 px, lossless) · thumb.webp (640 px) · model.glb             ~60 s
```

## Cache keys

| Stage | Key | Invalidated by |
|---|---|---|
| Analysis | `(sha256, 'analyze', 'geometry-<ANALYSIS_VERSION>')` | bumping `mesh.ANALYSIS_VERSION` (re-analysed on next schedule) |
| Preview | `(sha256, 'render', RENDER_PRESET)` | bumping `cad_assets.RENDER_PRESET`, then `cad_worker --rerender` (explicit, because it costs a minute of CPU per model) |
| Adopted preview | `(sha256, 'render', 'adopted')` | never: previews that existed before this pipeline, including the official kits' assembly renders |

What never triggers processing: title, description, price, category, pricing rules, material or colour changes,
listing approval or publication, a re-upload of the same bytes, the same file uploaded by another host.

Colours are applied in the browser. The still is rendered once in neutral grey and recoloured in linear light by
`assets/product-visuals.js`; the GLB is recoloured by `assets/viewer.js`. Host capabilities and stock still decide
which colours are offered, and the server still prices and validates every configuration (`pricing.quote`).

## Previews in pages

Listings reach their previews through `cad_path → cad_files → cad_assets → cad_jobs`, loaded in one query per page
of listings, with no file read (before, `status.json` was read from disk for every listing serialized). A listing
shows the current preset's preview, else an adopted or older one, else its state (`pending`, `processing`,
`failed`). Preview URLs name a directory that never changes once written. They are served with
`Cache-Control: private, max-age=31536000, immutable` and explicit types (`model/gltf-binary`, which Caddy
compresses). A new model or preset gives a new URL.

## Analysis

`mesh.analyze` welds vertices (1e-4 mm, as the renderer) and reports:

- dimensions, bounds, triangle and vertex counts, surface area;
- volume (only when the surface is closed and consistently wound);
- boundary and non-manifold edges, winding consistency, inverted normals, zero-area triangles;
- connected bodies, 3MF build items (`parts`, names kept) and units;
- the share of downward-facing area steeper than 45° above the bed.

Findings are graded:

| Level | Meaning | Examples |
|---|---|---|
| error | definite geometry defect | open surface, non-manifold edges, inconsistent or inverted normals |
| warning | heuristic | zero-area triangles, probable unit mistakes (STL has no unit), overall size under 1 mm, overhangs that will likely need supports |
| info | neutral fact | units assumed, several bodies, "wall thickness and print success need slicing and a test print" |

Printer suitability is evaluated where the printers are known. The analysis endpoint lists the owner's printers
with fit or no fit, and job eligibility checks the assigned host's build volumes against the order's dimensions
(unchanged). Nothing here is presented as a guarantee that a print will succeed.

`GET /api/listings/{id}/cad/analysis` (owner and administrators) returns the analysis and the fit per printer.

## Safety of untrusted files

- Content decides the format: a ZIP is never parsed as STL, and a 3MF must be a ZIP.
- 3MF archives are limited to 100 members, 40 MB in total and 20 MB per member, with a compression ratio of at most
  200. Absolute or `..` paths, encrypted members, duplicate names, `<!` (DTD and entities) and component recursion
  beyond 16 levels are all refused.
- Meshes are limited to 400,000 triangles (1.2 M ASCII vertices); coordinates must be finite and within ±10 km.
- Blender never opens the upload. It receives a `.npy` array (loaded with `allow_pickle=False`) and runs
  `--factory-startup`, niced, with a CPU-time limit and an optional address-space limit, in a container with no
  network and no capabilities.
- The worker never writes listings or orders. It writes only `cad_assets`, `cad_jobs` and `uploads/renders`.

## Reliability

- Claims carry a deadline (render timeout + 2 min). A worker killed mid-job leaves the claim to expire, and the job
  is taken again as a new attempt.
- Up to `CAD_MAX_ATTEMPTS` (3) attempts with backoff (30 s, 2 min). After that the job is `failed` with the reason.
  The owner's "Regenerate preview" requeues failed stages only; it never redoes a ready preview.
- On start and every 5 minutes the worker registers files referenced by listings or order lines that have no row
  yet (older uploads, seeded or attached official products), adopts their previews and queues what is missing.
- Interrupted work directories and partial writes older than an hour are removed.

## Retention

- **Original CAD files are never deleted** by any code path. Orders pin the exact file and hash they were sold
  with, and hosts download that file.
- `python -m app.cad_worker --storage-report` lists unreferenced originals (old uploads replaced since) and preview
  directories nothing references. Deleting an unreferenced original is a decision for an administrator.
- `--storage-report --prune-orphan-previews` removes only preview directories that no listing, order line or
  `cad_jobs` row references. They can be rendered again from their CAD file.

## Storage layout and future object storage

```
uploads/cad/<sha256[:48]>.<stl|3mf>    immutable originals (older uploads: random 48-hex names)
uploads/renders/<id>/                  immutable previews (older: <cad stem>/ with status.json)
uploads/products/, avatars/, requests/ images and attachments (unchanged)
```

Every path is derived from a name stored in the database and resolved in one place: `cad_assets.cad_dir()`,
`renders_dir()` and `manufacturing.cad_file()`. Moving to S3-compatible storage means replacing those functions and
the `FileResponse` calls in `app/cad.py` with object reads or signed URLs. The names and database rows stay as they
are.

## Benchmarks

See [PRODUCTION_REPORT.md](PRODUCTION_REPORT.md): parsing is 5–29× faster than the pure-Python parser, renders are
pixel-identical and 1–9% faster, the still is 35% smaller, GLB transfer is 41–75% smaller, and a repeat product
view downloads nothing.
