from order_fixtures import provision_test_host, with_confirmation
"""Run independently: uses only an isolated temporary SQLite database and mailbox."""
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
import re
from email import policy
from email.parser import BytesParser
def mail_text(path): return BytesParser(policy=policy.default).parsebytes(path.read_bytes()).get_content()
root=tempfile.TemporaryDirectory(prefix='ol-accounts-')
os.environ['DATABASE_URL']='sqlite:///'+root.name+'/test.db'
os.environ['UPLOAD_DIR']=root.name+'/uploads'
os.environ['MAIL_OUTBOX']=root.name+'/mail'
os.environ['MAIL_TRANSPORT']='file'
os.environ['APP_ENV']='development'
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, rate
from app.database import Base,engine,SessionLocal
from app.models import User,AccountToken
Base.metadata.create_all(engine)

def signup(name='MarcoLab'):
    client=TestClient(app)
    response=client.post('/api/auth/register',json={'email':name+'@example.org','username':name,'password':'Openlabs2026'})
    assert response.status_code==201,response.text
    client.headers['X-CSRF-Token']=response.json()['csrf_token']
    return client

def token():
    path=max(Path(os.environ['MAIL_OUTBOX']).glob('*.eml'),key=lambda p:p.stat().st_mtime_ns)
    return re.search(r'token=([A-Za-z0-9_-]+)',mail_text(path))[1]

def test_accounts():
    client=TestClient(app)
    for password in ['openlabs2026','Openlabs','Open1']:
        assert client.post('/api/auth/register',json={'email':'valid@example.org','username':'Valid','password':password}).status_code==422
    assert client.post('/api/auth/register',json={'email':'invalid','username':'Valid','password':'Openlabs2026'}).status_code==422
    a=signup(); b=signup('OtherLab')
    for body in [{'email':'MarcoLab@example.org','username':'Different'},{'email':'different@example.org','username':'MARCOLAB'}]:
        assert client.post('/api/auth/register',json={**body,'password':'Openlabs2026'}).status_code==409
    assert not a.get('/api/auth/me').json()['user']['email_verified']
    assert a.post('/api/listings',json={}).status_code==403
    assert a.get('/api/auth/username?username=marcolab').json()['available']
    assert not b.get('/api/auth/username?username=marcolab').json()['available']
    assert b.patch('/api/profile',json={'username':'MARCOLAB'}).status_code==409
    data={'username':'MarcoLab','first_name':'Marco','last_name':'Rossi','phone':'+39 011 1234567','country':'IT','city':'Torino','street':'Via Roma 1','postal_code':'10100','region':'Piedmont'}
    assert a.patch('/api/profile',json=data).status_code==200
    assert a.get('/api/auth/me').json()['user']['first_name']=='Marco'
    assert a.patch('/api/profile',json={'username':'MarcoLab','country':'ZZ'}).status_code==422
    address={k:v for k,v in data.items() if k!='username'}
    r=a.put('/api/addresses/0',json={**address,'is_default':True});assert r.status_code==200,r.text
    aid=r.json()['id']
    assert b.get('/api/addresses').json()==[]
    assert b.delete('/api/addresses/'+str(aid)).status_code==404
    assert b.put('/api/addresses/'+str(aid),json=address).status_code==404
    assert a.put('/api/addresses/0',json={**address,'label':'Home','is_default':True}).status_code==200
    assert sum(x['is_default'] for x in a.get('/api/addresses').json())==1
    t=token() # OtherLab's verification email
    assert client.post('/api/auth/verify',json={'token':t}).status_code==200
    assert client.post('/api/auth/verify',json={'token':t}).status_code==400
    assert b.get('/api/auth/me').json()['user']['email_verified']
    with SessionLocal() as db:
        for row in db.scalars(select(AccountToken)):row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        db.commit()
    paths=sorted(Path(os.environ['MAIL_OUTBOX']).glob('*.eml'),key=lambda p:p.stat().st_mtime_ns)
    expired=re.search(r'token=([A-Za-z0-9_-]+)',mail_text(paths[0]))[1]
    assert client.post('/api/auth/verify',json={'token':expired}).status_code==400
    assert a.post('/api/auth/change-password',json={'current_password':'Openlabs2026','password':'weak'}).status_code==422
    assert a.post('/api/auth/change-password',json={'current_password':'wrong','password':'NewPassword2026'}).status_code==401
    assert a.post('/api/auth/change-password',json={'current_password':'Openlabs2026','password':'NewPassword2026'}).status_code==200
    assert client.post('/api/auth/forgot-password',json={'email':'MarcoLab@example.org'}).status_code==200
    assert client.post('/api/auth/reset-password',json={'token':token(),'password':'ResetPassword2026'}).status_code==200
    assert a.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/login',json={'email':'marcolab@example.org','password':'ResetPassword2026'}).status_code==200
    engine.dispose()
    assert client.get('/api/auth/me').json()['user']['city']=='Torino'
    assert len(client.get('/api/addresses').json())==2
    assert len(client.get('/api/countries').json())==249

