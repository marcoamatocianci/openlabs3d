"""OpenLabs3D rotating DNA pipette stand. Millimeters; every part modelled in its FDM print orientation.

Original geometry. Concept inspired by "DNA pipette stand / holder, customizable" by pixel on Printables
(https://www.printables.com/model/1332410-dna-pipette-stand-holder-customizable); no files from that
design were used.

Parts (print each flat side down, no supports intended):
  foot         wide base with an integral spindle the tower turns on
  tower_lower  helix tower, lower half; spindle bore below, keyed spigot on top
  tower_upper  helix tower, upper half; keyed socket below, keyed spigot on top
  crown        hanger arms with knob hangers and the embossed logo finial
Rotation is a printed plain bearing (spindle in bore, on a thrust ring); no hardware.
"""
import math
import cadquery as cq

# UNVERIFIED pipette fit: universal single-channel defaults, not measured on any brand.
# Confirm with a test print of the crown (see README) before relying on them.
PIPETTE_FIT = {
    'knob_width': 7.0,        # tangential width of the knob the finger hook rests on; must pass the hook opening
    'knob_height': 7.0,       # knob height above the bed when the crown is printed
    'knob_length': 18.0,      # radial length available to the finger hook
    'lip_height': 13.0,       # retaining lip at the knob end that stops the hook sliding off
    'hang_radius': 67.0,      # knob centre radius; neighbouring pipettes are 2·r·sin(180°/n) apart
    'min_spacing': 60.0,      # required centre spacing between neighbouring pipettes (body clearance)
    'tip_clearance': 240.0,   # minimum free drop from the knob top to the foot for the hanging pipette
}

PARAMETERS = {
    'positions': 6,
    'helix': True,
    'logo': 'OpenLabs3D',
    'bed': (200.0, 200.0, 200.0),      # assumed per-part build volume
    'foot_diameter': 190.0, 'foot_height': 12.0,
    'tower_radius': 25.0, 'tower_height': 250.0,
    'spindle_diameter': 20.0, 'spindle_height': 20.0, 'bearing_clearance': 0.4,   # diametral
    'thrust_ring': (40.0, 52.0, 1.5),  # inner/outer diameter and height of the bearing ring on the foot
    'key_diameter': 24.0, 'key_flat': 2.5, 'joint_clearance': 0.25,               # per side
    'spigot_height': 10.0, 'crown_spigot_height': 6.0,
    'helix_pitch': 195.0, 'strand_radius': 3.0, 'rung_spacing': 16.0,
    'arm_width': 14.0, 'arm_height': 8.0, 'hub_diameter': 56.0, 'hub_height': 24.0,
    'overhang_limit_deg': 45.0, 'design_slope_deg': 50.0,
}

P, F = PARAMETERS, PIPETTE_FIT
assert 2 * F['hang_radius'] * math.sin(math.pi / P['positions']) >= F['min_spacing'], 'pipettes would touch'
# Knob top above the foot surface: a hanging pipette needs at least tip_clearance of free drop.
assert P['thrust_ring'][2] + P['tower_height'] + F['knob_height'] >= F['tip_clearance'], 'tower too short for pipettes'
assert F['hang_radius'] + F['knob_length'] / 2 < P['foot_diameter'] / 2, 'hanging load must stay inside the footprint'
CONE_RISE = math.tan(math.radians(P['design_slope_deg']))   # socket ceilings rise at 50°, never flatter


def d_profile(diameter, flat, height, z=0.0):
    """Keyed D section: a cylinder with one flat, so joints only seat with the helix aligned."""
    r = diameter / 2
    cylinder = cq.Workplane('XY').workplane(offset=z).circle(r).extrude(height)
    return cylinder.cut(cq.Workplane('XY').workplane(offset=z).center(2 * r - flat, 0).rect(2 * r, 2 * r).extrude(height))


def keyed_socket(height, from_top_of=None):
    """Socket opening downward with a 50° conical ceiling (prints without bridging)."""
    d = P['key_diameter'] + 2 * P['joint_clearance']
    flat = P['key_flat'] - P['joint_clearance']
    body = d_profile(d, flat, height)
    cone = cq.Workplane('XY').add(cq.Solid.makeCone(d / 2, 0.5, (d / 2 - 0.5) * CONE_RISE, cq.Vector(0, 0, height)))
    return body.union(cone)


