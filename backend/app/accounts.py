"""Account settings and single-use, hashed inbox verification/reset tokens."""
import re
import secrets
from datetime import datetime, timezone
from typing import Literal
import pycountry
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from sqlalchemy import select, delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from . import email_service, models, schemas, config
from .database import get_db
from .main import require, mutate, current, fail, digest, hasher, user_data, session_limit

router = APIRouter(prefix='/api')
class Contact(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    first_name: str = Field(default='', max_length=100)
    last_name: str = Field(default='', max_length=100)
    phone: str = Field(default='', max_length=40)
    country: str = Field(default='', max_length=2)
    city: str = Field(default='', max_length=150)
    region: str = Field(default='', max_length=150)
    postal_code: str = Field(default='', max_length=30)
    street: str = Field(default='', max_length=200)
    additional: str = Field(default='', max_length=200)
    @field_validator('country')
    @classmethod
    def country_code(cls, value):
        value=value.upper()
        if value and not pycountry.countries.get(alpha_2=value): raise ValueError('Select a country')
        return value
    @field_validator('phone')
    @classmethod
    def phone_format(cls, value):
        if value and (not re.fullmatch(r'\+?[0-9 () .-]+',value) or not 7<=len(re.sub(r'\D','',value))<=15): raise ValueError('Enter an international phone number')
        return value
class Profile(Contact):
    username: str = Field(min_length=3,max_length=32,pattern=r'^[A-Za-z0-9_]+$')
    display_name: str | None = Field(default=None,min_length=1,max_length=100)
class Address(Contact):
    # Optional free-text label such as Laboratory, Home or Work.
    label: str = Field(default='',max_length=40)
    is_default: bool=False
class TokenInput(BaseModel):
    token: str = Field(min_length=20,max_length=200)
class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    password: str = Field(min_length=8,max_length=128)
    _policy=field_validator('password')(schemas.Register.password_policy.__func__)
class ResetPassword(TokenInput):
    password: str = Field(min_length=8,max_length=128)
    _policy=field_validator('password')(schemas.Register.password_policy.__func__)
class EmailInput(BaseModel):
    email: EmailStr

LINK_MESSAGES = {'invalid':'This link is not valid. It may have been replaced by a newer one.', 'expired':'This link has expired.', 'used':'This link has already been used.'}
def link_refused(code): fail(400, {'code':code, 'message':LINK_MESSAGES[code]})

def redeem(db, token, purposes):
    """Single use. The conditional update lets exactly one of several simultaneous attempts through."""
    hashed, now = digest(token), datetime.now(timezone.utc)
    row = db.execute(update(models.AccountToken).where(models.AccountToken.token_hash == hashed, models.AccountToken.purpose.in_(purposes), models.AccountToken.used_at.is_(None), models.AccountToken.expires_at > now)
                     .values(used_at=now).returning(models.AccountToken.user_id, models.AccountToken.purpose, models.AccountToken.new_email)).first()
    if row:
        user = db.get(models.User, row.user_id)
        if not user or not user.active: db.rollback(); link_refused('invalid')
        return user, row.purpose, row.new_email
    found = db.get(models.AccountToken, hashed)
    if found is None or found.purpose not in purposes: link_refused('invalid')
    link_refused('used' if found.used_at else 'expired')

def mark_verified(user):
    user.email_verified, user.email_verified_at, user.legacy_email_access = True, datetime.now(timezone.utc), False

@router.get('/countries')
def countries(): return sorted([{'code':c.alpha_2,'name':c.name} for c in pycountry.countries],key=lambda c:c['name'])

# Regions and cities for the address forms (GeoNames, CC BY 4.0; built by scripts/build_locations.py).
_locations=None
def locations_data():
    global _locations
    if _locations is None:
        import gzip, json
        from pathlib import Path
        with gzip.open(Path(__file__).parent/'geodata'/'locations.json.gz','rt',encoding='utf-8') as source: _locations=json.load(source)
    return _locations
@router.get('/countries/{code}/locations')
def country_locations(code: str, response: Response):
    code=code.upper()
    if not pycountry.countries.get(alpha_2=code): fail(404,'Unknown country')
    entry=locations_data().get(code,{'regions':{},'cities':[]})
    response.headers['Cache-Control']='public, max-age=86400'
    # Cities as compact rows [name, region code, aliases?]: large countries list tens of thousands of towns.
    return {'regions':[{'code':k,'name':v} for k,v in entry['regions'].items()],'cities':entry['cities'],'source':'GeoNames (CC BY 4.0)'}

@router.get('/auth/username')
def available(username: str, auth=Depends(current), db: Session=Depends(get_db)):
    if not re.fullmatch(r'[A-Za-z0-9_]{3,32}',username): return {'available':False}
    owner=db.scalar(select(models.User.id).where(models.User.username==username))
    return {'available':owner is None or bool(auth and owner==auth[0].id)}

RESEND_MESSAGE = 'If an account requiring verification exists for this address, a new verification email will be sent.'
class ResendInput(BaseModel):
    email: EmailStr | None = None
@router.post('/auth/resend-verification')
def resend(body: ResendInput, request: Request, auth=Depends(current), db: Session=Depends(get_db)):
    session_limit(request,'resend-verification')
    # Without an address, someone signed in means their own: that is all a page opened before this field existed sends.
    email=str(body.email).lower() if body.email else auth[0].email if auth else None
    if not email: fail(422,'Enter your email address')
    user=db.scalar(select(models.User).where(models.User.email==email,models.User.active.is_(True)))
    queued=False
    if user and not user.email_verified:
        queued=email_service.enqueue_limited(db,'verify_email',user.email,user.id);db.commit();email_service.wake()
    message=RESEND_MESSAGE    # The same answer whatever happened: unknown, verified, in its cooldown or sent.
    if auth and auth[0].email==email:    # Only the account's own owner can be told what actually happened.
        message='Your email is already verified.' if auth[0].email_verified else f'A new verification email is on its way to {email}.' if queued else 'We sent you one a moment ago. Check your inbox, or try again in a minute.'
    return {'message':message,'resend_after':config.EMAIL_RESEND_COOLDOWN_SECONDS,**email_service.capture_info()}

@router.post('/auth/verify')
def verify(body: TokenInput, request: Request, auth=Depends(current), db: Session=Depends(get_db)):
    session_limit(request,'verify')
    user,purpose,new_email=redeem(db,body.token,('verify','email_change'))
    signed_in=bool(auth and auth[0].id==user.id)
    if purpose=='email_change':
        old=user.email
        taken=db.scalar(select(models.User.id).where(models.User.email==new_email,models.User.id!=user.id))
        if taken or user.pending_email!=new_email:
            if user.pending_email==new_email: user.pending_email=None
            db.commit();fail(409,{'code':'conflict','message':'This address cannot be used for your account. Your current address has not changed.'})
        user.email,user.pending_email=new_email,None;mark_verified(user)
        # Links sent to the old address stop working, and so do other sessions.
        db.execute(delete(models.AccountToken).where(models.AccountToken.user_id==user.id,models.AccountToken.token_hash!=digest(body.token)))
        email_service.cancel_pending(db,user.id,('verify_email','email_change','password_reset','finish_registration'))
        db.execute(delete(models.LoginSession).where(models.LoginSession.user_id==user.id,models.LoginSession.token_hash!=(auth[1].token_hash if signed_in else '')))
        db.add(models.Activity(actor_id=user.id,action='user.email_changed',subject=f'user:{user.id}'))
        email_service.enqueue(db,'email_changed_notice',old,user.id,{'new_address':email_service.mask_address(new_email)})
        try: db.commit()
        except IntegrityError: db.rollback();fail(409,{'code':'conflict','message':'This address cannot be used for your account. Your current address has not changed.'})
        email_service.wake()
        return {'status':'email_changed','email':new_email,'signed_in':signed_in,'message':'Your email address has been changed.'}
    if user.email_verified: db.commit();return {'status':'verified','signed_in':signed_in,'message':'Your email is verified.'}
    mark_verified(user);db.add(models.Activity(actor_id=user.id,action='user.email_verified',subject=f'user:{user.id}'));db.commit()
    return {'status':'verified','signed_in':signed_in,'message':'Your email is verified. You can now sign in.'}

@router.post('/auth/forgot-password')
def forgot(body: EmailInput, request: Request, db: Session=Depends(get_db)):
    session_limit(request,'forgot-password')
    user=db.scalar(select(models.User).where(models.User.email==str(body.email).lower(),models.User.active.is_(True)))
    if user: email_service.enqueue_limited(db,'password_reset',user.email,user.id);db.commit();email_service.wake()
    return {'message':'If this account exists, a reset message has been requested.'}

@router.post('/auth/reset-password')
def reset(body: ResetPassword, request: Request, db: Session=Depends(get_db)):
    session_limit(request,'reset-password')
    user,_,_=redeem(db,body.token,('reset',));user.password_hash=hasher.hash(body.password)
    # The link reached this inbox, which confirms the address.
    if not user.email_verified: mark_verified(user)
    db.execute(delete(models.LoginSession).where(models.LoginSession.user_id==user.id))
    email_service.enqueue(db,'password_changed',user.email,user.id);db.commit();email_service.wake()
    return {'message':'Password reset. Sign in with your new password.'}

@router.post('/auth/change-password')
def change_password(body: PasswordChange, request: Request, auth=Depends(mutate), db: Session=Depends(get_db)):
    session_limit(request,'change-password',auth[0].id)
    try: hasher.verify(auth[0].password_hash,body.current_password)
    except (VerifyMismatchError,InvalidHashError): fail(401,'Incorrect current password')
    auth[0].password_hash=hasher.hash(body.password)
    db.execute(delete(models.AccountToken).where(models.AccountToken.user_id==auth[0].id,models.AccountToken.purpose=='reset'))
    db.execute(delete(models.LoginSession).where(models.LoginSession.user_id==auth[0].id,models.LoginSession.token_hash!=auth[1].token_hash))
    email_service.enqueue(db,'password_changed',auth[0].email,auth[0].id);db.commit();email_service.wake()
    return {'message':'Password changed. Other sessions have been signed out.'}

@router.patch('/profile')
def profile(body: Profile, auth=Depends(mutate), db: Session=Depends(get_db)):
    for key,value in body.model_dump(exclude_unset=True,exclude={'display_name'}).items():
        if value is not None: setattr(auth[0],key,value)
    # One public name: the username. The legacy display_name column is kept in step, never edited.
    auth[0].display_name=auth[0].username
    db.add(models.Activity(actor_id=auth[0].id,action='profile.updated',subject=f'user:{auth[0].id}',detail=', '.join(sorted(body.model_dump(exclude_unset=True,exclude={'display_name'})))[:1000]))
    try: db.commit()
    except IntegrityError: db.rollback();fail(409,'Username is already in use')
    return user_data(auth[0])

def address_data(row): return {key:getattr(row,key) for key in ('id',*Address.model_fields)}
@router.get('/addresses')
def addresses(auth=Depends(require), db: Session=Depends(get_db)):
    return [address_data(a) for a in db.scalars(select(models.UserAddress).where(models.UserAddress.user_id==auth[0].id).order_by(models.UserAddress.is_default.desc(),models.UserAddress.id))]
@router.put('/addresses/{address_id}')
def save_address(address_id: int, body: Address, auth=Depends(mutate), db: Session=Depends(get_db)):
    if any(not getattr(body,k) for k in ('first_name','last_name','phone','country','city','street')): fail(422,'Complete the recipient and address information')
    if not body.postal_code: fail(422,'Enter the postal code')
    if not body.region: fail(422,'Enter the region or province')
    row=db.get(models.UserAddress,address_id) if address_id else models.UserAddress(user_id=auth[0].id)
    if not row or row.user_id!=auth[0].id: fail(404,'Address not found')
    data=body.model_dump()
    # Exactly one default once a user has addresses: the first saved address becomes it.
    other_default=db.scalar(select(models.UserAddress.id).where(models.UserAddress.user_id==auth[0].id,models.UserAddress.is_default.is_(True),models.UserAddress.id!=(row.id or 0)))
    if other_default is None: data['is_default']=True
    if data['is_default']: db.execute(update(models.UserAddress).where(models.UserAddress.user_id==auth[0].id).values(is_default=False))
    for key,value in data.items(): setattr(row,key,value)
    db.add(row)
    db.add(models.Activity(actor_id=auth[0].id,action='address.saved',subject=f'user:{auth[0].id}',detail=data['label'] or data['city']))
    try: db.commit()
    except IntegrityError: db.rollback();fail(409,'Address changed concurrently. Try again.')
    return address_data(row)
@router.delete('/addresses/{address_id}')
def remove_address(address_id: int, auth=Depends(mutate), db: Session=Depends(get_db)):
    row=db.get(models.UserAddress,address_id)
    if not row or row.user_id!=auth[0].id: fail(404,'Address not found')
    was_default=row.is_default;db.delete(row);db.flush()
    db.add(models.Activity(actor_id=auth[0].id,action='address.deleted',subject=f'user:{auth[0].id}',detail=row.label or row.city))
    if was_default:
        oldest=db.scalar(select(models.UserAddress).where(models.UserAddress.user_id==auth[0].id).order_by(models.UserAddress.id))
        if oldest: oldest.is_default=True
    db.commit();return {'ok':True}

class ChangeEmail(EmailInput):
    current_password: str = Field(max_length=128)
CHANGE_MESSAGE='If this address can be used, a confirmation link is on its way to it. Your current address stays active until then.'
@router.post('/auth/change-email')
def change_email(body: ChangeEmail, request: Request, auth=Depends(mutate), db: Session=Depends(get_db)):
    session_limit(request,'change-email',auth[0].id)
    user=auth[0]
    if user.password_hash.startswith('!'): fail(409,'Set a password first, then you can change your email.')
    try: hasher.verify(user.password_hash,body.current_password)
    except (VerifyMismatchError,InvalidHashError): fail(401,'Incorrect current password')
    email=str(body.email).lower()
    if email==user.email:
        if user.email_verified:return {'message':'This is already your email address.','pending_email':user.pending_email}
        # Someone retyping their own unverified address wants it confirmed.
        queued=email_service.enqueue_limited(db,'verify_email',email,user.id);db.commit();email_service.wake()
        return {'message':f'This is already your address, and it is not verified yet. A verification email is on its way to {email}.' if queued else 'We sent you a verification email a moment ago. Check your inbox, or try again in a minute.','pending_email':user.pending_email,**email_service.capture_info()}
    # Asking again within the cooldown keeps the link already sent. Otherwise earlier links stop working.
    if user.pending_email!=email or not email_service.recently_queued(db,'email_change',email):
        db.execute(delete(models.AccountToken).where(models.AccountToken.user_id==user.id,models.AccountToken.purpose=='email_change'))
        email_service.cancel_pending(db,user.id,('email_change',))
        user.pending_email=email
        owner=db.scalar(select(models.User.id).where(models.User.email==email))
        # A taken address looks the same from here: its owner is told, and no link exists to confirm it.
        if owner: email_service.enqueue_limited(db,'account_exists',email,owner)
        else: email_service.enqueue_limited(db,'email_change',email,user.id)
        db.commit();email_service.wake()
    return {'message':CHANGE_MESSAGE,'pending_email':email,**email_service.capture_info()}

@router.delete('/auth/change-email')
def cancel_email_change(auth=Depends(mutate), db: Session=Depends(get_db)):
    auth[0].pending_email=None
    db.execute(delete(models.AccountToken).where(models.AccountToken.user_id==auth[0].id,models.AccountToken.purpose=='email_change'))
    email_service.cancel_pending(db,auth[0].id,('email_change',))
    db.commit();return {'message':'Email change cancelled.','pending_email':None}

class Preferences(BaseModel):
    theme: Literal['light','dark','system']
@router.put('/preferences')
def preferences(body: Preferences,auth=Depends(mutate),db: Session=Depends(get_db)):
    auth[0].theme=body.theme;db.commit();return user_data(auth[0])

from fastapi import UploadFile, File
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
import io
from .avatars import AvatarChoice, assign_picture, picture_data, PHOTO_NAME
@router.post('/profile/avatar')
async def upload_avatar(file: UploadFile=File(...),auth=Depends(mutate),db: Session=Depends(get_db)):
    data=await file.read(2*1024*1024+1)
    if len(data)>2*1024*1024:fail(413,'Avatar must be no larger than 2 MB')
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in ('PNG','JPEG','WEBP') or img.width*img.height>16000000:fail(422,'Use PNG, JPEG or WebP under 16 megapixels')
            img.load();img=ImageOps.exif_transpose(img).convert('RGB');img.thumbnail((512,512))
            output=io.BytesIO();img.save(output,format='WEBP',quality=85)
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):fail(422,'Invalid image')
    directory=config.UPLOAD_DIR.parent/'avatars';directory.mkdir(parents=True,exist_ok=True)
    name=secrets.token_hex(24)+'.webp';path=directory/name;path.write_bytes(output.getvalue())
    old=picture_data(auth[0].profile_picture).get('file')
    assign_picture(auth[0], {'kind':'photo','file':name})
    try:db.commit()
    except Exception:db.rollback();path.unlink(missing_ok=True);raise
    if old:(directory/old).unlink(missing_ok=True)
    return user_data(auth[0])
