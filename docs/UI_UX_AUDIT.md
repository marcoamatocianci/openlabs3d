# OpenLabs3D: workflow boards and platform UI/UX audit

Date: 2026-11-01 · Branch `claude/review-fixes` (working tree) · Scope: Printing jobs, host overview, My
orders, and a consistency and usability review of every page for guests, buyers, printing hosts and
administrators.

Findings are marked **Fixed** (changed and verified in the browser), **Documented** (a recommendation, not
implemented) or **Intentional** (looks inconsistent but is deliberate). Usability problems (§4) are kept apart
from aesthetic suggestions (§3, marked *aesthetic*).

---

## 1. Summary of the Kanban redesign

**One shared component.** `workflowBoard()` in `assets/navigation.js` draws one column per stage, in stage
order. The stages and the statuses each one holds come from the API (`app/lifecycle.py`: each status group
now also returns its `statuses`). As a result, the board places every record in the server's own column, and
the browser keeps no second copy of the lifecycle. Finished work (completed, cancelled) is never in a column;
it lives in History.

| Page | Before | After |
|------|--------|-------|
| **Printing jobs** (host) | One list of every active job, filtered by status chips | Board: **Available · Accepted · In progress · Ready to ship** side by side, with **Awaiting buyer** (shipped, nothing left to do) as a full-width lane underneath. Job history stays a compact, searchable, filterable list |
| **Host overview** | Its own three-column board (separate markup and CSS) | The same component, cards and stages as Printing jobs, without the available pool, at most three cards per stage, with "N more in Printing jobs" |
| **My orders** (buyer) | A long column of large cards, filtered by status chips; details expanded inside each card | Board: **Pending · In progress · Shipping**. Previous orders is a compact searchable list. Both open the same order-details dialog |

**Job cards** show:
- the tinted product preview, product name, material and the ordered colour with its swatch, and the quantity;
- the order reference (the same one the buyer sees), the value, and when the job reached its stage ("Accepted 2 hours ago");
- one primary action (Accept job / Start printing / Mark ready / Mark shipped), with **Details** and **Download STL** as quiet links.

Shipped jobs show the carrier and tracking instead of an action. **Details** opens a dialog with:
- the product and the order;
- the job's progress;
- the pinned model;
- the buyer's contact and delivery address (once the job is yours), and the shipment.

The dialog's footer offers the next step. That step still goes through the existing confirmation dialog and
the same endpoints, so no drag-and-drop state changes are possible.

**Order cards** answer the three buyer questions:
1. **What did I order?** Product previews, names, material, exact colour and quantity.
2. **Where is it?** The column, a short badge ("Awaiting a host", "Accepted", "In production", "Ready to ship", "Shipped"), and a five-step progress bar.
3. **Do I need to do anything?** Shipped products appear in an "On its way" panel with tracking and **Mark as received**. The card is outlined in blue when it needs action.

**Aggregation rule for multi-product orders.** The column is the server's order status
(`operations.sync_order`). An order reaches a stage once every product has. The exception is production,
which starts with the first product printed. The lifecycle is unchanged, so no product's stage is hidden
behind the order's:
- each product shown on the card names its own stage;
- an order with more products than the card shows gets a summary line ("1 received · 1 in production · 1 awaiting a host");
- a product ahead of the order turns the badge into "Partly shipped" or "Partly received";
- the details dialog lists every product with its own stage badge and shipment.

**Delivered column: not added.** The application has no "delivered but still open" state: a shipped product
completes when the buyer confirms receipt. A Delivered column would therefore always be empty or duplicate
Previous orders.

**Responsive behaviour** (container queries, so it follows the board's width, not the window's):
- **Wide** (≥ 876 px for four columns, ≥ 654 px for three): every column side by side, at equal widths.
- **Narrower:** one column at a time (`min(86%, 300px)`), scroll-snapped, with the next column peeking in.
  A strip of stage pills with counts shows which stage is in view and jumps to the others.

| Width | Printing jobs | My orders |
|-------|---------------|-----------|
| 1440 / 1366 / 1280 | 4 columns + lane | 3 columns |
| 1024 (sidebar shown) | scroll, ~2 columns in view, strip | 3 columns |
| 768 | scroll, 2 columns + peek, strip | 3 columns |
| 430 / 390 / 375 / 320 | 1 column + peek, strip | 1 column + peek, strip |

