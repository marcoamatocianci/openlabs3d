"""Bounded STL and basic mesh-only 3MF inspection; never a printability certificate."""
import io,json,math,re,secrets,struct,zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
import hashlib
from fastapi import APIRouter,Depends,UploadFile,File,Response
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import models,config
from .database import get_db
from .main import require,mutate,admin_mutate,fail,get_listing,owned,changed,listing_data,current,can_view
router=APIRouter(prefix='/api')
MAX_CAD=20*1024*1024

from . import cad_assets
from .cad_assets import has_preview
from .mesh import ANALYSIS_VERSION,inspect_mesh,load_mesh,printer_fit  # noqa: F401 (inspect_mesh: public helper)
from .manufacturing import CAD_NAME,cad_file,MANUFACTURING_STATES
from .visuals import visual_revision

PREVIEW_TYPES={'.glb':'model/gltf-binary','.webp':'image/webp','.png':'image/png'}
PARSE_ERRORS=(ValueError,UnicodeError,zipfile.BadZipFile,ET.ParseError,KeyError,IndexError,struct.error)
INVALID='Invalid or unsupported STL/3MF mesh. Export a flattened, non-degenerate model.'
def units_warnings(mesh):
    """Unit hints that need no full analysis (STL stores no unit; OpenLabs3D reads millimetres)."""
    dims=mesh.dimensions;warnings=[]
    if mesh.format=='stl':
        if max(dims)<2:warnings.append('The model is under 2 mm. It may have been exported in metres or inches; re-export it in millimetres.')
        if max(dims)>1000:warnings.append('The model is over 1 m. It may have been exported in micrometres or a smaller unit; re-export it in millimetres.')
    return warnings
def parse_upload(data,filename):
    ext=PurePosixPath(filename or '').suffix.lower()
    if ext not in ('.stl','.3mf'):fail(422,'Upload an STL or 3MF file')
    try:return load_mesh(data,ext)
    except PARSE_ERRORS:fail(422,INVALID)
def processing_data(db,digest):
    asset=db.get(models.CadAsset,digest)
    jobs={j.kind:j.status for j in db.scalars(select(models.CadJob).where(models.CadJob.sha256==digest).order_by(models.CadJob.id))}
    return {'analysis':'ready' if asset and asset.analysis_version==ANALYSIS_VERSION else jobs.get('analyze','pending'),
            'preview':'ready' if has_preview(db,digest) else jobs.get('render','pending')}

@router.post('/listings/{listing_id}/cad')
async def upload_cad(listing_id:int,file:UploadFile=File(...),auth=Depends(mutate),db:Session=Depends(get_db)):
    """Validate, store once by content and queue analysis and previews for the CAD worker. Content uploaded
    before (by anyone) reuses its analysis and previews: nothing is processed twice."""
    p=get_listing(db,listing_id);owned(p,auth)
    if p.status=='archived':fail(409,'Archived product cannot be edited')
    data=await file.read(MAX_CAD+1)
    if len(data)>MAX_CAD:fail(413,'Model must be no larger than 20 MB')
    # Parsing, hashing and writing are CPU and disk work: off the event loop, so other requests keep flowing.
    mesh=await run_in_threadpool(parse_upload,data,file.filename);dimensions=mesh.dimensions
    name,digest,created=await run_in_threadpool(cad_assets.store,data,mesh.format)
    try:
        cad_assets.register(db,name,digest,mesh.format,len(data));cad_assets.schedule(db,digest)
        p.cad_path=name;p.cad_dimensions=json.dumps(dimensions);changed(p,auth)
        db.commit()
    except Exception:
        db.rollback()
        if created and db.get(models.CadFile,name) is None:(cad_assets.cad_dir()/name).unlink(missing_ok=True)
        raise
    db.refresh(p)
    printers=db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==p.owner_id)).all()
    fits=any(all(a<=b for a,b in zip(sorted(dimensions),sorted([q.x,q.y,q.z]))) for q in printers)
    return {'listing':listing_data(p),'dimensions_mm':dimensions,'format':mesh.format.upper(),'processing':processing_data(db,digest),
            'warnings':units_warnings(mesh),
            'warning':'Mesh parsed; printability is not verified.'+(' Dimensions exceed all registered printer volumes.' if printers and not fits else '')}
