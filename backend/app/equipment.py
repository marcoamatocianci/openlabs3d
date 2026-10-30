"""Curated manufacturer specifications checked 2026-10-30. Unknown compatibility stays unknown."""
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
 ('Bambu Lab','A1 mini','FDM',180,180,180,'https://cdn1.bambulab.com/documentation/quick-start-f507128172bdf/Quick%20start%20guide%20-%20A1%20mini-EN.pdf',['PLA','PETG','TPU'],'Open-frame printer; ABS, ASA, PC and nylon are not recommended by the manufacturer.'),
 ('Bambu Lab','A1','FDM',256,256,256,'https://cdn1.bambulab.com/documentation/quick-start-a75adcb1d5d5e/Quick%20Start%20Guide%20for%20A1.pdf',['PLA','PETG','TPU'],'Open-frame printer; ABS, ASA, PC and nylon are not recommended by the manufacturer.'),
 ('Bambu Lab','A2L','FDM',330,320,325,'https://blog.bambulab.com/bambu-lab-a2l-creative-playground-extra-large/',['PLA','PETG'],'Open-frame printer for non-engineering filaments; maximum bed temperature 80 °C.'),
 ('Bambu Lab','P1P','FDM',256,256,256,'https://public-cdn.bambulab.com/store/bambulab-P1P-tech-specs.pdf',['PLA','PETG','TPU','ABS','ASA','PA / Nylon','PC'],'PA, PC, ABS and ASA are rated capable; enclosure and material-specific conditions matter.'),
 ('Bambu Lab','P1S','FDM',256,256,256,'https://cdn1.bambulab.com/documentation/quick-start-2024-01-17/Quick-Start-P1S_en.pdf',['PLA','PETG','TPU','ABS','ASA','PA / Nylon','PC'],'PA/PC are rated capable, not ideal; stock nozzle is not recommended for fiber composites.'),
 ('Bambu Lab','P2S','FDM',256,256,256,'https://blog.bambulab.com/the-icon-redefined-meet-the-p2s-a-completely-reengineered-version-of-the-ultra-productive-p1-series/',[],'Confirm material and nozzle compatibility for the installed equipment.'),
 ('Bambu Lab','X1','FDM',256,256,256,'https://cdn1.bambulab.com/documentation/Quick%20Start%20Guide%20for%20X1%20Combo%26X1-Carbon%20Combo-v1.pdf',['PLA','PETG','TPU','ABS','ASA','PA / Nylon','PC'],'Fiber-reinforced materials are not recommended with the standard X1 nozzle.'),
 ('Bambu Lab','X1 Carbon','FDM',256,256,256,'https://cdn1.bambulab.com/documentation/Quick%20Start%20Guide%20for%20X1%20Combo%26X1-Carbon%20Combo-v1.pdf',['PLA','PETG','TPU','ABS','ASA','PA / Nylon','PC'],'Confirm nozzle and material-specific requirements.'),
 ('Bambu Lab','X1E','FDM',256,256,256,'https://cdn1.bambulab.com/x1e/spec/X1E%20Spec%28EN%29.pdf',[],'Confirm material and nozzle compatibility for the installed equipment.'),
 ('Bambu Lab','X2D','FDM',256,256,260,'https://blog.bambulab.com/two-extruders-one-purpose-what-is-x2d-direct-drive-extrusion-and-auxiliary-extrusion/',[],'Confirm material and toolhead compatibility for the installed equipment.'),
 ('Bambu Lab','H2D','FDM',325,320,325,'https://eu.store.bambulab.com/products/h2d',[],'Single-nozzle volume; dual-nozzle printing is limited to 300 × 320 × 325 mm.'),
 ('Bambu Lab','H2C','FDM',305,320,325,'https://blog.bambulab.com/bambu-lab-h2c-where-multi-material-vortek-system-meets-engineering-precision/',[],'Single-nozzle volume; dual-nozzle printing is limited to 300 × 320 × 325 mm.'),
 ('Bambu Lab','H2S','FDM',340,320,340,'https://blog.bambulab.com/h2s-the-ultimate-single-nozzle-3d-printer-now-bigger-than-ever/',[],'Confirm material and nozzle compatibility for the installed equipment.'),
 ('Elegoo','Centauri 2','FDM',256,256,256,'https://www.elegoo.com/products/centauri-2',['PLA','PETG','TPU'],'ABS, ASA, nylon and PC are not recommended. TPU with CANVAS requires the manufacturer adapter and disconnected CANVAS cable.'),
 ('Elegoo','Centauri Carbon','FDM',256,256,256,'https://us.elegoo.com/products/centauri-carbon',[],'Confirm material compatibility and enclosure settings for the installed equipment.'),
 ('Elegoo','Centauri Carbon 2','FDM',256,256,256,'https://ca.elegoo.com/fr/products/centauri-carbon-2',['PLA','PETG','TPU','ABS','ASA','PA / Nylon','PC'],'Confirm nozzle, filament-specific requirements and enclosure settings.'),
 ('Elegoo','Neptune 3','FDM',220,220,280,'https://www.elegoo.com/en-gb/products/elegoo-neptune-3-fdm-3d-printer',[],'Confirm the nozzle and filament requirements for the installed equipment.'),
 ('Elegoo','Neptune 3 Pro','FDM',225,225,280,'https://us.elegoo.com/products/elegoo-neptune-3-pro-fdm-3d-printer-225x225x280mm',['PLA','PETG','TPU','ABS','ASA'],'Confirm ventilation, enclosure and filament requirements.'),
 ('Elegoo','Neptune 3 Max','FDM',420,420,500,'https://legacy.us.elegoo.com/pages/elegoo-day-sale',['PLA','PETG','TPU','ABS'],'Confirm ventilation, enclosure and filament requirements.'),
 ('Elegoo','Neptune 4','FDM',225,225,265,'https://www.elegoo.com/collections/3d-printing/products/elegoo-neptune-4-fdm-3d-printer',[],'Confirm material compatibility for the installed equipment.'),
 ('Elegoo','Neptune 4 Pro','FDM',225,225,265,'https://eu.elegoo.com/en-dk/products/elegoo-neptune-4-pro-fdm-3d-printer',['PLA','PETG','TPU','ABS','ASA','PA / Nylon'],'Confirm enclosure and filament requirements for engineering materials.'),
 ('Elegoo','Neptune 4 Plus','FDM',320,320,385,'https://www.elegoo.com/products/neptune-4-plus-fdm-3d-printer',['PLA','PETG','TPU','ABS','ASA','PA / Nylon'],'Confirm enclosure and filament requirements for engineering materials.'),
 ('Elegoo','Neptune 4 Max','FDM',420,420,480,'https://eu.elegoo.com/en-nl/products/neptune-4-max-fdm-3d-printer',[],'Confirm material compatibility for the installed equipment.'),
 ('Elegoo','OrangeStorm Giga','FDM',800,800,1000,'https://download.elegoo.com/06%20FDM%20Printer/03%20OrangeStorm%20Giga/1.User%20Manual/OrangeStorm%20Giga-User%20Manual-V1.5-20240604.pdf',[],'Volume is for a single print head; multi-head setups may impose additional limits.'),
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
        stmt=insert(models.PrinterModel).values(manufacturer=manufacturer,model=model,technology=technology,x=x,y=y,z=z,source=source,verified=True,materials=json.dumps(materials),limitations=limitations)
        db.execute(stmt.on_conflict_do_update(index_elements=['manufacturer','model'],set_={k:getattr(stmt.excluded,k) for k in ('technology','x','y','z','source','verified','materials','limitations')},where=models.PrinterModel.verified.is_(True)))
    db.commit()
