# CAD product visualization

`python -m app.render_product path/to/model.stl --output path/to/output`

Run from backend, or set PYTHONPATH=backend. Requires Pillow and Blender (included in the backend image); BLENDER_BIN may override the executable path. STL coordinates are interpreted as millimeters; 3MF units and component transforms are converted to millimeters. CAD files are read-only. Models keep their supplied Z-up print orientation, are centered on XY and placed on Z=0; automatic arbitrary rotation is intentionally avoided.

Output: 1200px transparent PNG, 640px WebP (Lanczos downscale of the same render, light colour-only sharpening, lossless-quality alpha), centered GLB and a dimension/status manifest.

Studio look (`backend/app/studio_scene.py`): the product floats on a fully transparent background, with no floor and no ground shadow. The camera is a 100 mm three-quarter view, 30° above and 35° off the front, auto-fitted so the bounding box fills 72% of the frame. Lighting comes from three large softboxes (an overhead-left key that casts shadows, plus a broad fill and a rim strip that don't) and a grey room. The material is matte-satin PLA/PETG: 0.6 roughness, restrained specular, 0.35 mm softened edges, faint 0.2 mm layer lines, and local ambient occlusion so bores and recesses read with depth. Cycles runs at 48 adaptive samples with denoising and the Standard view transform, taking about 60–85 s per official rack with 2 threads.

Recoloring: the still is neutral grey (linear albedo 0.55). `assets/product-visuals.js` recolors it in linear light. It maps the swatch hex to a muted filament albedo (20% less saturated, 15% darker, never pure white or black) and keeps a 6% achromatic reflection share, so dark plastics keep their sheen. `ALBEDO` in the scene and `RENDER_ALBEDO` in the script must stay equal. The 3D viewer applies the same albedo mapping and a matching light rig. Three.js updates only the product material. Screen colors remain an approximation of physical filament; no translucency is invented without catalogue metadata.

Upload validates CAD, commits it, and schedules rendering in a serialized background worker with a 180-second subprocess timeout. Generated data lives beside existing CAD storage under `uploads/renders/<cad-stem>/`. Product configuration APIs advertise ready visuals. Original CAD access restrictions remain; a derived preview mesh is visible to users who can view the product. Failed/pending previews have an explicit placeholder. Owners/admins can regenerate from the listing editor. Background jobs are process-local: after a restart, regenerate any interrupted preview through that control.

Browsing preferences use account-namespaced localStorage (guest namespace when signed out), keyed independently by product. This is device-local, not cross-device account synchronization. Cards read the same material/color as detail pages. Invalid saved choices are kept as unavailable and require a fresh explicit choice; checkout still validates the chosen configuration on the server.

## Verification

- All three original STL/3MF pairs parsed with exact envelopes: 118 × 82 × 32, 110 × 85 × 52, and 124 × 86 × 62 mm.
- All three renders generated with transparent alpha, 1200px PNGs and 640px WebP thumbnails. The 15 mL render was generated directly from its 3MF assembly; the other two from STL.
- Installed container Blender regeneration verified after adding its NumPy dependency and detecting optional denoiser support.
- Backend coverage includes component transforms/unit conversion, output creation, original-file preservation, failure reporting, upload scheduling, and existing host eligibility tests.
- `tests/product_visuals_browser.js` passed via Playwright MCP against development: visible WebGL color change, orange catalogue synchronization, refresh persistence, independent products, mobile/dark layouts, invalid saved selection blocking/recovery, no page errors.
- Signed-in buyer flow was also checked manually with PLA Orange on the microtube rack.