def test_preferences_and_avatar():
    import io
    from PIL import Image
    rate.clear()
    client=signup('PreferencesLab')
    assert client.put('/api/preferences',json={'theme':'dark'}).status_code==200
    assert client.get('/api/auth/me').json()['user']['theme']=='dark'
    assert client.put('/api/preferences',json={'theme':'invalid'}).status_code==422
    assert client.post('/api/profile/avatar',files={'file':('fake.png',b'invalid','image/png')}).status_code==422
    assert client.post('/api/profile/avatar',files={'file':('big.png',b'x'*(2*1024*1024+1),'image/png')}).status_code==413
    image=io.BytesIO();Image.new('RGB',(50,50),'blue').save(image,format='PNG')
    assert client.post('/api/profile/avatar',files={'file':('../../photo.png',image.getvalue(),'image/png')}).status_code==200
    assert client.get('/api/profile/avatar').headers['content-type']=='image/webp'
    assert TestClient(app).get('/api/profile/avatar').status_code==401
    assert client.delete('/api/profile/avatar').status_code==200
    assert client.get('/api/profile/avatar').status_code==404

def test_address_defaults_and_labels():
    rate.clear();a=signup('AddressLab');b=signup('AddressOther')
    base={'first_name':'Ada','last_name':'Bench','phone':'+39 011 1234567','country':'IT','city':'Torino','street':'Via Nizza 1','postal_code':'10126','region':'Piedmont'}
    # Postal code and region are required for saved addresses.
    for missing in ('postal_code','region'):
        assert a.put('/api/addresses/0',json={**base,missing:''}).status_code==422
    assert a.get('/api/addresses').json()==[]
    first=a.put('/api/addresses/0',json={**base,'label':''});assert first.status_code==200,first.text
    assert first.json()['is_default'] and first.json()['label']==''
    second=a.put('/api/addresses/0',json={**base,'street':'Via Po 2','label':'  Work  '}).json()
    assert second['label']=='Work' and not second['is_default']
    assert a.put('/api/addresses/0',json={**base,'label':'x'*41}).status_code==422
    # Unsetting the only default keeps it; choosing another default moves it.
    assert a.put('/api/addresses/'+str(first.json()['id']),json={**base,'is_default':False}).json()['is_default']
    assert a.put('/api/addresses/'+str(second['id']),json={**base,'street':'Via Po 2','is_default':True}).json()['is_default']
    rows={x['id']:x for x in a.get('/api/addresses').json()}
    assert [x['id'] for x in rows.values() if x['is_default']]==[second['id']]
    assert b.put('/api/addresses/'+str(second['id']),json={**base,'is_default':True}).status_code==404
    assert a.delete('/api/addresses/'+str(second['id'])).status_code==200
    assert [x['is_default'] for x in a.get('/api/addresses').json()]==[True]
    assert a.patch('/api/profile',json={'username':'AddressLab','display_name':'  '}).status_code==422
    # A single public name: display_name follows the username and is no longer edited.
    assert a.patch('/api/profile',json={'username':'AddressLab','display_name':'Bench Lab'}).json()['display_name']=='AddressLab'
    assert a.patch('/api/profile',json={'username':'Address_Lab2'}).json()['display_name']=='Address_Lab2'

def test_country_locations():
    client=TestClient(app)
    italy=client.get('/api/countries/it/locations')
    assert italy.status_code==200 and 'max-age' in italy.headers['cache-control']
    data=italy.json()
    regions={r['name']:r['code'] for r in data['regions']}
    assert 'Piedmont' in regions and len(regions)==20
    turin=next(c for c in data['cities'] if c[0]=='Turin')
    assert turin[1]==regions['Piedmont'] and 'Torino' in turin[2]  # The local name is a search alias.
    assert any(c[0]=='Pinerolo' for c in data['cities'])  # Towns, not only large cities.
    assert all(c[1] in regions.values() or c[1]=='' for c in data['cities'])
    assert data['source'].startswith('GeoNames')
    assert client.get('/api/countries/ZZ/locations').status_code==404

