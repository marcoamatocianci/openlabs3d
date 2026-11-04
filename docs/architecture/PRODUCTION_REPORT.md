# Production architecture: technical report (2026-11-04, branch `v7-production`)

What changed, what was measured, and what did not improve. All numbers were measured on the development machine
(22 cores, NVMe, Docker 29, Compose 5.3) against a copy of the development data: 5 users, 19 listings, 19 orders,
26 jobs, 22 CAD files. Production-like runs used the real production Compose files with their CPU and memory limits
(`ol3d-rehearsal` project on loopback ports). No production server existed at the time of writing.

## 1. Summary

| Area | Before | After |
|---|---|---|
| Database | SQLite (one file, global writer lock) | PostgreSQL 18; same write ordering via an advisory lock; SQLite still used in development |
| Data migration | none | verified copy: counts + SHA-256 of every table, one transaction; 650 rows in < 1 s; cutover 43 s |
| CAD parsing | pure Python, in the request | numpy, 5–29× faster, identical dimensions |
| Rendering | FastAPI `BackgroundTasks` in the web process, lost on restart, keyed by upload name | separate worker container, durable queue, retries, crash recovery, keyed by content |
| Duplicate content | re-stored and re-rendered | stored once, analysed once, rendered once |
| Existing previews at cutover | n/a | 13 adopted, **0 Blender runs** |
| Upload request | parse in request + render queued in-process | 0.11 s for a 0.7 MB STL; render happens in the worker |
| Web image | 1.87 GB (with Blender) | 499 MB (worker image 1.99 GB) |
| Product page, mobile-like link (9 Mbit/s, 60 ms), first view | 3.32 s to 3D, 3.52 MB | **1.70 s**, 1.68 MB |
| Product page, repeat view | 2.60 s, 2.76 MB | **0.08 s, 0 bytes** |
| API latency (PostgreSQL vs SQLite) | — | **+3 to +17 ms** per request (see §4: network round trips) |
| Backups | manual, site stopped, SQLite file + tar | daily online `pg_dump` + uploads + config, restic off-server, monthly restore test |
| Tests | 152 (2026-11-01) → 296 at baseline | 309 on PostgreSQL, 307 + 2 PostgreSQL-only on SQLite; 4 browser suites |

## 2. PostgreSQL migration

- Schema drift between the migrated SQLite schema and the models: 6 cosmetic differences (unenforced `VARCHAR`
  lengths, unique index vs constraint). PostgreSQL built from the models upgraded from `77a` to `78a` with **0**
  differences.
- First full test run on PostgreSQL: 288/296 passed. The 8 failures were:
  - 6 from **a real latent bug**: `orders.contact` was `VARCHAR(200)` while checkout stores up to 1000 characters.
    SQLite never enforced it; PostgreSQL rejects it, so production orders would have failed. Fixed in `78a` (Text).
  - 2 that also failed on SQLite before any change: a stale rate-limit test, and a compose test that read the
    developer's `.env`. Both fixed.
- An audit of every request-schema limit against its column found no other mismatch.
- Migration tool on the development data: 650 rows in 24 tables (27 with the new CAD tables), < 1 s, all checksums
  equal, ids and Argon2 hashes preserved, sequences continue after the copied ids. A second run is refused.

## 3. CAD pipeline

### Parsing and analysis (`app/mesh.py`)

| File | Size | Triangles | Old parse | New parse | Speed-up | Analysis | Dimensions equal |
|---|---|---|---|---|---|---|---|
| mechanical-pipette-holder.stl | 13.3 MB | 266,232 | 1.04 s | 0.060 s | 17× | 0.95 s | yes |
| microtube_rack_24.stl | 4.2 MB | 84,300 | 0.36 s | 0.012 s | 29× | 0.20 s | yes |
| microtube_rack_24.3mf | 1.0 MB | 84,300 | 1.30 s | 0.274 s | 5× | 0.20 s | yes |
| centrifuge_rack_15ml_12.3mf | 0.5 MB | 42,940 | 0.66 s | 0.121 s | 5× | 0.09 s | yes |
| dna_pipette_stand_6.3mf (kit) | 1.1 MB | 63,892 | 0.99 s | 0.173 s | 6× | 0.16 s | yes |
| pipette_holder.3mf (kit) | 1.1 MB | 73,146 | 1.15 s | 0.223 s | 5× | 0.17 s | yes |
| concept_b_fin_tiers.stl | 8.4 MB | 168,960 | 0.73 s | 0.028 s | 26× | 0.48 s | yes |

