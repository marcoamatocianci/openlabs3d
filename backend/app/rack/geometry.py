"""The CAD generator: a spec becomes one CadQuery solid. Worker only, never imported by the web process.

The spec comes from the planner; no user text reaches this module except a label already checked against an allowed
alphabet, which is drawn as letters and never evaluated.
"""
import math
import cadquery as cq
import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCP.TopAbs import TopAbs_REVERSED
from OCP.TopLoc import TopLoc_Location
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt
from .labels import font_path
from .structure import inset_at

class GeometryError(ValueError): pass

def mesh_absolute(solid, tolerance, angular):
    """Mesh to a tolerance in millimetres. CadQuery's own mesh() makes it relative to each edge's length, which on a long curved
    wall meant errors near 1 mm, where this gives a tenth of the tolerance with fewer triangles."""
    BRepMesh_IncrementalMesh(solid.wrapped, tolerance, False, angular, True)

def surface_mesh(solid, tolerance, angular):
    """A display mesh whose normals come from the CAD surfaces themselves, not from averaging triangles: (vertices, faces,
    normals). Each CAD face keeps its own vertices, so a designed edge stays sharp and a curved wall shades as what it is,
    however long and thin the kernel's triangles are."""
    mesh_absolute(solid, tolerance, angular)
    vertices, normals, triangles, offset = [], [], [], 0
    for face in solid.Faces():
        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face.wrapped, location)
        if mesh is None: continue
        reversed_face = face.wrapped.Orientation() == TopAbs_REVERSED
        transform = location.Transformation()     # a face cut by a moved tool keeps its mesh in that tool's own coordinates
        properties = BRepLProp_SLProps(BRepAdaptor_Surface(face.wrapped), 1, 1e-6)
        for i in range(1, mesh.NbNodes() + 1):
            node, uv = mesh.Node(i).Transformed(transform), mesh.UVNode(i)
            vertices.append((node.X(), node.Y(), node.Z()))
            properties.SetParameters(uv.X(), uv.Y())
            if properties.IsNormalDefined():
                n = properties.Normal()
                normals.append((-n.X(), -n.Y(), -n.Z()) if reversed_face else (n.X(), n.Y(), n.Z()))
            else: normals.append((0.0, 0.0, 0.0))
        for i in range(1, mesh.NbTriangles() + 1):
            a, b, c = mesh.Triangle(i).Get()
            triangles.append((offset + a - 1, offset + c - 1, offset + b - 1) if reversed_face else (offset + a - 1, offset + b - 1, offset + c - 1))
        offset += mesh.NbNodes()
    return np.array(vertices, dtype=np.float64), np.array(triangles, dtype=np.int64), np.array(normals, dtype=np.float64)

def _prism(poly, z0, z1):
    outer = cq.Wire.makePolygon([cq.Vector(x, y, z0) for x, y in poly['outer']], close=True)
    holes = [cq.Wire.makePolygon([cq.Vector(x, y, z0) for x, y in ring], close=True) for ring in poly['holes']]
    return cq.Solid.extrudeLinear(outer, holes, cq.Vector(0, 0, z1 - z0))

def _cavity(tube, chamfer):
    """A bore as a revolved profile: seat, wall and entry chamfer. Cached per shape by the caller."""
    bore, deck, floor = tube['bore_d'] / 2, tube['deck'], tube['floor']
    drain = tube['drain_d'] / 2
    if tube['seat'] == 'tapered':
        tip = max(tube['tip_d'] / 2 + .3, drain + .3)
        cone = tube['cone']
        points = [(0, -1), (drain, -1), (drain, floor), (tip, floor), (bore, floor + cone), (bore, deck - chamfer), (bore + chamfer, deck), (bore + chamfer, deck + 1), (0, deck + 1)]
    else:
        # Lightweight: the wall stops just into the base; the hub keeps a shallow dimple that locates the tip.
        tip = max(tube['tip_d'] / 2 + .3, drain + .3)
        ledge = floor - .6
        dimple = ledge - 1.0
        points = [(0, -1), (drain, -1), (drain, dimple), (tip, dimple), (tip + 1.0, ledge), (bore, ledge), (bore, deck - chamfer), (bore + chamfer, deck), (bore + chamfer, deck + 1), (0, deck + 1)]
    profile = cq.Workplane('XZ').polyline(points).close()
    return profile.revolve(360, (0, 0, 0), (0, 1, 0)).val()

