# OpenLabs3D account and marketplace implementation report

Implemented locally on 28 October 2026 in the existing application. No repository commits, pushes, pull requests, remote modifications, or external deployments were performed. The existing HTML/CSS/JavaScript/Three.js frontend, FastAPI/SQLAlchemy backend, Alembic, SQLite, Caddy, Docker Compose, and filesystem storage remain in use.

## A. Implemented features

Added verified account registration, unique usernames, account/contact settings, saved addresses, avatars, appearance preferences, persistent owner-specific carts, direct purchasing, structured checkout, equipment-based host applications, sourced printer and material catalogues, role-specific navigation, required host CAD submission, and direct administrator product management.

The initial inspection found working Argon2 password hashing, cookie sessions, CSRF/origin checks, host approval, backend price calculations, historical order snapshots, image validation, and official-product publication. These were extended rather than replaced. The shared browser basket, missing account fields, unverified registration, unrestricted buyer listing creation, and shared navigation required changes.

## B. Account management

- Email syntax and uniqueness validation remain server-side. New accounts are unverified. Verification uses random tokens stored only as SHA-256 hashes, expiring after 60 minutes, consumed atomically once. Resend has a 60-second database-backed cooldown; verification and authentication endpoints have attempt throttling.
- Verified email is required for ordering, host application submission, and listing creation/submission/publication. Existing users were not falsely marked verified.
- Configurable SMTP uses environment variables. Development defaults to private `.eml` files under `/app/data/uploads/mail`, outside static serving. The UI explicitly says no real email was sent in this mode. Local mailbox verification was tested; real SMTP delivery was not.
- Passwords require at least eight characters, an uppercase letter and a number; maximum 128 characters. Special characters are allowed. Registration, changes and resets share backend validation. The frontend provides immediate requirements feedback and show/hide controls. Existing Argon2id hashing remains.
- Usernames use 3–32 ASCII letters, digits or underscores. SQLite `NOCASE` uniqueness enforces concurrent case-insensitive uniqueness. `MarcoLab` and `marcolab` collide; `MARC0LAB` is different because zero and letter O are distinct. Existing display names were retained, with deterministic collision-safe username backfilling. First/last names were not guessed from display names.
- Separate first/last names, international phone, normalized country code, city, region, alphanumeric postal code, street and additional information persist on the user record. Email changes require the current password, revoke other sessions, and require verification again.
- Multiple saved addresses support add/edit/delete and a default protected by a unique partial index. Orders retain independent delivery snapshots.
- Avatar uploads accept PNG/JPEG/WebP, validate decoded image data, limit uploads to 2 MB and 16 megapixels, strip metadata by re-encoding to WebP, and use generated filenames. Preview, replace, remove, default avatar and navigation display are implemented.
- Light/dark/system preferences persist on accounts. A pre-stylesheet theme script uses local storage and system preferences to reduce theme flashes. Blue branding is retained.
- Payment Methods contains the requested future-release notice. No card, CVV or banking data is collected.
- Country choices use the ISO dataset supplied by `pycountry`. Country-aware city suggestions are a deliberately small local hint list; manual entry is supported, and the UI states the list is not exhaustive.

## C. Shopping experience

Authenticated carts are SQLite rows scoped to the session's user. Product, material, color and quantity persist; prices are calculated by the existing backend pricing engine. Quantity changes and deletes are owner-scoped. Concurrent additions use atomic database updates. Removed/unavailable products remain removable from a basket.

The old shared browser basket is not automatically imported into an account. Authenticated shopping requires sign-in; the old sample/demo basket stays separate. This avoids transferring one user's browser data into another user's account.

Buy Now stores a separate tab-local draft and does not add to or clear the basket. A guest's selected configuration survives authentication and returns to checkout. Logout discards the direct draft rather than transferring it to the next account.

Both checkout paths use the existing order-creation/price-validation engine. Contact fields autofill, saved addresses populate the form, missing contact details link to Account Settings, and a return link preserves checkout context. Edited shipping fields become a manual address rather than silently using an unchanged saved address. Contact and delivery information are validated and snapshotted. Order creation and purchased cart-line removal commit together. Idempotency prevents repeat submission from creating duplicate orders.

## D. Printing hosts

The five-step application covers personal information, printer equipment, supported materials, production capabilities, and review/submission. It reuses account contact information, retains tab drafts during navigation, and supports server-side draft saving. Company/workshop name and weekly availability are optional. Multiple printer models and quantities are supported; totals and technology/material summaries are derived from equipment. Editing approved equipment requires renewed review before expanded capabilities can be used.

Catalogue seeding is idempotent. Build volumes are in millimeters, in X × Y × Z order. Sources checked during implementation:

| Manufacturer | Model | Technology | Build volume (mm) | Source |
|---|---|---|---|---|
| Bambu Lab | P1S | FDM | 256 × 256 × 256 | [Manufacturer guide](https://cdn1.bambulab.com/documentation/quick-start-2024-01-17/Quick-Start-P1S_en.pdf) |
| Prusa Research | Original Prusa MK4S | FDM | 250 × 210 × 220 | [Manufacturer product page](https://www.prusa3d.com/product/original-prusa-mk4s-3d-printer-7/) |
| Creality | K1C | FDM | 220 × 220 × 250 | [Manufacturer product page](https://www.creality.com/products/k1c-carbon-3d-printer) |
| UltiMaker | S5 | FDM | 330 × 240 × 300 | [Manufacturer specifications](https://ultimaker.com/3d-printers/s-series/ultimaker-s5/) |
| Anycubic | Photon Mono M5s | Resin | 218 × 123 × 200 | [Manufacturer specifications; HWD converted to XYZ](https://store.anycubic.com/blogs/news/anycubic-photon-mono-m5s-release) |
| Elegoo | Saturn 4 Ultra 12K | Resin/MSLA | 218.88 × 122.88 × 220 | [Manufacturer specifications](https://us.elegoo.com/products/saturn-4-ultra-12k-10inch-monochrome-lcd-resin-3d-printer) |
| Formlabs | Form 4 | Resin | 200 × 125 × 210 | [Manufacturer support](https://formlabs.com/support/What-is-the-largest-part-I-can-print-on-a-Formlabs-printer/) |

Known printer selection derives dimensions and technology on the backend, preventing contradictory client values. Custom equipment is separately stored as user-provided, with positive bounded dimensions and quantities. Administrators can accept suggestions into the catalogue as unverified; acceptance is not manufacturer verification.

The material catalogue includes PLA, PLA+, PETG, ABS, ASA, TPU, PA/Nylon, PC, Standard Resin, Tough Resin, Flexible Resin and High-Temperature Resin. Equipment uses technology-filtered checkboxes. P1S documented families and limitations are recorded; other families remain explicitly unverified where not individually checked. No universal FDM compatibility is assumed. Product forms also expose catalogue material choices.

## E. Role-based workspaces

- Buyers: dashboard, catalogue, existing custom-request workflow, basket, orders, host application and account settings. Listing creation is denied by the backend.
- Approved hosts: jobs, own products, listing creation, printers/capabilities, account settings and separate shopping links. Pending/suspended applications cannot create listings.
- Administrators: dashboard, product management, approvals, hosts, printer/material catalogues, users, marketplace orders, activity and settings. Their navigation omits Basket, My Orders, Custom Request, Become a Printing Host and regular Create Listing. Personal order/cart endpoints deny administrator access.

The browser verified administrator navigation and immediate publication using an isolated administrator account. All mutation permissions remain backend-enforced.

## F. Product management

Approved, verified hosts can create/edit drafts, manage images, upload CAD, choose materials, and submit for administrator approval. Host submission and approval require an uploaded parsed model.

CAD uploads accept STL or supported single-model, flattened 3MF, capped at 20 MB. Validation checks content, bounded triangle counts, finite coordinates, non-degenerate dimensions, archive entry paths/sizes/compression ratios, XML entity/declaration exclusions, and triangle indices. Archives are never extracted. Component/transformed 3MF files are rejected with instructions to flatten them. Generated filenames, ownership checks and protected downloads restrict CAD access to owners, administrators and assigned hosts. Bounding-box dimensions and equipment-size warnings are provided; parsing is not a printability guarantee. STL coordinates are interpreted as millimeters.

Administrators use Create Official Product and the existing explicit Publish Now confirmation. Official products publish directly without entering the host approval queue. Editing, unpublish, archive and removal are distinct actions. Removal uses a tombstone and retains order references and assets; removed products disappear from public catalogue/homepage queries. Archived products can also be removed.

Existing Three.js product previews remain functional and were checked on the local live site. Automatic new preview generation for uploaded CAD is not implemented; uploaded CAD has inspection/dimension feedback.

## G. Testing

Final automated result: **29 passed, 0 failed**, with five existing/dependency deprecation warnings. See [pytest-results.txt](pytest-results.txt). Fixtures use isolated test databases and assets. Legacy tests were updated for the new registration, verification, approved-host and administrator-role contracts; the old permissions were not retained merely to satisfy old assertions.

Coverage includes password/email/username rules; concurrent username collisions; verification expiry/reuse/throttling; profile and address ownership; reset/session revocation; avatar formats/limits; theme persistence; owner-specific carts; concurrent additions; removed cart items; Buy Now basket isolation; idempotent checkout; structured contact validation; equipment quantities/technology/dimensions/seeding; role boundaries; CAD requirements and unsafe uploads; direct official publication; removal with historical orders; and existing order/job/image/configurator regressions.

Playwright checks passed for registration/profile persistence, theme refresh, printer specification/material selection, role navigation, official publication confirmation, local-mail verification, saved-address autofill, direct ordering without clearing the basket, guest Buy Now through login, and same-browser account switching. Buyer B saw an empty cart, added three items, and Buyer A recovered their original one-item cart.

Responsive checks: **48 page/viewport combinations** across buyer, host and administrator screens at 390, 768, 1024 and 1440 pixels showed no horizontal overflow. These are layout checks, not a claim of exhaustive accessibility certification. Screenshots: [mobile checkout](checkout-mobile.png), [administrator desktop](admin-desktop.png). Buyer/host measurements are saved in [responsive-results.json](responsive-results.json).

An isolated cart survived two separate Docker container runs using a temporary mounted database. The live site passed health/account UI/catalogue checks, and an existing Three.js product rendered a nonzero-size WebGL canvas.

Migrations were first tested against a separate copy of the populated database. After local startup, all original columns/rows for 8 users, 5 products, 3 orders, 3 order items, 1 product image and 3 printing jobs matched the pre-upgrade backup. Foreign-key violations: zero. See [migration-check.json](migration-check.json). Backup: `backups/pre-account-upgrade.db`, mode 0600.

Not verified: real SMTP/inbox delivery, exhaustive browser/OS accessibility coverage, arbitrary 3MF extensions, physical printability, and material-specific hardware qualification. Payments and shipping integrations remain intentionally absent. The pre-existing custom-request/sample workflows remain demonstrations, as before this task.

## H. Significant modified files

- Backend additions: `backend/app/accounts.py`, `shopping.py`, `equipment.py`, `cad.py`.
- Backend extensions: `models.py`, `schemas.py`, `main.py`, `operations.py`, `create_admin.py`, and `requirements.txt`.
- Additive migrations: `58a_accounts.py`, `59a_preferences.py`, `60a_carts.py`, `61a_equipment.py`, `62a_cad_removal.py`.
- Frontend additions: `assets/accounts.js`, `theme.js`, `shopping.js`, `equipment.js`, `workspaces.js`.
- Frontend integration: `index.html`, `style.css`, `marketplace.js`, `operations.js`.
- Configuration: `.env.example`, `compose.yaml`, `compose.production.yaml`.
- Testing: `backend/tests/test_accounts.py`, `conftest.py`, `order_fixtures.py`, updated existing regression fixtures, and `scripts/account_preview.py`.
- Evidence and this report: `docs/account-system/`.

Pre-existing edits to configurator/viewer/Caddy files and pre-existing untracked files were retained. They appear in Git status and should not be mistaken for newly authored changes in this task.

## I. Local access and operation

Live local application: **http://localhost:8080/**. Backend and Caddy are healthy. Current migration: `62a_cad_removal`. Running backend source hashes matched the checked local files.

Start/update from the project directory:

```bash
docker compose up -d --build
```

Stop without deleting data:

```bash
docker compose stop backend caddy
```

The Docker exporter encountered a cache/snapshot error during development. A non-destructive retry succeeded:

```bash
docker compose build --no-cache backend
docker compose up -d backend caddy
```

Existing accounts must verify their email before sensitive marketplace actions. In development, request a verification message from Account Settings, then inspect the private local mailbox:

```bash
docker compose exec backend ls /app/data/uploads/mail
# Read the chosen .eml file locally, then open its verification link.
docker compose exec backend cat /app/data/uploads/mail/CHOSEN_FILENAME.eml
```

For real mail, configure `MAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_FROM`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `PUBLIC_BASE_URL` in the local environment. Production disallows the file-mail transport. SMTP secrets must not be committed.

Run tests with the project's backend requirements plus pytest/httpx installed. This session used an existing isolated dependency directory:

```bash
PYTHONPATH=/tmp/openlabs3d-test-deps:backend python3 -m pytest backend/tests -q
```

The loopback-only QA preview uses its own `/tmp` database and mailbox at port 8096, not the live database:

```bash
PYTHONPATH=/tmp/openlabs3d-test-deps python3 scripts/account_preview.py
# Ctrl+C stops the preview.
```

## J. Git status

No commit, push, synchronization, pull request, merge, remote GitHub write, or external deployment was performed. GitHub MCP was unavailable; Playwright MCP and Context7 were verified working. Public manufacturer documentation was consulted without uploading project data.

The complete `git status --short` output follows:

```text
 M .env.example
 M assets/configurator.js
 M assets/viewer.js
 M backend/app/create_admin.py
 M backend/app/main.py
 M backend/app/models.py
 M backend/app/operations.py
 M backend/app/schemas.py
 M backend/requirements.txt
 M backend/tests/test_configurator.py
 M backend/tests/test_marketplace.py
 M backend/tests/test_operations.py
 M backend/tests/test_z_collection.py
 M caddy/Caddyfile
 M caddy/Caddyfile.dev
 M compose.production.yaml
 M compose.yaml
 M index.html
 M marketplace.js
 M operations.js
 M style.css
?? assets/accounts.js
?? assets/equipment.js
?? assets/shopping.js
?? assets/theme.js
?? assets/workspaces.js
?? backend/app/accounts.py
?? backend/app/cad.py
?? backend/app/equipment.py
?? backend/app/shopping.py
?? backend/migrations/versions/58a_accounts.py
?? backend/migrations/versions/59a_preferences.py
?? backend/migrations/versions/60a_carts.py
?? backend/migrations/versions/61a_equipment.py
?? backend/migrations/versions/62a_cad_removal.py
?? backend/tests/conftest.py
?? backend/tests/order_fixtures.py
?? backend/tests/test_accounts.py
?? docs/
?? scripts/account_preview.py

```
