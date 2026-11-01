from order_fixtures import CONTACT, ADDRESS
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_marketplace import app, register, headers, SessionLocal, User, hasher, upload_test_cad

def admin_client():
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email=='admin@example.org')):
            db.add(User(email='admin@example.org',display_name='Admin',password_hash=hasher.hash('admin test password'),role='admin',email_verified=True))
            db.commit()
    client=TestClient(app)
    response=client.post('/api/auth/login',json={'email':'admin@example.org','password':'admin test password'})
    return client,response.json()['csrf_token']

def test_host_order_and_job_workflow():
    buyer, host, other = [TestClient(app) for _ in range(3)]
    buyer_token=register(buyer,'operations-buyer@example.org',host=True)
    host_token=register(host,'operations-host@example.org')
    admin,admin_token=admin_client()
    application={'name':'Test workshop','contact':'workshop@example.org','country':'Italy','region':'Turin','printers':'Printer A','technologies':'FDM','materials':'PETG, PLA','dimensions':'200 x 200 x 200 mm','capabilities':'Small batches','additional':'','submit':True}
    result=structured_application(host,host_token)
    assert result.status_code==200, result.text
    host_id=result.json()['id']
    assert host.get('/api/host/jobs').status_code==403
    assert host.post(f'/api/admin/hosts/{host_id}/approve',json={},headers=headers(host_token)).status_code==403
    assert admin.post(f'/api/admin/hosts/{host_id}/approve',json={},headers=headers(admin_token)).json()['status']=='approved'
    assert admin.post(f'/api/admin/hosts/{host_id}/approve',json={},headers=headers(admin_token)).status_code==409
    stock(host,host_token)
    assert host.get('/api/auth/me').json()['user']['role']=='host'
    listing=buyer.post('/api/listings',json={'title':'Orderable rack','description':'Rack','category':'Tube racks','price_cents':1200,'material':'PETG','dimensions':'20 mm','compatibility':'Tubes'},headers=headers(buyer_token)).json()
    upload_test_cad(buyer,listing['id'],buyer_token)
    assert buyer.post(f'/api/listings/{listing["id"]}/submit',headers=headers(buyer_token)).status_code==200
    assert admin.post(f'/api/admin/listings/{listing["id"]}/approve',headers=headers(admin_token)).status_code==200
    payload={'idempotency_key':'unique_test_key_1234','contact':CONTACT,'address':ADDRESS,'items':[{'listing_id':listing['id'],'quantity':2,'color':'black','expected_price_cents':1200}]}
    stale={**payload,'items':[{'listing_id':listing['id'],'quantity':2,'color':'black','expected_price_cents':1}]}
    assert buyer.post('/api/orders',json=stale,headers=headers(buyer_token)).status_code==409
    assert buyer.get('/api/orders').json()==[]
    order=buyer.post('/api/orders',json=payload,headers=headers(buyer_token))
    assert order.status_code==201, order.text
    assert order.json()['total_cents']==2400
    assert buyer.post('/api/orders',json=payload,headers=headers(buyer_token)).json()['id']==order.json()['id']
    assert other.get('/api/orders').status_code==401
    job_id=order.json()['jobs'][0]['id']
    visible=host.get('/api/host/jobs').json()
    assert any(j['id']==job_id for j in visible)
    assert 'address' not in str(visible)
    assert host.post(f'/api/host/jobs/{job_id}/accept',headers=headers(host_token)).status_code==200
    assigned=next(j for j in host.get('/api/host/jobs').json() if j['id']==job_id)
    assert __import__('json').loads(assigned['fulfillment']['address'])['street']=='Test address'
    assert host.post(f'/api/host/jobs/{job_id}/accept',headers=headers(host_token)).status_code==409
    # Hosts can no longer complete a job: only the buyer does, by confirming receipt.
    assert host.post(f'/api/host/jobs/{job_id}/status',json={'status':'completed'},headers=headers(host_token)).status_code==422
    assert host.post(f'/api/host/jobs/{job_id}/status',json={'status':'shipped','carrier':'DHL','tracking_number':'1'},headers=headers(host_token)).status_code==409
    for status in ('printing','ready'):
        assert host.post(f'/api/host/jobs/{job_id}/status',json={'status':status},headers=headers(host_token)).status_code==200
    ship_job(host,host_token,job_id)
    assert buyer.get('/api/orders').json()[0]['status']=='shipped'
    received=buyer.post(f'/api/orders/{order.json()["id"]}/jobs/{job_id}/received',headers=headers(buyer_token))
    assert received.status_code==200, received.text
    assert received.json()['status']=='completed' and received.json()['jobs'][0]['status']=='completed'
    assert buyer.get('/api/orders').json()[0]['status']=='completed'
    assert admin.post(f'/api/admin/orders/{order.json()["id"]}/cancel',headers=headers(admin_token)).status_code==409
    assert admin.get('/api/admin/overview').json()['orders_completed']>=1
    assert admin.post(f'/api/admin/users/{result.json()["user_id"]}/suspend',headers=headers(admin_token)).status_code==200
    assert host.get('/api/auth/me').status_code==401

