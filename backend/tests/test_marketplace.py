import io
import os
from pathlib import Path
import tempfile

root = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(root.name) / 'test.db')
os.environ['UPLOAD_DIR'] = str(Path(root.name) / 'uploads')
from fastapi.testclient import TestClient
from PIL import Image
from app.database import Base, engine, SessionLocal
from app.main import app, hasher
from app.models import User, Category

Base.metadata.create_all(engine)
with SessionLocal() as db:
    db.add(Category(name='Tube racks',sort_order=0,active=True))
    db.commit()

def register(client, email, host=False):
    r=client.post('/api/auth/register',json={'email':email,'password':'LongPasswordForTest2026','display_name':email.split('@')[0], 'username':email.split('@')[0].replace('-','_')})
    assert r.status_code==201, r.text
    from app.models import HostApplication
    from sqlalchemy import select
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==email));user.email_verified=True
        user.first_name='Test';user.last_name='User';user.phone='+39 011 1234567';user.country='IT';user.city='Torino'
        if host:
            user.role='host';db.add(HostApplication(user_id=user.id,status='approved'))
        db.commit()
    return r.json()['csrf_token']
def headers(token): return {'X-CSRF-Token':token}
def picture():
    f=io.BytesIO(); Image.new('RGB',(32,32),'red').save(f,format='PNG'); return f.getvalue()
def test_complete_marketplace():
    owner, stranger, admin, anonymous = [TestClient(app) for _ in range(4)]
    token=register(owner,'owner@example.org',host=True); other=register(stranger,'other@example.org')
    with SessionLocal() as db:
        db.add(User(email='admin@example.org',display_name='Admin',password_hash=hasher.hash('admin test password'),role='admin',email_verified=True));db.commit()
    login=admin.post('/api/auth/login',json={'email':'admin@example.org','password':'admin test password'})
    assert login.status_code==200; admin_token=login.json()['csrf_token']
    assert owner.get('/api/auth/me').status_code==200
    assert anonymous.post('/api/listings',json={}).status_code==401
    assert owner.post('/api/listings',json={}).status_code==403
    assert owner.post('/api/listings',json={'owner_id':2},headers=headers(token)).status_code==422
    assert owner.post('/api/listings',json={'listing_type':'official'},headers=headers(token)).status_code==403
    r=owner.post('/api/listings',json={'title':'Test rack','description':'A rack','category':'Tube racks','price_cents':1299,'material':'PETG','dimensions':'10 mm','compatibility':'Tubes'},headers=headers(token)); assert r.status_code==201, r.text
    id=r.json()['id']
    assert stranger.get(f'/api/listings/{id}').status_code==404
    assert stranger.patch(f'/api/listings/{id}',json={'title':'stolen'},headers=headers(other)).status_code==403
    assert owner.patch(f'/api/listings/{id}',json={'title':'Updated rack'},headers=headers(token)).json()['title']=='Updated rack'
    assert owner.post(f'/api/listings/{id}/images',files={'files':('fake.png',b'not an image','image/png')},headers=headers(token)).status_code==422
    uploaded=owner.post(f'/api/listings/{id}/images',files={'files':('rack.png',picture(),'image/png')},headers=headers(token)); assert uploaded.status_code==201, uploaded.text
    image=uploaded.json()['images'][0]['id']
    assert stranger.get(f'/api/listings/{id}/images/{image}').status_code==404
    assert owner.get(f'/api/listings/{id}/images/{image}').status_code==200
    upload_test_cad(owner,id,token)
    assert owner.post(f'/api/listings/{id}/submit',headers=headers(token)).json()['status']=='pending'
    assert owner.post(f'/api/admin/listings/{id}/approve',headers=headers(token)).status_code==403
    assert admin.post(f'/api/admin/listings/{id}/approve',headers=headers(admin_token)).json()['status']=='approved'
    assert anonymous.get('/api/listings').json()['total']==1
    assert anonymous.get(f'/api/listings/{id}/images/{image}').status_code==200
    # A new client and database connection see persistent state and files.
    engine.dispose()
    assert TestClient(app).get(f'/api/listings/{id}').json()['title']=='Updated rack'
    assert TestClient(app).get(f'/api/listings/{id}/images/{image}').status_code==200
    assert owner.patch(f'/api/listings/{id}',json={'description':'Changed'},headers=headers(token)).json()['status']=='pending'
    assert anonymous.get(f'/api/listings/{id}').status_code==404
    assert anonymous.get(f'/api/listings/{id}/images/{image}').status_code==404
    assert owner.delete(f'/api/listings/{id}',headers=headers(token)).json()['status']=='archived'
    assert owner.post('/api/auth/logout',headers=headers(token)).status_code==200
    assert owner.get('/api/auth/me').status_code==401
    assert owner.post('/api/auth/login',json={'email':'owner@example.org','password':'wrong'}).status_code==401
    assert owner.post('/api/auth/login',json={'email':'owner@example.org','password':'LongPasswordForTest2026'}).status_code==200

