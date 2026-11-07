"""The two design families, as plans the CAD generator, the browser preview and the material estimate all share.

Lightweight is an open structure: funnels that follow each tube's cone, windows, collars and short bridges. Premium is a
drafted body on a recessed plinth. Both print upright without support by construction: walls narrow upward or lean less
than the printable limit, window roofs are steeper than it, and spans between collars stay under the bridging limit.
"""
import math
from dataclasses import dataclass, field
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from .rules import RULES

OUTER_SEGMENTS = 8      # per quarter circle, for corners
ARC_ERROR_MM = .05      # the largest distance a faceted outer surface may stray from the true arc
PREVIEW_SEGMENTS = 6

@dataclass
class Tube:
    profile_id: str
    x: float
    y: float
    bore_d: float
    cap_d: float
    deck: float
    floor: float
    cone: float
    tip_d: float
    length: float
    @property
    def radius(self): return self.bore_d / 2

@dataclass
class Structure:
    style: str
    rect: tuple
    tubes: list
    filled: list                     # [(z0, z1, polygon without bores)] bottom to top
    terraces: list = field(default_factory=list)   # Premium: [{'rect', 'z'}], lowest first
    corner_r: float = 0.0
    top_fillet: float = 0.0
    bottom_chamfer: float = 0.0
    plate: dict | None = None
    funnels: list = field(default_factory=list)    # Lightweight: [{'shape', 'at'}]
    links: list = field(default_factory=list)      # Lightweight: bridges and walls between tubes
    base: object = None                            # Lightweight: the plan of the base band
    walls: list = field(default_factory=list)      # Lightweight: the sleeve wall of each tube
    holes: dict = field(default_factory=dict)      # bores already united, by which are open and how finely they are drawn
    label: dict | None = None

def arc_segments(r):
    """Segments per quarter circle that keep a radius within ARC_ERROR_MM: larger sleeves need more to look round."""
    return max(4, math.ceil(math.pi / 4 / math.acos(max(0.0, 1 - ARC_ERROR_MM / max(r, ARC_ERROR_MM)))))

def disc(x, y, r, segments=None): return Point(x, y).buffer(r, quad_segs=segments or arc_segments(r))

def rounded_rect(x0, y0, x1, y1, r):
    r = min(r, (x1 - x0) / 2 - .01, (y1 - y0) / 2 - .01)
    if r <= .01: return box(x0, y0, x1, y1)
    return box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, quad_segs=OUTER_SEGMENTS)

def bar(ax, ay, bx, by, width): return LineString([(ax, ay), (bx, by)]).buffer(width / 2, cap_style='flat')

def gabriel_edges(points):
    """Pairs with no third point inside the circle on their diameter: planar, connected, and close to what a
    designer would draw between neighbours. Cubic, so kept to arrays: MAX_TUBES tubes take about 10 ms."""
    p = np.asarray(points, dtype=float)
    i, j = np.triu_indices(len(p), 1)
    middles = (p[i] + p[j]) / 2
    radii = ((p[i] - p[j]) ** 2).sum(axis=1) / 4
    distances = ((p[None, :, :] - middles[:, None, :]) ** 2).sum(axis=2)
    pairs = np.arange(len(i))
    distances[pairs, i] = np.inf; distances[pairs, j] = np.inf
    # Strictly outside: in a square grid the four corners share a circle, and accepting that tie put two crossing diagonal
    # webs in every pocket, with windows cut through each other, which a slicer then wanted to support.
    keep = (distances > radii[:, None] + 1e-6).all(axis=1)
    return [(int(a), int(b)) for a, b in zip(i[keep], j[keep])]

def _closing(geometry, r): return geometry.buffer(r, quad_segs=4).buffer(-r, quad_segs=4)

def _fill_small_holes(geometry, area):
    """Openings too small to save material or to clean through are only print time and stringing."""
    kept = []
    for poly in polygons(geometry):
        if poly.area < 1.0: continue          # numerical dust left by the 2D booleans, not material
        kept.append(Polygon(poly.exterior, [r for r in poly.interiors if Polygon(r).area >= area]))
    return unary_union(kept)

