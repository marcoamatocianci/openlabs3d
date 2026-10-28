# Product collection implementation and verification

Implemented October 28, 2026. Running on the existing Compose stack at http://localhost:8080. Only the backend and Caddy services were rebuilt. Existing data volumes were preserved; pre-migration backup: `backups/pre-collection-backup.tar.gz` (gitignored).

## Changes
- Authenticated administrator-owned official listings have an explicit publish endpoint, publication timestamp, approving actor, and activity entry. The form confirms before saving/uploading/publishing. New drafts remain unpublished. Community/host submissions retain moderation. Client-supplied official, featured, status and collection fields cannot bypass authorization.
- JPEG, PNG and WebP uploads are validated by decoding, oriented, bounded in size and saved in their original format. PNG/WebP alpha survives. Old JPEG storage paths remain readable. Cards, detail views, dashboards and upload previews use centered contain presentation. Public product media reserves layout space, avoids scaling above intrinsic size and displays errors/fallback text.
- Homepage featured/latest sections query the same approved-only, paginated listing API as the catalogue. Featured selection is administrator controlled; recent publications fill a short featured selection. No static sample catalogue is rendered.
- Nine transparent 1024px PNGs were generated with Blender 4.5.3/Cycles. Reusable script: `scripts/render_racks.py`. Assets: `assets/products/{microtube-rack,15ml-rack,50ml-rack}/{aqua-blue,signal-red,cream}.png`. See the asset README for geometry and rendering details. No imagegen fallback was needed. Geometry and camera remain identical across each product's colors. Tube fit is not validated.
- Color IDs are persisted across detail navigation/refresh, cart lines, checkout, order snapshots and printing jobs. Distinct colors of one product can be ordered separately. Unsupported colors are rejected server-side.
- Idempotent collection seeding inserts three keyed official records without modifying user listings, uploaded images or orders. Compose enables seeding on startup when an active administrator exists. The prior demo products were JavaScript/localStorage data. Existing database product `Rack 1` was preserved.

## Verification
- GitHub MCP, Context7 MCP and Playwright MCP were operational.
- Automated suite: **18 passed**. Includes permissions, draft/public visibility, moderation, image validation, transparent WebP, featured retrieval, seed idempotency and color snapshots in orders/jobs.
- Existing dependency warnings remain: Starlette TestClient/httpx and FastAPI startup-event deprecations.
- Playwright: administrator login → image upload → confirmation → immediate publication; correct price/image on homepage after refresh; catalogue navigation; WebP containment/centering and successful decoding.
- All three rack pages and all nine color image changes verified. Cart colors survived refresh; checkout persisted colors in order items and printing-job payloads.
- Homepage/catalogue/detail tested at **390, 768 and 1440 px**; no horizontal overflow. Screenshots captured at each width.
- Running Compose stack is healthy; public smoke checks and all collection assets passed. Mutation tests used the separate preview database in `/tmp`, not deployed records.
- No outstanding test failures. No tube-fit, printability or laboratory suitability validation was performed.

## Screenshots
- `.playwright-mcp/final-homepage.png`
- `.playwright-mcp/final-catalogue.png`
- `.playwright-mcp/final-microtube-aqua-blue.png`
- `.playwright-mcp/final-microtube-signal-red.png`
- `.playwright-mcp/final-microtube-cream.png`
- Responsive evidence: `.playwright-mcp/{home,catalogue,product-api-1}-{390,768,1440}.png`

## Main files
`backend/app/{main,models,schemas,operations,seed_collection}.py`, `backend/migrations/versions/36a_product_collection.py`, `backend/tests/test_z_collection.py`, `app.js`, `marketplace.js`, `operations.js`, `collection.js`, `style.css`, `index.html`, `compose.yaml`, `compose.production.yaml`, `scripts/render_racks.py`, `scripts/preview_server.py`, and `assets/products/`.

## Git
No commits or pushes were made. The workspace was already entirely untracked at inspection; Git reports `??` for the application files and directories, including the new assets, scripts and report. It cannot provide a tracked before/after diff for this starting state.
