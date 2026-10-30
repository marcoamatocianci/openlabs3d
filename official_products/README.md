# Official rack manufacturing assets

**Revision 3:** Current files are the open-frame Bridge collection with the softened premium finish. See [BRIDGE.md](BRIDGE.md) and [finish details](redesign/finish-v3.md) for geometry, validation, manufacturing limitations, and rollback instructions. The description below documents the archived revision 1 block designs, retained in `previous/block_v1/`.

Each product folder contains real CadQuery STL/3MF exports and editable source/model.py. Units are millimeters; print upright, flat base on the bed. Vertical blind wells have a 3 mm floor and outer corners have a 2 mm radius. PLA or PETG, initially 0.2 mm layers, 3–4 perimeters and 15–20% infill; confirm settings with your printer. Supports should not be needed. These are substantial closed-body racks rather than the existing illustrative open-deck renders.

| Model | Envelope X × Y × Z (mm) | Arrangement | Bore diameter | Pitch X/Y |
|---|---|---|---|---|
| microtube_rack_24 | 118 × 82 × 32 | 6 × 4 | 11.8 | 18/18 |
| centrifuge_rack_15ml_12 | 110 × 85 × 52 | 4 × 3 | 17 | 25/25 |
| centrifuge_rack_50ml_6 | 124 × 86 × 62 | 3 × 2 | 30 | 39/39 |

Assumed nominal tube body diameters: 11, 16 and 29 mm respectively, giving 0.8/1/1 mm diametral clearance. Tube brands, cap envelopes, flange seating, conical tips, printer shrinkage and removal clearance require physical fit tests before use. No sterilization or laboratory qualification is claimed.

`python official_products/validate.py` requires numpy, trimesh, networkx, scipy and lxml. validation.json records independently reopened exports: watertight, consistent winding, one solid, positive triangle areas, matching bounds and volume (relative tolerance 1e-5). Actual OrcaSlicer import has not been tested.

`PYTHONPATH=backend python -m app.attach_official_cad` attaches STL files through existing restricted CAD storage using collection keys, without creating records or changing prices/capabilities. Set DATABASE_URL and UPLOAD_DIR explicitly for the intended local instance. Both original exports remain here. Existing preview GLBs remain conceptual and do not depict the new closed-body construction.
