"""Run in the CadQuery environment (see pipette_holder/README.md).

Exports the pipette holder as three printable parts (one STL and 3MF each, in print orientation), a
multi-object kit 3MF for printing hosts, and an assembled STL/3MF used only for renders and the 3D viewer.
Reopens every file and writes pipette_holder/validation.json: mesh integrity, STL/3MF equivalence, B-rep
agreement and print checks per part (overhangs, floating layers, wall thickness, bed fit), joint fit, clearance
against the stand-in pipette envelope, static stability compared with the reference, and estimated material use.
"""
import hashlib, json, math, runpy, zipfile
from pathlib import Path
import cadquery as cq
import numpy as np
import trimesh
from shapely.geometry import MultiPoint, Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent
NAME = 'pipette_holder'
FOLDER = ROOT / NAME
REFERENCE = ROOT.parent / 'exaple_product' / 'mechanical-pipette-holder.stl'
PREVIOUS = ROOT / 'previous' / 'pipette_holder_v1' / 'validation.json'
OVERHANG_LIMIT_DEG = 45.0
TESSELLATION_TOLERANCE_DEG = 1.5            # designed 45-degree cones/vaults tessellate to <= 46.2
DENSITY = {'PLA': 1.24, 'PETG': 1.27}         # g/cm3
PIPETTE_MASS_G = 120.0                        # assumed mass of one manual single-channel pipette
PIPETTE_COM_BELOW_HOOK = 72.0                 # stand-in pipette mass centre below the finger hook


def export(shape, path, tolerance=0.03, angular=0.1):
    cq.exporters.export(shape, str(path.with_suffix('.stl')), tolerance=tolerance, angularTolerance=angular)
    mesh = trimesh.load(path.with_suffix('.stl'), force='mesh'); mesh.units = 'mm'
    path.with_suffix('.3mf').write_bytes(trimesh.exchange.threemf.export_3MF(trimesh.Scene(mesh)))
    return check_files(mesh, path)


def check_files(mesh, path, printable=True):
    reopened = trimesh.load(path.with_suffix('.3mf'), force='mesh')
    for m in (mesh, reopened):
        assert m.is_watertight and m.is_winding_consistent and m.is_volume, path.name
        # The display-only assembly may keep float32 zero-area slivers; printable parts may not.
        assert np.all(m.area_faces > 0) or not printable, path.name
    assert np.allclose(mesh.bounds, reopened.bounds, atol=1e-5)
    assert np.isclose(mesh.volume, reopened.volume, rtol=1e-7)
    return mesh, reopened


def overhangs(mesh, limit_deg):
    """Area of downward faces flatter than the limit (measured from vertical); bed contact excluded."""
    nz = mesh.face_normals[:, 2]
    low = mesh.triangles_center[:, 2] > mesh.bounds[0, 2] + 0.05
    worst = np.degrees(np.arcsin(np.clip(-nz[low], 0, 1))).max(initial=0)
    bad = low & (-nz > math.sin(math.radians(limit_deg)) + 1e-9)
    return float(mesh.area_faces[bad].sum()), float(worst), mesh.triangles_center[bad]


def floating_layers(mesh, layer=.2):
    heights = np.arange(layer / 2, mesh.extents[2], layer)
    previous, islands = None, []
    for height, section in zip(heights, mesh.section_multiplane([0, 0, 0], [0, 0, 1], heights)):
        if section is None:
            islands.append(float(height)); continue
        polygons = list(section.polygons_full); current = unary_union(polygons)
        if previous is not None:
            # 1e-4 mm2 also catches regions that start from a single point (a hanging apex)
            islands += [float(height) for p in polygons if p.area > 1e-4 and p.intersection(previous).area < 1e-9]
        previous = current
    return islands