def _stack_downward(levels, plan_at):
    """Bands bottom to top from plan_at(top height), each grown to contain every band above it."""
    spans = list(zip(levels, levels[1:]))
    result, above = [], None
    for z0, z1 in reversed(spans):
        plan = plan_at(z0, z1)
        if above is not None: plan = plan.union(above)
        result.append((z0, z1, plan)); above = plan
    return list(reversed(result))

def tube_wall(t): return RULES.fine_wall_mm if t.bore_d < 14 else RULES.sleeve_wall_mm

def drain_d(t): return round(min(3.0, max(RULES.min_hole_mm, t.tip_d - 1.0)), 2)

@dataclass
class Funnel:
    """One tube's seat in a Lightweight rack: a thin funnel that follows the tube's own cone (steeper than the printable
    limit for every tube in the library), then a sleeve opened by windows, closed at the top by a collar. Every tube of one
    shape shares one Funnel, so the CAD builds each shape once."""
    bore: float
    tip: float
    floor: float
    cone_top: float
    deck: float
    wall: float
    drain: float
    belts: tuple = ()                # heights where a shorter neighbour's bridge lands, kept closed
    windows: tuple = ()              # {'angle', 'width', 'z0', 'shoulder', 'apex'}
    def inner(self, z):
        if z >= self.cone_top: return self.bore
        return self.tip + (self.bore - self.tip) * max(0.0, z - self.floor) / (self.cone_top - self.floor)
    def outer(self, z): return self.inner(z) + self.wall
    def spec(self):
        return {'bore': self.bore, 'tip': self.tip, 'floor': self.floor, 'cone_top': self.cone_top, 'deck': self.deck, 'wall': self.wall, 'windows': list(self.windows)}

def _half_width(w, z):
    """Half the width of a window at this height: round below, straight, pointed above."""
    half = w['width'] / 2
    if z <= w['z0'] or z >= w['apex']: return 0.0
    if z < w['z0'] + half: return math.sqrt(max(0.0, half ** 2 - (w['z0'] + half - z) ** 2))
    if z <= w['shoulder']: return half
    return half * (w['apex'] - z) / (w['apex'] - w['shoulder'])

def _funnel_windows(bore, wall, z_low, z_high, belts):
    """Four windows around a sleeve, on the diagonals: bridges and ribs run along the rows, so nothing lands on an opening.
    Between belts, each span of sleeve gets its own tier, and a span too short to carry a window stays closed."""
    mid = bore + wall / 2
    arc = 2 * math.pi * mid / 4
    # Slim, so what is left reads as a sleeve on four solid pillars, and not as a cage.
    width = round(min(arc - RULES.pillar_mm, arc * .5), 2)
    roof = math.tan(math.radians(RULES.window_roof_deg))
    result, spans, low = [], [], z_low
    for belt in sorted(belts):
        spans.append((low, belt - RULES.collar_mm - 1)); low = belt + 1
    spans.append((low, z_high))
    for start, stop in spans:
        shoulder = stop - width / 2 * roof
        if shoulder - start < width / 2 + 2: continue
        for k in range(4):
            result.append({'angle': round(math.pi / 4 + k * math.pi / 2, 6), 'width': width, 'z0': round(start, 2), 'shoulder': round(shoulder, 2), 'apex': round(stop, 2)})
    return tuple(result)

def _funnels(tubes):
    decks = sorted({t.deck for t in tubes})
    found = {}
    for t in tubes:
        cone = min(t.cone, t.deck - t.floor - 3)
        wall = tube_wall(t)
        cone_top = round(t.floor + cone, 2)
        belts = tuple(d for d in decks if cone_top + 4 < d < t.deck - 6)
        drain = drain_d(t)
        key = (t.bore_d, t.tip_d, t.floor, cone_top, t.deck, belts)
        if key not in found:
            windows = _funnel_windows(t.radius, wall, cone_top + 1.5, t.deck - RULES.collar_mm, belts)
            found[key] = Funnel(t.radius, round(max(t.tip_d / 2 + .3, drain / 2 + .3), 3), t.floor, cone_top, t.deck, wall, drain / 2, belts, windows)
    return found, lambda t: next(f for k, f in found.items() if k[:3] == (t.bore_d, t.tip_d, t.floor) and k[4] == t.deck)

