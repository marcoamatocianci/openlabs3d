"""Bounded STL/3MF parsing and geometry analysis with numpy; never a printability certificate.

load_mesh() is the only reader of untrusted CAD bytes. It checks the content against the extension (a ZIP is
never read as STL, and an STL never as 3MF), caps triangles, archive members, sizes and compression ratios,
refuses XML declarations and entities, and returns millimetre build coordinates with 3MF units, component and
build-item transforms applied. analyze() measures the welded mesh. Blender is never needed for either.
"""
import io, math, re, struct, zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
import numpy as np

MAX_TRIANGLES = 400_000
MAX_ASCII_VERTICES = 1_200_000
NS = {'m': 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
UNITS = {'micron': .001, 'millimeter': 1, 'centimeter': 10, 'inch': 25.4, 'foot': 304.8, 'meter': 1000}
# Binary STL record: normal, three vertices, attribute byte count.
STL_RECORD = np.dtype([('normal', '<f4', 3), ('v', '<f4', (3, 3)), ('attr', '<u2')])
# Vertices closer than this are one vertex (as the renderer's weld): exports repeat shared corners per triangle.
WELD_MM = 1e-4
ANALYSIS_VERSION = 1

@dataclass
class Mesh:
    format: str                  # 'stl' or '3mf', from the content
    triangles: np.ndarray        # (n, 3, 3) float64 millimetres
    unit: str                    # the 3MF unit, or 'millimeter (assumed)' for STL
    parts: list = field(default_factory=list)   # 3MF build items: [{'object_id', 'name', 'triangles'}]

    @property
    def dimensions(self):
        flat = self.triangles.reshape(-1, 3)
        return [round(float(v), 4) for v in flat.max(0) - flat.min(0)]

def _stl(data):
    count = struct.unpack_from('<I', data, 80)[0] if len(data) >= 84 else 0
    if count and len(data) == 84 + count * 50:
        if count > MAX_TRIANGLES: raise ValueError('Too many triangles')
        return np.frombuffer(data, STL_RECORD, count, 84)['v'].astype(np.float64)
    text = data.decode('ascii')
    if not text.strip().startswith('solid') or 'endsolid' not in text: raise ValueError('Invalid STL')
    vertices = re.findall(r'\bvertex\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)', text)
    if not vertices or len(vertices) % 3 or len(vertices) > MAX_ASCII_VERTICES: raise ValueError('Invalid STL triangles')
    return np.array(vertices, dtype=np.float64).reshape(-1, 3, 3)

def _transform(value):
    if not value: return None
    matrix = [float(v) for v in value.split()]
    if len(matrix) != 12 or not all(math.isfinite(v) for v in matrix): raise ValueError('Invalid transform')
    # 3MF row vectors: p' = p · M + t, with M the first nine values row by row.
    return np.array(matrix[:9]).reshape(3, 3), np.array(matrix[9:])

def _apply(triangles, transform):
    if transform is None: return triangles
    matrix, offset = transform
    return triangles @ matrix + offset

def _3mf(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 100 or sum(e.file_size for e in entries) > 40 * 1024 * 1024: raise ValueError('3MF archive exceeds limits')
        names = set()
        for e in entries:
            p = PurePosixPath(e.filename)
            if (p.is_absolute() or '..' in p.parts or '\\' in e.filename or e.filename in names or e.flag_bits & 1
                    or e.file_size > 20 * 1024 * 1024 or e.file_size / max(1, e.compress_size) > 200):
                raise ValueError('Unsafe 3MF archive')
            names.add(e.filename)
        paths = [e.filename for e in entries if e.filename.lower().endswith('.model')]
        if len(paths) != 1: raise ValueError('Only single-model 3MF files are supported')
        # zipfile stops at the declared size and checks the CRC, so a lying header cannot inflate further.
        xml = archive.read(paths[0])
    if b'<!' in xml: raise ValueError('XML declarations and entities are prohibited')
    root = ET.fromstring(xml)
    unit = root.get('unit', 'millimeter')
    scale = UNITS.get(unit)
    if scale is None: raise ValueError('Unknown model units')
    objects = {o.attrib['id']: o for o in root.findall('m:resources/m:object', NS)}
    total = [0]
    def grow(n):
        total[0] += n
        if total[0] > MAX_TRIANGLES: raise ValueError('Too many triangles')
    def expand(identifier, trail=()):
        if identifier in trail or len(trail) > 16: raise ValueError('Recursive 3MF component')
        obj = objects[identifier]; result = []
        for mesh in obj.findall('m:mesh', NS):
            vertices = np.array([[v.attrib['x'], v.attrib['y'], v.attrib['z']] for v in mesh.findall('m:vertices/m:vertex', NS)], dtype=np.float64).reshape(-1, 3)
            ids = np.array([[t.attrib['v1'], t.attrib['v2'], t.attrib['v3']] for t in mesh.findall('m:triangles/m:triangle', NS)], dtype=np.int64).reshape(-1, 3)
            if ids.size and (ids.min() < 0 or ids.max() >= len(vertices)): raise ValueError('Invalid triangle index')
            grow(len(ids)); result.append(vertices[ids])
        for component in obj.findall('m:components/m:component', NS):
            child = expand(component.attrib['objectid'], trail + (identifier,))
            grow(len(child)); result.append(_apply(child, _transform(component.get('transform'))))
        return np.concatenate(result) if result else np.empty((0, 3, 3))
    triangles, parts = [], []
    for item in root.findall('m:build/m:item', NS):
        identifier = item.attrib['objectid']
        placed = _apply(expand(identifier), _transform(item.get('transform'))) * scale
        triangles.append(placed)
        parts.append({'object_id': identifier, 'name': (objects[identifier].get('name') or f'Object {identifier}')[:120], 'triangles': len(placed)})
    if total[0] > MAX_TRIANGLES: raise ValueError('Too many triangles')
    return (np.concatenate(triangles) if triangles else np.empty((0, 3, 3))), unit, parts

def load_mesh(data, ext):
    """Parse untrusted bytes. Raises ValueError (or zipfile/XML/struct/Unicode/Key/Index errors) when invalid."""
    is_zip = data[:4] == b'PK\x03\x04'
    if ext == '.stl':
        if is_zip: raise ValueError('This file is a ZIP archive, not an STL')
        triangles, fmt, unit, parts = _stl(data), 'stl', 'millimeter (assumed)', []
    elif ext == '.3mf':
        if not is_zip: raise ValueError('A 3MF file must be a ZIP archive')
        (triangles, unit, parts), fmt = _3mf(data), '3mf'
    else: raise ValueError('Upload STL or 3MF')
    if not len(triangles): raise ValueError('No mesh triangles')
    if not np.isfinite(triangles).all() or np.abs(triangles).max() > 1e7: raise ValueError('Invalid mesh coordinates')
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    mesh = Mesh(fmt, triangles, unit, parts)
    if not (np.abs(cross) > 1e-12).any() or any(d <= 0 for d in mesh.dimensions): raise ValueError('Degenerate or flat geometry')
    return mesh

def inspect_mesh(data, ext, include_triangles=False):
    """Dimensions in millimetres (and the (n, 3, 3) triangle array when asked)."""
    mesh = load_mesh(data, ext)
    return (mesh.dimensions, mesh.triangles) if include_triangles else mesh.dimensions

def _components(faces, vertex_count):
    """Connected bodies, by label propagation over shared vertices with pointer jumping."""
    if not len(faces): return 0
    labels = np.arange(vertex_count)
    for _ in range(10_000):
        lowest = labels[faces].min(axis=1)
        updated = labels.copy()
        np.minimum.at(updated, faces.ravel(), np.repeat(lowest, 3))
        updated = updated[updated]
        if np.array_equal(updated, labels): break
        labels = updated
    return len(np.unique(labels[np.unique(faces)]))

def analyze(mesh):
    """Geometry facts and findings for one mesh. Findings separate definitive defects ('error'), heuristics
    ('warning'), neutral facts ('info'); none of them predicts whether a print will succeed."""
    t = mesh.triangles
    flat = t.reshape(-1, 3)
    lower, upper = flat.min(0), flat.max(0)
    dims = upper - lower
    cross = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    doubled = np.linalg.norm(cross, axis=1)
    degenerate = doubled <= 1e-10
    keys = np.round(flat / WELD_MM).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    vertex_count = int(inverse.max()) + 1
    faces = inverse.reshape(-1, 3)
    collapsed = (faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2]) | (faces[:, 0] == faces[:, 2])
    good = faces[~(collapsed | degenerate)]
    directed = np.concatenate([good[:, [0, 1]], good[:, [1, 2]], good[:, [2, 0]]])
    undirected = np.sort(directed, axis=1)
    edge_keys = undirected[:, 0] * vertex_count + undirected[:, 1]
    _, counts = np.unique(edge_keys, return_counts=True)
    boundary, non_manifold = int((counts == 1).sum()), int((counts > 2).sum())
    directed_keys = directed[:, 0] * vertex_count + directed[:, 1]
    consistent = len(np.unique(directed_keys)) == len(directed_keys)
    closed = boundary == 0 and non_manifold == 0 and len(good) > 0
    signed = float(np.einsum('ij,ij->i', t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6)
    components = _components(good, vertex_count)
    unit_normals = cross[~degenerate] / doubled[~degenerate, None]
    face_min_z = t[~degenerate, :, 2].min(axis=1)
    areas = doubled[~degenerate] / 2
    overhang = (unit_normals[:, 2] < -math.cos(math.radians(45))) & (face_min_z > lower[2] + 0.2)
    area = float(areas.sum())
    overhang_ratio = float(areas[overhang].sum() / area) if area else 0.0

    findings = []
    def add(level, code, message): findings.append({'level': level, 'code': code, 'message': message})
    if boundary: add('error', 'open_mesh', f'The surface is not closed: {boundary} edges border only one triangle. Slicers may fill or drop the gaps.')
    if non_manifold: add('error', 'non_manifold', f'{non_manifold} edges are shared by more than two triangles (non-manifold geometry).')
    if not consistent: add('error', 'inconsistent_winding', 'Some neighbouring triangles face opposite ways (inconsistent normals).')
    elif closed and signed < 0: add('error', 'inverted_normals', 'The surface normals point inwards (inverted mesh).')
    if int(degenerate.sum() + (collapsed & ~degenerate).sum()):
        add('warning', 'degenerate_faces', f'{int((degenerate | collapsed).sum())} zero-area triangles; usually harmless, slicers ignore them.')
    if mesh.format == 'stl':
        add('info', 'units_assumed', 'STL files carry no unit: coordinates are read as millimetres.')
        if dims.max() < 2: add('warning', 'units_small', 'The model is under 2 mm. It may have been exported in metres or inches; re-export it in millimetres.')
        if dims.max() > 1000: add('warning', 'units_large', 'The model is over 1 m. It may have been exported in micrometres or a smaller unit; re-export it in millimetres.')
    if dims.min() < 1: add('warning', 'thin_model', f'The thinnest overall dimension is {dims.min():.2f} mm; features this small may not print.')
    if components > 1:
        add('info', 'multiple_bodies', f'{components} separate bodies' + (f' in {len(mesh.parts)} build items' if len(mesh.parts) > 1 else '') + '; each prints as its own part.')
    if overhang_ratio > .05:
        add('warning', 'overhangs', f'About {overhang_ratio:.0%} of the surface faces downwards steeper than 45° above the bed: FDM prints will likely need supports in this orientation.')
    add('info', 'needs_slicing', 'Wall thickness, bridges, tolerances and print success can only be confirmed by slicing and a test print.')
    return {
        'version': ANALYSIS_VERSION, 'format': mesh.format, 'unit': mesh.unit,
        'dimensions_mm': mesh.dimensions,
        'bounds_mm': {'min': [round(float(v), 4) for v in lower], 'max': [round(float(v), 4) for v in upper]},
        'triangles': int(len(t)), 'vertices': vertex_count,
        'surface_area_mm2': round(area, 2),
        'volume_mm3': round(abs(signed), 2) if closed and consistent else None,
        'watertight': bool(closed), 'winding_consistent': bool(consistent),
        'inverted_normals': bool(closed and consistent and signed < 0),
        'boundary_edges': boundary, 'non_manifold_edges': non_manifold,
        'degenerate_faces': int((degenerate | collapsed).sum()), 'components': components,
        'overhang_area_ratio': round(overhang_ratio, 4),
        'parts': mesh.parts, 'findings': findings,
    }

def printer_fit(dimensions, printers):
    """Whether the model fits each printer volume in some axis-aligned orientation (as job eligibility)."""
    return [{'id': p['id'], 'fits': all(a <= b for a, b in zip(sorted(dimensions), sorted([p['x'], p['y'], p['z']])))} for p in printers]
