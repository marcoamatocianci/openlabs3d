# Pipette holder — 3 positions, Bridge family, three-part kit

A bench holder for three hook-hung single-channel pipettes, redesigned from the reference
`exaple_product/mechanical-pipette-holder.stl` (kept unchanged; SHA-256 recorded in `validation.json`).
It uses the same design language as the Bridge racks (`microtube_rack_24`, `centrifuge_rack_15ml_12`,
`centrifuge_rack_50ml_6`), so the collection reads as one family.

Revision 2 is **68 mm taller** (280 mm to the hook rest, was 212 mm) and prints as **three separate parts**
(base, column, head) joined by keyed press-fit spigots. Every part fits a 180 × 180 × 180 mm printer. The
single-part revision 1 is archived in `../previous/pipette_holder_v1/`.

> **UNVERIFIED pipette fit.** Every fit dimension lives in `PIPETTE_FIT` in `source/model.py`. They are carried
> over from the reference geometry, not measured on any brand. Do the test prints below before relying on it.

![render](renders/render.png)

## Files

| Path | Purpose |
|---|---|
| `source/model.py` | Parametric CadQuery source (`PARAMETERS`, `PIPETTE_FIT`, `build_parts()`) |
| `parts/{base,column,head}.{stl,3mf}` | Printable parts in print orientation, millimetres |
| `pipette_holder.3mf` | Kit: all three parts as separate objects; the file printing hosts download |
| `assembly/pipette_holder_assembled.{stl,3mf}` | Assembled model, used only for renders and the 3D viewer |
| `renders/` | Studio still, thumbnail and viewer GLB of the assembly, from `backend/app/render_product.py` |
| `validation.json` | Measured results of `../build_pipette_holder.py` (per part, joints, fit, stability) |
| `review/` | Review sheets: stand-in pipettes, exploded parts with a joint section, parts on 180 mm beds; stand-in pipette STL (display only) |
| `reference/` | Measurements and render of the reference, made before the redesign |
| `concepts/` | Concept studies: `concepts.py` (A, B, C), `concept_b_fin_tiers_model.py`, their STLs and renders |

As with the DNA pipette stand, a listing would store the kit as its CAD file and take its renders from the
assembly. `host_cad_dimensions_mm` in `validation.json` (93.0 × 144.0 × 164.1) is the per-axis maximum of the
sorted part envelopes, so printer matching requires every part to fit, not the 280 mm assembly.

## How the reference works (and what was kept)

The reference is a 175.6 × 153.9 × 218 mm tripod with a 31 mm column and three positions at 120°. Each pipette
hangs by its **finger hook** over a rounded crest (r ≈ 22 mm), with the hook nose in a D-shaped pocket.
The back of the handle leans on a **concave band** (r ≈ 43 mm). The lower end hangs over a leg with a raised-rim
trough. Only the hook and the back of the grip touch the holder, so plunger and ejector buttons stay free. These
datums are preserved: hook rest at r 19–31 mm, nose pocket at r 11–19 mm, cradle contact at r 41.9 mm, pipette
axis at r 58 mm.

Weak points found: the mesh is not watertight (7 shells, slivers at z 102–117 mm). The loop bands are thin, with
≈45° inner overhangs. A tripod footprint puts the tipping edge 56.6 mm from the centre. The deep blind pockets
are hard to clean.

## Design

Built entirely from the Bridge vocabulary: rounded-polygon prisms with **7 mm vertical radii**, **1.6 mm** rolled
top perimeters, a **0.8 mm** bed chamfer, **gabled windows** (tapered piers, 45° roof, 2 mm tool fillets),
**1.1 mm entry chamfers** and the racks' **1.2/2.4 mm locating cone** where tips land. With *n* positions every
prism is a rounded 2*n*-gon with one face towards each pipette.

| Element | Function |
|---|---|
| Canopy (hex deck, z 257.5–280) | Finger hook rests on the flat deck. The nose drops into a chamfered 20 × 8 mm stadium slot, which also centres a 16 mm hook ±2 mm |
| Collar (hex ring, 6 mm wall, z 200–240) | Each pipette face carries a concave R22 cradle: handles up to Ø44 touch along its centre line, never on an edge. Between positions the ring spans on 45° gables |
| Webs (7 mm, one per pipette) | Carry each cradle straight down to the mast; lower edge rises at 50° |
| Mast (hex column, apothem 17) | Four tiers of gabled windows, one or two per part, leave six piers; open for cleaning |
| Plinth (hex slab, 4 mm) | Hexagonal footprint (tipping edge 71.3 mm), tip wells with locating cone, pointed through-windows between positions |

### Why 280 mm

