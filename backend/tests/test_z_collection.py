import os, tempfile, sys
_test_root=tempfile.TemporaryDirectory()
os.environ.setdefault("DATABASE_URL", "sqlite:///"+_test_root.name+"/test.db")
os.environ.setdefault("UPLOAD_DIR", _test_root.name+"/uploads")
import io
import uuid
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, func
from app.main import app, hasher
from app.database import Base, SessionLocal, engine
from app.models import User, Listing, Activity, OrderItem
from app.seed_collection import seed

@pytest.fixture
def collection(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import get_db
    from app import config
    isolated=create_engine('sqlite:///'+str(tmp_path/'collection.db'),connect_args={'check_same_thread':False})
    factory=sessionmaker(bind=isolated)
    monkeypatch.setattr(sys.modules[__name__], 'SessionLocal', factory)
    monkeypatch.setattr(config, 'UPLOAD_DIR', tmp_path/'uploads')
    def test_db():
        with factory() as db: yield db
    app.dependency_overrides[get_db]=test_db
    Base.metadata.create_all(isolated)
    email=uuid.uuid4().hex+'@example.org'
    with SessionLocal() as db:
        admin=User(email=email,display_name='Collection QA',password_hash=hasher.hash('collection password'),role='admin');db.add(admin);db.commit();seed(db,admin);seed(db,admin)
    client=TestClient(app);r=client.post('/api/auth/login',json={'email':email,'password':'collection password'});client.headers['X-CSRF-Token']=r.json()['csrf_token']
    yield client
    app.dependency_overrides.clear()
    isolated.dispose()

def test_seed_and_public_filters(collection):
    with SessionLocal() as db: assert db.scalar(select(func.count()).select_from(Listing).where(Listing.collection_key.is_not(None)))==3
    public=TestClient(app)
    items=public.get('/api/listings?featured=true&per_page=3').json()['items']
    assert len(items)==3 and all(p['status']=='approved' and len(p['color_images'])==3 for p in items)

def test_publish_webp_drafts_and_permissions(collection):
    c=collection
    payload=dict(title='QA WebP',category='Tube racks',description='QA',price_cents=2000,material='PETG',dimensions='100 mm',compatibility='test',listing_type='official')
    p=c.post('/api/listings',json=payload).json();id=p['id'];assert p['status']=='draft'
    public=TestClient(app);assert public.get(f'/api/listings/{id}').status_code==404
    f=io.BytesIO();Image.new('RGBA',(90,45),(10,80,120,100)).save(f,format='WEBP',lossless=True)
    r=c.post(f'/api/listings/{id}/images',files={'files':('image.webp',f.getvalue(),'image/webp')});assert r.status_code==201
    url=r.json()['images'][0]['url'];image=c.get(url);assert image.headers['content-type']=='image/webp'
    decoded=Image.open(io.BytesIO(image.content));assert decoded.size==(90,45) and 'A' in decoded.getbands()
    r=c.post(f'/api/listings/{id}/publish');assert r.json()['status']=='approved' and r.json()['approved_by']
    assert public.get(f'/api/listings/{id}').status_code==200
    with SessionLocal() as db: assert not db.scalar(select(Activity).where(Activity.subject==f'listing:{id}',Activity.action=='listing.submitted'))
    c.delete(f'/api/listings/{id}');assert public.get(f'/api/listings/{id}').status_code==404
    buyer=TestClient(app);r=buyer.post('/api/auth/register',json={'email':uuid.uuid4().hex+'@example.org','password':'collection password','display_name':'Buyer'});buyer.headers['X-CSRF-Token']=r.json()['csrf_token']
    assert buyer.post('/api/listings',json=payload).status_code==403
    payload['listing_type']='community';p=buyer.post('/api/listings',json=payload).json()
    assert buyer.post(f"/api/listings/{p['id']}/publish").status_code==403
    assert buyer.post(f"/api/listings/{p['id']}/submit").json()['status']=='pending'
    assert public.get(f"/api/listings/{p['id']}").status_code==404

def test_order_color_snapshot(collection):
    c=collection;p=c.get('/api/listings?featured=true').json()['items'][0]
    body={'idempotency_key':uuid.uuid4().hex,'contact':'QA','address':'QA','items':[{'listing_id':p['id'],'quantity':1,'expected_price_cents':p['price_cents'],'color':color} for color in ['cream','signal-red']]}
    r=c.post('/api/orders',json=body);assert r.status_code==201,r.text
    assert {i['color'] for i in r.json()['items']}=={'cream','signal-red'}
    assert {j['item']['color'] for j in r.json()['jobs']}=={'cream','signal-red'}
    body['idempotency_key']=uuid.uuid4().hex;body['items'][0]['color']='unknown';assert c.post('/api/orders',json=body).status_code==422
