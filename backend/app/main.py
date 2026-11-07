import json
import hashlib
import io
import math
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, select, func, or_
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import StaleDataError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from . import config, email_service, models, schemas
from .avatars import picture_data
from .database import get_db

import logging
class _RedactQuery(logging.Filter):
    """Access log lines keep the path but not the query: OAuth callbacks carry single-use codes there."""
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str) and '?' in record.args[2]:
            record.args = (*record.args[:2], record.args[2].split('?', 1)[0] + '?…', *record.args[3:])
        return True
logging.getLogger('uvicorn.access').addFilter(_RedactQuery())
# The interactive API documentation is a development aid; production does not publish its schema.
_docs = config.APP_ENV != 'production'
app = FastAPI(title='OpenLabs3D API', docs_url='/api/docs' if _docs else None, openapi_url='/api/openapi.json' if _docs else None, redoc_url=None)
hasher = PasswordHasher()
# Checked when there is no account to check, so a request takes as long whether or not the address is registered.
NO_ACCOUNT_HASH = hasher.hash(secrets.token_urlsafe(32))
# Argon2 cannot match this, so no password opens the account until a new one is set from its inbox.
UNUSABLE_PASSWORD = '!unusable'
USERNAME_TAKEN = 'This username is already in use. If it is yours and your email is not confirmed yet, open the link we sent you, or sign in to ask for a new one.'
rate = defaultdict(deque)
rate_lock = threading.Lock()
login_lock = threading.Lock()
login_clock = time.monotonic
upload_lock = threading.Lock()
Image.MAX_IMAGE_PIXELS = 20_000_000

def digest(token): return hashlib.sha256(token.encode()).hexdigest()
def fail(code, message): raise HTTPException(status_code=code, detail=message)
def throttle(key, limit, seconds):
    now = time.monotonic()
    with rate_lock:
        # Bound the in-memory limiter even when clients change IP addresses.
        if len(rate) > 10000:
            for k in list(rate):
                if not rate[k] or rate[k][-1] < now - 900: del rate[k]
        q = rate[key]
        while q and q[0] < now-seconds: q.popleft()
        if len(q) >= limit: fail(429, 'Too many attempts. Please try again later.')
        q.append(now)
def same_origin(request):
    origin = request.headers.get('origin')
    if origin and urlparse(origin).netloc.lower() != request.headers.get('host', '').lower():
        fail(403, 'Invalid request origin')
    if request.headers.get('sec-fetch-site') == 'cross-site': fail(403, 'Invalid request origin')
def current(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get('ol3d_session')
    if not token: return None
    session = db.get(models.LoginSession, digest(token))
    if not session or session.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc): return None
    user = db.get(models.User, session.user_id)
    return (user, session) if user and user.active and may_sign_in(user) else None
def require(auth = Depends(current)):
    if not auth: fail(401, 'Please sign in')
    return auth
def mutate(request: Request, auth = Depends(require)):
    same_origin(request)
    if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), auth[1].csrf): fail(403, 'Invalid CSRF token')
    return auth
def admin(auth = Depends(require)):
    if auth[0].role != 'admin': fail(403, 'Administrator access required')
    return auth
def admin_mutate(auth = Depends(mutate)):
    if auth[0].role != 'admin': fail(403, 'Administrator access required')
    return auth

def new_session(user, response, db, request=None):
    # Always a new token: a session id planted before signing in is worthless afterwards (session fixation).
    previous = request.cookies.get('ol3d_session') if request else None
    if previous: db.execute(delete(models.LoginSession).where(models.LoginSession.token_hash == digest(previous)))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(models.LoginSession(token_hash=digest(token), user_id=user.id, csrf=csrf, expires_at=datetime.now(timezone.utc)+timedelta(days=14)))
    db.commit()
    response.set_cookie('ol3d_session', token, httponly=True, secure=config.SECURE_COOKIE, samesite='lax', max_age=14*86400, path='/')
    return {'user': user_data(user), 'csrf_token': csrf}
def user_data(user): return {**{key:getattr(user,key) for key in ('id','email','display_name','role','username','theme','email_verified','pending_email','first_name','last_name','phone','country','city','region','postal_code','street','additional')}, 'profile_picture':picture_data(user.profile_picture)}
def color_images(p):
    return {c:f'/assets/products/{p.collection_key}/{c}.png' for c in ('aqua-blue','signal-red','cream')} if p.collection_key else {}