Never any page-level horizontal overflow. After an action, the board keeps its sideways position (per
address); a stage link (`#host/jobs?group=ready`, `#orders?group=shipping`) opens on that stage and marks it.

## 2. Shared components created or reused

| Component | Where | Used by |
|-----------|-------|---------|
| `workflowBoard`, `bindWorkflowBoards`, stage strip, `syncWorkflowStrip`, `scrollToStage` | `navigation.js` | Printing jobs, host overview, My orders |
| `.wf-*` styles (column, card, lane, strip, section head, toolbar) | `style.css` "Workflow boards" | the same three pages; replaces the separate `.hb-*` overview board |
| `orderLineThumb` / `orderLineConfig` (tinted preview, swatch + "Material · Colour") | `navigation.js` | job cards, job history rows, order cards, order rows, both details dialogs. Host and buyer now name colours identically |
| `openReview` / `reviewSection` / `reviewItem` (detail dialog) | moved from `workspaces.js` to `navigation.js` | admin approvals (unchanged), job details (new), order details (new) |
| `actionDialog` (themed confirmation with in-dialog errors and a busy state) | reused | every job step, Mark as received, address change, order deletion |
| `scopeNav` (Active/History pills + status chips), `pager`, `emptyState`, `statusBadge`/`jobBadge` | reused | both boards and both history views |
| `--control-radius` | `style.css` | every button, text field, dropdown and search field |

## 3. UI inconsistencies discovered

Measured with a computed-style inventory across 38 pages (7 guest, 9 buyer, 9 host, 13 admin) at
1440 px and 390 px.

| # | Finding | Evidence | Status |
|---|---------|----------|--------|
| I1 | Controls had five corner radii | Buttons 5, 6, 7, 8 and 9 px. Fields 4 px (account, settings, auth), 6 px (search), 7 px (wizards, custom requests), 8 px (dropdowns) | **Fixed**: one `--control-radius` (7 px) for buttons, fields, dropdowns and search. Pills stay fully rounded; avatars, icon toggles and text links are excluded on purpose |
| I2 | Two date formats | "11/1/2026, 4:09:09 PM" (admin, job history, order updates, activity) against "Nov 1, 2026" (My orders) | **Fixed**: `safeDate` is now medium date + short time, e.g. "Nov 1, 2026, 4:09 PM" |
| I3 | Two names for one order | Hosts saw "Order #9", buyers "OL3D-A79FAD5E6D2B4815" | **Fixed**: jobs carry `order_reference`; hosts see the buyer's reference everywhere |
| I4 | Colour shade dropped for hosts | Host rows showed "PLA · Black"; the buyer saw "PLA · Black · #1B1B1B" for the same line | **Fixed**: one helper for both |
| I5 | Same state, two colours | "Accepted" was amber for buyers and blue for jobs and administrators | **Fixed**: amber = waiting for someone to take it, blue = being made or delivered, green = done, red = cancelled, for orders and jobs alike. Approval and payment-like states keep their own meaning |
| I6 | Two vocabularies on My orders | Order badges ("Accepted · awaiting printing", "Production in progress", "Ready for delivery") differed from product stages | **Fixed**: one set: Awaiting a host · Accepted · In production · Ready to ship · Shipped · Received / Completed |
| I7 | Destructive actions looked neutral | Admin "Cancel order" and "Suspend" (hosts, users) were plain ghost buttons, often the only button in a row | **Fixed**: quiet red text with a red hover, still secondary |
| I8 | Two board implementations | Host overview had its own `.hb-*` board | **Fixed**: one component (§2) |
| I9 | Field heights vary | 32 to 42 px across forms (account fields 36 px, admin search 33 px, settings 40–42 px, wizards 36–38 px) | **Documented** (R3) |
| I10 | Five page-title sizes | Hero 62 px, public pages 40 px, sign-in 34 px, My orders and Account 32 px, workspaces 28 px. The buyer's own pages mix 32 px (My orders, Account) and 40 px (Basket, Custom requests) | **Documented** (R4), *aesthetic* |
| I11 | Buyer page widths | Account ≈ 880 px, My orders 1080 px, Custom requests 1180 px, Basket ≈ 1205 px | **Partly fixed**: My orders now 1180 px, like Custom requests, which also gives the board room. **Documented** (R4) |
| I12 | Card radii | 10 px (section cards, lists, stats, board cards), 12 px (account settings cards, board columns), 14 px (inventory cards), 8 px (About panels), 16 px (product cards) | **Documented**, *aesthetic*. Product cards are browsing cards and may differ; 12/14 px could become 10 px |
| I13 | Order references | Monospace in admin Orders, proportional elsewhere | **Documented**, *aesthetic* |
| I14 | Two eyebrow styles | `.eyebrow` (10 px, 2 px tracking) on public pages, `.ws-crumb` (11 px, .08 em) in workspaces | **Documented**, *aesthetic*. The orange dot is used on both and nowhere else, as established |
| I15 | Custom-request "Quoted" vs "Accepted" | Admins see "Quoted", customers "Accepted · quote sent" | **Intentional** (`custom-requests.js`: internal vs customer wording) |
| — | Navigation pills | Every `.chip`, `.segment`, `.eq-tab` is 44 px tall and fully rounded, with the same active colour, on all 38 pages, 8 widths and both themes | Verified consistent (`tests/unified_navigation_browser.py`) |
| — | Status badges | One size (23 px), shape and weight everywhere | Verified consistent |

