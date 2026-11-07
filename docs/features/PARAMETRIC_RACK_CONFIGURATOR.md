# Design Your Rack

A buyer chooses the tubes they use. The software lays them out, generates one solid printable rack as real CAD, checks it, prices it from the measured solid, and sells it through the existing cart, checkout and printing jobs. It runs in the normal OpenLabs3D application at `http://localhost:8080`, with no separate server.

## Product lifecycle

| Stage | What it is | Where the buyer sees it |
|---|---|---|
| Draft | `rack_designs` row, freely editable; unsaved changes also kept in the browser | My designs |
| Exact model | `rack_builds` row and files, one per geometry, shared and cached | The configurator |
| Offered for sale | An internal private `listings` row for this buyer and geometry, with pinned CAD | Nowhere: basket and checkout show it as a custom rack |
| Order | `order_items.rack_snapshot`, a full copy that never changes | My orders |
| Manufacturing | The normal `printing_jobs` row | Printing jobs, for eligible hosts |

The private listing is an implementation detail: the cart, checkout and job system key off a listing, so reusing one avoids a second ordering system. No page presents it as a product. Editing a draft never reaches an order. **Reorder** takes today's hosts and price through the basket, and never reuses an old price.

## Host matching

Printing areas are never a fixed list. `availability.rack_envelopes()` reads approved FDM printers of active approved hosts, each limited to its approved capabilities intersected with its host's inventory, excluding the buyer's own printers, filtered by the chosen material and exact colour. The result drives the **Available printing area** control, the layout search, and the size check.

Usable area is the build volume less `printer_margin_mm` (5 mm each side) and `printer_margin_z_mm` (5 mm). These are documented defaults in `rack/rules.py`: there is no per-printer data on real margins.

The same question is asked again at each stage, from current data:

| When | Check |
|---|---|
| Configuring | `plan`: printing areas, host count for this size and finish |
| Offering for sale | `POST /racks/listing`: exact model ready, **measured** dimensions, `pricing.quote` for this finish |
| Basket and checkout | `pricing.quote`, against the listing's measured dimensions |
| Listing jobs, accepting a job | `availability.job_ineligibility`, shared with every product: never the buyer, approved host, one approved printer that fits upright and has the exact shade |

If hosts change between design and purchase, checkout refuses the line with a clear message and no order is created. A rack may turn about Z but never tip over: only upright is safe for its overhangs.

## CAD architecture and resources

CadQuery runs only in the existing worker container (`python -m app.cad_worker`), in a subprocess per build with CPU, memory and wall-clock limits. The worker takes one job at a time, rack builds first, and `docker compose up --scale worker=N` is the way to add capacity, since claims are safe across workers. There is no Redis or Celery: a table queue was sufficient.

Budget about **1.2 GB per concurrent build** at worst, 0.6–0.8 GB typically. The container limit in `compose.production.yaml` is 3 GB. `RACK_BUILD_MEMORY_MB` caps address space, which runs far above resident memory because OpenCASCADE reserves more than it uses: 2.8 GB crashes the largest rack, 4 GB does not. A crash there is a failed build, not a dead worker.

## Architecture

```
assets/rack-configurator.js   one configuration object; shelf, top view and 3D stage all read it
        │ POST /api/racks/plan (debounced, cancelled when stale)                 milliseconds, no CAD, no write lock
        ▼
backend/app/rack/
  schema.py      RackConfiguration: strict, versioned; unknown fields refused; nothing in it is ever executed
  profiles.py    tube library, each profile recording where its dimensions came from
  layout.py      positions: automatic candidates, or checks on manual positions
  structure.py   the two design families as plans (shapely): shared by CAD, preview and estimate
  labels.py      label fitting from the fonts' own metrics
  planner.py     all of the above → plan: spec, hash, issues, estimates
  estimate.py    material and price rules
        │ POST /api/racks/builds → rack_builds row (spec hash = identity)
        ▼
worker (python -m app.cad_worker), one job at a time; web never imports CadQuery
  queue.py       claim, subprocess with CPU/memory/time limits, cancellation, retention
  build.py       solid → validate → only then write STL, 3MF, GLB, stills
  geometry.py    CadQuery solid from the spec
  export.py      mesh clean-up and file writers
        │ POST /api/racks/listing  (only with a ready build)
        ▼
backend/app/racks.py   private immutable Listing → existing /api/cart → /api/checkout → PrintingJob → /api/jobs/{id}/cad
```

