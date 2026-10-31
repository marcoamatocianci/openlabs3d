"""Pipette holder concept studies (CadQuery). Run from this folder:

    /home/mcianci/mcp/cadquery-contrib/mcp-server/.venv/bin/python concepts.py

Writes concept_{a,b,c}.stl and pipette_proxy.stl (studies, not print files: they are not all watertight).
concept_b here is the unrefined tiered fin study; its refined form is concept_b_fin_tiers_model.py, and the
chosen design is ../source/model.py. All share the functional datums measured on the
reference (exaple_product/mechanical-pipette-holder.stl): three hanging positions at 120 degrees, finger hook
resting on a crest near r=22 mm, handle back leaning on a concave saddle near r=43 mm / z=150-165, pipette
axis near r=58 mm with its lower end over the base. Units: millimetres, Z up, base on the bed.
"""
import math
from pathlib import Path
import cadquery as cq

D = dict(
    n=3,              # pipette positions
    first_deg=90.0,   # angle of the first position
    hook_z=212.0,     # crest top: underside of the finger hook
    crest_r=24.0,     # crest centre radius
    nose_r=(11.0, 19.0),  # radial span of the hook-nose pocket
    axis_r=58.0,      # pipette axis radius
    body_r=15.5,      # assumed handle radius at the saddle
    clearance=0.6,    # radial clearance added to the pipette envelope
    saddle_z=(146.0, 166.0),
)
HERE = Path(__file__).resolve().parent


def stations():
    return [D['first_deg'] + i * 360.0 / D['n'] for i in range(D['n'])]


def at(shape, deg):
    return shape.rotate((0, 0, 0), (0, 0, 1), deg)


def revolve(points):
    """Closed (r, z) outline revolved about Z."""
    return cq.Workplane('XZ').polyline(points).close().revolve(360, (0, 0, 0), (0, 1, 0))


def spline_profile(outer, top_z):
    """Solid of revolution: flat base, spline flank through `outer` (r, z) points, flat top."""
    wp = cq.Workplane('XZ').moveTo(0, 0).lineTo(outer[0][0], 0).lineTo(*outer[0])
    wp = wp.spline(outer[1:], includeCurrent=True).lineTo(0, top_z).close()
    return wp.revolve(360, (0, 0, 0), (0, 1, 0))


def pipette_proxy(deg, grow=0.0):
    """Illustrative single-channel pipette (NOT a measured brand): hook-hung, axis vertical."""
    H, R = D['hook_z'], D['body_r'] + grow
    pts = [(0, H - 205), (2.5 + grow, H - 205), (7 + grow, H - 180), (7 + grow, H - 125), (R, H - 92),
           (R, H + 25), (8 + grow, H + 25), (8 + grow, H + 45), (0, H + 45)]
    body = revolve(pts).translate((D['axis_r'], 0, 0))
    back = D['axis_r'] - D['body_r'] + 1
    arm = cq.Workplane('XY').box(back - D['nose_r'][0] + 2, 16 + 2 * grow, 6 + grow, centered=(False, True, False)) \
        .translate((D['nose_r'][0] - 1, 0, H))
    nose = cq.Workplane('XY').box(5 + 2 * grow, 16 + 2 * grow, 10, centered=(False, True, False)) \
        .translate((D['nose_r'][0] + 1 - grow, 0, H - 9))
    return at(body.union(arm).union(nose), deg)


def envelopes(grow):
    out = None
    for deg in stations():
        p = pipette_proxy(deg, grow)
        out = p if out is None else out.union(p)
    return out


def pipette_cylinders(z0, z1):
    """Handle envelope plus clearance, as cutters that form the concave saddles."""
    out = None
    for deg in stations():
        c = cq.Workplane('XY').circle(D['body_r'] + D['clearance']).extrude(z1 - z0) \
            .translate((D['axis_r'], 0, z0))
        c = at(c, deg)
        out = c if out is None else out.union(c)
    return out


def hook_cuts(depth=12.0, dip=40.0):
    """Nose pocket inboard of the crest, plus a shallow transverse dip that self-centres the hook."""
    out = None
    H = D['hook_z']
    for deg in stations():
        a, b = D['nose_r']
        pocket = cq.Workplane('XY').box(b - a, 20, depth + 20, centered=(False, True, False)) \
            .edges('|Z').fillet(3.5).translate((a, 0, H - depth))
        saddle = cq.Workplane('YZ').circle(dip).extrude(60).translate((D['nose_r'][1], 0, H + dip - 2.2))
        cut = at(pocket.union(saddle), deg)
        out = cut if out is None else out.union(cut)
    return out