from .pricing import options, quote, Rules

def listing_data(p):
    return {**{k:getattr(p,k) for k in ('id','owner_id','title','description','category','price_cents','currency','material','dimensions','compatibility','listing_type','status','rejection_reason','created_at','updated_at','published_at','featured','approved_by','collection_key','cad_dimensions','removed','rack_design_id')}, 'custom_rack':bool(p.rack_hash), 'has_cad':bool(p.cad_path), 'cad_format':p.cad_path.rsplit('.',1)[-1].upper() if p.cad_path else '', 'configurator':options(p), 'color_images':color_images(p), 'seller':p.owner.username or p.owner.display_name, 'images':[{'id':i.id,'url':f'/api/listings/{p.id}/images/{i.id}', 'thumbnail_url':f'/api/listings/{p.id}/images/{i.id}?thumbnail=true', 'sort_order':i.sort_order} for i in sorted(p.images,key=lambda x:x.sort_order)]}
def get_listing(db, listing_id):
    p = db.scalar(select(models.Listing).options(selectinload(models.Listing.images), selectinload(models.Listing.owner)).where(models.Listing.id==listing_id))
    if not p or p.removed: fail(404, 'Listing not found')
    return p
def can_view(p, auth):
    if p.rack_hash: return bool(auth and (auth[0].id == p.owner_id or auth[0].role == 'admin'))    # private to its buyer
    return p.status == 'approved' or bool(auth and (auth[0].id == p.owner_id or auth[0].role == 'admin'))
def owned(p, auth):
    if p.rack_hash: fail(403, 'A custom rack is generated from its design and cannot be edited. Change the design instead.')
    if auth[0].role != 'admin':
        if auth[0].role != 'host' or not auth[0].email_verified: fail(403, 'Verified approved host access required')
    if p.owner_id != auth[0].id and auth[0].role != 'admin': fail(403, 'Not permitted')
def changed(p, auth=None):
    if p.status == 'approved':
        p.status = 'draft' if auth and auth[0].role == 'admin' and p.owner_id == auth[0].id and p.listing_type == 'official' else 'pending'
        p.published_at = None; p.approved_by = None
    elif p.status == 'rejected': p.status = 'draft'
    # Advance the version for photo changes and already-pending edits.
    flag_modified(p, 'status')
def complete(p, db):
    if p.listing_type=='community' and not p.cad_path: fail(422,'Upload a valid STL or 3MF model before submission')
    missing = [name for name in ('title','description','category','material','dimensions','compatibility') if not getattr(p,name).strip()]
    if p.price_cents <= 0: missing.append('price')
    if missing: fail(422, 'Complete these fields before submission: ' + ', '.join(missing))
    if not db.scalar(select(models.Category.id).where(models.Category.name == p.category, models.Category.active.is_(True))): fail(422, 'Choose an active category before submission')

def may_sign_in(user): return user.email_verified or user.legacy_email_access
def password_matches(stored, password):
    try: return hasher.verify(stored, password)
    except (VerifyMismatchError, InvalidHashError): return False

# Per address, for 15 minutes. A lab or campus shares one address, so these are generous: the tight limits sit on what
# is being attacked, which is one account (5 failed sign-ins) or one mailbox (email_service cooldown and hourly limit).
IP_LIMITS = {'register':30, 'verify':60, 'resend-verification':30, 'forgot-password':30, 'reset-password':30}
def session_limit(request, action, account_id=None):
    same_origin(request)
    # Signed in: limited per account, so colleagues behind one address never share a limit.
    if account_id is not None: return throttle((action, 'account', account_id), 10, 900)
    # Caddy overwrites X-Real-IP with the peer address; the backend is not public.
    throttle((action, request.headers.get('x-real-ip', request.client.host if request.client else 'unknown')), IP_LIMITS.get(action, 10), 900)

from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
def invalid_request(request, exc):
    # Same 422 shape, without echoing inputs: non-finite numbers such as Infinity cannot be encoded as JSON.
    return JSONResponse(status_code=422, content={'detail':[{k:v for k,v in e.items() if k in ('type','loc','msg')} for e in exc.errors()]})
