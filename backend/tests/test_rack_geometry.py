"""The CAD generator, end to end. Exports are reopened and measured with trimesh, independently of the CAD kernel that
made them: holes are counted and measured from a cross-section of the mesh, not from the plan.

Needs CadQuery and trimesh, which only the worker image and a development environment have (requirements-cad.txt).
These tests say nothing about printed strength or fit: see docs/features/PARAMETRIC_RACK_CONFIGURATOR.md.
"""
import io, math, zipfile
import numpy as np
import pytest
pytest.importorskip('cadquery')
trimesh = pytest.importorskip('trimesh')
from shapely.geometry import LineString, Point
from shapely.ops import polygonize, unary_union
from app.mesh import analyze, load_mesh
from app.rack import build as rack_build, geometry
from app.rack.planner import plan
from app.rack.profiles import PROFILES
from app.rack.rules import MAX_TUBES, RULES
from app.rack.schema import RackConfiguration
from app.rack.structure import body_profile, inset_at

P50, P15, P15M, P05 = 'conical-50-generic', 'conical-15-generic', 'micro-1.5-generic', 'micro-0.5-generic'
PRINTER = [(500, 500, 256)]
HOLE_TOLERANCE_MM = .25       # measured against a faceted section

def configuration(tubes, style='lightweight', **extra):
    return RackConfiguration(tubes=[{'profile_id': p, 'quantity': n} for p, n in tubes.items()], style=style, **extra)

_built = {}
def built(tmp_path_factory, key, config):
    """Build each configuration once per test run: geometry is deterministic and CAD is the slow part."""
    if key not in _built:
        result = plan(config, PRINTER)
        assert result['ok'], result['issues']
        directory = tmp_path_factory.mktemp('rack')
        output = rack_build.run(result['spec'], directory)
        stl = trimesh.load(directory / 'rack.stl', force='mesh')
        threemf = trimesh.load(directory / 'rack.3mf', force='mesh')
        _built[key] = dict(plan=result, output=output, dir=directory, stl=stl, threemf=threemf)
    return _built[key]

def section_faces(mesh, z):
    """Closed regions of the plane z in the mesh, from its triangles alone."""
    segments = trimesh.intersections.mesh_plane(mesh, plane_normal=[0, 0, 1], plane_origin=[0, 0, z])
    lines = [LineString(np.round(s[:, :2], 4)) for s in segments if np.linalg.norm(s[0, :2] - s[1, :2]) > 1e-6]
    return list(polygonize(unary_union(lines)))

def holes_at(mesh, tube):
    """The opening around this tube at a height just under its deck, as measured from the mesh."""
    z = tube['deck'] - 2.0
    return [f for f in section_faces(mesh, z) if f.contains(Point(tube['x'], tube['y']))]

def assert_sound(case):
    """What every exported rack must satisfy, whichever options made it."""
    for mesh in (case['stl'], case['threemf']):
        assert mesh.is_watertight and mesh.is_winding_consistent and mesh.is_volume
        assert len(mesh.split(only_watertight=False)) == 1
        assert mesh.volume > 0
    expected = case['plan']['dims']
    label = case['plan']['label']
    slack = .05 + (label['depth'] if label and label['style'] == 'embossed' else 0)
    assert np.all(np.abs(case['stl'].extents - np.array(expected)) <= slack)
    assert case['stl'].bounds[0][2] == pytest.approx(0, abs=1e-3)
    assert np.allclose(case['stl'].extents, case['threemf'].extents, atol=1e-3)
    assert np.all(case['threemf'].bounds[0] >= [0, 0, -1e-6])      # on the bed: slicers take a 3MF's position literally
    assert case['stl'].volume == pytest.approx(case['threemf'].volume, rel=1e-3)
    # Facets sit inside true arcs, so holes get a hair smaller and the mesh a hair larger, bounded by the mesh tolerance.
    assert abs(case['stl'].volume - case['output']['metrics']['volume_mm3']) <= case['output']['metrics']['area_mm2'] * rack_build.FINE
    checks = case['output']['report']['geometry_checked']
    assert checks and all(c['status'] == 'pass' for c in checks)
    # The plan's estimate, used before the CAD exists, stays close to the measured solid.
    assert case['plan']['metrics']['volume_mm3'] == pytest.approx(case['output']['metrics']['volume_mm3'], rel=.06)

