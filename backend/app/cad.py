"""Bounded STL and basic mesh-only 3MF inspection; never a printability certificate."""
import io,json,math,re,secrets,struct,zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from fastapi import APIRouter,Depends,UploadFile,File,BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import models,config
from .database import get_db
from .main import require,mutate,admin_mutate,fail,get_listing,owned,changed,listing_data,current,can_view
router=APIRouter(prefix='/api')
MAX_CAD=20*1024*1024

from .mesh import inspect_mesh

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
    name=secrets.token_hex(24)+ext;path=directory/name;path.write_bytes(data)
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
