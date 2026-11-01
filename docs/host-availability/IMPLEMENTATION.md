# Host-based product availability

Completed 2026-10-29, building on migration 64a and the shared availability module.

## Behavior

- Each printer stores an explicit material-to-color map. Empty maps mean unknown availability. Material lists and all legacy equipment information remain intact.
- Eligibility requires an approved host application, active user with host role, a positive printer quantity, valid CAD dimensions that fit that printer's build volume (axis rotation allowed), and the exact material/color on that same printer. Product pricing rules further restrict materials offered for purchase.
- `/api/listings/{id}/availability` returns uncached backend options. The configurator refreshes on selection changes, window focus, and every 15 seconds while visible. Invalid selections are replaced with an available choice with an explanation; no choices clears selections and disables both purchase buttons. Failed requests also disable purchasing.
- Quotes, cart additions/updates, checkout submission, and the existing order engine use the shared rules. Starting cart checkout rejects unavailable lines; direct checkout re-quotes its draft. Cart responses include an unavailable reason. Existing assigned jobs and historical orders remain accessible under the existing role rules.
- Job eligibility (added 2026-11-01) is one function, `availability.job_ineligibility(job, host_id)`, used by Available Jobs, acceptance, and the administrator's order view. A host never sees or accepts a job from their own order (compared by user id; the claim UPDATE also enforces `buyer_id != host`). Each job is one order line and needs a single approved printer that fits the line *as sold* (its pinned `manufacturing_dimensions`, not the listing's current model) and offers the exact material and shade. Acceptance re-runs the check inside the request's write transaction. Buyers, hosts included, are only offered (configurator, quote, cart, checkout) what some host other than themselves can make, so no order can be placed that only its buyer could fulfil. When only the viewer's own printers could make a product, the availability response sets `own_printers_only` and the configurator says so instead of calling it unavailable to everyone. Administrators see, per available job, which hosts can take it and why others cannot. Jobs already held by their own buyer are flagged ("Host is the buyer"), never changed automatically. The admin overview counts both situations (`unmatched_jobs`, `self_assigned_jobs`, the latter only while the job is still in work), and each warning opens `#admin/orders?attention=unmatched|own-order` (`GET /api/admin/orders?paginated=true&attention=…`): only those orders, marked on the row and expanded. Tests: `backend/tests/test_job_eligibility.py`, `tests/job_eligibility_browser.py` (`scripts/catalogue_preview.py`).
- On the deployed SQLite database, mutating HTTP requests acquire `BEGIN IMMEDIATE` before authentication and eligibility reads. Equipment updates, suspensions, cart writes, checkout, and job acceptance serialize through the database writer lock. Validation and order insertion therefore occur before a competing capability update can commit. Lock timeouts use the existing retryable 503 response.
- Existing host review rules remain: saving equipment changes moves the host to draft/pending and pauses eligibility until approval. There is no automatic inventory or color backfill.
- Administrator pricing edits retain all configured material factors, including materials temporarily unavailable from hosts.

## Development migration

Verified the running service's `APP_ENV=development`. Created a SQLite backup at `/app/data/before-material-colors-20261029.db` in the development data volume, rebuilt the development backend and applied `64a_material_colors` through Alembic startup. Verified the new column, revision, integrity check (`ok`), and all three existing orders. No production database was accessed. The development database contains zero registered printers, so lack of purchasable combinations is expected until hosts register and are approved.

## Verification

- 19 availability/integration tests: exact pair persistence, same-printer evaluation, dimensions and malformed/unknown dimensions, inactive/suspended/wrong-role hosts, API customization/cart/checkout/job flow, role and ownership enforcement, legacy migration preservation, and a concurrent checkout/suspension transaction.
- 20 existing marketplace/operations/collection/configurator tests passed. Purchase fixtures now explicitly register known dimensions and colors. The integer-pricing unit test isolates arithmetic from availability; integration tests use real eligibility.
- 10 existing account/equipment/cart/CAD/role tests passed with explicit manufacturable fixtures.
- Reusable Playwright workflow `tests/availability_browser.js` passed ten checks: filtering, price, persistent cart, direct checkout, assignment, host color editing, live invalidation, empty state, mobile layout, and no page exceptions.
- JavaScript syntax checks and `git diff --check` passed. Existing FastAPI lifespan and test-client dependency deprecation warnings remain.

Run backend suites in their existing separate database environments:

```sh
PYTHONPATH=backend pytest -q backend/tests/test_host_availability.py backend/tests/test_availability_integration.py
PYTHONPATH=backend pytest -q backend/tests/test_marketplace.py backend/tests/test_operations.py backend/tests/test_z_collection.py backend/tests/test_configurator.py
PYTHONPATH=backend pytest -q backend/tests/test_accounts.py
```

For browser verification, run `python scripts/availability_preview.py` with backend dependencies installed, then execute `tests/availability_browser.js` through Playwright's run-code tool. It uses port 18097 and a fresh temporary SQLite database with clearly isolated QA fixtures. Run against a fresh preview instance each time.

## Operational boundaries

- Missing or invalid CAD dimensions fail closed. Text descriptions such as “100 mm” are not treated as verified geometry.
- Open-page background updates are polled (up to 15 seconds); purchase and assignment requests always validate on the server regardless of UI freshness.
- Dimension fit checks the existing bounding-box constraint, not unmodeled process properties or a stock reservation. Colors are host-declared capabilities reviewed through the existing approval workflow.
- Transaction serialization is implemented for the project's SQLite deployment. A future database-engine migration requires an equivalent locking strategy and concurrency tests.
