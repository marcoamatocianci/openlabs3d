"""Curated manufacturer specifications checked 2026-10-28. Unknown compatibility stays unknown."""
import json
import re
from typing import Literal
from datetime import datetime,timezone
from fastapi import APIRouter,Depends
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,delete
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from . import models
from .database import get_db
from .main import require,mutate,admin_mutate,fail,admin
router=APIRouter(prefix='/api')
CATALOGUE=[
 ('Bambu Lab','P1S','FDM',256,256,256,'https://cdn1.bambulab.com/documentation/quick-start-2024-01-17/Quick-Start-P1S_en.pdf',['PLA','PETG','TPU','ABS','ASA','PA / Nylon','PC'],'PA/PC are rated capable, not ideal; stock nozzle is not recommended for fiber composites.'),
 ('Prusa Research','Original Prusa MK4S','FDM',250,210,220,'https://www.prusa3d.com/product/original-prusa-mk4s-3d-printer-7/',[],'Material compatibility not individually verified; confirm enclosure and nozzle requirements.'),
 ('Creality','K1C','FDM',220,220,250,'https://www.creality.com/products/k1c-carbon-3d-printer',[],'Original K1C specifications; do not substitute another variant. Material families not individually verified.'),
 ('UltiMaker','S5','FDM',330,240,300,'https://ultimaker.com/3d-printers/s-series/ultimaker-s5/',[],'Uses 2.85 mm filament. Compatibility depends on print core and material profile.'),
 ('Anycubic','Photon Mono M5s','RESIN',218,123,200,'https://store.anycubic.com/blogs/news/anycubic-photon-mono-m5s-release',[],'Manufacturer H×W×D converted to X×Y×Z. Resin-specific exposure calibration required.'),
 ('Elegoo','Saturn 4 Ultra 12K','RESIN',218.88,122.88,220,'https://us.elegoo.com/products/saturn-4-ultra-12k-10inch-monochrome-lcd-resin-3d-printer',[],'MSLA, 405 nm. This is the 12K variant; resin families not individually verified.'),
 ('Formlabs','Form 4','RESIN',200,125,210,'https://formlabs.com/support/What-is-the-largest-part-I-can-print-on-a-Formlabs-printer/',[],'Use manufacturer-approved material profiles; do not assume generic resin support.')]
def seed_equipment(db):
    for technology,names in [('FDM',['PLA','PLA+','PETG','ABS','ASA','TPU','PA / Nylon','PC']),('RESIN',['Standard Resin','Tough Resin','Flexible Resin','High-Temperature Resin'])]:
        for name in names:db.execute(insert(models.Material).values(name=name,technology=technology).on_conflict_do_nothing())
    for manufacturer,model,technology,x,y,z,source,materials,limitations in CATALOGUE:
        db.execute(insert(models.PrinterModel).values(manufacturer=manufacturer,model=model,technology=technology,x=x,y=y,z=z,source=source,verified=True,materials=json.dumps(materials),limitations=limitations).on_conflict_do_nothing())
    db.commit()
def printer_data(p):
    keys=('id','manufacturer','model','technology','x','y','z')
    result={k:getattr(p,k) for k in keys};result['materials']=json.loads(p.materials)
    if isinstance(p,models.HostPrinter):result['material_colors']=json.loads(p.material_colors or '{}')
    if isinstance(p,models.HostPrinter):result.update(model_id=p.model_id,quantity=p.quantity,verified=bool(p.model_id and __import__('sqlalchemy').orm.object_session(p).get(models.PrinterModel,p.model_id).verified))
    else:result.update(source=p.source,verified=p.verified,limitations=p.limitations)
    return result
@router.get('/printer-catalogue')
def catalogue(db:Session=Depends(get_db)):
    return [printer_data(p) for p in db.scalars(select(models.PrinterModel).order_by(models.PrinterModel.manufacturer,models.PrinterModel.model))]
@router.get('/materials')
def materials(db:Session=Depends(get_db)):
    return [{'name':m.name,'technology':m.technology} for m in db.scalars(select(models.Material).order_by(models.Material.name))]
class EquipmentInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    model_id:int|None=None
    manufacturer:str=Field(default='',max_length=100)
    model:str=Field(default='',max_length=100)
    technology:Literal['FDM','RESIN']='FDM'
    x:float=Field(default=1,gt=0,le=5000,allow_inf_nan=False)
    y:float=Field(default=1,gt=0,le=5000,allow_inf_nan=False)
    z:float=Field(default=1,gt=0,le=5000,allow_inf_nan=False)
    quantity:int=Field(ge=1,le=100,strict=True)
    materials:list[str]=Field(default_factory=list,max_length=12)
    material_colors:dict[str,dict[str,str]]=Field(default_factory=dict,max_length=12)
class ApplicationInput(BaseModel):
    company:str=Field(default='',max_length=150)
    weekly_hours:int|None=Field(default=None,ge=1,le=168)
    printers:list[EquipmentInput]=Field(max_length=30)
    submit:bool=False
@router.get('/host/equipment')
def equipment(auth=Depends(require),db:Session=Depends(get_db)):
    return [printer_data(p) for p in db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==auth[0].id))]
@router.put('/host/equipment-application')
def application(body:ApplicationInput,auth=Depends(mutate),db:Session=Depends(get_db)):
    user=auth[0]
    if user.role=='admin':fail(403,'Administrators cannot apply as hosts')
    host=db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==user.id))
    if host and host.status not in ('draft','rejected','approved'):fail(409,'Application is under review or suspended')
    approved = bool(host and host.status=='approved')
    revision = db.scalar(select(models.EquipmentRevision).where(models.EquipmentRevision.user_id==user.id, models.EquipmentRevision.status.in_(['draft','pending']))) if approved else None
    if revision and revision.status=='pending':fail(409,'Equipment update is already awaiting review')
    if body.submit:
        from .operations import settings
        if not approved and not settings(db)['host_applications_open']:fail(409,'Host applications are closed')
        if not user.email_verified:fail(403,'Verify your email before applying')
        if any(not getattr(user,k) for k in ('first_name','last_name','phone','country','city')):fail(422,'Your contact information is incomplete. Complete Account Information.')
        if not approved and not body.printers:fail(422,'Register at least one printer')
    equipment=[]
    for item in body.printers:
        data=item.model_dump();model=db.get(models.PrinterModel,item.model_id) if item.model_id else None
        if item.model_id and not model:fail(422,'Unknown printer model')
        if model:
            for key in ('manufacturer','model','technology','x','y','z'):data[key]=getattr(model,key)
            if any(data[k] is None for k in ('x','y','z')):fail(422,'Build volume unknown; use a custom printer entry')
        elif body.submit and (not item.manufacturer or not item.model):fail(422,'Enter manufacturer and model')
        valid=set(db.scalars(select(models.Material.name).where(models.Material.technology==data['technology'])))
        if not set(item.materials)<=valid:fail(422,'Selected materials do not match printer technology')
        if body.submit and not item.materials:fail(422,'Select supported materials for every printer')
        if not set(item.material_colors) <= set(item.materials):fail(422,'Colors must belong to a selected material')
        for material, colors in item.material_colors.items():
            if len(colors)>40 or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}',name) or not re.fullmatch(r'#[0-9a-fA-F]{6}',hex) for name,hex in colors.items()):fail(422,'Use color names such as aqua-blue and six-digit hex colors')
        if body.submit and any(not item.material_colors.get(m) for m in item.materials):fail(422,'Configure available colors for each material before submitting')
        data['material_colors']=json.dumps(item.material_colors)
        data['materials']=json.dumps(sorted(set(item.materials)));equipment.append(models.HostPrinter(user_id=user.id,**data))
    if approved:
        proposal={'company':body.company,'weekly_hours':body.weekly_hours,'printers':[equipment_payload(p) for p in equipment]}
        if not revision:
            revision=models.EquipmentRevision(user_id=user.id,before=json.dumps(approved_payload(db,user.id)),proposal='{}')
            db.add(revision)
        revision.proposal=json.dumps(proposal)
        revision.status='pending' if body.submit else 'draft'
        revision.rejection_reason=''
        from .operations import log
        if body.submit:log(db,user.id,'equipment.submitted',f'user:{user.id}')
        db.commit()
        return revision_data(revision,db)
    db.execute(delete(models.HostPrinter).where(models.HostPrinter.user_id==user.id));db.add_all(equipment)
    if not host:host=models.HostApplication(user_id=user.id);db.add(host)
    # Legacy summaries retained for existing moderation and job matching, derived from structured records.
    host.name=' '.join([user.first_name,user.last_name]);host.contact=user.email+' '+user.phone;host.country=user.country;host.region=user.city
    host.printers=', '.join(f'{p.manufacturer} {p.model} × {p.quantity}' for p in equipment)
    host.technologies=', '.join(sorted({p.technology for p in equipment}));host.materials=', '.join(sorted({m for p in equipment for m in json.loads(p.materials)}))
    host.dimensions='See registered equipment';host.capabilities=f'{sum(p.quantity for p in equipment)} printers; weekly availability: {body.weekly_hours or "not specified"} hours'
    host.additional=body.company
    # First-time applicants retain the existing account application workflow.
    host.status='pending' if body.submit else 'draft';host.rejection_reason=''
    if body.submit:host.submitted_at=datetime.now(timezone.utc)
    db.commit()
    return {'status':host.status,'printers':[printer_data(p) for p in equipment],'total':sum(p.quantity for p in equipment)}
