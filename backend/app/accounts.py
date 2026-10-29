"""Account settings and single-use, hashed inbox verification/reset tokens."""
import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Literal
import pycountry
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from sqlalchemy import select, delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from . import models, schemas, config
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

# SMTP acceptance is not an assertion of final inbox delivery.
def issue_token(db, user, purpose):
    latest=db.scalar(select(models.AccountToken).where(models.AccountToken.user_id==user.id,models.AccountToken.purpose==purpose).order_by(models.AccountToken.created_at.desc()))
    if latest and latest.created_at.replace(tzinfo=timezone.utc)>datetime.now(timezone.utc)-timedelta(seconds=60):
        return 'Please wait 60 seconds before requesting another message.'
    token=secrets.token_urlsafe(32)
    db.execute(delete(models.AccountToken).where(models.AccountToken.user_id==user.id,models.AccountToken.purpose==purpose))
    db.add(models.AccountToken(token_hash=digest(token),user_id=user.id,purpose=purpose,expires_at=datetime.now(timezone.utc)+timedelta(minutes=60)))
    db.commit()
    base=os.getenv('PUBLIC_BASE_URL','http://localhost:8080').rstrip('/')
    message=EmailMessage();message['To']=user.email;message['From']=os.getenv('SMTP_FROM','OpenLabs3D <noreply@localhost>')
    message['Subject']='Verify your OpenLabs3D email' if purpose=='verify' else 'Reset your OpenLabs3D password'
    message.set_content(f"Open this link within 60 minutes:\n{base}/#{purpose}?token={token}\nIgnore this message if you did not request it.")
    transport=os.getenv('MAIL_TRANSPORT','file' if config.APP_ENV=='development' else 'smtp')
    try:
        if transport=='file' and config.APP_ENV=='development':
            directory=Path(os.getenv('MAIL_OUTBOX',str(config.UPLOAD_DIR.parent/'mail')))
            directory.mkdir(parents=True,exist_ok=True,mode=0o700)
            path=directory/(secrets.token_hex(16)+'.eml')
            with open(path,'x',opener=lambda path,flags:os.open(path,flags,0o600)) as stream: stream.write(message.as_string())
            return 'Saved to the local development mailbox. No real email was sent.'
        if transport!='smtp': raise ValueError('Invalid email transport')
        host=os.environ['SMTP_HOST']; port=int(os.getenv('SMTP_PORT','587'))
        with smtplib.SMTP(host,port,timeout=10) as smtp:
            smtp.ehlo()
            if os.getenv('SMTP_STARTTLS','true')=='true': smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
            if os.getenv('SMTP_USERNAME'): smtp.login(os.environ['SMTP_USERNAME'],os.environ['SMTP_PASSWORD'])
            smtp.send_message(message)
        return 'Accepted by the SMTP server; check your inbox.'
    except (OSError, smtplib.SMTPException, KeyError, ValueError):
        db.execute(delete(models.AccountToken).where(models.AccountToken.token_hash==digest(token)));db.commit()
        return 'Email could not be sent. Please retry or contact the administrator.'

def consume(db, token, purpose):
    # DELETE RETURNING makes concurrent redemption single-use.
    uid=db.execute(delete(models.AccountToken).where(models.AccountToken.token_hash==digest(token),models.AccountToken.purpose==purpose,models.AccountToken.expires_at>datetime.now(timezone.utc)).returning(models.AccountToken.user_id)).scalar_one_or_none()
    user=db.get(models.User,uid) if uid else None
    if not user or not user.active: db.rollback();fail(400,'Invalid or expired link')
    return user

@router.get('/countries')
def countries(): return sorted([{'code':c.alpha_2,'name':c.name} for c in pycountry.countries],key=lambda c:c['name'])

@router.get('/auth/username')
def available(username: str, auth=Depends(current), db: Session=Depends(get_db)):
    if not re.fullmatch(r'[A-Za-z0-9_]{3,32}',username): return {'available':False}
    owner=db.scalar(select(models.User.id).where(models.User.username==username))
    return {'available':owner is None or bool(auth and owner==auth[0].id)}

@router.post('/auth/resend-verification')
def resend(request: Request, auth=Depends(mutate), db: Session=Depends(get_db)):
    session_limit(request,'resend-verification')
    return {'message':'Email already verified.' if auth[0].email_verified else issue_token(db,auth[0],'verify')}

@router.post('/auth/verify')
def verify(body: TokenInput, request: Request, db: Session=Depends(get_db)):
    session_limit(request,'verify')
    user=consume(db,body.token,'verify');user.email_verified=True;db.commit()
    return {'message':'Email verified. You can now use marketplace services.'}

@router.post('/auth/forgot-password')
def forgot(body: EmailInput, request: Request, db: Session=Depends(get_db)):
    session_limit(request,'forgot-password')
    user=db.scalar(select(models.User).where(models.User.email==str(body.email).lower(),models.User.active.is_(True)))
    if user: issue_token(db,user,'reset')
    return {'message':'If this account exists, a reset message has been requested.'}

