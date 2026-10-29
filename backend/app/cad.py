"""Bounded STL and basic mesh-only 3MF inspection; never a printability certificate."""
import io,json,math,re,secrets,struct,zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from fastapi import APIRouter,Depends,UploadFile,File
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import models,config
from .database import get_db
from .main import require,mutate,admin_mutate,fail,get_listing,owned,changed,listing_data
router=APIRouter(prefix='/api')
MAX_CAD=20*1024*1024

def inspect_mesh(data,ext):
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
            if root.findall('.//m:components',ns) or any('transform' in e.attrib for e in root.iter()):raise ValueError('Component/transformed 3MF files are not supported; export a flattened mesh')
            for mesh in root.findall('.//m:mesh',ns):
                vertices=[tuple(float(v.attrib[k])*scale for k in ('x','y','z')) for v in mesh.findall('m:vertices/m:vertex',ns)]
                for t in mesh.findall('m:triangles/m:triangle',ns):
                    ids=[int(t.attrib[k]) for k in ('v1','v2','v3')]
                    if any(i<0 or i>=len(vertices) for i in ids):raise ValueError('Invalid triangle index')
                    triangles.append([vertices[i] for i in ids])
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
    return dimensions

@router.post('/listings/{listing_id}/cad')
async def upload_cad(listing_id:int,file:UploadFile=File(...),auth=Depends(mutate),db:Session=Depends(get_db)):
    p=get_listing(db,listing_id);owned(p,auth)
    if p.status=='archived':fail(409,'Archived product cannot be edited')
    data=await file.read(MAX_CAD+1)
    if len(data)>MAX_CAD:fail(413,'Model must be no larger than 20 MB')
    ext=PurePosixPath(file.filename or '').suffix.lower()
    try:dimensions=inspect_mesh(data,ext)
    except (ValueError,UnicodeError,zipfile.BadZipFile,ET.ParseError,KeyError,IndexError,struct.error):fail(422,'Invalid or unsupported STL/3MF mesh. Export a flattened, non-degenerate model.')
    directory=config.UPLOAD_DIR.parent/'cad';directory.mkdir(parents=True,exist_ok=True)
    name=secrets.token_hex(24)+ext;path=directory/name;path.write_bytes(data)
    p.cad_path=name;p.cad_dimensions=json.dumps(dimensions);changed(p,auth)
    try:db.commit()
    except Exception:db.rollback();path.unlink(missing_ok=True);raise
    printers=db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==p.owner_id)).all()
    fits=any(all(a<=b for a,b in zip(sorted(dimensions),sorted([q.x,q.y,q.z]))) for q in printers)
    return {'listing':listing_data(p),'dimensions_mm':dimensions,'warning':'Mesh parsed; printability is not verified.'+(' Dimensions exceed all registered printer volumes.' if printers and not fits else '')}
@router.get('/listings/{listing_id}/cad')
def download_cad(listing_id:int,auth=Depends(require),db:Session=Depends(get_db)):
    p=db.get(models.Listing,listing_id)
    if not p or not p.cad_path:fail(404,'Model not found')
    assigned=db.scalar(select(models.PrintingJob.id).join(models.OrderItem,models.OrderItem.id==models.PrintingJob.item_id).where(models.OrderItem.listing_id==listing_id,models.PrintingJob.host_id==auth[0].id))
    if p.owner_id!=auth[0].id and auth[0].role!='admin' and not assigned:fail(403,'Model access is restricted to its owner, administrators and assigned hosts')
    if not re.fullmatch(r'[a-f0-9]{48}\.(stl|3mf)',p.cad_path):fail(404,'Model not found')
    path=config.UPLOAD_DIR.parent/'cad'/p.cad_path
    if not path.is_file():fail(404,'Model not found')
    return FileResponse(path,filename='model'+path.suffix,media_type='application/octet-stream',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})
@router.post('/admin/products/{listing_id}/{action}')
def product_action(listing_id:int,action:str,auth=Depends(admin_mutate),db:Session=Depends(get_db)):
    p=get_listing(db,listing_id)
    if action not in ('unpublish','remove'):fail(404,'Unknown product action')
    p.status='draft' if action=='unpublish' else 'archived';p.published_at=None
    if action=='remove':p.removed=True
    db.add(models.Activity(actor_id=auth[0].id,action='product.'+action,subject=f'listing:{p.id}'));db.commit()
    return {'ok':True,'message':'Product removed from the marketplace; historical records and assets retained.' if action=='remove' else 'Product unpublished.'}
