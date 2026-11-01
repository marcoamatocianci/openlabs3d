# OpenLabs3D — Project Overview for Agents

A single reference for anyone (human or agent) picking up work on this repository: what the
product is, how the code is organised, the domain rules that must not be broken, every major
workflow, how to run and test it, and what is still open. Topic-specific deep dives live next
to this file (see [Further reading](#14-further-reading)).

Last updated: 2026-10-30 · branch `v4`.

---

## 1. What OpenLabs3D is

A marketplace that connects **laboratories (buyers)** with independent **3D-printing hosts**.

- Products are lab tools (tube racks, pipette holders, fixtures…) defined by a CAD model
  (STL/3MF). Hosts and administrators publish them; administrators approve community listings.
- Buyers configure a product (material, color, quantity), add it to a basket and submit an
  **order request**. No payment or shipping is integrated: buyer and host arrange both directly.
- Each order line becomes a **printing job** that an eligible approved host accepts and moves
  through `accepted → ready → shipped → completed` (the buyer completes it by confirming receipt;
  reporting `printing` between accepted and ready is optional).
- A product configuration is only purchasable if some approved host has a printer that is
  certified for the material, actually stocks that material in the requested color, and has a
  build volume large enough for the model.

Roles: `guest`, `buyer`, `host` (approved printing host), `admin`. Hosts are also buyers.

---

## 2. Architecture

```
Browser ──► Caddy (:8080 dev / :80,:443 prod)
              ├── /api/*  → FastAPI backend (uvicorn :8000, Docker service "backend")
              └── static  → index.html, *.js, style.css, assets/ (bind-mounted into /srv)
Backend ──► SQLite  /app/data/openlabs3d.db  (Docker volume app_data)
        ──► uploads /app/data/uploads/{products,cad,renders}
        ──► Blender (installed in the backend image) for product preview renders
```

- **Frontend:** plain HTML/CSS/JavaScript, no build step, no framework. Three.js (vendored in
  `assets/vendor/three`) for the 3D viewer.
- **Backend:** FastAPI + SQLAlchemy 2 + Alembic + Pydantic 2, Python 3.12. SQLite with WAL.
- **Containers:** `compose.yaml` (dev, Caddy on 8080) and `compose.production.yaml` (HTTPS
  via Caddy, `APP_ENV=production` → secure cookies). The backend container runs
  `alembic upgrade head` on every start.

---

## 3. Repository map

```
index.html                 Single page; loads every script in a fixed order (see §4)
style.css                  All styles; design tokens on :root and [data-theme=dark]
app.js                     Original prototype: router, demo catalogue/basket, catalogue() template
marketplace.js             API client (api()), auth, catalogue filter() request, listing routes
operations.js              Orders/onboarding views, adminAction(), safeDate(), panelMessage()
collection.js              Official collection helpers, confirmOfficial(), colorLabels
assets/
  theme.js                 Applies saved/system light-dark theme before paint
  navigation.js            Topbar, account menu, workspace sidebar, icons, statusBadge, emptyState
  product-visuals.js       CAD render tinting per filament color, product cards, imageMarkup()
  configurator.js          Product page: material/color/quantity, live price, 3D viewer
  viewer.js                ES module: mountViewer(host, url, color, material) for STL/GLB
  accounts.js              Account pages, accountAction(), countries
  shopping.js              Basket, checkout, line thumbnails
  catalogue-filters.js     Marketplace filter bar (dropdowns, price popover, chips)
  equipment.js             Host "My equipment": overview tabs, stock editor, revision wizard
  listing-editor.js        Four-step product listing editor
  workspaces.js            Role-aware router + admin/host workspace pages; triggers first render()
backend/
  app/main.py              App, auth/session deps, listings CRUD, pricing, images, approvals
  app/models.py            SQLAlchemy models (see §5)
  app/schemas.py           Pydantic request models
  app/accounts.py          Profile, verification/reset tokens, addresses, avatar, preferences
  app/operations.py        Host applications, orders, printing jobs, admin users/settings/activity
  app/shopping.py          Server-side cart and structured checkout
  app/equipment.py         Printer catalogue, host equipment, revisions, stock availability
  app/availability.py      Host eligibility: compatible_printers / combinations / supports
  app/pricing.py           Pricing rules, options(), quote()
  app/cad.py               CAD upload/inspect/download, render triggers, visual assets
  app/mesh.py              STL/3MF parser → bounding box (mm)
  app/render_product.py    Blender render pipeline (render.png, thumb.webp, model.glb)
  app/studio_scene.py      Blender studio scene used by render_product
  app/visuals.py           visual_data(): render status + asset URLs for a listing
  app/seed_*.py, attach_official_cad.py, enable_rack_materials.py, create_admin.py  Utilities
  migrations/versions/     Alembic migrations (latest: 66a_printer_capabilities)
  tests/                   pytest suite (77 tests)
caddy/                     Caddyfile (prod) and Caddyfile.dev
official_products/         Source CAD (STL/3MF) + renders for the official collection
scripts/                   Preview servers for isolated QA, render scripts, snapshot restore
tests/                     Browser test scripts (Playwright, run against preview servers)
docs/                      This file and topic reports
```

---

## 4. Frontend architecture (important conventions)

**Override chain.** There is no module bundler. Later scripts wrap functions defined by earlier
ones, e.g. `const equipmentRender = render; render = function(){ … equipmentRender(); }`.
The load order in `index.html` is therefore significant:

```
theme.js → catalogue-filters.js → app.js → navigation.js → marketplace.js → operations.js
→ collection.js → product-visuals.js → configurator.js → accounts.js → shopping.js
→ equipment.js → listing-editor.js → workspaces.js (calls render() once at the end)
```

Rules for new frontend code:
- Put new features in their own `assets/*.js` file and load it **before `workspaces.js`**,
  otherwise the initial render runs without it.
- Always bump the `?v=` query string of changed files in `index.html` (cache busting).
- Globals used everywhere: `$`, `esc` (HTML escaping, always use it), `api(path, options)`,
  `account`, `toast`, `showError`, `money`, `icon(name)`, `statusBadge(status,label)`,
  `emptyState(title,text,action)`, `workspacePage(kind,title,body,action)`.
- **Routing** is hash based (`#catalogue`, `#product/api-12`, `#my-printers/materials`…).
  `workspaces.js` maps admin/host routes to async page loaders (`adminPages`, `hostPages`)
  returning `{title, body, action, bind}`. `equipment.js` intercepts `#my-printers/edit` and
  `#onboarding`; `marketplace.js` handles `#create-listing` and `#edit-listing/{id}`.
- Shared modal: `<dialog id="modal">`. Any element with `data-close-modal` closes it.
- Design system: tokens such as `--ink --teal --surface --paper --line --subtle --hover
  --accent-soft --control-border --focus --success-*/--warning-*/--danger-*/--info-*`,
  redefined under `[data-theme=dark]`. Use tokens, never hard-coded colors.
- CSS namespaces for the newer features: `.eq-*` (equipment and shared stepper/cards),
  `.le-*` (listing editor), `.cf-*` (catalogue filters), `.review-*` (admin review dialogs).

---

## 5. Data model (backend/app/models.py)

| Model | Purpose / key fields |
|---|---|
| `User` | email, username, display_name, `role` (buyer/host/admin), `email_verified`, contact fields (first/last name, phone, country, city), theme, `active` |
| `LoginSession` | hashed session token + CSRF token, expiry (cookie `ol3d_session`) |
| `AccountToken` | single-use hashed verify/reset tokens |
| `UserAddress`, `CartItem` | saved delivery addresses; server-side basket lines (listing, material, color, qty) |
| `Listing` | product. `status` draft/pending/approved/rejected/archived, `listing_type` community/official, `price_cents` (base), `material` (primary, legacy), `configuration` (pricing rules JSON), `dimensions` (display text), `cad_path`, `cad_dimensions` (JSON [x,y,z] mm, used for matching), `featured`, `removed`, `version` |
| `ProductImage` | listing photographs (re-encoded, thumbnails) |
| `Category` | active catalogue categories |
| `HostApplication` | host account approval: `status` draft/pending/approved/rejected/suspended + legacy text summaries (printers, materials, capabilities “… weekly availability: N hours”, `additional` = workshop) |
| `Material` | catalogue of materials with `technology` FDM/RESIN (seeded) |
| `PrinterModel` | printer catalogue: manufacturer, model, technology, x/y/z, documented `materials`, `limitations`, `source`, `verified` (seeded from `equipment.CATALOGUE`) |
| `HostPrinter` | a host's **approved** printer: specs, `quantity`, `capabilities` (admin-approved materials), `materials` + `material_colors` (host-managed **stock**) |
| `EquipmentRevision` | proposed equipment change: `status` draft/pending/approved/rejected, `before`/`proposal` JSON, `rejection_reason`, timestamps. Partial unique index: max one open (draft/pending) per host |
| `Order`, `OrderItem` | order request + immutable line snapshot (title, material, color, price, `manufacturing_dimensions`) |
| `PrintingJob` | one per order line; `host_id`, `status` available/accepted/printing/ready/completed/cancelled |
| `Activity` | audit log; `MarketplaceSetting` | name, contact, host applications open |

Migrations are additive; never edit an applied migration — add a new one.

---

## 6. Core domain rules (do not break)

1. **Printer capabilities vs. stock.**
   - *Capabilities* (`HostPrinter.capabilities`) = materials the printer is certified for.
     Derived server-side by `equipment.resolve_capabilities`: the printer catalogue's documented
     materials (∩ material catalogue for that technology); for undocumented models, only
     capabilities an admin already approved for the same printer; otherwise **none** (never
     assumed). Changing capabilities/specs requires an equipment revision + admin approval.
   - *Stock* (`materials`, `material_colors`) = what the host has on the shelf. Edited directly via
     `PUT /api/host/printers/{id}/availability`, no approval, takes effect immediately, but must
     be a subset of capabilities.
2. **Marketplace eligibility** (`availability.py`, reused by availability, quote, cart, checkout,
   job listing and job acceptance — there is only one matching implementation): a material/color
   is available for a product if an **approved, active host** with role host has a printer whose
   build volume fits the product's `cad_dimensions` (sorted axis comparison), the material is in
   both its capabilities and its stock, and the color is registered for that material — and the
   product's pricing rules include the material.
3. **Accepted jobs are immutable.** Orders snapshot material/color/price/dimensions. Removing stock
   never cancels or alters existing jobs. An equipment revision that removes capabilities cannot
   be approved while an active job (accepted/printing/ready) would be left without a capable
   printer.
4. **Host role is never revoked by equipment editing.** Only explicit admin suspension affects it.
5. **Pricing** (`pricing.py`): `price_cents` is the base; `configuration.materials` maps each
   material to a factor in basis points (100–100000, i.e. 1%–1000%); unit price =
   `(base × factor + 5000) // 10000`; optional quantity `discounts` (bps) and `max_quantity`.
   The listing editor sets base = lowest material price and solves factors so each entered price
   is reproduced exactly. Pricing materials must exist in the `Material` table.
6. **Listing approval.** Community listings: draft → submit → pending → admin approve/reject.
   Official listings (admins only): published directly. **Any edit of an approved listing takes it
   off the marketplace** (status → pending, or draft for own official) until re-approved — this is
   existing architecture; the editor therefore offers no "Save draft" on approved listings.
7. **CAD.** Max 20 MB, STL or single-model 3MF, parsed by `mesh.inspect_mesh` (bounded, safe ZIP/XML
   handling). STL has no units → always interpreted as millimetres (warnings if the model is
   < 2 mm or > 1 m). 3MF units are converted. Uploaded geometry is authoritative: manual
   `cad_dimensions` are only accepted while no CAD file exists.
8. **Security.** Session cookie (HttpOnly, SameSite=Lax, Secure in production) + CSRF header
   `X-CSRF-Token` and same-origin check on every mutation (`mutate` dependency). Login is rate
   limited per account and per IP. Uploaded files are private; CAD download is limited to owner,
   admins and assigned hosts. Always escape user text with `esc()` in the frontend.

---

## 7. Workflows by role

### Buyer
1. Browse `#catalogue`: search + filter bar (category, material, price popover with slider €5 →
   highest catalogue price, sort; Apply at far right; removable chips; Clear filters).
2. Product page `#product/api-{id}`: choose material/color (only available combinations),
   quantity; live quote; 3D viewer; add to basket or buy now.
3. `#basket` → `#checkout`: contact + address (saved addresses supported), idempotent submit →
   order request with one printing job per line. Follow it in `#orders`.

### Printing host — onboarding
1. Buyer completes contact details, then `#onboarding` (same five-step editor as equipment):
   personal info → printers (catalogue or custom) → supported materials (read-only, from
   catalogue) → capabilities (weekly hours) → submit. Admin approves in Approvals; the user
   becomes `host`.
2. After approval the host stocks materials and colors in **My equipment → Materials & Colors**.

### Printing host — equipment (`#my-printers`)
- **Printers tab:** approved printer cards (illustration, spec popover on hover/focus/tap,
  approved capabilities, current stock). One contextual card below: *Equipment draft*
  (Continue editing / Delete draft), *Pending approval* (read-only) or a rejection banner
  (Revise and resubmit). **Modify equipment** is disabled while a draft or pending revision exists.
- **Modify equipment** (`#my-printers/edit`): wizard — Personal information, Printer equipment
  (cards + side drawer to add/edit/remove), Supported materials (read-only confirmation),
  Production capabilities, Review (Unchanged/Modified/New/Removed per printer). Save draft
  (private `EquipmentRevision` draft, approved equipment unchanged) or Submit for approval
  (pending). Unsaved edits survive reload (sessionStorage); leaving asks to save/discard.
- **Materials & Colors tab** (`#my-printers/materials`): per approved printer, tick stocked
  materials (unsupported ones are shown disabled) and manage colors via the Add color popover
  (24 standard colors + custom name/swatch; duplicates by name or shade rejected). Each change
  saves immediately and is live for buyers.

### Printing host — listings and jobs
- **My listings** (`#my-listings`): rows show the CAD render tinted like the marketplace card.
- **Listing editor** (`#create-listing`, `#edit-listing/{id}`): Product information (+ photos) →
  CAD model (upload → instant measurement via `/api/cad/inspect`, local STL 3D preview, render
  status after save; manual X/Y/Z only without CAD) → Materials & pricing (catalogue chips,
  per-material unit prices) → Review. Save draft (private) / Submit for approval.
  Pending listings: "Save changes". Approved listings: only "Submit changes for review".
- **Printing jobs** (`#host/jobs`): available jobs matching the host's eligibility; accept, then
  advance status. Buyer contact/address is revealed after acceptance.

### Administrator (`#admin…`)
- **Approvals** (`#admin/pending`): equipment update requests (before/after), new host
  applications, product listings. **View details** dialogs show everything submitted:
  listings (fields, images + generated render, CAD Preview 3D / Download, measured size,
  per-material prices, submitting host, dates) and host applications (applicant, facility,
  printer cards, capabilities, stock, dates). Approve/Reject from the dialog or the row.
- Products, Printers (catalogue + host suggestions), Materials, Categories, Users (incl.
  delete with password confirmation), Printing hosts (suspend/restore), Orders (cancel/reopen),
  Activity log, Settings. Official products: `#admin/create-official`.

---

## 8. API reference (all under `/api`)

Auth & account: `POST auth/register|login|logout`, `GET auth/me`, `POST auth/verify|resend-verification|forgot-password|reset-password|change-email|change-password`, `GET auth/username`, `PATCH profile`, `DELETE profile`, `GET|POST|DELETE profile/avatar`, `GET|PUT|DELETE addresses[/{id}]`, `PUT preferences`, `GET countries`.

Catalogue & listings: `GET listings` (q, category, material, sort, featured, page, per_page, max_price_cents), `GET listings/mine`, `GET|PATCH|DELETE listings/{id}`, `POST listings`, `POST listings/{id}/submit|publish`, `PUT listings/{id}/pricing`, `POST|GET|DELETE listings/{id}/images[/{image_id}]`, `PUT listings/{id}/images/order`, `GET listings/{id}/availability`, `POST listings/{id}/quote`, `GET categories`, `GET settings`.

CAD: `POST cad/inspect` (measure only, stores nothing), `POST|GET listings/{id}/cad`, `POST listings/{id}/render`, `GET listings/{id}/visuals/{revision}/{render.png|thumb.webp|model.glb}`.

Cart & orders: `GET|POST|PUT cart`, `DELETE cart/{item_id}`, `POST checkout`, `POST orders`, `GET orders`.

Hosts & equipment: `GET|PUT host/application`, `GET host/equipment`, `PUT host/equipment-application` (draft or submit; specs only), `GET|DELETE host/equipment-revision` (DELETE removes only the draft), `PUT host/printers/{id}/availability` (stock), `GET printer-catalogue`, `GET materials`, `GET host/jobs`, `POST host/jobs/{id}/accept`, `POST host/jobs/{id}/status`.

Admin: `GET admin/overview|listings|users|hosts|orders|activity|categories|equipment-revisions|printer-suggestions`, `POST admin/listings/{id}/approve|reject`, `POST admin/products/{id}/{action}`, `POST admin/hosts/{id}/{decision}`, `POST admin/equipment-revisions/{id}/{approve|reject}`, `POST admin/printer-suggestions/{id}/approve`, `POST admin/users/{id}/{action}`, `DELETE admin/users/{id}`, `POST admin/orders/{id}/cancel`, `POST admin/jobs/{id}/reopen`, `PUT admin/categories/{id}`, `PUT admin/settings`. `GET admin/hosts` includes each applicant's `equipment`.

Validation errors return 422 `{detail:[{type,loc,msg}]}` (raw inputs are not echoed).

---

## 9. Running, testing and deploying

### Docker (normal use)
```bash
docker compose up -d --build          # dev site on http://localhost:8080
docker compose exec backend python -m app.create_admin
docker compose restart caddy          # REQUIRED after editing index.html or style.css (see below)
```
- **Caddy single-file bind mounts:** `index.html`, `style.css`, `app.js`, … are mounted as
  individual files. Editors that replace the file (new inode) leave Caddy serving the old copy
  until `docker compose restart caddy`. `assets/` is a directory mount and updates live.
- Backend code changes require `docker compose up -d --build backend` (migrations run on start).
- Back up before migrations: copy `/app/data/openlabs3d.db` (e.g. via sqlite3 `.backup`);
  local backups go to `backups/` (git-ignored). Never `docker compose down -v`.
- `scripts/restore_snapshot.sh` restores `snapshot/app-data.tar.gz` into an empty volume only.

### Local Python (no project venv on this machine)
```bash
cd backend
~/.local/bin/uv run --no-project --python 3.12 --with-requirements requirements.txt \
  --with pytest --with httpx python -m pytest -q            # 77 tests, ~4 min
```
Tests use isolated temporary SQLite databases. When a test talks to pricing/equipment through a
custom fixture database, seed the catalogue with `equipment.seed_equipment(db)` (the real app
seeds it at startup).

### Browser QA
- Isolated preview server (temp DB with buyer/host/other/admin accounts, password
  `TestPassword2026`, a test listing):
  `uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/equipment_preview.py`
  → http://127.0.0.1:18099. Stop it with `pkill -f "[e]quipment_preview.py"` (the bracket stops
  pkill matching its own shell).
- `tests/equipment_revisions_browser.js` is a Playwright function (`async (page) => …`) for the
  Playwright MCP `browser_run_code_unsafe` tool, or any Node runner with Playwright.
- On this machine the Playwright MCP servers expect `/opt/google/chrome/chrome`, which is not
  installed. Working alternatives: Python Playwright (`uv run --with playwright`) or Node with the
  cached Playwright in `~/.npm/_npx/*/node_modules/playwright` and Chromium in
  `~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`. For WebGL (3D viewer) launch with
  `--use-gl=swiftshader --enable-unsafe-swiftshader`.
- Never run write-heavy QA against the real Docker site; read-only checks (e.g. catalogue
  filters as a guest) are fine.

### Rendering
Renders are produced in the backend container by Blender (`render_product`). Locally, Blender
lives in `~/.local/bin/blender`; run
`BLENDER_BIN=$HOME/.local/bin/blender uv run --no-project --python 3.12 --with Pillow python -m app.render_product <model.stl> --output <dir>` from `backend/`.
Render assets live in `UPLOAD_DIR/../renders/<cad file stem>/` with `status.json`.

---

## 10. Recent implementation history (2026-10-30)

All committed in `3238b83` on `v4` unless noted.

1. **My Equipment redesign** — compact approved printer cards with spec popovers; wizard hidden
   behind *Modify equipment* on its own route; contextual draft/pending/rejected card; drawer-based
   printer editing. Backend: `DELETE host/equipment-revision` now deletes only the draft row
   (previously it re-created a draft equal to approved equipment, which kept Modify disabled);
   revision responses include timestamps.
2. **Capabilities vs. stock** — migration `66a_printer_capabilities` (backfills capabilities from
   approved materials); revisions certify specs only; new stock endpoint; Materials & Colors tab;
   matching requires capability ∩ stock; capability-based active-job protection; legacy pending
   revisions still approve.
3. **My Listings thumbnails** use the generated CAD render like the marketplace.
4. **Admin approval details** — View details dialogs for listings and host applications;
   `listing_data.cad_format`; `admin/hosts` includes printers.
5. **Listing editor** — four-step editor, multi-material per-material pricing, `POST cad/inspect`,
   manual dimensions only without CAD, catalogue-validated pricing materials, safe 422 handler.
6. **Catalogue filter bar** (*not yet committed*) — new `assets/catalogue-filters.js`; Max Width
   removed (frontend and the `max_width` API parameter); price popover with dynamic slider;
   listbox dropdowns; Apply at far right; unapplied-changes indicator; chips; Clear; empty state;
   session persistence.

---

## 11. Known issues and open decisions

- **Approved listings have no private draft**: editing unpublishes them until re-approved. A
  listing revision system (like `EquipmentRevision`) would fix this; requires schema work.
- **Undocumented printer models** (catalogue entries with no documented materials, e.g. P2S, H2D,
  K1C, Prusa MK4S, resin printers) get no capabilities for new hosts, so nothing can be stocked.
  Needs either an admin UI to set a model's supported materials or catalogue data completion.
  Renaming a custom printer also creates a new identity without capabilities.
- 3MF files cannot be previewed in 3D before the first save (preview comes from the server render).
- Re-selected files (photos/CAD) are not restorable after a page reload; text fields are.
- The catalogue Material filter still offers only PLA/PETG (original options preserved).
- `snapshot/` (16 MB development data archive) and `scripts/restore_snapshot.sh` are untracked;
  committing them is the owner's decision.
- Legacy free-text `Listing.material` values that are not in the material catalogue are not
  carried into the new editor's material chips.

---

## 12. Conventions for future changes

- Keep changes scoped; reuse `availability.py`, `pricing.py`, `mesh.py`, `viewer.js`,
  `printerCard()`/`statusBadge()`/`emptyState()` instead of duplicating logic.
- Validate on the backend; frontend checks are for UX only.
- Add a pytest for every backend contract change and update browser scripts when UI flows change.
- Additive migrations with downgrade paths; back up the live DB before deploying migrations.
- Match surrounding code style (compact JS/Python in older files, readable style in newer
  `assets/*.js`). Escape all user-provided text.
- Do not commit or push unless the owner asks; the working branch is `v4`.

---

## 13. Glossary

| Term | Meaning |
|---|---|
| Capability | Material a host printer is certified (admin-approved) to print |
| Stock / availability | Materials and colors a host currently has, managed without approval |
| Revision | Proposed change to a host's printer specifications (`EquipmentRevision`) |
| Official product | Admin-owned listing published without review |
| Community listing | Host-owned listing that requires admin approval |
| Visual / render | Server-generated preview of a CAD model (PNG still, WebP thumbnail, GLB) |
| Factor (bps) | Per-material price multiplier relative to the base price, in basis points |

---

## 14. Further reading

- `docs/EQUIPMENT_REVISIONS.md` — why approved hosts edit equipment through revisions.
- `docs/host-availability/IMPLEMENTATION.md` — material/color availability and matching.
- `docs/product-visualization/README.md` — render pipeline and color tinting.
- `docs/account-system/REPORT.md` — accounts, verification, addresses.
- `docs/button-audit/STATUS.md`, `docs/state-of-the-art/` — UI audit and background research.
- `README.md` — installation and operation (Italian).