@router.post('/cad/inspect')
async def inspect_cad(file:UploadFile=File(...),auth=Depends(mutate)):
    """Measure a model without storing it, so the editor can show dimensions before saving."""
    if auth[0].role not in ('host','admin') or not auth[0].email_verified:fail(403,'Verified approved host access required')
    data=await file.read(MAX_CAD+1)
    if len(data)>MAX_CAD:fail(413,'Model must be no larger than 20 MB')
    mesh=await run_in_threadpool(parse_upload,data,file.filename)
    return {'format':mesh.format.upper(),'dimensions_mm':mesh.dimensions,'units':'millimetres (STL has no unit; assumed)' if mesh.format=='stl' else 'millimetres (from 3MF unit)',
            'warnings':units_warnings(mesh),'parts':len(mesh.parts) or 1}

@router.get('/listings/{listing_id}/cad/analysis')
def cad_analysis(listing_id:int,auth=Depends(require),db:Session=Depends(get_db)):
    """Geometry findings for the listing's current model, for its owner and administrators. Heuristic checks
    are labelled as such; nothing here guarantees a successful print."""
    p=db.get(models.Listing,listing_id)
    if not p or not p.cad_path:fail(404,'Model not found')
    if p.owner_id!=auth[0].id and auth[0].role!='admin':fail(403,'Model analysis is restricted to its owner and administrators')
    asset=p.cad_file.asset if p.cad_file else None
    if asset is None:return {'status':'pending'}
    result={'status':'ready' if asset.analysis_version==ANALYSIS_VERSION else processing_data(db,asset.sha256)['analysis'],'processing':processing_data(db,asset.sha256)}
    if asset.analysis:
        analysis=json.loads(asset.analysis);result['analysis']=analysis
        printers=db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==p.owner_id)).all()
        result['printers']=[{'id':q.id,'name':f'{q.manufacturer} {q.model}','volume_mm':[q.x,q.y,q.z],**f} for q,f in zip(printers,printer_fit(analysis['dimensions_mm'],[{'id':q.id,'x':q.x,'y':q.y,'z':q.z} for q in printers]))]
    return result

@router.get('/listings/{listing_id}/cad')
def download_cad(listing_id:int,auth=Depends(require),db:Session=Depends(get_db)):
    """The listing's current model, for its owner and administrators. Hosts download the model of
    a specific order through /api/jobs/{job_id}/cad."""
    p=db.get(models.Listing,listing_id)
    if not p or not p.cad_path:fail(404,'Model not found')
    if p.owner_id!=auth[0].id and auth[0].role!='admin':fail(403,'Model access is restricted to its owner and administrators. Printing hosts download the model from their job.')
    # A buyer's custom rack is made by a host from the order; its manufacturing file is not a download for the buyer.
    if p.rack_hash and auth[0].role!='admin':fail(403,'Manufacturing files for custom racks are released to the printing host of an order.')
    path=cad_file(p.cad_path)
    if path is None or not path.is_file():fail(404,'Model not found')
    return FileResponse(path,filename='model'+path.suffix,media_type='application/octet-stream',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})

@router.get('/jobs/{job_id}/cad')
def job_cad(job_id:int,format:str='',auth=Depends(require),db:Session=Depends(get_db)):
    """The exact model sold with this order line. Checked on every request (no reusable links):
    administrators, or the host currently assigned while the job is accepted, printing or ready."""
    job=db.get(models.PrintingJob,job_id)
    user=auth[0]
    # Jobs of other hosts, unassigned and reassigned jobs look the same as missing ones.
    if not job or (user.role!='admin' and job.host_id!=user.id):fail(404,'Model not found')
    order=db.get(models.Order,job.order_id)
    if user.role!='admin':
        from .operations import active_host
        active_host(auth,db)   # 403 once the host is suspended, deactivated or no longer approved
        if job.status not in MANUFACTURING_STATES or order.status=='cancelled':
            fail(403,'Manufacturing files are available only while your job is accepted, printing or ready for delivery')
    item=job.item
    name,expected=item.cad_path,item.cad_sha256
    # A custom rack also pins a 3MF of the same geometry; other lines hold exactly one file.
    if format=='3mf' and item.rack_snapshot:
        pinned=json.loads(item.rack_snapshot).get('files',{}).get('3mf') or {}
        name,expected=pinned.get('name',''),pinned.get('sha256','')
    elif format not in ('','stl'):fail(404,'No manufacturing file was recorded in that format')
    path=cad_file(name)
    if path is None or item.cad_status not in ('pinned','unverified'):fail(404,'No manufacturing file was recorded for this order line')
    if not path.is_file():fail(404,'The manufacturing file for this order line is missing; contact an administrator')
    # The bytes sent are the bytes checked, on every download (rare: about once per job), so a file changed on
    # disk is refused even if its size and timestamps were kept.
    data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
    if expected and digest!=expected:fail(409,'The manufacturing file failed its integrity check; contact an administrator')
    return Response(data,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="{order.reference}-line-{item.id}{path.suffix}"','X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store',
        'X-Content-SHA256':digest,'X-OpenLabs3D-Model-Version':item.cad_status})