def test_two_hosts_cannot_accept_the_same_job():
    buyer, first, second = [TestClient(app) for _ in range(3)]
    admin,admin_token=admin_client()
    buyer_token=register(buyer,'race-buyer@example.org',host=True)
    first_token=register(first,'race-first-host@example.org')
    first_id=first.get('/api/auth/me').json()['user']['id']
    second_token=register(second,'race-second-host@example.org')
    application={'name':'Second workshop','contact':'host@example.org','country':'Italy','region':'Turin','printers':'Printer B','technologies':'FDM','materials':'PETG','dimensions':'200 mm','capabilities':'Printing','additional':'','submit':True}
    for client,token in ((first,first_token),(second,second_token)):
        host_id=structured_application(client,token).json()['id']
        assert admin.post(f'/api/admin/hosts/{host_id}/approve',json={},headers=headers(admin_token)).status_code==200
        stock(client,token)
    product=buyer.post('/api/listings',json={'title':'Race rack','description':'Rack','category':'Tube racks','price_cents':1200,'material':'PETG','dimensions':'20 mm','compatibility':'Tubes'},headers=headers(buyer_token)).json()
    upload_test_cad(buyer,product['id'],buyer_token)
    assert buyer.post(f'/api/listings/{product["id"]}/submit',headers=headers(buyer_token)).status_code==200
    assert admin.post(f'/api/admin/listings/{product["id"]}/approve',headers=headers(admin_token)).status_code==200
    order=buyer.post('/api/orders',json={'idempotency_key':'race_test_key_12345','contact':CONTACT,'address':ADDRESS,'items':[{'listing_id':product['id'],'quantity':1,'color':'black','expected_price_cents':product['price_cents']}]},headers=headers(buyer_token)).json()
    job_id=order['jobs'][0]['id']
    def claim(pair):
        client, token=pair
        return client.post(f'/api/host/jobs/{job_id}/accept',headers=headers(token)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(claim, [(first,first_token),(second,second_token)]))
    assert statuses.count(200)==1
    assert all(code in (200,409,503) for code in statuses)
    jobs=next(o for o in admin.get('/api/admin/orders').json() if o['id']==order['id'])['jobs']
    assert jobs[0]['status']=='accepted'
    assert jobs[0]['host_id'] in (first_id,second.get('/api/auth/me').json()['user']['id'])
    second_buyer=TestClient(app)
    second_buyer_token=second_buyer.post('/api/auth/login',json={'email':'race-buyer@example.org','password':'LongPasswordForTest2026'}).json()['csrf_token']
    duplicate={'idempotency_key':'concurrent_order_key_123','contact':CONTACT,'address':ADDRESS,'items':[{'listing_id':product['id'],'quantity':1,'color':'black','expected_price_cents':product['price_cents']}]}
    def place(pair):
        client,token=pair
        return client.post('/api/orders',json=duplicate,headers=headers(token))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(place,[(buyer,buyer_token),(second_buyer,second_buyer_token)]))
    assert all(r.status_code in (201,503) for r in results)
    retry=buyer.post('/api/orders',json=duplicate,headers=headers(buyer_token))
    assert retry.status_code==201
    assert all(r.json()['id']==retry.json()['id'] for r in results if r.status_code==201)
    assert len(buyer.get('/api/orders').json())==2

