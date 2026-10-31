# OpenLabs3D codebase audit: logo, My Orders and architecture

Date: 2026-10-31 · Branch `v4` (uncommitted working tree) · Scope: FastAPI backend, SQLite/Alembic,
vanilla-JS frontend, Docker Compose/Caddy, CAD rendering, marketplace and order flows.

Every finding is marked **Confirmed** (reproduced, measured, or shown directly by the code path and data)
or **Potential** (a risk or improvement without an observed failure). Numbers come from the measurements
in §9.

---

## 1. Summary of implemented fixes

| # | Change | Result |
|---|--------|--------|
| 1 | New logo everywhere (topbar on every page and workspace, footer, favicon) | Uses the supplied `OpenLabs3D Laboratory Printer Logo.png`. The background is removed without redrawing anything; Bright and Dark variants; 16 KB WebP instead of a 1.1 MB PNG |
| 2 | My Orders shows the purchased colour | Each order line now stores the colour hex offered at checkout. Previews are the existing neutral render, recoloured in the browser, with a swatch and the "Material · Colour" text |
| 3 | My Orders no longer refreshes on filter changes | No scroll jump, no page rebuild, no thumbnail flash, one API request per change, tab highlighted immediately |
| 4 | Order serialisation batched | Orders page: 35 → 9 SQL queries for 10 orders, constant in page size (also `/admin/orders`, which is unpaginated) |
| 5 | Host job list checks eligibility once per product, not once per job | Fewer printer-capability queries; unused variables removed |
| 6 | Duplicate Blender renders dropped | Repeated "regenerate" or upload requests for the same model run Blender once while a render is queued or running |
| 7 | Thumbnail recolouring capped at display size | 33 ms → 3.3 ms per new image+colour on the main thread (My Orders only; catalogue unchanged) |

## 2. Files modified

**Branding**
- `assets/brand/`: new. `openlabs3d-logo.webp`, `openlabs3d-logo-dark.webp`, `openlabs3d-logo.png` (transparent master, not loaded by the site), `favicon-32.png`, `favicon-192.png`, `apple-touch-icon.png`.
- `scripts/build_brand_assets.py`: new. Rebuilds every asset above from the supplied artwork.
- `index.html`: favicon links, static topbar and footer logo, asset versions.
- `assets/navigation.js`: `BRAND_LOGO`. The text name stays for screen readers.
- `style.css`: `.brand-logo` rules. Removed the dead `.logo-image` and `.footer-logo` crop rules, which only fitted the old square logo.

**My Orders**
- `assets/buyer-orders.js`: configuration line and swatch, recoloured thumbnails, in-place updates. The per-product `/api/listings/{id}` preview loader is removed.
- `app.js`: the `hashchange` handler keeps the scroll position for query-only changes on routes in `inPageRoutes`.
- `assets/product-visuals.js`: optional `data-tint-size` and a shared `tintKey()`.
- `style.css`: `.bo-config`, `.bo-swatch`, the reveal for tinted thumbnails, and a delayed dim while loading. Removed the unused `.bo-loading`.
- `backend/app/models.py`, `backend/migrations/versions/68a_order_color_snapshot.py`: `order_items.color_hex`.
- `backend/app/pricing.py`: `quote()` also returns `color_hex`.
- `backend/app/operations.py`: snapshots `color_hex`; `orders_data()` batches jobs, history and listings and adds a `thumbnail` URL for publicly viewable products; per-product eligibility in `/host/jobs`.
- `backend/app/render_product.py`: de-duplication of renders already queued or running.

**Tests and documentation**
- `backend/tests/test_order_configuration.py`: new, 6 tests.
- `backend/tests/test_availability_integration.py`: migration head updated.
- `tests/my_orders_browser.py`: new, 57 checks.
- `tests/run_playwright_script.js`: new. Runs the existing `async (page) => …` scripts without the Playwright MCP.
- `tests/buyer_orders_browser.js`: colour label expectation updated.
- `scripts/orders_preview.py`: half of the fixture orders now carry colour snapshots.
- `docs/orders/IMPLEMENTATION.md`: updated.

## 3. Root cause of the My Orders refresh problem (Confirmed)

Measured with Playwright on the development stack before the fix (buyer account, 6 orders). Each status
click caused:

1. **Jump to top.** The only `hashchange` listener (`app.js`) called `render(); scrollTo(0,0)` on *every* hash
   change. Filters, sort and pages live in the hash query (`#orders?category=…`), so every filter click
   was treated as a new page. Measured: `scrollY` went from 260 to 0 on every click.