def tower():
    """Exact B-rep tower core; the helix relief is added as a mesh in helix_relief()."""
    return cq.Workplane('XY').circle(P['tower_radius']).extrude(P['tower_height']).faces('>Z').edges().fillet(1.6)


def helix_relief():
    """Two strands 180° apart with nucleotide rungs, as one watertight mesh in full-tower coordinates.

    Swept B-rep strands tessellate with open seams, so the relief is built as meshes and fused with a
    manifold boolean. At 195 mm pitch the strand axis rises at ~50°, so its underside never overhangs
    more than ~40° from vertical; rung faces slope at 50° above and below. Everything is fused to the wall.
    """
    import numpy as np, trimesh
    from shapely.geometry import Point, Polygon
    r, h, pitch = P['tower_radius'], P['tower_height'], P['helix_pitch']
    pieces = []
    t = np.linspace(-0.5, h / pitch + 0.5, 700) * 2 * np.pi
    for phase in (0, np.pi):
        path = np.c_[(r + 1) * np.cos(t + phase), (r + 1) * np.sin(t + phase), pitch * t / (2 * np.pi)]
        pieces.append(trimesh.creation.sweep_polygon(Point(0, 0).buffer(P['strand_radius'], 16), path))
    rise = 2.7 * CONE_RISE   # 2.7 mm outward run over the 50° slope
    profile = np.array([[r - 0.5, 0], [r + 2.2, rise], [r + 2.2, rise + 1.2], [r - 0.5, 2 * rise + 1.2], [r - 0.5, 0]])
    ring = trimesh.creation.revolve(profile, sections=96)
    z, side = P['rung_spacing'] / 2, 0
    while z < h - 2 * rise - 4:
        a0 = np.radians(360 * z / pitch + 180 * side + 6); angles = np.linspace(a0, a0 + np.radians(168), 48)
        wedge = trimesh.creation.extrude_polygon(Polygon([(0, 0)] + [(r * 2 * np.cos(a), r * 2 * np.sin(a)) for a in angles]), 2 * rise + 3)
        wedge.apply_translation((0, 0, -1))
        rung = trimesh.boolean.intersection([ring, wedge], engine='manifold'); rung.apply_translation((0, 0, z))
        pieces.append(rung); z += P['rung_spacing']; side ^= 1
    relief = trimesh.boolean.union(pieces, engine='manifold')
    slab = trimesh.creation.box((4 * r, 4 * r, h)); slab.apply_translation((0, 0, h / 2))
    return trimesh.boolean.intersection([relief, slab], engine='manifold')


def build_parts():
    split = P['tower_height'] / 2
    full = tower()
    lower = full.intersect(cq.Workplane('XY').circle(40).extrude(split))
    upper = full.intersect(cq.Workplane('XY').workplane(offset=split).circle(40).extrude(split)).translate((0, 0, -split))

    # Lower tower: spindle bore from below, keyed spigot on top.
    bore = P['spindle_diameter'] + P['bearing_clearance']
    bore_depth = P['spindle_height'] + 0.5
    lower = lower.cut(cq.Workplane('XY').circle(bore / 2).extrude(bore_depth))
    lower = lower.cut(cq.Workplane('XY').add(cq.Solid.makeCone(bore / 2, 0.5, (bore / 2 - 0.5) * CONE_RISE, cq.Vector(0, 0, bore_depth))))
    lower = lower.union(d_profile(P['key_diameter'], P['key_flat'], P['spigot_height'], split).edges('>Z').chamfer(0.6))

    # Upper tower: keyed socket below, keyed spigot on top for the crown.
    upper = upper.cut(keyed_socket(P['spigot_height'] + 0.5))
    upper = upper.union(d_profile(P['key_diameter'], P['key_flat'], P['crown_spigot_height'], split).edges('>Z').chamfer(0.6))

    # Foot: wide disc, thrust ring and spindle the tower turns on.
    fd, fh = P['foot_diameter'], P['foot_height']
    foot = cq.Workplane('XY').circle(fd / 2).extrude(fh).faces('>Z').edges().fillet(4)
    ring_in, ring_out, ring_h = P['thrust_ring']
    foot = foot.union(cq.Workplane('XY').workplane(offset=fh).circle(ring_out / 2).circle(ring_in / 2).extrude(ring_h))
    spindle = cq.Workplane('XY').workplane(offset=fh).circle(P['spindle_diameter'] / 2).extrude(P['spindle_height']).faces('>Z').edges().chamfer(1.5)
    foot = foot.union(spindle)

    # Crown: hub finial with logo and radial arms ending in knob hangers, printed in its use orientation.
    n, ah, aw = P['positions'], P['arm_height'], P['arm_width']
    hub = cq.Workplane('XY').circle(P['hub_diameter'] / 2).extrude(P['hub_height']).faces('>Z').edges().fillet(2)
    crown = hub
    knob_start = F['hang_radius'] - F['knob_length'] / 2
    for i in range(n):
        a = 360 * i / n
        arm = cq.Workplane('XY').center((P['hub_diameter'] / 2 - 2 + knob_start) / 2, 0).rect(knob_start - P['hub_diameter'] / 2 + 2, aw).extrude(ah)
        # Knob: flat underside on the bed, rounded top the finger hook rests on.
        knob = tombstone(F['knob_width'], F['knob_height'], F['knob_length'], knob_start)
        lip = tombstone(F['knob_width'] + 3, F['lip_height'], 4.0, knob_start + F['knob_length'])
        crown = crown.union(arm.union(knob).union(lip).rotate((0, 0, 0), (0, 0, 1), a))
    crown = crown.cut(keyed_socket(P['crown_spigot_height'] + 0.5))
    if P['logo']:
        text = cq.Workplane('XY').workplane(offset=P['hub_height']).text(P['logo'], 6.5, 1.0, combine=True, font='Sans', kind='bold', halign='center', valign='center')
        crown = crown.union(text)
    return {'foot': foot, 'tower_lower': lower, 'tower_upper': upper, 'crown': crown}


