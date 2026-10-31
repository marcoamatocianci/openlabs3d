"""Custom tool requests: a researcher describes a problem, attaches references and tracks the review.
Requests are separate from marketplace orders; nothing here creates listings, prices, jobs or payments."""
import io,json,re,secrets,struct,zipfile
from pathlib import Path,PurePosixPath
from xml.etree import ElementTree as ET
from fastapi import APIRouter,Depends,Form,UploadFile,File,Response
from fastapi.responses import FileResponse
from PIL import Image,ImageOps,UnidentifiedImageError
from pydantic import ValidationError
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session,selectinload
from . import models,schemas,config
from .database import get_db
from .main import require,mutate,admin,admin_mutate,fail,throttle
from .mesh import inspect_mesh

router=APIRouter(prefix='/api')
STORAGE=config.UPLOAD_DIR.parent/'requests'
MAX_FILES=6
MAX_TOTAL=25*1024*1024  # below the proxy's 30 MB request body limit
LIMITS={'model':20*1024*1024,'image':10*1024*1024,'document':10*1024*1024}
KINDS={'.stl':'model','.3mf':'model','.png':'image','.jpg':'image','.jpeg':'image','.webp':'image','.pdf':'document'}
MEDIA={'.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.pdf':'application/pdf'}
STORED=re.compile(r'[a-f0-9]{48}\.(stl|3mf|png|jpg|webp|pdf)')

def reference(r):return f'CR-{r.id:05d}'
def file_data(r,f):return {'id':f.id,'filename':f.filename,'kind':f.kind,'size':f.size,'url':f'/api/custom-requests/{r.id}/files/{f.id}'}
def request_data(r,staff=False):
    data={**{k:getattr(r,k) for k in ('id','title','application','dimensions','compatibility','quantity','material','requirements','status','created_at','updated_at')},
          'reference':reference(r),'conditions':json.loads(r.conditions or '[]'),'files':[file_data(r,f) for f in r.files]}
    if staff:
        u=r.user;data['admin_notes']=r.admin_notes
        data['user']={k:getattr(u,k) for k in ('id','display_name','username','email','role','phone','city','country')}
    return data
def load(db,request_id):
    r=db.scalar(select(models.CustomRequest).options(selectinload(models.CustomRequest.files),selectinload(models.CustomRequest.user)).where(models.CustomRequest.id==request_id))
    if not r:fail(404,'Request not found')
    return r
def visible(r,auth):
    # Other people's requests answer exactly like missing ones.
    if r.user_id!=auth[0].id and auth[0].role!='admin':fail(404,'Request not found')
    return r

def checked(name,data):
    """Validate one reference file by content, not only by extension. Images are re-encoded,
    which drops embedded metadata such as GPS positions."""
    ext=PurePosixPath(name).suffix.lower();kind=KINDS.get(ext)
    if not kind:fail(422,f'{name}: unsupported file type. Use STL, 3MF, PNG, JPEG, WebP or PDF.')
    if len(data)>LIMITS[kind]:fail(413,f'{name}: exceeds {LIMITS[kind]//(1024*1024)} MB')
    if not data:fail(422,f'{name}: the file is empty')
    if kind=='model':
        try:inspect_mesh(data,ext)
        except (ValueError,UnicodeError,zipfile.BadZipFile,ET.ParseError,KeyError,IndexError,struct.error):fail(422,f'{name}: not a readable STL or 3MF mesh')
        return kind,ext,data
    if kind=='document':
        if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-2048:]:fail(422,f'{name}: not a valid PDF document')
        return kind,ext,data
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in ('JPEG','PNG','WEBP') or img.width*img.height>20_000_000:fail(422,f'{name}: unsupported image or image dimensions')
            fmt=img.format;img.load();img=ImageOps.exif_transpose(img).convert('RGB' if fmt=='JPEG' else 'RGBA')
            img.thumbnail((3000,3000),Image.Resampling.LANCZOS);out=io.BytesIO();img.save(out,format=fmt,**({'quality':90} if fmt!='PNG' else {}))
            return kind,{'JPEG':'.jpg','PNG':'.png','WEBP':'.webp'}[fmt],out.getvalue()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):fail(422,f'{name}: not a readable image')