def printer_data(p):
    keys=('id','manufacturer','model','technology','x','y','z')
    result={k:getattr(p,k) for k in keys};result['materials']=json.loads(p.materials)
    if isinstance(p,models.HostPrinter):
        result['material_colors']=json.loads(p.material_colors or '{}');result['capabilities']=json.loads(p.capabilities or '[]')
        model=__import__('sqlalchemy').orm.object_session(p).get(models.PrinterModel,p.model_id) if p.model_id else None
        result.update(model_id=p.model_id,quantity=p.quantity,verified=bool(model and model.verified),documented=bool(model and json.loads(model.materials)))
    else:result.update(source=p.source,verified=p.verified,limitations=p.limitations)
    return result
SPEC_KEYS=('model_id','manufacturer','model','technology','x','y','z','quantity')
def spec(p):
    """Certified part of a printer: what revisions compare and administrators approve."""
    # Revisions saved before capabilities existed recorded approved materials instead.
    return {k:p.get(k) for k in SPEC_KEYS}|{'capabilities':sorted(p['capabilities'] if 'capabilities' in p else p.get('materials') or [])}
def resolve_capabilities(db,user_id,data):
    """Supported materials come from the printer catalogue; hosts cannot choose them.
    Undocumented models keep only capabilities an administrator already approved for that printer."""
    valid=set(db.scalars(select(models.Material.name).where(models.Material.technology==data['technology'])))
    model=db.get(models.PrinterModel,data['model_id']) if data.get('model_id') else None
    documented=json.loads(model.materials) if model else []
    if documented:return sorted(valid&set(documented))
    previous=db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==user_id,models.HostPrinter.manufacturer==data['manufacturer'],models.HostPrinter.model==data['model'],models.HostPrinter.technology==data['technology']))
    return sorted(valid&{m for q in previous for m in json.loads(q.capabilities or '[]')})
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
        data=item.model_dump(exclude={'materials','material_colors'});model=db.get(models.PrinterModel,item.model_id) if item.model_id else None
        if item.model_id and not model:fail(422,'Unknown printer model')
        if model:
            for key in ('manufacturer','model','technology','x','y','z'):data[key]=getattr(model,key)
            if any(data[k] is None for k in ('x','y','z')):fail(422,'Build volume unknown; use a custom printer entry')
        elif body.submit and (not item.manufacturer or not item.model):fail(422,'Enter manufacturer and model')
        # Material and color stock is managed separately; a revision only certifies the printer.
        data['capabilities']=json.dumps(resolve_capabilities(db,user.id,data))
        data['materials']='[]';data['material_colors']='{}'
        equipment.append(models.HostPrinter(user_id=user.id,**data))
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
    host.technologies=', '.join(sorted({p.technology for p in equipment}));host.materials=''
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
    return {**{k:getattr(p,k) for k in SPEC_KEYS},'capabilities':sorted(json.loads(p.capabilities or '[]'))}

