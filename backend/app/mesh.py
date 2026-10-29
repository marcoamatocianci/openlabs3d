import io,math,re,struct,zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
def inspect_mesh(data,ext,include_triangles=False):
    triangles=[]
    if ext=='.stl':
        count=struct.unpack_from('<I',data,80)[0] if len(data)>=84 else 0
        if count and len(data)==84+count*50:
            if count>400000:raise ValueError('Too many triangles')
            for offset in range(84,len(data),50):
                values=struct.unpack_from('<12f',data,offset);triangles.append([values[3:6],values[6:9],values[9:12]])
        else:
            text=data.decode('ascii')
            if not text.strip().startswith('solid') or 'endsolid' not in text:raise ValueError('Invalid STL')
            vertices=[tuple(map(float,match)) for match in re.findall(r'\bvertex\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)',text)]
            if not vertices or len(vertices)%3 or len(vertices)>1200000:raise ValueError('Invalid STL triangles')
            triangles=[vertices[i:i+3] for i in range(0,len(vertices),3)]
    elif ext=='.3mf':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries=archive.infolist()
            if len(entries)>100 or sum(e.file_size for e in entries)>40*1024*1024:raise ValueError('3MF archive exceeds limits')
            names=set()
            for e in entries:
                p=PurePosixPath(e.filename)
                if p.is_absolute() or '..' in p.parts or '\\' in e.filename or e.filename in names or e.flag_bits&1 or e.file_size>20*1024*1024 or e.file_size/max(1,e.compress_size)>200:raise ValueError('Unsafe 3MF archive')
                names.add(e.filename)
            paths=[e.filename for e in entries if e.filename.lower().endswith('.model')]
            if len(paths)!=1:raise ValueError('Only single-model 3MF files are supported')
            xml=archive.read(paths[0])
            if b'<!' in xml:raise ValueError('XML declarations and entities are prohibited')
            root=ET.fromstring(xml);ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
            scale={'micron':.001,'millimeter':1,'centimeter':10,'inch':25.4,'foot':304.8,'meter':1000}.get(root.get('unit','millimeter'))
            if scale is None:raise ValueError('Unknown model units')
            objects={o.attrib['id']:o for o in root.findall('m:resources/m:object',ns)}
            def transform(vertex, value):
                if not value:return vertex
                matrix=list(map(float,value.split()))
                if len(matrix)!=12 or not all(math.isfinite(v) for v in matrix):raise ValueError('Invalid transform')
                return tuple(sum(vertex[j]*matrix[j*3+i] for j in range(3))+matrix[9+i] for i in range(3))
            def expand(identifier, trail=()):
                if identifier in trail or len(trail)>16:raise ValueError('Recursive 3MF component')
                obj=objects[identifier];result=[]
                for mesh in obj.findall('m:mesh',ns):
                    vertices=[tuple(float(v.attrib[k]) for k in ('x','y','z')) for v in mesh.findall('m:vertices/m:vertex',ns)]
                    for t in mesh.findall('m:triangles/m:triangle',ns):
                        ids=[int(t.attrib[k]) for k in ('v1','v2','v3')]
                        if any(i<0 or i>=len(vertices) for i in ids):raise ValueError('Invalid triangle index')
                        result.append([vertices[i] for i in ids])
                        if len(result)>400000:raise ValueError('Too many triangles')
                for component in obj.findall('m:components/m:component',ns):
                    for tri in expand(component.attrib['objectid'],trail+(identifier,)):
                        result.append([transform(v,component.get('transform')) for v in tri])
                        if len(result)>400000:raise ValueError('Too many triangles')
                return result
            for item in root.findall('m:build/m:item',ns):
                for tri in expand(item.attrib['objectid']):
                    triangles.append([tuple(c*scale for c in transform(v,item.get('transform'))) for v in tri])
                    if len(triangles)>400000:raise ValueError('Too many triangles')
    else:raise ValueError('Upload STL or 3MF')
    if not triangles:raise ValueError('No mesh triangles')
    lower=[math.inf]*3;upper=[-math.inf]*3;valid=False
    for tri in triangles:
        for v in tri:
            if any(not math.isfinite(c) or abs(c)>1e7 for c in v):raise ValueError('Invalid mesh coordinates')
            for i in range(3):lower[i]=min(lower[i],v[i]);upper[i]=max(upper[i],v[i])
        a=[tri[1][i]-tri[0][i] for i in range(3)];b=[tri[2][i]-tri[0][i] for i in range(3)]
        if any(abs(a[i]*b[(i+1)%3]-a[(i+1)%3]*b[i])>1e-12 for i in range(3)):valid=True
    dimensions=[round(upper[i]-lower[i],4) for i in range(3)]
    if not valid or any(d<=0 for d in dimensions):raise ValueError('Degenerate or flat geometry')
    return (dimensions,triangles) if include_triangles else dimensions