def assert_holes(case):
    """The right number of holes, in the right places, of the right size, measured from the mesh."""
    tubes = case['plan']['tubes']
    assert len(tubes) == case['output']['metrics']['holes']
    for tube in tubes:
        found = holes_at(case['stl'], tube)
        assert len(found) == 1, f'no single opening at {tube}'
        opening = found[0]
        assert Point(opening.centroid).distance(Point(tube['x'], tube['y'])) < HOLE_TOLERANCE_MM
        assert 2 * math.sqrt(opening.area / math.pi) == pytest.approx(tube['bore_d'], abs=HOLE_TOLERANCE_MM)

SINGLE = [('1x50', {P50: 1}), ('6x50', {P50: 6}), ('20x50', {P50: 20}), ('24x1.5', {P15M: 24}), ('1x0.5', {P05: 1}), ('1x15', {P15: 1}), ('1x1.5', {P15M: 1})]
MIXED = [('15x50+5x15', {P50: 15, P15: 5}), ('6x50+12x1.5', {P50: 6, P15M: 12}), ('all-four', {P50: 3, P15: 4, P15M: 8, P05: 6})]

@pytest.mark.parametrize('style', ['lightweight', 'premium'])
@pytest.mark.parametrize('name,tubes', SINGLE + MIXED, ids=[n for n, _ in SINGLE + MIXED])
def test_racks_are_sound_and_their_holes_are_where_planned(tmp_path_factory, style, name, tubes):
    case = built(tmp_path_factory, (style, name), configuration(tubes, style))
    assert_sound(case); assert_holes(case)

@pytest.mark.parametrize('style', ['lightweight', 'premium'])
@pytest.mark.parametrize('position', ['front', 'left'])
@pytest.mark.parametrize('kind', ['engraved', 'embossed'])
def test_labels_are_real_geometry(tmp_path_factory, style, position, kind):
    tubes = {P50: 6}
    built(tmp_path_factory, (style, '6x50'), configuration(tubes, style))
    case = built(tmp_path_factory, (style, 'label', position, kind), configuration(tubes, style, label={'text': 'Lab 03', 'position': position, 'style': kind}))
    assert_sound(case); assert_holes(case)
    assert any(c['code'] == 'label_geometry' for c in case['output']['report']['geometry_checked'])
    label = case['plan']['label']
    # The letters are in the solid: they change its volume, in the direction their style says, and the name's own
    # outline can be found at the depth it should be, measured on the mesh along the face's own normal.
    plain = built(tmp_path_factory, (style, '6x50'), configuration(tubes, style))
    normal = face_normal(position, label['rake'])
    depths = (case['stl'].vertices - np.array(label['anchor'])) @ normal
    x_dir = np.cross((0, 0, 1), normal); x_dir = x_dir / np.linalg.norm(x_dir)
    z_dir = np.cross(normal, x_dir)
    across = (case['stl'].vertices - np.array(label['anchor'])) @ x_dir; up = (case['stl'].vertices - np.array(label['anchor'])) @ z_dir
    inside = (np.abs(across) < label['width'] / 2 + 1) & (np.abs(up) < label['cap'] / 2 + 1)
    if kind == 'engraved':
        assert np.isclose(depths[inside], -label['depth'], atol=.03).sum() > 8
    else:
        assert depths[inside].max() == pytest.approx(min(label['depth'], label.get('flat') or label['depth']), abs=.03)
        assert case['output']['metrics']['volume_mm3'] != plain['output']['metrics']['volume_mm3']

def face_normal(position, rake):
    r = math.radians(rake)
    xy = {'front': (0, -1), 'back': (0, 1), 'left': (-1, 0), 'right': (1, 0)}[position]
    return np.array((xy[0] * math.cos(r), xy[1] * math.cos(r), math.sin(r)))

def test_premium_top_label_is_engraved_in_the_deck(tmp_path_factory):
    case = built(tmp_path_factory, ('premium', 'label-top'), configuration({P50: 6}, 'premium', label={'text': 'Lab 03', 'position': 'top'}))
    assert_sound(case); assert_holes(case)
    deck = case['plan']['dims'][2]
    assert len(case['stl'].vertices[np.isclose(case['stl'].vertices[:, 2], deck - RULES.engrave_depth_mm, atol=.01)]) > 8