def approved_payload(db,user_id):
    host=db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==user_id))
    return {'company':host.additional if host else '', 'weekly_hours':int(re.search(r'weekly availability: (\d+)',host.capabilities)[1]) if host and re.search(r'weekly availability: (\d+)',host.capabilities) else None,
            'printers':[equipment_payload(p) for p in db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==user_id).order_by(models.HostPrinter.id))]}

def revision_data(r,db):
    user=db.get(models.User,r.user_id)
    return {'id':r.id,'user_id':r.user_id,'host':user.display_name,'email':user.email,'status':r.status,
            'before':json.loads(r.before),'proposal':json.loads(r.proposal),'rejection_reason':r.rejection_reason,
            'created_at':r.created_at,'updated_at':r.updated_at,'reviewed_at':r.reviewed_at}

@router.get('/host/equipment-revision')
def my_revision(auth=Depends(require),db:Session=Depends(get_db)):
    r=db.scalar(select(models.EquipmentRevision).where(models.EquipmentRevision.user_id==auth[0].id).order_by(models.EquipmentRevision.id.desc()))
    return revision_data(r,db) if r else None

@router.delete('/host/equipment-revision')
def discard_revision(auth=Depends(mutate),db:Session=Depends(get_db)):
    # Deletes only the private draft; approved equipment and earlier reviewed revisions are untouched.
    host=db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==auth[0].id))
    if not host or host.status!='approved':fail(403,'Approved host account required')
    r=db.scalar(select(models.EquipmentRevision).where(models.EquipmentRevision.user_id==auth[0].id,models.EquipmentRevision.status.in_(['draft','pending'])))
    if r and r.status=='pending':fail(409,'A pending request cannot be discarded')
    if r:db.delete(r);db.commit()
    return my_revision(auth,db)

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
        before=json.loads(r.before);proposal=json.loads(r.proposal)
        if [spec(p) for p in approved_payload(db,r.user_id)['printers']]!=[spec(p) for p in before['printers']]:fail(409,'Approved equipment changed; reject this revision so the host can submit a fresh proposal')
        proposed=[spec(p) for p in proposal['printers']]
        # Accepted work keeps its assignment and immutable order snapshot. A proposal may only
        # remove capabilities if one proposed printer can still make each active job.
        import math
        removes_capabilities=any(spec(p) not in proposed for p in before['printers'])
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
            if not any(job.item.material in p['capabilities'] and all(a<=b for a,b in zip(sorted(dimensions),sorted([p['x'],p['y'],p['z']]))) for p in proposed):
                fail(409,f'Equipment is required by active job {job.id}; complete or explicitly reassign that job first')
        # Unchanged printers keep their record and stock; a modified printer keeps the stock its new
        # capabilities still allow; new printers start with no stock.
        existing=list(db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==r.user_id).order_by(models.HostPrinter.id)))
        pending=[]
        for data in proposed:
            match=next((p for p in existing if equipment_payload(p)==data),None)
            if match:existing.remove(match)
            else:pending.append(data)
        for data in pending:
            match=next((p for p in existing if (p.manufacturer,p.model)==(data['manufacturer'],data['model'])),None)
            if match:existing.remove(match)
            else:match=models.HostPrinter(user_id=r.user_id,materials='[]',material_colors='{}');db.add(match)
            for k in SPEC_KEYS:setattr(match,k,data[k])
            match.capabilities=json.dumps(data['capabilities'])
            stock=[m for m in json.loads(match.materials or '[]') if m in data['capabilities']]
            match.materials=json.dumps(stock);match.material_colors=json.dumps({m:c for m,c in json.loads(match.material_colors or '{}').items() if m in stock})
        for p in existing:db.delete(p)
        db.flush()
        host.additional=proposal['company']
        host.printers=', '.join(f"{p['manufacturer']} {p['model']} × {p['quantity']}" for p in proposal['printers'])
        sync_host_summary(db,host)
        host.technologies=', '.join(sorted({p['technology'] for p in proposal['printers']}))
        host.capabilities=f"{sum(p['quantity'] for p in proposal['printers'])} printers; weekly availability: {proposal['weekly_hours'] or 'not specified'} hours"
    r.status='approved' if decision=='approve' else 'rejected'
    r.rejection_reason=body.reason.strip();r.reviewed_by=auth[0].id;r.reviewed_at=datetime.now(timezone.utc)
    from .operations import log
    log(db,auth[0].id,f'equipment.{decision}',f'user:{r.user_id}',body.reason.strip())
    db.commit()
    return revision_data(r,db)