def _cavities(spec):
    tools, cache = [], {}
    for tube in spec['tubes']:
        key = (tube['bore_d'], tube['deck'], tube['floor'], tube['tip_d'], tube['cone'], tube['seat'], tube['drain_d'])
        if key not in cache: cache[key] = _cavity(tube, spec['entry_chamfer'])
        tools.append(cache[key].moved(cq.Location(cq.Vector(tube['x'], tube['y'], 0))))
    return tools

def _window(w):
    """A pointed opening through a sleeve or a web."""
    half = w['width'] / 2
    ux, uy = math.cos(w['angle']), math.sin(w['angle'])
    plane = cq.Plane(origin=(w['x'] + ux * w['r0'], w['y'] + uy * w['r0'], 0), xDir=(-uy, ux, 0), normal=(ux, uy, 0))
    points = [(-half, w['z0']), (half, w['z0']), (half, w['shoulder']), (0, w['apex']), (-half, w['shoulder'])]
    return cq.Workplane(plane).polyline(points).close().extrude(w['r1'] - w['r0']).val()

def _rounded(rect, z, corner, top, bottom, report):
    """One Premium terrace. Each edge treatment falls back rather than failing: fillet, then chamfer, then nothing."""
    x0, y0, x1, y1 = rect
    body = cq.Workplane('XY').center((x0 + x1) / 2, (y0 + y1) / 2).rect(x1 - x0, y1 - y0).extrude(z)
    if corner > 0:
        try: body = body.edges('|Z').fillet(corner)
        except Exception: report.append('corner fillet skipped')
    if top > 0:
        for name, apply in (('fillet', lambda b: b.faces('>Z').edges().fillet(top)), ('chamfer', lambda b: b.faces('>Z').edges().chamfer(min(top, .8)))):
            try:
                candidate = apply(body)
                if candidate.val().isValid(): body = candidate; break
            except Exception: pass
            report.append(f'top {name} skipped')
    else:
        try: body = body.faces('>Z').edges().chamfer(.4)
        except Exception: report.append('top chamfer skipped')
    if bottom > 0:
        try: body = body.faces('<Z').edges().chamfer(bottom)
        except Exception: report.append('bottom chamfer skipped')
    return body.val()

def _text(spec, inset, outward):
    """The label's letters as solids, from `inset` mm inside the face to `outward` mm outside it."""
    label = spec['label']
    x, y, z = label['anchor']
    planes = {'front': ((x, y + inset, z), (1, 0, 0), (0, -1, 0)), 'back': ((x, y - inset, z), (-1, 0, 0), (0, 1, 0)),
              'left': ((x + inset, y, z), (0, -1, 0), (-1, 0, 0)), 'right': ((x - inset, y, z), (0, 1, 0), (1, 0, 0)),
              'top': ((x, y, z - inset), (1, 0, 0), (0, 0, 1))}
    origin, x_dir, normal = planes[label['position']]
    plane = cq.Plane(origin=origin, xDir=x_dir, normal=normal)
    return cq.Workplane(plane).text(label['text'], label['size'], inset + outward, combine=False, clean=True, fontPath=font_path(label['font']), halign='center', valign='center').val()