### Why a private listing

Cart, quote, checkout and job eligibility all key off a `Listing`. A rack sold as a listing gets all of it with no second
ordering system: `pricing.quote()`, price-change review, `manufacturing.snapshot()`, `availability.job_ineligibility()`
and the host's download route work unchanged. One listing per buyer and geometry (`uq_listing_rack`).

Such a listing has `rack_hash` set, and that decides everything that makes it private:

| Where | Rule |
|---|---|
| `main.can_view` | owner and administrators only |
| `pricing.quote` | only its owner can buy it, by any route (cart, `/orders`, checkout) |
| `main.owned` | nobody can edit it, including an owner who is a host |
| catalogue, `/listings/mine`, admin list, overview | excluded |
| `cad.download_cad` | the buyer does not get the manufacturing file |
| `cad.rack_job_preview` | a host may see the picture of a rack it can take or has taken, not the 3D model |

## Configuration schema

```jsonc
{
  "schema_version": 1,
  "tubes": [{"profile_id": "conical-50-generic", "quantity": 15}],     // automatic layouts
  "layout": {
    "mode": "auto",                                                    // or "manual"
    "spacing": "standard", "arrangement": "auto", "orientation": "auto", "columns": null, "outer_margin_mm": 0,
    "positions": [{"profile_id": "...", "x": 0, "y": 0}]               // manual layouts, in mm; +y is the back
  },
  "style": "lightweight",                                              // or "premium"
  "edge": "soft", "corner_radius_mm": null, "clearance_adjust_mm": 0,
  "overrides": {"conical-15-generic": {"body_diameter_mm": 17.8}},     // within OVERRIDE_LIMITS
  "label": {"text": "Lab 03", "font": "sans", "size_mm": null, "position": "front", "style": "engraved"}
}
```

The planner turns this into a **spec**: positions, seats and solids, centred, with no reference to the library. The spec is
what the generator reads and what is hashed, so a layout moved as a whole, or arrived at differently, is the same rack, and
an order can always be rebuilt without the library. `GEOMETRY_VERSION` is in the spec: changing the generator gives new
hashes and never reuses old files.

## Tube profiles

Tube volume does not determine dimensions, so every profile records `verification_status` and `source_reference`.

| Profile | Body Ø | Cap Ø | Length | Status |
|---|---|---|---|---|
| `micro-0.5-generic` | 8.0 | 11.0 | 30.5 | generic, values assumed: no drawing could be read |
| `micro-1.5-generic` | 10.9 | 14.0 | 39.0 | generic; Eppendorf sheet read via a distributor, labels not certain; cap estimated |
| `conical-15-generic` | 17.4 | 22.5 | 120.8 | generic; from the Corning 352096 sheet |
| `conical-50-generic` | 30.0 | 34.5 | 115.0 | generic; Corning and distributor listings; cap estimated |
| `falcon-352096` | 17.37 | 22.48 | 120.75 | published, unmeasured; the cap reading is unconfirmed |
| `falcon-352070` | 30.0 | 34.5 | 114.55 | published, unmeasured; cap estimated |

**No profile has been measured.** Cone length and tip diameter are assumed in all of them, because the manufacturers' drawings
could not be retrieved (HTTP 403). The interface says so next to the shelf and in *Tube sizes*. Buyers may adjust body, cap
and length within `OVERRIDE_LIMITS`. Add a container by adding a profile: nothing else needs changing.

## Layout

Automatic layouts place tall tubes at the back, and search within the chosen printing area, or else whatever the eligible printers allow, including rows as wide as those printers. For each of a set of widths and each arrangement (grouped, flowing mixed
rows, staggered), rows are centred and then settle forward until the nearest tube of any earlier row sets the distance, so
different tubes nest rather than sit on a uniform grid. Candidates are scored by fit on a printer first, then area with a
penalty for long thin shapes. Deterministic and tested. Worst case 120 tubes: under a second.