2. **Full rebuild.** `renderBuyerOrders()` replaced the entire `#app` (`$('#app').innerHTML = buyerOrdersShell(…)`)
   after each response. Before that, it inserted an "Updating orders…" paragraph at the top of the page,
   which pushed the content down: a layout shift, then a full re-mount (`.bo-page` was a new node every time).
3. **Thumbnail flash and repeated fetches.** Each rebuild reset every thumbnail to a camera icon, then
   `loadBuyerOrderPreviews()` fetched `/api/listings/{id}` again for every product: 2–4 extra requests per
   click on 6 orders. That loader also produced a console 404 for each archived product.
4. **Favicon re-request.** Chromium re-requests the favicon on every hash navigation; that file was the
   1.1 MB logo PNG. It was served from cache, but it was still a request on every click.

**Fix:** the cause is addressed, not masked.
- `hashchange` only scrolls to the top when the route path changes, or when the route did not opt in through `inPageRoutes` (only `#orders` opts in).
- `renderBuyerOrders()` keeps the page shell. It highlights the chosen tab at once, keeps the previous orders visible and marks the region `aria-busy`, then swaps only the toolbar (keeping keyboard focus) and the results region.
- Dimming starts only after 120 ms, so fast responses never flash.
- Preview URLs come with the order response, so there are no per-product requests.
- Tinted images are reused from the existing cache, so returning to a filter shows the colours at once.
- A new *page* (Previous/Next) scrolls to the list start, but only if the list top is above the viewport.
- Stale responses are still discarded by the existing request counter.

**After (measured):** one `/api/orders` request per click; `.bo-page` is the same node; scroll position
unchanged (174 → 174 on the development stack, 164 → 164 in the isolated preview); no listing requests;
no console errors; Back/Forward restore filters without rebuilding the page.

## 4. Product colour visualisation

**Data (Confirmed gap):** order lines stored only the colour *slug* (`color='orange'`). Hex values live in
each host printer's current stock (`host_printers.material_colors`). In the development data,
`grey` maps to the custom `#282a2e`, not the standard palette's `#8a8d91`. So neither the
standard palette nor current stock can tell what a past buyer actually saw.

**Solution:**
- **Snapshot at order time.** `quote()` already resolves the exact hex shown to the buyer
  (`options()['colors_by_material'][material][color]`). Order lines now store it in `order_items.color_hex`
  (migration `68a`). Each line of a multi-product order has its own snapshot, and later stock or
  product changes cannot alter it (tested).
- **Historical lines are not guessed.** The 13 existing development lines keep `color_hex=''`. The UI shows
  the recorded name ("PLA · Orange") with no swatch, on the neutral render. This follows the requirement
  "display the recorded color name rather than inventing a color".
- **Preview:** reuses the catalogue's `tintProductImage()`, the same linear-light recolouring as product
  cards; there are no new Blender renders. Recolouring works on a 160 px copy (2× the 72 px thumbnail):
  3.3 ms per new image+colour, 0.1–0.2 ms from cache.
- **Preview URL:** returned by `/api/orders` only for products that are still publicly viewable. The image
  route itself still enforces `can_view`, so access is not widened. Removed products get a labelled
  placeholder.
- **Swatch:** a 12 px swatch with a theme-aware ring (visible for black in Dark mode) plus the colour name,
  so the colour is recognisable even without a preview.

Optional next step (not done): existing lines could be backfilled from current stock. That would be a
guess, not history, so it was not applied automatically.

## 5. Architectural issues