def test_cart_checkout_isolation():
    from app.models import Listing,Order
    rate.clear();a=signup('BuyerAlpha');b=signup('BuyerBeta')
    with SessionLocal() as db:
        u=db.scalar(select(User).where(User.username=='BuyerAlpha'));u.email_verified=True
        p=Listing(owner_id=u.id,title='Test rack',price_cents=1000,material='PETG',status='approved',cad_dimensions='[10,10,10]');db.add(p);provision_test_host(db);db.commit();pid=p.id
    line={'listing_id':pid,'material':'PETG','color':'black','quantity':2}
    r=a.put('/api/cart',json=line);assert r.status_code==200,r.text
    assert b.get('/api/cart').json()==[]
    aid=a.get('/api/cart').json()[0]['id']
    assert b.delete('/api/cart/'+str(aid)).status_code==404
    assert b.put('/api/cart',json={**line,'quantity':1}).status_code==200
    engine.dispose()
    assert a.get('/api/cart').json()[0]['quantity']==2
    assert b.get('/api/cart').json()[0]['quantity']==1
    contact={'first_name':'A','last_name':'Buyer','phone':'+39 011 1234567','country':'IT','city':'Torino','street':'Via Roma 1'}
    body={'idempotency_key':'direct-test-key-1234','contact':contact,'direct':{**line,'quantity':1}}
    body=with_confirmation(a,body)
    response=a.post('/api/checkout',json=body);assert response.status_code==201,response.text
    assert response.json()['total_cents']==1000
    import json
    assert json.loads(response.json()['contact'])['email']=='buyeralpha@example.org'
    assert a.get('/api/cart').json()[0]['quantity']==2
    assert a.post('/api/checkout',json=body).json()['id']==response.json()['id']
    assert b.post('/api/checkout',json={**body,'idempotency_key':'unverified-key-123'}).status_code==403
    profile=a.get('/api/auth/me').json()['user']
    invalid=a.post('/api/checkout',json={**body,'idempotency_key':'invalid-email-key-123','contact':{**contact,'email':'invalid'}})
    assert invalid.status_code==422
    contact={**contact,'email':'alternate@example.org','first_name':'Alternative'}
    response=a.post('/api/checkout',json=with_confirmation(a,{'idempotency_key':'basket-test-key-1234','contact':contact}));assert response.status_code==201,response.text
    assert a.get('/api/cart').json()==[]
    assert len(b.get('/api/cart').json())==1
    assert 'Via Roma 1' in response.json()['address']
    snapshot=json.loads(response.json()['contact'])
    assert snapshot['email']=='alternate@example.org' and snapshot['first_name']=='Alternative'
    assert a.get('/api/auth/me').json()['user']==profile

def test_equipment():
    from app.equipment import seed_equipment
    from app.models import PrinterModel
    rate.clear();client=signup('EquipmentLab')
    with SessionLocal() as db:
        seed_equipment(db);seed_equipment(db)
        from app.equipment import CATALOGUE
        assert len(db.scalars(select(PrinterModel)).all())==len(CATALOGUE)
        user=db.scalar(select(User).where(User.username=='EquipmentLab'));user.email_verified=True
        for k,v in {'first_name':'Host','last_name':'Lab','phone':'+39 011 1234567','country':'IT','city':'Torino'}.items():setattr(user,k,v)
        db.commit()
    printers=client.get('/api/printer-catalogue').json();p=next(p for p in printers if p['model']=='P1S')
    body={'printers':[{'model_id':p['id'],'quantity':2,'technology':'RESIN','materials':['PLA'],'material_colors':{'PLA':{'black':'#000000'}}},{'manufacturer':'Custom','model':'One','technology':'RESIN','x':100,'y':100,'z':200,'quantity':1,'materials':['Standard Resin'],'material_colors':{'Standard Resin':{'black':'#000000'}}}],'submit':True}
    result=client.put('/api/host/equipment-application',json=body);assert result.status_code==200,result.text
    assert result.json()['total']==3
    assert result.json()['printers'][0]['technology']=='FDM'
    assert result.json()['printers'][0]['x']==256
    body['printers'][1]['x']=-1
    assert client.put('/api/host/equipment-application',json=body).status_code==422
    other=signup('EquipmentOther')
    assert other.get('/api/host/equipment').json()==[]

