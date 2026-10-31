"""OpenLabs3D pipette holder — BRIDGE family, parametric CadQuery source (single printable part).

The holder is built from the same vocabulary as the Bridge racks (microtube_rack_24, centrifuge_rack_*):
rounded-polygon prisms with 7 mm vertical radii, a 1.6 mm rolled top perimeter, a 0.8 mm bed chamfer,
gabled windows whose roofs rise at 45 degrees from vertical piers, 1.1 mm entry chamfers and cone
locating dimples where tips land. For n pipettes every prism is a rounded 2n-gon with a face towards
each pipette.

  plinth   rounded hexagon slab; tip wells with the rack's locating dimple; gabled through-windows
           between the positions
  mast     rounded hexagon column pierced by stacked gabled windows, leaving six piers
  collar   rounded hexagon ring wall on a faceted 48-degree underside, carried by one web in line with
           each pipette; between the webs it
           spans on the racks' 45-degree gables. Each pipette face carries the concave cradle
  canopy   solid rack-like deck on a faceted 48-degree underside; the finger hook rests on its flat top
           with the hook nose in a chamfered stadium slot, which also centres it

Millimetres, Z up, printed upright as modelled. Build and validate with ../../build_pipette_holder.py.
"""
import math
import cadquery as cq

# Functional datums carried over from the reference (exaple_product/mechanical-pipette-holder.stl):
# finger hook resting near r = 22 mm, nose pocket inboard of it, handle back leaning on a concave saddle near
# r = 43 mm / z = 150-165, pipette axis near r = 58 mm. The pipette below is a stand-in envelope used to
# carve clearances; it is NOT a measurement of any brand. See README.md before relying on the fit.
PIPETTE_FIT = dict(
    axis_r=58.0,          # pipette axis radius from the holder centre
    body_r=15.5,          # handle radius at the cradle (back of grip at axis_r - body_r = 42.5)
    hook_reach=31.5,      # finger hook: from handle back towards the centre
    hook_width=16.0,
    hook_thickness=6.0,
    nose_drop=10.0,       # hook nose hanging below the crest
    above_hook=45.0,      # plunger top above the crest
    below_hook=205.0,     # pipette lower end below the crest (no tip fitted)
    clearance=0.6,        # radial clearance between the envelope and the holder
)

PARAMETERS = dict(
    positions=3,
    first_angle_deg=90.0,
    hook_z=212.0,                  # canopy top = underside of the finger hook = overall height
    # Bridge finish, identical to the racks
    corner_radius=7.0,             # vertical edges of every prism
    top_fillet=1.6,                # rolled top perimeters
    bed_chamfer=0.8,
    entry_chamfer=1.1,             # slot and well entries
    window_fillet=2.0,             # gabled window tool edges (apex left sharp so it prints without bridging)
    underside_deg=48.0,            # collar and canopy undersides, from horizontal (45 rule + tessellation margin)
    # plinth
    plinth_apothem=72.0,
    plinth_height=4.0,             # the racks' 4 mm base
    plinth_windows=(22.0, 64.0, 15.0),  # radial from, radial to, half width: pointed through-windows
    tip_well=(9.0, 1.0),           # radius, depth; the rack's 1.2/2.4 mm locating cone sits at its floor
    # mast
    mast_apothem=17.0,
    mast_windows=[(12.0, 54.0), (62.0, 96.0), (112.0, 154.0), (162.0, 184.0)],  # (bottom z, apex z) per tier
    mast_window_half=5.5,
    # collar (cradle ring)
    collar_apothem=46.5,           # face towards each pipette
    collar_wall=6.0,
    collar_top=172.0,
    collar_underside_z=132.0,      # inner edge of the ring's 48-degree underside
    collar_vault_apex=162.0,       # 45-degree gables between the webs
    web_thickness=7.0,
    web_underside_deg=50.0,
    web_top=168.0,
    vault_margin=0.8,              # keeps gable tools off the web faces
    cradle_radius=22.0,            # concave cradle; contact stays on its centre line for handles up to R22
    # canopy (hook rest)
    canopy_apothem=31.0,
    canopy_underside_z=189.5,     # 6 mm rim at the pipette faces
    nose_slot=(15.0, 20.0, 8.0, 12.0),  # centre r, length (tangential), width (radial), depth: stadium slot
    min_pipette_gap=20.0,          # required free gap between neighbouring handles
)

P, F = PARAMETERS, PIPETTE_FIT


def stations():
    return [P['first_angle_deg'] + i * 360.0 / P['positions'] for i in range(P['positions'])]


def axes():
    """Face-normal axes of the 2n-gon: one through each pipette face and its opposite face."""
    return [P['first_angle_deg'] + i * 180.0 / P['positions'] for i in range(P['positions'])]


def at(shape, deg):
    return shape.rotate((0, 0, 0), (0, 0, 1), deg)


def union_all(shapes):
    out = None
    for s in shapes:
        out = s if out is None else out.union(s)
    return out


def checked(cutter):
    """Boolean tools must be valid positive-volume solids; a degenerate union silently loses features."""
    for s in cutter.solids().vals():
        assert s.isValid() and s.Volume() > 0, 'degenerate cutter solid'
    return cutter


