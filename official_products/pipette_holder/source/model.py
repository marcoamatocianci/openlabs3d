"""OpenLabs3D pipette holder — BRIDGE family, parametric CadQuery source, printed as three parts.

The holder is built from the same vocabulary as the Bridge racks (microtube_rack_24, centrifuge_rack_*):
rounded-polygon prisms with 7 mm vertical radii, a 1.6 mm rolled top perimeter, a 0.8 mm bed chamfer,
gabled windows whose roofs rise at 45 degrees from vertical piers, 1.1 mm entry chamfers and cone
locating dimples where tips land. For n pipettes every prism is a rounded 2n-gon with a face towards
each pipette.

  plinth   rounded hexagon slab; tip wells with the rack's locating dimple; gabled through-windows
           between the positions
  mast     rounded hexagon column pierced by stacked gabled windows, leaving six piers
  collar   rounded hexagon ring wall on a faceted 48-degree underside, carried by one web in line with
           each pipette; between the webs it spans on the racks' 45-degree gables. Each pipette face
           carries the concave cradle
  canopy   solid rack-like deck on a faceted 48-degree underside; the finger hook rests on its flat top
           with the hook nose in a chamfered stadium slot, which also centres it

Printed parts (each upright as modelled, flat face on the bed, no supports intended):

  base     plinth and the foot of the mast; keyed spigot on top
  column   middle of the mast; keyed socket below, keyed spigot on top. Both joints are identical, so a
           second column stacks for a taller holder
  head     top of the mast with the collar, webs and canopy; keyed socket below

Every joint is a rounded n-gon spigot with a corner at every other mast corner, so a part seats only in
the n orientations that keep the head's positions over the base's tip wells. Each split plane is finished
like a rack body (rolled top below, bed chamfer above), so the joint reads as a deliberate reveal.

Millimetres, Z up, modelled assembled. Build and validate with ../../build_pipette_holder.py.
"""
import math
import cadquery as cq

# Functional datums carried over from the reference (exaple_product/mechanical-pipette-holder.stl):
# finger hook resting near r = 22 mm, nose pocket inboard of it, handle back leaning on a concave saddle,
# pipette axis near r = 58 mm. The pipette below is a stand-in envelope used to carve clearances; it is NOT a
# measurement of any brand. See README.md before relying on the fit.
PIPETTE_FIT = dict(
    axis_r=58.0,          # pipette axis radius from the holder centre
    body_r=15.5,          # handle radius at the cradle (back of grip at axis_r - body_r = 42.5)
    hook_reach=31.5,      # finger hook: from handle back towards the centre
    hook_width=16.0,
    hook_thickness=6.0,
    nose_drop=10.0,       # hook nose hanging below the crest
    above_hook=45.0,      # plunger top above the crest
    below_hook=205.0,     # pipette lower end below the crest (no tip fitted)
    tip_drop=60.0,        # a fitted 1000 uL tip beyond the nozzle; it must hang clear of the plinth
    clearance=0.6,        # radial clearance between the envelope and the holder
)

