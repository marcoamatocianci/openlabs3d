# OpenLabs3D: workflow boards and platform UI/UX audit

Date: 2026-11-01 · Branch `claude/review-fixes`, then `v6` · Scope: Printing jobs, host overview, My
orders, and a consistency and usability review of every page for guests, buyers, printing hosts and
administrators. A second pass the same day separated the host overview from Printing jobs (§1, "Second
pass").

Findings are marked **Fixed** (changed and verified in the browser), **Documented** (a recommendation, not
implemented) or **Intentional** (looks inconsistent but is deliberate). Usability problems (§4) are kept apart
from aesthetic suggestions (§3, marked *aesthetic*).

---

## 1. Summary of the Kanban redesign

> Later passes replaced this board: §6 (third, fourth and fifth pass) describes the current `stageBoard()`, now the only board component.

**One shared component.** `workflowBoard()` in `assets/navigation.js` draws one column per stage, in stage
order. The stages and the statuses each one holds come from the API (`app/lifecycle.py`: each status group
now also returns its `statuses`). As a result, the board places every record in the server's own column, and
the browser keeps no second copy of the lifecycle. Finished work (completed, cancelled) is never in a column;
it lives in History.

| Page | Before | After |
|------|--------|-------|
| **Printing jobs** (host) | One list of every active job, filtered by status chips | Expandable board (second pass): **Available · In production · Ready to ship · Awaiting buyer**. One stage is open with detailed cards; the others are compact columns. Job history is a secondary button to a compact, searchable, filterable list |
| **Host overview** | Its own three-column board (separate markup and CSS) | Second pass: four stage counts, what needs attention, one line of activity and **Manage printing jobs**. No job cards |
| **My orders** (buyer) | A long column of large cards, filtered by status chips; details expanded inside each card | Board: **Pending · In progress · Shipping**. Previous orders is a compact searchable list. Both open the same order-details dialog |

### Second pass: a simpler overview and an expandable Printing jobs board

The first pass gave the overview the same board as Printing jobs, so the two pages repeated each other.
They now answer different questions.

**Host overview: "what is happening right now?"**
- **Four summary cards:** Available, In production, Ready to ship, Awaiting buyer. Each shows its count, an icon in the stage's status colour and one line of description. The counts come from the same API response as the board, so the two pages always agree.
- **Each card opens Printing jobs on its stage** (`#host/jobs?group=ready`).
- **Alerts, only when there are any:** no approved printers; no materials in stock (so no job can match); an equipment update awaiting review or not approved; listings returned with review notes.
- **One activity line:** jobs in hand and their value, completed jobs, published listings.
- **Actions:** **Manage printing jobs →** is the page action, with Job history as a quiet link.
- **Removed:** the board, the job cards and the previous four stat cards.

**Printing jobs: where the work is done.** It uses `stageBoard()` in `navigation.js`, built on the same
stages from the API and the same card renderer.
- **All collapsed** (sixth pass, §6): the open stage's header collapses the board into one proportional mosaic.
- **Wide** (board ≥ 680 px), the **balanced mosaic** (fifth pass, §6):
  - the open stage takes two thirds of the row, or 5/7 (about 71%) from a board width of 900 px, and shows full job cards;
  - the other stages share a compact grid on the right, which stays in view while a long stage scrolls. Each panel shows an icon, name, count and coloured previews, and is sized by its job count. Clicking one opens it (WAI-ARIA accordion pattern: `aria-expanded`; `aria-disabled` on the open header).
- **Narrower** (phones and small tablets): rounded stage pills, 2×2 on phones and one row of four from 600 px, with the open stage underneath.
- **Switching** is local: no request and no reload. Panels slide to their new places (0.32 s) only while switching, never on load or resize, and not at all with reduced motion.
- **Remembering the stage:** the open stage is written to the address (`replaceState`, no history entry) and to the session. A refresh, or a return from another page, reopens it. Without either, the first stage with work opens.
- **Old links** (`?group=accepted`, `?group=in-progress`, `#host/jobs/accepted`) open In production.
- **After a step,** the open stage stays open. Focus goes to the job if it is still there, otherwise to the card now in its place. The stage the job moved to lights up once with its new count.
- **Search** filters cards in every stage and turns the counts into match counts. Stages without matches are dimmed, and the open stage says when none of its own cards match.

**Accepted vs In progress.** The host sees one stage, **In production** (`JOB_SCOPES`: `accepted` and
`printing`). Accepting puts a job there at once. Its next step is **Mark ready to ship**: the backend now
allows `ready` from `accepted` as well as from `printing`. The internal states are kept:
- **Reporting the print start is optional.** `printing` still exists, and "Report printing started" is offered only in the job details.
- **Nothing is recorded that the host did not report.** A job that skips the report gets no `printing` status and no `job.printing` event.
- **The card says which:** a small Accepted or Printing badge.
- **Administrators** may cancel an order at any stage before completion, whatever the host reported (fourth pass, below). Reopening a job for another host is still allowed only while it is `accepted`.
- **The buyer still sees "In production"** once a print start is reported, or when another product of the order is further along. The lifecycle groups for orders are unchanged.

**Job cards** (the open stage of Printing jobs) show:
- the tinted product preview, product name, quantity, material and the ordered colour with its swatch;
- dimensions and the model file ("STL model");
- the order reference (the same one the buyer sees), the value, and when the job reached its stage ("Accepted 2 hours ago");
- in In production, whether printing was reported;
- the actions this stage allows: Accept job, Mark ready to ship or Mark shipped, plus **Details** and **Download STL** (only once the job is yours).

Cards stack when the stage is narrower than 420 px.

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

| Width | Printing jobs (second pass) | My orders |
|-------|---------------|-----------|
| 1440 / 1366 / 1280, 900 | 4 stages side by side, one open | 3 columns |
| 1024 (sidebar shown) / 768 | 4 stage pills in a row, one stage below | 3 columns |
| 430 / 390 / 375 / 320 | 2×2 stage pills, one stage below | 1 column + peek, strip |

Never any page-level horizontal overflow. After an action, My orders keeps its sideways position (per
address) and Printing jobs keeps its open stage. A stage link (`#host/jobs?group=ready`,
`#orders?group=shipping`) opens on that stage.

## 2. Shared components created or reused

| Component | Where | Used by |
|-----------|-------|---------|
| `stageBoard`, `mosaicPlan`, `arrangeMosaic`, `openSection` | `navigation.js` | every Active/History list (`workflowBoard` was removed in the fifth pass) |
| `stageBoard`, `openStage`, `syncStageMatches` (expandable board) and `.sb-*` / `.jc-*` styles | `navigation.js`, `style.css` | Printing jobs |
| `.ho-*` summary cards and alerts | `workspaces.js`, `style.css` | Host overview |
| `.wf-card`, `.wf-link`, `.wf-toolbar`, `.wf-empty`; `.sb-*` (board and mosaic); `.ss-*` (Expand section) | `style.css` | every stage board; replaces the separate `.hb-*` overview board |
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

**Third pass (product decision, 2026-11-01):** every Active/History list now uses the expandable stage board
of Printing jobs, including the places §7 first advised against. What §7 was protecting is kept: search
(server-side on paged lists, with a match count per stage), comparison (cards keep the same anatomy in every
stage) and paging through long histories ("Load more" within a stage, 12 cards at a time).

| Area | Stages | Loading |
|------|--------|---------|
| Printing jobs (host) | Available · In production · Ready to ship · Awaiting buyer | all active jobs at once |
| Job history (host) | Completed · Cancelled | first page of each stage (`columns=true`), Load more |
| My orders (buyer) | Pending · In progress · Shipping | all current orders |
| Previous orders (buyer) | Completed · Cancelled | first page of each stage, Load more |
| My requests (buyer, host) | Submitted · Under review · Accepted / Request history: Closed (one column) | all at once |
| Admin orders | Pending · In progress · Shipping / Completed · Cancelled | first page of each stage, Load more |
| Admin approvals | Host applications · Equipment updates · Listings · Printer suggestions / history by the same types | pending all at once; history by page |
| Admin custom requests | Submitted · Under review · Quoted / Closed | all at once |
| Host overview | A summary, not a board (four stage counts) | — |

`stageBoard` gained opt-in options for this, so Printing jobs is unchanged: counts from the API (`count`,
`total`), "Load more" and Try again per stage (`load`, `onLoad`), a single full-width column when a scope has
one stage, `rememberStage` (address + session), a one-time highlight of the stage an item moved to
(`stageBumpNext`), and `boardCard`, the shared card anatomy (preview · title and details · value and time ·
note · Details and at most one main action; read-only cards put Details under the value, with no footer).

Measured on the same fixture data (content height in px, before → after; lower is more compact):
Previous orders 807 → 483 (1366) and 1470 → 598 (390); My requests 1874 → 686 and 2355 → 947; Admin order
history 739 → 338; Admin orders 817 → 463 and 1467 → 675; Request history 846 → 523. Taller than before:
Job history with a single job (220 → 414; 383 → 511 on a phone: the stage header and the richer card),
pending Approvals (400 → 539; 555 → 812 on a phone: the stage header, and four stage pills on a phone) and
admin Request history (367 → 386).

**Fourth pass (2026-11-02): a mosaic on Printing jobs, generalised by the fifth pass below.** The collapsed stages no longer sit as narrow
columns. They share a grid on the right of the open stage (`mosaicPlan` in `navigation.js`):
- **Sized by count, on a bounded scale:**
  - no jobs: a slim one-line bar;
  - 1–2 jobs: small;
  - 3–5 jobs: medium, with the stage hint when it spans the grid;
  - 6 or more: large, always across the grid, with the hint and bigger previews.

  A busy stage stands out without crowding the others.
- **Arranged by the counts:**
  - the panels stay in workflow order, in rows of one panel across both columns or two side by side;
  - small and medium panels pair up wherever that makes the mosaic shortest (a small dynamic program over the three or so panels), so rows are always full and nothing is hard-coded;
  - two columns from a board width of 860 px, one column from 760 px; narrower, the stage pills as before.
- **Previews:** up to three on a half-width panel and five across the grid, always on one row, with "+n" for the rest.
- **Switching:**
  - the open stage moves to the main area and the old one joins the mosaic. In the page order, the open stage comes first, as on screen;
  - panels slide from where they were, and a growing panel is revealed from its old size rather than stretched (FLIP with `clip-path`; text never distorts);
  - a switch during a switch carries on from where the panels are drawn;
  - with reduced motion the switch is instant;
  - switching from far down a long stage brings the board's top back into view.

**Fifth pass (2026-11-02): Balanced Mosaic everywhere, and Expand section.** Three levels of detail, on one component:
1. **Collapsed mosaic:** a compact overview of the other stages.
2. **Open stage:** its cards, inside the board.
3. **Expand section:** all its items, in a large dialog.

*One component.* `workflowBoard` and its styles are gone. My orders now uses `stageBoard` like every other
Active/History list, so the mosaic and the dialog need no per-page code; each board only declares its noun, sort
options and whether its API can search. Single-stage scopes (Request history) stay one full-width column, with
Expand section.

*The mosaic (`mosaicPlan`, replacing the fourth pass's rules):*
- **Bounded sizes:** no jobs · 1–2 · 3–5 · 6–10 · more, with weights 2, 3, 4 and 5 and a fixed slim bar for no jobs. 40 jobs get less than three times the room of 3.
- **Arrangement:** each candidate is scored by how close each panel's area comes to its weight, with a small cost per row; ties go to the busiest stage across the grid. The largest two sizes always span the grid, and two panels stack, because side by side they would be too narrow. Workflow order is kept, and every row is full.
- **A rectangle with the open stage:** the rows are `fr` tracks, so the mosaic matches the open stage's height, up to a maximum that grows with the workload. A short list gives one aligned rectangle; a long one leaves the mosaic at its maximum, sticky, instead of stretching into empty tiles.
- **What it reacts to:** switching stage, new counts, the board's width (container queries: one column from 680 px, two from 780 px, the wider split from 900 px) and a search, which sizes each panel and its previews by what still matches.

*Expand section (`openSection`):*
- **Two steps:** a collapsed panel only opens its stage. The button is on the open stage alone, and is hidden when the stage is empty.
- **The dialog:** a native modal at 92% of the screen (nearly full-screen on a phone), with internal scrolling, a locked page behind, focus kept inside, Escape to close and focus returned to the button. It reuses the board's cards and actions. With text in the search, the first Escape clears it.
- **No second copy of the state:** its items come from the board's own columns. Whenever the page redraws after an action, the dialog redraws from the new columns, so a job that moved on leaves it and the counts follow. Focus stays on the same card, or the one now in its place. Opening it makes no request.
- **Details and confirmations** open above it under a lighter scrim, so one page stays dimmed. Escape closes only the top one, and focus returns to its button.
- **Large stages:**
  - cards are drawn 24 at a time, with Show more;
  - paged stages load their next page once, and the board gets the same page;
  - search runs in the browser for stages it holds completely, on the server for paged ones (debounced, one request), and for approval history (no server search) after loading every page;
  - a sort other than the server's own order loads every page first (in pages of 50), so the order is true.

**Sixth pass (2026-11-02): colour hierarchy and the all-collapsed overview.** Every stage board now has three states:

| State | What it shows | How you get there |
|-------|---------------|-------------------|
| **Overview** | Every stage a tile of one proportional mosaic | Click the open stage's header (or its pressed pill on a phone) |
| **Focus** | One open stage, the others a neutral mosaic | Click a tile or a panel |
| **Popup** | All the stage's items | Expand section, on the open stage only |

*Colour.* The open stage always leads:
- **Open stage:** the stage's tone on its header, a tinted border, a soft shadow, a 17 px title, full-colour previews.
- **Side panels in Focus:** neutral whatever their tone: a quiet surface, a thin border, a muted icon with one 6 px status dot, a small count, slightly desaturated previews. Colour means status, so Approvals' amber is on the open queue's header and in dots, and Approved and Rejected keep green and red.
- **Tiles in the Overview:** each in its stage's colour at 40% of the header's tone (72% under the mouse), at one level: same type, border and no lift.

*The overview's layout (`overviewPlan`).* An ordered treemap: stages keep their workflow order, and of every way to cut the rectangle (side by side or stacked, recursively) it takes the one with the most comfortable tiles, growing the mosaic if any tile would fall below its minimum.
- **Weights are bounded and nonlinear:** 1 for no items, then `1.6 + 1.5·log2(n + 1)`, capped at 9 (reached at about 30 items).
- **A minimum share** keeps near-empty stages usable (enough to fit one row of tiles) without inflating the mosaic. Above it, areas follow the weights exactly, and the height follows the total workload, within a maximum.
- **Three width classes** (board under 520 px, under 780 px, wider) are computed up front and applied by container queries, so resizing needs no script. Each tile adapts its own content with a size container query.
- **Hover and keyboard focus** lift a tile just perceptibly (`scale(1.012)`, 1 px up, a soft shadow). Neighbours do not move and are never touched. No hover effect on touch screens; none of the movement with reduced motion.
- **A search** re-plans it from the stage's matches.

*Remembering.* All collapsed is explicit: `group=none` (`type=none` on Approvals) in the address and in the session, so a refresh, a return or Back and Forward never reopens a stage. A first visit still opens the first stage with work. A link to a stage, or an overview warning's `attention` link, opens that stage.

## 7. Where Kanban would be inappropriate

- **Admin users, printing hosts, products, printers, materials, categories, activity:** data management. Search, filter and compare rows, so tables and lists fit.
- **Host product listings:** draft, pending review, published, rejected, archived. Most listings sit in a final state, and a host has few; a list with status badges and filters is clearer.
- **Catalogue:** browsing, so cards.
- Approvals, job history and previous orders were listed here before the third pass (§6).

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

### Second pass (host overview and expandable Printing jobs)

Run after the second-pass changes, each suite against a freshly started fixture:

| Suite | Fixture | Result |
|-------|---------|--------|
| `tests/workflow_boards_browser.py` (host part rewritten) | workflow_preview | **130/130** |
| `tests/host_job_dialog_browser.py` | catalogue_preview | **41/41**, no native dialogs |
| `tests/job_eligibility_browser.py` | catalogue_preview | **26/26** |
| `tests/integrity_browser.py` | catalogue_preview | **24/24** |
| `tests/my_orders_browser.py` | orders_preview | **57/57** |
| `tests/buyer_orders_browser.js` | orders_preview | **passed** (17 groups) |
| `tests/history_views_browser.js`, `tests/workspace_overview_browser.js` | equipment_preview | **passed** |
| `tests/admin_approvals_browser.js`, `tests/checkout_contact_browser.js` | equipment_preview | **passed** |
| `tests/custom_requests_filter_browser.js`, `tests/account_locations_browser.js` | catalogue_preview | **passed** |
| `tests/unified_navigation_browser.py` | workflow_preview | **passed** |
| Backend `pytest tests/` | temporary databases | **152 passed** |

What the board suite now verifies, against the spec's checklist:
- **Overview:** exactly four summary cards with the API counts and the board's stage names; no job cards, previews or board; Manage printing jobs is the page action. Each card opens Printing jobs on its stage.
- **Expandable board:**
  - exactly one stage is open after every switch, with `aria-expanded` to match;
  - the open stage takes 65–75% of the row; the other stages are in the mosaic on its right, show no cards, and their names fit (`tests/mosaic_board_browser.py`);
  - switching sends no request and causes no reload, and the address remembers the stage.
- **Cards:** every In production card shows the product, recoloured preview, material and swatch, quantity, dimensions, model file, order reference, time in stage and Download; Accepted or Printing as reported.
- **Workflow:**
  - Accept puts the job in In production at once, with counts, the navigation badge and the server in agreement, focus kept in the open stage, and the destination stage lit up;
  - reporting the print start is optional;
  - Mark ready to ship works from accepted and from printing; Mark shipped moves the job to Awaiting buyer with its tracking;
  - after the buyer confirms receipt, the job is in Job history only;
  - overview counts equal the board's and the server's;
  - old links open In production; no "Start printing" anywhere.
- **Search:** stage counts become match counts, and clearing the search restores them.
- **Widths and themes:**
  - 320 and 390 px with touch: a 2×2 grid of 44 px pills, one stage, stacked cards with full-width 44 px actions;
  - 768, 900 and 1024 px: the open stage and the mosaic;
  - no page overflow in Bright or Dark.

The local Docker backend was rebuilt after backing up the development database to
`backups/pre-stage-board-20261101-184904.db` (no migration). On :8080 with the development host account, the
overview, Printing jobs (In production opened from its card) and Job history render at 1440 and 390 px
without console errors or overflow.

### Fourth pass (admin cancellation and the Printing jobs mosaic)

**Admin cancellation.** `POST /api/admin/orders/{id}/cancel` reuses the one existing cancellation:
- **Before:** only `pending` or `accepted` orders could be cancelled, so a host's optional "Report printing started" decided whether an administrator could intervene.
- **Now:** administrators may cancel any order that is not completed, with a required reason (`OrderCancellation`: 3–500 characters).
- **Every job not yet shipped** (`available`, `accepted`, `printing`, `ready`) is cancelled:
  - it keeps its host, so it stays in that host's Job history;
  - the model file is refused to the host from then on (the existing `cad.py` rule for cancelled orders); administrators keep it.
- **Shipped and received products** are never cancelled or altered. An order holding any is refused (409) unless the request acknowledges them (`shipped_acknowledged`). That is the exceptional resolution, with returns and refunds handled outside OpenLabs3D. A shipped product stays confirmable by the buyer.
- **Completed orders** are closed (409).
- **Recorded:**
  - `order.cancelled` with the reason as its note (administrators see notes in order details; buyers do not);
  - one `job.cancelled` per stopped job, saying where it was ("…while printing", "…while accepted (printing start not reported)").
  - Nothing is deleted.
- **Idempotent:** a repeat changes and records nothing.
- **Races:** the conditional update runs inside the request's write reservation, so a host step or receipt that lands first is either included or refuses the cancellation.
- **Unchanged:** buyers still only delete never-accepted orders, and hosts cannot cancel.

The admin dialog (Orders card or Details) lists each product with its stage and what happens to it ("Will be
cancelled" / "Kept as is"). It warns when a host may already be making something, and shows a red
exceptional-cancellation warning with a required checkbox when something shipped. The reason field is
required, the confirm button is the danger button, errors stay in the dialog, and the board refreshes in place.

| Suite | Fixture | Result |
|-------|---------|--------|
| `backend/tests/test_operations.py::test_admin_cancels_orders_at_any_production_stage` | temporary database | **passed** |
| `tests/admin_cancel_browser.py` | workflow_preview | **57/57** |
| `tests/mosaic_board_browser.py` | workflow_preview (distributions rewritten in the browser) | **594/594** |
| `tests/workflow_boards_browser.py` | workflow_preview | **131/131** |
| `tests/stage_boards_browser.js`, `history_views`, `workspace_overview`, `admin_approvals`, `equipment_revisions`, `admin_user_profile`, `checkout_contact`, `buyer_orders`, `custom_requests_filter`, `unified_navigation` | their fixtures | **passed** |
| `tests/host_job_dialog_browser.py` · `job_eligibility_browser.py` · `integrity_browser.py` · `my_orders_browser.py` | catalogue / orders | **41 · 27 · 24 · 49 passed** |
| Backend `pytest tests/` | temporary databases | **153 passed** |

The mosaic suite draws the real page with six job distributions (all empty, one stage with 14, 3 in each,
several empty stages, mixed, small counts) and every stage open. For each layout it checks:
- one open stage in the main area, taking 70–80% of the row;
- the other stages in workflow order on the right;
- sizes that follow the counts and every count shown;
- no clipped text and no word broken across lines;
- no overlapping panels and no holes in a row;
- previews on one row, with "+n" adding up to the count;
- hints only where there is room;
- no page overflow.

It also checks six expected arrangements. Switching is checked at 60, 5 and 0 ms between clicks: it always
settles on the last stage clicked, with no animation left, no request and no reload. Keyboard switching and
reload persistence are covered too. Widths: 1920, 1440, 1280 and 900 (one column) in Bright and Dark, and the
pills at 1024, 768, 390 and 320. All-empty shows "You're all caught up".

### Fifth pass (Balanced Mosaic and Expand section)

Frontend only: no backend, status or lifecycle change, so the backend suite was not re-run (153 passed in the fourth pass, on the same backend code).

| Suite | Fixture | Result |
|-------|---------|--------|
| `tests/section_modal_browser.py` (new) | workflow_preview | **163/163** |
| `tests/mosaic_board_browser.py` | workflow_preview (distributions rewritten in the browser) | **994/994** |
| `tests/workflow_boards_browser.py` | workflow_preview | **125/125** |
| `tests/admin_cancel_browser.py` | workflow_preview | **57/57** |
| `tests/stage_boards_browser.js` | workflow_preview | **passed** |
| `tests/host_job_dialog_browser.py` · `job_eligibility_browser.py` · `integrity_browser.py` | catalogue_preview | **41 · 27 · 24 passed** |
| `tests/custom_requests_filter_browser.js`, `unified_navigation_browser.py` | catalogue_preview | **passed** |
| `tests/my_orders_browser.py`, `buyer_orders_browser.js` | orders_preview | **49 passed; passed** |
| `tests/history_views_browser.js`, `workspace_overview`, `admin_approvals`, `equipment_revisions`, `admin_user_profile`, `checkout_contact` | equipment_preview | **passed** |

The section suite covers these, with real jobs and orders moving through real actions:
- **Interaction:** the action appears only on the open stage; a collapsed panel opens no dialog; the right stage opens, with no request.
- **Modal behaviour:** size, focus trap, Escape, close button, dimmed page, scroll lock, focus restoration, no duplicate ids.
- **Search and sort:** every sort order checked against the API; a dropdown's Escape stays with the dropdown.
- **Actions:** Details above the section; accept, mark ready and ship from it, with board, counts and server in agreement, one write and one read per step, no reload; emptying a stage.
- **Large stages:** 60 jobs in batches; server-paged stages (Show more, search, Oldest, Details on a later page, one request per typed search).
- **Other boards:** admin cancel, My orders (progress, tracking, Mark as received), Previous orders, approval history.
- **Environment:** Back, reduced motion; 320, 390, 768, 1024, 1280 and 1440 px in Bright and Dark.

Screenshots of the mosaic and the dialog were inspected at those widths. On :8080 with the development accounts (read-only), host, buyer and admin boards and sections render at 1440 and 390 px with no console errors or overflow.

### Sixth pass (colour hierarchy and the overview)

Frontend only, so the backend suite was not re-run (153 passed in the fourth pass, on the same backend code).

| Suite | Fixture | Result |
|-------|---------|--------|
| `tests/overview_mosaic_browser.py` (new) | workflow_preview | **1051/1051** |
| `tests/approval_colors_browser.py` (new) | equipment_preview | **27/27** |
| `tests/mosaic_board_browser.py` | workflow_preview | **994/994** |
| `tests/section_modal_browser.py` | workflow_preview | **163/163** |
| `tests/admin_cancel_browser.py` | workflow_preview | **57/57** |
| `tests/workflow_boards_browser.py` | workflow_preview | **125/125** |
| `tests/host_job_dialog_browser.py` · `job_eligibility_browser.py` · `integrity_browser.py` | catalogue_preview | **41 · 27 · 24 passed** |
| `tests/my_orders_browser.py`, `buyer_orders_browser.js`, `stage_boards_browser.js`, `history_views`, `workspace_overview`, `admin_approvals`, `equipment_revisions`, `admin_user_profile`, `checkout_contact`, `custom_requests_filter`, `unified_navigation` | their fixtures | **passed** (49 for my_orders) |

The overview suite measures colour as drawn (composited over the page): chroma, difference from the page, border strength, type and icon sizes and text contrast, on every tone in both themes. It covers uneven counts (0, 1, 3, 10, 30+), and proportions against the weights, at 320, 390, 768, 1024, 1280 and 1440 px in Bright and Dark.

Screenshots of the overview and the expanded layout were inspected at those widths.

## 10. Unresolved limitations

- **No deadline or estimated delivery** exists in the data model (U10, R6).
- **Current orders load in full** (pages of 50, fetched together). That is right for a buyer's active orders, but there is no upper bound for an extreme account.
- **Board search on My orders filters cards** but leaves column counts at their totals (R7). Printing jobs shows match counts per stage (second pass).
- **Accessibility was verified with keyboard and focus checks, ARIA structure and automated axe-core rules**, not with a screen reader. Columns are labelled sections with headings, counts carry text for assistive technology, and the strip uses buttons.
- **Development database:** before the Docker backend was rebuilt to serve the new response fields, it was backed up to `backups/pre-workflow-boards-20261101-162538.db`. There was no migration.
- **Out of scope by instruction:** prices, matching and eligibility rules, CAD models, payments and migrations are unchanged. Two lifecycle changes: Mark ready to ship straight from accepted (second pass), and administrator cancellation at any stage before completion (fourth pass). Statuses, order aggregation, reopening and buyer deletion are as before.
- **Admin reopen** still needs the job to be `accepted`: a job whose host reported printing cannot be handed to another host, only cancelled.
- ~~Pages can fetch their data up to three times on load.~~ Resolved: see `docs/architecture/STABILIZATION_AUDIT.md`.
- ~~Paged sorts can be slow on a very long history.~~ Resolved: the server sorts them. Only "Longest in this stage", which needs each job's stage history, still fetches every page, and it exists on active stages only.
- ~~The dialog's scroll position after an action on a paged stage.~~ Resolved: a stage keeps how much was loaded, up to 50 cards.