The analysis found that `exaple_product/mechanical-pipette-holder.stl` is not closed: it has boundary edges,
non-manifold edges and inconsistent winding. The official products are all watertight. The kits report 3 and 4
bodies, matching their parts.

Cross-check with Blender's own topology (same 1e-4 mm weld):

- microtube rack: both report 42,036 vertices and 0 problem edges.
- example STL: both report 133,112 vertices and an open surface. Ours finds 3 boundary + 6 non-manifold edges;
  Blender finds 9 + 3, because it drops 6 duplicate triangles on weld, and those duplicates are what makes edges
  non-manifold in our count.

### Rendering

Blender 5.2 on the host, 2 threads, same scene and settings:

| Model | Old wall / peak RSS | New wall / peak RSS | Image difference |
|---|---|---|---|
| microtube rack, 84k triangles | 59.5 s / 1.78 GB | 58.9 s / 1.72 GB | 0 (pixel-identical) |
| pipette holder, 266k triangles | 39.7 s / 1.95 GB | 36.1 s / 1.82 GB | 0 (pixel-identical) |

The mesh hand-off now uses a binary numpy array and bulk `foreach_set` instead of a JSON triangle list and
`from_pydata`. That saves 1–9%; Cycles sampling dominates. In the worker container (Debian Blender 4.3, no
denoiser, 96 samples), a 15k-triangle part took 58.1 s in Blender and 1.8 s to encode (60 s total).

The real saving is not doing work: content addressing, adoption of existing previews and the rule that only content
changes trigger rendering. At cutover, 14 files turned out to be 13 contents; all 13 previews were adopted, and the
13 analyses took 1.3 s in total.

Not changed, deliberately: render resolution, samples and look (the studio-matched matte style is a product
decision). EEVEE was not adopted: it needs a GPU or software OpenGL on a headless server, and Cycles at 2 threads
fits the "once per model" budget.

### Output sizes

| Asset | Before | After |
|---|---|---|
| Still (1200 px) | PNG 412 KB | lossless WebP 268 KB (−35%, identical pixels; the browser recolouring needs exact values) |
| Thumbnail (640 px) | WebP 17.6 KB | unchanged |
| GLB on the wire (rack, 2.75 MB) | 2.75 MB (not compressed) | 0.70 MB gzip / 0.91 MB in the browser (zstd) |
| GLB on the wire (other model, 1.61 MB) | 1.61 MB | 0.95 MB zstd (−41%) |

GLB compression is plain HTTP compression (Caddy now compresses `model/gltf-binary`), so the browser needs no
decoder. Draco or meshopt would shrink GLBs further, but they add a WASM decoder (about 300 KB) or a build step for
models that already load in under 2 s on a mobile-like link. Not adopted.

## 4. API latency and throughput

Same benchmark inside each backend container (200 sequential requests per endpoint, then 16 concurrent readers for
10 s). Columns: old code on SQLite (development stack); new code on SQLite (no resource limits); new code on
PostgreSQL (production Compose limits, backend 2 CPU).

| p50, ms | old + SQLite | new + SQLite | new + PostgreSQL |
|---|---|---|---|
| catalogue | 6.8 | 8.3 | 17.0 |
| product | 6.1 | 6.5 | 13.4 |
| availability | 5.0 | 4.3 | 13.0 |
| categories | 2.7 | 2.2 | 4.0 |
| buyer orders | 14.9 | 14.4 | 24.5 |
| buyer cart | 4.9 | 4.1 | 7.2 |
| host active jobs | 13.0 | 8.2 | 24.5 |
| admin orders | 17.8 | 14.6 | 34.5 |
| preview thumbnail | 5.9 | 5.7 | 11.1 |
| 16 concurrent readers | 108 req/s | 101 req/s | 72.5 req/s |

Reading this table:

- **The code changes are neutral or faster** (columns 1 and 2). Host jobs went from 13.0 to 8.2 ms and admin orders
  from 17.8 to 14.6 ms, partly because preview status no longer reads `status.json` from disk for every listing.
- **PostgreSQL is slower per request than in-process SQLite.** A query is a network round trip: 115 µs for
  `SELECT 1`, 260 µs for a listing row. Checkout of a pooled connection costs about 0.5 ms (pre-ping, BEGIN,
  ROLLBACK), and a page makes 6–15 queries. Profiling showed 13 round trips per product request and no hot spot in
  application code.