@router.post('/admin/printer-suggestions/{printer_id}/approve')
def approve_suggestion(printer_id:int,auth=Depends(admin_mutate),db:Session=Depends(get_db)):
    p=db.get(models.HostPrinter,printer_id)
    if not p or p.model_id:fail(404,'Unreviewed suggestion not found')
    existing=db.scalar(select(models.PrinterModel).where(models.PrinterModel.manufacturer==p.manufacturer,models.PrinterModel.model==p.model))
    if not existing:
        existing=models.PrinterModel(**{k:getattr(p,k) for k in ('manufacturer','model','technology','x','y','z','materials')},source='Administrator-reviewed host suggestion',verified=False,limitations='User-provided specifications; manufacturer verification pending.')
        db.add(existing);db.flush()
    p.model_id=existing.id;db.commit();return printer_data(existing)

@router.get('/admin/printer-suggestions')
def suggestions(auth=Depends(admin),db:Session=Depends(get_db)):
    return [printer_data(p) for p in db.scalars(select(models.HostPrinter).where(models.HostPrinter.model_id.is_(None)))]


def equipment_payload(p):
    return {**{k:getattr(p,k) for k in ('model_id','manufacturer','model','technology','x','y','z','quantity')},
            'materials':sorted(set(json.loads(p.materials))),'material_colors':json.loads(p.material_colors or '{}')}

def approved_payload(db,user_id):
    host=db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==user_id))
    return {'company':host.additional if host else '', 'weekly_hours':int(re.search(r'weekly availability: (\d+)',host.capabilities)[1]) if host and re.search(r'weekly availability: (\d+)',host.capabilities) else None,
            'printers':[equipment_payload(p) for p in db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==user_id).order_by(models.HostPrinter.id))]}

def revision_data(r,db):
    user=db.get(models.User,r.user_id)
    return {'id':r.id,'user_id':r.user_id,'host':user.display_name,'email':user.email,'status':r.status,
            'before':json.loads(r.before),'proposal':json.loads(r.proposal),'rejection_reason':r.rejection_reason}

@router.get('/host/equipment-revision')
def my_revision(auth=Depends(require),db:Session=Depends(get_db)):
    r=db.scalar(select(models.EquipmentRevision).where(models.EquipmentRevision.user_id==auth[0].id).order_by(models.EquipmentRevision.id.desc()))
    return revision_data(r,db) if r else None

@router.delete('/host/equipment-revision')
def discard_revision(auth=Depends(mutate),db:Session=Depends(get_db)):
    r=db.scalar(select(models.EquipmentRevision).where(models.EquipmentRevision.user_id==auth[0].id,models.EquipmentRevision.status.in_(['draft','pending'])))
    if r and r.status=='pending':fail(409,'A pending request cannot be discarded')
    host=db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==auth[0].id))
    if not host or host.status!='approved':fail(403,'Approved host account required')
    current=json.dumps(approved_payload(db,auth[0].id))
    if not r:
        r=models.EquipmentRevision(user_id=auth[0].id,status='draft',proposal=current,before=current)
        db.add(r)
    else:r.proposal=current;r.before=current
    db.commit()
    return revision_data(r,db)