Two tubes need the largest of: bores plus 2.4 mm of wall, caps plus a finger gap, and, across a step in height, the taller
tube's wall plus the shorter tube's cap. Manual positions are checked by the same rules: errors (overlap, thin wall, touching
caps) block the design; tight finger gaps warn.

## Geometry

Each design family carries a version in its specification: **Lightweight is version 3, Premium is version 4**. A stored specification of version 2 still builds with the code that sold it, and purchased files are pinned on the order, so a redesign never reaches an existing order.

**Lightweight: engineered minimalism.** One continuous load path: base frame and ribs, a hub under each tube, a thin funnel following the tube's own cone, a sleeve opened by four slim lancet windows, a collar, and short arched bridges from collar to collar. Every funnel leans less than the printable limit (the steepest, 50 mL, is 33 degrees from vertical; a test holds the whole tube library to it). A funnel is what makes this work for microtubes: it leaves room between neighbours at the base, where a straight sleeve did not. Bridge undersides rise at 60 degrees, so they need no bridging. Each funnel shape is built once and reused, which is why the largest rack builds much faster than the earlier design. A name goes on a slim plate leaning back 30 degrees along one edge, no wider than the name.

**Premium: soft industrial.** The body is not a box with fillets. Its wall is a cross-section (`structure.body_profile`) that is widest at 42% of the height, tucks in towards the bed, and curves in to meet the deck at a tangent, with no edge between wall and deck. `geometry._soft_body` builds that wall as exact surfaces: the profile extruded along each straight side and revolved about each corner's axis, sewn with the flat top and bottom. A loft through sections was tried first and rejected: it overshot the planned outline by up to 1.75 mm per side.

Proportions follow the rack's height, so a 24 mm microtube rack and a 45 mm Falcon rack have the same character. Each corner has its own radius, as large as keeps the deck around the tube nearest it: concentric with a tube in the corner, and capsule-like on a single row. Tall tubes form a raised level along the back of a long low deck, its outline following those tubes, joined to the deck by a concave radius. Bores get a rounded lead-in, always ending on flat deck: where one ran into the curve at the deck's edge, the two surfaces met in a sliver the mesher could not close. A short tube enclosed by a taller level gets a raised well, keeping its seating depth.

A Premium rack is low because it holds a tube by its cone plus enough straight wall to keep it upright, not by a share of its length: depth beyond that is only height and plastic. If the kernel cannot make a blend, cut through it or mesh it, the build tries smaller radii and then a plain junction, which is equally sound. Booleans use a 0.0001 mm tolerance, because the kernel can otherwise lose a cut where a cavity nearly touches a curved wall.

**Labels** are real letters in the solid. On Premium, the name sits on a soft flat: a plane just deep enough for the letters, whose edge is where it leaves the convex wall, so there is no plate and no pocket. The flat takes up to 1.6 mm off that side, and the rack's reported size says so. A rack may widen by up to 50% to carry a name rather than refuse it. Letters come from bundled fonts that allow it (`app/rack/fonts/LICENSES.md`). Bold faces only;
each font's stroke width is measured by a test, and its minimum size follows from that. Text is restricted to an alphabet both
fonts draw, and is only ever drawn. Web-process metrics match CAD text within 1.5%.

## Validation

`build.run()` refuses to write any file until these pass. A failure is reported; nothing invalid is ever exported.

| Kind | What | How |
|---|---|---|
| Checked automatically | one solid, kernel validity, positive volume | CAD kernel |
| | watertight, consistent outward normals, one body, dimensions within 0.05 mm, flat on the bed | the exported mesh, read back by `app/mesh.py` |
| | every cavity clear to full diameter, a seat under every tube, walls at the deck, label present | point probes in the solid |
| | STL and 3MF are the same body | both re-read through the upload parser |
| Estimated | overhang share, orientation, material, price | design rules; labelled as estimates |
| Physical test only | tube fit, strength, adhesion, chemical and temperature behaviour | not claimed; see below |

Print time is deliberately not shown: only a slicer with the host's profile can work it out. Mass comes from a model fitted to PrusaSlicer on the ten validation racks (within about 15%), labelled an estimate; solid volume is never presented as filament.