def width_at(mesh, z):
    return float(np.ptp(mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1]).vertices[:, 0]))

def test_premium_wall_is_convex_and_blends_into_the_deck(tmp_path_factory):
    """A soft body in the solid, not only in the render: measured on the exported mesh."""
    case = built(tmp_path_factory, ('premium', '6x50'), configuration({P50: 6}, 'premium'))
    mesh, (w, _, h) = case['stl'], case['plan']['dims']
    profile = case['plan']['spec']['terraces'][0]['profile']
    belly = profile['belly']
    samples = [width_at(mesh, z) for z in (.3, belly / 2, belly, (belly + h) / 2, h - 4, h - .5)]
    assert samples[2] == pytest.approx(w, abs=.1)                                # widest at the belly
    assert samples[0] < samples[1] < samples[2] > samples[3] > samples[4] > samples[5]    # and narrower both ways, without a step
    assert w - samples[0] > 2 and w - samples[5] > 4                             # by an amount that can be seen
    assert case['plan']['metrics']['min_wall_mm'] >= RULES.min_wall_mm
    assert case['output']['metrics']['overhang_area_ratio'] == 0                 # all of it within the printable limit

@pytest.mark.parametrize('height', [22.0, 27.0, 60.5, 63.5, 90.0])
def test_the_wall_below_the_belly_stays_well_inside_the_printable_limit(height):
    profile = body_profile(height, 1.25)
    worst = max((inset_at(profile, z) - inset_at(profile, z + .1)) / .1 for z in np.arange(0, profile['belly'], .1))
    assert math.degrees(math.atan(worst)) <= RULES.tuck_max_deg

def test_each_corner_follows_the_tube_nearest_it():
    """Different tubes in different corners make different radii; a single row makes capsule ends."""
    mixed = plan(configuration({P50: 15, P15M: 5}, 'premium'), PRINTER)
    assert all(r >= 6 for t in mixed['terraces'] for r in t['corners'])
    row = plan(configuration({P15M: 4}, 'premium'), PRINTER)
    width, depth = row['dims'][:2]
    assert min(row['terraces'][0]['corners']) >= .33 * min(width, depth)
    for tubes in ({P50: 6}, {P15: 30}, {P15M: 24}):
        result = plan(configuration(tubes, 'premium'), PRINTER)
        assert result['ok'] and result['metrics']['min_wall_mm'] >= RULES.min_wall_mm
        assert all(r > 6 for r in result['terraces'][0]['corners'])

def test_tall_tubes_make_a_raised_level_along_the_back(tmp_path_factory):
    config = configuration({P50: 2, P15: 3, P15M: 18, P05: 15}, 'premium')
    case = built(tmp_path_factory, ('premium', 'rear-terrace'), config)
    assert_sound(case); assert_holes(case)
    result = case['plan']
    tall = [t for t in result['tubes'] if t['deck'] == max(x['deck'] for x in result['tubes'])]
    low = [t for t in result['tubes'] if t['deck'] < tall[0]['deck']]
    assert min(t['y'] for t in tall) > min(t['y'] for t in low)
    assert not any('blend' in n for n in case['output']['notes'])
    x0, _, x1, _ = result['terraces'][1]['rect']
    assert x1 - x0 > .7 * result['dims'][0]         # a level across the rack, not a block standing on a tray

def test_premium_changes_do_not_touch_a_lightweight_rack():
    result = plan(configuration({P50: 6}), PRINTER)
    assert result['spec']['geometry_version'] == 3
    assert plan(configuration({P50: 6}, 'premium'), PRINTER)['spec']['geometry_version'] == 4

