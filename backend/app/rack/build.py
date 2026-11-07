"""python -m app.rack.build SPEC.json OUTPUT_DIR  (worker only, in a subprocess with CPU and memory limits)

Makes the solid, checks it, and only then writes files. Anything that fails a geometry check is an error and no file
is exported. The report keeps three kinds of statement apart: geometry that was checked automatically, manufacturing
feasibility that is estimated, and what only a test print can show.
"""
import argparse, ctypes, gc, json, math, sys, time
from pathlib import Path
import numpy as np
from . import export, geometry
from .rules import RULES
from ..mesh import MAX_TRIANGLES, analyze, load_mesh

FINE, FINE_ANGLE = .03, .25
COARSE, COARSE_ANGLE = .15, .42
# A soft Premium body is meshed to an absolute tolerance: the preview within 0.05 mm of the solid, the files within 0.03 mm.
SOFT_ANGLE, SOFT_PREVIEW = .5, .05
BOUNDS_TOLERANCE_MM = .05

class ValidationFailed(ValueError):
    def __init__(self, checks): super().__init__('; '.join(c['message'] for c in checks if c['status'] == 'fail')); self.checks = checks

def _check(checks, code, passed, message): checks.append({'code': code, 'status': 'pass' if passed else 'fail', 'message': message})

class Sections:
    """Is a point inside the exported mesh? Cuts the mesh at a height and counts crossings of a ray in that plane.
    The probes below use this rather than the CAD kernel's classifier: they test the very mesh being shipped, and a
    large rack's few thousand points take a fraction of a second instead of about a minute."""
    def __init__(self, vertices, faces):
        self.triangles, self.cache = vertices[faces], {}
    def _segments(self, z):
        key = round(z, 3)
        if key not in self.cache:
            t = self.triangles[(self.triangles[:, :, 2].min(axis=1) < key) & (self.triangles[:, :, 2].max(axis=1) > key)]
            ends = []
            for i, j in ((0, 1), (1, 2), (2, 0)):
                a, b = t[:, i], t[:, j]
                crossing = (a[:, 2] < key) != (b[:, 2] < key)
                w = (key - a[crossing, 2]) / (b[crossing, 2] - a[crossing, 2])
                ends.append((np.nonzero(crossing)[0], a[crossing, :2] + (b[crossing, :2] - a[crossing, :2]) * w[:, None]))
            order, points = np.concatenate([e[0] for e in ends]), np.concatenate([e[1] for e in ends])
            points = points[np.argsort(order, kind='stable')]
            self.cache[key] = points.reshape(-1, 2, 2)
        return self.cache[key]
    def inside(self, points, z):
        """For (n, 2) points at height z: True where inside the solid. An odd number of crossings to the right."""
        s = self._segments(z + 1.3e-4)     # just off any flat face or vertex
        p = np.asarray(points, dtype=float) + [0, 1.7e-5]
        y0, y1, x0, x1 = s[:, 0, 1], s[:, 1, 1], s[:, 0, 0], s[:, 1, 0]
        spans = (y0[None, :] > p[:, 1, None]) != (y1[None, :] > p[:, 1, None])
        with np.errstate(divide='ignore', invalid='ignore'):
            at = x0[None, :] + (p[:, 1, None] - y0[None, :]) / (y1 - y0)[None, :] * (x1 - x0)[None, :]
        return ((spans & (at > p[:, 0, None])).sum(axis=1) % 2) == 1

def _ring(x, y, radius, count):
    angles = np.arange(count) * 2 * math.pi / count + .13     # off the facets' own vertices
    return np.stack([x + radius * np.cos(angles), y + radius * np.sin(angles)], axis=1)

def _probe_tubes(sections, spec, checks):
    """Open where a tube goes, solid where a seat must be, measured on the mesh being shipped, not on the plan."""
    blocked, floorless, walls = [], [], []
    for n, t in enumerate(spec['tubes']):
        r, deck, floor = t['bore_d'] / 2, t['deck'], t['floor']
        # Probe heights stay clear of the ring where a lead-in ends: a slice along a ring of mesh vertices cannot be counted reliably.
        clear = lambda z: z - .37 if abs(z - (deck - t.get('lead', 0))) < .05 else z
        middle = (floor + t['cone'] + deck) / 2 if t['seat'] == 'tapered' else (floor + deck) / 2
        # Facets sit inside the true circle by up to the mesh tolerance, so clearance is probed that far in.
        if sections.inside([[t['x'], t['y']]], middle).any() or sections.inside(_ring(t['x'], t['y'], r - FINE - .02, 12), clear(deck - 1.5)).any(): blocked.append(n + 1)
        if not sections.inside(_ring(t['x'], t['y'], t['drain_d'] / 2 + .4, 6), .5).any(): floorless.append(n + 1)
        if not sections.inside(_ring(t['x'], t['y'], r + .5, 8), clear(deck - 2)).all() and (spec['style'] == 'premium' or spec.get('geometry_version', 1) >= 3): walls.append(n + 1)
    _check(checks, 'tube_cavities', not blocked, f'All {len(spec["tubes"])} tube cavities are clear to their full diameter.' if not blocked else f'Material blocks tube positions {blocked[:8]}.')
    _check(checks, 'tube_seats', not floorless, 'Every position has a seat under the tube.' if not floorless else f'No seat found under positions {floorless[:8]}.')
    if spec['style'] == 'premium' or spec.get('geometry_version', 1) >= 3:
        _check(checks, 'tube_walls', not walls, 'Every position has a wall at its deck.' if not walls else f'No wall found around positions {walls[:8]}.')

