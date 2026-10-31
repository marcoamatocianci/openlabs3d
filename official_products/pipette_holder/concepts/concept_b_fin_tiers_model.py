"""OpenLabs3D pipette holder — parametric CadQuery source (single printable part).

Three fin piers stand in line with the pipettes. Each fin's outline is the support path of one pipette:
splayed foot, slim mast, cradle, hook crown. The fins meet in a Y-section mast and carry two vaulted
tiers: a saddle band whose cradles are cut by the pipette envelope itself, and a hook crown with a
self-centring dip and a nose pocket. An orbit ring ties the feet at the bed so the tipping footprint is a
circle (r = ring_r[1]) instead of a tripod (r_tip / 2). Pointed vaults under both tiers keep every
downward face at 45 degrees or steeper, in the vocabulary of the Bridge rack collection.

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
    hook_z=212.0,                 # crest top: underside of the finger hook; overall height
    fin_thickness=7.5,
    fin_edge_radius=3.0,
    hub_radius=6.5,
    # hook crown: annulus with a 45-degree chamfered underside and pointed vaults between fins
    crown_r=(19.0, 31.0),
    crown_height=20.0,
    crown_vault_crown=7.0,        # material left above each crown vault apex
    crest_dip=(40.0, 2.2),        # transverse self-centring dip: cylinder radius, depth at the centre
    nose_pocket=(11.0, 19.0, 20.0, 22.0, 3.5),  # r from, r to (= crown inner r), width, depth, corner radius
    cap_recess=4.0,               # dial cap top below the crest rim
    # saddle band
    band_r=(39.0, 46.5),
    band_z=(134.0, 168.0),
    band_vault_spring=126.0,      # vaults spring below the band so their 45-degree apex fits under it
    band_vault_crown=12.0,
    cradle_radius=22.0,           # concave cradle; contact stays on its centre line for handles up to R22
    tier_top_radius=3.0,
    tier_underside_deg=48.0,      # conical tier undersides, from horizontal; margin over the 45-degree rule
    # bed
    ring_r=(70.0, 79.0),
    ring_height=5.5,
    ring_top_radius=2.5,
    tip_pad=(12.0, 7.0, 10.0, 2.4),  # pad radius, pad height, dimple sphere radius, dimple depth
    bottom_chamfer=0.6,
    vault_margin=0.8,             # keeps vault cutters off the fin faces
    min_pipette_gap=20.0,         # required free gap between neighbouring handles
)

P, F = PARAMETERS, PIPETTE_FIT


def stations():
    return [P['first_angle_deg'] + i * 360.0 / P['positions'] for i in range(P['positions'])]


def at(shape, deg):
    return shape.rotate((0, 0, 0), (0, 0, 1), deg)


def union_all(shapes):
    out = None
    for s in shapes:
        out = s if out is None else out.union(s)
    return out


def check_parameters():
    n, half = P['positions'], math.pi / P['positions']
    gap = 2 * F['axis_r'] * math.sin(half) - 2 * F['body_r']
    assert gap >= P['min_pipette_gap'], f'pipettes {gap:.1f} mm apart: lower positions or raise axis_r'
    assert F['axis_r'] - F['body_r'] - F['clearance'] < P['band_r'][1], 'band does not reach the handle'
    assert P['ring_r'][0] > F['axis_r'] + P['tip_pad'][0] - 4, 'tip pads must overlap the ring'
    assert n >= 3


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


# ------------------------------------------------------------------------------------------- elements
def fin(deg):
    """One pier, drawn in its radial plane. Outline points are (r, z)."""
    H, t = P['hook_z'], P['fin_thickness']
    b0, b1 = P['band_r']
    z0, z1 = P['band_z']
    c0 = P['crown_r'][1] - 2
    r_ring = P['ring_r'][1] - 1
    lower = [(r_ring, P['ring_height']), (64, 6.2), (50, 8.5), (38, 15.5), (28, 29), (22.5, 50), (20.5, 80),
             (21, 100), (28.5, z0 - 13), (b0 + 1, z0 + 1), (b0 + 1.5, z0 + 10)]
    # The fin edge stays inside the band (r <= b0 + 1.5, short of the handle clearance line) so the cradle is
    # formed by the band alone and the envelope cut leaves no step in the fin. It then turns inwards and
    # leaves through the band's open centre, crossing the inner wall at an angle below the rolled top:
    # a fin edge meeting that roll near-tangentially tessellates into open edges.
    # One tangent-continuous spline from foot to crown: a kink in the outline breaks the edge fillet's mesh.
    upper = [(b0 + 1.5, z1 - 12), (b0 - 2.5, z1), (c0 + 3, z1 + 14), (c0, H - P['crown_height'])]
    wp = (cq.Workplane('XZ').moveTo(0, 0).lineTo(r_ring, 0).lineTo(*lower[0])
          .spline(lower[1:] + upper, includeCurrent=True).lineTo(c0, H - 5).lineTo(0, H - 5).close())
    f = wp.extrude(t / 2, both=True).edges('not(<Z)').fillet(P['fin_edge_radius'])
    return at(f, deg)


def tier(r_in, r_out, z0, z1, top_radius):
    """Annulus whose underside is a cone rising outwards at tier_underside_deg, with a rolled top."""
    rr = top_radius
    rise = (r_out - r_in) * math.tan(math.radians(P['tier_underside_deg']))
    prof = (cq.Workplane('XZ').moveTo(r_in, z0).lineTo(r_out, z0 + rise).lineTo(r_out, z1 - rr)
            .threePointArc((r_out - rr * (1 - math.sqrt(.5)), z1 - rr * (1 - math.sqrt(.5))), (r_out - rr, z1))
            .lineTo(r_in + rr, z1)
            .threePointArc((r_in + rr * (1 - math.sqrt(.5)), z1 - rr * (1 - math.sqrt(.5))), (r_in, z1 - rr))
            .close())
    return prof.revolve(360, (0, 0, 0), (0, 1, 0))


def vaults(r_in, z_spring, z_apex):
    """Pointed vault cutters between neighbouring fins. Each half-arch is a circular arc through the
    springing point whose tangent at the apex is exactly 45 degrees: no underside flatter than that."""
    half = math.pi / P['positions']
    t2 = P['fin_thickness'] / 2
    w = r_in * math.sin(half) - t2 - P['vault_margin']
    d = z_apex - z_spring
    assert d > w, f'vault too flat to print: rise {d:.1f} <= half-span {w:.1f}'
    x_from = (w + t2 + P['vault_margin']) / math.tan(half)   # along the bisector, clear of both fins
    assert x_from < math.sqrt(r_in ** 2 - w ** 2), 'vault cannot reach the tier between fins'
    c = (w * w + d * d) / (2 * (d - w))
    rho, zc = c * math.sqrt(2), z_apex - c

    def mid(s):
        a0 = math.atan2(z_spring - zc, s * w + s * c)
        a1 = math.atan2(z_apex - zc, s * c)
        a = (a0 + a1) / 2
        return (-s * c + rho * math.cos(a), zc + rho * math.sin(a))

    low = z_spring - 20
    prof = (cq.Workplane('YZ').moveTo(-w, low).lineTo(w, low).lineTo(w, z_spring)
            .threePointArc(mid(1), (0, z_apex)).threePointArc(mid(-1), (-w, z_spring)).close()
            .extrude(80).translate((x_from, 0, 0)))
    return union_all(at(prof, d0 + 180.0 / P['positions']) for d0 in stations())


def cradles():
    """Concave cylinders behind each handle; the innermost line sits at the handle back plus clearance."""
    R = P['cradle_radius']
    contact = F['axis_r'] - F['body_r'] - F['clearance']
    z0, z1 = P['band_z']
    cyl = cq.Workplane('XY').circle(R).extrude(z1 - z0 + 20).translate((contact + R, 0, z0 - 10))
    return union_all(at(cyl, d) for d in stations())


def hook_cuts():
    """Nose pocket inboard of the crest plus the shallow transverse dip that self-centres the hook."""
    H = P['hook_z']
    a, b, width, depth, corner = P['nose_pocket']
    dip_r, dip_depth = P['crest_dip']
    pocket = cq.Workplane('XY').box(b + 4 - a, width, depth + 20, centered=(False, True, False)) \
        .edges('|Z').fillet(corner).translate((a, 0, H - depth))
    # The slot's outer wall is the crown's inner face: a rectangle reaching past it would notch the ring
    # and leave hanging corners under the 48-degree cone.
    pocket = pocket.intersect(cq.Workplane('XY').circle(b).extrude(depth + 20).translate((0, 0, H - depth)))
    # Starts 2 mm inside the slot: a dip face tangent to the slot wall makes the union degenerate.
    dip = cq.Workplane('YZ').circle(dip_r).extrude(60).translate((b - 2, 0, H + dip_r - dip_depth))
    return union_all(at(pocket.union(dip), d) for d in stations())


def tip_pads():
    r, h, _, _ = P['tip_pad']
    pad = cq.Workplane('XY').circle(r).extrude(h).edges('>Z').fillet(2.5).edges('<Z').chamfer(P['bottom_chamfer'])
    return union_all(at(pad.translate((F['axis_r'], 0, 0)), d) for d in stations())


def tip_dimples():
    _, h, sr, depth = P['tip_pad']
    # Pole turned sideways: a sphere pole at the dimple bottom tessellates into a non-manifold point.
    ball = cq.Workplane('XY').sphere(sr).rotate((0, 0, 0), (1, 0, 0), 90)
    return union_all(at(ball.translate((F['axis_r'], 0, h + sr - depth)), d) for d in stations())


# ------------------------------------------------------------------------------------------- assembly
def checked(cutter):
    """Boolean tools must be valid positive-volume solids; a degenerate union silently loses features."""
    for s in cutter.solids().vals():
        assert s.isValid() and s.Volume() > 0, 'degenerate cutter solid'
    return cutter


def build():
    check_parameters()
    H = P['hook_z']
    # Hub where the fins meet: gives their rounded top ends one clean junction instead of a point.
    hub = cq.Workplane('XY').circle(P['hub_radius']).extrude(H - 5).faces('>Z').edges().fillet(2.5)
    body = hub.union(union_all(fin(d) for d in stations()))

    b0, b1 = P['band_r']
    z0, z1 = P['band_z']
    band = tier(b0, b1, z0, z1, P['tier_top_radius']).cut(vaults(b0, P['band_vault_spring'], z1 - P['band_vault_crown']))
    c0, c1 = P['crown_r']
    cz0 = H - P['crown_height']
    crown = tier(c0, c1, cz0, H, P['tier_top_radius']).cut(vaults(c0, cz0, H - P['crown_vault_crown']))
    # Dial cap: closes the crown centre 4 mm below the rim. Its conical underside rises at 50 degrees
    # (not 45) because the nose slots cut it into skewed facets that would otherwise tessellate past 45.
    top, hr = H - P['cap_recess'], P['hub_radius'] - 0.5
    drop = (c0 + 0.5 - hr) * math.tan(math.radians(50))
    cap = (cq.Workplane('XZ').polyline([(0, top), (c0 + 0.5, top), (c0 + 0.5, top - 2),
                                        (hr, top - 2 - drop), (0, top - 2 - drop)])
           .close().revolve(360, (0, 0, 0), (0, 1, 0)))
    crown = crown.union(cap)

    r0, r1 = P['ring_r']
    ring = (cq.Workplane('XY').circle(r1).circle(r0).extrude(P['ring_height'])
            .faces('>Z').edges().fillet(P['ring_top_radius']).faces('<Z').edges().chamfer(P['bottom_chamfer']))

    body = body.union(band).union(crown).union(ring).union(tip_pads())
    body = body.cut(checked(union_all(pipette_envelope(d, F['clearance']) for d in stations())))
    body = body.cut(checked(cradles())).cut(checked(hook_cuts())).cut(checked(tip_dimples()))
    return body


def proxies():
    """Stand-in pipettes for renders and clearance checks only (never exported as the product)."""
    return union_all(pipette_envelope(d) for d in stations())


if __name__ == '__main__':
    s = build().val()
    bb = s.BoundingBox()
    print(f'valid={s.isValid()} volume={s.Volume() / 1000:.2f} cm3 bbox={bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f}')