@app.exception_handler(StaleDataError)
def stale_listing(request, exc): return JSONResponse(status_code=409, content={'detail':'Listing changed concurrently. Reload and try again.'})
@app.exception_handler(OperationalError)
def database_busy(request, exc): return JSONResponse(status_code=503, content={'detail':'Database is busy. Please try again.'}, headers={'Retry-After':'2'})
@app.get('/api/health')
def health(db: Session = Depends(get_db)):
    db.execute(select(1)); return {'status':'ok'}
@app.post('/api/auth/register', status_code=201)
def register(body: schemas.Register, request: Request, db: Session = Depends(get_db)):
    """No session is created: the account opens once its inbox is confirmed. A registered address gets the same
    answer in the same time as a new one, and the mail tells its owner what happened."""
    session_limit(request, 'register')
    email = str(body.email).lower()
    # Checked first and answered the same whoever the address belongs to: otherwise a taken username would show
    # whether an address is registered. Usernames are public; addresses are not.
    if db.scalar(select(models.User.id).where(models.User.username == body.username)) is not None: fail(409, USERNAME_TAKEN)
    password_hash = hasher.hash(body.password)
    existing = db.scalar(select(models.User).where(models.User.email == email))
    same_password = password_matches(existing.password_hash if existing else NO_ACCOUNT_HASH, body.password)
    if existing is None:
        user = models.User(email=email, username=body.username, display_name=body.username, password_hash=password_hash, role='buyer')
        db.add(user)
        try: db.flush()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(select(models.User).where(models.User.email == email))
            if existing is None: fail(409, USERNAME_TAKEN)
        else:
            db.add(models.Activity(actor_id=user.id, action='user.registered', subject=f'user:{user.id}'))
            email_service.enqueue(db, 'verify_email', email, user.id)
    if existing is not None and existing.active:
        if may_sign_in(existing): email_service.enqueue_limited(db, 'account_exists', email, existing.id)
        # Not active yet: the name chosen now replaces the earlier choice. It is free, as checked above.
        elif same_password:
            existing.username = existing.display_name = body.username
            email_service.enqueue_limited(db, 'verify_email', email, existing.id)
        else:
            existing.username = existing.display_name = body.username
            # A second registration with another password. Either one could be someone else who registered this
            # address first, hoping its owner confirms the account and leaves their password working. Neither
            # password survives: whoever holds the inbox sets a new one.
            existing.password_hash = UNUSABLE_PASSWORD
            db.execute(delete(models.AccountToken).where(models.AccountToken.user_id == existing.id, models.AccountToken.purpose == 'verify'))
            email_service.cancel_pending(db, existing.id, ('verify_email',))
            email_service.enqueue_limited(db, 'finish_registration', email, existing.id)
    db.commit()
    email_service.wake()
    return {'verification_required':True, 'email':email, 'resend_after':config.EMAIL_RESEND_COOLDOWN_SECONDS,
            'message':"We've sent a verification link to your email address. Please verify your email to activate your OpenLabs3D account.", **email_service.capture_info()}
@app.post('/api/auth/login')
def login(body: schemas.Login, request: Request, response: Response, db: Session = Depends(get_db)):
    same_origin(request)
    ip = request.headers.get('x-real-ip', request.client.host if request.client else 'unknown')
    email = str(body.email).lower()
    # The account key is independent of IP, while the IP key limits password spraying.
    account_key = ('login-account', digest(email))
    ip_key = ('login-ip', ip)
    window = 900
    # Serialize check/verify/record to prevent concurrent attempts from bypassing limits.
    with login_lock:
        now = login_clock()
        with rate_lock:
            if len(rate) > 10000:
                for key in list(rate):
                    if not rate[key] or rate[key][-1] <= now - window:
                        del rate[key]
            wait = 0
            for key, limit in ((account_key, 5), (ip_key, 50)):
                q = rate.get(key)
                if not q: continue
                while q and q[0] <= now - window: q.popleft()
                if len(q) >= limit: wait = max(wait, math.ceil(q[0] + window - now))
                if not q: rate.pop(key, None)
            if wait:
                raise HTTPException(status_code=429, detail='Too many failed sign-in attempts.', headers={'Retry-After': str(wait)})
        user = db.scalar(select(models.User).where(models.User.email == email))
        valid = password_matches(user.password_hash if user and user.active else NO_ACCOUNT_HASH, body.password) and bool(user and user.active)
        if not valid:
            with rate_lock:
                now = login_clock()
                rate[account_key].append(now)
                rate[ip_key].append(now)
            fail(401, 'Incorrect email or password')
        with rate_lock:
            rate.pop(account_key, None)
        # Only reached with the right password, so it says nothing about whether an address is registered.
        if not may_sign_in(user):
            fail(403, {'code':'email_unverified', 'message':'Please verify your email address before signing in. We can send you a new link.', **email_service.capture_info()})
        if hasher.check_needs_rehash(user.password_hash): user.password_hash = hasher.hash(body.password); db.commit()
        return new_session(user, response, db, request)
