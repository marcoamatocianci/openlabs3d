"""Isolated HTTP workflow and migration tests; never use the development database."""
import hashlib
import json
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from app import database, models
from app.main import app
from app.equipment import seed_equipment

@pytest.fixture
def workflow(tmp_path, monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'workflow.db'),connect_args={'check_same_thread':False,'timeout':10})
    database.Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(database,'engine',engine)
    monkeypatch.setattr(database,'SessionLocal',sessions)
    clients={};ids={}
    with sessions() as db:
        seed_equipment(db)
        for name,role in [('buyer','buyer'),('host','host'),('other','host'),('admin','admin')]:
            u=models.User(email=name+'@example.org',password_hash='unused',display_name=name,role=role,email_verified=True,first_name='Test',last_name='User',phone='123456789',country='IT',city='Torino')
            db.add(u);db.flush();ids[name]=u.id
            token=secrets.token_urlsafe(32)
            from datetime import datetime,timedelta,timezone
            db.add(models.LoginSession(user_id=u.id,token_hash=hashlib.sha256(token.encode()).hexdigest(),csrf='test-csrf',expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
            c=TestClient(app);c.cookies.set('ol3d_session',token);c.headers['X-CSRF-Token']='test-csrf';clients[name]=c
            if role=='host':db.add(models.HostApplication(user_id=u.id,status='approved',materials='PLA, PETG'))
        p=models.Listing(owner_id=ids['admin'],title='Test rack',status='approved',material='PLA',configuration='{"materials":{"PLA":10000,"PETG":12000}}',cad_dimensions='[100,100,100]',price_cents=1000)
        db.add(p);db.flush();pid=p.id
        for name,colors in [('host',{'PLA':{'black':'#000000','red':'#ff0000'},'PETG':{'black':'#000000'}}),('other',{'PLA':{'blue':'#0000ff'},'PETG':{'white':'#ffffff'}})]:
            db.add(models.HostPrinter(user_id=ids[name],manufacturer='Custom',model='Printer',technology='FDM',x=200,y=200,z=200,quantity=1,materials='["PLA","PETG"]',material_colors=json.dumps(colors)))
        db.commit()
    yield clients,ids,pid,sessions
    for c in clients.values():c.close()
    engine.dispose()

def checkout_body(pid,color='black',material='PLA'):
    return {'idempotency_key':secrets.token_hex(16),'contact':{'first_name':'Test','last_name':'User','phone':'123456789','country':'IT','city':'Torino','street':'Via Roma 1'},'direct':{'listing_id':pid,'material':material,'color':color,'quantity':1}}

def test_customization_cart_checkout_assignment(workflow):
    clients,ids,pid,sessions=workflow;b=clients['buyer']
    availability=b.get(f'/api/listings/{pid}/availability')
    assert availability.headers['cache-control']=='no-store'
    assert set(availability.json()['colors_by_material']['PLA'])=={'black','red','blue'}
    assert set(availability.json()['colors_by_material']['PETG'])=={'black','white'}
    line={'listing_id':pid,'material':'PLA','color':'black','quantity':1}
    assert b.post('/api/cart',json={**line,'color':'white'}).status_code==422
    assert b.post('/api/cart',json=line).status_code==200
    assert b.put('/api/cart',json={**line,'quantity':2}).status_code==200
    assert clients['other'].get('/api/cart').json()==[]
    order=b.post('/api/checkout',json=checkout_body(pid,'red'))
    assert order.status_code==201,order.text
    assert b.get('/api/cart').json()[0]['quantity']==2 # Direct checkout preserves cart.
    jobs=clients['host'].get('/api/host/jobs').json()
    assert jobs
    jid=jobs[0]['id']
    assert clients['other'].post(f'/api/host/jobs/{jid}/accept').status_code==403
    assert clients['host'].post(f'/api/host/jobs/{jid}/accept').status_code==200
    assert clients['buyer'].post(f'/api/host/jobs/{jid}/accept').status_code==403
    with sessions() as db:
        db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==ids['host'])).status='suspended';db.commit()
    assert b.get('/api/cart').json()[0]['available'] is False
    assert b.post('/api/checkout',json=checkout_body(pid)).status_code==422
    assert b.post('/api/cart',json=line).status_code==422
    assert b.get('/api/orders').status_code==200

def test_same_printer_dimensions_unknown_and_role_access(workflow):
    clients,ids,pid,sessions=workflow;b=clients['buyer']
    with sessions() as db:
        db.scalar(select(models.HostPrinter).where(models.HostPrinter.user_id==ids['other'])).x=50;db.commit()
    opts=b.get(f'/api/listings/{pid}/availability').json()
    assert set(opts['colors_by_material']['PLA'])=={'black','red'}
    assert b.post('/api/checkout',json=checkout_body(pid,'blue')).status_code==422
    with sessions() as db:
        db.get(models.Listing,pid).cad_dimensions='[]';db.commit()
    assert b.get(f'/api/listings/{pid}/availability').json()['materials']=={}
    assert b.post('/api/checkout',json=checkout_body(pid)).status_code==422
    assert TestClient(app).get('/api/host/equipment').status_code==401
    assert clients['admin'].put('/api/host/equipment-application',json={'printers':[]}).status_code==403
    assert b.post('/api/admin/hosts/1/approve',json={}).status_code==403