def test_admin_cannot_approve_own_community_listing():
    client=TestClient(app)
    token=client.post('/api/auth/login',json={'email':'admin@example.org','password':'admin test password'}).json()['csrf_token']
    data={'title':'Own','description':'Description','category':'Tube racks','price_cents':1,'material':'PLA','dimensions':'1','compatibility':'x'}
    assert client.post('/api/listings',json=data,headers=headers(token)).status_code==403

def test_image_limits_order_and_origin():
    client=TestClient(app)
    token=register(client,'pictures@example.org',host=True)
    id=client.post('/api/listings',json={},headers=headers(token)).json()['id']
    files=[('files',(f'{i}.png',picture(),'image/png')) for i in range(2)]
    uploaded=client.post(f'/api/listings/{id}/images',files=files,headers=headers(token)); assert uploaded.status_code==201
    images=uploaded.json()['images']; ids=[i['id'] for i in images]
    assert client.put(f'/api/listings/{id}/images/order',json={'image_ids':ids[::-1]},headers=headers(token)).json()['images'][0]['id']==ids[1]
    assert client.put(f'/api/listings/{id}/images/order',json={'image_ids':[ids[0],ids[0]]},headers=headers(token)).status_code==422
    assert client.post(f'/api/listings/{id}/images',files={'files':('large.png',b'a'*(5*1024*1024+1),'image/png')},headers=headers(token)).status_code==413
    assert client.patch(f'/api/listings/{id}',json={'title':'bad'},headers={**headers(token),'Origin':'https://other.example'}).status_code==403
    assert client.delete(f'/api/listings/{id}/images/{ids[0]}',headers=headers(token)).status_code==200
    assert client.get(f'/api/listings/{id}/images/{ids[0]}').status_code==404

def test_compose_configuration():
    import shutil, subprocess
    import pytest
    if not shutil.which('docker'): pytest.skip('Docker CLI unavailable')
    project=Path(__file__).resolve().parents[2]
    env={**os.environ,'SITE_DOMAIN':'example.com'}
    for args in ([],['-f','compose.yaml','-f','compose.production.yaml']):
        result=subprocess.run(['docker','compose',*args,'config','--quiet'],cwd=project,env=env,capture_output=True,text=True)
        assert result.returncode==0, result.stderr

def test_stale_review_cannot_overwrite_changed_listing():
    import pytest
    from sqlalchemy.orm.exc import StaleDataError
    from app.models import Listing
    client=TestClient(app)
    token=register(client,'race@example.org',host=True)
    id=client.post('/api/listings',json={},headers=headers(token)).json()['id']
    with SessionLocal() as first, SessionLocal() as second:
        reviewer=first.get(Listing,id); editor=second.get(Listing,id)
        editor.title='New title'; second.commit()
        reviewer.status='approved'
        with pytest.raises(StaleDataError): first.commit()

def test_catalogue_filters_before_pagination():
    from datetime import datetime, timezone
    from app.models import Listing
    with SessionLocal() as db:
        owner = db.query(User).filter_by(email='owner@example.org').one()
        for n in range(14):
            db.add(Listing(owner_id=owner.id, title=f'Filtered {n}', description='test', category='Filter test',
                           price_cents=1000 if n == 0 else 5000, material='PETG' if n == 0 else 'PLA',
                           dimensions='25 × 20 mm' if n == 0 else '100 × 20 mm', compatibility='test',
                           status='approved', published_at=datetime.now(timezone.utc)))
        db.commit()
    client = TestClient(app)
    response = client.get('/api/listings', params={'category':'Filter test', 'material':'petg', 'max_price_cents':1500, 'max_width':30, 'per_page':1})
    assert response.status_code == 200
    assert response.json()['total'] == 1
    assert response.json()['items'][0]['title'] == 'Filtered 0'

def test_upload_after_deletion_preserves_order():
    client=TestClient(app)
    token=register(client,'ordering@example.org',host=True)
    listing_id=client.post('/api/listings',json={},headers=headers(token)).json()['id']
    files=[('files',(f'{i}.png',picture(),'image/png')) for i in range(3)]
    images=client.post(f'/api/listings/{listing_id}/images',files=files,headers=headers(token)).json()['images']
    assert client.delete(f'/api/listings/{listing_id}/images/{images[1]["id"]}',headers=headers(token)).status_code == 200
    result=client.post(f'/api/listings/{listing_id}/images',files={'files':('new.png',picture(),'image/png')},headers=headers(token))
    assert result.status_code == 201
    assert [image['sort_order'] for image in result.json()['images']] == [0, 2, 3]


def upload_test_cad(client,listing_id,token):
    import struct
    data=b'test'.ljust(80,b'\0')+struct.pack('<I',1)+struct.pack('<12fH',0,0,1,0,0,0,10,0,0,0,10,10,0)
    result=client.post(f'/api/listings/{listing_id}/cad',files={'file':('test.stl',data)},headers=headers(token))
    assert result.status_code==200,result.text