@router.post('/custom-requests',status_code=201)
async def submit(response:Response,payload:str=Form(...),files:list[UploadFile]=File(default=[]),auth=Depends(mutate),db:Session=Depends(get_db)):
    user=auth[0]
    if user.role=='admin':fail(403,'Administrators review custom requests in the admin workspace')
    if not user.email_verified:fail(403,'Verify your email before submitting a custom request')
    try:body=schemas.CustomRequestInput.model_validate_json(payload)
    except ValidationError as e:fail(422,'; '.join(f"{'.'.join(map(str,x['loc']))}: {x['msg']}" for x in e.errors(include_input=False))[:500])
    # A retried submission (double click, lost response) returns the request already stored.
    existing=db.scalar(select(models.CustomRequest.id).where(models.CustomRequest.user_id==user.id,models.CustomRequest.idempotency_key==body.idempotency_key))
    if existing:response.status_code=200;return request_data(load(db,existing))
    if body.material and not db.scalar(select(models.Material.name).where(models.Material.name==body.material)):fail(422,'Choose a listed material, or leave the preference open')
    if len(files)>MAX_FILES:fail(422,f'Attach at most {MAX_FILES} files')
    throttle(('custom-request',user.id),10,3600)
    prepared,total=[],0
    for f in files:
        name=Path(f.filename or 'file').name[:255] or 'file'
        data=await f.read(max(LIMITS.values())+1);total+=len(data)
        if total>MAX_TOTAL:fail(413,f'Attachments exceed {MAX_TOTAL//(1024*1024)} MB in total')
        prepared.append((name,*checked(name,data)))
    r=models.CustomRequest(user_id=user.id,conditions=json.dumps(body.conditions),**body.model_dump(exclude={'conditions'}))
    db.add(r);written=[]
    try:
        STORAGE.mkdir(parents=True,exist_ok=True)
        for name,kind,ext,data in prepared:
            stored=secrets.token_hex(24)+ext;path=STORAGE/stored;path.write_bytes(data);written.append(path)
            r.files.append(models.CustomRequestFile(filename=name,storage_path=stored,kind=kind,size=len(data)))
        db.flush();db.add(models.Activity(actor_id=user.id,action='request.submitted',subject=f'request:{r.id}',detail=r.title[:200]))
        db.commit()
    except IntegrityError:
        # Two identical submissions raced: keep the first and discard this copy's files.
        db.rollback()
        for path in written:path.unlink(missing_ok=True)
        existing=db.scalar(select(models.CustomRequest.id).where(models.CustomRequest.user_id==user.id,models.CustomRequest.idempotency_key==body.idempotency_key))
        if not existing:raise
        response.status_code=200;return request_data(load(db,existing))
    except Exception:
        db.rollback()
        for path in written:path.unlink(missing_ok=True)
        raise
    return request_data(load(db,r.id))

@router.get('/custom-requests')
def mine(auth=Depends(require),db:Session=Depends(get_db)):
    items=db.scalars(select(models.CustomRequest).options(selectinload(models.CustomRequest.files)).where(models.CustomRequest.user_id==auth[0].id).order_by(models.CustomRequest.created_at.desc(),models.CustomRequest.id.desc())).all()
    return [request_data(r) for r in items]
@router.get('/custom-requests/{request_id}')
def detail(request_id:int,auth=Depends(require),db:Session=Depends(get_db)):
    r=visible(load(db,request_id),auth);return request_data(r,staff=auth[0].role=='admin')
@router.get('/custom-requests/{request_id}/files/{file_id}')
def download(request_id:int,file_id:int,download:bool=False,auth=Depends(require),db:Session=Depends(get_db)):
    r=visible(load(db,request_id),auth);f=next((x for x in r.files if x.id==file_id),None)
    if not f or not STORED.fullmatch(f.storage_path):fail(404,'File not found')
    path=STORAGE/f.storage_path
    if not path.is_file():fail(404,'File not found')
    # Only images display inline; models and PDFs always download.
    inline=f.kind=='image' and not download
    return FileResponse(path,filename=f.filename,content_disposition_type='inline' if inline else 'attachment',media_type=MEDIA.get(path.suffix,'application/octet-stream') if inline or f.kind=='document' else 'application/octet-stream',
        headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store','Content-Security-Policy':"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"})

@router.get('/admin/custom-requests')
def admin_list(status:schemas.CustomRequestStatus|None=None,auth=Depends(admin),db:Session=Depends(get_db)):
    query=select(models.CustomRequest).options(selectinload(models.CustomRequest.files),selectinload(models.CustomRequest.user)).order_by(models.CustomRequest.created_at.desc(),models.CustomRequest.id.desc())
    if status:query=query.where(models.CustomRequest.status==status)
    return [request_data(r,staff=True) for r in db.scalars(query).all()]
@router.patch('/admin/custom-requests/{request_id}')
def review(request_id:int,body:schemas.CustomRequestReview,auth=Depends(admin_mutate),db:Session=Depends(get_db)):
    r=load(db,request_id);changes=[]
    if body.status is not None and body.status!=r.status:
        changes.append(f"Status: {body.status.replace('_',' ')}");r.status=body.status
    if body.admin_notes is not None and body.admin_notes.strip()!=r.admin_notes:
        changes.append('Internal notes updated');r.admin_notes=body.admin_notes.strip()
    if changes:
        db.add(models.Activity(actor_id=auth[0].id,action='request.updated',subject=f'request:{r.id}',detail='; '.join(changes)));db.commit()
    return request_data(load(db,r.id),staff=True)
def pending_count(db):return db.scalar(select(func.count()).select_from(models.CustomRequest).where(models.CustomRequest.status=='submitted'))