def _text3(spec, inset, outward):
    """The letters on any face, leaning back by the label's rake."""
    label = spec['label']
    x, y, z = label['anchor']
    rake = math.radians(label.get('rake') or 0)
    side = {'front': ((0, -1), (1, 0)), 'back': ((0, 1), (-1, 0)), 'left': ((-1, 0), (0, -1)), 'right': ((1, 0), (0, 1))}.get(label['position'])
    if side:
        (nx, ny), x_dir = side
        normal = (nx * math.cos(rake), ny * math.cos(rake), math.sin(rake)); x_dir = (*x_dir, 0)
    else: normal, x_dir = (0, 0, 1), (1, 0, 0)
    plane = cq.Plane(origin=(x - normal[0] * inset, y - normal[1] * inset, z - normal[2] * inset), xDir=x_dir, normal=normal)
    return plane, cq.Workplane(plane).text(label['text'], label['size'], inset + outward, combine=False, clean=True, fontPath=font_path(label['font']), halign='center', valign='center').val()

def _section(rect, corners, by, z):
    """A rounded rectangle at a height, with its own radius at each corner, always as eight edges so that sections can be lofted."""
    x0, y0, x1, y1 = rect[0] + by, rect[1] + by, rect[2] - by, rect[3] - by
    k = 1 - math.sqrt(.5)
    a, b, c, d = (max(.3, r - by) for r in corners)    # front-left, front-right, back-right, back-left
    v = lambda x, y: cq.Vector(x, y, z)
    edges = [cq.Edge.makeLine(v(x0 + a, y0), v(x1 - b, y0)),
             cq.Edge.makeThreePointArc(v(x1 - b, y0), v(x1 - b * k, y0 + b * k), v(x1, y0 + b)),
             cq.Edge.makeLine(v(x1, y0 + b), v(x1, y1 - c)),
             cq.Edge.makeThreePointArc(v(x1, y1 - c), v(x1 - c * k, y1 - c * k), v(x1 - c, y1)),
             cq.Edge.makeLine(v(x1 - c, y1), v(x0 + d, y1)),
             cq.Edge.makeThreePointArc(v(x0 + d, y1), v(x0 + d * k, y1 - d * k), v(x0, y1 - d)),
             cq.Edge.makeLine(v(x0, y1 - d), v(x0, y0 + a)),
             cq.Edge.makeThreePointArc(v(x0, y0 + a), v(x0 + a * k, y0 + a * k), v(x0 + a, y0))]
    return cq.Wire.assembleEdges(edges)

def _wall_points(profile):
    """The wall's profile as (height, inset) points, split at the belly, where it is vertical: two curves, each smooth."""
    start, belly, height, r = profile['start'], profile['belly'], profile['height'], profile['round']
    lower = [start + (belly - start) * k / 6 for k in range(7)] if belly > start else []
    upper_straight = [belly + (height - r - belly) * k / 6 for k in range(7)]
    arc = [height - r + r * math.sin(math.pi / 2 * k / 7) for k in range(1, 8)]
    return [(z, inset_at(profile, z)) for z in lower], [(z, inset_at(profile, z)) for z in upper_straight + arc]

def _profile_edges(points_lists, place):
    edges = []
    for points in points_lists:
        if len(points) < 2: continue
        vectors = [place(inset, z) for z, inset in points]
        # A wall that does not lean here (a raised level below its belly) is a straight line.
        straight = all(abs(p[1] - points[0][1]) < 1e-6 for p in points)
        if straight: edges.append(cq.Edge.makeLine(vectors[0], vectors[-1])); continue
        # Vertical where the two curves meet at the belly, so no crease shows there; flat where the wall meets the deck.
        belly_is_first = points[0][1] < points[-1][1]
        up = cq.Vector(0, 0, 1)
        if belly_is_first:
            # Level where it arrives at the deck: the wall turns into the deck with no edge at all.
            inward = vectors[-1] - vectors[-2]
            edges.append(cq.Edge.makeSpline(vectors, tangents=[up, cq.Vector(inward.x, inward.y, 0).normalized()]))
        else: edges.append(cq.Edge.makeSpline(vectors, tangents=[(vectors[1] - vectors[0]).normalized(), up]))
    return edges