@router.put('/profile/avatar-style')
def save_avatar_style(body:AvatarChoice,auth=Depends(mutate),db: Session=Depends(get_db)):
    """Replace the active picture atomically; uploads use the same selection property."""
    assign_picture(auth[0], body.model_dump(exclude_none=True));db.commit()
    return user_data(auth[0])
@router.get('/profile/avatar')
def get_avatar(user_id:int|None=None,auth=Depends(require),db: Session=Depends(get_db)):
    user=auth[0]
    if user_id is not None and user_id!=user.id:
        if user.role!='admin':fail(403,'This profile picture is not accessible')
        user=db.get(models.User,user_id)
        if user is None:fail(404,'User not found')
    name=picture_data(user.profile_picture).get('file')
    if not name or not re.fullmatch(PHOTO_NAME,name):fail(404,'No profile photo')
    path=config.UPLOAD_DIR.parent/'avatars'/name
    if not path.is_file():fail(404,'No profile photo')
    return FileResponse(path,media_type='image/webp',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
@router.delete('/profile/avatar')
def delete_avatar(auth=Depends(mutate),db: Session=Depends(get_db)):
    old=picture_data(auth[0].profile_picture).get('file')
    assign_picture(auth[0], {'kind':'initials'});db.commit()
    if old:(config.UPLOAD_DIR.parent/'avatars'/old).unlink(missing_ok=True)
    return user_data(auth[0])