## 4. Usability problems discovered

Actual problems, as opposed to the aesthetic suggestions marked above.

| # | Problem | Status |
|---|---------|--------|
| U1 | **Broken attention link.** Admin overview "1 printing job without a host → Review" opened *Pending orders*, which was empty: the order had another product in production, so it was *In progress* | **Fixed**: `GET /admin/orders?attention=unassigned` lists orders with any job still waiting for a host, whatever the order's stage; the overview links there with an explanatory banner |
| U2 | **One stage at a time.** Printing jobs and My orders showed either one status at a time (a chip) or everything in one long undifferentiated list | **Fixed**: boards (§1) |
| U3 | **Mixed orders hid product stages.** A multi-product order was labelled by the order's aggregate only; seeing that one product had shipped, or was still unassigned, meant opening the details | **Fixed**: product stages on the card, summary line, "Partly shipped/received", per-product badges in the details |
| U4 | **No shared order identifier** between host and buyer, so they could not refer to the same order | **Fixed** (I3) |
| U5 | **Inline details caused long pages.** Order details expanded inside the card, and each job row had its own "Buyer contact and delivery" disclosure | **Fixed**: details dialogs, so cards stay a fixed, scannable size |
| U6 | **Disabled pager on one page.** The catalogue showed disabled Previous/Next buttons when everything fit on one page | **Fixed**: just "N matching published listings" |
| U7 | **Two primary buttons.** My listings (empty) had "New listing" and "Create listing", two primary buttons with different labels for one action | **Fixed**: one "New listing" (the header action appears once listings exist) |
| U8 | **Focus loss after a refusal.** A job taken meanwhile left focus on `<body>`, or on a hidden filter chip | **Fixed**: focus goes to the job's next step, its card, the column it was in, or (empty board) the Active jobs tab |
| U9 | **No "Is there anything to do?" signal** on My orders | **Fixed**: an "On its way" panel with Mark as received, and an outlined card |
| U10 | **No deadline or ETA data** exists in the backend | **Documented** (R6). Cards show time in stage instead ("Listed 3 hours ago", "Shipped yesterday") |
| U11 | **Confirmation dialogs on every job step** | Considered, kept: each step is visible to the buyer and cannot be undone by the host. "Mark shipped" collects tracking in the same dialog |

Checked and found sound:
- One obvious primary action per page and per card.
- Loading states disable confirm buttons, so steps cannot be submitted twice.
- Filters and scope switches update in place, with no page reload or scroll jump.
- History loads only when opened.
- Counts in pills, column headers and the navigation badge agree with the server after each action (tested).

## 5. Changes implemented

Backend changes are additive response fields and one read-only filter value: no migration, no lifecycle,
pricing, matching or eligibility change.

