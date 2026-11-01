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
        # Stock is the host's material inventory limited to what this printer is approved for.
        from .availability import printer_stock
        stock=printer_stock(p)
        result['materials']=sorted(stock);result['material_colors']=stock;result['capabilities']=json.loads(p.capabilities or '[]')
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
        if body.submit and proposal==approved_payload(db,user.id):fail(422,'Nothing has changed compared with your approved equipment')
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
class SuggestionReview(BaseModel):
    """Approve as unverified (no body), or verify the specifications: then every field is checked by an administrator."""
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    verify:bool=False
    technology:Literal['FDM','RESIN']|None=None
    x:float|None=Field(default=None,gt=0,le=5000,allow_inf_nan=False)
    y:float|None=Field(default=None,gt=0,le=5000,allow_inf_nan=False)
    z:float|None=Field(default=None,gt=0,le=5000,allow_inf_nan=False)
    materials:list[str]=Field(default_factory=list,max_length=20)
    source:str=Field(default='',max_length=1000)
    limitations:str=Field(default='',max_length=2000)

def catalogue_model_for(db,spec,body,actor):
    """The catalogue entry for a suggested printer: created (unverified, or verified with the reviewed
    specifications), or the existing entry for that manufacturer and model, updated when verified."""
    body=body or SuggestionReview()
    existing=db.scalar(select(models.PrinterModel).where(models.PrinterModel.manufacturer==spec['manufacturer'],models.PrinterModel.model==spec['model']))
    if not existing:
        existing=models.PrinterModel(manufacturer=spec['manufacturer'],model=spec['model'],technology=spec['technology'],x=spec['x'],y=spec['y'],z=spec['z'],materials='[]',
                                     source='Administrator-reviewed host suggestion',verified=False,limitations='User-provided specifications; manufacturer verification pending.')
        db.add(existing)
    if body.verify:
        if None in (body.technology,body.x,body.y,body.z):fail(422,'Enter technology and build volume to verify the specifications')
        if not body.source:fail(422,'Enter the source of the verified specifications')
        valid=set(db.scalars(select(models.Material.name).where(models.Material.technology==body.technology)))
        if not set(body.materials)<=valid:fail(422,'Select materials of the chosen technology')
        for k in ('technology','x','y','z','source','limitations'):setattr(existing,k,getattr(body,k))
        existing.materials=json.dumps(sorted(set(body.materials)));existing.verified=True
    db.flush()
    from .operations import log
    log(db,actor,'printer.verified' if body.verify else 'printer.suggestion_approved',f'printer_model:{existing.id}',f"{existing.manufacturer} {existing.model}")
    return existing

@router.post('/admin/printer-suggestions/{printer_id}/approve')
def approve_suggestion(printer_id:int,body:SuggestionReview|None=None,auth=Depends(admin_mutate),db:Session=Depends(get_db)):
    p=db.get(models.HostPrinter,printer_id)
    if not p or p.model_id:fail(404,'Unreviewed suggestion not found')
    model=catalogue_model_for(db,{k:getattr(p,k) for k in ('manufacturer','model','technology','x','y','z')},body,auth[0].id)
    # Every registered printer of that model links to the entry; verified materials become its capabilities.
    for q in db.scalars(select(models.HostPrinter).where(models.HostPrinter.manufacturer==model.manufacturer,models.HostPrinter.model==model.model,models.HostPrinter.model_id.is_(None))):
        q.model_id=model.id
        if model.verified:q.capabilities=model.materials
    db.commit();return printer_data(model)

@router.post('/admin/printer-suggestions/revision/{revision_id}/{index}/approve')
def approve_revision_suggestion(revision_id:int,index:int,body:SuggestionReview|None=None,auth=Depends(admin_mutate),db:Session=Depends(get_db)):
    """A printer typed by hand in a pending equipment revision of an approved host."""
    r=db.get(models.EquipmentRevision,revision_id)
    proposal=json.loads(r.proposal) if r and r.status=='pending' else {}
    printers=proposal.get('printers',[])
    if not 0<=index<len(printers) or printers[index].get('model_id'):fail(404,'Unreviewed suggestion not found')
    model=catalogue_model_for(db,printers[index],body,auth[0].id)
    for p in printers:
        if (p['manufacturer'],p['model'])==(model.manufacturer,model.model) and not p.get('model_id'):
            p['model_id']=model.id
            if model.verified:p['capabilities']=json.loads(model.materials)
    r.proposal=json.dumps(proposal)
    db.commit();return printer_data(model)

@router.get('/admin/printer-suggestions')
def suggestions(auth=Depends(admin),db:Session=Depends(get_db)):
    """Printers not in the catalogue: from host applications (registered printers) and from pending
    equipment revisions of approved hosts. One entry per manufacturer and model."""
    result,seen=[],set()
    for p in db.scalars(select(models.HostPrinter).where(models.HostPrinter.model_id.is_(None)).order_by(models.HostPrinter.id)):
        key=(p.manufacturer.casefold(),p.model.casefold())
        if key in seen:continue
        seen.add(key);user=db.get(models.User,p.user_id)
        result.append({**printer_data(p),'origin':'application','suggested_by':user.username if user else '','approve':f'/admin/printer-suggestions/{p.id}/approve'})
    for r in db.scalars(select(models.EquipmentRevision).where(models.EquipmentRevision.status=='pending').order_by(models.EquipmentRevision.created_at)):
        user=db.get(models.User,r.user_id)
        for i,p in enumerate(json.loads(r.proposal).get('printers',[])):
            key=(p['manufacturer'].casefold(),p['model'].casefold())
            if p.get('model_id') or key in seen:continue
            seen.add(key)
            result.append({**{k:p[k] for k in ('manufacturer','model','technology','x','y','z','quantity')},'materials':[],'origin':'revision','revision_id':r.id,
                           'suggested_by':user.username if user else '','approve':f'/admin/printer-suggestions/revision/{r.id}/{i}/approve'})
    return result