def safe_fillet(wp, selector, r):
    try:
        return wp.edges(selector).fillet(r)
    except Exception as exc:
        print(f'  fillet skipped ({selector}, r={r}): {type(exc).__name__}')
        return wp


# ---------------------------------------------------------------- Concept A: Minimal Precision
def concept_a():
    """Slim column, two 45-degree collars (saddle disc and hook crown) on a tri-lobe plinth."""
    from shapely.geometry import Point
    from shapely.ops import unary_union
    lobes = [Point(D['axis_r'] * math.cos(math.radians(d)), D['axis_r'] * math.sin(math.radians(d))).buffer(19)
             for d in stations()]
    plinth = unary_union([Point(0, 0).buffer(34)] + lobes).convex_hull.buffer(-6).buffer(6)
    xy = list(plinth.exterior.coords)[:-1]
    base = cq.Workplane('XY').polyline(xy).close().extrude(7)
    base = safe_fillet(base, '>Z', 3)
    column = revolve([(0, 5), (13, 5), (16, 9), (12.5, 30), (12.5, 200), (0, 200)])
    collar = revolve([(0, 118), (13, 118), (47, 152), (47, 162), (44, 165), (13, 170), (0, 170)])
    crown = revolve([(0, 186), (12.5, 186), (31, 204.5), (31, D['hook_z'] - 3), (28, D['hook_z']),
                     (0, D['hook_z'])])
    body = base.union(column).union(collar).union(crown)
    body = body.cut(pipette_cylinders(120, 175)).cut(hook_cuts())
    for deg in stations():  # tip landing dimple
        body = body.cut(at(cq.Workplane('XY').sphere(9).translate((D['axis_r'], 0, 7 + 6.5)), deg))
    return body


# ---------------------------------------------------------------- Concept B: Architectural Framework
def blade(deg):
    t = 6.0
    outer = [(86, 3), (70, 6.5), (42, 18), (21, 46), (14, 82), (14, 118), (21, 146), (34, 172), (37, 194),
             (31, 218)]
    wp = cq.Workplane('XZ').moveTo(0, 0).lineTo(86, 0).lineTo(*outer[0]).spline(outer[1:], includeCurrent=True) \
        .lineTo(0, 218).close().extrude(t / 2, both=True)
    # pointed-arch window, Bridge collection vocabulary
    win = (cq.Workplane('XZ').moveTo(8, 150).lineTo(8, 186).threePointArc((14.5, 197), (21, 186))
           .lineTo(21, 160).close().extrude(t, both=True))
    wp = wp.cut(win)
    return at(wp, deg)


def concept_b1():
    """Rejected first framework: blades between the positions, tied by rings (crest ring floated free)."""
    body = None
    for deg in stations():
        b = blade(deg + 180.0 / D['n'])
        body = b if body is None else body.union(b)
    ring = lambda r0, r1, z0, z1: cq.Workplane('XY').circle(r1).circle(r0).extrude(z1 - z0).translate((0, 0, z0))
    saddle = ring(38, 47, *D['saddle_z'])
    saddle = safe_fillet(saddle, '%CIRCLE', 2.5)
    crest = revolve([(D['nose_r'][1] + 1, D['hook_z'] - 9), (D['crest_r'] + 7, D['hook_z'] - 9),
                     (D['crest_r'] + 7, D['hook_z'] - 4), (D['crest_r'] + 3, D['hook_z']),
                     (D['nose_r'][1] + 4, D['hook_z']), (D['nose_r'][1] + 1, D['hook_z'] - 3)])
    tip = ring(50, 66, 0, 5)
    tip = safe_fillet(tip, '>Z', 2)
    body = body.union(saddle).union(crest).union(tip)
    body = body.cut(pipette_cylinders(120, 180)).cut(hook_cuts())
    for deg in stations():
        pad = cq.Workplane('XY').circle(14).extrude(6).translate((D['axis_r'], 0, 0))
        body = body.union(at(pad, deg))
        body = body.cut(at(cq.Workplane('XY').sphere(9).translate((D['axis_r'], 0, 6 + 6.5)), deg))
    return body