| ID | Severity | Status | Finding | Recommendation |
|----|----------|--------|---------|----------------|
| A1 | High | **Fixed** (§11.2) | **Orders do not pin the CAD revision.** `OrderItem` snapshots title, material, colour, price and `manufacturing_dimensions`, but not `cad_path`. `GET /listings/{id}/cad` serves the listing's *current* model to assigned hosts. If the owner uploads a new model after an order (re-approval required, but older orders are still open), the host prints the new geometry. | Add `order_items.cad_path` (snapshot at `persist_order`). Have hosts download the order's file (`/host/jobs/{id}/cad`). Keep old CAD files while orders reference them. |
| A2 | Medium | Confirmed | **Frontend routing is a chain of global `render` overrides** (10 definitions across `app.js`, `marketplace.js`, `operations.js`, `collection.js`, `configurator.js` ×2, `accounts.js`, `shopping.js`, `equipment.js`, `workspaces.js`), plus `renderOperations`/`workspaceRoute` wrappers. Behaviour depends on script order; every navigation passes through every wrapper; page state is rebuilt by default. This structure produced the My Orders refresh bug. | Introduce a route table (`route → {render, update}`) and migrate pages one at a time. Pages with query-driven views get an `update()` like My Orders now has. |
| A3 | Medium | Confirmed | **Circular import `main` ↔ `operations`.** `import app.operations` before `app.main` fails (`ImportError: cannot import name 'router' from partially initialized module`). It works only because `main` is always imported first. | Move auth dependencies (`require`, `mutate`, …) and helpers to `app/auth.py`; routers import from there. |
| A4 | Low | Partly fixed (§11.6) | Dead code: `save_application` (`PUT /host/application`) always returns 410, but keeps 20 unreachable lines; `custom()` demo in `app.js`; `color_images()` for three legacy colours. | Remove when convenient. |
| A5 | Low | **Fixed** (§11.4) | Colour names are formatted differently: My Orders and host stock use `colorTitle()` ("Green fluo"); product page, cart and admin show raw slugs ("green-fluo"). | Use `colorTitle()` everywhere. |
| A6 | Low | **Fixed** (§11.5) | The browser test suites have drifted from the current UI and data. `tests/availability_browser.js` targets the pre-redesign `.host-color-editor`. `pipette_stand_browser.js` and `product_visuals_browser.js` assume development data that has since changed (stand archived; the 15 mL rack's first PETG colour is now yellow). | Point them at isolated fixtures (like `orders_preview.py`) and update the selectors. |

## 6. Performance bottlenecks

| ID | Severity | Status | Finding | Evidence | Action |
|----|----------|--------|---------|----------|--------|
| P1 | Medium | **Fixed** | `order_data()` ran 2 queries per order (jobs, history) | 10 orders: **35 → 9** queries; equal for 2 and 8 orders (test) | `orders_data()` batch |
| P2 | Medium | **Fixed** | My Orders fetched `/api/listings/{id}` per product on every render | 2–4 extra requests per click → 0 | thumbnail URL in order payload |
| P3 | Medium | **Fixed** | `/host/jobs` ran `supports()` (printer query) for every available job | 20 jobs / 12 products: eligibility alone was 42 queries; whole request now 27; combinations computed once per product (test) | per-request memo |
| P4 | Medium | **Fixed** | Thumbnail recolouring processed the full 640 px render for a 72 px thumbnail | 33 ms → 3.3 ms per image+colour | `data-tint-size` |
| P5 | Medium | **Fixed** (§11.6) | `listing_data()` calls `options()` → `compatible_printers()` once per listing. Catalogue, `/listings/mine` and the unpaginated `/admin/listings` are N+1 | 12-product catalogue page: 16 queries | Load approved printers once per request and pass them to `combinations()` |
| P6 | Low | **Partly fixed** (§11.6) | `cart_data()` quotes per line (printer query each); checkout quotes every line twice | 4-line cart: 11 queries | Same shared printer load as P5 |
| P7 | Low | Confirmed | Visual assets are `Cache-Control: private, no-cache`, so every thumbnail revalidates (304) on each page. Long caching is unsafe today because "Regenerate" rewrites the same URL | — | Add a render version (e.g. status timestamp) to the visual URL, then use `max-age`/`immutable` |
| P8 | Low | Potential | `/admin/orders`, `/admin/listings` and `/admin/users` are unpaginated | grows linearly | Paginate as `/orders?paginated=true` does |

## 7. Security and data-integrity concerns

| ID | Severity | Status | Finding | Recommendation |
|----|----------|--------|---------|----------------|
| S1 | High | **Fixed** (§11.1) | **Cart checkout cannot detect a price change.** `/api/checkout` builds `expected_price_cents` from a fresh server quote and passes it to `persist_order`. Its "Price changed" check therefore always passes, so an order is placed at the new price if pricing rules change between viewing the basket and confirming. (`POST /orders` with a client price is protected.) | Have the client send the per-line prices it showed (`expected_price_cents`); reject with 409 on mismatch, as `POST /orders` already does. |
| S2 | Medium | **Fixed** (§11.4) | **Colour slugs are ambiguous across printers.** `combinations()` merges `material_colors` with `dict.update`, so the same slug with different hex values resolves to whichever printer was read last. The development data shows this: PETG `yellow` is `#f6c700` on one printer and `#f8e45c` on another, and the API serves `#f8e45c`. A host is matched to jobs by slug only, so it may accept a "yellow" order whose shade came from another host's stock. | Reject duplicate slugs with different hex per host (or namespace custom colours). Optionally match jobs on the new `color_hex` snapshot as well. |
| S3 | Medium | **Fixed** (§11.3) | **Host CAD access never expires.** `download_cad` allows any host that was *ever* assigned a job for the listing, including cancelled or completed jobs, and serves every future revision. | Restrict to jobs in `accepted/printing/ready` (and to the order's pinned revision, see A1). |
| S4 | Low | Potential | Configuration is insecure by default: `APP_ENV` defaults to `development`, which disables `Secure` cookies and switches mail to file delivery. `compose.production.yaml` sets it correctly. | Default to production and require an explicit opt-in to development. |
| S5 | Low | Potential | Login and upload rate limits are in-process memory (`rate` dict). They hold for the current single-process deployment but not with several workers or replicas. | Document the single-worker assumption, or move limits to the database or Redis if scaling. |
| — | — | Verified OK | Buyer order ownership (`/orders` filtered by buyer, tested); private files (custom-request files, listing images and visuals gated by owner/admin/`can_view`); CSRF plus same-origin on all mutations; idempotent order and custom-request creation; atomic job transitions (`UPDATE … WHERE status=…`); concurrent-accept test; upload validation by content; no secrets or tokens in logs (render errors log only the file name and Blender stderr). | — |

## 8. CAD rendering and file management

| ID | Severity | Status | Finding | Action |
|----|----------|--------|---------|--------|
| C1 | Medium | **Fixed** | `POST /listings/{id}/render` queued a new Blender run on every click (each up to 180 s, serialised by a lock) | Dropped while the same model is queued or running; a later request renders again (test) |
| C2 | Low | Confirmed | Replacing a model leaves the previous `cad/<hash>` file and `renders/<hash>/` folder on disk. This is partly intentional ("historical assets retained") but unbounded. | Garbage-collect revisions referenced by no listing and no open order (after A1) |
| C3 | — | Verified OK | Temporary files: `TemporaryDirectory` per render; STL/3MF parsing is bounded and validated; filenames are random or content-hashed; render paths are validated by regex. | — |

## 9. Ranked recommendations

Updated 2026-10-31 after the second pass (§11). Resolved: S1, A1, S3, S2, A5, A6, P5 and most of P6.

1. **Medium:** A2, a route table for the frontend; A3, break the circular import.
2. **Low:** P7 (versioned visual URLs), P8 (admin pagination), A4 (`save_application` dead code), C2 (CAD garbage collection, which must now skip files referenced by order lines), S4, S5.

## 10. Test results

**Backend:** `cd backend && uv run --no-project --python 3.12 --with-requirements requirements.txt --with pytest --with httpx python -m pytest -q`
- **91 passed** (85 existing + 6 new in `test_order_configuration.py`): colour snapshot survives stock changes; legacy lines are not guessed; preview URL follows product visibility; fixed query count; one eligibility check per product; one Blender run per model while queued.
- Migration `68a_order_color_snapshot` was applied to the development database after a backup (`backups/pre-order-colour-20261031-080313.db`). All 9 orders and 13 lines are intact.

**Browser:** Python Playwright with the local Chromium; the Playwright MCP cannot find Chrome on this machine.

| Suite | Target | Result |
|-------|--------|--------|
| `tests/my_orders_browser.py` (new) | isolated `scripts/orders_preview.py` | **57/57**: colours and swatches, multi-colour order, legacy order, details, 4 filters (1 request each, page kept, scroll kept, highlighted during a 500 ms delayed load), Back/Forward, rapid clicks, sort, pagination, reload, logo Bright/Dark, favicon, 820/390 px in both themes, no console errors |
| `tests/buyer_orders_browser.js` | same | **pass** (15 groups) |
| `tests/checkout_contact_browser.js` | isolated `scripts/equipment_preview.py` | **pass**: account autofill, saved contact, Buy Now, order persistence, mobile |
| `tests/equipment_revisions_browser.js` | same | **pass**: 24 checks, including host stock and marketplace availability |
| `tests/product_visuals_browser.js` | development stack | Catalogue recolouring, 3D colour change and card memory pass. Fails at a later assertion expecting "white" as the 15 mL rack default; the current development stock lists yellow first (A6, data drift, not a code change) |
| `tests/pipette_stand_browser.js` | development stack | Fails: listing 9 is archived in the development database (A6) |
| `tests/availability_browser.js` | isolated `availability_preview.py` | Fails: targets the pre-redesign `.host-color-editor` stock UI (A6; `assets/equipment.js` was not changed) |

**Logo:** inspected in Bright and Dark on the homepage, sign-in, buyer, host and admin workspaces and the footer.
Only the matching variant is displayed; aspect ratio 431:96 is preserved; 32 px tall on desktop, 27 px on
mobile, clear of the topbar actions at 390 px.

**Measurement scripts** (not part of the suite) used for §3 and §6: a request, scroll and DOM-churn probe of
the filter chips; SQL statement counting with a SQLAlchemy `before_cursor_execute` listener on a temporary
database; `performance.now()` around `tintProductImage()`.

## 11. Second pass: critical marketplace fixes (2026-10-31)

### 11.1 Price integrity (S1)

**Root cause:** `/api/checkout` built each line's `expected_price_cents` from a fresh server quote, so
the order engine's "price changed" check compared the server with itself and always passed. Baskets
stored no price at all.

**Fix (migration `69a_cart_price_confirmation`):**
- `cart_items.confirmed_unit_price_cents` stores the unit price the buyer saw. *Add to Cart* (product page and catalogue card) sends the price on screen.
- `GET /api/cart` flags lines whose authoritative quote differs, with the message "The price of this product has changed from €X to €Y. Please review the updated price before continuing."
- `POST /api/cart/{id}/accept-price` records the buyer's explicit acceptance. If the price moved again, it returns 409 with the newer price.
- *Buy Now* keeps the shown price client-side and checks it at submission.
- Checkout now requires `confirmed`: every line exactly as the page showed it, with its unit price.
- The server re-quotes inside the request's `BEGIN IMMEDIATE` transaction, so no concurrent price, rule or stock change can commit in between. It refuses with 409 when:
  - the basket differs from the page (`cart_changed`);
  - any price differs from the confirmed or accepted one (`price_changed`, listing each change);
  - the stored order prices differ from the confirmed ones.
- Submitted prices are only compared, never charged. The order stores the confirmed integer-cent prices, so `orders.total_cents` is the exact amount a future payment step can collect.
- **Interface:** the basket and checkout summary show the notice under the line, with **Accept updated price**. Checkout and Submit stay disabled until every change is accepted. A change between page load and submission reloads the summary with a one-line "Your order was not placed" banner.
- Lines saved before this migration (`NULL`) ask the buyer to review the current price once.

### 11.2 Pinned manufacturing files (A1)

**Root cause:** order lines did not reference a CAD file, and hosts downloaded the listing's current one.

**Fix (migration `70a_order_manufacturing_snapshot`):**
- Order lines store `listing_version`, `cad_path`, `cad_sha256` and `cad_status`. Material, colour, colour hex, quantity, dimensions and manufacturing dimensions were already snapshotted.
- CAD files are immutable: each upload gets a new random name, opened with exclusive create (`xb`) so it can never overwrite, and nothing deletes them. The official-collection files are content-addressed. `app/manufacturing.py` documents the rule.
- `cad_status` values:
  - `pinned`: recorded at order time, with its checksum.
  - `unverified`: older lines. The purchased version can't be established, so the migration froze them to the model referenced when it ran, with that file's checksum, and flags this in the host and admin views.
  - `none`: the product had no CAD file.
  - `missing`: the file was absent at order time.
- On the development database, all 13 existing lines became `unverified`, with checksums.
- **Downloads:** `/api/jobs/{job_id}/cad` serves the line's own file after verifying its SHA-256 (409 if it no longer matches). It returns `X-Content-SHA256` and `X-OpenLabs3D-Model-Version`.

### 11.3 Manufacturing-file access (S3)

`/api/jobs/{job_id}/cad` re-authorizes every request; there are no reusable or signed links, and responses are `private, no-store`:
- administrators always have access;
- otherwise only the host currently assigned to the job, while it is `accepted`, `printing` or `ready`, the order is not cancelled, and the host's approval and account are active.

Each case returns:

| Case | Response |
|---|---|
| Unassigned, reassigned (after *Reopen job*) or another host's job | 404 |
| Completed or cancelled job | 403 |
| Suspended or no longer approved host | 403 |

`/api/listings/{id}/cad` (the listing's current model) is now owner and administrator only; it previously also allowed any host ever assigned a job for that listing. Files are never deleted on revocation.

**Interface:**
- hosts get **Download STL/3MF** on active jobs, plus a note when the version is unverified;
- administrators get the same link per job in Orders.

### 11.4 Colour identity (S2, A5)

**Root cause:** `combinations()` merged every printer's `{name: hex}` with `dict.update`, so two shades
sharing a name collapsed into one option. On the development data, PETG "yellow" exists as `#f6c700` and
`#f8e45c`, and the API offered only the last one read. Jobs matched hosts by name only.

**Fix (no schema change; colour keys widened to 48 characters in the models and schemas):**
- `availability.offers()` lists every stocked shade as (material, name, hex, host).
- A name stocked in one shade keeps its plain key (`orange`), so existing baskets, links and saved choices are unaffected. A name stocked in several shades becomes one option per shade, keyed `name~rrggbb` and shown as "Orange · #E66A3C". Plain `orange` then no longer quotes.
- Since the colour-snapshot migration (`68a`, first pass), order lines store the exact hex. Hosts now see and can accept a job only if they stock the same material, name **and** shade. Legacy lines without a recorded shade still match by name.
- One shared `colorName()` replaces three inconsistent label functions.
- The host material interface is unchanged.

### 11.5 Updated browser tests (A6)

| Suite | Change | Result |
|---|---|---|
| `tests/availability_browser.js` | stock edits through My Equipment → Materials & Colors; asserts live availability, the now-unavailable basket line, and that the accepted order keeps PETG White `#ffffff` | **pass** (11) |
| `tests/pipette_stand_browser.js` | runs on the new isolated `scripts/catalogue_preview.py` (official collection, real renders and CAD files, fixed stock) | **pass** (8) |
| `tests/product_visuals_browser.js` | same fixture; finds products by collection key; checks the default against the actual eligible combinations instead of "White" | **pass** (7) |
| `tests/checkout_contact_browser.js` | its Buy Now shortcut now stores the shown price, as the button does | **pass** (10) |
| `tests/integrity_browser.py` (new) | basket and checkout notices, a second change before submission, Buy Now drift, two shades of black, host download and revocation, mobile and Dark | **24/24** |

Also unchanged and passing: `equipment_revisions_browser.js` (24), `buyer_orders_browser.js` (15),
`my_orders_browser.py` (57).

**Backend: 101 passed**, the previous 91 plus `tests/test_marketplace_integrity.py` (10 tests):
- price change → acceptance → second change → order at the confirmed price;
- stale displayed price and legacy lines;
- multiple lines with discounts and a changed basket;
- Buy Now;
- pinned CAD after a new upload, plus a tampered-file check;
- access through assignment, reassignment, completion, suspension and cancellation;
- migration upgrade/downgrade/upgrade on a seeded database;
- two shades as two options, with the order surviving a stock change;
- shade matching per host;
- printer cache freshness and one printer query per catalogue page.

### 11.6 Cleanup and measurements

- **Printer lookup per request (P5, P6):** approved printers are loaded once per request (`Session.info`). The cache is cleared on every flush, commit, rollback and bulk statement, and pending changes are flushed before reading it.

  | Request | Queries before | Queries after |
  |---|---|---|
  | 12-product catalogue page | 16 | 5 |
  | 4-line basket | 11 | 8 |
  | host job list (20 jobs) | 27 | 17 |

  Checkout still quotes each line twice; it is now cheap.
- Removed the obsolete 1.1 MB `openlabs3d-logo.png` and its two Caddy bind mounts (`compose.yaml`, `compose.production.yaml`), the preview-server allow-list entry, and its use as a sample upload in `tests/browser_workflow.py`. Both compose files validate; the running Caddy container was recreated without the mount.
- Removed unreachable basket code in `assets/configurator.js`: a second cart-price validator and `changeCart`, both shadowed by `assets/shopping.js`.

### 11.7 Remaining limitations

- Historical order lines are `unverified`: their original CAD version cannot be proven.
- Historical orders keep no colour hex (as before).
- The 3D preview (`model.glb`) of a published product is public by design. It is a render mesh, not the manufacturing file, but it contains the geometry.
- If two hosts later diverge on a colour name, existing basket lines using the plain name become unavailable and must be re-chosen; nothing is substituted.
- SQLite does not enforce `VARCHAR` lengths, so colour keys were widened in the models and schemas without a table rebuild; a future PostgreSQL migration must widen `color` to 48.