def _funnel_section(funnel, z):
    """The funnel's plan at a height, at the origin."""
    ring = Point(0, 0).buffer(funnel.outer(z), quad_segs=5).difference(Point(0, 0).buffer(funnel.inner(z), quad_segs=5))
    for w in funnel.windows:
        half = _half_width(w, z)
        if half <= 0: continue
        c, s = math.cos(w['angle']), math.sin(w['angle'])
        r0, r1 = funnel.bore * .3, funnel.bore + funnel.wall + 1
        ring = ring.difference(Polygon([(r0 * c + half * s, r0 * s - half * c), (r1 * c + half * s, r1 * s - half * c), (r1 * c - half * s, r1 * s + half * c), (r0 * c - half * s, r0 * s + half * c)]))
    return ring

def lightweight(tubes, rect, label_plate=None):
    """An open structure with one continuous load path: bed, base frame and ribs, a hub under each tube, its funnel and
    sleeve, its collar, and short bridges from collar to collar. Material goes only where a tube needs it, which is why this
    also works for microtubes: a funnel leaves room between neighbours at the base, where a straight sleeve would not."""
    x0, y0, x1, y1 = rect
    rib, base_h = RULES.rib_mm, RULES.base_mm
    edges = gabriel_edges([(t.x, t.y) for t in tubes]) if len(tubes) > 1 else []
    funnels, funnel_of = _funnels(tubes)
    frame = rounded_rect(x0, y0, x1, y1, 7).difference(rounded_rect(x0 + RULES.frame_mm, y0 + RULES.frame_mm, x1 - RULES.frame_mm, y1 - RULES.frame_mm, 3))
    pieces = [frame]
    for t in tubes:
        f = funnel_of(t)
        pieces.append(disc(t.x, t.y, f.tip + f.wall + 1.0))
    for i, j in edges:
        a, b = tubes[i], tubes[j]
        pieces.append(bar(a.x, a.y, b.x, b.y, rib if max(a.bore_d, b.bore_d) >= 14 else rib - .8))
    inner = (x0 + RULES.frame_mm / 2, y0 + RULES.frame_mm / 2, x1 - RULES.frame_mm / 2, y1 - RULES.frame_mm / 2)
    for t in tubes:
        wall = tube_wall(t)
        sides = [(inner[0], t.y), (inner[2], t.y), (t.x, inner[1]), (t.x, inner[3])]
        near = [s for s in sides if len(tubes) == 1 or math.hypot(s[0] - t.x, s[1] - t.y) <= t.radius + wall + 18]
        for s in near: pieces.append(bar(t.x, t.y, s[0], s[1], rib - .8 if t.bore_d < 14 else rib))
    if label_plate: pieces.append(box(*label_plate['foot']))
    # Rounding the inside corners is the transition between rib and hub: it costs little and it is where a rib would crack.
    base = _fill_small_holes(_closing(unary_union(pieces), 2.0), 25.0)
    base = base.difference(unary_union([disc(t.x, t.y, funnel_of(t).drain) for t in tubes]))
    # Links between tubes above the base: a bridge where collars nearly touch, a wall with a window where they do not.
    links = []
    for i, j in edges:
        a, b = tubes[i], tubes[j]
        top = min(a.deck, b.deck)
        distance = math.hypot(a.x - b.x, a.y - b.y)
        fa, fb = funnel_of(a), funnel_of(b)
        gap = distance - fa.outer(top) - fb.outer(top)
        if gap < .4: continue       # the collars already touch (a tight layout made by hand)
        if gap <= RULES.max_bridge_mm:
            links.append(_bridge(a, b, fa, fb, distance, gap, top))
        elif gap <= 30:
            ux, uy = (b.x - a.x) / distance, (b.y - a.y) / distance
            sa, sb = fa.outer(top) - .4, distance - fb.outer(top) + .4
            wall = bar(a.x + ux * sa, a.y + uy * sa, a.x + ux * sb, a.y + uy * sb, RULES.web_mm)
            links.append({'z0': base_h - .2, 'z1': top, 'shape': wall, 'window': _web_window(a, b, fa, fb, distance, gap, top)})
    funnel_data = [{'shape': f.spec(), 'at': [[t.x, t.y] for t in tubes if funnel_of(t) is f], 'bands': _funnel_bands(f)} for f in funnels.values()]
    filled = _lightweight_sections(tubes, funnels, funnel_of, links, base, label_plate)
    return Structure('lightweight', rect, tubes, filled, plate=label_plate, funnels=funnel_data, links=links, base=base, walls=[tube_wall(t) for t in tubes])