def diamond(half_w, z0, z1, web=3.5, r0=0.0, r1=100.0):
    """Prism along the radial (X) axis whose (t, z) outline widens from the web at 45 degrees, so any
    flange that is intersected with it prints without support."""
    rise = half_w - web
    pts = [(-web, z0), (web, z0), (half_w, z0 + rise), (half_w, z1), (-half_w, z1), (-half_w, z0 + rise)]
    return cq.Workplane('YZ').polyline(pts).close().extrude(r1 - r0).translate((r0, 0, 0))


def fin_b(deg, t=7.0):
    H = D['hook_z']
    outer = [(78, 4.5), (64, 5.0), (50, 6.5), (38, 13), (28, 27), (22, 48), (20, 78), (20, 112), (24, 128),
             (33, 142), (39.5, 154), (39, 166), (33, 180), (29, 194), (29.5, H - 8)]
    wp = cq.Workplane('XZ').moveTo(0, 0).lineTo(78, 0).lineTo(*outer[0]) \
        .spline(outer[1:], includeCurrent=True).lineTo(26, H - 4).lineTo(0, H - 4).close()
    fin = wp.extrude(t / 2, both=True)
    fin = safe_fillet(fin, 'not(<Z)', 2.4)
    lancet = lambda r0, r1, z0, z1: (cq.Workplane('XZ').moveTo(r0, z0).lineTo(r1, z0).lineTo(r1, z1)
                                     .threePointArc(((r0 + r1) / 2, z1 + (r1 - r0) * 0.9), (r0, z1)).close()
                                     .extrude(t, both=True))
    fin = fin.cut(lancet(9, 24, 140, 180)).cut(lancet(7.5, 13.5, 44, 114))
    return at(fin, deg)


def cradle(deg, R=22.0, wall=5.0, half_w=14.0):
    """Curved shell behind the handle: concave face R wraps the grip, contact line at the handle back."""
    contact = D['axis_r'] - D['body_r']
    z0, z1 = D['saddle_z']
    c = contact + R
    shell = cq.Workplane('XY').circle(R + wall).circle(R).extrude(z1 - z0 + 14).translate((c, 0, z0 - 14))
    shell = shell.intersect(diamond(half_w, z0 - 14, z1, r0=c - R - wall - 1, r1=c))
    shell = safe_fillet(shell, '|Z', 1.6)
    return at(shell, deg)


def crest(deg, half_w=12.0):
    H = D['hook_z']
    a, b = D['nose_r'][1], D['crest_r'] + 7
    prof = (cq.Workplane('XZ').moveTo(a, H - 22).lineTo(b, H - 22).lineTo(b, H - 4)
            .threePointArc((b - 1.2, H - 1.2), (b - 4, H)).lineTo(a + 3, H)
            .threePointArc((a + 0.9, H - 0.9), (a, H - 3)).close().extrude(half_w, both=True))
    return at(prof.intersect(diamond(half_w, H - 22, H + 1)), deg)


def concept_b2():
    """Second framework: fins in line with the pipettes, separate cradle shells and crest blocks."""
    body = None
    for deg in stations():
        part = fin_b(deg).union(cradle(deg)).union(crest(deg))
        body = part if body is None else body.union(part)
    ring = cq.Workplane('XY').circle(79).circle(70).extrude(5)
    ring = safe_fillet(ring, '>Z', 2.4)
    body = body.union(ring)
    for deg in stations():
        pad = cq.Workplane('XY').circle(12).extrude(6.5).translate((D['axis_r'], 0, 0))
        body = body.union(at(safe_fillet(pad, '>Z', 2.5), deg))
        body = body.cut(at(cq.Workplane('XY').sphere(10).translate((D['axis_r'], 0, 6.5 + 8)), deg))
    return body.cut(hook_cuts())