- `backend/app/lifecycle.py`: each status group also returns `statuses`.
- `backend/app/operations.py`:
  - `listing_thumbnails()` (one query, publicly viewable products only, the same rule the image route enforces);
  - jobs carry `item_id` and `item.thumbnail`; order lines carry `id`;
  - `/host/jobs` rows carry `order_reference`;
  - `/admin/orders?attention=unassigned`.
- `backend/tests/test_operations.py`: assertions for the above (group statuses match `JOB_SCOPES`, shared reference, item mapping, unassigned filter).
- `assets/navigation.js`: board component, stage strip, scroll memory, shared order-line preview and colour, shared detail dialog.
- `assets/workspaces.js`:
  - job card, job history row, job details dialog and progress, Printing jobs board and history, host overview board;
  - focus return after steps;
  - the attention filter and a single listing call to action;
  - quiet-danger styling for Cancel order and Suspend.
- `assets/buyer-orders.js`: board, previous-orders rows, order-details dialog (address change, receipt and deletion work from it and refresh it in place), loading of every current order (pages of 50), labels and tones.
- `style.css`:
  - "Workflow boards" (`.wf-*`), shared order-line styles, job-history and previous-order row grids, detail-dialog product rows;
  - My orders card, row and dialog rules, replacing the old card rules;
  - removed the `.hb-*` overview board;
  - control radius; danger-text hover; My orders width.
- `operations.js`: `safeDate` format. `marketplace.js`: single-page catalogue count. `index.html`: asset versions (`workflow-1`).
- `scripts/workflow_preview.py` (new): an isolated fixture with orders and jobs in every stage, placed and advanced through the real API (port 18102).
- Tests:
  - new `tests/workflow_boards_browser.py`;
  - `tests/buyer_orders_browser.js` rewritten for the board, with the same coverage plus the new behaviour;
  - `tests/my_orders_browser.py`, `tests/host_job_dialog_browser.py`, `tests/job_eligibility_browser.py` and `tests/history_views_browser.js` updated to the new markup.
- Kept from the working tree: the buyer's "delete an order nobody has accepted" feature. Its button now sits in the order-details dialog.

## 6. Where Kanban is beneficial

| Area | Why | Status |
|------|-----|--------|
| Printing jobs (host) | Each job moves through five stages with one host action per stage; hosts work across stages at once | Implemented |
| Host overview | Summary of the same board | Implemented |
| My orders (buyer) | Few items per buyer; the question is "where is each order?" | Implemented |
| Admin custom requests | Three active states (Submitted → Under review → Quoted/Accepted) worked one request at a time | **Recommended later** (R5): volumes are low today and each request needs its details dialog; the list with status chips works. The component can be reused as is |
| Admin orders | — | A compact overview already exists: stage pills with counts, plus the overview's "Needs attention" links (now correct, U1). A board would hide search and comparison, which administrators need here |

## 7. Where Kanban would be inappropriate

- **Admin approvals:** a review queue. One item is decided at a time, in a dialog; there is no progression to watch.
- **Admin users, printing hosts, products, printers, materials, categories, activity:** data management. Search, filter and compare rows, so tables and lists fit.
- **Host product listings:** draft, pending review, published, rejected, archived. Most listings sit in a final state, and a host has few; a list with status badges and filters is clearer. Reconsider only if hosts manage many drafts.
- **Catalogue:** browsing, so cards.
- **Job history and previous orders:** finished work; compact searchable lists.

## 8. Remaining recommendations, by impact

1. **High: deploy frontend and backend together.** The boards need the new `statuses` field. The local Docker backend was rebuilt (database backed up first, see §10).
2. **High: replace the chain of global `render` overrides with a route table** (A2 in `docs/architecture/CODEBASE_AUDIT.md`). Both boards update in place, but the workspace still rebuilds `#app` after each step.
3. **Medium: one field height** (40 px) for text fields, selects and dropdowns across account, settings, admin search and wizards (I9).
4. **Medium: one page-header pattern** for the buyer's own pages (My orders, Custom requests list, Account, Basket): the same title size, width and eyebrow (I10, I11).
5. **Medium: admin custom-requests board** when request volume grows (§6).
6. **Medium: an estimated completion date**, entered by the host on accepting a job, so cards can show a real deadline (U10). This needs a backend field and a migration, which were out of scope.
7. **Low: board search updates column counts** (counts are currently the totals while searching).
8. **Low: sticky column headers, or scrolling inside columns**, if a host regularly has more than ten jobs in one stage.
9. **Low, aesthetic:** card radii (I12), monospace references (I13), eyebrow styles (I14).