def _soft_body(terrace):
    """One level of a Premium rack as exact surfaces: the wall's profile extruded along each straight side and revolved about
    each corner's own axis, so the seams are tangent, nothing overshoots the planned outline, and the kernel gets true
    cylinders-of-a-curve to work with. Sewn with flat faces at top and bottom into one solid."""
    profile, rect, corners = terrace['profile'], terrace['rect'], terrace['corners']
    x0, y0, x1, y1 = rect
    a, b, c, d = corners        # front-left, front-right, back-right, back-left
    # Each corner: its axis, its radius, and the direction its quarter turn starts from, going anticlockwise round the rack.
    turns = (((x0 + a, y0 + a), a, math.pi), ((x1 - b, y0 + b), b, 1.5 * math.pi), ((x1 - c, y1 - c), c, 0.0), ((x0 + d, y1 - d), d, .5 * math.pi))
    curves = _wall_points(profile)
    faces = []
    for n, ((cx, cy), radius, start) in enumerate(turns):
        place_at = lambda angle: (lambda inset, z: cq.Vector(cx + (radius - inset) * math.cos(angle), cy + (radius - inset) * math.sin(angle), z))
        axis = gp_Ax1(gp_Pnt(cx, cy, 0), gp_Dir(0, 0, 1))
        for edge in _profile_edges(curves, place_at(start)):
            faces.append(cq.Face(BRepPrimAPI_MakeRevol(edge.wrapped, axis, math.pi / 2).Shape()))
        # The straight side from this corner's end to the next corner's start.
        (nx, ny), next_radius, next_start = turns[(n + 1) % 4]
        end = start + math.pi / 2
        run = cq.Vector(nx + next_radius * math.cos(next_start) - (cx + radius * math.cos(end)), ny + next_radius * math.sin(next_start) - (cy + radius * math.sin(end)), 0)
        if run.Length > 1e-3:
            for edge in _profile_edges(curves, place_at(end)):
                faces.append(cq.Face(BRepPrimAPI_MakePrism(edge.wrapped, run.wrapped).Shape()))
    levels = (profile['start'], profile['height'])
    for z in levels:
        faces.append(cq.Face.makeFromWires(_section(rect, corners, inset_at(profile, z), z)))
    solid = cq.Solid.makeSolid(cq.Shell.makeShell(faces))
    if solid.Volume() < 0: solid = cq.Solid(solid.wrapped.Reversed())
    return solid

# The kernel can lose a cut where a cavity's surface nearly touches a curved wall. This little tolerance settles it, far below anything printable.
CUT_TOLERANCE_MM = 1e-4

def _blended(plain, spec, radius):
    """A concave radius where each raised level meets the deck, instead of a crease. None if the kernel cannot make it."""
    deck = spec['terraces'][0]['z']
    body = plain
    for terrace in spec['terraces'][1:]:
        x0, y0, x1, y1 = terrace['rect']
        def at_foot(edge):
            c = edge.Center()
            return abs(c.z - deck) < 1e-3 and x0 - .5 <= c.x <= x1 + .5 and y0 - .5 <= c.y <= y1 + .5
        try:
            body = body.fillet(min(radius, (terrace['z'] - deck) / 4), [e for e in body.Edges() if at_foot(e)])
            if not body.isValid() or len(body.Solids()) != 1: return None
            body = body.Solids()[0]
        except Exception: return None
    return body

def _fresh_body(spec):
    pieces = [_soft_body(t) for t in spec['terraces']]
    return pieces[0].fuse(*pieces[1:]) if len(pieces) > 1 else pieces[0]