@app.get('/api/auth/me')
def me(auth = Depends(require)): return {'user':user_data(auth[0]), 'csrf_token':auth[1].csrf}
@app.post('/api/auth/logout')
def logout(response: Response, auth = Depends(mutate), db: Session = Depends(get_db)):
    db.delete(auth[1]); db.commit(); response.delete_cookie('ol3d_session', path='/'); return {'ok':True}

@app.get('/api/listings')
def catalogue(q: str = '', category: str = '', sort: str = 'newest', featured: bool = False, page: int = 1, per_page: int = 12, material: str = '', max_price_cents: int | None = None, db: Session = Depends(get_db)):
    if page < 1 or not 1 <= per_page <= 50 or sort not in ('newest','oldest','price_asc','price_desc') or (max_price_cents is not None and max_price_cents < 0): fail(422, 'Invalid filters, pagination or sort')
    query = select(models.Listing).where(models.Listing.status == 'approved', models.Listing.removed.is_(False), models.Listing.rack_hash.is_(None))
    if featured: query = query.where(models.Listing.featured.is_(True))
    if q: query = query.where(or_(*[c.icontains(q[:200], autoescape=True) for c in (models.Listing.title, models.Listing.description, models.Listing.compatibility)]))
    if category: query = query.where(models.Listing.category == category[:100])
    if material: query = query.where(models.Listing.material.icontains(material[:200], autoescape=True))
    if max_price_cents is not None: query = query.where(models.Listing.price_cents <= max_price_cents)
    # Dimensions are free text. Only a leading numeric width can be compared.
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    order = {'newest':models.Listing.published_at.desc(), 'oldest':models.Listing.published_at.asc(), 'price_asc':models.Listing.price_cents.asc(), 'price_desc':models.Listing.price_cents.desc()}[sort]
    items = db.scalars(query.options(selectinload(models.Listing.images),selectinload(models.Listing.owner)).order_by(order, models.Listing.id.desc()).offset((page-1)*per_page).limit(per_page)).all()
    return {'items':[listing_data(p) for p in items], 'total':total, 'page':page, 'per_page':per_page}
@app.get('/api/listings/mine')
def mine(auth = Depends(require), db: Session = Depends(get_db)):
    items = db.scalars(select(models.Listing).options(selectinload(models.Listing.images),selectinload(models.Listing.owner)).where(models.Listing.owner_id==auth[0].id, models.Listing.rack_hash.is_(None)).order_by(models.Listing.updated_at.desc())).all()
    return [listing_data(p) for p in items]
@app.get('/api/listings/{listing_id}')
def detail(listing_id: int, auth = Depends(current), db: Session = Depends(get_db)):
    p=get_listing(db, listing_id)
    if not can_view(p,auth): fail(404,'Listing not found')
    return listing_data(p)
@app.post('/api/listings', status_code=201)
def create(body: schemas.ListingInput, auth = Depends(mutate), db: Session = Depends(get_db)):
    if auth[0].role == 'admin' and body.listing_type != 'official': fail(403, 'Administrators must create official products')
    if auth[0].role != 'admin':
        from .operations import active_host
        active_host(auth,db)
    if body.listing_type == 'official' and auth[0].role != 'admin': fail(403,'Only administrators can create official listings')
    if body.featured and auth[0].role != 'admin': fail(403,'Administrator access required')
    if not auth[0].email_verified: fail(403, 'Verify your email before creating listings')
    values=body.model_dump(); manual=values.pop('cad_dimensions')
    p=models.Listing(**values, owner_id=auth[0].id, cad_dimensions=json.dumps(manual or [])); db.add(p); db.commit(); db.refresh(p); return listing_data(p)