## Manufacturing constraints

`app/rack/rules.py`, one place. Walls, overhang, hole and feature limits follow the conservative FDM defaults in the
dfam-check table (Hubs guides, consistent with ISO/ASTM 52910). Racks must fit a printer **upright**: they may turn about Z,
never tip over, must be FDM, and keep a 5 mm margin. `availability.fits(printer, dims, upright=True)` applies this for quotes,
job lists and acceptance. Other products keep the existing any-orientation rule.

Over the limit, the plan names the dimension and draws the printable area. Nothing is scaled or split.

## Interface

`assets/rack-route.js` adds the routes (`#design-rack`, `#design-rack/<id>`, `#my-designs`) and a few hundred bytes to every page. The configurator's script, styles and three.js load only when opened. There is one configuration object; every view below reads and changes it.

**The buyer decides:** tubes, style, optionally a height and a name, material and colour. Everything else is worked out.

| Earlier control | Now |
|---|---|
| Automatic / By hand | Removed. Racks are arranged automatically; **Edit layout** is an action |
| Pattern (best fit, rows, staggered, grouped) | Removed from the interface; the layout engine decides. Stored designs that used it still build |
| Spacing dropdown | Automatic. A segmented control in Advanced, and "Compact" uses the tightest spacing that still clears caps |
| Shape (wider / deeper) | Automatic. A small illustrated choice in Advanced |
| Tubes per row | Automatic. Optional in Advanced |
| Top view tab | Removed. The viewer has a Top button; the top view is where you edit |

**Layouts.** `planner._layouts_that_fit` offers Balanced, Compact and Wide as real top-view drawings, only those that fit an available printer and differ by more than 5% in a dimension. One result means no choice is shown. Fixing rows or orientation in Advanced turns the choice off.

**Rack height** is real geometry, not scale. `height_mm` in the configuration moves each tube's deck, within limits computed for those tubes by `layout.depth_limits`:

| Tube | Lowest hold | Recommended (Premium) | Highest hold |
|---|---|---|---|
| Rule | cone + straight wall of 0.4 × width, at least 10 mm; a tube too short for that, its cone | cone + straight wall of 0.85 × width, at least 20 mm, leaving 46% of the length to hold | leaves 38% of the length, at least 12 mm |
| Rack height, 50 mL | 31.5 mm | 45 mm | 73.5 mm |
| Rack height, 15 + 50 mL | 34.5 mm | 45 mm | 77 mm |
| Rack height, 1.5 mL | 22.5 mm | 23.5 mm | 26.5 mm |

These are design rules, not measured strength. In a mixed rack every tube moves together, each within its own limits. Bore diameter, seat and floor do not change; the body's curve follows the new height. Out of range is refused with the nearest height that works, as a one-tap action, and nothing is built or sold. If tubes change so a chosen height no longer suits them, the height moves to the nearest that does, and says so.

**Layout editor.** Drag a tube; it aligns to other tubes, with guides. Drop it on another to swap them, or across empty space to select several. Tap a tube chip then an empty place to add. The rack's outline and size follow the drag, without asking the server. Conflicts show at once. **Suggest** asks the engine for its layout and draws it over yours with what would change; it is never applied without asking. No CAD is generated while editing: the exact model is made on **Done**, and opening the editor and changing nothing leaves the rack automatic. Every action has a keyboard or button alternative.

**On a phone** (`PHONE` in `rack-configurator.js`: up to 760 px wide, or a short landscape screen), the same controls work differently:

- The model stays in view above the choices, in about a third of the screen, and takes no gestures: a thumb on it scrolls the page. Tapping it opens a focused full-screen view with rotate, pinch and Close. The 3D library sets `touch-action: none` on its canvas, which the stylesheet has to override, or the page would not scroll.
- Tubes, style and height are on the first screen. Everything else is one list whose rows say what they are set to, opening bottom sheets that are real `<dialog>` elements: focus is held and returned, Escape closes them, and a pull on the heading dismisses them. A section moves into the sheet and back, so there is one copy of each control.
- The layout editor takes the whole screen. A finger drags a tube without scrolling; arrows do the same without dragging. A button swaps the sheet for the live 3D model.
- One-line purchase bar with Buy now first, hidden while typing. Saving is under Review. A reason shows only if the buyer can act on it. On its side, a phone shows the model beside the choices.

