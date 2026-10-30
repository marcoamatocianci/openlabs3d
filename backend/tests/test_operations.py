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
    assert host.post(f'/api/host/jobs/{job_id}/status',json={'status':'completed'},headers=headers(host_token)).status_code==409
    for status in ('printing','ready','completed'):
        assert host.post(f'/api/host/jobs/{job_id}/status',json={'status':status},headers=headers(host_token)).status_code==200
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
        assert db.scalar(select(User).where(User.email=='new-admin@example.org')).role=='admin'

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


def stock(client,token):
    """After approval the host stocks materials and colors directly, without a revision."""
    printer=client.get('/api/host/equipment').json()[0]
    assert {'PLA','PETG'}<=set(printer['capabilities'])
    response=client.put(f"/api/host/printers/{printer['id']}/availability",json={'materials':['PLA','PETG'],'material_colors':{'PLA':{'black':'#000000'},'PETG':{'black':'#000000'}}},headers=headers(token))
    assert response.status_code==200,response.text