def tombstone(width, height, length, start):
    """Radial bar with a flat base and a semicircular top: printable flat, smooth where the hook sits."""
    r = width / 2
    profile = cq.Workplane('YZ').workplane(offset=start).moveTo(-r, 0).lineTo(r, 0).lineTo(r, height - r).threePointArc((0, height), (-r, height - r)).close()
    return profile.extrude(length)


def mesh_of(shape, tolerance):
    import tempfile, os, trimesh
    handle, path = tempfile.mkstemp(suffix='.stl'); os.close(handle)
    try:
        cq.exporters.export(shape, path, tolerance=tolerance, angularTolerance=.1)
        return trimesh.load(path, force='mesh')
    finally:
        os.remove(path)


def clean(mesh):
    """Collapse sliver and zero-area triangles left by booleans so the mesh survives a float32 STL round trip.

    0.02 mm is far below FDM resolution (0.4 mm nozzle, 0.2 mm layers); volume changes by < 0.01%.
    """
    import numpy as np, trimesh, manifold3d
    solid = manifold3d.Manifold(manifold3d.Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32), tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))
    out = solid.simplify(0.02).to_mesh()
    return trimesh.Trimesh(out.vert_properties[:, :3], out.tri_verts)


def part_meshes(tolerance=.03):
    """Printable parts as watertight meshes in print orientation (towers carry the helix relief)."""
    import trimesh
    meshes = {name: mesh_of(shape, tolerance) for name, shape in parts.items()}
    if P['helix']:
        split = P['tower_height'] / 2
        relief = helix_relief()
        for name, z0 in (('tower_lower', 0.0), ('tower_upper', split)):
            slab = trimesh.creation.box((200, 200, split)); slab.apply_translation((0, 0, z0 + split / 2))
            piece = trimesh.boolean.intersection([relief, slab], engine='manifold'); piece.apply_translation((0, 0, -z0))
            meshes[name] = trimesh.boolean.union([meshes[name], piece], engine='manifold')
    return {name: clean(mesh) for name, mesh in meshes.items()}


def assemble(meshes):
    """Assembled stand for renders and the viewer only; hosts print the separate parts."""
    import trimesh
    seat = P['foot_height'] + P['thrust_ring'][2]; split = P['tower_height'] / 2
    placed = [meshes['foot']]
    # Each part sinks 0.05 mm into the one below so coplanar contact faces fuse into one display solid.
    for n, (name, z) in enumerate((('tower_lower', seat), ('tower_upper', seat + split), ('crown', seat + P['tower_height'])), 1):
        placed.append(meshes[name].copy().apply_translation((0, 0, z - 0.05 * n)))
    return clean(trimesh.boolean.union(placed, engine='manifold'))


parts = build_parts()