**Viewer.** The plan's shapes at once, one geometry per funnel shape instanced, then the worker's exact preview. Hemisphere and three directional lights; a generated environment map was measured and dropped (600 ms of blocking at load, for reflections matte filament barely shows). The shadow is redrawn only when the model changes. Framing is calculated from the model's box and keeps the buyer's viewing direction when the rack changes size. The default angle matches the static renders.

**"Exact model" means what is on screen.** The chip says so only once the mesh of the solid the files come from has arrived in the viewer, and stops at once when the rack changes. That mesh is the same solid as the STL and 3MF, to an absolute tolerance, with normals taken from the CAD surfaces (`geometry.surface_mesh`). Builds are cached by the hash of their specification, so an older model cannot be shown for a newer rack. The browser suite compares the viewer with the CAD's measured size and volume, and a geometry test checks every point of the preview lies within 0.1 mm of the STL. CadQuery's own `mesh()` treats tolerance as relative to edge length, which gave errors near 1 mm on long curved walls: `geometry.mesh_absolute` is why it no longer does.

Accessible alternatives: every position can be selected and moved by keyboard (arrows; Shift for 5 mm; Delete), with an arrow pad on touch screens, and a table of positions with number fields. A live text summary carries what the 3D view shows. Problems are never colour alone.

## Pricing

Rates are configuration, not code: the marketplace setting `rack_pricing`, edited by administrators under Settings, validated by `estimate.Rates`, and every change is logged.

`unit price = (setup + material + machine time + per position + label) × design factor × (1 + marketplace fee)`, rounded up to 10 cents.

| Rate | Default | Needs validating against |
|---|---|---|
| Material, EUR/kg (PLA, PETG, ABS, ASA) | 25, 28, 30, 34 | Real filament costs |
| Setup, per rack | 4.50 | Real handling time |
| Machine time, per hour | 1.80 | Host compensation |
| Assumed print speed, mm³/s | 5 | Host printers (the generic slicer profile reached far less; modern printers more) |
| Per position / label | 0.06 / 1.50 | Inspection and setup effort |
| Premium factor | 1.15 | A pricing decision |
| Marketplace fee | 12% | A business decision |

**All defaults are prototype values.** The interface says "estimated prototype manufacturing price" until an administrator marks the rates validated. The result becomes the private listing's price and material factors, then `pricing.quote()` does the rest; the browser never supplies a price. There is one price per rack and finish, not per host, because hosts have no price data. Changed rates reach a rack next time it is offered or reordered, and placed orders keep their price. No online payment exists: orders are requests, and the host arranges payment, as for every product.

## Slicer results

`scripts/rack_slicer_check.py` slices the validation racks with **PrusaSlicer 2.9.2** in a disposable container, using one generic profile: 0.4 mm nozzle, 0.2 mm layers, 3 perimeters, 15% gyroid infill. That is one reproducible profile, not every host's printer. `scripts/rack_validation_prints.py` builds the set.

| Result | Finding |
|---|---|
| STL and 3MF load and slice | All 13 racks, both formats |
| Manifold, one part, correct size and layer count | All 13 |
| Automatic supports, unnamed racks | 0 on all 9, including the lowest heights the control allows |
| Automatic supports, named racks | Yes, under letter ledges of under 1 mm: about 1 to 2 m on a Lightweight nameplate, 5 to 12 m on a Premium side. Tested and not caused by the flat (0 alone), nor reduced by shallower letters or a leaning face. Leave automatic supports off for these, and check the first print |
| Material | Slicer within 10% of the estimate |

Print times from this profile are not representative and are not shown anywhere.

## Security

- Manufacturing files are never in a public path. Builds live under `uploads/rack-builds`, not served statically; only coarse
  previews have a route, named by a 256-bit hash with no way to list them. A simplified mesh is not complete IP protection.
- At listing, files are copied to the immutable CAD store, and hosts get them from `/api/jobs/{id}/cad` under existing rules:
  assigned host, open job, hash re-checked on every download.
