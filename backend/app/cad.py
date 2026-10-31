"""Bounded STL and basic mesh-only 3MF inspection; never a printability certificate."""
import io,json,math,re,secrets,struct,zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
import hashlib
from fastapi import APIRouter,Depends,UploadFile,File,BackgroundTasks,Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import models,config
from .database import get_db
from .main import require,mutate,admin_mutate,fail,get_listing,owned,changed,listing_data,current,can_view
router=APIRouter(prefix='/api')
MAX_CAD=20*1024*1024

from .mesh import inspect_mesh
from .manufacturing import cad_file,MANUFACTURING_STATES

@router.post('/listings/{listing_id}/cad')
async def upload_cad(listing_id:int,background_tasks:BackgroundTasks,file:UploadFile=File(...),auth=Depends(mutate),db:Session=Depends(get_db)):
    p=get_listing(db,listing_id);owned(p,auth)
    if p.status=='archived':fail(409,'Archived product cannot be edited')
    data=await file.read(MAX_CAD+1)
    if len(data)>MAX_CAD:fail(413,'Model must be no larger than 20 MB')
    ext=PurePosixPath(file.filename or '').suffix.lower()
    try:dimensions=inspect_mesh(data,ext)
    except (ValueError,UnicodeError,zipfile.BadZipFile,ET.ParseError,KeyError,IndexError,struct.error):fail(422,'Invalid or unsupported STL/3MF mesh. Export a flattened, non-degenerate model.')
    directory=config.UPLOAD_DIR.parent/'cad';directory.mkdir(parents=True,exist_ok=True)
    # A new random name per upload: files referenced by earlier orders are never overwritten.
    name=secrets.token_hex(24)+ext;path=directory/name
    with path.open('xb') as stream:stream.write(data)
    p.cad_path=name;p.cad_dimensions=json.dumps(dimensions);changed(p,auth)
    try:db.commit()
    except Exception:db.rollback();path.unlink(missing_ok=True);raise
    from .render_product import render_asset
    background_tasks.add_task(render_asset,path)
    printers=db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==p.owner_id)).all()
    fits=any(all(a<=b for a,b in zip(sorted(dimensions),sorted([q.x,q.y,q.z]))) for q in printers)
    return {'listing':listing_data(p),'dimensions_mm':dimensions,'warning':'Mesh parsed; printability is not verified.'+(' Dimensions exceed all registered printer volumes.' if printers and not fits else '')}
@router.post('/cad/inspect')
async def inspect_cad(file:UploadFile=File(...),auth=Depends(mutate)):
    """Measure a model without storing it, so the editor can show dimensions before saving."""
    if auth[0].role not in ('host','admin') or not auth[0].email_verified:fail(403,'Verified approved host access required')
    data=await file.read(MAX_CAD+1)
    if len(data)>MAX_CAD:fail(413,'Model must be no larger than 20 MB')
    ext=PurePosixPath(file.filename or '').suffix.lower()
    if ext not in ('.stl','.3mf'):fail(422,'Upload an STL or 3MF file')
    try:dimensions=inspect_mesh(data,ext)
    except (ValueError,UnicodeError,zipfile.BadZipFile,ET.ParseError,KeyError,IndexError,struct.error):fail(422,'Invalid or unsupported STL/3MF mesh. Export a flattened, non-degenerate model.')
    warnings=[]
    if ext=='.stl':
        # STL stores no units; OpenLabs3D always reads coordinates as millimetres.
        if max(dimensions)<2:warnings.append('The model is under 2 mm. It may have been exported in metres or inches; re-export it in millimetres.')
        if max(dimensions)>1000:warnings.append('The model is over 1 m. It may have been exported in micrometres or a smaller unit; re-export it in millimetres.')
    return {'format':ext[1:].upper(),'dimensions_mm':dimensions,'units':'millimetres (STL has no unit; assumed)' if ext=='.stl' else 'millimetres (from 3MF unit)','warnings':warnings}

@router.get('/listings/{listing_id}/cad')
def download_cad(listing_id:int,auth=Depends(require),db:Session=Depends(get_db)):
    """The listing's current model, for its owner and administrators. Hosts download the model of
    a specific order through /api/jobs/{job_id}/cad."""
    p=db.get(models.Listing,listing_id)
    if not p or not p.cad_path:fail(404,'Model not found')
    if p.owner_id!=auth[0].id and auth[0].role!='admin':fail(403,'Model access is restricted to its owner and administrators. Printing hosts download the model from their job.')
    path=cad_file(p.cad_path)
    if path is None or not path.is_file():fail(404,'Model not found')
    return FileResponse(path,filename='model'+path.suffix,media_type='application/octet-stream',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})

@router.get('/jobs/{job_id}/cad')
def job_cad(job_id:int,auth=Depends(require),db:Session=Depends(get_db)):
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
    path=cad_file(item.cad_path)
    if path is None or item.cad_status not in ('pinned','unverified'):fail(404,'No manufacturing file was recorded for this order line')
    if not path.is_file():fail(404,'The manufacturing file for this order line is missing; contact an administrator')
    data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
    if item.cad_sha256 and digest!=item.cad_sha256:fail(409,'The manufacturing file failed its integrity check; contact an administrator')
    return Response(data,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="{order.reference}-line-{item.id}{path.suffix}"','X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store',
        'X-Content-SHA256':digest,'X-OpenLabs3D-Model-Version':item.cad_status})
@router.post('/admin/products/{listing_id}/{action}')
def product_action(listing_id:int,action:str,auth=Depends(admin_mutate),db:Session=Depends(get_db)):
    p=get_listing(db,listing_id)
    if action not in ('unpublish','remove','official','community'):fail(404,'Unknown product action')
    # Official / community: the listing type only; status and publication stay as they are.
    if action in ('official','community'):
        p.listing_type=action
        db.add(models.Activity(actor_id=auth[0].id,action='product.type_changed',subject=f'listing:{p.id}',detail=action));db.commit()
        return {'ok':True,'message':f'Marked as {action} product.','listing_type':action}
    p.status='draft' if action=='unpublish' else 'archived';p.published_at=None
    if action=='remove':p.removed=True
    db.add(models.Activity(actor_id=auth[0].id,action='product.'+action,subject=f'listing:{p.id}'));db.commit()
    return {'ok':True,'message':'Product removed from the marketplace; historical records and assets retained.' if action=='remove' else 'Product unpublished.'}

@router.get('/listings/{listing_id}/visuals/{revision}/{asset}')
def visual_asset(listing_id:int,revision:str,asset:str,auth=Depends(current),db:Session=Depends(get_db)):
    p=get_listing(db,listing_id)
    if not can_view(p,auth) or asset not in ('render.png','thumb.webp','model.glb') or revision!=PurePosixPath(p.cad_path).stem:
        fail(404,'Preview unavailable')
    path=config.UPLOAD_DIR.parent/'renders'/revision/asset
    if not path.is_file():fail(404,'Preview unavailable')
    return FileResponse(path,headers={'Cache-Control':'private, no-cache','X-Content-Type-Options':'nosniff'})

@router.post('/listings/{listing_id}/render')
def regenerate_render(listing_id:int,background_tasks:BackgroundTasks,auth=Depends(mutate),db:Session=Depends(get_db)):
    p=get_listing(db,listing_id);owned(p,auth)
    if not re.fullmatch(r'[a-f0-9]{48}\.(stl|3mf)',p.cad_path):fail(404,'CAD file unavailable')
    from .render_product import render_asset
    background_tasks.add_task(render_asset,config.UPLOAD_DIR.parent/'cad'/p.cad_path)
    return {'status':'queued'}