def test_the_premium_preview_is_the_same_shape_as_the_exported_model(tmp_path_factory):
    """The preview carries the CAD's own normals on its own mesh path, so check it against the file a host would print."""
    case = built(tmp_path_factory, ('premium', '6x50'), configuration({P50: 6}, 'premium'))
    glb = (case['dir'] / 'preview.glb').read_bytes()
    assert b'exact_normals' in glb
    preview = trimesh.load(io.BytesIO(glb), file_type='glb', force='mesh')
    # glTF is Y up: X stays, CAD Y is -Z, CAD Z is Y.
    points = preview.vertices[:, [0, 2, 1]] * [1, -1, 1]
    assert np.allclose(points.min(axis=0), case['stl'].bounds[0], atol=.2) and np.allclose(points.max(axis=0), case['stl'].bounds[1], atol=.2)
    for tube in case['plan']['tubes']:      # every bore is where it belongs, not at its tool's origin
        near = np.hypot(points[:, 0] - tube['x'], points[:, 1] - tube['y'])
        wall = (near > tube['bore_d'] / 2 - .4) & (near < tube['bore_d'] / 2 + .4) & (points[:, 2] > tube['floor']) & (points[:, 2] < tube['deck'])
        assert wall.sum() >= 8
    # Every point of what the buyer sees lies on the model that is printed, and the other way round.
    pytest.importorskip('rtree')
    shown = trimesh.Trimesh(points, preview.faces, process=True)
    for source, target in ((shown, case['stl']), (case['stl'], shown)):
        samples, _ = trimesh.sample.sample_surface(source, 3000, seed=1)
        assert trimesh.proximity.closest_point(target, samples)[1].max() < .1
    # And it is wound outward: welded, its signed volume is that of the rack.
    assert trimesh.Trimesh(preview.vertices, preview.faces, process=True).volume == pytest.approx(case['stl'].volume, rel=.03)

@pytest.mark.parametrize('tubes,tallest', [({P50: 6}, 47), ({P15: 12}, 47), ({P15M: 24}, 24), ({P05: 24}, 20), ({P50: 15, P15: 5}, 47)])
def test_premium_racks_are_low_and_still_hold_their_tubes(tubes, tallest):
    result = plan(configuration(tubes, 'premium'), PRINTER)
    assert result['dims'][2] <= tallest
    for t in result['tubes']:
        profile = PROFILES[t['profile_id']]
        held = t['deck'] - t['floor']
        # Past the cone wherever the tube is long enough to have room; always something left to hold; the floor is intact.
        assert held >= min(profile.cone_length_mm + RULES.grip_min_mm, profile.overall_length_mm * (1 - RULES.exposed_share)) - .5
        assert t['length'] - held >= t['length'] * RULES.exposed_share - .5
        assert t['floor'] >= RULES.floor_mm - .01

def test_a_low_premium_rack_is_lighter_than_a_tall_one_would_be():
    assert plan(configuration({P50: 20}, 'premium'), PRINTER)['estimates']['materials']['PETG']['grams'] < 420

def test_lightweight_height_is_unchanged():
    assert plan(configuration({P50: 6}), PRINTER)['dims'][2] == 60.5 and plan(configuration({P15M: 24}), PRINTER)['dims'][2] == 27.5

@pytest.mark.parametrize('style', ['premium', 'lightweight'])
@pytest.mark.parametrize('name,tubes', [('falcon', {P50: 6}), ('micro', {P15M: 12}), ('mixed', {P50: 2, P15M: 8})], ids=['falcon', 'micro', 'mixed'])
@pytest.mark.parametrize('end', ['min', 'max'])
def test_the_lowest_and_highest_racks_are_real_sound_solids(tmp_path_factory, style, name, tubes, end):
    height = plan(configuration(tubes, style), PRINTER)['height'][end]
    case = built(tmp_path_factory, (style, name, end), configuration(tubes, style, height_mm=height))
    assert_sound(case); assert_holes(case)
    assert case['stl'].extents[2] == pytest.approx(height, abs=.26)         # the height in the file is the height asked for
    assert all(c['status'] == 'pass' for c in case['output']['report']['geometry_checked'])

def test_a_lightweight_nameplate_is_slim_and_leans_back(tmp_path_factory):
    plain = built(tmp_path_factory, ('lightweight', '6x50'), configuration({P50: 6}))
    case = built(tmp_path_factory, ('lightweight', 'label', 'front', 'engraved'), configuration({P50: 6}, 'lightweight', label={'text': 'Lab 03', 'position': 'front', 'style': 'engraved'}))
    added = case['output']['metrics']['volume_mm3'] - plain['output']['metrics']['volume_mm3']
    assert added < 9000      # mm3: a slim plate and its frame, far from a slab across the whole front
    spec = case['plan']['spec']['plate']
    assert spec['s1'] - spec['s0'] < case['plan']['dims'][0]
    assert spec['run'] / spec['height'] == pytest.approx(math.tan(math.radians(RULES.label_rake_deg)), abs=.01)