def _cut_premium(spec, tools, notes, blend=True):
    """The body with its cavities. The kernel occasionally cannot blend a level or cut through the blend, so it tries smaller
    radii, and a plain junction prints just as well: a rack is never refused for its blend. Each attempt starts from a newly
    made body, because a failed blend can leave the shape it was given unusable for later booleans."""
    blends = len(spec['terraces']) > 1
    for radius in (1.8, 1.0, .6) if blends and blend else ():
        body = _blended(_fresh_body(spec), spec, radius)
        if body is None: continue
        try:
            result = body.cut(*tools, tol=CUT_TOLERANCE_MM)
            if len(result.Solids()) == 1 and result.isValid(): return result
        except ValueError: pass
    if blends: notes.append('terrace blend skipped')
    for tolerance in (CUT_TOLERANCE_MM, None, 1e-3):
        try:
            result = _fresh_body(spec).cut(*tools, tol=tolerance)
            if len(result.Solids()) == 1 and result.isValid(): return result
        except ValueError: pass
    raise GeometryError('The rack could not be cut into one valid solid')

def _premium_cavity(tube):
    """A bore with a tapered seat and a rounded lead-in, revolved."""
    bore, deck, floor, lead = tube['bore_d'] / 2, tube['deck'], tube['floor'], tube['lead']
    drain, tip = tube['drain_d'] / 2, max(tube['tip_d'] / 2 + .3, tube['drain_d'] / 2 + .3)
    k = lead * (1 - math.sqrt(.5))
    profile = (cq.Workplane('XZ').moveTo(0, -1).lineTo(drain, -1).lineTo(drain, floor).lineTo(tip, floor).lineTo(bore, floor + tube['cone']).lineTo(bore, deck - lead)
               .threePointArc((bore + k, deck - k), (bore + lead, deck)).lineTo(bore + lead, deck + 1).lineTo(0, deck + 1).close())
    return profile.revolve(360, (0, 0, 0), (0, 1, 0)).val()

def _window_solid(shape, w):
    """A window through a funnel's wall: round below, pointed above, cut from inside the bore outward."""
    half = w['width'] / 2
    ux, uy = math.cos(w['angle']), math.sin(w['angle'])
    r0 = math.sqrt(max(0.0, shape['bore'] ** 2 - half ** 2)) - .6
    r1 = shape['bore'] + shape['wall'] + .6
    plane = cq.Plane(origin=(ux * r0, uy * r0, 0), xDir=(-uy, ux, 0), normal=(ux, uy, 0))
    low = w['z0'] + half
    sketch = cq.Workplane(plane).moveTo(-half, low).threePointArc((0, w['z0']), (half, low)).lineTo(half, w['shoulder']).lineTo(0, w['apex']).lineTo(-half, w['shoulder']).close()
    return sketch.extrude(r1 - r0).val()

def _funnel_solid(shape, chamfer):
    """One tube's funnel, sleeve and collar, as a single revolved wall with its windows cut."""
    bore, tip, floor, cone_top, deck, wall = shape['bore'], shape['tip'], shape['floor'], shape['cone_top'], shape['deck'], shape['wall']
    rim = .25                 # enough to take the edge off; a bridge meets the collar flush
    below = floor - .4        # sunk into the hub, so the two fuse cleanly
    points = [(tip, below), (tip + wall, below), (tip + wall, floor), (bore + wall, cone_top), (bore + wall, deck - rim), (bore + wall - rim, deck), (bore + chamfer, deck), (bore, deck - chamfer), (bore, cone_top), (tip, floor)]
    solid = cq.Workplane('XZ').polyline(points).close().revolve(360, (0, 0, 0), (0, 1, 0)).val()
    tools = [_window_solid(shape, w) for w in shape['windows']]
    return solid.cut(*tools) if tools else solid

def _web_tool(w):
    half = w['width'] / 2
    ux, uy = math.cos(w['angle']), math.sin(w['angle'])
    plane = cq.Plane(origin=(w['x'] - ux * 3, w['y'] - uy * 3, 0), xDir=(-uy, ux, 0), normal=(ux, uy, 0))
    low = w['z0'] + half
    return cq.Workplane(plane).moveTo(-half, low).threePointArc((0, w['z0']), (half, low)).lineTo(half, w['shoulder']).lineTo(0, w['apex']).lineTo(-half, w['shoulder']).close().extrude(6).val()