def test_migration_preserves_existing_data(tmp_path):
    import os, sqlite3, subprocess, sys
    from pathlib import Path
    backend=Path(__file__).resolve().parents[1]
    db_path=tmp_path/'migration.db'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(db_path),'UPLOAD_DIR':str(tmp_path/'uploads')}
    def upgrade(revision):
        result=subprocess.run([sys.executable,'-m','alembic','upgrade',revision],cwd=backend,env=env,capture_output=True,text=True)
        assert result.returncode==0, result.stderr
    upgrade('2120e271d395')
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO users (id,email,password_hash,display_name,role,created_at,updated_at) VALUES (1,'preserved@example.org','hash','Existing','buyer',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO listings (owner_id,title,description,category,price_cents,currency,material,dimensions,compatibility,listing_type,status,rejection_reason,version,created_at,updated_at) VALUES (1,'Preserved','Description','Existing category',100,'EUR','PLA','10 mm','Test','community','draft','',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
    upgrade('head')
    with sqlite3.connect(db_path) as db:
        assert db.execute('SELECT email,active FROM users WHERE id=1').fetchone()==('preserved@example.org',1)
        assert db.execute('SELECT title FROM listings').fetchone()==('Preserved',)
        assert db.execute("SELECT active FROM categories WHERE name='Existing category'").fetchone()==(1,)

def test_admin_creation_uses_registration_validation(monkeypatch):
    import pytest
    from app.create_admin import main
    from app import create_admin
    responses=iter(['not-an-email','Name','InvalidAdmin'])
    monkeypatch.setattr('builtins.input',lambda _:next(responses))
    monkeypatch.setattr(create_admin.getpass,'getpass',lambda _:'A sufficiently long password 2026')
    with pytest.raises(SystemExit): main()
    responses=iter(['new-admin@example.org','New Admin','NewAdmin'])
    monkeypatch.setattr('builtins.input',lambda _:next(responses))
    main()
    with SessionLocal() as db:
        created=db.scalar(select(User).where(User.email=='new-admin@example.org'))
        assert created.role=='admin' and created.display_name=='NewAdmin'  # One public name: the username.

def test_admin_creation_rejects_invalid_utf8_input(monkeypatch):
    import pytest
    from app import create_admin
    for email, name, passwords in (
        ('broken\udcc3@example.org', 'Name', ['A sufficiently long password 2026']),
        ('encoding-name@example.org', 'Name\udcc3', ['A sufficiently long password 2026']),
        ('encoding-password@example.org', 'Name', ['A sufficiently long password 2026\udcc3']),
        ('encoding-confirm@example.org', 'Name', ['A sufficiently long password 2026', 'A sufficiently long password 2026\udcc3']),
    ):
        responses = iter([email, name, "EncodingTest"])
        secrets = iter(passwords)
        monkeypatch.setattr('builtins.input', lambda _: next(responses))
        monkeypatch.setattr(create_admin.getpass, 'getpass', lambda _: next(secrets))
        with pytest.raises(SystemExit, match='invalid text encoding'):
            create_admin.main()
        with SessionLocal() as db:
            assert not db.scalar(select(User).where(User.email == email.encode('utf-8', 'replace').decode('utf-8')))

def test_account_deletion_requires_password_and_revokes_all_sessions():
    from app.main import rate
    from app.models import Activity, HostApplication, LoginSession
    rate.clear()
    client, other_session = TestClient(app), TestClient(app)
    email = 'delete-self@example.org'
    token = register(client, email)
    user_id = client.get('/api/auth/me').json()['user']['id']
    assert other_session.post('/api/auth/login', json={'email':email,'password':'LongPasswordForTest2026'}).status_code == 200
    with SessionLocal() as db:
        db.add(HostApplication(user_id=user_id, name='Workshop', contact='private contact'))
        db.commit()
    def delete(password, token_headers):
        return client.request('DELETE', '/api/profile', json={'password':password}, headers=token_headers)
    assert delete('LongPasswordForTest2026', {}).status_code == 403
    assert delete('wrong password', headers(token)).status_code == 401
    assert client.get('/api/auth/me').status_code == 200
    assert delete('LongPasswordForTest2026', headers(token)).status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    assert other_session.get('/api/auth/me').status_code == 401
    with SessionLocal() as db:
        assert db.get(User, user_id) is None
        assert not db.scalar(select(HostApplication).where(HostApplication.user_id == user_id))
        assert not db.scalar(select(LoginSession).where(LoginSession.user_id == user_id))
        assert not db.scalar(select(Activity).where(Activity.actor_id == user_id))
    register(TestClient(app), email)

def test_admin_deletion_permissions_and_linked_records():
    from app.main import rate
    rate.clear()
    user, stranger = TestClient(app), TestClient(app)
    token = register(user, 'delete-linked@example.org', host=True)
    stranger_token = register(stranger, 'delete-stranger@example.org')
    user_id = user.get('/api/auth/me').json()['user']['id']
    admin, admin_token = admin_client()
    request = lambda client, target, password, token: client.request('DELETE', f'/api/admin/users/{target}', json={'password':password}, headers=headers(token))
    assert request(stranger,user_id,'LongPasswordForTest2026',stranger_token).status_code == 403
    assert request(admin,user_id,'wrong password',admin_token).status_code == 401
    assert user.post('/api/listings',json={'title':'Owned listing'},headers=headers(token)).status_code == 201
    assert request(admin,user_id,'admin test password',admin_token).status_code == 409
    assert user.get('/api/auth/me').status_code == 200
    stranger_id = stranger.get('/api/auth/me').json()['user']['id']
    assert request(admin,stranger_id,'admin test password',admin_token).status_code == 200
    assert stranger.get('/api/auth/me').status_code == 401

def test_admin_can_delete_admin_account():
    from app.main import rate
    rate.clear()
    with SessionLocal() as db:
        other = User(email='delete-admin@example.org',display_name='Other admin',password_hash=hasher.hash('another admin password'),role='admin')
        db.add(other); db.commit(); other_id = other.id
    other_client = TestClient(app)
    other_token = other_client.post('/api/auth/login',json={'email':'delete-admin@example.org','password':'another admin password'}).json()['csrf_token']
    admin, admin_token = admin_client()
    response = admin.request('DELETE', f'/api/admin/users/{other_id}',json={'password':'admin test password'},headers=headers(admin_token))
    assert response.status_code == 200
    assert other_client.get('/api/auth/me').status_code == 401


def structured_application(client,token):
    from app.equipment import seed_equipment
    from app.models import PrinterModel
    with SessionLocal() as db:
        seed_equipment(db);model_id=db.scalar(select(PrinterModel.id).where(PrinterModel.model=='P1S'))
    response=client.put('/api/host/equipment-application',json={'printers':[{'model_id':model_id,'quantity':1}],'submit':True},headers=headers(token))
    assert response.status_code==200,response.text
    return client.get('/api/host/application')


def ship_job(client,token,job_id,**extra):
    body={'status':'shipped','carrier':'DHL Express','tracking_number':'JD0146000032','tracking_url':'https://www.dhl.com/track?id=JD0146000032','note':'Left with reception',**extra}
    response=client.post(f'/api/host/jobs/{job_id}/status',json=body,headers=headers(token))
    assert response.status_code==200, response.text
    return response.json()

def stock(client,token):
    """After approval the host stocks materials and colors once, for all printers, without a revision."""
    printer=client.get('/api/host/equipment').json()[0]
    assert {'PLA','PETG'}<=set(printer['capabilities'])
    response=client.put('/api/host/materials',json={'material_colors':{'PLA':{'black':'#000000'},'PETG':{'black':'#000000'}}},headers=headers(token))
    assert response.status_code==200,response.text


def test_buyer_order_pages_filters_and_snapshots():
    from datetime import datetime, timedelta
    from app.models import Order, OrderItem, Listing
    from app.main import rate
    rate.clear()
    buyer,other=TestClient(app),TestClient(app)
    register(buyer,'history-buyer@example.org')
    register(other,'history-other@example.org')
    uid=buyer.get('/api/auth/me').json()['user']['id']
    other_id=other.get('/api/auth/me').json()['user']['id']
    with SessionLocal() as db:
        p=Listing(owner_id=uid,title='Changed listing',price_cents=9999,material='PETG',status='archived',removed=True)
        db.add(p);db.flush()
        for n,status in enumerate(['pending','accepted','printing','ready','shipped','completed','cancelled']):
            o=Order(buyer_id=uid,reference=f'QA-HISTORY-{n}',idempotency_key=f'qa-history-{n}',contact=CONTACT,address=ADDRESS,total_cents=2400,status=status,created_at=datetime(2026,1,1)+timedelta(days=n))
            db.add(o);db.flush()
            db.add(OrderItem(order_id=o.id,listing_id=p.id,title='Original rack',quantity=2,price_cents=1200,material='PLA',color='orange',dimensions='10 mm'))
        db.add(Order(buyer_id=other_id,reference='QA-HISTORY-PRIVATE',idempotency_key='private-history',contact=CONTACT,address=ADDRESS,total_cents=0))
        db.commit()
    path='/api/orders?paginated=true&per_page=2'
    # Current orders by default: everything not completed or cancelled, newest first.
    data=buyer.get(path).json()
    groups=lambda d,scope:{g['key']:g['count'] for g in d['scopes'][scope]['groups']}
    assert data['scope']=='active' and data['scopes']['active']['total']==5 and data['scopes']['history']['total']==2
    assert groups(data,'active')=={'pending':1,'in-progress':3,'shipping':1} and groups(data,'history')=={'completed':1,'cancelled':1}
    assert data['pages']==3 and [o['status'] for o in data['items']]==['shipped','ready']
    assert buyer.get(path+'&page=2').json()['items'][0]['status']=='printing'
    assert buyer.get(path+'&sort=oldest').json()['items'][0]['status']=='pending'
    assert buyer.get(path+'&page=999').json()['page']==3
    for scope,group,statuses in [('active','pending',['pending']),('active','in-progress',['accepted','printing']),('active','shipping',['shipped']),
                                 ('history','all',['completed','cancelled']),('history','completed',['completed']),('history','cancelled',['cancelled'])]:
        filtered=buyer.get(path+f'&scope={scope}&group={group}&sort=oldest').json()
        assert [o['status'] for o in filtered['items']]==statuses, (scope,group)
        assert filtered['scopes']==data['scopes']  # Counts do not depend on the filter.
    item=buyer.get(path+'&scope=history&group=completed').json()['items'][0]['items'][0]
    assert (item['title'],item['material'],item['color'],item['quantity'],item['price_cents'])==('Original rack','PLA','orange',2,1200)
    # Search by reference or product name, within the selected scope.
    assert [o['reference'] for o in buyer.get(path+'&scope=history&q=history-5').json()['items']]==['QA-HISTORY-5']
    assert buyer.get(path+'&scope=history&q=original').json()['total']==2 and buyer.get(path+'&q=nothing-like-this').json()['total']==0
    assert other.get(path).json()['scopes']['active']['total']==1
    assert other.get(path).json()['items'][0]['reference']=='QA-HISTORY-PRIVATE'
    assert TestClient(app).get(path).status_code==401
    assert buyer.get(path+'&group=unknown').status_code==422
    assert buyer.get(path+'&scope=history&group=pending').status_code==422
    assert buyer.get(path+'&scope=archive').status_code==422
    assert buyer.get('/api/orders?paginated=true&per_page=1000').status_code==422
    assert len(buyer.get('/api/orders').json())==7  # Original client contract remains valid.


def test_shipping_requires_details_and_only_the_buyer_completes():
    from app.models import Activity
    buyer, host, stranger = [TestClient(app) for _ in range(3)]
    buyer_token=register(buyer,'shipping-buyer@example.org',host=True)
    host_token=register(host,'shipping-host@example.org')
    stranger_token=register(stranger,'shipping-stranger@example.org')
    admin,admin_token=admin_client()
    host_id=structured_application(host,host_token).json()['id']
    assert admin.post(f'/api/admin/hosts/{host_id}/approve',json={},headers=headers(admin_token)).status_code==200
    stock(host,host_token)
    lines=[]
    for title in ('Shipping rack','Shipping holder'):
        listing=buyer.post('/api/listings',json={'title':title,'description':'Rack','category':'Tube racks','price_cents':1200,'material':'PETG','dimensions':'20 mm','compatibility':'Tubes'},headers=headers(buyer_token)).json()
        upload_test_cad(buyer,listing['id'],buyer_token)
        buyer.post(f'/api/listings/{listing["id"]}/submit',headers=headers(buyer_token))
        assert admin.post(f'/api/admin/listings/{listing["id"]}/approve',headers=headers(admin_token)).status_code==200
        lines.append({'listing_id':listing['id'],'quantity':1,'color':'black','expected_price_cents':1200})
    order=buyer.post('/api/orders',json={'idempotency_key':'shipping_test_key_123','contact':CONTACT,'address':ADDRESS,'items':lines},headers=headers(buyer_token))
    assert order.status_code==201, order.text
    order=order.json()
    first,second=[j['id'] for j in order['jobs']]
    order_id=order['id']
    for job in (first,second):
        assert host.post(f'/api/host/jobs/{job}/accept',headers=headers(host_token)).status_code==200
        for status in ('printing','ready'):
            assert host.post(f'/api/host/jobs/{job}/status',json={'status':status},headers=headers(host_token)).status_code==200
    def status(body): return host.post(f'/api/host/jobs/{first}/status',json=body,headers=headers(host_token)).status_code
    # Shipment details are required, validated, and accepted only with the shipped status.
    assert status({'status':'shipped'})==422
    assert status({'status':'shipped','carrier':'DHL'})==422
    assert status({'status':'shipped','tracking_number':'123'})==422
    assert status({'status':'shipped','carrier':'DHL','tracking_number':'123','tracking_url':'javascript:alert(1)'})==422
    assert status({'status':'ready','carrier':'DHL'})==422
    # The buyer cannot confirm a job that has not shipped.
    assert buyer.post(f'/api/orders/{order_id}/jobs/{first}/received',headers=headers(buyer_token)).status_code==409
    shipped=ship_job(host,host_token,first)
    assert shipped['status']=='shipped'
    assert shipped['shipment']['carrier']=='DHL Express' and shipped['shipment']['tracking_number']=='JD0146000032'
    assert shipped['shipment']['tracking_url'].startswith('https://') and shipped['shipment']['note']=='Left with reception' and shipped['shipment']['shipped_at']
    assert host.post(f'/api/host/jobs/{first}/status',json={'status':'shipped','carrier':'DHL','tracking_number':'2'},headers=headers(host_token)).status_code==409
    # One of two jobs shipped: the order is still in production; the buyer sees the tracking details.
    mine=buyer.get('/api/orders').json()[0]
    assert mine['status']=='ready'
    assert next(j for j in mine['jobs'] if j['id']==first)['shipment']['tracking_number']=='JD0146000032'
    assert next(j for j in mine['jobs'] if j['id']==second)['shipment'] is None
    ship_job(host,host_token,second,tracking_url='',note='')
    assert buyer.get('/api/orders').json()[0]['status']=='shipped'
    assert admin.get('/api/admin/overview').json()['orders_shipped']>=1
    assert admin.post(f'/api/admin/orders/{order_id}/cancel',headers=headers(admin_token)).status_code==409
    # Only the buyer of this order confirms receipt, one job at a time.
    assert stranger.post(f'/api/orders/{order_id}/jobs/{first}/received',headers=headers(stranger_token)).status_code==404
    assert host.post(f'/api/orders/{order_id}/jobs/{first}/received',headers=headers(host_token)).status_code==404
    assert buyer.post(f'/api/orders/{order_id}/jobs/{first}/received').status_code==403
    assert buyer.post(f'/api/orders/{order_id + 999}/jobs/{first}/received',headers=headers(buyer_token)).status_code==404
    partial=buyer.post(f'/api/orders/{order_id}/jobs/{first}/received',headers=headers(buyer_token))
    assert partial.status_code==200 and partial.json()['status']=='shipped'
    assert buyer.post(f'/api/orders/{order_id}/jobs/{first}/received',headers=headers(buyer_token)).status_code==409
    done=buyer.post(f'/api/orders/{order_id}/jobs/{second}/received',headers=headers(buyer_token)).json()
    assert done['status']=='completed' and {j['status'] for j in done['jobs']}=={'completed'}
    assert [h['action'] for h in done['history']].count('job.completed')==2 and 'order.completed' in [h['action'] for h in done['history']]
    buyer_id=buyer.get('/api/auth/me').json()['user']['id']
    with SessionLocal() as db:
        events={(a.action,a.subject):a for a in db.scalars(select(Activity).where(Activity.subject.in_([f'job:{first}',f'job:{second}',f'order:{order_id}'])))}
        assert events[('job.shipped',f'job:{first}')].detail=='DHL Express · JD0146000032'
        assert events[('job.completed',f'job:{first}')].actor_id==buyer_id
        assert events[('order.completed',f'order:{order_id}')].actor_id==buyer_id
    # The completed job stays in the host's list, with its shipment.
    finished=next(j for j in host.get('/api/host/jobs').json() if j['id']==first)
    assert finished['status']=='completed' and finished['shipment']['carrier']=='DHL Express'
    # Admin user profile: account info, host printing specs and filterable activity.
    host_id=host.get('/api/auth/me').json()['user']['id']
    assert buyer.get(f'/api/admin/users/{buyer_id}').status_code==403
    profile=admin.get(f'/api/admin/users/{buyer_id}').json()
    assert profile['user']['email']=='shipping-buyer@example.org' and profile['counts']['orders']==1 and profile['addresses']==[]
    hosted=admin.get(f'/api/admin/users/{host_id}').json()
    assert hosted['host']['status']=='approved' and hosted['host']['printers'] and hosted['host']['inventory']['PLA']=={'black':'#000000'}
    def actions(uid,kind='all'): return [e['action'] for e in admin.get(f'/api/admin/users/{uid}/activity?type={kind}').json()]
    assert set(actions(buyer_id,'purchases'))=={'order.created'}
    assert set(actions(buyer_id,'completions'))=={'job.completed','order.completed'}
    assert actions(buyer_id,'cancellations')==[] and actions(buyer_id,'custom_requests')==[]
    assert set(actions(host_id,'printing'))=={'job.accepted','job.printing','job.ready','job.shipped'} and actions(host_id,'printing').count('job.shipped')==2
    general=actions(buyer_id)
    assert 'order.created' in general and 'job.shipped' in general  # What happened to the buyer's order.
    assert 'job.completed' in actions(host_id,'completions')  # The host sees completions of its jobs.
    assert admin.get(f'/api/admin/users/{buyer_id}/activity?type=bogus').status_code==422
    assert admin.get('/api/admin/users/999999').status_code==404


def test_buyer_changes_delivery_address_until_something_ships():
    import json
    from app.models import Activity, Order, OrderItem, PrintingJob, Listing
    buyer, other = TestClient(app), TestClient(app)
    token=register(buyer,'address-buyer@example.org')
    other_token=register(other,'address-other@example.org')
    uid=buyer.get('/api/auth/me').json()['user']['id']
    with SessionLocal() as db:
        ids={}
        listing=Listing(owner_id=uid,title='Address rack',price_cents=1200,material='PLA',status='approved');db.add(listing);db.flush()
        for name,statuses,order_status in [('open',['printing','ready'],'printing'),('shipped',['ready','shipped'],'ready'),('done',['completed'],'completed'),('cancelled',['cancelled'],'cancelled')]:
            o=Order(buyer_id=uid,reference=f'QA-ADDRESS-{name}',idempotency_key=f'qa-address-{name}',contact=CONTACT,address=ADDRESS,total_cents=1200,status=order_status)
            db.add(o);db.flush()
            for n,status in enumerate(statuses):
                item=OrderItem(order_id=o.id,listing_id=listing.id,title='Rack',quantity=1,price_cents=1200,material='PLA',color='black',dimensions='10 mm')
                db.add(item);db.flush();db.add(PrintingJob(order_id=o.id,item_id=item.id,status=status))
            ids[name]=o.id
        db.commit()
    new={'first_name':'Ada','last_name':'Lovelace','phone':'+39 011 7654321','street':'Via Nuova 5','additional':'Lab 3','postal_code':'10121','city':'Torino','region':'TO','country':'it'}
    def change(client,name,body=new,tok=token): return client.put(f'/api/orders/{ids[name]}/address',json=body,headers=headers(tok))
    response=change(buyer,'open')
    assert response.status_code==200, response.text
    saved=json.loads(response.json()['address'])
    assert saved['street']=='Via Nuova 5' and saved['country']=='IT' and saved['postal_code']=='10121'
    assert 'order.address_changed' in [h['action'] for h in response.json()['history']]
    with SessionLocal() as db:
        assert db.scalar(select(Activity).where(Activity.action=='order.address_changed',Activity.subject==f'order:{ids["open"]}')).actor_id==uid
    # Locked once a product has shipped or completed, and on cancelled orders.
    for name in ('shipped','done','cancelled'):
        assert change(buyer,name).status_code==409
        with SessionLocal() as db: assert db.get(Order,ids[name]).address==ADDRESS
    # Validation, ownership and CSRF.
    assert change(buyer,'open',{**new,'street':''}).status_code==422
    assert change(buyer,'open',{**new,'country':'XX'}).status_code==422
    assert change(buyer,'open',{**new,'unexpected':'x'}).status_code==422
    assert change(other,'open',tok=other_token).status_code==404
    assert buyer.put(f'/api/orders/{ids["open"]}/address',json=new).status_code==403
    assert buyer.put('/api/orders/999999/address',json=new,headers=headers(token)).status_code==404


def test_active_work_and_history_follow_the_authoritative_status():
    """Completed and cancelled work leaves the active lists by itself; nothing is flagged or removed."""
    from app.models import Order, CustomRequest
    buyer, host = TestClient(app), TestClient(app)
    buyer_token=register(buyer,'history-scope-buyer@example.org',host=True)
    host_token=register(host,'history-scope-host@example.org')
    admin,admin_token=admin_client()
    host_id=structured_application(host,host_token).json()['id']
    assert admin.post(f'/api/admin/hosts/{host_id}/approve',json={},headers=headers(admin_token)).status_code==200
    stock(host,host_token)
    lines=[]
    for title in ('Scope rack A','Scope rack B','Scope rack C'):
        listing=buyer.post('/api/listings',json={'title':title,'description':'Rack','category':'Tube racks','price_cents':1200,'material':'PETG','dimensions':'20 mm','compatibility':'Tubes'},headers=headers(buyer_token)).json()
        upload_test_cad(buyer,listing['id'],buyer_token)
        buyer.post(f'/api/listings/{listing["id"]}/submit',headers=headers(buyer_token))
        assert admin.post(f'/api/admin/listings/{listing["id"]}/approve',headers=headers(admin_token)).status_code==200
        lines.append({'listing_id':listing['id'],'quantity':1,'color':'black','expected_price_cents':1200})
    order=buyer.post('/api/orders',json={'idempotency_key':'history_scope_order_1','contact':CONTACT,'address':ADDRESS,'items':lines[:2]},headers=headers(buyer_token)).json()
    done,shipped=[j['id'] for j in order['jobs']]
    # A second order the host accepted, then cancelled by an administrator before printing.
    withdrawn=buyer.post('/api/orders',json={'idempotency_key':'history_scope_order_2','contact':CONTACT,'address':ADDRESS,'items':lines[2:]},headers=headers(buyer_token)).json()
    dropped=withdrawn['jobs'][0]['id']
    assert host.post(f'/api/host/jobs/{dropped}/accept',headers=headers(host_token)).status_code==200
    assert admin.post(f'/api/admin/orders/{withdrawn["id"]}/cancel',headers=headers(admin_token)).status_code==200
    for job in (done,shipped):
        assert host.post(f'/api/host/jobs/{job}/accept',headers=headers(host_token)).status_code==200
        for status in ('printing','ready'):
            assert host.post(f'/api/host/jobs/{job}/status',json={'status':status},headers=headers(host_token)).status_code==200
        ship_job(host,host_token,job)
    assert buyer.post(f'/api/orders/{order["id"]}/jobs/{done}/received',headers=headers(buyer_token)).status_code==200
    jobs=lambda q:host.get('/api/host/jobs?'+q).json()
    # Host: shipped work stays active until the buyer confirms; completed and cancelled go to history.
    active=jobs('scope=active')
    assert {j['id'] for j in active['items']}>={shipped} and not {done,dropped}&{j['id'] for j in active['items']}
    assert {g['key']:g['count'] for g in active['scopes']['active']['groups']}['shipped']==1
    assert [j['id'] for j in jobs('scope=active&group=shipped')['items']]==[shipped]
    history=jobs('scope=history')
    assert {j['id'] for j in history['items']}=={done,dropped} and history['scopes']['history']['total']==2
    assert [j['id'] for j in jobs('scope=history&group=cancelled')['items']]==[dropped]
    finished=next(j for j in history['items'] if j['id']==done)
    assert finished['status']=='completed' and finished['shipment']['tracking_number']=='JD0146000032' and finished['item']['material']=='PETG'
    assert finished['item']['listing_version'] is not None and finished['fulfillment']['address']
    assert host.get(f'/api/jobs/{done}/cad').status_code==403 and host.get(f'/api/jobs/{dropped}/cad').status_code==403, 'history grants no manufacturing access'
    assert host.post(f'/api/host/jobs/{dropped}/status',json={'status':'printing'},headers=headers(host_token)).status_code==409
    assert jobs('scope=history&q=Scope rack A')['total']==1 and jobs('scope=history&q=nothing')['total']==0
    assert host.get('/api/host/jobs?scope=history&group=available').status_code==422
    assert any(j['id']==done for j in host.get('/api/host/jobs').json()), 'the original list contract is unchanged'
    # Buyer: the order is shipped (all remaining jobs shipped or done), so still current.
    current=buyer.get('/api/orders?paginated=true').json()
    assert [o['id'] for o in current['items']]==[order['id']] and current['items'][0]['status']=='shipped'
    assert [o['id'] for o in buyer.get('/api/orders?paginated=true&scope=history&group=cancelled').json()['items']]==[withdrawn['id']]
    # Admin orders: active and history, server-side, with the eligibility data the page shows.
    admin_orders=lambda q:admin.get('/api/admin/orders?paginated=true&'+q).json()
    assert order['id'] in [o['id'] for o in admin_orders('scope=active&group=shipping')['items']]
    assert order['id'] not in [o['id'] for o in admin_orders('scope=history')['items']]
    assert isinstance(admin.get('/api/admin/orders').json(),list)
    assert buyer.get('/api/admin/orders?paginated=true').status_code==403
    assert buyer.post(f'/api/orders/{order["id"]}/jobs/{shipped}/received',headers=headers(buyer_token)).status_code==200
    with SessionLocal() as db: assert db.get(Order,order['id']).status=='completed'
    assert order['id'] in [o['id'] for o in admin_orders('scope=history&group=completed')['items']]
    assert order['id'] not in [o['id'] for o in admin_orders('scope=active')['items']]
    assert order['id'] in [o['id'] for o in buyer.get('/api/orders?paginated=true&scope=history').json()['items']]
    assert admin_orders('scope=history&q='+order['reference'])['total']==1
    # Custom requests: accepted (quoted) stays active; closed is history; reopening brings it back.
    rid=buyer.post('/api/custom-requests',data={'payload':__import__('json').dumps({'idempotency_key':'history_scope_request','title':'Scope holder','application':'A holder used to test active and history lists.','dimensions':'10 x 10 x 10 mm','quantity':1})},headers=headers(buyer_token)).json()['id']
    def request_scope():
        mine=buyer.get('/api/custom-requests?scope=active').json()
        return 'active' if rid in [r['id'] for r in mine['items']] else 'history' if rid in [r['id'] for r in buyer.get('/api/custom-requests?scope=history').json()['items']] else None
    for status,expected in (('quoted','active'),('closed','history'),('under_review','active')):
        assert admin.patch(f'/api/admin/custom-requests/{rid}',json={'status':status},headers=headers(admin_token)).status_code==200
        assert request_scope()==expected, status
    assert isinstance(buyer.get('/api/custom-requests').json(),list)
    assert admin.get('/api/admin/custom-requests?scope=active&group=under_review').json()['items'][0]['id']==rid
    with SessionLocal() as db: assert db.get(CustomRequest,rid) is not None
    # Approval History: each review decision, with its reviewer and reason; pending queues are unaffected.
    pending=buyer.post('/api/listings',json={'title':'Scope rejected','description':'Rack','category':'Tube racks','price_cents':1200,'material':'PETG','dimensions':'20 mm','compatibility':'Tubes'},headers=headers(buyer_token)).json()
    upload_test_cad(buyer,pending['id'],buyer_token); buyer.post(f'/api/listings/{pending["id"]}/submit',headers=headers(buyer_token))
    assert admin.post(f'/api/admin/listings/{pending["id"]}/reject',json={'reason':'Missing drawings'},headers=headers(admin_token)).status_code==200
    history=admin.get('/api/admin/approvals/history?type=listings').json()
    rejected=next(i for i in history['items'] if i['title']=='Scope rejected')
    assert rejected['decision']=='rejected' and rejected['reason']=='Missing drawings' and rejected['reviewer'] and rejected['submitter']
    assert all(i['type']=='listings' for i in history['items'])
    hosts=admin.get('/api/admin/approvals/history?type=hosts').json()['items']
    assert any(i['decision']=='approved' and i['link']=='admin/users/'+str(host.get('/api/auth/me').json()['user']['id']) for i in hosts)
    everything=admin.get('/api/admin/approvals/history?per_page=2').json()
    assert everything['total']==sum(everything['counts'].values()) and len(everything['items'])==2 and everything['pages']>=2
    assert buyer.get('/api/admin/approvals/history').status_code==403
    assert admin.get('/api/admin/approvals/history?type=orders').status_code==422
