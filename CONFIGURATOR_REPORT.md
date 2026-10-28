# Interactive product configurator

Implemented in the existing FastAPI/SQLAlchemy/SQLite and vanilla JavaScript application; running at http://localhost:8080.

## Features
- Product detail pages have an interactive Three.js viewer with OrbitControls, mouse/touch rotation, scroll/pinch zoom, zoom buttons and Reset View. Bounding-box framing, studio lights, shadows, antialiasing and neutral background.
- Real material colors change on the existing mesh, preserving camera position. Existing Aqua blue, Signal red and Cream are retained. PLA/PETG/ABS have subtle roughness differences when enabled.
- Material selector, accessible radio swatches, bounded quantity input/buttons, server quotes and complete price breakdown.
- Cart lines distinguish product/material/color, show color thumbnails and totals, and revalidate prices when opened or quantities change. Checkout independently recalculates prices and rejects stale/tampered expected prices.
- Order items retain material/color/quantity and final unit price snapshots. Existing quantity and unit-price fields derive the line total; printing hosts see the configuration and total.
- Static image gallery fallback for products without models and image fallback when model loading fails.

## Assets and integration
`assets/models/{microtube-rack,15ml-rack,50ml-rack}.glb` are actual meshes exported by the existing Blender script with Boolean openings and bevelled structural parts. Run `blender -b --python scripts/render_racks.py -- --models-only` to regenerate without PNG rendering. Files range from 485 KB to 1.7 MB.

Three.js 0.180.0 and its MIT license are vendored locally under `assets/vendor/three/`. `assets/viewer.js` lazy-loads on product details, supports GLB/glTF and STL loaders, caps pixel ratio at 2, renders on interaction/resize and disposes GPU resources on navigation. No external runtime service or homepage WebGL scenes.

## Pricing and database
Migration `47b_configurator` adds `listings.model_url` and `listings.configuration`; existing collection rows receive model references. Existing prices, materials, listings, orders and volumes are preserved.

`POST /api/listings/{id}/quote` validates published availability, material, color and quantity. Prices use integer cents, integer basis points and half-up rounding. `PUT /api/listings/{id}/pricing` requires an administrator and validates stored rules. An administrator pricing editor is available below the product page. Rules consist of material multipliers, quantity discount thresholds and maximum quantity. 10000 basis points means 1.0 multiplier; 500 means 5% discount. Existing products default to their existing material at their existing price and no discount. Additional materials/discounts must be deliberately enabled based on fulfillment support.

## Verification
- **20 pytest tests passed**, including existing regressions, integer pricing, invalid material/color/quantity, unauthorized pricing writes, price tampering, final order/job configuration and snapshot retention after price-rule changes.
- Playwright: all three GLBs loaded; rotate/zoom/reset exercised; existing color switches; PLA/PETG/ABS prices verified against isolated rules; quantity discounts verified; cart and checkout completed; host dashboard showed PETG, Cream and 10 units at €19.44/unit.
- Isolated example: €18 base × 1.20 PETG × 0.90 discount = €19.44/unit, €194.40 for 10. These test rules were not applied to live products.
- Layouts at 390, 768, 1440 px: no horizontal overflow; no JavaScript exceptions during interaction checks.
- Existing image-only live listing verified with zero canvases and a visible product image.
- Live backend and Caddy restarted successfully; live model references and original base prices confirmed afterward. Database backup: `backups/pre-configurator-backup.tar.gz` (ignored by Git).
- Screenshots: `.playwright-mcp/configurator-390.png`, `configurator-768.png`, `configurator-1440.png` (isolated test configuration).

## Limits and unverified items
- Tube compatibility, mechanical strength and manufacturing suitability are not engineering validated.
- Actual physical-device touch gestures, STL files and simulated network/model failures were not browser-tested; their input/loading paths are implemented.
- Live container restart was verified, but no synthetic completed order was inserted into production to test its restart lifecycle. Isolated checkout snapshots were verified through API reads.
- Model upload/validation UI is future work. The persisted model URL field and STL/GLTF loaders provide the extension point.
- Existing test dependency deprecations remain. Signed-out auth probes return the expected 401; GPU driver warnings may appear in the test browser.

## Main files
`assets/configurator.js`, `assets/viewer.js`, `assets/models/`, `assets/vendor/three/`, `backend/app/pricing.py`, `backend/app/{main,models,schemas,operations,seed_collection}.py`, `backend/migrations/versions/47b_configurator.py`, `backend/tests/test_configurator.py`, `scripts/{render_racks,preview_server}.py`, `marketplace.js`, `operations.js`, `index.html`, `style.css`.

Git branch: `v2`, tracking `origin/v2`. Changes committed and pushed under the user's standing authorization; `main` remains unchanged.