ARCH_DEG = 60.0     # a bridge's underside, from horizontal: clear of the angle at which slicers start to add support

def _bridge(a, b, fa, fb, distance, gap, top):
    """A short plate from collar to collar, its underside a shallow arch at the printable limit: it needs no bridging at
    all, and its ends spread into each sleeve instead of meeting it at a corner."""
    under = top - RULES.collar_mm
    middle = (fa.outer(top) + distance - fb.outer(top)) / 2
    # The foot lands on a funnel that recedes as it goes down, so each arm's slope is found by following it there.
    slope = math.tan(math.radians(ARCH_DEG))
    foot = lambda f, low: max(f.outer(low) - .25, f.inner(low) + .15)
    low = under - 1.0
    for _ in range(6):
        reach = max(middle - foot(fa, low), distance - foot(fb, low) - middle)
        low = under - reach * slope
    low = max(low, RULES.base_mm + 1.0)
    # Each end stays in that sleeve's wall at every height it reaches, never in the bore: its top starts just outside the
    # bore, and its foot just inside the outer surface.
    a_top, b_top = fa.inner(top) + .15, distance - fb.inner(top) - .15
    a_low, b_low = foot(fa, low), distance - foot(fb, low)
    return {'kind': 'bridge', 'x': a.x, 'y': a.y, 'angle': round(math.atan2(b.y - a.y, b.x - a.x), 6), 'thick': RULES.bridge_mm,
            'profile': [(round(a_top, 3), top), (round(b_top, 3), top), (round(b_low, 3), round(low, 3)), (round(middle, 3), round(under, 3)), (round(a_low, 3), round(low, 3))],
            'z0': round(low, 3), 'z1': top, 'window': None,
            # The part of the plate inside the two sleeve walls, already counted with the funnels.
            'embedded': round((fa.wall + fb.wall - .3) * RULES.bridge_mm * (RULES.collar_mm + (under - low) / 2), 1)}

def _web_window(a, b, fa, fb, distance, gap, top):
    """A pointed opening in a long wall, centred between the two sleeves. Its legs stand on the base rib."""
    width = min(gap - 6, 26.0)
    z0, apex = RULES.base_mm + 2.5, top - RULES.collar_mm - 1
    shoulder = apex - width / 2 * math.tan(math.radians(RULES.window_roof_deg))
    if width < 6 or shoulder - z0 < width / 2 + 2: return None
    along = (fa.outer(top) + gap / 2) / distance
    return {'x': round(a.x + (b.x - a.x) * along, 3), 'y': round(a.y + (b.y - a.y) * along, 3), 'angle': round(math.atan2(b.y - a.y, b.x - a.x) + math.pi / 2, 6), 'width': round(width, 2), 'z0': round(z0, 2), 'shoulder': round(shoulder, 2), 'apex': round(apex, 2)}

def _funnel_bands(f):
    """One funnel shape sliced into bands, once per shape: the browser instances it and the estimate multiplies it."""
    levels = {f.floor, f.deck, f.cone_top, round(f.deck - RULES.collar_mm, 2)}
    for k in (1, 2): levels.add(round(f.floor + (f.cone_top - f.floor) * k / 3, 2))
    for w in f.windows: levels.update((w['z0'], round(w['z0'] + w['width'] * .25, 2), round(w['z0'] + w['width'] / 2, 2), w['shoulder'], round((w['shoulder'] + w['apex']) / 2, 2), w['apex']))
    spans = []
    for z in sorted(levels):
        if not spans or z - spans[-1] >= .4: spans.append(z)
    spans[-1] = f.deck
    return [(z0, z1, _funnel_section(f, (z0 + z1) / 2)) for z0, z1 in zip(spans, spans[1:])]