The hook rest rose from 212 to 280 mm so that the stand-in pipette (205 mm below the hook) hangs **71.7 mm**
above the plinth instead of 4.7 mm, and still clears it by **12.3 mm** with a 1000 µL tip fitted (`tip_drop`,
60 mm beyond the nozzle, unverified). `check_parameters()` enforces at least 10 mm. All head geometry moved up
unchanged; the extra height is mast.

### Parts and joints

| Part | Envelope (mm) | Contains | Joints | PLA est. |
|---|---|---|---|---|
| base | 164.1 × 144.0 × 76 | plinth, mast to z 62, window tier 12–54 | spigot on top | 103 g |
| column | 37.1 × 34.0 × 94 | mast z 62–142, window tier 90–134 | socket below, spigot on top | 41 g |
| head | 105.2 × 93.0 × 138 | mast from z 142, collar, webs, canopy, window tiers 180–222 and 230–252 | socket below | 155 g |

- **Keyed spigots.** Each joint is a rounded triangle (inradius 8 mm, 3 mm corners, 14 mm engagement) with its
  corners on alternate mast corners, where the wall is thickest (at least 5.1 mm round the socket). A part seats only in
  the three orientations that keep the head's positions over the base's tip wells; a 60° error cannot be assembled.
- **Press fit that tolerates printers.** 0.25 mm clearance per side, as on the DNA stand, plus one vertical
  0.8 mm crush rib per spigot face reaching 0.2 mm into the socket wall. The ribs deform on assembly, so the fit
  stays snug whether a printer prints holes slightly large or small. The spigot core never touches its socket
  (checked on the exact B-rep); the ribs are the only overlap (4.8 mm³ per joint). A drop of glue is optional.
- **Support-free sockets.** Sockets open downward from each part's bed face. The mouth carries the racks' 1.1 mm
  entry chamfer, which leads the spigot in and absorbs elephant's foot. The ceiling is a faceted pyramid rising
  at 48° from every face to a point, so nothing bridges. A solid band of at least 3 mm separates each ceiling
  from the window above it, and 8 mm of solid mast sits under every joint.
- **Reveals.** Each split plane is finished like a rack body: rolled 1.6 mm top below, 0.8 mm bed chamfer above.
  The joints read as two deliberate reveal lines on the mast, each 8 mm above a window apex.
- **Stackable.** Both joints are identical. A second column adds 80 mm (hook rest at 360 mm) for longer pipettes.
  That configuration is not validated, and it is less stable; see below.

## Concepts

All concepts share the reference datums and were checked against the same stand-in pipette (`concepts/`).

| Concept | Idea | Solid cm³ | PLA est. g | Tipping edge mm | Verdict |
|---|---|---|---|---|---|
| A Minimal Precision | Slim column, two 45° discs, tri-lobe plinth | 393.5 | 192 | 48.0 | Generic candlestick; small saddles; least stable |
| B Architectural Framework | Spline fins in line with the pipettes, round vaulted tiers, orbit ring | 231.9 | 192 | 78.5 | Lightest and most stable, but its own vocabulary, not the racks' |
| C Contemporary Industrial | Vase spine with flutes cut by the pipette envelope | 661.4 | 275 | 79.9 | Sculptural, very heavy, pawn-like |
| **Bridge tower (chosen)** | B's structure re-expressed in the rack vocabulary | **281.0** | **256** | **71.3** | Coherent with the racks; stable; open and cleanable |

The concept figures are for the 212 mm single-part height. B was the strongest engineering concept. It was carried
through full refinement (`concept_b_fin_tiers_model.py`, watertight and validated) before being re-expressed in the
rack language to keep the collection coherent.

## Comparison

| | Reference | Revision 1 (single part) | **Revision 2 (this kit)** |
|---|---|---|---|
| Envelope X × Y × Z (mm) | 175.6 × 153.9 × 218.0 | 164.1 × 144.0 × 212.0 | **164.1 × 144.0 × 280.0** |
| Largest part (mm) | one piece | 164.1 × 144.0 × 212.0 | **164.1 × 144.0 × 76; tallest 138** |
| Fits a 180 mm cube printer | no | no | **yes, every part** |
| Solid volume | 330.9 cm³ (open mesh) | 281.0 cm³ | **337.7 cm³** |
| PLA, same estimate | 188 g | 256 g | **298 g** |
| Pipette lower end above plinth | — | 4.7 mm | **71.7 mm** |
| Centre to tipping edge | 56.6 mm (tripod) | 71.3 mm | **71.3 mm** |
| Mesh | not watertight, 7 shells | watertight single solid | **3 watertight single solids** |