def check_parameters():
    half = math.pi / P['positions']
    gap = 2 * F['axis_r'] * math.sin(half) - 2 * F['body_r']
    assert gap >= P['min_pipette_gap'], f'pipettes {gap:.1f} mm apart: lower positions or raise axis_r'
    assert F['axis_r'] - F['body_r'] - F['clearance'] < P['collar_apothem'], 'collar does not reach the handle'
    assert P['plinth_apothem'] > F['axis_r'] + P['tip_well'][0] + 4, 'tip wells must sit on the plinth'
    for bottom, apex in P['mast_windows']:
        assert apex - bottom > 2 * P['mast_window_half'], 'mast window too short for its gable'
    assert P['positions'] >= 3


# ------------------------------------------------------------------------------------------- primitives
def prism(apothem, z0, z1, top=True, bottom=True):
    """Rounded 2n-gon prism with a face towards each pipette, finished like a Bridge rack body."""
    sides = 2 * P['positions']
    circum = apothem / math.cos(math.pi / sides)
    body = cq.Workplane('XY').polygon(sides, 2 * circum).extrude(z1 - z0).translate((0, 0, z0))
    body = body.edges('|Z').fillet(P['corner_radius'])
    if top:
        body = body.faces('>Z').edges().fillet(P['top_fillet'])
    if bottom:
        body = body.faces('<Z').edges().chamfer(P['bed_chamfer'])
    return at(body, P['first_angle_deg'] - 180.0 / sides)


def underside(r0, z0, z1):
    """Everything above a faceted 2n-sided pyramid whose planar faces leave apothem r0 at z0 and rise
    outwards at underside_deg (one facet per prism face), up to z1."""
    k = math.tan(math.radians(P['underside_deg']))
    far = 300.0
    wedge = (cq.Workplane('XZ').polyline([(-far, z0 + (-far - r0) * k), (r0 + (z1 - z0) / k, z1), (-far, z1)])
             .close().extrude(far, both=True))
    sides = 2 * P['positions']
    out = None
    for i in range(sides):
        w = at(wedge, P['first_angle_deg'] + i * 360.0 / sides)
        out = w if out is None else out.intersect(w)
    return out


def gable(half, bottom, apex, x0=-100.0, x1=100.0):
    """The racks' window: slightly tapered piers, 45-degree roof to a sharp apex, 2 mm tool fillets.
    Built along X from x0 to x1."""
    shoulder = apex - half
    profile = [(-half + 2, bottom), (half - 2, bottom), (half, shoulder), (0, apex), (-half, shoulder)]
    tool = cq.Workplane('YZ').polyline(profile).close().extrude(x1 - x0).translate((x0, 0, 0))
    soft = [e for e in tool.edges('|X').vals() if e.Center().z < apex - 1e-3]
    return tool.newObject(soft).fillet(P['window_fillet'])


def windows(half, bottom, apex):
    return union_all(at(gable(half, bottom, apex), d) for d in axes())


# ------------------------------------------------------------------------------------------- elements
def plinth():
    r, depth = P['tip_well']
    h, c = P['plinth_height'], P['entry_chamfer']
    body = prism(P['plinth_apothem'], 0, h)
    a, b, w = P['plinth_windows']
    pointed = (cq.Workplane('XY').polyline([(a, 0), (a + w, w), (b - w, w), (b, 0), (b - w, -w), (a + w, -w)])
               .close().extrude(h + 2).translate((0, 0, -1)).edges('|Z').fillet(P['window_fillet']))
    body = body.cut(checked(union_all(at(pointed, d + 180.0 / P['positions']) for d in stations())))
    well = (cq.Workplane('XY').circle(r).extrude(depth + 1).translate((0, 0, h - depth))
            .union(cq.Workplane('XY').add(cq.Solid.makeCone(r, r + c + 0.01, c + 0.01, cq.Vector(0, 0, h - c))))
            .union(cq.Workplane('XY').add(cq.Solid.makeCone(1.2, 2.4, 1.2, cq.Vector(0, 0, h - depth - 1.2)))))
    return body.cut(checked(union_all(at(well.translate((F['axis_r'], 0, 0)), d) for d in stations())))


def mast():
    body = prism(P['mast_apothem'], 0, P['canopy_underside_z'] + 8, top=False)
    for bottom, apex in P['mast_windows']:
        body = body.cut(checked(windows(P['mast_window_half'], bottom, apex)))
    return body