- Requests never carry code: only validated numbers, enums and a label in a fixed alphabet. CAD runs in a subprocess, niced,
  with address-space, CPU and wall-clock limits, on the worker's no-internet network.
- Abuse limits: 120 tubes per rack; new geometry limited per account and per address; a bounded queue returns 503 when full;
  identical geometry costs nothing; builds nobody is polling are skipped, or stopped mid-build.

## Data

Migration `79a_parametric_racks` only adds: tables `rack_designs` and `rack_builds`, columns `listings.rack_hash`,
`rack_snapshot`, `rack_design_id` and `order_items.rack_snapshot`. It uses plain `ADD COLUMN`, because a batch recreate would drop
the unnamed CHECK constraints on those tables in SQLite.

| | Mutable? | Holds |
|---|---|---|
| `rack_designs` | yes, a draft | name, configuration |
| `rack_builds` | cache; cleaned after 14 days unused | spec, status, report; files under `uploads/rack-builds/<hash>` |
| private `listings` row | geometry never; price only if rules change | snapshot, pinned CAD file |
| `order_items.rack_snapshot` | never | configuration, spec, resolved profiles, report, file names and hashes, pricing |

## Deployment

The feature is part of the normal stack, with nothing extra to start:

```bash
docker compose up -d --build      # from this repository; .env sets COMPOSE_PROJECT_NAME=sitev2 locally
```

`http://localhost:8080` is Compose project `sitev2`, whose data lives in the volume `sitev2_app_data`. Migrations run when the backend starts. Generated and purchased CAD live on that volume, so restarts keep them. Before the deployment that introduced this feature, the database and uploads were backed up to `backups/pre-rack-*` in the checkout the site previously ran from. To go back: stop this stack, restore that database, and start the stack from that folder.

PostgreSQL is supported the same way: see `docs/deployment/POSTGRESQL_MIGRATION.md`. `scripts/rack_preview.py` is a developer convenience with its own temporary data, and the feature never needs it.

Worker image: 3.4 GB, of which Blender (for catalogue previews) is 1.1 GB. CadQuery needs `vtk` (loaded in full, about 640 MB) and OCP (265 MB); `numba`, `llvmlite`, `scipy` and `trame` were removed, and `casadi`'s unused solver plugins pruned. `app/rack/smoke.py` builds real racks during the image build, so a broken prune fails the build.

## Testing

```bash
cd backend
pytest tests/test_rack_engine.py tests/test_rack_marketplace.py     # no CAD needed
pytest tests/test_rack_geometry.py                                  # real CAD, about 4 minutes; skipped without CadQuery
OPENLABS3D_TEST_POSTGRES_URL=postgresql+psycopg://... pytest tests/test_rack_marketplace.py tests/test_schema_parity.py

python tests/rack_configurator_browser.py http://127.0.0.1:8096 /tmp/shots chromium firefox webkit     # RACK_STEPS="phone_journey" runs one part
```

The browser suite creates accounts' orders and jobs, so point it at a disposable stack seeded by `app/seed_rack_fixtures.py` (it refuses to run without `OPENLABS3D_QA_FIXTURES=yes`), never at the real site. It runs under the real Caddy CSP, so it polls rather than using `wait_for_function`, which CSP blocks. In WebKit, a request cancelled at the exact moment the main frame navigates is a teardown artifact; the suite ignores only that signature within 0.2 s of a navigation and prints how many it ignored. Any other request failure still fails the run.

`test_rack_geometry.py` reopens exports with trimesh and measures hole count, position and diameter from a cross-section of the
mesh alone, independently of the CAD kernel. This is what caught collapsed triangles the site's own analyser tolerated.

## Before accepting real customers

Software is complete for local use. These need real-world work first:

1. **Print the set** from `scripts/rack_validation_prints.py` and fill in the `measured` fields of its manifest: bores, fit with real tubes, strength when loaded, tip angle, label legibility. Nothing has been printed.
2. **Measure real tubes**, then update `verification_status`, cone and tip sizes, and clearances, which are starting values. Keep the prototype notices until then.
3. **Validate the rates** above, and mark them validated.
4. **Decide payment.** Nothing is charged online today.