def _lightweight_sections(tubes, funnels, funnel_of, links, base, plate):
    """What the funnels do not cover, as separate small prisms: nothing here is shared, so nothing needs a union."""
    filled = [(0.0, RULES.base_mm, base.union(_plate_slice(plate, RULES.base_mm / 2)) if plate else base)]
    for link in links:
        if link.get('kind') == 'bridge':
            under = link['profile'][3][1]
            filled.append((under, link['z1'], _link_section(link, (under + link['z1']) / 2)))
            filled.append((link['z0'], under, _link_section(link, (under + link['z0']) / 2)))
        else:
            w = link['window']
            if not w: filled.append((link['z0'], link['z1'], link['shape'])); continue
            for z0, z1 in ((link['z0'], w['z0']), (w['z0'], w['shoulder']), (w['shoulder'], w['apex']), (w['apex'], link['z1'])):
                if z1 > z0: filled.append((z0, z1, _link_section(link, (z0 + z1) / 2)))
    if plate:
        steps = 5
        for k in range(steps):
            z0, z1 = RULES.base_mm + (plate['height'] - RULES.base_mm) * k / steps, RULES.base_mm + (plate['height'] - RULES.base_mm) * (k + 1) / steps
            filled.append((z0, z1, _plate_slice(plate, (z0 + z1) / 2)))
    return filled

def _link_section(link, z):
    if link.get('kind') == 'bridge':
        cut = Polygon(link['profile']).intersection(LineString([(-1e4, z), (1e4, z)]))
        if cut.is_empty: return Polygon()
        c, s = math.cos(link['angle']), math.sin(link['angle'])
        pieces = []
        for line in (cut.geoms if hasattr(cut, 'geoms') else [cut]):
            xs = [p[0] for p in line.coords]
            if max(xs) - min(xs) < .01: continue
            pieces.append(bar(link['x'] + c * min(xs), link['y'] + s * min(xs), link['x'] + c * max(xs), link['y'] + s * max(xs), link['thick']))
        return unary_union(pieces) if pieces else Polygon()
    w = link['window']
    if not w: return link['shape']
    half = _half_width(w, z)
    if half <= 0: return link['shape']
    c, s = math.cos(w['angle']), math.sin(w['angle'])
    return link['shape'].difference(LineString([(w['x'] - c * 4 + 0, w['y'] - s * 4), (w['x'] + c * 4, w['y'] + s * 4)]).buffer(half, cap_style='flat'))

def _plate_slice(plate, z):
    """The leaning nameplate at a height, in plan."""
    x0, x1, face, depth, sign, along = plate['s0'], plate['s1'], plate['face'], plate['thick'], plate['sign'], plate['along']
    if z > plate['height'] - 3:          # the rounded top corners
        k = 3 - math.sqrt(max(0.0, 9 - (z - plate['height'] + 3) ** 2))
        x0, x1 = x0 + k, x1 - k
    run = plate['run'] * z / plate['height']
    a, b = face - sign * run, face - sign * (run + depth)
    return box(x0, min(a, b), x1, max(a, b)) if along == 'x' else box(min(a, b), x0, max(a, b), x1)

def inset_rect(rect, by): return (rect[0] + by, rect[1] + by, rect[2] - by, rect[3] - by)

def _clamp(value, low, high): return max(low, min(high, value))

def body_profile(height, scale=1.0):
    """The Premium wall as a cross-section: how far it stands in from the rack's outline at each height. Widest about a third
    of the way up, tucking in towards the bed and curving in towards the deck, proportional to the rack, so that a short
    microtube rack and a tall Falcon rack have the same character."""
    return {'height': height, 'belly': round(height * .42, 3), 'tuck': round(_clamp(.045 * height, 1.2, 2.6) * scale, 3),
            'lean': round(_clamp(.05 * height, 1.0, 3.0) * scale, 3), 'round': round(_clamp(.055 * height, 1.4, 3.2) * scale, 3), 'start': 0.0}

def terrace_profile(top, base):
    """A raised level rises out of the deck below it with the same curve, in proportion to its own height."""
    rise = top - base
    return {'height': top, 'belly': base, 'tuck': 0.0, 'lean': round(_clamp(.03 * rise, .4, 1.4), 3), 'round': round(_clamp(.08 * rise, 1.0, 2.2), 3), 'start': base - 1.0}

def inset_at(profile, z):
    """How far the wall stands in at height z. Below the belly a parabola; above it a parabola into a quarter ellipse, whose
    tangent meets the deck: no edge between wall and deck."""
    belly, height = profile['belly'], profile['height']
    if z <= belly: return profile['tuck'] * ((belly - z) / belly) ** 2 if belly > 0 else 0.0
    u = (z - belly) / (height - belly)
    v = max(0.0, (z - (height - profile['round'])) / profile['round'])
    return profile['lean'] * u * u + profile['round'] * (1 - math.sqrt(max(0.0, 1 - v * v)))