def collar():
    """Ring wall on a 48-degree underside, gabled between the webs, plus one web per pipette."""
    a, wall, top, z0 = P['collar_apothem'], P['collar_wall'], P['collar_top'], P['collar_underside_z']
    inner = a - wall
    ring = prism(a, z0 - 1, top, bottom=False).cut(prism(inner, z0 - 60, top + 5, top=False, bottom=False))
    ring = ring.intersect(underside(inner - 1, z0, top + 1))
    # Gables between neighbouring webs (half-tunnels, outwards from the mast only).
    half_angle, t2 = math.pi / P['positions'], P['web_thickness'] / 2
    w = (inner - 1) * math.sin(half_angle) - t2 - P['vault_margin']
    apex = P['collar_vault_apex']
    assert apex - w <= z0 + 1, 'gable shoulders would leave the ring edge floating'
    x_from = (w + t2 + P['vault_margin']) / math.tan(half_angle)
    assert x_from < math.sqrt((inner - 1) ** 2 - w ** 2), 'gable cannot reach the ring between webs'
    tool = gable(w, z0 - 40, apex, x_from, x_from + 80)
    ring = ring.cut(checked(union_all(at(tool, d + 180.0 / P['positions']) for d in stations())))
    # Webs: lower edge leaves the mast at web_underside_deg; outer edge stops short of the handle. Inside the
    # mast the web starts flat, so that stub must sit in a solid mast band, never inside a mast window.
    m, r_out = P['mast_apothem'] - 1, F['axis_r'] - F['body_r'] - F['clearance'] - 0.4
    k = math.tan(math.radians(P['web_underside_deg']))
    wz0 = z0 + 1 - (r_out - m) * k
    for bottom, apex in P['mast_windows']:
        assert not bottom - 1 < wz0 < apex + 1, f'web root at z={wz0:.1f} falls inside a mast window'
    web = (cq.Workplane('XZ').polyline([(0, wz0), (m, wz0), (r_out, z0 + 1), (r_out, P['web_top']), (0, P['web_top'])])
           .close().extrude(t2, both=True))
    web = web.edges('|Y').fillet(P['window_fillet'])
    return ring.union(union_all(at(web, d) for d in stations()))


def canopy():
    top = P['hook_z']
    block = prism(P['canopy_apothem'], P['canopy_underside_z'] - 1, top, bottom=False)
    return block.intersect(underside(P['mast_apothem'] - 1, P['canopy_underside_z'], top + 1))


def cradles():
    """Concave cylinders behind each handle; the innermost line sits at the handle back plus clearance."""
    R = P['cradle_radius']
    contact = F['axis_r'] - F['body_r'] - F['clearance']
    z0 = P['collar_underside_z']
    cyl = cq.Workplane('XY').circle(R).extrude(P['collar_top'] - z0 + 40).translate((contact + R, 0, z0 - 30))
    return union_all(at(cyl, d) for d in stations())


def hook_cuts():
    """Stadium nose slot with the racks' 1.1 mm entry chamfer; 20 mm long for a 16 mm hook nose, so it also
    centres the hook (+/- 2 mm) on the flat deck."""
    H = P['hook_z']
    rc, length, width, depth = P['nose_slot']
    c = P['entry_chamfer']
    slot = cq.Workplane('XY').workplane(offset=H - depth).slot2D(length, width, 90).extrude(depth + 5)
    entry = (cq.Workplane('XY').workplane(offset=H - c).slot2D(length, width, 90)
             .workplane(offset=c + 0.01).slot2D(length + 2 * c + 0.02, width + 2 * c + 0.02, 90).loft())
    cut = slot.union(entry).translate((rc, 0, 0))
    return union_all(at(cut, d) for d in stations())


# ------------------------------------------------------------------------------------------- envelope
def pipette_envelope(deg, grow=0.0):
    """Stand-in pipette at one position: revolved body with a finger hook and nose. grow = clearance."""
    H, R, ax = P['hook_z'], F['body_r'] + grow, F['axis_r']
    pts = [(0, H - F['below_hook']), (2.5 + grow, H - F['below_hook']), (7 + grow, H - 180), (7 + grow, H - 125),
           (R, H - 92), (R, H + 25), (8 + grow, H + 25), (8 + grow, H + F['above_hook']), (0, H + F['above_hook'])]
    body = cq.Workplane('XZ').polyline(pts).close().revolve(360, (0, 0, 0), (0, 1, 0)).translate((ax, 0, 0))
    back = ax - F['body_r']
    nose_r = back - F['hook_reach']
    w = F['hook_width'] + 2 * grow
    arm = cq.Workplane('XY').box(back - nose_r + 2, w, F['hook_thickness'] + grow, centered=(False, True, False)) \
        .translate((nose_r - grow, 0, H))
    nose = cq.Workplane('XY').box(5 + 2 * grow, w, F['nose_drop'] + 1, centered=(False, True, False)) \
        .translate((nose_r - grow, 0, H - F['nose_drop']))
    return at(body.union(arm).union(nose), deg)


def proxies():
    """Stand-in pipettes for renders and clearance checks only (never exported as the product)."""
    return union_all(pipette_envelope(d) for d in stations())


# ------------------------------------------------------------------------------------------- assembly
def build():
    check_parameters()
    body = plinth().union(mast()).union(collar()).union(canopy())
    body = body.cut(checked(union_all(pipette_envelope(d, F['clearance']) for d in stations())))
    body = body.cut(checked(cradles())).cut(checked(hook_cuts()))
    return body


if __name__ == '__main__':
    s = build().val()
    bb = s.BoundingBox()
    print(f'valid={s.isValid()} volume={s.Volume() / 1000:.2f} cm3 bbox={bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f}')