def test_role_permissions():
    from app.models import HostApplication
    rate.clear();buyer=signup('RoleBuyer');host=signup('RoleHost');admin=signup('RoleAdmin')
    with SessionLocal() as db:
        h=db.scalar(select(User).where(User.username=='RoleHost'));h.email_verified=True;h.role='host';db.add(HostApplication(user_id=h.id,status='approved'))
        a=db.scalar(select(User).where(User.username=='RoleAdmin'));a.role='admin';a.email_verified=True;db.commit()
    assert buyer.post('/api/listings',json={}).status_code==403
    assert host.post('/api/listings',json={}).status_code==201
    assert admin.post('/api/listings',json={}).status_code==403
    assert admin.post('/api/listings',json={'listing_type':'official'}).status_code==201
    assert admin.get('/api/orders').status_code==403
    assert buyer.get('/api/admin/users').status_code==403
    assert admin.get('/api/admin/users').status_code==200

def test_cad_and_product_lifecycle(monkeypatch):
    generated=[]
    monkeypatch.setattr("app.render_product.render_asset", lambda path: generated.append(path))
    import struct,io,zipfile
    from app.models import HostApplication,Category,Order,Listing
    from app.cad import inspect_mesh
    rate.clear();host=signup('CADHost');admin=signup('CADAdmin');buyer=signup('CADBuyer')
    with SessionLocal() as db:
        u=db.scalar(select(User).where(User.username=='CADHost'));u.role='host';u.email_verified=True;db.add(HostApplication(user_id=u.id,status='approved'))
        a=db.scalar(select(User).where(User.username=='CADAdmin'));a.role='admin';a.email_verified=True
        if not db.scalar(select(Category).where(Category.name=='CAD Test')):db.add(Category(name='CAD Test'))
        db.commit()
    fields={'title':'CAD rack','description':'Local test','category':'CAD Test','price_cents':1000,'material':'PLA','dimensions':'10 mm','compatibility':'Test'}
    r=host.post('/api/listings',json=fields);assert r.status_code==201,r.text
    pid=r.json()['id']
    assert host.post(f'/api/listings/{pid}/submit').status_code==422
    assert host.post(f'/api/listings/{pid}/cad',files={'file':('bad.stl',b'not mesh')}).status_code==422
    stl=b'test'.ljust(80,b'\0')+struct.pack('<I',1)+struct.pack('<12fH',0,0,1,0,0,0,10,0,0,0,10,10,0)
    r=host.post(f'/api/listings/{pid}/cad',files={'file':('../../test.stl',stl)});assert r.status_code==200,r.text
    assert r.json()['dimensions_mm']==[10,10,10]
    assert buyer.get(f'/api/listings/{pid}/cad').status_code==403
    assert host.post(f'/api/listings/{pid}/submit').json()['status']=='pending'
    assert admin.post(f'/api/admin/listings/{pid}/approve').status_code==200
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../model.model','<model/>')
    assert host.post(f'/api/listings/{pid}/cad',files={'file':('bad.3mf',archive.getvalue())}).status_code==422
    r=admin.post('/api/listings',json={**fields,'listing_type':'official'});assert r.status_code==201,r.text
    oid=r.json()['id'];assert admin.post(f'/api/listings/{oid}/publish').json()['status']=='approved'
    assert admin.post(f'/api/admin/products/{oid}/official').status_code==404  # The listing type is not edited here.
    assert admin.post(f'/api/admin/products/{oid}/unpublish').status_code==200
    assert buyer.get(f'/api/listings/{oid}').status_code==404
    assert admin.post(f'/api/listings/{oid}/publish').status_code==200
    with SessionLocal() as db:
        u=db.scalar(select(User).where(User.username=='CADBuyer'));u.email_verified=True;db.get(Listing,oid).cad_dimensions='[10,10,10]';provision_test_host(db);db.commit()
    contact={'first_name':'CAD','last_name':'Buyer','phone':'+39 011 1234567','country':'IT','city':'Torino','street':'Test 1'}
    order=buyer.post('/api/checkout',json=with_confirmation(buyer,{'idempotency_key':'cad-historical-order','contact':contact,'direct':{'listing_id':oid,'material':'PLA','color':'black','quantity':1}}));assert order.status_code==201,order.text
    assert admin.post(f'/api/admin/products/{oid}/remove').status_code==200
    assert buyer.get(f'/api/listings/{oid}').status_code==404
    assert buyer.get('/api/orders').json()[0]['items'][0]['title']=='CAD rack'