@app.patch('/api/listings/{listing_id}')
def edit(listing_id: int, body: schemas.ListingPatch, auth = Depends(mutate), db: Session = Depends(get_db)):
    p=get_listing(db,listing_id); owned(p,auth)
    values=body.model_dump(exclude_unset=True)
    if any(v is None for v in values.values()): fail(422,'Fields cannot be null')
    if 'featured' in values and auth[0].role != 'admin': fail(403,'Administrator access required')
    if 'listing_type' in values and auth[0].role != 'admin': fail(403,'Only administrators can change listing type')
    if p.status == 'archived': fail(409,'Archived listings cannot be edited')
    if 'cad_dimensions' in values:
        # Uploaded geometry is authoritative; manual dimensions only stand in when no CAD file exists.
        if p.cad_path: fail(409,'Dimensions are extracted from the uploaded CAD file')
        values['cad_dimensions']=json.dumps(values['cad_dimensions'])
    if any(getattr(p,k)!=v for k,v in values.items()):
        changed(p,auth)
        if auth[0].role == 'admin' and p.owner_id == auth[0].id and p.listing_type == 'official': p.status='draft'; p.published_at=None
        for k,v in values.items(): setattr(p,k,v)
        db.commit()
    return listing_data(p)
@app.delete('/api/listings/{listing_id}')
def archive(listing_id: int, auth = Depends(mutate), db: Session = Depends(get_db)):
    p=get_listing(db,listing_id); owned(p,auth); p.status='archived'; p.published_at=None; db.add(models.Activity(actor_id=auth[0].id, action='listing.archived', subject=f'listing:{p.id}')); db.commit(); return listing_data(p)
@app.post('/api/listings/{listing_id}/submit')
def submit(listing_id: int, auth = Depends(mutate), db: Session = Depends(get_db)):
    p=get_listing(db,listing_id); owned(p,auth)
    if not auth[0].email_verified: fail(403, 'Verify your email before submitting listings')
    if p.status not in ('draft','rejected'): fail(409,'Only drafts and rejected listings can be submitted')
    if auth[0].role == 'admin': fail(403, 'Use official product publication')
    from .operations import active_host
    active_host(auth,db)
    complete(p, db); p.status='pending'; p.rejection_reason=''; db.add(models.Activity(actor_id=auth[0].id, action='listing.submitted', subject=f'listing:{p.id}')); db.commit(); return listing_data(p)

@app.post('/api/listings/{listing_id}/publish')
def publish(listing_id: int, auth = Depends(admin_mutate), db: Session = Depends(get_db)):
    if not auth[0].email_verified: fail(403, 'Verify your email before publishing')
    p=get_listing(db,listing_id)
    if p.owner_id != auth[0].id or p.listing_type != 'official': fail(403,'Only your own official products can be published directly')
    if p.status == 'archived': fail(409,'Archived listings cannot be published')
    complete(p,db)
    p.status='approved'; p.published_at=datetime.now(timezone.utc); p.approved_by=auth[0].id; p.rejection_reason=''
    db.add(models.Activity(actor_id=auth[0].id,action='listing.published',subject=f'listing:{p.id}'))
    db.commit(); return listing_data(p)