## 9. Test results

Browser suites run with Python and Node Playwright on Chromium 1248, each against a freshly started isolated
fixture (never the development database). After the final changes:

| Suite | Fixture | Result |
|-------|---------|--------|
| `tests/workflow_boards_browser.py` (new) | workflow_preview | **58/58** |
| `tests/my_orders_browser.py` | orders_preview | **57/57** |
| `tests/buyer_orders_browser.js` | orders_preview | **passed** (17 groups) |
| `tests/host_job_dialog_browser.py` | catalogue_preview | **41/41**, no native dialogs |
| `tests/job_eligibility_browser.py` | catalogue_preview | **26/26** |
| `tests/integrity_browser.py` | catalogue_preview | **24/24** |
| `tests/history_views_browser.js` | equipment_preview | **passed** |
| `tests/workspace_overview_browser.js` | equipment_preview | **passed** |
| `tests/admin_approvals_browser.js` | equipment_preview | **passed** |
| `tests/custom_requests_filter_browser.js` | catalogue_preview | **passed** |
| `tests/account_locations_browser.js` | catalogue_preview | **passed** |
| `tests/checkout_contact_browser.js` | equipment_preview | **passed** |
| `tests/unified_navigation_browser.py` | workflow_preview | **passed** |
| Backend `pytest tests/` (all files) | temporary databases | **152 passed** |

`tests/unified_navigation_browser.py` covers buyer, host and admin; 1440, 1280, 1024, 768, 430, 390, 375 and
320 px; both themes. On every page it checks pill height, radius and active colour and the absence of page
overflow, and it clicks the first and last pill of each group.

What the new board suite verifies:
- **Data:** columns in API stage order; column counts match the API; each job and order appears once, in its status's column; no completed or cancelled item on a board. History lists the closed items, with details.
- **Cards:** primary action per stage; colour swatch from the checkout snapshot; recoloured previews; order reference, material and quantity.
- **Actions:** accept from the board, which moves the card, updates counts and the navigation badge, causes no reload and moves focus to the next step. Details → step closes the details first. A stage link marks its column.
- **Narrow widths (320, 390 and 375 px):** one column plus a peek; the strip shows the stage in view and jumps; a step keeps the board's position.
- **My orders:**
  - a mixed order is in progress, with every product stage counted and the shipped product confirmable from the card;
  - address change from the details refreshes them;
  - delete starts on Cancel and removes the card;
  - Mark as received moves the order to Previous orders, which are searchable by reference;
  - previous-order details show "Received" with the address locked.

**Visual inspection** (screenshots reviewed, not only asserted):
- Printing jobs, host overview and My orders at 320, 375, 390, 430, 768, 1024 and 1440 px in Bright and Dark: 42 captures, 0 px overflow each.
- Job and order details dialogs at 1440 and 390 px.
- All 38 pages for the four roles at 1440 and 390 px: 0 px overflow on every page.
- The local Docker site with the development accounts after the backend rebuild: Printing jobs, Job history, My orders, Previous orders, admin overview and the new attention filter render with no console errors.

## 10. Unresolved limitations

- **No deadline or estimated delivery** exists in the data model (U10, R6).
- **Current orders load in full** (pages of 50, fetched together). That is right for a buyer's active orders, but there is no upper bound for an extreme account.
- **Board search filters cards** but leaves column counts at their totals (R7).
- **Accessibility was verified with keyboard and focus checks and ARIA structure**, not with a screen reader. Columns are labelled sections with headings, counts carry text for assistive technology, and the strip uses buttons.
- **Development database:** before the Docker backend was rebuilt to serve the new response fields, it was backed up to `backups/pre-workflow-boards-20261101-162538.db`. There was no migration.
- **Out of scope by instruction:** prices, matching and eligibility rules, CAD models, lifecycle semantics, payments and migrations are unchanged.
