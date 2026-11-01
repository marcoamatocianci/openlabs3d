# Active work and history

Every operational list shows work still in progress by default; finished work moves to a History view
one click away. Nothing is flagged, archived or deleted for this: which view an item belongs to is derived
from its authoritative status, so a status change moves it automatically (a reopened custom request
returns to the active queue).

## Classification (`backend/app/lifecycle.py`)

| Workflow | Active (default view) | History |
|---|---|---|
| Orders (buyer, admin) | Pending `pending` · In progress `accepted` `printing` `ready` · Shipping `shipped` | Completed `completed` · Cancelled `cancelled` |
| Printing jobs (host) | Available · Accepted · In progress `printing` · Ready to ship `ready` · Awaiting buyer `shipped` | Completed · Cancelled |
| Custom requests | Submitted · Under review · Accepted `quoted` | Closed `closed` |
| Approvals (admin) | The pending review queues | Approval history: each decision from `activity_log` |

Workflow-specific meanings: a shipped job stays active until its buyer confirms receipt (only then is it
`completed`); a ready job (printed, not shipped) is active; an accepted (`quoted`) custom request still
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

Scoped responses carry `scopes`: for `active` and `history`, a total and per-group counts (independent of
the selected group and search), so the two navigation levels never disagree with the server. History is
fetched only when opened, filtered and paginated in SQL; search matches an order reference or product name.
An unknown group returns 422 and the page falls back to the whole scope.

## Interface

Two navigation levels, both the shared pill components: level 1 switches Current / History (History is
visually secondary until selected, with its own count), level 2 filters that scope by status. The view
lives in the hash query (`#orders?scope=history&group=completed`), so Back/Forward and reloads restore it;
these routes are in `inPageRoutes`, so switching updates the list in place and keeps the scroll position.
Earlier path links (`#host/jobs/accepted`, `#admin/orders/pending`) open the matching view.

- Buyer My orders: Current orders / Previous orders (search by order number or product).
- Host: Overview board (Accepted · In production · Shipped) with Job history linked; Printing jobs:
  Active jobs / Job history. History rows are read-only (no steps, no model downloads; the API refuses both).
- Admin: Orders (Active orders / Order history, search), Approvals (Pending / Approval history),
  Custom requests (Active / Request history); the overview counts active orders and history separately.

Order snapshots, colours, previews and the change-address rules are unchanged (see the git history of this
file for the earlier buyer-only notes).

## Verification

Backend: `cd backend && uv run --no-project --python 3.12 --with-requirements requirements.txt --with pytest --with httpx python -m pytest -q`
(`test_buyer_order_pages_filters_and_snapshots`, `test_active_work_and_history_follow_the_authoritative_status`).

Browser (each on a fresh fixture, `node tests/run_playwright_script.js FILE` or `uv run … python FILE OUT`):
`buyer_orders_browser.js` and `my_orders_browser.py` (`scripts/orders_preview.py`, port 18100),
`history_views_browser.js` and `admin_approvals_browser.js` (`scripts/equipment_preview.py`, 18099),
`custom_requests_filter_browser.js` and `host_job_dialog_browser.py` (`scripts/catalogue_preview.py`, 18101).
Fixtures use temporary databases; password `TestPassword2026`.