def profile_levels(profile):
    """Heights at which the quick preview slices the wall: closer together where it turns fastest, so that the curve reads as a curve."""
    start, belly, height, r = profile['start'], profile['belly'], profile['height'], profile['round']
    levels = [start]
    if profile['tuck'] > 0: levels += [belly * k / 6 for k in range(1, 6)]
    if belly > start: levels.append(belly)
    upper = height - r
    levels += [belly + (upper - belly) * k / 4 for k in range(1, 4)]
    levels += [height - r * (1 - math.sin(math.pi / 2 * k / 6)) for k in range(0, 7)]
    return [round(z, 3) for z in levels]

def top_inset(profile): return profile['lean'] + profile['round']

def corner_rect(rect, radii, by=0.0):
    """A rounded rectangle with its own radius at each corner, in the order front-left, front-right, back-right, back-left."""
    x0, y0, x1, y1 = inset_rect(rect, by)
    points = []
    corners = ((x0, y0, math.pi, radii[0]), (x1, y0, 1.5 * math.pi, radii[1]), (x1, y1, 0.0, radii[2]), (x0, y1, .5 * math.pi, radii[3]))
    for n, (cx, cy, start, radius) in enumerate(corners):
        r = max(.3, radius - by)
        ox, oy = cx + (r if n in (0, 3) else -r), cy + (r if n in (0, 1) else -r)
        steps = arc_segments(r)
        points += [(ox + r * math.cos(start + k * math.pi / 2 / steps), oy + r * math.sin(start + k * math.pi / 2 / steps)) for k in range(steps + 1)]
    return Polygon(points)

def soft_corners(tubes, rect, inset, scale=1.0, wanted=None):
    """A radius for each corner of an outline, as large as keeps the deck around the tube nearest it, so the outline follows
    its tubes: concentric with a tube in the corner, and a capsule end on a single row."""
    x0, y0, x1, y1 = rect
    short = min(x1 - x0, y1 - y0)
    ceiling = min(.49 * short, 26.0)
    radii = []
    for sx, sy, cx, cy in ((1, 1, x0, y0), (-1, 1, x1, y0), (-1, -1, x1, y1), (1, -1, x0, y1)):
        best = ceiling
        for t in tubes:
            dx, dy = (t.x - cx) * sx, (t.y - cy) * sy
            need = t.radius + RULES.min_wall_mm + .5 + inset
            r = ceiling
            while r > 1.0:
                # Inside the corner's square, the tube must keep its wall from the arc; outside it, the straight side rules.
                if dx >= r or dy >= r or r - math.hypot(r - dx, r - dy) >= need: break
                r -= .25
            best = min(best, r)
        radii.append(round(best, 2))
    if wanted is not None: radii = [round(min(wanted, r), 2) for r in radii]
    floor = inset + 1.5      # the wall curves in by this much, so the corner's axis must stand further in than that
    return [round(max(min(r * scale, ceiling), min(floor, .49 * short)), 2) for r in radii]

