"""Run in the CadQuery environment (see pipette_holder/README.md).

Exports the pipette holder (one printable part) to STL and 3MF, reopens both, and writes
pipette_holder/validation.json: mesh integrity, STL/3MF equivalence, B-rep agreement, print checks
(overhangs, floating layers, wall thickness, bed fit), clearance against the stand-in pipette envelope,
static stability compared with the reference, and an estimated material use.
"""
import hashlib, json, math, runpy
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
SMALLEST_COMMON_BED = (250.0, 210.0, 220.0)  # Prusa MK4S, the smallest FDM volume in the seeded catalogue
                                              # apart from the 180 mm cube class
OVERHANG_LIMIT_DEG = 45.0
TESSELLATION_TOLERANCE_DEG = 1.5            # designed 45-degree cones/vaults tessellate to <= 46.2
DENSITY = {'PLA': 1.24, 'PETG': 1.27}         # g/cm3
PIPETTE_MASS_G = 120.0                        # assumed mass of one manual single-channel pipette


def export(shape, path, tolerance=0.03, angular=0.1):
    cq.exporters.export(shape, str(path.with_suffix('.stl')), tolerance=tolerance, angularTolerance=angular)
    mesh = trimesh.load(path.with_suffix('.stl'), force='mesh'); mesh.units = 'mm'
    path.with_suffix('.3mf').write_bytes(trimesh.exchange.threemf.export_3MF(trimesh.Scene(mesh)))
    reopened = trimesh.load(path.with_suffix('.3mf'), force='mesh')
    for m in (mesh, reopened):
        assert m.is_watertight and m.is_winding_consistent and m.is_volume, path.name
        assert np.all(m.area_faces > 0), path.name
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