def _nameplate(spec):
    """A slim plate leaning back along one edge, its top corners rounded, standing on the frame."""
    plate = spec['plate']
    half, height, run, thick = plate['s1'], plate['height'], plate['run'], plate['thick']
    distance = abs(plate['face'])
    rake = math.atan2(run, height)
    length = height / math.cos(rake)
    # Drawn on the plate's own leaning face at the front edge, then turned to its side. It starts below the bed and is trimmed flat.
    plane = cq.Plane(origin=(0, -distance, 0), xDir=(1, 0, 0), normal=(0, -math.cos(rake), math.sin(rake)))
    r, k = 3.0, 3.0 * (1 - math.sqrt(.5))
    outline = (cq.Workplane(plane).moveTo(-half, -6).lineTo(half, -6).lineTo(half, length - r).threePointArc((half - k, length - k), (half - r, length))
               .lineTo(-half + r, length).threePointArc((-half + k, length - k), (-half, length - r)).close())
    body = outline.extrude(-thick * math.cos(rake)).val()
    trim = cq.Workplane('XY').box(4 * half + 40, 4 * distance + 40, 30, centered=(True, True, False)).translate((0, 0, -30)).val()
    body = body.cut(trim)
    angle = {'front': 0, 'back': 180, 'left': -90, 'right': 90}[plate['position']]
    return body.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), angle)

def _bridge(link):
    c, s = math.cos(link['angle']), math.sin(link['angle'])
    plane = cq.Plane(origin=(link['x'], link['y'], 0), xDir=(c, s, 0), normal=(s, -c, 0))
    return cq.Workplane(plane).polyline(link['profile']).close().extrude(link['thick'] / 2, both=True).val()

def _close_pairs(spec):
    """Tubes so close (only in a hand-made layout) that one's wall would reach into its neighbour's bore."""
    wall_of = {}
    for funnel in spec['funnels']:
        for x, y in funnel['at']: wall_of[(x, y)] = funnel['shape']['wall']
    tubes, close = spec['tubes'], set()
    for i, a in enumerate(tubes):
        for j in range(i + 1, len(tubes)):
            b = tubes[j]
            if math.hypot(a['x'] - b['x'], a['y'] - b['y']) < (a['bore_d'] + b['bore_d']) / 2 + wall_of.get((a['x'], a['y']), 2) + wall_of.get((b['x'], b['y']), 2): close.update((i, j))
    return [tubes[i] for i in close]

def _lightweight(spec):
    base = [_prism(poly, 0, spec['base']['z1']) for poly in spec['base']['polys']]
    parts = list(base)
    for funnel in spec['funnels']:
        solid = _funnel_solid(funnel['shape'], spec['entry_chamfer'])
        parts += [solid.moved(cq.Location(cq.Vector(x, y, 0))) for x, y in funnel['at']]
    for link in spec['links']:
        if link['kind'] == 'bridge': parts.append(_bridge(link)); continue
        prisms = [_prism(poly, link['z0'], link['z1']) for poly in link['polys']]
        if link['window']:
            tool = _web_tool(link['window'])
            prisms = [p.cut(tool) for p in prisms]
        parts += prisms
    if spec.get('plate'): parts.append(_nameplate(spec))
    body = parts[0].fuse(*parts[1:]) if len(parts) > 1 else parts[0]
    close = _close_pairs(spec)
    if close: body = body.cut(*[_cavity(t, spec['entry_chamfer']).moved(cq.Location(cq.Vector(t['x'], t['y'], 0))) for t in close])
    return body