@router.post('/auth/reset-password')
def reset(body: ResetPassword, request: Request, db: Session=Depends(get_db)):
    session_limit(request,'reset-password')
    user=consume(db,body.token,'reset');user.password_hash=hasher.hash(body.password)
    db.execute(delete(models.LoginSession).where(models.LoginSession.user_id==user.id));db.commit()
    return {'message':'Password reset. Sign in with your new password.'}

@router.post('/auth/change-password')
def change_password(body: PasswordChange, request: Request, auth=Depends(mutate), db: Session=Depends(get_db)):
    session_limit(request,'change-password')
    try: hasher.verify(auth[0].password_hash,body.current_password)
    except (VerifyMismatchError,InvalidHashError): fail(401,'Incorrect current password')
    auth[0].password_hash=hasher.hash(body.password)
    db.execute(delete(models.AccountToken).where(models.AccountToken.user_id==auth[0].id,models.AccountToken.purpose=='reset'))
    db.execute(delete(models.LoginSession).where(models.LoginSession.user_id==auth[0].id,models.LoginSession.token_hash!=auth[1].token_hash));db.commit()
    return {'message':'Password changed. Other sessions have been signed out.'}

@router.patch('/profile')
def profile(body: Profile, auth=Depends(mutate), db: Session=Depends(get_db)):
    for key,value in body.model_dump(exclude_unset=True).items():
        if value is not None: setattr(auth[0],key,value)
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
    row=db.get(models.UserAddress,address_id) if address_id else models.UserAddress(user_id=auth[0].id)
    if not row or row.user_id!=auth[0].id: fail(404,'Address not found')
    data=body.model_dump()
    # Exactly one default once a user has addresses: the first saved address becomes it.
    other_default=db.scalar(select(models.UserAddress.id).where(models.UserAddress.user_id==auth[0].id,models.UserAddress.is_default.is_(True),models.UserAddress.id!=(row.id or 0)))
    if other_default is None: data['is_default']=True
    if data['is_default']: db.execute(update(models.UserAddress).where(models.UserAddress.user_id==auth[0].id).values(is_default=False))
    for key,value in data.items(): setattr(row,key,value)
    db.add(row)
    try: db.commit()
    except IntegrityError: db.rollback();fail(409,'Address changed concurrently. Try again.')
    return address_data(row)
@router.delete('/addresses/{address_id}')
def remove_address(address_id: int, auth=Depends(mutate), db: Session=Depends(get_db)):
    row=db.get(models.UserAddress,address_id)
    if not row or row.user_id!=auth[0].id: fail(404,'Address not found')
    was_default=row.is_default;db.delete(row);db.flush()
    if was_default:
        oldest=db.scalar(select(models.UserAddress).where(models.UserAddress.user_id==auth[0].id).order_by(models.UserAddress.id))
        if oldest: oldest.is_default=True
    db.commit();return {'ok':True}

class ChangeEmail(EmailInput):
    current_password: str = Field(max_length=128)
@router.post('/auth/change-email')
def change_email(body: ChangeEmail, request: Request, auth=Depends(mutate), db: Session=Depends(get_db)):
    session_limit(request,'change-email')
    try: hasher.verify(auth[0].password_hash,body.current_password)
    except (VerifyMismatchError,InvalidHashError): fail(401,'Incorrect current password')
    email=str(body.email).lower()
    if email==auth[0].email:return {'message':'Email unchanged.'}
    auth[0].email=email;auth[0].email_verified=False
    db.execute(delete(models.AccountToken).where(models.AccountToken.user_id==auth[0].id))
    db.execute(delete(models.LoginSession).where(models.LoginSession.user_id==auth[0].id,models.LoginSession.token_hash!=auth[1].token_hash))
    try: db.commit()
    except IntegrityError:db.rollback();fail(409,'Email is already in use')
    return {'message':issue_token(db,auth[0],'verify')}

class Preferences(BaseModel):
    theme: Literal['light','dark','system']
@router.put('/preferences')
def preferences(body: Preferences,auth=Depends(mutate),db: Session=Depends(get_db)):
    auth[0].theme=body.theme;db.commit();return user_data(auth[0])

from fastapi import UploadFile, File
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
import io
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
    old=auth[0].avatar;auth[0].avatar=name
    try:db.commit()
    except Exception:db.rollback();path.unlink(missing_ok=True);raise
    if old:(directory/old).unlink(missing_ok=True)
    return user_data(auth[0])
@router.get('/profile/avatar')
def get_avatar(auth=Depends(require)):
    name=auth[0].avatar
    if not name or not re.fullmatch(r'[a-f0-9]{48}\.webp',name):fail(404,'No avatar')
    path=config.UPLOAD_DIR.parent/'avatars'/name
    if not path.is_file():fail(404,'No avatar')
    return FileResponse(path,media_type='image/webp',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
@router.delete('/profile/avatar')
def delete_avatar(auth=Depends(mutate),db: Session=Depends(get_db)):
    old=auth[0].avatar;auth[0].avatar='';db.commit()
    if old:(config.UPLOAD_DIR.parent/'avatars'/old).unlink(missing_ok=True)
    return user_data(auth[0])