def test_a_long_name_widens_the_rack_rather_than_being_refused():
    short = plan(configuration({P50: 4}, 'premium'), PRINTER)
    named = plan(configuration({P50: 4}, 'premium', label={'text': 'Molecular Biology'}), PRINTER)
    assert named['ok'], named['issues']
    assert named['dims'][0] >= short['dims'][0]
    much_too_long = plan(configuration({P05: 2}, 'premium', label={'text': 'Department of Molecular Biology and Genetics'}), PRINTER)
    assert any(i['code'] == 'label_too_long' for i in much_too_long['issues'])

def test_a_stored_specification_of_the_earlier_design_still_builds(tmp_path_factory):
    """Orders keep their specification: a rack sold before a redesign must stay buildable as it was sold."""
    from shapely.geometry import box
    ring = {'outer': [[-30, -30], [30, -30], [30, 30], [-30, 30]], 'holes': []}
    tube = {'profile_id': P15, 'x': 0.0, 'y': 0.0, 'bore_d': 18.2, 'deck': 60.0, 'floor': 3.2, 'tip_d': 5.0, 'cone': 20.0, 'seat': 'dimple', 'drain_d': 3.0}
    spec = {'geometry_version': 2, 'style': 'lightweight', 'footprint': [-30, -30, 30, 30], 'dims': [60, 60, 60.0], 'tubes': [tube], 'label': None, 'entry_chamfer': .8,
            'bands': [{'z0': 0.0, 'z1': 60.0, 'polys': [ring]}], 'windows': []}
    assert box(-1, -1, 1, 1).area == 4
    solid, _, _ = geometry.build(spec)
    assert solid.isValid() and solid.Volume() > 0

def test_lightweight_is_support_free_and_open(tmp_path_factory):
    case = built(tmp_path_factory, ('lightweight', '20x50'), configuration({P50: 20}))
    report = case['output']['report']
    assert case['output']['metrics']['overhang_area_ratio'] < .02
    assert any('print upright' in f['message'] for f in report['manufacturing_estimated'])
    # Open under the tubes and open between them: the base covers far less than the footprint.
    assert case['plan']['metrics']['bed_contact_mm2'] < .65 * case['plan']['dims'][0] * case['plan']['dims'][1]

def test_square_grids_have_no_crossing_diagonal_webs():
    from app.rack.structure import gabriel_edges
    grid = [(x, y) for x in (0, 38, 76) for y in (0, 38)]
    assert sorted(gabriel_edges(grid)) == [(0, 1), (0, 2), (1, 3), (2, 3), (2, 4), (3, 5), (4, 5)]

def test_premium_uses_much_more_material_for_a_solid_body(tmp_path_factory):
    light = built(tmp_path_factory, ('lightweight', '6x50'), configuration({P50: 6}))
    solid = built(tmp_path_factory, ('premium', '6x50'), configuration({P50: 6}, 'premium'))
    assert light['stl'].volume < solid['stl'].volume * .4

def test_premium_tube_seats_taper_to_the_tip(tmp_path_factory):
    """A tapered seat, not a cylindrical hole: lower in the cavity the opening is much narrower than the bore."""
    case = built(tmp_path_factory, ('premium', '6x50'), configuration({P50: 6}, 'premium'))
    tube = case['plan']['tubes'][0]
    low = [f for f in section_faces(case['stl'], tube['floor'] + 2) if f.contains(Point(tube['x'], tube['y']))]
    assert len(low) == 1 and 2 * math.sqrt(low[0].area / math.pi) < tube['bore_d'] * .55