import pytest
@pytest.fixture(autouse=True)
def isolated_account_database(tmp_path,monkeypatch):
    import sys
    from sqlalchemy import create_engine,event
    from sqlalchemy.orm import sessionmaker
    from app.database import get_db
    from app import config
    isolated=create_engine('sqlite:///'+str(tmp_path/'accounts.db'),connect_args={'check_same_thread':False})
    @event.listens_for(isolated,'connect')
    def fk(connection,_):connection.execute('PRAGMA foreign_keys=ON')
    factory=sessionmaker(bind=isolated)
    monkeypatch.setattr(sys.modules[__name__],'SessionLocal',factory)
    monkeypatch.setattr(sys.modules[__name__],'engine',isolated)
    monkeypatch.setattr(config,'UPLOAD_DIR',tmp_path/'uploads'/'products')
    monkeypatch.setenv('MAIL_OUTBOX',str(tmp_path/'mail'))
    Base.metadata.create_all(isolated)
    def session():
        with factory() as db:yield db
    app.dependency_overrides[get_db]=session
    rate.clear()
    yield
    app.dependency_overrides.clear();isolated.dispose()

def test_verification_rate_limit_and_username_race():
    from concurrent.futures import ThreadPoolExecutor
    rate.clear()
    def attempt(index):
        return TestClient(app).post('/api/auth/register',json={'username':'ConcurrentLab' if index==0 else 'concurrentlab','email':f'concurrent{index}@example.org','password':'ValidPassword2026'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(attempt,[0,1]))
    assert sorted(statuses)==[201,409]
    client=TestClient(app)
    for _ in range(10):assert client.post('/api/auth/verify',json={'token':'x'*43}).status_code==400
    assert client.post('/api/auth/verify',json={'token':'x'*43}).status_code==429

def test_cart_concurrent_add_and_removed_item():
    from concurrent.futures import ThreadPoolExecutor
    from app.models import Listing
    client=signup('CartRace')
    with SessionLocal() as db:
        u=db.scalar(select(User).where(User.username=='CartRace'))
        p=Listing(owner_id=u.id,title='Race cart',price_cents=100,material='PLA',status='approved',cad_dimensions='[10,10,10]');db.add(p);provision_test_host(db);db.commit();pid=p.id
    def add(_):
        other=TestClient(app);other.cookies.update(client.cookies);other.headers.update(client.headers)
        return other.post('/api/cart',json={'listing_id':pid,'material':'PLA','color':'black','quantity':1}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(add,[0,1]))==[200,200]
    assert client.get('/api/cart').json()[0]['quantity']==2
    with SessionLocal() as db:
        p=db.get(Listing,pid);p.removed=True;p.status='archived';db.commit()
    cart=client.get('/api/cart');assert cart.status_code==200
    assert not cart.json()[0]['available']
    assert client.delete('/api/cart/'+str(cart.json()[0]['id'])).status_code==200

def test_old_order_endpoint_requires_contact_details():
    client=signup('IncompleteBuyer')
    response=client.post('/api/orders',json={'idempotency_key':'invalid-contact-test','contact':'Arbitrary','address':'Text','items':[{'listing_id':1,'quantity':1,'expected_price_cents':100}]})
    assert response.status_code==422


def test_login_failures_and_expiration(monkeypatch):
    import app.main as main
    clock = [10000.0]
    monkeypatch.setattr(main, 'login_clock', lambda: clock[0])
    signup('RateAlice'); signup('RateBob')
    client = TestClient(app)
    def login(name, password='Openlabs2026', ip='203.0.113.1'):
        return client.post('/api/auth/login', headers={'x-real-ip': ip}, json={'email':name+'@example.org','password':password})
    # Successful sessions never count as failures, even when switching users.
    for _ in range(12):
        response=login('RateAlice' if _ % 2 else 'RateBob')
        assert response.status_code == 200
        client.headers['X-CSRF-Token']=response.json()['csrf_token']
        assert client.post('/api/auth/logout').status_code == 200
    for _ in range(4): assert login('RateAlice','wrong').status_code == 401
    assert login('RateAlice').status_code == 200  # clears only Alice's account failures
    for _ in range(4): assert login('RateAlice','wrong',ip='203.0.113.2').status_code == 401
    assert login('RateAlice','wrong',ip='203.0.113.2').status_code == 401
    blocked=login('RateAlice',ip='203.0.113.2')
    assert blocked.status_code == 429 and blocked.headers['retry-after']=='900'
    assert login('RateBob',ip='203.0.113.2').status_code == 200
    clock[0] += 899.1
    assert login('RateAlice',ip='203.0.113.2').headers['retry-after']=='1'
    clock[0] += .9
    assert login('RateAlice',ip='203.0.113.2').status_code == 200
    # Password spraying across accounts is stopped by the separate IP bucket.
    for i in range(10): assert login('unknown'+str(i),'wrong',ip='203.0.113.3').status_code == 401
    assert login('RateBob',ip='203.0.113.3').status_code == 429
    assert login('RateBob',ip='203.0.113.4').status_code == 200
    clock[0] += 900
    assert login('RateBob',ip='203.0.113.3').status_code == 200