def test_equipment_persistence_and_unknown_colors(workflow):
    clients,ids,pid,sessions=workflow;host=clients['host']
    printer={'manufacturer':'Custom','model':'Registered','technology':'FDM','x':200,'y':200,'z':200,'quantity':1,'materials':['PLA'],'material_colors':{'PLA':{'cream':'#e7d9bc'}}}
    r=host.put('/api/host/equipment-application',json={'printers':[printer],'submit':False})
    assert r.status_code==200,r.text
    assert host.get('/api/host/equipment-revision').json()['proposal']['printers'][0]['material_colors']==printer['material_colors']
    assert clients['buyer'].get('/api/host/equipment').json()==[]
    assert 'cream' not in clients['buyer'].get(f'/api/listings/{pid}/availability').json()['colors'] # Draft is ineligible.
    bad={**printer,'material_colors':{'PETG':{'cream':'#e7d9bc'}}}
    assert host.put('/api/host/equipment-application',json={'printers':[bad]}).status_code==422
    unknown={**printer,'material_colors':{}}
    assert host.put('/api/host/equipment-application',json={'printers':[unknown],'submit':True}).status_code==422
    assert host.put('/api/host/equipment-application',json={'printers':[unknown]}).status_code==200
    assert host.get('/api/host/equipment-revision').json()['proposal']['printers'][0]['materials']==['PLA']

def test_checkout_serializes_concurrent_suspension(workflow,monkeypatch):
    clients,ids,pid,sessions=workflow
    from app import shopping
    original=shopping.quote;entered=threading.Event();release=threading.Event();changed=threading.Event()
    def pause(*args,**kwargs):
        entered.set();assert release.wait(5);return original(*args,**kwargs)
    monkeypatch.setattr(shopping,'quote',pause)
    def suspend():
        with sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==ids['host'])).status='suspended'
            db.commit();changed.set()
    with ThreadPoolExecutor(2) as pool:
        order=pool.submit(clients['buyer'].post,'/api/checkout',json=checkout_body(pid,'red'))
        assert entered.wait(5)
        edit=pool.submit(suspend)
        assert not changed.wait(.2) # Writer cannot pass the eligibility/order transaction.
        release.set();assert order.result().status_code==201;edit.result()
    assert clients['buyer'].post('/api/checkout',json=checkout_body(pid,'red')).status_code==422

def test_migration_preserves_legacy_equipment(tmp_path):
    import os,subprocess,sqlite3
    root=Path(__file__).resolve().parents[1];path=tmp_path/'migration.db'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(path),'PYTHONPATH':str(root)}
    import sys
    def upgrade(revision):subprocess.run([sys.executable,'-m','alembic','upgrade',revision],cwd=root,env=env,check=True,capture_output=True)
    upgrade('63a_profile_addresses')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO host_printers (user_id,manufacturer,model,technology,x,y,z,quantity,materials) VALUES (1,'Legacy','Printer','FDM',200,200,200,1,'[\"PLA\"]')")
    upgrade('head')
    with sqlite3.connect(path) as db:
        row=db.execute('SELECT materials,material_colors,x FROM host_printers').fetchone()
        assert row==('["PLA"]','{}',200)
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='65a_equipment_revisions'

def test_material_color_availability_tracks_product_and_host(workflow):
    clients,ids,pid,sessions=workflow
    buyer=clients['buyer']
    with sessions() as db:
        # Use one approved host, with the requested explicit per-material colors.
        other=db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==ids['other']))
        other.status='suspended'
        printer=db.scalar(select(models.HostPrinter).where(models.HostPrinter.user_id==ids['host']))
        printer.materials=json.dumps(['PLA','PETG'])
        printer.material_colors=json.dumps({'PLA':{'black':'#000000','white':'#ffffff','blue':'#0000ff'},'PETG':{'black':'#000000'}})
        db.commit()
    endpoint=f'/api/listings/{pid}/availability'
    available=buyer.get(endpoint).json()
    assert set(available['materials'])=={'PLA','PETG'}
    assert set(available['colors_by_material']['PLA'])=={'black','white','blue'}
    assert set(available['colors_by_material']['PETG'])=={'black'}
    for material,color,expected in [('PLA','blue',1000),('PETG','black',1200)]:
        q=buyer.post(f'/api/listings/{pid}/quote',json={'material':material,'color':color,'quantity':1})
        assert q.status_code==200 and q.json()['unit_price_cents']==expected
    assert buyer.post(f'/api/listings/{pid}/quote',json={'material':'PETG','color':'blue','quantity':1}).status_code==422
    with sessions() as db:
        printer=db.scalar(select(models.HostPrinter).where(models.HostPrinter.user_id==ids['host']))
        printer.materials=json.dumps(['PETG']);db.commit()
    assert set(buyer.get(endpoint).json()['materials'])=={'PETG'}
    with sessions() as db:
        db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==ids['host'])).status='pending';db.commit()
    assert buyer.get(endpoint).json()['materials']=={}
    with sessions() as db:
        db.scalar(select(models.HostApplication).where(models.HostApplication.user_id==ids['host'])).status='approved'
        printer=db.scalar(select(models.HostPrinter).where(models.HostPrinter.user_id==ids['host']))
        printer.materials=json.dumps(['PLA','PETG'])
        db.get(models.Listing,pid).configuration=json.dumps({'materials':{'PETG':12000}});db.commit()
    assert set(buyer.get(endpoint).json()['materials'])=={'PETG'}
    assert buyer.post(f'/api/listings/{pid}/quote',json={'material':'PLA','color':'blue','quantity':1}).status_code==422