def test_short_tubes_stand_on_raised_seats_when_a_taller_terrace_surrounds_them(tmp_path_factory):
    positions = [(P50, x, y) for x in (-40, 0, 40) for y in (-40, 0, 40) if (x, y) != (0, 0)] + [(P15M, 0, 0)]
    config = RackConfiguration(style='premium', layout={'mode': 'manual', 'positions': [{'profile_id': p, 'x': x, 'y': y} for p, x, y in positions]})
    case = built(tmp_path_factory, ('premium', 'interleaved'), config)
    assert_sound(case); assert_holes(case)
    centre = next(t for t in case['plan']['tubes'] if t['profile_id'] == P15M)
    assert centre['deck'] == case['plan']['dims'][2] and centre['floor'] > 20

@pytest.mark.parametrize('style', ['lightweight', 'premium'])
def test_large_tube_counts_stay_within_time_and_mesh_limits(tmp_path_factory, style):
    case = built(tmp_path_factory, (style, 'max'), configuration({P05: MAX_TUBES}, style))
    assert_sound(case)
    assert case['output']['metrics']['total_seconds'] < 150
    assert case['output']['metrics']['triangles'] < 400_000

@pytest.mark.parametrize('edge', ['sharp', 'soft', 'rounded'])
def test_edge_treatments(tmp_path_factory, edge):
    case = built(tmp_path_factory, ('premium', 'edge', edge), configuration({P15: 6}, 'premium', edge=edge))
    assert_sound(case); assert_holes(case)
    assert not case['output']['notes']

def test_an_excessive_radius_never_reaches_the_solid(tmp_path_factory):
    case = built(tmp_path_factory, ('premium', 'radius'), configuration({P50: 2}, 'premium', corner_radius_mm=50))
    assert any(i['code'] == 'fillet_clamped' for i in case['plan']['issues'])
    assert_sound(case); assert_holes(case)

def test_a_failing_blend_falls_back_instead_of_failing(monkeypatch):
    monkeypatch.setattr(geometry, '_blended', lambda *a: None)
    spec = plan(configuration({P50: 2, P15M: 12}, 'premium'), PRINTER)['spec']
    solid, notes, _ = geometry.build(spec)
    assert solid.isValid() and 'terrace blend skipped' in notes

def test_invalid_geometry_is_refused_and_nothing_is_written(tmp_path):
    spec = plan(configuration({P15: 2}, 'premium'), PRINTER)['spec']
    tube = spec['tubes'][0]
    other = spec['tubes'][1]
    other['x'], other['y'] = tube['x'] + 100, tube['y']    # a cavity out in the air: dimensions still match, but it has no wall
    with pytest.raises(rack_build.ValidationFailed) as refused:
        rack_build.run(spec, tmp_path)
    assert any(c['status'] == 'fail' for c in refused.value.checks)
    assert not (tmp_path / 'rack.stl').exists() and not (tmp_path / 'rack.3mf').exists()

def test_exports_are_reproducible_and_previews_are_coarser(tmp_path_factory):
    case = built(tmp_path_factory, ('lightweight', '6x50'), configuration({P50: 6}))
    metrics = case['output']['metrics']
    assert metrics['preview_triangles'] <= metrics['triangles']
    premium = built(tmp_path_factory, ('premium', '6x50'), configuration({P50: 6}, 'premium'))['output']['metrics']
    assert premium['preview_triangles'] < premium['triangles']
    again = tmp_path_factory.mktemp('again')
    rack_build.run(case['plan']['spec'], again)
    assert (again / 'rack.stl').read_bytes() == (case['dir'] / 'rack.stl').read_bytes()
    assert (again / 'rack.3mf').read_bytes() == (case['dir'] / 'rack.3mf').read_bytes()
    # The site's own bounded parser accepts both, as it does any upload.
    assert analyze(load_mesh((case['dir'] / 'rack.3mf').read_bytes(), '.3mf'))['watertight']
    with zipfile.ZipFile(io.BytesIO((case['dir'] / 'rack.3mf').read_bytes())) as archive:
        assert sorted(archive.namelist()) == ['3D/3dmodel.model', '[Content_Types].xml', '_rels/.rels']
    glb = (case['dir'] / 'preview.glb').read_bytes()
    assert glb[:4] == b'glTF'
    scene = trimesh.load(io.BytesIO(glb), file_type='glb', force='mesh')
    assert scene.is_watertight or len(scene.faces) == metrics['preview_triangles']