@app.post('/api/listings/{listing_id}/images', status_code=201)
async def upload(listing_id: int, files: list[UploadFile] = File(...), auth = Depends(mutate), db: Session = Depends(get_db)):
    p=get_listing(db,listing_id); owned(p,auth)
    if p.status == 'archived': fail(409,'Archived listings cannot be edited')
    if not files or len(files)>config.MAX_IMAGES: fail(422,'Too many images')
    processed=[]
    for f in files:
        data=await f.read(config.MAX_UPLOAD+1)
        if len(data)>config.MAX_UPLOAD: fail(413,'Image exceeds the size limit')
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.format not in ('JPEG','PNG','WEBP') or img.width*img.height > 20_000_000 or max(img.size)>10000: fail(422,'Unsupported image or image dimensions')
                fmt=img.format; ext={'JPEG':'.jpg','PNG':'.png','WEBP':'.webp'}[fmt]
                img.load(); img=ImageOps.exif_transpose(img).convert('RGBA' if fmt != 'JPEG' else 'RGB')
                img.thumbnail((2400,2400), Image.Resampling.LANCZOS)
                full=io.BytesIO(); img.save(full,format=fmt,**({'quality':92} if fmt != 'PNG' else {}))
                img.thumbnail((640,640), Image.Resampling.LANCZOS); thumb=io.BytesIO(); img.save(thumb,format=fmt)
                processed.append((Path(f.filename or 'image').name[:255],full.getvalue(),thumb.getvalue(),ext))
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError): fail(422,'Invalid image file')
    paths=[]
    with upload_lock:
        # Refresh after validation so simultaneous uploads cannot exceed the limit.
        db.expire(p,['images'])
        if len(p.images)+len(processed)>config.MAX_IMAGES: fail(422, f'Maximum {config.MAX_IMAGES} images per listing')
        config.UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
        try:
            next_order = max((image.sort_order for image in p.images), default=-1) + 1
            for filename, full, thumb, ext in processed:
                name=uuid.uuid4().hex+ext
                for suffix, data in (('',full),('_thumb'+ext,thumb)):
                    path=config.UPLOAD_DIR/(name+suffix); path.write_bytes(data); paths.append(path)
                db.add(models.ProductImage(listing_id=p.id,filename=filename,storage_path=name,sort_order=next_order))
                next_order += 1
            changed(p,auth); db.commit()
        except Exception:
            db.rollback()
            for path in paths: path.unlink(missing_ok=True)
            raise
    db.expire(p,['images']); return listing_data(p)