def vault_cutters(r_from, r_to, w, z_low, z_spring, z_apex):
    """Pointed vaults between neighbouring fins. Each half-arch is a circle through the springing point
    whose tangent at the apex is exactly 45 degrees, so every underside face prints without support."""
    d = z_apex - z_spring
    assert d > w, 'vault too flat for 45 degree printing'
    c = (w * w + d * d) / (2 * (d - w))
    rho = c * math.sqrt(2)
    zc = z_apex - c
    def mid(sign):  # point on the arc halfway (by angle) between springing and apex
        a0 = math.atan2(z_spring - zc, sign * w - (-sign * c))
        a1 = math.atan2(z_apex - zc, 0 - (-sign * c))
        a = (a0 + a1) / 2
        return (-sign * c + rho * math.cos(a), zc + rho * math.sin(a))
    prof = (cq.Workplane('YZ').moveTo(-w, z_low).lineTo(w, z_low).lineTo(w, z_spring)
            .threePointArc(mid(1), (0, z_apex)).threePointArc(mid(-1), (-w, z_spring)).close()
            .extrude(r_to - r_from).translate((r_from, 0, 0)))
    out = None
    for deg in stations():
        v = at(prof, deg + 180.0 / D['n'])
        out = v if out is None else out.union(v)
    return out


def tier(r_in, r_out, z0, z1, round_top=2.5):
    t = cq.Workplane('XY').circle(r_out).circle(r_in).extrude(z1 - z0).translate((0, 0, z0))
    return safe_fillet(t, '>Z', round_top)


def fin(deg, t=7.5):
    H = D['hook_z']
    outer = [(78, 5.5), (64, 6.2), (50, 8.5), (38, 15.5), (28, 29), (22.5, 50), (20.5, 80), (21, 100),
             (28, 114), (40, 127), (44, 136)]
    wp = (cq.Workplane('XZ').moveTo(0, 0).lineTo(78, 0).lineTo(*outer[0])
          .spline(outer[1:], includeCurrent=True).lineTo(44, 168)
          .spline([(38, 176), (31, 186), (29, H - 20)], includeCurrent=True)
          .lineTo(29, H - 5).lineTo(0, H - 5).close())
    f = wp.extrude(t / 2, both=True)
    return at(safe_fillet(f, 'not(<Z)', 3.0), deg)


def concept_b():
    """Three fins in line with the pipettes, a Y-section mast, two vaulted tiers (saddle band and
    hook crown) and an orbit ring at the bed for a circular tipping footprint."""
    H = D['hook_z']
    body = None
    for deg in stations():
        body = fin(deg) if body is None else body.union(fin(deg))
    band = tier(39, 46.5, 126, 168, 3.0).cut(vault_cutters(22, 60, 29, 114, 126, 156))
    crown = tier(19, 31, H - 20, H, 3.0).cut(vault_cutters(12, 40, 12, H - 32, H - 20, H - 7))
    ring = tier(70, 79, 0, 5.5, 2.5)
    body = body.union(band).union(crown).union(ring)
    for deg in stations():
        pad = cq.Workplane('XY').circle(12).extrude(7).translate((D['axis_r'], 0, 0))
        body = body.union(at(safe_fillet(pad, '>Z', 2.5), deg))
    body = body.cut(envelopes(D['clearance'])).cut(pipette_cylinders(118, 175)).cut(hook_cuts())
    for deg in stations():
        body = body.cut(at(cq.Workplane('XY').sphere(10).translate((D['axis_r'], 0, 7 + 7.6)), deg))
    return body


# ---------------------------------------------------------------- Concept C: Contemporary Industrial
def concept_c():
    """One sculpted vase-like spine whose flutes are the pipette envelopes: saddles and tip seats emerge
    from subtracting the pipettes themselves."""
    H = D['hook_z']
    outer = [(80, 2.5), (62, 6.5), (40, 15), (25, 34), (18, 66), (17, 100), (22, 128), (38, 150), (48, 162),
             (45, 172), (32, 184), (25, 194), (27, 204), (31, H - 3), (29, H)]
    body = spline_profile(outer, H)
    body = body.cut(envelopes(D['clearance'])).cut(pipette_cylinders(130, 180)).cut(hook_cuts())
    return body


def export(wp, name):
    path = HERE / f'{name}.stl'
    cq.exporters.export(wp, str(path), tolerance=0.05, angularTolerance=0.15)
    s = wp.val()
    bb = s.BoundingBox()
    print(f'{name}: valid={s.isValid()} solids={len(wp.solids().vals())} vol={s.Volume() / 1000:.1f} cm3 '
          f'bbox={bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f}')


if __name__ == '__main__':
    import sys
    which = sys.argv[1:] or ['proxy', 'a', 'b', 'c']
    if 'proxy' in which:
        export(envelopes(0), 'pipette_proxy')
    for k in ['a', 'b', 'b1', 'b2', 'c']:
        if k in which:
            export(globals()[f'concept_{k}'](), f'concept_{k}')