- Joining the preview lookup (three `selectin` loads into one query) took the product page from 8 to 6 statements
  and from 15.2 to 13.4 ms, and concurrent reads from 59 to 72.5 req/s. The concurrent test is bound by one Python
  process: 80% of a core for the backend, 21% for PostgreSQL.
- In absolute terms every page stays under 35 ms of server time, well below internet round-trip times. What
  PostgreSQL buys is:
  - concurrent writers from two processes (web and worker) without "database is locked";
  - reads that never wait for writes (tested);
  - online, consistent backups (1.5 s for the whole database);
  - row locking and `SKIP LOCKED` for the queue;
  - a path to point-in-time recovery.
- Not done: removing `pool_pre_ping` (saves about 0.1 ms but turns a PostgreSQL restart into failed requests),
  autocommit for GET requests (some GET dependencies write), and more Uvicorn workers (login rate limits are per
  process).

## 5. Frontend

- three.js r180: the official minified builds replace the unminified ones (vendored files verified byte-identical
  to the npm release first). 2.0 MB → 0.72 MB to parse; 421 KB → 190 KB on the wire (gzip).
- The 3D viewer was already loaded on demand (`import()` on product and editor pages only); catalogue cards use
  640 px WebP thumbnails with `loading="lazy"`; colour changes never contact the server. These stay as they were.
- Static models, product images, hero and brand assets get `Cache-Control: public, max-age=86400`. Previews get
  `immutable` (§3).
- Product page, mobile-like link (CDP throttling: 9 Mbit/s down, 60 ms latency, 390 px viewport), time until the 3D
  model is displayed:

| | First visit | Repeat visit |
|---|---|---|
| Before | 3,319 ms, 3.52 MB | 2,597 ms, 2.76 MB (GLB re-downloaded every time) |
| After | 1,697 ms, 1.68 MB | 78 ms, 0 bytes |

  The repeat-visit figure needs a trusted origin: Chromium does not cache responses from an origin with a
  certificate error, so it was measured over HTTP with the new code.

## 6. Infrastructure, measured on the rehearsal

| Step | Result |
|---|---|
| `deploy/cutover-to-postgres.sh` | 43 s (stop, snapshot, schemas, copy + verify, start, health) |
| `deploy/backup.sh` | 1.5 s, 30 MB (dump 135 KB, uploads 30.6 MB zstd) |
| `deploy/verify-backup.sh` | restored into a throwaway database: 28 tables counted, revision `78a`, 5/5 Argon2 hashes |
| `deploy/restore.sh` on a clean project | 12 s + start; sign-in, order history and previews (including a new render) worked; a second restore into the non-empty project was refused |
| Worker internet access | blocked (internal network); database reachable |
| Published ports | Caddy only |
| Backend | uid 10001, read-only root filesystem |
| Worker capabilities | `CapEff: 0` |

The rehearsal caught one deployment bug: Docker file secrets keep their host permissions, so a `0600` secret could
not be read by the container user. `deploy/lib.sh` now enforces a `0700` directory with a `0644` file.

Idle memory: backend 96 MB, worker 95 MB, PostgreSQL 80 MB, Caddy 14 MB.

## 7. Storage

On the development data: 22 CAD files (33.6 MB), of which 7 (11.9 MB, 36%) are no longer referenced by any listing
or order (replaced uploads). There are 22 preview directories (32.0 MB), 7 of them orphans (10.4 MB). Originals are
kept under the existing never-delete rule. The storage report lists them; orphaned previews can be pruned on demand.
New uploads are stored by content, so a repeated upload adds nothing.

## 8. Not done, and why

- **WAL archiving / point-in-time recovery:** daily logical backups are sufficient at current volume. The upgrade
  path is documented (PRODUCTION.md).
- **S3-compatible storage:** paths are resolved in three functions, so the swap is contained; local NVMe is cheaper
  and faster at this size.
- **Thin-wall detection:** needs slicing or ray casting. It is reported as "needs slicing" rather than guessed.
- **Server-side checks against printer build volumes at upload:** they already happen at job eligibility for the
  assigned host, and the analysis endpoint shows the owner's printers. Nothing new was invented.
- **Real server, DNS, production cutover:** not performed; they need your machine, domain and go-ahead.