def wall_thickness(mesh, samples=4000, seed=1):
    """Distance from sampled surface points to the opposite surface along the inward normal."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(mesh.faces), size=min(samples, len(mesh.faces)), replace=False, p=mesh.area_faces / mesh.area)
    origins = mesh.triangles_center[idx] - mesh.face_normals[idx] * 1e-3
    hits, rays, _ = mesh.ray.intersects_location(origins, -mesh.face_normals[idx], multiple_hits=False)
    d = np.linalg.norm(hits - origins[rays], axis=1)
    d = d[d > 1e-3]
    return d


def footprint(mesh, z=0.1):
    section = mesh.section([0, 0, 1], [0, 0, z])
    pts = np.vstack([e[:, :2] for e in section.discrete])
    return MultiPoint(pts).convex_hull, unary_union(list(section.to_2D()[0].polygons_full)).area


def tipping(hull, com_xy, com_z):
    """Smallest horizontal distance from the CoM projection to the footprint edge, and the static
    tilt angle before tipping over that edge."""
    p = Point(*com_xy)
    assert hull.contains(p)
    d = hull.exterior.distance(p)
    return d, math.degrees(math.atan2(d, com_z))


def brep_volume(solid, step=1.0):
    """B-rep volume by summing exact slab intersections. OCC's whole-solid GProp integration has been seen to
    misreport by ~3 % on fillets swept along splines, so the mesh is checked against this instead."""
    bb = solid.BoundingBox()
    total, z = 0.0, bb.zmin
    while z < bb.zmax:
        slab = cq.Solid.makeBox(bb.xlen + 2, bb.ylen + 2, step, cq.Vector(bb.xmin - 1, bb.ymin - 1, z))
        total += solid.intersect(slab).Volume()
        z += step
    return total


def material(volume_mm3, area_mm2, perimeter_mm=1.8, infill=.15):
    """Coarse unsliced estimate: 4 x 0.45 mm perimeters over the whole surface plus 15 % infill."""
    shell = min(volume_mm3, area_mm2 * perimeter_mm)
    printed = shell + infill * (volume_mm3 - shell)
    out = {}
    for name, rho in DENSITY.items():
        grams = printed / 1000 * rho
        out[name] = dict(grams=round(grams, 1), filament_m_1_75mm=round(printed / (math.pi * .875 ** 2) / 1000, 1))
    return dict(method='4 x 0.45 mm perimeters + 15 % gyroid-equivalent infill; not a slicer result',
                printed_volume_cm3=round(printed / 1000, 1), **out)


def volume(shape):
    return sum(s.Volume() for s in shape.solids().vals()) if shape.solids().vals() else 0.0


def assemble(meshes, seats):
    """Assembled holder for renders and the viewer only; hosts print the separate parts. Each part sinks
    0.05 mm into the one below so the joint faces fuse into one display solid."""
    placed = [meshes[name].copy().apply_translation((0, 0, z - 0.05 * i)) for i, (name, z) in enumerate(seats.items())]
    return trimesh.boolean.union(placed, engine='manifold')


def build():
    model = runpy.run_path(str(FOLDER / 'source/model.py'))
    P, F = model['PARAMETERS'], model['PIPETTE_FIT']
    seats, parts = model['seats'](), model['build_parts']()
    bed = np.array(P['bed'])
    report = {'product': NAME, 'source': f'{NAME}/source/model.py', 'units': 'mm', 'assumed_bed_mm': list(P['bed']),
              'print_orientation': 'each part upright as modelled, flat face on the bed, no supports intended',
              'parts': []}
    (FOLDER / 'parts').mkdir(exist_ok=True); (FOLDER / 'assembly').mkdir(exist_ok=True)
    kit = trimesh.Scene(); offset = 0.0; envelope = np.zeros(3); meshes = {}; totals = dict(volume=0.0, area=0.0)
    for name in model['PARTS']:
        shape = model['printable'](name, parts[name])
        solid = shape.val()
        assert len(shape.solids().vals()) == 1 and solid.isValid(), name
        mesh, reopened = export(shape, FOLDER / 'parts' / name)
        assert len(mesh.split()) == 1, name
        v_brep = brep_volume(solid)
        assert np.isclose(mesh.volume, v_brep, rtol=2e-3), (name, mesh.volume, v_brep)
        assert np.all(np.sort(mesh.extents) <= np.sort(bed)), (name, mesh.extents)
        area, worst, _ = overhangs(mesh, OVERHANG_LIMIT_DEG)
        area_tol, _, _ = overhangs(mesh, OVERHANG_LIMIT_DEG + TESSELLATION_TOLERANCE_DEG)
        area50, _, _ = overhangs(mesh, OVERHANG_LIMIT_DEG + 5)
        islands = floating_layers(mesh)
        assert not islands and area_tol < 1.0, (name, islands[:5], area_tol)
        walls = wall_thickness(mesh)
        _, contact = footprint(mesh)
        meshes[name] = mesh
        totals['volume'] += mesh.volume; totals['area'] += mesh.area
        envelope = np.maximum(envelope, np.sort(mesh.extents))
        kit.add_geometry(mesh.copy().apply_translation((offset - mesh.bounds[0, 0], -mesh.centroid[1], -mesh.bounds[0, 2])),
                         node_name=name, geom_name=name)
        offset += mesh.extents[0] + 10
        report['parts'].append(dict(
            part=name, file=f'parts/{name}.stl', sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                         for p in ((FOLDER / 'parts' / name).with_suffix(s) for s in ('.stl', '.3mf'))},
            dimensions_mm=[round(v, 3) for v in mesh.extents],
            volume_cm3=dict(brep_slab_integrated=round(v_brep / 1000, 3), stl=round(mesh.volume / 1000, 3), **{'3mf': round(reopened.volume / 1000, 3)}),
            surface_area_cm2=round(mesh.area / 100, 1), triangles=len(mesh.faces),
            mesh=dict(watertight=True, winding_consistent=True, is_volume=True, single_body=True, positive_triangle_areas=True,
                      euler_number=int(mesh.euler_number), brep_valid=bool(solid.isValid()), stl_3mf_equal=True),
            fits_bed=True, bed_contact_area_cm2=round(contact / 100, 1),
            overhang_area_over_limit_mm2=round(area, 2), overhang_area_over_limit_plus_tessellation_tolerance_mm2=round(area_tol, 2),
            overhang_area_over_50deg_mm2=round(area50, 2), steepest_downward_face_deg=round(worst, 1), floating_layers_0_2mm=0,
            wall_thickness_mm=dict(sampled_points=int(len(walls)), p01=round(float(np.percentile(walls, 1)), 2),
                                   p05=round(float(np.percentile(walls, 5)), 2), median=round(float(np.median(walls)), 2)),
            material_estimate=material(mesh.volume, mesh.area)))

    # Joints, checked on the exact B-rep in assembled position: the spigot core clears its socket, the crush ribs
    # are the only interference, and nothing else of neighbouring parts overlaps.
    j1, j2 = P['joint_z']
    joints = []
    for lower, upper, z in (('base', 'column', j1), ('column', 'head', j2)):
        core = volume(model['spigot'](z, ribs=False).intersect(parts[upper]))
        ribs = volume(model['spigot'](z).cut(model['spigot'](z, ribs=False)).intersect(parts[upper]))
        overlap = volume(parts[lower].intersect(parts[upper]))
        assert core < 1e-6 and ribs > 0 and abs(overlap - ribs) < 1e-3, (lower, upper, core, ribs, overlap)
        joints.append(dict(joint=f'{lower} -> {upper}', z_mm=z, spigot_core_clears_socket=True,
                           clearance_per_side_mm=P['joint_clearance'],
                           crush_rib_interference_mm=round(P['crush_rib'][1] - P['joint_clearance'], 2),
                           crush_rib_overlap_mm3=round(ribs, 3), other_overlap_mm3=round(overlap - ribs, 4),
                           engagement_mm=P['spigot_height'], orientations=P['positions']))
    assert volume(parts['base'].intersect(parts['head'])) < 1e-6
    report['joints'] = joints
    report['host_cad_dimensions_mm'] = [round(v, 3) for v in envelope]

    kit_path = FOLDER / f'{NAME}.3mf'
    kit_path.write_bytes(trimesh.exchange.threemf.export_3MF(kit))
    # Mirror backend/app/mesh.py limits so printing hosts can always download the kit.
    entries = zipfile.ZipFile(kit_path).infolist()
    assert all(e.file_size <= 20 * 1024 * 1024 for e in entries) and sum(e.file_size for e in entries) <= 40 * 1024 * 1024, 'kit exceeds CAD limits'
    assert sum(len(m.faces) for m in kit.geometry.values()) <= 400000, 'kit exceeds triangle limit'
    report['kit'] = dict(file=kit_path.name, objects=list(model['PARTS']), sha256=hashlib.sha256(kit_path.read_bytes()).hexdigest())

    assembly_path = FOLDER / 'assembly' / f'{NAME}_assembled'
    assembly = assemble(meshes, seats)
    assembly.export(assembly_path.with_suffix('.stl'))
    assembly = trimesh.load(assembly_path.with_suffix('.stl'), force='mesh')
    assembly_path.with_suffix('.3mf').write_bytes(trimesh.exchange.threemf.export_3MF(trimesh.Scene(assembly)))
    check_files(assembly, assembly_path, printable=False)
    report['assembled'] = dict(file=f'assembly/{NAME}_assembled.stl', bounding_box_mm=dict(
        min=[round(v, 3) for v in assembly.bounds[0]], max=[round(v, 3) for v in assembly.bounds[1]],
        size=[round(v, 3) for v in assembly.extents]), triangles=len(assembly.faces))
    # The printed stack: the display union above sinks each joint by 0.05 mm, the parts themselves do not.
    report['assembled_dimensions_mm'] = [round(v, 3) for v in assembly.extents[:2]] + [P['hook_z']]

    # Stand-in pipettes: never exported as the product; written for the review renders only.
    review = FOLDER / 'review'; review.mkdir(exist_ok=True)
    proxies = model['proxies']()
    cq.exporters.export(proxies, str(review / 'pipette_proxy.stl'), tolerance=.05, angularTolerance=.15)
    clash = sum(volume(parts[n].intersect(proxies)) for n in model['PARTS'])
    # Distances from the bare envelope to the holder, measured on the exact B-rep in assembled position.
    head, plinth = parts['head'].val(), model['plinth']().val()
    probe = lambda r, z, deg: cq.Vertex.makeVertex(r * math.cos(math.radians(deg)), r * math.sin(math.radians(deg)), z)
    d0 = model['stations']()[0]
    back = F['axis_r'] - F['body_r']
    cradle_gap = min(head.distance(probe(back, z, d0)) for z in np.linspace(P['collar_underside_z'] + 10, P['collar_top'] - 3, 9))
    crest_gap = head.distance(probe(P['nose_slot'][0] + 8, P['hook_z'], d0))
    lower_end = P['hook_z'] - F['below_hook']
    report['fit_checks_against_stand_in_pipette'] = dict(
        envelope_intersection_mm3=round(clash, 4),
        handle_back_to_cradle_mm=round(cradle_gap, 3),
        hook_underside_to_deck_mm=round(crest_gap, 3),
        lower_end_above_plinth_mm=round(plinth.distance(probe(F['axis_r'], lower_end, d0)), 3),
        fitted_tip_end_above_plinth_mm=round(plinth.distance(probe(F['axis_r'], lower_end - F['tip_drop'], d0)), 3),
        pipette_centre_spacing_mm=round(2 * F['axis_r'] * math.sin(math.pi / P['positions']), 1),
        free_gap_between_handles_mm=round(2 * F['axis_r'] * math.sin(math.pi / P['positions']) - 2 * F['body_r'], 1),
    )
    assert clash < 1e-3 and cradle_gap > 0.5 and crest_gap < 1e-3

    est = material(totals['volume'], totals['area'])
    hull, contact_area = footprint(assembly)
    com = sum(meshes[n].center_mass * meshes[n].volume + np.array([0, 0, seats[n] * meshes[n].volume]) for n in meshes) / totals['volume']
    m_holder = est['PLA']['grams']
    pip = [np.array([F['axis_r'] * math.cos(math.radians(d)), F['axis_r'] * math.sin(math.radians(d)),
                     P['hook_z'] - PIPETTE_COM_BELOW_HOOK]) for d in model['stations']()]
    def loaded(k):
        total = m_holder + k * PIPETTE_MASS_G
        c = (com * m_holder + sum(pip[:k], np.zeros(3)) * PIPETTE_MASS_G) / total
        d, ang = tipping(hull, c[:2], c[2])
        return dict(pipettes=k, mass_g=round(total), com_mm=[round(v, 1) for v in c], edge_distance_mm=round(d, 1),
                    tilt_to_tip_deg=round(ang, 1), side_push_to_tip_N=round(total / 1000 * 9.81 * d / P['hook_z'], 2))
    report['stability'] = dict(
        assumed_pipette_mass_g=PIPETTE_MASS_G, assumed_pipette_com_height_mm=P['hook_z'] - PIPETTE_COM_BELOW_HOOK,
        holder_com_mm=[round(v, 1) for v in com], footprint='convex hull of the bed contact (hexagonal plinth)',
        bed_contact_area_cm2=round(contact_area / 100, 1),
        centre_to_tipping_edge_mm=round(hull.exterior.distance(Point(0, 0)), 1),
        side_push_measured_at='canopy deck (hook_z)', cases=[loaded(k) for k in (0, 1, P['positions'])])
    report['material_estimate'] = dict(**est, solid_volume_cm3=round(totals['volume'] / 1000, 1),
                                       surface_area_cm2=round(totals['area'] / 100, 1))

    ref = trimesh.load(REFERENCE, force='mesh')
    ref_hull, _ = footprint(ref)
    ref_centre = np.array([124.89, 89.72])  # column centroid measured at z = 100 mm
    ref_edge = ref_hull.exterior.distance(Point(*ref_centre))
    # The reference mesh is open (7 shells), so its volume comes from 0.5 mm section integration.
    ref_volume = sum(sum(p.area for p in sec.polygons_full) * .5
                     for sec in ref.section_multiplane([0, 0, 0], [0, 0, 1], list(np.arange(.25, ref.extents[2], .5)))
                     if sec is not None)
    report['reference_comparison'] = dict(
        source='exaple_product/mechanical-pipette-holder.stl (unchanged)',
        sha256=hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
        size_mm=[round(v, 1) for v in ref.extents], positions=3, watertight=bool(ref.is_watertight),
        shells=len(ref.split(only_watertight=False)), volume_cm3_section_integrated=round(ref_volume / 1000, 1),
        pla_grams_same_estimate=material(ref_volume, ref.area)['PLA']['grams'], centre_to_tipping_edge_mm=round(ref_edge, 1))
    if PREVIOUS.exists():
        v1 = json.loads(PREVIOUS.read_text())
        report['previous_version'] = dict(
            source='previous/pipette_holder_v1 (single part)', size_mm=v1['bounding_box_mm']['size'],
            volume_cm3=v1['volume_cm3']['stl'], pla_grams_same_estimate=v1['material_estimate']['PLA']['grams'],
            stability_cases=v1['stability']['cases'])
    report['parameters'] = P
    report['pipette_fit_unverified'] = F
    (FOLDER / 'validation.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ('joints', 'host_cad_dimensions_mm', 'assembled', 'fit_checks_against_stand_in_pipette',
                                             'stability', 'material_estimate')}, indent=1))
    for p in report['parts']:
        print(p['part'], p['dimensions_mm'], p['volume_cm3']['stl'], 'cm3', 'steepest', p['steepest_downward_face_deg'],
              'over-limit', p['overhang_area_over_limit_mm2'], 'tol', p['overhang_area_over_limit_plus_tessellation_tolerance_mm2'],
              'walls', p['wall_thickness_mm'], p['material_estimate']['PLA']['grams'], 'g')


if __name__ == '__main__':
    build()