@router.get('/admin/equipment-revisions')
def revision_queue(auth=Depends(admin),db:Session=Depends(get_db)):
    return [revision_data(r,db) for r in db.scalars(select(models.EquipmentRevision).where(models.EquipmentRevision.status=='pending').order_by(models.EquipmentRevision.created_at))]

from . import schemas
@router.post('/admin/equipment-revisions/{revision_id}/{decision}')
def decide_revision(revision_id:int,decision:str,body:schemas.Reject,auth=Depends(admin_mutate),db:Session=Depends(get_db)):
    if decision not in ('approve','reject'):fail(404,'Unknown action')
    r=db.scalar(select(models.EquipmentRevision).where(models.EquipmentRevision.id==revision_id).with_for_update())
    if not r:fail(404,'Equipment revision not found')
    if r.user_id==auth[0].id:fail(403,'You cannot review your own equipment')
    if r.status!='pending':fail(409,'Revision has already been reviewed')
    if decision=='reject' and not body.reason.strip():fail(422,'Enter a rejection reason')
    host=db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==r.user_id))
    if decision=='approve':
        if not host or host.status!='approved':fail(409,'Host account must be approved before activating equipment')
        if approved_payload(db,r.user_id)!=json.loads(r.before):fail(409,'Approved equipment changed; reject this revision so the host can submit a fresh proposal')
        proposal=json.loads(r.proposal)
        # Accepted work keeps its assignment and immutable order-item requirements.
        # Require a single proposed printer capable of each active job before removal.
        import math
        removes_capabilities=any(p not in proposal['printers'] for p in json.loads(r.before)['printers'])
        for job in db.scalars(select(models.PrintingJob).where(models.PrintingJob.host_id==r.user_id,models.PrintingJob.status.in_(['accepted','printing','ready']))):
            if not removes_capabilities:continue
            try:
                dimensions=json.loads(job.item.manufacturing_dimensions)
                if not dimensions:
                    dimension=r'(\d+(?:\.\d+)?)\s*(?:mm)?'
                    match=re.fullmatch(r'\s*'+dimension+r'\s*[x×*]\s*'+dimension+r'\s*[x×*]\s*'+dimension+r'\s*',job.item.dimensions,re.IGNORECASE)
                    dimensions=[float(v) for v in match.groups()] if match else []
            except (ValueError,TypeError):dimensions=[]
            if not isinstance(dimensions,list) or len(dimensions)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in dimensions):
                fail(409,f'Complete active job {job.id} before changing equipment: its build dimensions cannot be verified')
            if not any(job.item.material in p['materials'] and job.item.color in p['material_colors'].get(job.item.material,{}) and all(a<=b for a,b in zip(sorted(dimensions),sorted([p['x'],p['y'],p['z']]))) for p in proposal['printers']):
                fail(409,f'Equipment is required by active job {job.id}; complete or explicitly reassign that job first')
        # Reuse identical records so unrelated certified equipment retains its identity.
        existing=list(db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==r.user_id)))
        for data in proposal['printers']:
            match=next((p for p in existing if equipment_payload(p)==data),None)
            if match:existing.remove(match)
            else:
                values={**data,'materials':json.dumps(data['materials']),'material_colors':json.dumps(data['material_colors'])}
                db.add(models.HostPrinter(user_id=r.user_id,**values))
        for p in existing:db.delete(p)
        host.additional=proposal['company']
        host.printers=', '.join(f"{p['manufacturer']} {p['model']} × {p['quantity']}" for p in proposal['printers'])
        host.materials=', '.join(sorted({m for p in proposal['printers'] for m in p['materials']}))
        host.technologies=', '.join(sorted({p['technology'] for p in proposal['printers']}))
        host.capabilities=f"{sum(p['quantity'] for p in proposal['printers'])} printers; weekly availability: {proposal['weekly_hours'] or 'not specified'} hours"
    r.status='approved' if decision=='approve' else 'rejected'
    r.rejection_reason=body.reason.strip();r.reviewed_by=auth[0].id;r.reviewed_at=datetime.now(timezone.utc)
    from .operations import log
    log(db,auth[0].id,f'equipment.{decision}',f'user:{r.user_id}',body.reason.strip())
    db.commit()
    return revision_data(r,db)