The material estimate is coarse (4 × 0.45 mm perimeters + 15 % infill over the whole surface); slice it to know.
The thin walls and piers print almost entirely as perimeters, so the estimate is above the reference's despite
a similar solid volume.

## Printing

Print every part upright as modelled, flat face down. No supports intended. PLA or PETG, 0.4 mm nozzle,
0.2 mm layers, 4 perimeters, 15–20 % infill, matching the racks. Every part fits every FDM printer in the seeded
catalogue, including the Bambu Lab A1 mini (180 × 180 × 180 mm). Measured per part (`validation.json`):

- Watertight, consistently wound single solids; STL and 3MF bounds and volumes identical. The B-rep volume,
  integrated in 1 mm slabs, matches each mesh within 0.01 %.
- No downward face steeper than 46.0° from vertical. Every face over 45° is a designed 45° face within
  tessellation tolerance, and no face is over 50°.
- 0 floating regions at 0.2 mm layers. The check also catches regions that start from a single point.
- 0 mm³ intersection with the stand-in pipette envelope (0.6 mm clearance carved around it).
- **Use a 5–8 mm brim on the column and the head.** They stand on about 5 cm² of mast (the socket takes the
  middle), and the head is 138 mm tall with its collar high up. The base has 151.7 cm² on the bed and needs none.
- Assembly: press the column onto the base, then the head onto the column, turning each until the triangle
  drops in. If a joint is too tight, scrape the crush ribs; if it is loose, add a drop of glue.

Gable apexes are left sharp, so no window needs bridging. This differs from the racks, which round their crests
by 2 mm and accept a small bridge.

## Assumptions that need a physical prototype

- **Pipette fit.** Hook reach, hook width, nose size, handle radius, length below the hook and tip length are
  reference-derived defaults.
- **Buttons and labels.** Contact is only at the hook and the back of the grip. Confirm that no ejector or
  volume lock on your models sits on the back of the grip at the cradle height (z 210–237 mm).
- **Stability.** Assumes 120 g pipettes with their mass centre 72 mm below the hook. Being taller costs some
  margin. Sideways push at the deck to tip it: 0.74 N empty, 0.80 N with one pipette, 1.64 N with three
  (revision 1: 0.85, 0.92 and 2.03 N). Static tilt to tip with one pipette: 18.3° (was 23.9°). The plinth was kept
  at the same size; widening `plinth_apothem` to 76 mm still fits a 180 mm bed if more margin is needed. Tests to
  run: loaded tip-over, bumps, creep under load.
- **Joints.** The crush-rib press fit depends on the printer and material; the fit has not been printed yet. No
  pull-out or bending test.
- **Strength.** No FEA or impact test. Check the mast piers, the web roots and the spigot roots on the first print.
- **Cleaning.** All surfaces are reachable through the windows. FDM surfaces still need a suitable cleaning
  protocol. No sterilisation or laboratory qualification is claimed.

## Suggested test prints

1. **Hook fit, about 30 g.** Print only the top 30 mm of the head (slicer cut at 108 mm): canopy and slots.
   Check that each pipette's finger hook sits flat on the deck with its nose in the slot.
2. **Joint fit, about 29 g.** Print the column twice, cut in the slicer: its bottom 30 mm (socket) and its top
   30 mm (spigot, cut at 64 mm). Press them together and judge the force, play and pull-out.
3. Then print all three parts and check that each handle sits on its cradle, hangs vertically, clears its
   neighbours and lands over its well.

## Regenerate

```
cd official_products
uv run --no-project --python 3.12 --with cadquery --with trimesh --with manifold3d --with shapely \
  --with networkx --with scipy --with lxml --with rtree python build_pipette_holder.py
cd ../backend && BLENDER_BIN=blender uv run --no-project --python 3.12 --with Pillow \
  python -m app.render_product ../official_products/pipette_holder/assembly/pipette_holder_assembled.stl \
  --output ../official_products/pipette_holder/renders
```

The assembly is a display-only union in which each part sinks 0.05 mm into the one below, so its file measures
279.9 mm; the printed stack is 280 mm.

## On the site

On the local development site the kit replaces the single-part model of the admin-created official listing
"Pipette Holder Tree" (listing 17); its title, description, price and colours were left as entered. Hosts download
the kit, buyers see the assembly renders, and orders placed earlier keep the model they were sold with. To attach a
rebuilt kit (copy the folder into the backend container first; the image does not contain `official_products/`):

```
python -m app.attach_official_cad --listing 17 --kit pipette_holder --root /tmp/official_products
```

This also sets the listing's dimensions text from the assembled size. It is not part of `app.seed_collection`,
so other installations need their own listing.