def _probe_label(solid, spec, checks, volume_without):
    label = spec.get('label')
    if not label: return
    changed = abs(solid.Volume() - volume_without) > 1e-3
    expected = 'recessed' if label['style'] == 'engraved' else 'raised'
    _check(checks, 'label_geometry', changed, f'The label "{label["text"]}" is {expected} in the solid.' if changed else 'The label did not change the solid.')

def validate(solid, mesh_report, spec, vertices, faces, volume_without_label=None):
    """Hard geometry checks on the meshed solid. Raises ValidationFailed when any fails. The kernel's own validity
    check runs in geometry.build(), before meshing: once a triangulation is attached it can report false on a sound
    solid, and the mesh gets its own independent checks here."""
    checks = []
    _check(checks, 'single_solid', len(solid.Solids()) == 1, 'One connected CAD solid.')
    _check(checks, 'solid_valid', True, 'The solid passed the CAD kernel\'s validity check when it was made.')
    _check(checks, 'positive_volume', solid.Volume() > 0, f'Positive volume ({solid.Volume() / 1000:.1f} cm³).')
    _check(checks, 'watertight', mesh_report['watertight'], 'The exported mesh is watertight.' if mesh_report['watertight'] else f'{mesh_report["boundary_edges"]} open and {mesh_report["non_manifold_edges"]} non-manifold edges.')
    _check(checks, 'normals', mesh_report['winding_consistent'] and not mesh_report['inverted_normals'], 'Surface normals are consistent and point outward.')
    _check(checks, 'one_body', mesh_report['components'] == 1, f'The mesh is one body ({mesh_report["components"]} found).')
    measured, planned = mesh_report['dimensions_mm'], spec['dims']
    _check(checks, 'dimensions', all(abs(a - b) <= BOUNDS_TOLERANCE_MM + (spec['label']['depth'] if spec.get('label') and spec['label']['style'] == 'embossed' else 0) for a, b in zip(measured, planned)), f'Measured {measured[0]:.1f} × {measured[1]:.1f} × {measured[2]:.1f} mm against {planned[0]:.1f} × {planned[1]:.1f} × {planned[2]:.1f} mm planned.')
    _check(checks, 'sits_flat', abs(mesh_report['bounds_mm']['min'][2]) < 1e-3, 'The base lies on the build plate.')
    _probe_tubes(Sections(vertices, faces), spec, checks)
    if volume_without_label is not None: _probe_label(solid, spec, checks, volume_without_label)
    if any(c['status'] == 'fail' for c in checks): raise ValidationFailed(checks)
    return checks

def manufacturing(mesh_report, spec, notes):
    """Estimates against FDM design rules. A warning here does not stop a build; a test print decides."""
    findings = [{'code': 'orientation', 'status': 'estimate', 'message': 'Designed to print upright, base on the bed, without support: walls lean less than the printable limit, window roofs are steeper than it, and bridges are short.' + (' Engraved or raised letters on a Premium side leave ledges of under 1 mm, which an automatic support setting will fill; leave it off and check the first print.' if spec.get('label') and spec['label'].get('flat') else '')}]
    ratio = mesh_report['overhang_area_ratio']
    findings.append({'code': 'overhangs', 'status': 'estimate' if ratio < .02 else 'warning', 'message': f'{ratio:.1%} of the surface faces downward steeper than {RULES.self_support_deg:.0f}°.'})
    if notes: findings.append({'code': 'edge_treatment', 'status': 'warning', 'message': 'Some edge treatments used a simpler form: ' + ', '.join(notes) + '.'})
    return findings

PHYSICAL = ['Tube fit in the printed bores: filament, nozzle and shrinkage all change the real diameter.',
            'Strength and stiffness of the printed rack, loaded with full tubes.',
            'Layer adhesion and print success on a particular printer and material.',
            'Cleaning, chemical and temperature resistance. Sterility and autoclaving are not claimed.']