def equipment_payload(p):
    return {**{k:getattr(p,k) for k in SPEC_KEYS},'capabilities':sorted(json.loads(p.capabilities or '[]'))}

def approved_payload(db,user_id):
    host=db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==user_id))
    return {'company':host.additional if host else '', 'weekly_hours':int(re.search(r'weekly availability: (\d+)',host.capabilities)[1]) if host and re.search(r'weekly availability: (\d+)',host.capabilities) else None,
            'printers':[equipment_payload(p) for p in db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==user_id).order_by(models.HostPrinter.id))]}

def revision_data(r,db):
    user=db.get(models.User,r.user_id)
    return {'id':r.id,'user_id':r.user_id,'host':user.username or user.display_name,'email':user.email,'status':r.status,
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
        # Unchanged printers keep their record. Stock is the host's material inventory, so it follows
        # the approved capabilities of whichever printers are approved.
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
    """Legacy comma-separated material summary shown to administrators: inventory the printers can use."""
    from .availability import printer_stock
    host.materials=', '.join(sorted({m for p in db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==host.user_id)) for m in printer_stock(p,db)}))

class InventoryInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    material_colors:dict[str,dict[str,str]]=Field(default_factory=dict,max_length=20)

def inventory_data(db,user_id):
    """The host's materials and colours, and which approved printers can use each material."""
    from .availability import host_inventory
    printers=list(db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==user_id).order_by(models.HostPrinter.id)))
    usable={}
    for p in printers:
        for m in json.loads(p.capabilities or '[]'): usable.setdefault(m,[]).append(p.id)
    return {'material_colors':host_inventory(db,user_id),'printers_by_material':usable,
            'technologies':sorted({p.technology for p in printers})}

@router.get('/host/materials')
def my_materials(auth=Depends(require),db:Session=Depends(get_db)):
    return inventory_data(db,auth[0].id)

@router.put('/host/materials')
def update_materials(body:InventoryInput,auth=Depends(mutate),db:Session=Depends(get_db)):
    """Host-managed inventory: materials and colours owned, chosen once for all printers. Takes effect
    immediately for marketplace availability and new job matching; accepted jobs keep their snapshot."""
    from .availability import set_host_inventory
    user=auth[0]
    host=db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==user.id))
    if not host or host.status!='approved':fail(403,'Approved host account required')
    known=set(db.scalars(select(models.Material.name)))
    if not set(body.material_colors)<=known:fail(422,'Unknown material')
    for colors in body.material_colors.values():
        if len(colors)>40 or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}',name) or not re.fullmatch(r'#[0-9a-fA-F]{6}',hex) for name,hex in colors.items()):fail(422,'Use color names such as aqua-blue and six-digit hex colors')
        if len({h.lower() for h in colors.values()})!=len(colors):fail(422,'Each color may be listed only once per material')
    set_host_inventory(db,user.id,body.material_colors)
    sync_host_summary(db,host)
    from .operations import log
    log(db,user.id,'equipment.stock_updated',f'user:{user.id}',', '.join(sorted(body.material_colors)))
    db.commit()
    return inventory_data(db,user.id)


@router.get('/admin/printer-stats')
def printer_stats(auth=Depends(admin),db:Session=Depends(get_db)):
    """Registered printers of approved hosts grouped by type (manufacturer and model): units, hosts, and a
    utilisation rate — each type's share of active printing jobs. A job goes to the host's printer types that
    can actually make it (approved for its material and large enough): all of it when only one type can,
    shared by units when several can, and shared over all the host's types if none matches any more."""
    rows=db.execute(select(models.HostPrinter).join(models.HostApplication,models.HostApplication.user_id==models.HostPrinter.user_id).where(models.HostApplication.status=='approved')).scalars().all()
    types,by_host={},{}
    for p in rows:
        key=(p.manufacturer,p.model)
        t=types.setdefault(key,{'manufacturer':p.manufacturer,'model':p.model,'technology':p.technology,'units':0,'hosts':set(),'verified':False,'active_jobs':0.0})
        t['units']+=p.quantity;t['hosts'].add(p.user_id);by_host.setdefault(p.user_id,[]).append(p)
        if p.model_id:t['verified']=t['verified'] or bool(db.get(models.PrinterModel,p.model_id).verified)
    def fits(p,dims):return len(dims)==3 and all(a<=b for a,b in zip(sorted(dims),sorted([p.x,p.y,p.z])))
    jobs=db.scalars(select(models.PrintingJob).where(models.PrintingJob.status.in_(['accepted','printing','ready']),models.PrintingJob.host_id.in_(list(by_host)))).all()
    for job in jobs:
        printers=by_host[job.host_id]
        try:dims=[float(v) for v in json.loads(job.item.manufacturing_dimensions or '[]')]
        except (ValueError,TypeError):dims=[]
        able=[p for p in printers if job.item.material in json.loads(p.capabilities or '[]') and (not dims or fits(p,dims))] or printers
        units=sum(p.quantity for p in able)
        for p in able:types[(p.manufacturer,p.model)]['active_jobs']+=p.quantity/units
    total=len(jobs)
    result=[{**t,'hosts':len(t['hosts']),'active_jobs':round(t['active_jobs'],2),'utilisation':round(t['active_jobs']/total,4) if total else 0} for t in types.values()]
    return sorted(result,key=lambda t:(-t['units'],t['manufacturer'],t['model']))