def build():
    model = runpy.run_path(str(FOLDER / 'source/model.py'))
    P, F = model['PARAMETERS'], model['PIPETTE_FIT']
    shape = model['build']()
    solid = shape.val()
    assert len(shape.solids().vals()) == 1 and solid.isValid()
    mesh, reopened = export(shape, FOLDER / NAME)
    assert len(mesh.split()) == 1
    v_brep = brep_volume(solid)
    assert np.isclose(mesh.volume, v_brep, rtol=2e-3), (mesh.volume, v_brep)

    # Stand-in pipettes: never exported as the product; written for the review renders only.
    review = FOLDER / 'review'; review.mkdir(exist_ok=True)
    proxies = model['proxies']()
    cq.exporters.export(proxies, str(review / 'pipette_proxy.stl'), tolerance=.05, angularTolerance=.15)
    clash = shape.intersect(proxies).val().Volume() if shape.intersect(proxies).vals() else 0.0
    # Distances from the bare envelope to the holder, measured on the exact B-rep.
    probe = lambda r, z, deg: cq.Vertex.makeVertex(r * math.cos(math.radians(deg)), r * math.sin(math.radians(deg)), z)
    d0 = model['stations']()[0]
    back = F['axis_r'] - F['body_r']
    cradle_z = (P['collar_underside_z'] + 10, P['collar_top'] - 3)
    cradle_gap = min(solid.distance(probe(back, z, d0)) for z in np.linspace(*cradle_z, 9))
    crest_gap = solid.distance(probe(P['nose_slot'][0] + 8, P['hook_z'], d0))
    tip_end_z = P['hook_z'] - F['below_hook']
    tip_gap = solid.distance(probe(F['axis_r'], tip_end_z, d0))

    bed = np.array(SMALLEST_COMMON_BED)
    area, worst, _ = overhangs(mesh, OVERHANG_LIMIT_DEG)
    area_tol, _, _ = overhangs(mesh, OVERHANG_LIMIT_DEG + TESSELLATION_TOLERANCE_DEG)
    area50, _, _ = overhangs(mesh, OVERHANG_LIMIT_DEG + 5)
    islands = floating_layers(mesh)
    walls = wall_thickness(mesh)

    hull, contact_area = footprint(mesh)
    com = mesh.center_mass
    est = material(mesh.volume, mesh.area)
    m_holder = est['PLA']['grams']
    pip = [np.array([F['axis_r'] * math.cos(math.radians(d)), F['axis_r'] * math.sin(math.radians(d)), 140.0])
           for d in model['stations']()]
    def loaded(k):
        total = m_holder + k * PIPETTE_MASS_G
        c = (com * m_holder + sum(pip[:k], np.zeros(3)) * PIPETTE_MASS_G) / total
        d, ang = tipping(hull, c[:2], c[2])
        return dict(pipettes=k, mass_g=round(total), com_mm=[round(v, 1) for v in c], edge_distance_mm=round(d, 1),
                    tilt_to_tip_deg=round(ang, 1), side_push_to_tip_N=round(total / 1000 * 9.81 * d / P['hook_z'], 2))

    ref = trimesh.load(REFERENCE, force='mesh')
    ref_hull, _ = footprint(ref)
    ref_centre = np.array([124.89, 89.72])  # column centroid measured at z = 100 mm
    ref_edge = ref_hull.exterior.distance(Point(*ref_centre))
    # The reference mesh is open (7 shells), so its volume comes from 0.5 mm section integration.
    ref_volume = sum(sum(p.area for p in sec.polygons_full) * .5
                     for sec in ref.section_multiplane([0, 0, 0], [0, 0, 1], list(np.arange(.25, ref.extents[2], .5)))
                     if sec is not None)
    ref_material = material(ref_volume, ref.area)

    report = {
        'product': NAME,
        'source': 'pipette_holder/source/model.py',
        'units': 'mm',
        'print_orientation': 'upright as modelled, ring and fins on the bed, no supports intended',
        'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (FOLDER / f'{NAME}.stl', FOLDER / f'{NAME}.3mf')},
        'bounding_box_mm': {'min': [round(v, 3) for v in mesh.bounds[0]], 'max': [round(v, 3) for v in mesh.bounds[1]],
                            'size': [round(v, 3) for v in mesh.extents]},
        'volume_cm3': {'brep_slab_integrated': round(v_brep / 1000, 3), 'stl': round(mesh.volume / 1000, 3),
                       '3mf': round(reopened.volume / 1000, 3)},
        'surface_area_cm2': round(mesh.area / 100, 1),
        'triangles': len(mesh.faces),
        'mesh': dict(watertight=True, winding_consistent=True, is_volume=True, single_body=True,
                     positive_triangle_areas=True, euler_number=int(mesh.euler_number),
                     brep_valid=bool(solid.isValid()), stl_3mf_bounds_equal=True, stl_3mf_volume_equal=True),
        'printability': dict(
            fits_bed=bool(np.all(np.sort(mesh.extents) <= np.sort(bed))), reference_bed_mm=list(SMALLEST_COMMON_BED),
            bed_contact_area_cm2=round(contact_area / 100, 1),
            overhang_limit_deg_from_vertical=OVERHANG_LIMIT_DEG,
            overhang_area_over_limit_mm2=round(area, 2),
            overhang_area_over_limit_plus_tessellation_tolerance_mm2=round(area_tol, 2),
            overhang_area_over_50deg_mm2=round(area50, 2),
            steepest_downward_face_deg=round(worst, 1),
            floating_layers_0_2mm=len(islands),
            wall_thickness_mm=dict(sampled_points=int(len(walls)), p01=round(float(np.percentile(walls, 1)), 2),
                                   p05=round(float(np.percentile(walls, 5)), 2), median=round(float(np.median(walls)), 2),
                                   collar_wall=P['collar_wall'], web=P['web_thickness'],
                                   plinth=P['plinth_height'], canopy_rim=round(P['hook_z'] - P['canopy_underside_z'] -
                                   (P['canopy_apothem'] - P['mast_apothem'] + 1) * math.tan(math.radians(P['underside_deg'])), 1),
                                   note='low percentiles sample the feather edges where 48-degree undersides meet vertical walls'),
        ),
        'fit_checks_against_stand_in_pipette': dict(
            envelope_intersection_mm3=round(clash, 4),
            handle_back_to_cradle_mm=round(cradle_gap, 3),
            hook_underside_to_deck_mm=round(crest_gap, 3),
            lower_end_to_tip_pad_mm=round(tip_gap, 3),
            pipette_centre_spacing_mm=round(2 * F['axis_r'] * math.sin(math.pi / P['positions']), 1),
            free_gap_between_handles_mm=round(2 * F['axis_r'] * math.sin(math.pi / P['positions']) - 2 * F['body_r'], 1),
        ),
        'stability': dict(
            assumed_pipette_mass_g=PIPETTE_MASS_G, assumed_pipette_com_height_mm=140.0,
            holder_com_mm=[round(v, 1) for v in com],
            footprint='convex hull of the bed contact (hexagonal plinth)',
            centre_to_tipping_edge_mm=round(hull.exterior.distance(Point(0, 0)), 1),
            reference_centre_to_tipping_edge_mm=round(ref_edge, 1),
            cases=[loaded(k) for k in (0, 1, P['positions'])],
        ),
        'material_estimate': est,
        'reference_comparison': dict(
            source='exaple_product/mechanical-pipette-holder.stl (unchanged)',
            sha256=hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
            size_mm=[round(v, 1) for v in ref.extents], positions=3,
            watertight=bool(ref.is_watertight), shells=len(ref.split(only_watertight=False)),
            volume_cm3_section_integrated=round(ref_volume / 1000, 1),
            pla_grams_same_estimate=ref_material['PLA']['grams'],
            centre_to_tipping_edge_mm=round(ref_edge, 1),
            this_design=dict(size_mm=[round(v, 1) for v in mesh.extents], volume_cm3=round(mesh.volume / 1000, 1),
                             pla_grams_same_estimate=est['PLA']['grams'],
                             centre_to_tipping_edge_mm=round(hull.exterior.distance(Point(0, 0)), 1)),
        ),
        'parameters': P,
        'pipette_fit_unverified': F,
    }
    assert report['printability']['fits_bed'] and not islands and clash < 1e-3 and area_tol < 1.0
    (FOLDER / 'validation.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ('bounding_box_mm', 'volume_cm3', 'printability',
                                             'fit_checks_against_stand_in_pipette', 'stability', 'material_estimate')}, indent=1))


if __name__ == '__main__':
    build()