@app.get('/api/listings/{listing_id}/images/{image_id}')
def image(listing_id: int, image_id: int, thumbnail: bool = False, auth = Depends(current), db: Session = Depends(get_db)):
    p=get_listing(db,listing_id)
    if not can_view(p,auth): fail(404,'Image not found')
    img=next((i for i in p.images if i.id==image_id),None)
    if not img: fail(404,'Image not found')
    ext=Path(img.storage_path).suffix
    path=config.UPLOAD_DIR/(img.storage_path+('_thumb'+ext if thumbnail else '') if ext else img.storage_path+('_thumb.jpg' if thumbnail else '.jpg'))
    if not path.is_file(): fail(404,'Image not found')
    return FileResponse(path, media_type={'.webp':'image/webp','.png':'image/png'}.get(path.suffix,'image/jpeg'), headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
@app.delete('/api/listings/{listing_id}/images/{image_id}')
def remove_image(listing_id: int, image_id: int, auth = Depends(mutate), db: Session = Depends(get_db)):
    p=get_listing(db,listing_id); owned(p,auth)
    if p.status == 'archived': fail(409,'Archived listings cannot be edited')
    img=next ( (i for i in p.images if i.id==image_id),None)
    if not img: fail(404,'Image not found')
    name=img.storage_path; db.delete(img); changed(p,auth); db.commit()
    for suffix in (('', '_thumb'+Path(name).suffix) if Path(name).suffix else ('.jpg','_thumb.jpg')): (config.UPLOAD_DIR/(name+suffix)).unlink(missing_ok=True)
    return {'ok':True}
@app.put('/api/listings/{listing_id}/images/order')
def reorder(listing_id: int, body: schemas.Reorder, auth = Depends(mutate), db: Session = Depends(get_db)):
    p=get_listing(db,listing_id); owned(p,auth)
    if p.status == 'archived': fail(409,'Archived listings cannot be edited')
    if len(body.image_ids)!=len(p.images) or set(body.image_ids)!={i.id for i in p.images}: fail(422,'Provide each image exactly once')
    by_id={i.id:i for i in p.images}
    if body.image_ids != [i.id for i in p.images]:
        for n,i in enumerate(body.image_ids): by_id[i].sort_order=n
        changed(p,auth); db.commit()
    return listing_data(p)

@app.get('/api/admin/listings')
def admin_list(auth = Depends(admin), db: Session = Depends(get_db)):
    return [listing_data(p) for p in db.scalars(select(models.Listing).options(selectinload(models.Listing.images),selectinload(models.Listing.owner)).where(models.Listing.rack_hash.is_(None)).order_by(models.Listing.updated_at.desc())).all()]
@app.post('/api/admin/listings/{listing_id}/approve')
def approve(listing_id: int, auth = Depends(admin_mutate), db: Session = Depends(get_db)):
    p=get_listing(db,listing_id)
    if p.owner_id == auth[0].id and p.listing_type != 'official': fail(403,'You cannot approve your own community listing')
    if p.status != 'pending': fail(409,'Only pending listings can be approved')
    complete(p, db); p.status='approved'; p.approved_by=auth[0].id; p.published_at=datetime.now(timezone.utc); p.rejection_reason=''; db.add(models.Activity(actor_id=auth[0].id, action='listing.approved', subject=f'listing:{p.id}')); db.commit(); return listing_data(p)
@app.post('/api/admin/listings/{listing_id}/reject')
def reject(listing_id: int, body: schemas.Reject, auth = Depends(admin_mutate), db: Session = Depends(get_db)):
    p=get_listing(db,listing_id)
    if p.status != 'pending': fail(409,'Only pending listings can be rejected')
    p.status='rejected'; p.rejection_reason=body.reason.strip(); p.published_at=None; db.add(models.Activity(actor_id=auth[0].id, action='listing.rejected', subject=f'listing:{p.id}', detail=p.rejection_reason)); db.commit(); return listing_data(p)

from .operations import router as operations_router
app.include_router(operations_router)

@app.on_event('startup')
def start_email_delivery(): email_service.start_worker()
@app.on_event('shutdown')
def stop_email_delivery(): email_service.stop_worker()

@app.on_event('startup')
def seed_official_collection():
    import os
    if os.getenv('SEED_OFFICIAL_COLLECTION') != 'true': return
    from .database import SessionLocal
    from .seed_collection import seed
    with SessionLocal() as db:
        owner=db.scalar(select(models.User).where(models.User.role=='admin',models.User.active.is_(True)).order_by(models.User.id))
        if owner: seed(db,owner)

@app.get('/api/listings/{listing_id}/availability')
def product_availability(listing_id: int, response: Response, auth=Depends(current), db: Session=Depends(get_db)):
    p=get_listing(db,listing_id)
    if p.status != 'approved' or not can_view(p,auth): fail(404,'Listing not available')
    response.headers['Cache-Control']='no-store'
    # Per viewer: a host is not offered what only their own printers can make (see pricing.options).
    return options(p,auth[0].id if auth else None)

@app.post('/api/listings/{listing_id}/quote')
def price_quote(listing_id: int, body: schemas.QuoteInput, auth=Depends(current), db: Session=Depends(get_db)):
    p=get_listing(db,listing_id)
    if p.status != 'approved' or not can_view(p,auth): fail(404,'Listing not available')
    return quote(p,body.material,body.color,body.quantity,auth[0].id if auth else None)

@app.put('/api/listings/{listing_id}/pricing')
def pricing_rules(listing_id: int, body: Rules, auth=Depends(mutate), db: Session=Depends(get_db)):
    import json
    p=get_listing(db,listing_id)
    owned(p,auth)
    # Product compatibility comes from the platform material catalogue, not the host's current stock.
    allowed=set(db.scalars(select(models.Material.name)))|{p.material}
    if any(k not in allowed or not 100<=v<=100000 for k,v in body.materials.items()) or any(not 1<=k<=50 or not 0<=v<=9000 for k,v in body.discounts.items()): fail(422,'Invalid pricing rules')
    if auth[0].role != 'admin': changed(p,auth)
    p.configuration=json.dumps(body.model_dump());db.commit();return listing_data(p)

from .accounts import router as accounts_router
app.include_router(accounts_router)
from .shopping import router as shopping_router
app.include_router(shopping_router)
from .equipment import router as equipment_router
app.include_router(equipment_router)
@app.on_event('startup')
def seed_equipment_catalogue():
    from .equipment import seed_equipment
    from .database import SessionLocal
    with SessionLocal() as db:seed_equipment(db)
from .cad import router as cad_router
app.include_router(cad_router)
from .custom_requests import router as custom_requests_router
app.include_router(custom_requests_router)
from .identity import router as identity_router
app.include_router(identity_router)
from .racks import router as racks_router
app.include_router(racks_router)
