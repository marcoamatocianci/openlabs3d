"""Run in the CadQuery environment (see dna_pipette_stand_6/README.md).

Exports and validates the DNA pipette stand: one STL and 3MF per printable part, a multi-object
kit 3MF for printing hosts, and an assembled STL used only for renders and the 3D viewer.
"""
import json, math, runpy
from pathlib import Path
import cadquery as cq
import numpy as np
import trimesh
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent
NAME = 'dna_pipette_stand_6'
FOLDER = ROOT / NAME


def export(mesh, path, printable=True):
    mesh.export(path.with_suffix('.stl'))
    mesh = trimesh.load(path.with_suffix('.stl'), force='mesh'); mesh.units = 'mm'
    path.with_suffix('.3mf').write_bytes(trimesh.exchange.threemf.export_3MF(trimesh.Scene(mesh)))
    reopened = trimesh.load(path.with_suffix('.3mf'), force='mesh')
    for m in (mesh, reopened):
        assert m.is_watertight and m.is_winding_consistent and m.is_volume, path.name
        # The display-only assembly may keep float32 zero-area slivers; printable parts may not.
        assert np.all(m.area_faces > 0) or not printable, path.name
    assert np.allclose(mesh.bounds, reopened.bounds, atol=1e-5)
    assert np.isclose(mesh.volume, reopened.volume, rtol=1e-7)
    return mesh


def overhangs(mesh, limit_deg):
    """Area of downward faces steeper than the limit, measured from vertical; bed contact excluded."""
    nz = mesh.face_normals[:, 2]
    low = mesh.triangles_center[:, 2] > mesh.bounds[0, 2] + 0.05
    worst = np.degrees(np.arcsin(np.clip(-nz[low], 0, 1))).max(initial=0)
    bad = low & (-nz > math.sin(math.radians(limit_deg)))
    return float(mesh.area_faces[bad].sum()), float(worst)


def floating_layers(mesh, layer=.2):
    heights = np.arange(layer / 2, mesh.extents[2], layer)
    previous, islands = None, []
    for height, section in zip(heights, mesh.section_multiplane([0, 0, 0], [0, 0, 1], heights)):
        if section is None:
            islands.append(float(height)); continue
        polygons = list(section.polygons_full); current = unary_union(polygons)
        if previous is not None:
            islands += [float(height) for p in polygons if p.area > .01 and p.intersection(previous).area < 1e-6]
        previous = current
    return islands


def build():
    model = runpy.run_path(str(FOLDER / 'source/model.py'))
    P, F, parts = model['PARAMETERS'], model['PIPETTE_FIT'], model['parts']
    meshes = model['part_meshes']()
    bed = np.array(P['bed'])
    report = {'product': NAME, 'assumed_bed_mm': list(P['bed']), 'pipette_fit_unverified': F, 'parts': []}
    kit = trimesh.Scene(); offset = 0.0; envelope = np.zeros(3)
    for name, shape in parts.items():
        solids = shape.solids().vals()
        assert len(solids) == 1 and shape.val().isValid(), name
        mesh = export(meshes[name], FOLDER / 'parts' / name)
        assert len(mesh.split()) == 1, name
        # Towers add the helix relief on top of the exact core volume.
        assert mesh.volume >= shape.val().Volume() * .997, name
        dims = np.sort(mesh.extents)
        assert np.all(dims <= np.sort(bed)), (name, mesh.extents)
        area, worst = overhangs(mesh, P['overhang_limit_deg'])
        # Only the 1 mm flat tips of the truncated socket cones may exceed the limit.
        assert area < 2.0, (name, area)
        islands = floating_layers(mesh)
        assert not islands, (name, islands[:5])
        envelope = np.maximum(envelope, dims)
        kit.add_geometry(mesh.copy().apply_translation((offset - mesh.bounds[0, 0], -mesh.centroid[1], -mesh.bounds[0, 2])), node_name=name, geom_name=name)
        offset += mesh.extents[0] + 10
        report['parts'].append(dict(part=name, dimensions_mm=[round(v, 3) for v in mesh.extents], volume_cm3=round(mesh.volume / 1000, 2),
                                    triangles=len(mesh.faces), single_solid=True, watertight=True, fits_bed=True, floating_layers=0,
                                    overhang_area_over_limit_mm2=round(area, 2), steepest_downward_face_deg=round(worst, 1)))
    # Joint and bearing clearances, checked on the exact B-rep geometry.
    lower, upper, crown, foot = parts['tower_lower'], parts['tower_upper'], parts['crown'], parts['foot']
    split = P['tower_height'] / 2; seat = P['foot_height'] + P['thrust_ring'][2]
    checks = {
        'spindle_clears_tower_bore': foot.intersect(lower.translate((0, 0, seat))).val().Volume() < 1e-6,
        'lower_spigot_clears_upper_socket': lower.intersect(upper.translate((0, 0, split))).val().Volume() < 1e-6,
        'upper_spigot_clears_crown_socket': upper.intersect(crown.translate((0, 0, split))).val().Volume() < 1e-6,
        'pipette_spacing_mm': round(2 * F['hang_radius'] * math.sin(math.pi / P['positions']), 1),
        'knob_drop_above_foot_mm': round(P['thrust_ring'][2] + P['tower_height'] + F['knob_height'], 1),
        'load_radius_inside_footprint': F['hang_radius'] + F['knob_length'] / 2 < P['foot_diameter'] / 2,
    }
    assert all(v for k, v in checks.items() if isinstance(v, bool)), checks
    report['checks'] = checks
    report['host_cad_dimensions_mm'] = [round(v, 3) for v in envelope]
    kit_path = FOLDER / (NAME + '.3mf')
    kit_path.write_bytes(trimesh.exchange.threemf.export_3MF(kit))
    # Mirror backend/app/mesh.py limits so printing hosts can always download the kit.
    import zipfile
    entries = zipfile.ZipFile(kit_path).infolist()
    assert all(e.file_size <= 20 * 1024 * 1024 for e in entries) and sum(e.file_size for e in entries) <= 40 * 1024 * 1024, 'kit exceeds CAD limits'
    assert sum(len(m.faces) for m in kit.geometry.values()) <= 400000, 'kit exceeds triangle limit'
    assembly = export(model['assemble'](meshes), FOLDER / 'assembly' / (NAME + '_assembled'), printable=False)
    report['assembled_dimensions_mm'] = [round(v, 3) for v in assembly.extents]
    report['assembled_triangles'] = len(assembly.faces)
    (FOLDER / 'validation.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    for d in ('parts', 'assembly'): (FOLDER / d).mkdir(parents=True, exist_ok=True)
    build()