def _release_memory():
    """Hand back what the booleans used before meshing starts: measured 16% off the peak of the largest racks."""
    gc.collect()
    try: ctypes.CDLL('libc.so.6').malloc_trim(0)
    except OSError: pass

def run(spec, output):
    """Generate, validate and write. Returns the result stored with the build."""
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    solid, notes, volume_before_label = geometry.build(spec)
    build_seconds = round(time.perf_counter() - started, 2)
    _release_memory()
    # The preview mesh is coarser than the manufacturing one. Coarse first: OpenCASCADE refines a mesh in place but will not
    # coarsen it. A stored design of the earlier generation was planar facets, which a coarse mesh barely simplified.
    planar = spec['style'] == 'lightweight' and spec.get('geometry_version', 1) <= 2
    curved = spec.get('geometry_version', 1) >= 3      # both current families are true curves; the mesh of a stored earlier design stays as it was
    angle = SOFT_ANGLE if curved else FINE_ANGLE
    def meshes(shape):
        n_preview = None
        if curved: v_preview, f_preview, n_preview = geometry.surface_mesh(shape, SOFT_PREVIEW, SOFT_ANGLE)
        else: v_preview, f_preview = (None, None) if planar else export.triangles_of(shape, COARSE, COARSE_ANGLE)
        if curved: geometry.mesh_absolute(shape, FINE, angle)
        v, f = export.triangles_of(shape, FINE, angle)
        if v_preview is None: v_preview, f_preview = v, f
        if len(f) > MAX_TRIANGLES: raise geometry.GeometryError(f'The mesh has {len(f)} triangles, over the {MAX_TRIANGLES} limit')
        stl = export.stl_bytes(v, f)
        return v_preview, f_preview, n_preview, v, f, stl, analyze(load_mesh(stl, '.stl'))
    v_preview, f_preview, n_preview, v, f, stl, report = meshes(solid)
    if not report['watertight'] and curved and len(spec['terraces']) > 1:
        # The mesher occasionally cannot close a blend. A plain junction is as sound and prints as well: never refuse a rack for it.
        solid, notes, volume_before_label = geometry.build(spec, blend=False)
        if 'terrace blend skipped' not in notes: notes.append('terrace blend skipped')
        _release_memory()
        v_preview, f_preview, n_preview, v, f, stl, report = meshes(solid)
    checks = validate(solid, report, spec, v, f, volume_before_label)
    threemf = export.threemf_bytes(v, f)
    # The 3MF is the same geometry, read back through the same untrusted-file parser hosts' uploads use.
    threemf_report = analyze(load_mesh(threemf, '.3mf'))
    same = threemf_report['watertight'] and threemf_report['components'] == 1 and all(abs(a - b) < .01 for a, b in zip(threemf_report['dimensions_mm'], report['dimensions_mm']))
    if not same: raise ValidationFailed([{'code': 'threemf', 'status': 'fail', 'message': 'The 3MF export does not match the STL'}])
    checks.append({'code': 'exports_match', 'status': 'pass', 'message': 'STL and 3MF exports describe the same closed body.'})
    still = export.render_still(v_preview, f_preview, 1200, 1)
    files = {'rack.stl': stl, 'rack.3mf': threemf, 'preview.glb': export.glb_bytes(v_preview, f_preview, n_preview),
             'render.webp': export.webp_bytes(still, lossless=True, method=4), 'thumb.webp': export.webp_bytes(still.resize((640, 640)), quality=88, method=4)}
    for name, data in files.items():
        partial = output / f'.{name}.part'
        partial.write_bytes(data); partial.replace(output / name)
    volume, area = float(solid.Volume()), float(solid.Area())
    return {'metrics': {'volume_mm3': round(volume), 'area_mm2': round(area), 'dims_mm': report['dimensions_mm'], 'triangles': report['triangles'], 'preview_triangles': int(len(f_preview)),
                        'degenerate_faces': report['degenerate_faces'], 'overhang_area_ratio': report['overhang_area_ratio'], 'holes': len(spec['tubes']), 'build_seconds': build_seconds, 'total_seconds': round(time.perf_counter() - started, 2)},
            'report': {'geometry_checked': checks, 'manufacturing_estimated': manufacturing(report, spec, notes), 'requires_physical_test': PHYSICAL},
            'analysis': report, 'notes': notes, 'files': {name: len(data) for name, data in files.items()}}

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('spec'); parser.add_argument('output')
    args = parser.parse_args(argv)
    spec = json.loads(Path(args.spec).read_text())
    try:
        result = run(spec, args.output)
    except (ValidationFailed, geometry.GeometryError) as exc:
        print(json.dumps({'error': str(exc), 'checks': getattr(exc, 'checks', [])})); return 3
    (Path(args.output) / 'result.json').write_text(json.dumps(result, separators=(',', ':')))
    return 0

if __name__ == '__main__':
    sys.exit(main())