def premium(tubes, rect, edge_scale=(1.0, 1.0), wanted_corner=None, snap=10.0, margin=0.0):
    """A soft, full body: a lofted convex wall all round, with its own radius at each corner, and a raised level rising from
    the deck for each taller group of tubes, its outline following those tubes. A short tube enclosed by a taller level gets a
    raised well instead, so every tube keeps its own seating depth."""
    x0, y0, x1, y1 = rect
    corner_scale, soft_scale = edge_scale
    def level(z, base):
        group = [t for t in tubes if t.deck >= z]
        reach = RULES.outer_wall_mm + margin + top_inset(terrace_profile(z, base))
        edge = top_inset(body_profile(base)) + 1.0     # a raised level stands on the deck, inside its curve
        tx0 = min(t.x - t.radius - reach for t in group); tx1 = max(t.x + t.radius + reach for t in group)
        ty0 = min(t.y - t.radius - reach for t in group); ty1 = max(t.y + t.radius + reach for t in group)
        return (x0 + edge if tx0 - x0 - edge < snap else tx0, y0 + edge if ty0 - y0 - edge < snap else ty0, x1 - edge if x1 - edge - tx1 < snap else tx1, y1 - edge if y1 - edge - ty1 < snap else ty1)
    # Anything shorter under or beside a raised level, with too little room for its cap, rises to that level.
    base_deck = min(t.deck for t in tubes)
    changed = True
    while changed:
        changed = False
        for z in sorted({t.deck for t in tubes}, reverse=True):
            if z == base_deck: continue
            tx0, ty0, tx1, ty1 = level(z, base_deck)
            for t in tubes:
                if t.deck >= z: continue
                reach = t.cap_d / 2 + 2.0
                if tx0 - reach < t.x < tx1 + reach and ty0 - reach < t.y < ty1 + reach:
                    t.floor += z - t.deck; t.deck = z; changed = True
        base_deck = min(t.deck for t in tubes)
    decks = sorted({t.deck for t in tubes})
    body = body_profile(decks[0], soft_scale)
    # Tubes that all rose to one height leave the body itself at that height.
    corners = soft_corners(tubes, rect, top_inset(body), corner_scale, wanted_corner)
    terraces = [{'rect': list(rect), 'z': decks[0], 'corners': corners, 'profile': body}]
    for z in decks[1:]:
        r = level(z, decks[0])
        profile = terrace_profile(z, decks[0])
        group = [t for t in tubes if t.deck >= z]
        terraces.append({'rect': list(r), 'z': z, 'corners': soft_corners(group, r, top_inset(profile), corner_scale, wanted_corner), 'profile': profile})
    levels = {0.0, *(t.floor for t in tubes)}
    for terrace in terraces: levels.update(profile_levels(terrace['profile']))
    filled = []
    # Heights closer than this add nothing to see, and must not leave a gap between bands: the neighbours close it.
    spans = []
    for z in sorted(levels):
        if not spans or z - spans[-1] >= .05: spans.append(z)
        elif z in {t['z'] for t in terraces}: spans[-1] = z
    for z0, z1 in zip(spans, spans[1:]):
        parts = []
        for terrace in terraces:
            profile = terrace['profile']
            if z1 > terrace['z'] + 1e-6 or z0 < profile['start'] - 1e-6: continue
            # The band's wider end, so a wall is measured where it is thinnest at the top and the outline never falls short.
            at = z1 if z0 >= profile['belly'] else (z0 + z1) / 2
            parts.append(corner_rect(terrace['rect'], terrace['corners'], inset_at(profile, at)))
        filled.append((z0, z1, unary_union(parts)))
    return Structure('premium', rect, tubes, filled, terraces=terraces, corner_r=min(corners), top_fillet=body['round'])

def seat_volume(t):
    """Material a tapered seat leaves inside a cylindrical bore, in mm3 (added back to a bands-only volume)."""
    R, r, h = t.radius, t.tip_d / 2, min(t.cone, t.deck - t.floor - 3)
    return math.pi * R * R * h - math.pi * h * (R * R + R * r + r * r) / 3

def bored(structure, z0, plan, segments=PREVIEW_SEGMENTS):
    """A band's plan with the bores open at this height."""
    if structure.style == 'lightweight': return plan       # its sections already have their openings
    # Most bands of a rack have the same bores open, so their union is worked out once.
    open_now = tuple(i for i, t in enumerate(structure.tubes) if t.floor <= z0 + 1e-6 and t.deck > z0)
    if not open_now: return plan
    key = (open_now, segments)
    if key not in structure.holes: structure.holes[key] = unary_union([disc(structure.tubes[i].x, structure.tubes[i].y, structure.tubes[i].radius, segments) for i in open_now])
    return plan.difference(structure.holes[key])

def polygons(geometry):
    if geometry.is_empty: return []
    return list(geometry.geoms) if hasattr(geometry, 'geoms') else [geometry]

def rings(geometry, tolerance=.03):
    """JSON form of a plan: [{'outer': [[x, y], ...], 'holes': [...]}], ready to extrude."""
    result = []
    for poly in polygons(geometry.simplify(tolerance)):
        if poly.geom_type != 'Polygon' or poly.area < .01: continue
        result.append({'outer': [[round(x, 2), round(y, 2)] for x, y in poly.exterior.coords[:-1]], 'holes': [[[round(x, 2), round(y, 2)] for x, y in hole.coords[:-1]] for hole in poly.interiors]})
    return result

