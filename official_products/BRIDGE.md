# Bridge collection — revision 3, softened finish

Revision 3 keeps the approved Bridge structure and original envelopes/bores. Outer corner radii increase from 5 to 7 mm; the top perimeter now has a genuine 1.6 mm rolling fillet instead of a 0.7 mm chamfer. Vault transitions increase from 0.8 to 2 mm. Tube-entry chamfers increase from 0.6 to 1.1 mm, while nominal bores are unchanged. The underside retains a print-friendly 0.8 mm chamfer. Enlarged vault crests need bridge calibration in the trial print.

The previous Bridge geometry, sources and renders are archived at `previous/bridge_v2/`; development CAD-reference rollback is `cad_backups/bridge_v3_finish.json`. The original blocks remain archived separately. Current measurements are in `redesign/validation.json`. The following design history and table describe revision 2.

The nine sleeve studies were rejected for repetition and poor cleaning access. Bridge replaces sleeves with a continuous rounded canopy and intersecting vaulted webs. The second iteration adds splayed pier feet, 0.8 mm rounded arch transitions, 5 mm outside corner radii, 0.7 mm edge chamfers, and 0.6 mm entry lead-ins. All three final models were reviewed in isometric, front, top and right views.

| Product | Envelope XYZ, mm | Positions / pitch, mm | Bore, mm | Solid volume, cm³ | Reduction |
|---|---|---|---|---|---|
| microtube_rack_24 | 118 × 82 × 32 | 6 × 4 / 18 | 11.8 | 127.993 | 45.17% |
| centrifuge_rack_15ml_12 | 110 × 85 × 52 | 4 × 3 / 25 | 17 | 139.790 | 60.36% |
| centrifuge_rack_50ml_6 | 124 × 86 × 62 | 3 × 2 / 39 | 30 | 148.335 | 63.89% |

Volumes describe CAD geometry, not sliced filament consumption. Each model has a self-contained editable `source/model.py`, STL, millimeter-unit 3MF, and `renders/{render.png,thumb.webp,model.glb,status.json}`. The unchanged studio pipeline produces transparent images with no floor from actual exported geometry.

## Engineering review

Print upright on the plinth, PLA or PETG. Initial trial settings: 0.2 mm layers, 0.4 mm nozzle, four perimeters, 15–20% infill. Nominal webs are 5 mm at their narrow region, widening at the feet. Canopy thickness is at least 4 mm at the apex. Vault roofs rise at 45 degrees; their 0.8 mm rounded crests introduce small local bridges. Inspect slicer layers and calibrate bridging before deciding whether local supports are needed. No intentionally unsupported wide horizontal decks. Locating dimples leave 2.8 mm below tube tips.

Original footprints, pitches and bore sizes are retained. Boolean cylinder probes verify clear bores. Assumed tube bodies remain 11, 16 and 29 mm, giving 0.8/1/1 mm diametral clearance. Compatibility is brand-dependent: Eppendorf lists representative 1.5/2 mL tubes at 11 mm diameter; Corning drawings show some 15 mL tube envelopes larger than the preserved 17 mm bore. Do not claim compatibility with every 15 mL tube. Verify target tube drawings and print fit coupons, then check cap spacing, tip seating and removal clearance.

References: [Eppendorf catalogue](https://www.eppendorf.com/media/MAIN/00-General/Catalog/Product-Catalog-2024/Eppendorf-Maincatalog_2024_INT.pdf), [Corning dimensions](https://www.corning.com/catalog/cls/documents/protocols/CI-GLAB-003_REV11_DL.pdf).

Open passages improve visibility and cleaning access relative to closed wells. FDM surfaces and dimples still require an appropriate cleaning protocol. Physical fit, loaded tip-over, impact, creep and cleaning tests remain required. No physical strength test, FEA, sterilization or laboratory certification is claimed.

## Reproduction and validation

Use the existing CadQuery environment at `/home/mcianci/mcp/cadquery-contrib/mcp-server/.venv/bin/python`; system Python is unchanged. `build_redesign.py` stages and checks connected valid B-reps, watertight meshes, winding, positive triangle areas, one component, identical STL/3MF bounds and volumes, B-rep/mesh volume agreement, and bore clearance. Exact bounds and volumes are in `validation.json`. `validate.py` independently reopens the current exports.

Render using `PYTHONPATH=backend python -m app.render_product MODEL.stl --output OUTPUT` in the existing backend environment: 1200 px PNG, 640 px WebP, and matching GLB.

## Rollback

Geometric layer continuity was checked at 0.2 mm spacing: 160 microtube, 260 15 mL and 310 50 mL layers, with zero floating components. See `redesign/layer_validation.json`. This checks connected starting regions, not overhang extrusion quality or a complete slicer toolpath.

Old CAD/source assets are archived in `previous/block_v1/`. Previous hashed CAD and renders remain in application storage. `install_development.py` refuses non-development environments, matches only the three existing official collection keys, verifies unchanged bounds and ready renders, saves listing fields to `cad_backups/bridge_v2.json`, and changes only `cad_path` plus automatic ORM version/timestamp bookkeeping. Other listing fields are checked before commit.

Restore the three saved `cad_path` values in the development database and copy the archived model directories over the current ones to roll back. Product IDs, pricing, specifications and eligibility configuration are preserved. No production deployment.