PARAMETERS = dict(
    positions=3,
    first_angle_deg=90.0,
    hook_z=280.0,                  # canopy top = underside of the finger hook = overall height (v1: 212)
    joint_z=(62.0, 142.0),         # split planes: base | column | head
    bed=(180.0, 180.0, 180.0),     # every part fits the smallest printer in the catalogue (Bambu Lab A1 mini)
    # Bridge finish, identical to the racks
    corner_radius=7.0,             # vertical edges of every prism
    top_fillet=1.6,                # rolled top perimeters
    bed_chamfer=0.8,
    entry_chamfer=1.1,             # slot, well and socket entries
    window_fillet=2.0,             # gabled window tool edges (apex left sharp so it prints without bridging)
    underside_deg=48.0,            # collar, canopy and socket ceilings, from horizontal (45 rule + tessellation margin)
    # plinth
    plinth_apothem=72.0,
    plinth_height=4.0,             # the racks' 4 mm base
    plinth_windows=(22.0, 64.0, 15.0),  # radial from, radial to, half width: pointed through-windows
    tip_well=(9.0, 1.0),           # radius, depth; the rack's 1.2/2.4 mm locating cone sits at its floor
    # mast: (bottom z, apex z) per window tier; each tier stays inside one part
    mast_apothem=17.0,
    mast_windows=[(12.0, 54.0), (90.0, 134.0), (180.0, 222.0), (230.0, 252.0)],
    mast_window_half=5.5,
    # joints
    spigot_inradius=8.0,           # rounded triangle for 3 positions, corners towards alternate mast corners
    spigot_corner=3.0,
    spigot_height=14.0,
    spigot_chamfer=1.0,
    joint_clearance=0.25,          # per side, as the DNA stand's joints
    crush_rib=(0.8, 0.45),         # radius, reach beyond the spigot face: 0.2 mm interference, one rib per face
    socket_floor=3.0,              # solid mast between a socket ceiling and the window above it
    joint_band=8.0,                # solid mast between a window apex and the joint above it
    # collar (cradle ring)
    collar_apothem=46.5,           # face towards each pipette
    collar_wall=6.0,
    collar_top=240.0,
    collar_underside_z=200.0,      # inner edge of the ring's 48-degree underside
    collar_vault_apex=230.0,       # 45-degree gables between the webs
    web_thickness=7.0,
    web_underside_deg=50.0,
    web_top=236.0,
    vault_margin=0.8,              # keeps gable tools off the web faces
    cradle_radius=22.0,            # concave cradle; contact stays on its centre line for handles up to R22
    # canopy (hook rest)
    canopy_apothem=31.0,
    canopy_underside_z=257.5,      # 6 mm rim at the pipette faces
    nose_slot=(15.0, 20.0, 8.0, 12.0),  # centre r, length (tangential), width (radial), depth: stadium slot
    min_pipette_gap=20.0,          # required free gap between neighbouring handles
)

P, F = PARAMETERS, PIPETTE_FIT
PARTS = ('base', 'column', 'head')


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


def seats():
    """Bottom of each part in the assembly; subtract it to get the part in print orientation."""
    j1, j2 = P['joint_z']
    return dict(base=0.0, column=j1, head=j2)


def socket_height():
    """Socket depth plus its faceted ceiling, measured from the joint plane."""
    a = P['spigot_inradius'] + P['joint_clearance']
    return P['spigot_height'] + 0.5 + a * math.tan(math.radians(P['underside_deg']))


def check_parameters():
    half = math.pi / P['positions']
    gap = 2 * F['axis_r'] * math.sin(half) - 2 * F['body_r']
    assert gap >= P['min_pipette_gap'], f'pipettes {gap:.1f} mm apart: lower positions or raise axis_r'
    assert F['axis_r'] - F['body_r'] - F['clearance'] < P['collar_apothem'], 'collar does not reach the handle'
    assert P['plinth_apothem'] > F['axis_r'] + P['tip_well'][0] + 4, 'tip wells must sit on the plinth'
    assert P['hook_z'] - F['below_hook'] - F['tip_drop'] >= P['plinth_height'] + 10, 'a fitted tip would reach the plinth'
    assert P['positions'] >= 3
    j1, j2 = P['joint_z']
    spans = [(0.0, j1, None), (j1, j2, j1), (j2, P['hook_z'], j2)]
    for bottom, apex in P['mast_windows']:
        assert apex - bottom > 2 * P['mast_window_half'], 'mast window too short for its gable'
        span = [s for s in spans if s[0] <= bottom and apex <= s[1]]
        assert span, f'mast window {bottom}-{apex} crosses a joint'
        z0, z1, socket = span[0]
        assert socket is None or bottom >= socket + socket_height() + P['socket_floor'], f'window {bottom} opens into a socket'
        assert z1 == P['hook_z'] or apex <= z1 - P['joint_band'], f'window {apex} leaves no solid band under the joint'
    heights = (j1 + P['spigot_height'], j2 - j1 + P['spigot_height'], P['hook_z'] - j2)
    assert max(heights) <= P['bed'][2], f'part heights {heights} exceed the bed'
    assert 2 * P['plinth_apothem'] / math.cos(math.pi / (2 * P['positions'])) <= P['bed'][0] + 2, 'plinth exceeds the bed'


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


# ------------------------------------------------------------------------------------------- joints
def key_angle():
    """A rounded n-gon at this angle has its corners on every other mast corner, where the wall is thickest."""
    return P['first_angle_deg'] - 90.0 / P['positions']


def key_faces():
    n = P['positions']
    return [key_angle() + 180.0 / n + i * 360.0 / n for i in range(n)]


def key(inradius, corner, z0, z1):
    n = P['positions']
    body = cq.Workplane('XY').polygon(n, 2 * inradius / math.cos(math.pi / n)).extrude(z1 - z0).translate((0, 0, z0))
    return at(body.edges('|Z').fillet(corner), key_angle())