def sync_host_summary(db,host):
    """Legacy comma-separated material summary shown to administrators, derived from current stock."""
    host.materials=', '.join(sorted({m for p in db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==host.user_id)) for m in json.loads(p.materials or '[]')}))

class AvailabilityInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    materials:list[str]=Field(default_factory=list,max_length=12)
    material_colors:dict[str,dict[str,str]]=Field(default_factory=dict,max_length=12)

@router.put('/host/printers/{printer_id}/availability')
def update_availability(printer_id:int,body:AvailabilityInput,auth=Depends(mutate),db:Session=Depends(get_db)):
    """Host-managed stock: takes effect immediately for marketplace availability and new job matching,
    limited to the printer's approved capabilities. Accepted jobs keep their order snapshot."""
    user=auth[0]
    host=db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==user.id))
    if not host or host.status!='approved':fail(403,'Approved host account required')
    printer=db.get(models.HostPrinter,printer_id)
    if not printer or printer.user_id!=user.id:fail(404,'Printer not found')
    capabilities=set(json.loads(printer.capabilities or '[]'))
    catalogue=set(db.scalars(select(models.Material.name).where(models.Material.technology==printer.technology)))
    materials=list(dict.fromkeys(body.materials))
    if not set(materials)<=capabilities&catalogue:fail(422,'This printer is not approved for one or more selected materials')
    if not set(body.material_colors)<=set(materials):fail(422,'Colors must belong to a selected material')
    for colors in body.material_colors.values():
        if len(colors)>40 or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}',name) or not re.fullmatch(r'#[0-9a-fA-F]{6}',hex) for name,hex in colors.items()):fail(422,'Use color names such as aqua-blue and six-digit hex colors')
        if len({h.lower() for h in colors.values()})!=len(colors):fail(422,'Each color may be listed only once per material')
    printer.materials=json.dumps(sorted(materials))
    printer.material_colors=json.dumps({m:{n:h.lower() for n,h in c.items()} for m,c in body.material_colors.items()})
    db.flush();sync_host_summary(db,host)
    from .operations import log
    log(db,user.id,'equipment.stock_updated',f'user:{user.id}')
    db.commit()
    return printer_data(printer)
