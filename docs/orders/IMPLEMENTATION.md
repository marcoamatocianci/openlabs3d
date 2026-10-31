# Buyer order history

`assets/buyer-orders.js` wraps `renderOperations('orders')` before the final workspace
render. It only changes the authenticated buyer/host My orders view. Existing inline
`details` expansion is retained, with product, fulfillment, contact/delivery, and history sections.

## Presentation and data

- Pending: `pending`, `accepted`; accepted is explicitly labelled as awaiting printing.
- In progress: `printing`, `ready`; per-product jobs disclose partial fulfillment.
- Completed: `completed`. Cancelled: `cancelled`.
- Filters and newest/oldest sort use hash query parameters and account-scoped session storage.
- Ten orders per page. `GET /api/orders?paginated=true` adds optional category, sort,
  page and per_page (1–50) parameters. It returns items, category counts, total, page,
  pages and per_page. Queries and counts are restricted to the authenticated buyer.
  Existing callers without `paginated=true` retain their list response.
- All purchased names, material/color labels, quantities, unit/total prices and delivery
  details come from stored order snapshots. No order records or lifecycle rules changed.
- Colour: since migration `68a`, each order line stores `color_hex`, the exact colour offered at
  checkout (from `quote()`). Lines placed earlier keep `''`: they show the recorded colour name and no
  swatch, never a colour guessed from current stock.
- Previews: `/api/orders` returns a `thumbnail` URL per line for products that are still publicly viewable
  (the image route enforces the same rule). The neutral render is recoloured in the browser with the
  line's `color_hex` by the catalogue's `tintProductImage()` at 160 px (`data-tint-size`), and cached per
  image and colour. Removed products and products without a render get a labelled placeholder.
- Filters, sort and pages update the toolbar and list in place (`inPageRoutes` in `app.js` keeps the
  scroll position); the tab is highlighted immediately and the previous list dims only if loading takes
  longer than 120 ms. See `docs/architecture/CODEBASE_AUDIT.md` §3 for the original refresh problem.
- Assigned hosts use the host ID already exposed by the order API; no private host data is fetched.

## Verification

Backend: `cd backend && uv run --no-project --python 3.12 --with-requirements requirements.txt --with pytest --with httpx python -m pytest -q tests/test_operations.py`

Browser: start `uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/orders_preview.py`,
then run `tests/buyer_orders_browser.js` through Playwright MCP `browser_run_code_unsafe` (or
`node tests/run_playwright_script.js tests/buyer_orders_browser.js`) and
`uv run --no-project --python 3.12 --with playwright python tests/my_orders_browser.py OUTPUT_DIR`.
The preview creates a temporary database and fixture users on port 18100; no development
or production orders are used. Password: `TestPassword2026` (buyer/other/empty@example.org).

Verified: 9 backend tests; browser pagination, status counts/grouping, combined sorting,
filter persistence, multi-product orders, snapshot integrity after listing changes,
keyboard details, CAD/fallback previews, loading/retry/empty states, buyer isolation,
desktop/tablet/mobile layout and bright/dark status contrast. Screenshots are produced
in `.playwright-mcp/orders-*.png`.

Deploy source changes with the usual backend rebuild (runs migration `68a_order_color_snapshot`)
and a Caddy restart for changed single-file bind mounts.