def spigot(z, ribs=True):
    """Keyed spigot rising from a joint plane: chamfered lead-in and one vertical crush rib per face. The ribs
    deform on assembly, so the fit stays snug across printers that print holes slightly large or small."""
    a, h = P['spigot_inradius'], P['spigot_height']
    body = key(a, P['spigot_corner'], z, z + h).faces('>Z').edges().chamfer(P['spigot_chamfer'])
    if not ribs:
        return body
    r, reach = P['crush_rib']
    top = z + h - P['spigot_chamfer'] - 1.0
    x = a + reach - r
    rib = (cq.Workplane('XY').circle(r).extrude(top - z).translate((x, 0, z))
           .union(cq.Workplane('XY').add(cq.Solid.makeCone(r, 0.15, r - 0.15, cq.Vector(x, 0, top)))))
    return body.union(checked(union_all(at(rib, d) for d in key_faces())))


def socket(z):
    """Keyed socket opening downward from a joint plane. Its ceiling is a faceted pyramid rising at
    underside_deg from every face to a point, so it prints without bridging."""
    c = P['joint_clearance']
    a = P['spigot_inradius'] + c
    top = z + P['spigot_height'] + 0.5
    k = math.tan(math.radians(P['underside_deg']))
    cavity = key(a, P['spigot_corner'] + c, z - 1, top + a * k + 1)
    far = 100.0
    plane = (cq.Workplane('XZ').polyline([(-far, z - 2), (a + (top - z + 2) / k, z - 2), (-far, top + (a + far) * k)])
             .close().extrude(far, both=True))
    for d in key_faces():
        cavity = cavity.intersect(at(plane, d))
    return checked(cavity)


def mouth(part):
    """The racks' 1.1 mm entry chamfer round the socket mouth: leads the spigot in and absorbs elephant's foot."""
    edges = [e for w in part.faces('<Z').val().innerWires() for e in w.Edges()]
    assert edges, 'socket mouth not found on the bed face'
    return part.newObject(edges).chamfer(P['entry_chamfer'])


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


def mast(z0, z1, top=True, bottom=True):
    """One part's length of mast, with the window tiers that fall inside it."""
    body = prism(P['mast_apothem'], z0, z1, top=top, bottom=bottom)
    for low, apex in P['mast_windows']:
        if z0 <= low and apex <= z1:
            body = body.cut(checked(windows(P['mast_window_half'], low, apex)))
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
    # mast the web starts flat, so that stub must sit in a solid mast band, never inside a mast window, and
    # above the head's socket.
    m, r_out = P['mast_apothem'] - 1, F['axis_r'] - F['body_r'] - F['clearance'] - 0.4
    k = math.tan(math.radians(P['web_underside_deg']))
    wz0 = z0 + 1 - (r_out - m) * k
    for bottom, apex in P['mast_windows']:
        assert not bottom - 1 < wz0 < apex + 1, f'web root at z={wz0:.1f} falls inside a mast window'
    assert wz0 > P['joint_z'][1] + socket_height(), f'web root at z={wz0:.1f} falls below the head socket ceiling'
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


# ------------------------------------------------------------------------------------------- parts
def build_parts():
    """The three printable parts, in their assembled position (see seats() for print orientation)."""
    check_parameters()
    j1, j2 = P['joint_z']
    base = plinth().union(mast(0, j1, bottom=False)).union(spigot(j1))
    column = mouth(mast(j1, j2).cut(socket(j1))).union(spigot(j2))
    head = mast(j2, P['canopy_underside_z'] + 8, top=False).union(collar()).union(canopy())
    head = head.cut(checked(union_all(pipette_envelope(d, F['clearance']) for d in stations())))
    head = head.cut(checked(cradles())).cut(checked(hook_cuts()))
    head = mouth(head.cut(socket(j2)))
    return dict(base=base, column=column, head=head)


def printable(name, shape):
    """A part moved from its assembled position to its print position (bottom face on z = 0)."""
    return shape.translate((0, 0, -seats()[name]))


if __name__ == '__main__':
    for name, part in build_parts().items():
        s = printable(name, part).val()
        bb = s.BoundingBox()
        print(f'{name}: valid={s.isValid()} volume={s.Volume() / 1000:.2f} cm3 '
              f'bbox={bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f}')
