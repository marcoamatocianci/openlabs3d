# Active work and history

Every operational list shows work still in progress by default; finished work moves to a History view
one click away. Nothing is flagged, archived or deleted for this: which view an item belongs to is derived
from its authoritative status, so a status change moves it automatically (a reopened custom request
returns to the active queue).

## Classification (`backend/app/lifecycle.py`)

| Workflow | Active (default view) | History |
|---|---|---|
| Orders (buyer, admin) | Pending `pending` · In progress `accepted` `printing` `ready` · Shipping `shipped` | Completed `completed` · Cancelled `cancelled` |
| Printing jobs (host) | Available · In production `accepted` `printing` · Ready to ship `ready` · Awaiting buyer `shipped` | Completed · Cancelled |
| Custom requests | Submitted · Under review · Accepted `quoted` | Closed `closed` |
| Approvals (admin) | The pending review queues | Approval history: each decision from `activity_log` |

Workflow-specific meanings: a job is in production from the moment its host accepts it. Reporting the print
start (`printing`) is optional: Mark ready to ship is allowed from `accepted` or `printing`, and a job that
skips the report never gets a `printing` status or `job.printing` event. A shipped job stays active until its
buyer confirms receipt (only then is it `completed`); a ready job (printed, not shipped) is active; an accepted (`quoted`) custom request still
needs quotation or production work. Approval history records decisions only: approved hosts, products and
printers are still managed in their own pages. The application has no disputes or payment states (payment
and delivery are arranged between buyer and host), so no other status keeps finished work active.

## API

Each list keeps its original response when called without the new parameters.

- `GET /api/orders?paginated=true&scope=active|history&group=…&q=…&sort=…&page=…` (buyer)
- `GET /api/admin/orders?paginated=true&scope=…&group=…&q=…&page=…`
- `GET /api/host/jobs?scope=active|history&group=…&q=…&page=…` (active is unpaginated: bounded by current work)
- `GET /api/custom-requests?scope=…&group=…` and `GET /api/admin/custom-requests?scope=…&group=…`
- `GET /api/admin/approvals/history?type=all|hosts|equipment|listings|printers&page=…`
- Boards: `columns=true` on the paged lists above (buyer orders, admin orders, host job history, approval
  history) returns `columns`: the first page of every group of the scope at once, each with its `key`,
  `label`, `statuses`, `total` (search and `attention` included), `page` and `pages`. "Load more" then asks
  the same list for one `group` and the next `page`. No migration.

Scoped responses carry `scopes`: for `active` and `history`, a total and per-group counts (independent of
the selected group and search), so the two navigation levels never disagree with the server. History is
fetched only when opened, filtered and paginated in SQL; search matches an order reference or product name.
An unknown group returns 422 and the page falls back to the whole scope.

## Interface

Level 1 switches Current / History with the shared pills (History is visually secondary until selected,
with its own count). Level 2 is a stage board (`stageBoard` in `navigation.js`, the Printing jobs design):
one column per status group, one open with full cards, the others compact (name, count, previews) on wide
screens, stage pills on phones. The open stage is `?group=` (`?type=` in Approvals) in the address, kept
with `history.replaceState` and for the session; switching stage makes no request. Scope and search changes
are in the hash, so Back/Forward and reloads restore them. Earlier links (`#host/jobs/completed`,
`#admin/orders/pending`, `#admin/requests/submitted`) open the matching stage.

- Buyer My orders: Current orders (Pending · In progress · Shipping) / Previous orders (Completed · Cancelled, server
  search, sort).
- Custom requests → My requests: Submitted · Under review · Accepted / Request history (one column, Closed).
  Details open in the site dialog.
- Host: Printing jobs board; Job history: Completed · Cancelled, read-only cards (no steps, no model
  downloads; the API refuses both) with the shipment.
- Admin: Orders (Pending · In progress · Shipping / Completed · Cancelled; jobs, eligibility, delivery and
  history in a Details dialog; `?attention=` keeps its banner), Approvals (one stage per queue: Host
  applications · Equipment updates · Listings · Printer suggestions; Approval history by the same types),
  Custom requests (Submitted · Under review · Quoted, with "move to the next status" as each card's action /
  Request history).

Paged stages show their first 12 cards and "Load more"; a failed page stays inside its stage with Try again.
Small lists (custom requests, pending approvals) load at once and search in the browser, counting matches per
stage; paged ones search on the server, and each stage then shows its match count.

### Administrator cancellation

`POST /api/admin/orders/{id}/cancel` with `{"reason": "…", "shipped_acknowledged": false}`
(administrators only):
- **Any order not completed** can be cancelled, whatever the host reported.
- **Every job not yet shipped** (`available`, `accepted`, `printing`, `ready`) becomes `cancelled`. It keeps its host, so it is in that host's Job history, and the host loses the model file.
- **Shipped and received products keep their status** and shipment. An order holding any needs `shipped_acknowledged: true` (409 otherwise): the exceptional resolution, with returns and refunds handled outside the platform. The buyer can still confirm receipt of a shipped product; the order stays cancelled.
- **Completed orders:** 409.
- **A cancelled order:** 200, with no change and no new event.
- **Logged:** `order.cancelled` with the reason as its note (shown to administrators only), and `job.cancelled` per stopped job with the stage it was in.
- **Nothing is deleted.**
- **Reopen and buyer deletion are unchanged:**
  - `POST /api/admin/jobs/{id}/reopen` works only while a job is `accepted`;
  - buyers delete only orders no host ever accepted.

Order snapshots, colours, previews and the change-address rules are unchanged (see the git history of this
file for the earlier buyer-only notes).

## Verification

Backend: `cd backend && uv run --no-project --python 3.12 --with-requirements requirements.txt --with pytest --with httpx python -m pytest -q`
(`test_buyer_order_pages_filters_and_snapshots`, `test_active_work_and_history_follow_the_authoritative_status`).

Browser (each on a fresh fixture, `node tests/run_playwright_script.js FILE` or `uv run … python FILE OUT`):
`buyer_orders_browser.js` and `my_orders_browser.py` (`scripts/orders_preview.py`, port 18100),
`history_views_browser.js` and `admin_approvals_browser.js` (`scripts/equipment_preview.py`, 18099),
`custom_requests_filter_browser.js` and `host_job_dialog_browser.py` (`scripts/catalogue_preview.py`, 18101),
`stage_boards_browser.js` and `workflow_boards_browser.py` (`scripts/workflow_preview.py`, 18102).
Fixtures use temporary databases; password `TestPassword2026`.
