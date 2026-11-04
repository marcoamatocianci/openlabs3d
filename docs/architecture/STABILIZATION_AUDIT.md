# Stabilization audit

Reliability, architecture and bug-fixing pass on branch `v6`, November 2026. It followed Inspect → Reproduce → Fix → Test → Verify → Document, and changed nothing that testing showed to be correct.

**Status words:** Already Fixed (it held under new adversarial tests, no code changed) · Fixed Now · Partially Fixed · Not Reproducible · Still Open.

## Results

| Issue | Initial Status | Root Cause | Resolution | Tests |
|---|---|---|---|---|
| Duplicate startup requests | Confirmed. 21 of 21 routes repeated requests, 11.5 requests per load on average, 4–7 page builds, counts varied between loads | Four scripts and the boot routine called `render()` as they loaded, racing `/auth/me` | **Fixed Now.** One boot sequence (session, then the route's data, then one build). Identical in-flight reads share a response, and any write clears them. Strict assertion restored | `startup_requests_browser.py --strict`, `async_state_browser.py`, `my_orders_browser.py` |
| Kanban pagination reset | Confirmed. After an action a paged stage fell back to its first page. Also found: the page search box was emptied | Refreshes rebuilt from page 1 and no state was carried across the redraw | **Fixed Now.** A stage keeps how much was loaded (up to 50 cards in one read), plus sort, search, scroll and focus, on boards and in Expand section | `pagination_state_browser.py`, `section_modal_browser.py`, `stage_boards_browser.js` |
| History sorting | Confirmed. Sorting a page sorted only what was loaded, or fetched every page first | Sort was done in the browser | **Fixed Now.** `sort=newest\|oldest\|reference` on `/orders`, `/host/jobs` and `/admin/orders`, validated, with an id tie-break. No index added: the measurements did not justify one | `test_stabilization.py` (18 sorting tests), `history_views_browser.js` |
| Checkout price integrity | Not reproduced under attack | — | **Already Fixed.** The €18→€22 scenario, lying clients, rule changes, integer cents, the immutable order snapshot and the checkout race all hold | `test_stabilization.py`, `test_marketplace_integrity.py`, `integrity_browser.py` |
| CAD versioning | Not reproduced | — | **Already Fixed.** Orders keep the CAD they were sold with, through replacement, removal and reassignment. Lines that cannot be verified are flagged, not substituted | `test_stabilization.py`, `test_marketplace_integrity.py` |
| CAD authorization | Not reproduced for manufacturing files; one design exposure found (see Security) | — | **Already Fixed** for downloads: anonymous 401, other users 404, suspended hosts refused, revoked assignments refused, no paths leaked. **Still Open:** public preview meshes, which need your decision | `test_stabilization.py` |
| Material/color consistency | Not reproduced | — | **Already Fixed.** Exact material and shade; a changed shade key is never silently substituted; hosts cannot take their own orders | `test_stabilization.py`, `job_eligibility_browser.py` |
| Admin cancellation | Not reproduced | — | **Already Fixed.** A reason is required, shipped and received products are kept, forged requests are refused | `test_stabilization.py`, `admin_cancel_browser.py` |
| Browser compatibility | Not reproduced | No incompatibility found | **Not Reproducible.** 114 of 114 checks in each of Chromium 156, Firefox 157 and WebKit 27.2. See the limits below | `cross_browser_browser.py` |
| Accessibility | Confirmed. 151 serious axe nodes; the shared `#modal` had no accessible name or focus trap | Teal text at 4.13:1 on the page tint, a hidden label not matching the visible name, dialogs opened without naming | **Fixed Now** for what automated rules and keyboard checks can see: 0 axe violations in 116 scenes. **Not tested with a screen reader** | `accessibility_browser.py`, `keyboard_browser.py` |
| UI consistency | Confirmed, minor | See "UI consistency" | **Fixed Now.** Field heights, typed-text size, focus ring, one validation style, header sizes. Radii were already uniform, label gaps (6–8 px) left alone | Measured before and after; `cross_browser_browser.py`, `approval_colors_browser.py`, `overview_mosaic_browser.py` |

### Added by section 12 and 13

| Issue | Initial Status | Root Cause | Resolution | Tests |
|---|---|---|---|---|
| Stale board after a refused action | Confirmed. A host's next step or a buyer's Mark as received, refused because the state changed, left the old card on screen | Only host Accept and admin Cancel refreshed on refusal | **Fixed Now.** `actionDialog` takes a `refresh` for refusals (403, 404, 409); the host path now covers every step. Used by the buyer's address, received and delete actions, custom request steps and printer suggestions | `frontend_sync_browser.py` (22) |
| N+1 queries | Confirmed on four routes | One read per available job, host or basket line | **Fixed Now.** Statement counts no longer grow with the rows | `test_query_counts.py` |

## A regression this audit introduced and fixed

The startup optimisation in `assets/shopping.js` reused its basket read for up to 3 seconds, even after a basket write in that window, so a line added right after load did not appear. `checkout_contact_browser.js` caught it. Any write now invalidates that read, and `async_state_browser.py` covers it (line added 336 ms after load).

## Files modified

**Application:** `app.js`, `marketplace.js`, `operations.js`, `collection.js`, `index.html`, `style.css`, `assets/buyer-orders.js`, `assets/configurator.js`, `assets/custom-requests.js`, `assets/equipment.js`, `assets/navigation.js`, `assets/shopping.js`, `assets/workspaces.js`, `backend/app/operations.py`, `backend/app/shopping.py`.

**New tests:** `backend/tests/test_stabilization.py`, `backend/tests/test_query_counts.py`, `tests/accessibility_browser.py`, `tests/async_state_browser.py`, `tests/cross_browser_browser.py`, `tests/frontend_sync_browser.py`, `tests/keyboard_browser.py`, `tests/pagination_state_browser.py`, `tests/startup_requests_browser.py`.

**Updated tests:** `tests/my_orders_browser.py` (strict single-request assertion restored), `tests/section_modal_browser.py` (Oldest is now one server-sorted request), `tests/avatar_editor_browser.py` (see Tests).

**Documents:** this file, `docs/UI_UX_AUDIT.md` section 10.

The working tree also holds earlier uncommitted work (admin cancellation, mosaic, colour hierarchy), so `git status` lists more than this. Nothing is committed.

## Database

**No migration.** Latest revision is still `75a_username_display_name`. Users 5, listings 18, orders 19, jobs 26, the same before and after the backend rebuild.

Backup: `backups/pre-stabilization-20261102-231426.db` (integrity check passed). **It was taken after the rebuild, not before:** the first copy failed on a wrong `docker compose cp` flag and the script did not stop. The rebuild ran no migration and changed no rows, so this copy holds the same data, but the order was a mistake.

## Security

**No authentication or authorization bypass was found.** Direct requests, lying clients, forged cancellations, draft previews and old-revision previews were all refused.

**Confirmed exposure, by design, not fixed:** `/api/listings/{id}/visuals/{revision}/model.glb` serves the 3D preview of any approved listing to anyone, and it is exported from the same mesh without decimation (`studio_scene.py`; concluded from the code, because the dev volume held no renders to measure). Official products also have public `/assets/models/*.glb`. So the protected STEP/STL download does not by itself keep the geometry private. The product viewer needs this file, so the options are a decimated preview or server-rendered images only. **This is a product decision.**

## Performance measurements

**Startup** (21 routes, 3 loads each, workflow fixture):

| Measure | Before | After |
|---|---|---|
| Requests per load, average | 11.5 | 6.6 |
| Routes with duplicate requests | 21 of 21 | 0 of 21 |
| Page builds per load | 4–7 | 1–2 |
| Time to settle, average (includes the test's fixed waits) | 0.99 s | 0.85 s |

**SQL statements** (`test_query_counts.py`, QC_ORDERS=294: about 300 orders, 8 hosts, 8 products). Times are single samples, so treat them as indicative; the statement counts are exact.

| Route | Before | After | ms before | ms after |
|---|---|---|---|---|
| `/admin/overview` | 231 | 32 | 35.5 | 18.4 |
| `/admin/orders?paginated=true&per_page=50` | 65 | 17 | 25.1 | 21.6 |
| `/admin/hosts` | 15 | 7 | 12.0 | 9.9 |
| `/cart` (8 lines) | 13 | 6 | 9.9 | 7.4 |

**Investigated, no change needed:**

- **Listeners:** six cycles through each workspace added none on `window` or `document`. Growth appears only on board elements, which are replaced on each draw.
- **DOM:** node counts are stable across those cycles.
- **Expand section:** opens in 6 ms (median of 6, 5 cards).
- **Thumbnails:** one query per page (`listing_thumbnails`).
- **Payloads:** 1.3 KB per order; `/host/jobs?scope=active` is 173 KB at 300 available jobs, because the active board is unpaged by design. Caddy compresses with zstd and gzip.
- **Indexes:** at 200,000 orders, admin history took 16 ms, host 1.7 ms, buyer 0.17 ms. Composite indexes reach about 0.02 ms, which does not justify a migration yet. Reconsider at around 1 million orders, or if history exceeds 100 ms.
- **Account settings:** a buyer with a saved country renders a hidden city list of 9,825 items (10,353 DOM nodes, 42–46 ms on this machine). No problem measured here, so it was left alone; low-end phones were not measured.

## Accessibility

- **Automated:** axe-core 4.14, WCAG 2.2 A/AA rules, 116 scenes across Bright and Dark at 1366 and 390 px. 151 serious nodes before, 0 after. Automated rules find only part of the real problems.
- **Keyboard:** 27 checks (Tab order, Enter and Space, Escape, focus trap and restore).
- **Not tested:** screen readers. No claim of screen-reader compatibility is made.

## UI consistency

| Item | Before | After |
|---|---|---|
| Native select beside a text field | 2 px taller | Same height |
| Admin Settings fields | 40–42 px | 36 px, like other forms |
| Category rows | 32 and 34 px | 34 px |
| Typed text in labelled fields | 12 px | 13.5 px |
| Expand section search beside its sort | 33 and 40 px | 40 px (44 px at 640 px and below, matching the dropdown) |
| Purchase button focus ring | 35% teal | The standard ring |
| Invalid field style | Per form | One rule on `aria-invalid` |
| Buyer and Account page titles | 32 px | 28 px, 24 px on phones, matching workspaces |

Preserved, and still passing their suites: pill navigation, mosaic hierarchy, Expand section, approval colours.

## Tests executed

**Backend:** 194 passed.

**Browser, against isolated fixtures restarted for each suite:**

| Suite | Result | Suite | Result |
|---|---|---|---|
| overview_mosaic | 1051 | job_eligibility | 27 |
| mosaic_board | 994 | integrity | 24 |
| section_modal | 164 | approval_colors | 27 |
| workflow_boards | 125 | keyboard | 27 |
| cross_browser, each of 3 engines | 114 | pagination_state | 21 |
| avatar_editor | 78 | frontend_sync | 22 |
| admin_cancel | 57 | async_state | 17 |
| my_orders | 49 | accessibility | 0 violations in 116 scenes |
| unified_navigation | 48 | startup_requests --strict | 0 of 21 routes with duplicates |
| host_job_dialog | 41 | | |

Passed with a single overall result: `stage_boards`, `history_views`, `workspace_overview`, `admin_approvals`, `admin_user_profile`, `equipment_revisions`, `printer_suggestions`, `checkout_contact`, `buyer_orders`, `account_locations`, `admin_products_type`, `custom_requests_filter`, `pipette_stand`, `product_visuals`, `select`, `availability`, `host_equipment_summary`, `navigation_geometry` (read-only, against the running site).

**Two suites failed in the main run:**

- `checkout_contact` found the regression described above, a real defect that is now fixed.
- `avatar_editor` expected six colours and values no longer in the palette. The server and `docs/account-system/profile-pictures.md` both say five, so the test was obsolete. It now compares the exact values the server accepts, which is stricter.

The basket fix landed during the main run, so the suites touching it were run again and passed: `checkout_contact`, `integrity`, `availability`, `async_state`, `startup_requests --strict`, `my_orders`. The three-engine suites ran after it.

**Not run:**

- `tests/custom_requests_browser.py` writes into the development database, which this task said to preserve.
- `tests/browser_workflow.py` needs Selenium and a configured live URL.

## Remaining limitations

- **WebKit is not Safari.** It is Playwright's WPE build on Linux, run with one locally supplied library. No real Safari, iOS device or Android device was tested. Narrow widths were tested with desktop browsers, not touch emulation.
- **Frontend display rules still mirror some server rules:** `adminOrderCancellable`, `buyerOrderDeletable`, `buyerOrderAddressLocked`, `buyerOrderPartly`, `nextJobStep`. They only decide what to show. The server enforces each one, and a refused action now redraws the page. Removing them needs the API to send allowed actions.
- **Other people's changes appear on the next read.** There is no live push, so an open page stays as it was until an action or navigation.
- **"Longest in this stage"** still loads every page of an active stage, because it needs each job's stage history.
- **Custom requests are unpaginated,** loaded at once.
- **Depth is capped at 50 cards per stage** when restored after an action, so a deeper list returns to 50.
- **Admin reopen** still needs a job to be `accepted`, unchanged.

## Recommendations needing larger changes

1. **Preview meshes:** decide on a decimated preview or rendered images if geometry should stay private (see Security).
2. **Allowed actions from the API:** send each order's and job's allowed actions, and remove the display rules listed above.
3. **Live updates:** server-sent events or polling, if boards should follow other people's changes without an action.
4. **Lazy location lists:** render the city list on demand, if low-end phones show a problem on Account settings.