@router.post('/admin/products/{listing_id}/{action}')
def product_action(listing_id:int,action:str,auth=Depends(admin_mutate),db:Session=Depends(get_db)):
    p=get_listing(db,listing_id)
    if action not in ('unpublish','remove'):fail(404,'Unknown product action')
    p.status='draft' if action=='unpublish' else 'archived';p.published_at=None
    if action=='remove':p.removed=True
    db.add(models.Activity(actor_id=auth[0].id,action='product.'+action,subject=f'listing:{p.id}'));db.commit()
    return {'ok':True,'message':'Product removed from the marketplace; historical records and assets retained.' if action=='remove' else 'Product unpublished.'}

def rack_job_preview(p,auth,db,asset):
    """A host sees the picture of a custom rack it can take or has taken; nothing else about a private listing."""
    if not p.rack_hash or not auth or auth[0].role!='host' or asset=='model.glb':return False
    jobs=select(models.PrintingJob.id).join(models.OrderItem,models.OrderItem.id==models.PrintingJob.item_id).where(models.OrderItem.listing_id==p.id,(models.PrintingJob.status=='available')|(models.PrintingJob.host_id==auth[0].id)).limit(1)
    return db.scalar(jobs) is not None

@router.get('/listings/{listing_id}/visuals/{revision}/{asset}')
def visual_asset(listing_id:int,revision:str,asset:str,auth=Depends(current),db:Session=Depends(get_db)):
    p=get_listing(db,listing_id)
    if p.cad_file is not None:
        current=visual_revision(p);allowed=(current[0],{current[1],'thumb.webp','model.glb'}) if current else None
    else:   # not registered by the worker yet: the legacy folder named after the file
        allowed=(PurePosixPath(p.cad_path).stem,{'render.png','thumb.webp','model.glb'}) if CAD_NAME.fullmatch(p.cad_path or '') else None
    if not (can_view(p,auth) or rack_job_preview(p,auth,db,asset)) or allowed is None or revision!=allowed[0] or asset not in allowed[1]:
        fail(404,'Preview unavailable')
    path=config.UPLOAD_DIR.parent/'renders'/revision/asset
    if not path.is_file():fail(404,'Preview unavailable')
    # A preview directory never changes once referenced, so its files can be cached for good. Private: the
    # listing may be a draft only its owner sees. A new model or preset gives the listing a new URL.
    cache='private, max-age=31536000, immutable' if p.cad_file is not None else 'private, no-cache'
    # Explicit types: slim images have no /etc/mime.types, and Caddy compresses model/gltf-binary (about 4x).
    return FileResponse(path,media_type=PREVIEW_TYPES[path.suffix],headers={'Cache-Control':cache,'X-Content-Type-Options':'nosniff'})

@router.post('/listings/{listing_id}/render')
def regenerate_render(listing_id:int,auth=Depends(mutate),db:Session=Depends(get_db)):
    """Try a failed preview again. A ready or queued preview is never redone: the same content always
    gives the same images."""
    p=get_listing(db,listing_id);owned(p,auth)
    if not re.fullmatch(r'[a-f0-9]{48}\.(stl|3mf)',p.cad_path):fail(404,'CAD file unavailable')
    if p.cad_file is None:
        cad_assets.reconcile(db)   # an older file: register it (and adopt its previews) now
        db.refresh(p)
    if p.cad_file is None:fail(404,'CAD file unavailable')
    digest=p.cad_file.sha256;requeued=cad_assets.requeue_failed(db,digest);cad_assets.schedule(db,digest);db.commit()
    state=processing_data(db,digest)['preview']
    return {'status':'ready' if state=='ready' else 'queued','requeued':requeued}
