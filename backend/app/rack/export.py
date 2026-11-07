"""Manufacturing files and preview assets from a tessellated solid. numpy and Pillow only, so outputs are simple to audit."""
import io, json, struct, zipfile
import numpy as np
from PIL import Image

def triangles_of(solid, tolerance, angular):
    """A clean indexed mesh of the solid: per-face vertices welded, and triangles that collapse when welded dropped.
    The kernel leaves a few of those at very short edges; each counts its edge twice more, which stricter mesh tools
    read as non-manifold. Removing them changes neither the surface nor its closure."""
    vertices, faces = solid.tessellate(tolerance, angular)
    v = np.array([(p.x, p.y, p.z) for p in vertices], dtype=np.float64)
    welded, f = weld(v, np.array(faces, dtype=np.int64))
    keep = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    return welded, f[keep]

def stl_bytes(v, f, name=b'OpenLabs3D parametric rack'):
    t = v[f].astype(np.float32)
    normals = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True); lengths[lengths == 0] = 1
    record = np.zeros(len(f), dtype=[('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')])
    record['n'], record['v'] = normals / lengths, t
    return name.ljust(80, b' ')[:80] + struct.pack('<I', len(f)) + record.tobytes()

def weld(v, f, tolerance=1e-4):
    keys = np.round(v / tolerance).astype(np.int64)
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    welded = np.zeros((len(unique), 3)); welded[inverse.reshape(-1)] = v
    return welded, inverse.reshape(-1)[f]

BED_INSET_MM = 5.0
CONTENT_TYPES = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
RELS = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'

def threemf_bytes(v, f):
    """A single-object 3MF in millimetres, with a fixed timestamp so identical geometry gives identical bytes."""
    w, g = weld(v, f)
    # On the bed, not around the origin: a slicer takes a 3MF's position literally ("outside of the print volume"), and any
    # bed that holds the rack upright has this corner. STL readers re-centre, so only this format needs it.
    w = w - [w[:, 0].min() - BED_INSET_MM, w[:, 1].min() - BED_INSET_MM, w[:, 2].min()]
    vertices = ''.join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in w)
    triangles = ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in g)
    model = ('<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<resources><object id="1" type="model" name="OpenLabs3D rack"><mesh><vertices>{vertices}</vertices><triangles>{triangles}</triangles></mesh></object></resources>'
             '<build><item objectid="1"/></build></model>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in (('[Content_Types].xml', CONTENT_TYPES), ('_rels/.rels', RELS), ('3D/3dmodel.model', model)):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return buffer.getvalue()

def _vertex_normals(v, f):
    cross = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    normals = np.zeros_like(v)
    for k in range(3): np.add.at(normals, f[:, k], cross)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True); lengths[lengths == 0] = 1
    return normals / lengths

def glb_bytes(v, f, surface_normals=None):
    """A minimal binary glTF, Y up as glTF requires: the browser recolours it, so it carries one neutral material.
    With surface_normals the shading is the CAD's own, and asset.extras tells the viewer to leave it alone."""
    v = np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=1).astype(np.float32)
    if surface_normals is None: n = _vertex_normals(v.astype(np.float64), f).astype(np.float32)
    else: n = np.stack([surface_normals[:, 0], surface_normals[:, 2], -surface_normals[:, 1]], axis=1).astype(np.float32)
    indices = f.astype(np.uint32).reshape(-1).tobytes()
    positions, normals = v.tobytes(), n.tobytes()
    binary = indices + positions + normals
    gltf = {'asset': {'version': '2.0', 'generator': 'OpenLabs3D rack engine', **({'extras': {'exact_normals': True}} if surface_normals is not None else {})}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 1, 'NORMAL': 2}, 'indices': 0, 'material': 0}]}],
            'materials': [{'pbrMetallicRoughness': {'baseColorFactor': [.72, .75, .78, 1], 'metallicFactor': 0, 'roughnessFactor': .6}}],
            'buffers': [{'byteLength': len(binary)}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(indices), 'target': 34963}, {'buffer': 0, 'byteOffset': len(indices), 'byteLength': len(positions), 'target': 34962}, {'buffer': 0, 'byteOffset': len(indices) + len(positions), 'byteLength': len(normals), 'target': 34962}],
            'accessors': [{'bufferView': 0, 'componentType': 5125, 'count': int(f.size), 'type': 'SCALAR'},
                          {'bufferView': 1, 'componentType': 5126, 'count': len(v), 'type': 'VEC3', 'min': [float(c) for c in v.min(0)], 'max': [float(c) for c in v.max(0)]},
                          {'bufferView': 2, 'componentType': 5126, 'count': len(n), 'type': 'VEC3'}]}
    text = json.dumps(gltf, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4); binary += b'\0' * (-len(binary) % 4)
    return struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(text) + 8 + len(binary)) + struct.pack('<I', len(text)) + b'JSON' + text + struct.pack('<I', len(binary)) + b'BIN\0' + binary

def render_still(v, f, size=1200, supersample=2):
    """A neutral grey isometric picture on transparency, tinted to the buyer's colour in the browser like other stills.
    A painter's algorithm over a coarse mesh: quick and dependency-free, and good enough for a basket thumbnail."""
    from PIL import ImageDraw
    px = size * supersample
    yaw, pitch = np.radians(-32), np.radians(32)
    centre = (v.max(0) + v.min(0)) / 2
    p = v - centre
    x = p[:, 0] * np.cos(yaw) - p[:, 1] * np.sin(yaw)
    y = p[:, 0] * np.sin(yaw) + p[:, 1] * np.cos(yaw)
    up = p[:, 2] * np.cos(pitch) + y * np.sin(pitch)
    depth = y * np.cos(pitch) - p[:, 2] * np.sin(pitch)
    view = np.stack([x, up, depth], axis=1)
    scale = .92 * px / max(np.ptp(x), np.ptp(up))
    sx = px / 2 + (x - (x.max() + x.min()) / 2) * scale
    sy = px / 2 - (up - (up.max() + up.min()) / 2) * scale
    t = view[f]
    # (right, up, depth) is left-handed, so the cross product points inward here: negate it for the outward normal.
    normals = -np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True); lengths[lengths == 0] = 1
    normals = normals / lengths
    front = normals[:, 2] < 0
    light = np.array([-.35, .75, -.55]); light = light / np.linalg.norm(light)
    shade = (.62 + .38 * (normals * light).sum(axis=1)).clip(.25, 1)
    order = np.argsort(-t[:, :, 2].mean(axis=1))
    image = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for i in order:
        if not front[i]: continue
        a, b, c = f[i]
        grey = int(205 * shade[i])
        draw.polygon([(sx[a], sy[a]), (sx[b], sy[b]), (sx[c], sy[c])], fill=(grey, grey, grey, 255))
    return image.resize((size, size), Image.LANCZOS)

def webp_bytes(image, **options):
    buffer = io.BytesIO(); image.save(buffer, format='WEBP', **options); return buffer.getvalue()
