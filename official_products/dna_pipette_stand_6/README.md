# DNA pipette stand — 6 positions

A rotating bench stand for six single-channel pipettes: a double-helix tower with nucleotide rungs turns on a
wide foot, and each pipette hangs by its finger hook from a knob hanger under the OpenLabs3D finial.

Original OpenLabs3D geometry. Concept inspired by
["DNA pipette stand / holder, customizable" by pixel on Printables](https://www.printables.com/model/1332410-dna-pipette-stand-holder-customizable);
no files from that design were downloaded, traced or converted.

> **UNVERIFIED pipette fit.** Every fit dimension lives in `PIPETTE_FIT` in `source/model.py` and is a universal
> default, not a measurement of any brand. Do the test print below before relying on it.

## Files

| Path | Purpose |
|---|---|
| `source/model.py` | Parametric CadQuery source (`PARAMETERS`, `PIPETTE_FIT`) |
| `parts/{foot,tower_lower,tower_upper,crown}.{stl,3mf}` | Printable parts in print orientation |
| `dna_pipette_stand_6.3mf` | Kit: all four parts as separate objects; the file printing hosts download |
| `assembly/dna_pipette_stand_6_assembled.{stl,3mf}` | Assembled model, used only for renders and the 3D viewer |
| `renders/` | Studio still, thumbnail and viewer GLB from `backend/app/render_product.py` |
| `validation.json` | Measured results of `../build_pipette_stand.py` |

The listing stores the kit as its CAD file, so assigned hosts receive printable parts, while its render folder
comes from the assembly. `cad_dimensions` is the per-axis maximum of the sorted part envelopes, so printer
matching requires every part to fit, not the 288 mm tall assembly.

## Parts and printing

Assumed build volume: **200 × 200 × 200 mm per part** (fits every FDM printer in the seeded catalogue).
PLA, PETG or ABS; 0.4 mm nozzle, 0.2 mm layers, 4 perimeters, 15–20 % infill. No supports intended.

| Part | Envelope (mm) | Print |
|---|---|---|
| foot | 190 × 190 × 32 | flat; integral Ø20 mm spindle and thrust ring |
| tower_lower | 58 × 58 × 135 | upright; spindle bore below, keyed spigot on top |
| tower_upper | 58 × 58 × 131 | upright; keyed socket below, keyed spigot on top |
| crown | 160 × 144 × 25 | flat, in its use orientation; hub finial with embossed logo |

- **Rotation without hardware.** The tower's bore sits on the foot's spindle with 0.4 mm diametral clearance and
  rides on a 1.5 mm thrust ring; nothing else is required.
- **Joints.** Keyed D-shaped spigots with 0.25 mm clearance per side; the key also aligns the helix across the
  joint. They are friction fits; a drop of glue is optional.
- **Overhangs.** Helix strands rise at ~50° and rung faces slope at 50°, so downward faces stay within ~40° of
  vertical. Socket and bore ceilings are 50° cones ending in a 1 mm flat tip (the only faces over the 45° limit,
  < 1 mm² per part). `validation.json` records the measured area per part; every 0.2 mm layer is continuous.
- **Stability.** The knobs sit at 67 mm radius, inside the 95 mm foot radius, so a hanging load can't tip the stand
  over however the pipettes are arranged. Bumping it while loaded is still a risk. No ballast cavity.
- **Spacing.** 67 mm between neighbouring pipette centres; 258.5 mm free drop from the knob top to the foot.

## Pipette fit parameters (UNVERIFIED)

| Parameter | Default | Meaning |
|---|---|---|
| `knob_width` | 7.0 mm | must pass through the finger-hook opening |
| `knob_height` | 7.0 mm | knob height the hook rests on |
| `knob_length` | 18.0 mm | radial length available to the hook |
| `lip_height` | 13.0 mm | end lip that stops the hook sliding off |
| `hang_radius` | 67.0 mm | knob centre radius |
| `min_spacing` | 60.0 mm | required centre spacing between pipettes |
| `tip_clearance` | 240.0 mm | minimum drop from knob to foot for the longest pipette |

## Suggested test print

Print the **crown** first: 82 cm³, roughly 25 mm tall, and the only part that touches a pipette. Hang each of your
pipettes on a knob, holding the crown in your hand. Check that the finger hook passes over the knob and its lip,
that the pipette hangs vertically without touching its neighbours, and that it doesn't slide off when tilted.
Adjust `PIPETTE_FIT` and rebuild before printing the foot and towers. To check the bearing cheaply, print the foot
and only the bottom 25 mm of `tower_lower` (slicer cut).

## Regenerate

```
cd official_products
uv run --no-project --python 3.12 --with cadquery --with trimesh --with manifold3d --with shapely \
  --with networkx --with scipy --with lxml --with rtree python build_pipette_stand.py
cd ../backend && BLENDER_BIN=blender uv run --no-project --python 3.12 --with Pillow \
  python -m app.render_product ../official_products/dna_pipette_stand_6/assembly/dna_pipette_stand_6_assembled.stl \
  --output ../official_products/dna_pipette_stand_6/renders
blender -b -t 6 --python ../scripts/render_pipette_stand.py   # assets/products fallbacks + assets/models GLB
```

The listing is created by `app.seed_collection` (idempotent on `collection_key='dna-pipette-stand'`).
Attach the kit and renders to an existing instance with `PYTHONPATH=backend python -m app.attach_official_cad`
(set `DATABASE_URL` and `UPLOAD_DIR` explicitly; this also re-attaches the racks).

Pricing in the seed is a **placeholder**: €29.00 base, PLA/PETG/ABS at ×1.0.