## What has and has not been verified

Results on the final code, 2026-11-07:

| Check | Result |
|---|---|
| Backend, SQLite, CAD included | 570 passed, 2 skipped |
| Rack, schema parity and job eligibility tests, PostgreSQL | 72 passed |
| Rack browser suite, full Compose stack with PostgreSQL, Caddy and worker, including a real order from a phone viewport | Chromium 213/213, Firefox 211/211, WebKit 211/211 (5 teardown cancels ignored). Chromium's two extra checks use real touch events |
| Full build and validation sweep | 268 attempted across both families: 233 built and validated, 35 refused by design (names too long for a tiny rack, a top label on Lightweight), 0 failed |
| axe-core, WCAG 2.2 AA and best practice | 0 violations in 34 states, light and dark, including every sheet, the focused model and the phone editor |
| Lighthouse, configurator | Desktop: performance 84, accessibility 100, best practices 96, CLS 0.01. Simulated slow mobile with software graphics: performance 61, accessibility 100, CLS 0.014, blocking time 1.2 s |
| Viewer against the CAD | Premium: size within 0.01 mm, volume within 0.08%. The suite checks this on each run, and every sampled point of the preview within 0.1 mm of the STL |
| Restart and redeploy | Purchased STL and 3MF byte-identical |

Builds inside the worker image, one at a time:

| Rack | Time | Triangles | Preview GLB | Peak memory so far |
|---|---|---|---|---|
| 24 × 1.5 mL Premium | 3.0 s | 48,552 | 945 KB | 616 MiB |
| 15 × 50 + 5 × 15 mL Premium | 3.3 s | 61,828 | 1.1 MB | 640 MiB |
| The same, at its lowest height | 3.2 s | 58,890 | 1.2 MB | 640 MiB |
| 22 × 50 + 68 × 15 mL Premium | 7.3 s | 209,770 | 4.1 MB | 846 MiB |
| 24 × 1.5 mL Lightweight | 6.1 s | 44,872 | 1.1 MB | 846 MiB |
| 22 × 50 + 68 × 15 mL Lightweight, named | 39.7 s | 261,782 | 7.0 MB | 1,126 MiB |

Memory is the largest resident size of any build up to that row, so it never falls.

**Not verified, and not claimed:** that real tubes fit; printed strength, stiffness or stability under load (tip angle is arithmetic); real mass and print time on a host's printer; autoclaving, chemical resistance, sterility or any laboratory qualification.

## Known limitations

- **Skirted tubes** (self-standing conicals) are not modelled: seats assume a conical tip.
- **Open snap caps:** the finger gap is sized for closed caps, not for a lid opened in place.
- **A small Lightweight rack of large tubes** saves about half against Premium, but no more than the earlier design: 6 × 50 mL is about 74 g, as before.
- **A mixed rack on one printer only:** a design fits if one printer holds it upright; it is never split.
- **Text** is one line, in a Latin alphabet. Serif needs larger sizes than Sans because of its thin strokes.
- **Facets:** meshes are within about 0.03 mm of the true surfaces on average, measured against the solid.
- **Hosts have no price data**, so a rack has one price, whichever host takes it.
- **The largest Lightweight racks** carry a slicer stability warning, unresolved until printed.
- **Label ledges:** see Slicer results.
- **A Premium outline is about 5 to 15 mm larger** than the boxy earlier body, because curves need room around the tubes. It is lower, so it still uses less plastic: 374 g against 447 g for 20 × 50 mL.
- **Lightweight keeps its earlier height by default** (60.5 mm for 50 mL). The height control can make it lower.
- **The height limits are design rules.** Nothing has been measured with real tubes in a printed rack.
- **Raised levels** are straight-sided in plan; they do not yet scallop around each tube.
- **Preview shading:** a little mottling can show along the long top edge of a Premium rack in the browser. It is the display mesh, not the CAD.
- **SEO:** the page sets its own title and description, but as a hash route of the single-page site it cannot be indexed separately.
  A crawlable landing page needs server-side or static routes, which the site does not have today.
- **Payments:** none, as for every other product on the site.
- **The Blender layer** stays in the worker image for catalogue previews, even though racks do not use it.
