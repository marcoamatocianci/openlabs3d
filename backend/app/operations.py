from .availability import supports, host_shades, matches
"""Persistent host, order and marketplace administration workflows."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response, Query
from typing import Literal
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from sqlalchemy import select, update, delete, func, exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import models, schemas
from .database import get_db
from .main import require, mutate, admin, admin_mutate, fail, user_data, hasher, session_limit

router = APIRouter(prefix='/api')

def log(db, actor, action, subject, detail=''):
    db.add(models.Activity(actor_id=actor, action=action, subject=subject, detail=detail))

def host_data(host):
    fields = ('id','user_id','name','contact','country','region','printers','technologies','materials','dimensions','capabilities','additional','status','rejection_reason','submitted_at','reviewed_at','reviewed_by','updated_at')
    return {**{field:getattr(host, field) for field in fields}, 'user':user_data(host.user)}

def settings(db):
    values = {s.key:s.value for s in db.scalars(select(models.MarketplaceSetting)).all()}
    return {'marketplace_name':values.get('marketplace_name','OpenLabs3D'), 'contact':values.get('contact',''), 'host_applications_open':values.get('host_applications_open','true') == 'true'}

def active_host(auth, db):
    host = db.scalar(select(models.HostApplication).where(models.HostApplication.user_id == auth[0].id, models.HostApplication.status == 'approved'))
    if auth[0].role != 'host' or not host: fail(403, 'An approved active host account is required')
    return host

def shipment_data(job):
    if not job.shipped_at: return None
    return {'carrier':job.carrier, 'tracking_number':job.tracking_number, 'tracking_url':job.tracking_url, 'note':job.shipping_note, 'shipped_at':job.shipped_at}

def job_data(job):
    item = job.item
    return {'id':job.id, 'order_id':job.order_id, 'host_id':job.host_id, 'status':job.status, 'updated_at':job.updated_at, 'shipment':shipment_data(job),
            'item':{'color':item.color, 'color_hex':item.color_hex, 'listing_id':item.listing_id, 'title':item.title, 'material':item.material, 'dimensions':item.dimensions, 'quantity':item.quantity, 'price_cents':item.price_cents,
                    # Which model this line is made from; the file itself is served by /api/jobs/{id}/cad.
                    'listing_version':item.listing_version, 'cad_status':item.cad_status, 'cad_format':item.cad_path.rsplit('.',1)[-1].upper() if item.cad_path else '', 'cad_sha256':item.cad_sha256}}

def orders_data(orders, db):
    """Serialize orders with a fixed number of queries (jobs, history, listings), whatever the page size."""
    from .visuals import visual_data
    if not orders: return []
    ids = [o.id for o in orders]
    jobs = db.scalars(select(models.PrintingJob).options(selectinload(models.PrintingJob.item)).where(models.PrintingJob.order_id.in_(ids)).order_by(models.PrintingJob.id)).all()
    by_order = {}
    for job in jobs: by_order.setdefault(job.order_id, []).append(job)
    subjects = [f'order:{i}' for i in ids] + [f'job:{job.id}' for job in jobs]
    history = {}
    for e in db.scalars(select(models.Activity).where(models.Activity.subject.in_(subjects)).order_by(models.Activity.created_at, models.Activity.id)):
        history.setdefault(e.subject, []).append(e)
    listing_ids = {i.listing_id for o in orders for i in o.items}
    listings = {p.id:p for p in db.scalars(select(models.Listing).where(models.Listing.id.in_(listing_ids)))}
    thumbnails = {}
    for p in listings.values():
        # Only publicly viewable products get a preview URL; the image route enforces the same rule.
        visual = visual_data(p) if p.status == 'approved' and not p.removed else {}
        thumbnails[p.id] = visual.get('thumbnail', '') if visual.get('status') == 'ready' else ''
    def item_data(i):
        return {'color':i.color, 'color_hex':i.color_hex, 'listing_id':i.listing_id, 'title':i.title, 'quantity':i.quantity, 'price_cents':i.price_cents, 'material':i.material, 'thumbnail':thumbnails.get(i.listing_id, '')}
    result = []
    for order in orders:
        order_jobs = by_order.get(order.id, [])
        events = sorted([e for s in [f'order:{order.id}', *[f'job:{j.id}' for j in order_jobs]] for e in history.get(s, [])], key=lambda e: (e.created_at, e.id))
        result.append({'id':order.id, 'reference':order.reference, 'buyer_id':order.buyer_id, 'status':order.status, 'total_cents':order.total_cents, 'currency':order.currency, 'created_at':order.created_at,
            'contact':order.contact, 'address':order.address, 'items':[item_data(i) for i in order.items],
            'jobs':[job_data(j) for j in order_jobs], 'history':[{'action':e.action,'created_at':e.created_at} for e in events]})
    return result

def order_data(order, db): return orders_data([order], db)[0]

def sync_order(db, order_id):
    db.flush()
    order = db.get(models.Order, order_id)
    if order.status == 'cancelled': return
    statuses = list(db.scalars(select(models.PrintingJob.status).where(models.PrintingJob.order_id == order_id)))
    # The order reaches a stage once every job has: completed only after the buyer confirmed each one.
    if statuses and all(s == 'completed' for s in statuses): order.status = 'completed'
    elif statuses and all(s in ('shipped','completed') for s in statuses): order.status = 'shipped'
    elif statuses and all(s in ('ready','shipped','completed') for s in statuses): order.status = 'ready'
    elif any(s in ('printing','ready','shipped','completed') for s in statuses): order.status = 'printing'
    elif statuses and all(s == 'accepted' for s in statuses): order.status = 'accepted'
    else: order.status = 'pending'


def delete_account(user, actor, db):
    user_id = user.id
    dependencies = (
        (models.Listing, models.Listing.owner_id),
        (models.Order, models.Order.buyer_id),
        (models.PrintingJob, models.PrintingJob.host_id),
        (models.CustomRequest, models.CustomRequest.user_id),
    )
    if any(db.scalar(select(model.id).where(column == user_id).limit(1)) is not None for model, column in dependencies):
        fail(409, 'This account has listings, orders, printing jobs or custom requests and cannot be deleted while those records exist. Contact the site administrator.')
    # Preserve the activity history without retaining a foreign key to the deleted user.
    db.execute(update(models.Activity).where(models.Activity.actor_id == user_id).values(actor_id=None))
    db.execute(update(models.EquipmentRevision).where(models.EquipmentRevision.reviewed_by == user_id).values(reviewed_by=None))
    db.execute(delete(models.EquipmentRevision).where(models.EquipmentRevision.user_id == user_id))
    db.execute(update(models.HostApplication).where(models.HostApplication.reviewed_by == user_id).values(reviewed_by=None))
    db.execute(delete(models.HostApplication).where(models.HostApplication.user_id == user_id))
    db.execute(delete(models.LoginSession).where(models.LoginSession.user_id == user_id))
    db.delete(user)
    if actor.id != user_id:
        log(db, actor.id, 'user.deleted', f'user:{user_id}')
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, 'This account is linked to other records and cannot be deleted.')

def verify_deletion_password(body, request, actor):
    session_limit(request, 'delete-account')
    try:
        hasher.verify(actor.password_hash, body.password)
    except (VerifyMismatchError, InvalidHashError):
        fail(401, 'Incorrect password')

@router.delete('/profile')
def delete_profile(body: schemas.AccountDeletion, request: Request, response: Response, auth=Depends(mutate), db: Session=Depends(get_db)):
    verify_deletion_password(body, request, auth[0])
    delete_account(auth[0], auth[0], db)
    response.delete_cookie('ol3d_session', path='/')
    return {'ok':True}

@router.delete('/admin/users/{user_id}')
def admin_delete_user(user_id: int, body: schemas.AccountDeletion, request: Request, response: Response, auth=Depends(admin_mutate), db: Session=Depends(get_db)):
    verify_deletion_password(body, request, auth[0])
    user = db.get(models.User, user_id)
    if not user: fail(404, 'User not found')
    is_self = user.id == auth[0].id
    delete_account(user, auth[0], db)
    if is_self: response.delete_cookie('ol3d_session', path='/')
    return {'ok':True}

@router.get('/host/application')
def my_application(auth=Depends(require), db: Session=Depends(get_db)):
    host = db.scalar(select(models.HostApplication).where(models.HostApplication.user_id == auth[0].id))
    return host_data(host) if host else None

@router.put('/host/application')
def save_application(body: schemas.HostApplicationInput, auth=Depends(mutate), db: Session=Depends(get_db)):
    fail(410, 'Use the structured equipment application at /api/host/equipment-application')
    if auth[0].role == 'admin': fail(403, 'Administrators cannot apply as hosts')
    host = db.scalar(select(models.HostApplication).where(models.HostApplication.user_id == auth[0].id))
    if host and host.status not in ('draft','rejected'): fail(409, 'This application cannot be edited in its current state')
    if body.submit and not auth[0].email_verified: fail(403, 'Verify your email before submitting a host application')
    if body.submit and not settings(db)['host_applications_open']: fail(409, 'Host applications are currently closed')
    fields = body.model_dump(exclude={'submit'})
    if body.submit and any(not fields[name] for name in ('name','contact','country','region','printers','technologies','materials','dimensions','capabilities')):
        fail(422, 'Complete all required capability and contact fields before submitting')
    if not host:
        host = models.HostApplication(user_id=auth[0].id)
        db.add(host)
    for key, value in fields.items(): setattr(host,key,value)
    host.status = 'pending' if body.submit else 'draft'
    host.rejection_reason = ''
    if body.submit:
        host.submitted_at = datetime.now(timezone.utc)
        log(db, auth[0].id, 'host.submitted', f'user:{auth[0].id}')
    db.commit()
    return host_data(host)

@router.get('/admin/hosts')
def hosts(status: str='', auth=Depends(admin), db: Session=Depends(get_db)):
    query = select(models.HostApplication).options(selectinload(models.HostApplication.user)).order_by(models.HostApplication.updated_at.desc())
    if status: query = query.where(models.HostApplication.status == status)
    totals = {(host_id, job_status):count for host_id, job_status, count in db.execute(select(models.PrintingJob.host_id, models.PrintingJob.status, func.count()).where(models.PrintingJob.host_id.is_not(None)).group_by(models.PrintingJob.host_id, models.PrintingJob.status))}
    result=[]
    for host in db.scalars(query).all():
        # Read-only: the applicant's registered printers, so administrators can review them before deciding.
        from .equipment import printer_data
        printers=[printer_data(p) for p in db.scalars(select(models.HostPrinter).where(models.HostPrinter.user_id==host.user_id).order_by(models.HostPrinter.id))]
        result.append({**host_data(host), 'equipment':printers, 'active_jobs':sum(totals.get((host.user_id,s),0) for s in ('accepted','printing','ready','shipped')), 'completed_jobs':totals.get((host.user_id,'completed'),0)})
    return result

@router.post('/admin/hosts/{host_id}/{decision}')
def decide_host(host_id: int, decision: str, body: schemas.Reject, auth=Depends(admin_mutate), db: Session=Depends(get_db)):
    if decision not in ('approve','reject','suspend','restore'): fail(404,'Unknown action')
    host = db.get(models.HostApplication, host_id)
    if not host: fail(404,'Host application not found')
    if host.user_id == auth[0].id: fail(403,'You cannot review your own application')
    expected = {'approve':'pending','reject':'pending','suspend':'approved','restore':'suspended'}[decision]
    target = {'approve':'approved','reject':'rejected','suspend':'suspended','restore':'approved'}[decision]
    changed = db.execute(update(models.HostApplication).where(models.HostApplication.id==host_id, models.HostApplication.status==expected).values(status=target, rejection_reason=body.reason.strip(), reviewed_by=auth[0].id, reviewed_at=datetime.now(timezone.utc))).rowcount
    if changed != 1: fail(409,'Application has already changed')
    user = db.get(models.User, host.user_id)
    user.role = 'host' if target == 'approved' else 'buyer'
    log(db, auth[0].id, f'host.{decision}', f'user:{user.id}', body.reason.strip())
    db.commit(); db.refresh(host)
    return host_data(host)

@router.post('/orders', status_code=201)
def create_order(body: schemas.OrderInput, auth=Depends(mutate), db: Session=Depends(get_db)):
    return persist_order(body,auth,db)

def persist_order(body,auth,db,commit=True,contact_email=None):
    import json
    contact=json.loads(body.contact);contact['email']=contact_email or auth[0].email
    body.contact=json.dumps(contact,ensure_ascii=False)
    if not auth[0].email_verified: fail(403, 'Verify your email before ordering')
    if auth[0].role=='admin': fail(403, 'Use marketplace order management')
    existing = db.scalar(select(models.Order).where(models.Order.buyer_id==auth[0].id, models.Order.idempotency_key==body.idempotency_key))
    if existing: return order_data(existing, db)
    ids = [i.listing_id for i in body.items]
    if len({(i.listing_id,i.material,i.color) for i in body.items}) != len(ids): fail(422,'Combine duplicate products into one line')
    products = {p.id:p for p in db.scalars(select(models.Listing).where(models.Listing.id.in_(ids), models.Listing.status=='approved', models.Listing.removed.is_(False))).all()}
    if len(products) != len(set(ids)): fail(409,'A product is no longer available')
    if any(products[i].currency != 'EUR' for i in ids): fail(422,'Unsupported currency')
    from .pricing import quote
    from .manufacturing import snapshot
    quotes=[quote(products[line.listing_id],line.material,line.color,line.quantity) for line in body.items]
    if any(q['unit_price_cents'] != line.expected_price_cents for q,line in zip(quotes,body.items)): fail(409,'Price changed. Refresh the basket before ordering.')
    order = models.Order(reference='OL3D-'+uuid.uuid4().hex[:16].upper(), buyer_id=auth[0].id, idempotency_key=body.idempotency_key, contact=body.contact, address=body.address, total_cents=sum(q['total_cents'] for q in quotes), currency='EUR')
    try:
        db.add(order); db.flush()
        for line,q in zip(body.items,quotes):
            p=products[line.listing_id]
            # Everything needed to make this line exactly as sold, independent of later listing edits.
            item=models.OrderItem(color=line.color,color_hex=q['color_hex'],order_id=order.id,listing_id=p.id,title=p.title,material=q['material'],dimensions=p.dimensions,manufacturing_dimensions=p.cad_dimensions,quantity=line.quantity,price_cents=q['unit_price_cents'],**snapshot(p))
            db.add(item); db.flush()
            db.add(models.PrintingJob(order_id=order.id,item_id=item.id))
        log(db, auth[0].id, 'order.created', f'order:{order.id}')
        if commit: db.commit()
        else: db.flush()
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(models.Order).where(models.Order.buyer_id==auth[0].id,models.Order.idempotency_key==body.idempotency_key))
        if not existing: raise
        return order_data(existing,db)
    return order_data(order,db)

ORDER_GROUPS = {'pending':('pending','accepted'), 'in-progress':('printing','ready','shipped'),
                'completed':('completed',), 'cancelled':('cancelled',)}

@router.get('/orders')
def my_orders(auth=Depends(require), db: Session=Depends(get_db),
              paginated:bool=False, category:Literal['all','pending','in-progress','completed','cancelled']='all',
              sort:Literal['newest','oldest']='newest', page:int=Query(1,ge=1), per_page:int=Query(10,ge=1,le=50)):
    if auth[0].role=='admin': fail(403, 'Use marketplace order management')
    owned=models.Order.buyer_id==auth[0].id
    query=select(models.Order).options(selectinload(models.Order.items)).where(owned)
    direction=lambda column: column.asc() if sort=='oldest' else column.desc()
    query=query.order_by(direction(models.Order.created_at),direction(models.Order.id))
    # Preserve the original list contract for existing clients. The buyer UI opts into bounded pages.
    if not paginated:
        return orders_data(db.scalars(query).all(),db)
    by_status=dict(db.execute(select(models.Order.status,func.count()).where(owned).group_by(models.Order.status)).all())
    counts={'all':sum(by_status.values()), **{key:sum(by_status.get(s,0) for s in statuses) for key,statuses in ORDER_GROUPS.items()}}
    if category!='all':query=query.where(models.Order.status.in_(ORDER_GROUPS[category]))
    total=counts[category]
    pages=max(1,(total+per_page-1)//per_page)
    page=min(page,pages)
    orders=db.scalars(query.offset((page-1)*per_page).limit(per_page)).all()
    return {'items':orders_data(orders,db), 'counts':counts, 'total':total,
            'page':page, 'pages':pages, 'per_page':per_page}

@router.get('/host/jobs')
def host_jobs(auth=Depends(require), db: Session=Depends(get_db)):
    active_host(auth,db)
    jobs=db.scalars(select(models.PrintingJob).options(selectinload(models.PrintingJob.item)).where((models.PrintingJob.status=='available') | (models.PrintingJob.host_id==auth[0].id)).order_by(models.PrintingJob.id.desc())).all()
    result=[];eligible={}
    for job in jobs:
        if job.host_id != auth[0].id:
            # Same rule as supports(), evaluated once per product instead of once per job.
            listing_id=job.item.listing_id
            if listing_id not in eligible: eligible[listing_id]=host_shades(db.get(models.Listing,listing_id),auth[0].id)
            if not matches(eligible[listing_id],job.item.material,job.item.color,job.item.color_hex): continue
        item=job_data(job)
        if job.host_id==auth[0].id and job.status in ('accepted','printing','ready','shipped','completed'):
            order=db.get(models.Order,job.order_id)
            item['fulfillment']={'contact':order.contact,'address':order.address}
        result.append(item)
    return result

@router.post('/host/jobs/{job_id}/accept')
def accept_job(job_id: int, auth=Depends(mutate), db: Session=Depends(get_db)):
    active_host(auth,db)
    job=db.get(models.PrintingJob,job_id)
    if not job: fail(404,'Job not found')
    if not supports(db.get(models.Listing,job.item.listing_id),job.item.material,job.item.color,auth[0].id,job.item.color_hex): fail(403,'Your approved equipment cannot manufacture this material, color and product size')
    host_active=exists(select(models.HostApplication.id).join(models.User,models.User.id==models.HostApplication.user_id).where(models.HostApplication.user_id==auth[0].id,models.HostApplication.status=='approved',models.User.active.is_(True),models.User.role=='host'))
    order_active=exists(select(models.Order.id).where(models.Order.id==models.PrintingJob.order_id,models.Order.status!='cancelled'))
    changed=db.execute(update(models.PrintingJob).where(models.PrintingJob.id==job_id,models.PrintingJob.status=='available',models.PrintingJob.host_id.is_(None),host_active,order_active).values(status='accepted',host_id=auth[0].id,updated_at=datetime.now(timezone.utc))).rowcount
    if changed != 1: fail(409,'This job is no longer available')
    sync_order(db,job.order_id); log(db,auth[0].id,'job.accepted',f'job:{job_id}'); db.commit(); db.refresh(job)
    return job_data(job)

@router.post('/host/jobs/{job_id}/status')
def update_job(job_id: int, body: schemas.JobTransition, auth=Depends(mutate), db: Session=Depends(get_db)):
    active_host(auth,db)
    previous={'printing':'accepted','ready':'printing','shipped':'ready'}[body.status]
    job=db.get(models.PrintingJob,job_id)
    if not job or job.host_id != auth[0].id: fail(404,'Job not found')
    host_active=exists(select(models.HostApplication.id).join(models.User,models.User.id==models.HostApplication.user_id).where(models.HostApplication.user_id==auth[0].id,models.HostApplication.status=='approved',models.User.active.is_(True),models.User.role=='host'))
    moment=datetime.now(timezone.utc); values={'status':body.status,'updated_at':moment}
    if body.status=='shipped':
        values.update(carrier=body.carrier,tracking_number=body.tracking_number,tracking_url=body.tracking_url,shipping_note=body.note,shipped_at=moment)
    changed=db.execute(update(models.PrintingJob).where(models.PrintingJob.id==job_id,models.PrintingJob.host_id==auth[0].id,models.PrintingJob.status==previous,host_active).values(**values)).rowcount
    if changed != 1: fail(409,'Invalid job transition')
    detail=f'{body.carrier} · {body.tracking_number}' if body.status=='shipped' else ''
    sync_order(db,job.order_id); log(db,auth[0].id,f'job.{body.status}',f'job:{job_id}',detail); db.commit(); db.refresh(job)
    return job_data(job)

@router.post('/orders/{order_id}/jobs/{job_id}/received')
def confirm_received(order_id: int, job_id: int, auth=Depends(mutate), db: Session=Depends(get_db)):
    """The buyer confirms a shipped job arrived: it is completed, and the order with it once every job is."""
    order=db.get(models.Order,order_id)
    if not order or order.buyer_id!=auth[0].id: fail(404,'Order not found')
    job=db.get(models.PrintingJob,job_id)
    if not job or job.order_id!=order_id: fail(404,'Job not found')
    changed=db.execute(update(models.PrintingJob).where(models.PrintingJob.id==job_id,models.PrintingJob.status=='shipped').values(status='completed',updated_at=datetime.now(timezone.utc))).rowcount
    if changed != 1: fail(409,'Only a shipped item can be marked as received')
    log(db,auth[0].id,'job.completed',f'job:{job_id}','Receipt confirmed by the buyer')
    sync_order(db,order_id)
    if order.status=='completed': log(db,auth[0].id,'order.completed',f'order:{order_id}')
    db.commit(); db.refresh(order)
    return order_data(order,db)

@router.get('/admin/orders')
def all_orders(auth=Depends(admin), db: Session=Depends(get_db)):
    orders=db.scalars(select(models.Order).options(selectinload(models.Order.items)).order_by(models.Order.created_at.desc())).all()
    return orders_data(orders,db)

@router.post('/admin/orders/{order_id}/cancel')
def cancel_order(order_id: int, auth=Depends(admin_mutate), db: Session=Depends(get_db)):
    changed=db.execute(update(models.Order).where(models.Order.id==order_id,models.Order.status.in_(['pending','accepted'])).values(status='cancelled')).rowcount
    if changed != 1: fail(409,'Only orders not yet in production can be cancelled')
    db.execute(update(models.PrintingJob).where(models.PrintingJob.order_id==order_id,models.PrintingJob.status.in_(['available','accepted'])).values(status='cancelled',updated_at=datetime.now(timezone.utc)))
    log(db,auth[0].id,'order.cancelled',f'order:{order_id}'); db.commit()
    return order_data(db.get(models.Order,order_id),db)

@router.post('/admin/jobs/{job_id}/reopen')
def reopen_job(job_id: int, auth=Depends(admin_mutate), db: Session=Depends(get_db)):
    job=db.get(models.PrintingJob,job_id)
    if not job: fail(404,'Job not found')
    changed=db.execute(update(models.PrintingJob).where(models.PrintingJob.id==job_id,models.PrintingJob.status=='accepted').values(status='available',host_id=None,updated_at=datetime.now(timezone.utc))).rowcount
    if changed != 1: fail(409,'Only accepted jobs can be reopened before printing')
    sync_order(db,job.order_id); log(db,auth[0].id,'job.reopened',f'job:{job_id}'); db.commit(); db.refresh(job)
    return job_data(job)

@router.get('/admin/users')
def users(auth=Depends(admin), db: Session=Depends(get_db)):
    return [{**user_data(u),'active':u.active,'created_at':u.created_at} for u in db.scalars(select(models.User).order_by(models.User.created_at.desc())).all()]

@router.post('/admin/users/{user_id}/{action}')
def change_user(user_id: int, action: str, auth=Depends(admin_mutate), db: Session=Depends(get_db)):
    if action not in ('suspend','restore'): fail(404,'Unknown action')
    user=db.get(models.User,user_id)
    if not user: fail(404,'User not found')
    if user.role=='admin': fail(403,'Administrator accounts cannot be suspended here')
    user.active=action=='restore'
    if not user.active:
        for session in db.scalars(select(models.LoginSession).where(models.LoginSession.user_id==user.id)): db.delete(session)
    log(db,auth[0].id,f'user.{action}',f'user:{user.id}'); db.commit()
    return {**user_data(user),'active':user.active}

@router.get('/categories')
def categories(db: Session=Depends(get_db)):
    return [{'id':c.id,'name':c.name,'sort_order':c.sort_order,'active':c.active} for c in db.scalars(select(models.Category).where(models.Category.active.is_(True)).order_by(models.Category.sort_order,models.Category.name)).all()]

@router.get('/admin/categories')
def all_categories(auth=Depends(admin), db: Session=Depends(get_db)):
    return [{'id':c.id,'name':c.name,'sort_order':c.sort_order,'active':c.active} for c in db.scalars(select(models.Category).order_by(models.Category.sort_order,models.Category.name)).all()]

@router.put('/admin/categories/{category_id}')
def save_category(category_id: int, body: schemas.CategoryInput, auth=Depends(admin_mutate), db: Session=Depends(get_db)):
    name=body.name.strip()
    if not name: fail(422,'Category name is required')
    category=db.get(models.Category,category_id) if category_id else None
    if category_id and not category: fail(404,'Category not found')
    if not category:
        category=models.Category(name=name); db.add(category)
    else:
        old=category.name
        if old != name: db.execute(update(models.Listing).where(models.Listing.category==old).values(category=name, version=models.Listing.version+1, updated_at=datetime.now(timezone.utc)))
    category.name=name; category.sort_order=body.sort_order; category.active=body.active
    log(db,auth[0].id,'category.saved',name)
    try: db.commit()
    except IntegrityError: db.rollback(); fail(409,'Category already exists')
    return {'id':category.id,'name':category.name,'sort_order':category.sort_order,'active':category.active}

@router.get('/settings')
def public_settings(db: Session=Depends(get_db)): return settings(db)

@router.put('/admin/settings')
def change_settings(body: schemas.SettingsInput, auth=Depends(admin_mutate), db: Session=Depends(get_db)):
    for key,value in body.model_dump().items():
        setting=db.get(models.MarketplaceSetting,key)
        if not setting: setting=models.MarketplaceSetting(key=key,value=''); db.add(setting)
        setting.value=str(value).lower() if isinstance(value,bool) else value.strip()
    log(db,auth[0].id,'settings.updated','marketplace'); db.commit()
    return settings(db)

@router.get('/admin/activity')
def activity(auth=Depends(admin), db: Session=Depends(get_db)):
    return [{'id':a.id,'actor_id':a.actor_id,'action':a.action,'subject':a.subject,'detail':a.detail,'created_at':a.created_at} for a in db.scalars(select(models.Activity).order_by(models.Activity.created_at.desc(),models.Activity.id.desc()).limit(200)).all()]

@router.get('/admin/overview')
def overview(auth=Depends(admin), db: Session=Depends(get_db)):
    def count(model,*where): return db.scalar(select(func.count()).select_from(model).where(*where))
    return {'users':count(models.User), 'buyers':count(models.User,models.User.role=='buyer'), 'hosts':count(models.HostApplication,models.HostApplication.status=='approved'), 'pending_hosts':count(models.HostApplication,models.HostApplication.status=='pending'), 'pending_equipment':count(models.EquipmentRevision,models.EquipmentRevision.status=='pending'),
            'products':count(models.Listing), **{f'products_{s}':count(models.Listing,models.Listing.status==s) for s in ('approved','pending','draft','rejected')},
            'orders':count(models.Order), **{f'orders_{s}':count(models.Order,models.Order.status==s) for s in ('pending','accepted','printing','ready','shipped','completed','cancelled')}, 'available_jobs':count(models.PrintingJob,models.PrintingJob.status=='available'), 'custom_requests_new':count(models.CustomRequest,models.CustomRequest.status=='submitted')}