def _finish(body, spec, notes):
    label = spec.get('label')
    volume_before_label = body.Volume()
    if label:
        flat = label.get('flat')
        if flat:
            # Everything outside the plane of the name goes: where the plane leaves the convex wall is the edge of the soft flat.
            plane = _text3(spec, 0, .1)[0]
            span = 4 * max(abs(v) for v in spec['footprint'])
            body = body.cut(cq.Workplane(plane).rect(span, span).extrude(40).val())
            if label['style'] == 'engraved': body = body.cut(_text3(spec, label['depth'], .1)[1])
            else: body = body.fuse(_text3(spec, .3, min(label['depth'], flat))[1])
        elif label['style'] == 'engraved': body = body.cut(_text3(spec, label['depth'], .5)[1])
        else: body = body.fuse(_text3(spec, .3, label['depth'])[1])
    if spec['style'] == 'premium':
        try:
            cleaned = body.clean()
            if cleaned.isValid() and len(cleaned.Solids()) == len(body.Solids()): body = cleaned
        except Exception: notes.append('face merge skipped')
    solids = body.Solids()
    if len(solids) != 1: raise GeometryError(f'The model has {len(solids)} separate bodies instead of one')
    solid = solids[0]
    if not solid.isValid(): raise GeometryError('The solid failed validity checks')
    if solid.Volume() <= 0: raise GeometryError('The solid has no volume')
    return solid, notes, volume_before_label

def build(spec, blend=True):
    """(solid, notes, volume before the label). Raises GeometryError when one valid solid cannot be made: nothing invalid is ever exported.
    blend=False makes a Premium rack's raised levels meet the deck plainly, for the rare blend the mesher cannot close."""
    if spec.get('geometry_version', 1) <= 2: return _build_v2(spec)
    notes = []
    if spec['style'] == 'lightweight': return _finish(_lightweight(spec), spec, notes)
    cache, tools = {}, []
    for tube in spec['tubes']:
        key = (tube['bore_d'], tube['deck'], tube['floor'], tube['tip_d'], tube['cone'], tube['drain_d'], tube['lead'])
        if key not in cache: cache[key] = _premium_cavity(tube)
        tools.append(cache[key].moved(cq.Location(cq.Vector(tube['x'], tube['y'], 0))))
    return _finish(_cut_premium(spec, tools, notes, blend), spec, notes)

def _build_v2(spec):
    """The earlier design, kept so that a stored specification of geometry version 2 can still be built exactly as sold."""
    notes = []
    if spec['style'] == 'lightweight':
        parts = [_prism(poly, band['z0'], band['z1']) for band in spec['bands'] for poly in band['polys']]
        # The prisms touch only at their flat ends, which is what the boolean's glue mode is for: about 3x faster.
        body = parts[0].fuse(*parts[1:], glue=True) if len(parts) > 1 else parts[0]
    else:
        parts = [_rounded(t['rect'], t['z'], spec['corner_r'], spec['top_fillet'], spec['bottom_chamfer'], notes) for t in spec['terraces']]
        body = parts[0].fuse(*parts[1:]) if len(parts) > 1 else parts[0]
    tools = _cavities(spec)
    if spec.get('windows'): tools += [_window(w) for w in spec['windows']]
    body = body.cut(*tools)
    del parts, tools
    label = spec.get('label')
    volume_before_label = body.Volume()
    if label:
        if label['style'] == 'engraved': body = body.cut(_text(spec, label['depth'], .5))
        else: body = body.fuse(_text(spec, .3, label['depth']))
    # Merging coplanar faces helps Premium's few large faces. Lightweight's thousands of planar facets gain nothing
    # from it, and it was measured there to take twice the rest of the build and to invalidate the solid.
    if spec['style'] == 'premium':
        try:
            cleaned = body.clean()
            if cleaned.isValid() and len(cleaned.Solids()) == len(body.Solids()): body = cleaned
        except Exception: notes.append('face merge skipped')
    solids = body.Solids()
    if len(solids) != 1: raise GeometryError(f'The model has {len(solids)} separate bodies instead of one')
    solid = solids[0]
    if not solid.isValid(): raise GeometryError('The solid failed validity checks')
    if solid.Volume() <= 0: raise GeometryError('The solid has no volume')
    return solid, notes, volume_before_label
