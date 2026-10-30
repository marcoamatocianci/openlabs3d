"""HTTP integration coverage using isolated marketplace fixtures.
Printers are certified through revisions; material and color stock is host-managed."""
import json
import pytest
from sqlalchemy import select
from test_availability_integration import workflow, checkout_body
from app import models


def proposed(client):
    keep=('model_id','manufacturer','model','technology','x','y','z','quantity')
    return {'printers':[{k:p[k] for k in keep} for p in client.get('/api/host/equipment').json()]}

def colors(client,pid):
    return client.get(f'/api/listings/{pid}/availability').json()['colors']

def catalogue_id(sessions,model):
    with sessions() as db:return db.scalar(select(models.PrinterModel.id).where(models.PrinterModel.model==model))

def set_stock(client,printer,materials,colors):
    return client.put(f"/api/host/printers/{printer['id']}/availability",json={'materials':materials,'material_colors':colors})


def test_draft_review_rejection_and_resubmission(workflow):
    clients,ids,pid,sessions=workflow
    host,admin,buyer=clients['host'],clients['admin'],clients['buyer']
    original=host.get('/api/host/equipment').json()
    proposal=proposed(host);proposal['printers'][0]['quantity']=2
    draft=host.put('/api/host/equipment-application',json=proposal)
    assert draft.status_code==200,draft.text and draft.json()['status']=='draft'
    assert admin.get('/api/admin/equipment-revisions').json()==[]
    assert host.get('/api/host/equipment').json()==original
    assert host.get('/api/auth/me').json()['user']['role']=='host'
    proposal['printers'][0]['quantity']=3  # Latest unsaved edit is what gets submitted.
    pending=host.put('/api/host/equipment-application',json={**proposal,'submit':True})
    rid=pending.json()['id'];assert rid==draft.json()['id']
    assert host.put('/api/host/equipment-application',json=proposal).status_code==409
    assert buyer.post(f'/api/admin/equipment-revisions/{rid}/approve',json={}).status_code==403
    assert admin.post(f'/api/admin/equipment-revisions/{rid}/reject',json={}).status_code==422
    assert admin.post(f'/api/admin/equipment-revisions/{rid}/reject',json={'reason':'Check calibration'}).status_code==200
    assert host.get('/api/host/equipment').json()==original
    assert host.get('/api/host/equipment-revision').json()['rejection_reason']=='Check calibration'
    rid=host.put('/api/host/equipment-application',json={**proposal,'submit':True}).json()['id']
    assert admin.post(f'/api/admin/equipment-revisions/{rid}/approve',json={}).status_code==200
    assert admin.post(f'/api/admin/equipment-revisions/{rid}/approve',json={}).status_code==409
    after=host.get('/api/host/equipment').json()[0]
    assert after['quantity']==3 and after['id']==original[0]['id']
    # A modified printer keeps the stock its capabilities still allow.
    assert after['material_colors']==original[0]['material_colors'] and after['capabilities']==['PETG','PLA']
    assert host.get('/api/host/application').json()['status']=='approved'


def test_stock_is_immediate_and_bounded_by_capabilities(workflow):
    clients,ids,pid,sessions=workflow;h,a,b=clients['host'],clients['admin'],clients['buyer']
    printer=h.get('/api/host/equipment').json()[0]
    assert 'orange' not in colors(b,pid)
    stock={**printer['material_colors'],'PLA':{**printer['material_colors']['PLA'],'orange':'#FF8800'}}
    r=set_stock(h,printer,['PLA','PETG'],stock);assert r.status_code==200,r.text
    assert r.json()['material_colors']['PLA']['orange']=='#ff8800'
    assert 'orange' in colors(b,pid)  # No administrator approval.
    assert a.get('/api/admin/equipment-revisions').json()==[] and h.get('/api/host/equipment-revision').json() is None
    assert h.get('/api/host/equipment').json()[0]['material_colors']==r.json()['material_colors']  # Persisted.
    assert set_stock(h,printer,['PLA','ABS'],{'ABS':{'black':'#000000'}}).status_code==422  # Not an approved capability.
    assert set_stock(h,printer,['PLA'],{'PETG':{'black':'#000000'}}).status_code==422
    assert set_stock(h,printer,['PLA'],{'PLA':{'black':'#000000','jet':'#000000'}}).status_code==422
    assert set_stock(h,printer,['PLA'],{'PLA':{'Bad Name':'#000000'}}).status_code==422
    assert set_stock(clients['other'],printer,['PLA'],{}).status_code==404
    assert set_stock(b,printer,['PLA'],{}).status_code==403
    # Removing PETG takes it off the marketplace for this host; the other host still offers white.
    assert set_stock(h,printer,['PLA'],{'PLA':{'red':'#ff0000'}}).status_code==200
    availability=b.get(f'/api/listings/{pid}/availability').json()['colors_by_material']
    assert set(availability['PLA'])=={'red','blue'} and set(availability['PETG'])=={'white'}
    assert h.get('/api/auth/me').json()['user']['role']=='host'


def test_stock_removal_keeps_accepted_jobs(workflow):
    clients,ids,pid,sessions=workflow;h,b=clients['host'],clients['buyer']
    assert b.post('/api/checkout',json=checkout_body(pid,'red')).status_code==201
    job=h.get('/api/host/jobs').json()[0]
    assert h.post(f"/api/host/jobs/{job['id']}/accept").status_code==200
    printer=h.get('/api/host/equipment').json()[0]
    assert set_stock(h,printer,['PLA'],{'PLA':{'black':'#000000'}}).status_code==200
    assert 'red' not in colors(b,pid)
    assert b.post('/api/cart',json={'listing_id':pid,'material':'PLA','color':'red','quantity':1}).status_code==422
    assert b.post('/api/checkout',json=checkout_body(pid,'red')).status_code==422
    mine=[j for j in h.get('/api/host/jobs').json() if j['id']==job['id']][0]
    assert mine['status']=='accepted' and mine['item']['color']=='red'
    assert h.post(f"/api/host/jobs/{job['id']}/status",json={'status':'printing'}).status_code==200


def test_active_job_blocks_capability_removal_until_completion(workflow):
    clients,ids,pid,sessions=workflow
    h,a,b=clients['host'],clients['admin'],clients['buyer']
    assert b.post('/api/checkout',json=checkout_body(pid,'red')).status_code==201
    job=h.get('/api/host/jobs').json()[0]
    assert h.post(f"/api/host/jobs/{job['id']}/accept").status_code==200
    original=h.get('/api/host/equipment').json()
    r=h.put('/api/host/equipment-application',json={'printers':[],'submit':True});assert r.status_code==200,r.text
    rid=r.json()['id']
    blocked=a.post(f'/api/admin/equipment-revisions/{rid}/approve',json={})
    assert blocked.status_code==409,blocked.text
    assert h.get('/api/host/equipment').json()==original
    with sessions() as db:
        j=db.get(models.PrintingJob,job['id']);assert j.host_id==ids['host']
        j.status='completed';db.commit()
    assert a.post(f'/api/admin/equipment-revisions/{rid}/approve',json={}).status_code==200
    assert h.get('/api/auth/me').json()['user']['role']=='host'


def test_add_printer_preserves_unrelated_ids_and_discard(workflow):
    clients,ids,pid,sessions=workflow;h,a=clients['host'],clients['admin']
    original=h.get('/api/host/equipment').json()
    proposal=proposed(h);proposal['printers'].append({'model_id':catalogue_id(sessions,'P1S'),'quantity':1})
    assert h.put('/api/host/equipment-application',json=proposal).status_code==200
    assert h.delete('/api/host/equipment-revision').json() is None
    assert h.get('/api/host/equipment').json()==original
    r=h.put('/api/host/equipment-application',json={**proposal,'submit':True})
    assert h.delete('/api/host/equipment-revision').status_code==409
    assert a.post(f"/api/admin/equipment-revisions/{r.json()['id']}/approve",json={}).status_code==200
    approved=h.get('/api/host/equipment').json()
    assert len(approved)==2 and approved[0]==original[0]
    new=approved[1]
    assert new['model']=='P1S' and new['materials']==[] and {'PLA','PETG','ABS'}<=set(new['capabilities'])


def test_capabilities_come_from_catalogue_and_build_volume_stays_inactive(workflow):
    clients,ids,pid,sessions=workflow;h,a,b=clients['host'],clients['admin'],clients['buyer']
    proposal=proposed(h)
    proposal['printers'][0]['x']=50
    proposal['printers'].append({'model_id':catalogue_id(sessions,'A1 mini'),'quantity':1})
    r=h.put('/api/host/equipment-application',json={**proposal,'submit':True})
    assert r.status_code==200,r.text
    assert r.json()['proposal']['printers'][1]['capabilities']==['PETG','PLA','TPU']
    assert 'red' in colors(b,pid)  # Pending specifications do not change availability.
    assert a.post(f"/api/admin/equipment-revisions/{r.json()['id']}/approve",json={}).status_code==200
    assert 'red' not in colors(b,pid)  # Existing printer is now too small.
    mini=[p for p in h.get('/api/host/equipment').json() if p['model']=='A1 mini'][0]
    assert set_stock(h,mini,['ABS'],{'ABS':{'orange':'#ff8800'}}).status_code==422  # A1 mini is not rated for ABS.
    assert set_stock(h,mini,['PLA'],{'PLA':{'orange':'#ff8800'}}).status_code==200
    assert 'orange' in colors(b,pid)


def test_removing_last_printer_preserves_account_and_suspension_is_explicit(workflow):
    clients,ids,pid,sessions=workflow;h,a=clients['host'],clients['admin']
    r=h.put('/api/host/equipment-application',json={'printers':[],'submit':True})
    assert r.status_code==200,r.text
    assert a.post(f"/api/admin/equipment-revisions/{r.json()['id']}/approve",json={}).status_code==200
    assert h.get('/api/host/equipment').json()==[]
    assert h.get('/api/auth/me').json()['user']['role']=='host'
    account=h.get('/api/host/application').json()
    assert a.post(f"/api/admin/hosts/{account['id']}/suspend",json={}).status_code==200
    assert h.put('/api/host/equipment-application',json={'printers':[]}).status_code==409
    assert a.post(f"/api/admin/hosts/{account['id']}/restore",json={}).status_code==200
    assert h.get('/api/auth/me').json()['user']['role']=='host'


@pytest.mark.parametrize('legacy_dimensions',['Unknown','100 cm × 100 cm × 100 cm'])
def test_legacy_unknown_job_requirements_fail_closed_but_allow_additions(workflow,legacy_dimensions):
    clients,ids,pid,sessions=workflow;h,a,b=clients['host'],clients['admin'],clients['buyer']
    b.post('/api/checkout',json=checkout_body(pid,'red'))
    job=h.get('/api/host/jobs').json()[0];h.post(f"/api/host/jobs/{job['id']}/accept")
    with sessions() as db:
        j=db.get(models.PrintingJob,job['id']);j.item.manufacturing_dimensions='[]';j.item.dimensions=legacy_dimensions;db.commit()
    proposal=proposed(h);proposal['printers'].append({'model_id':catalogue_id(sessions,'P1S'),'quantity':1})
    r=h.put('/api/host/equipment-application',json={**proposal,'submit':True})
    assert a.post(f"/api/admin/equipment-revisions/{r.json()['id']}/approve",json={}).status_code==200
    proposal=proposed(h);proposal['printers']=proposal['printers'][1:]
    r=h.put('/api/host/equipment-application',json={**proposal,'submit':True})
    assert a.post(f"/api/admin/equipment-revisions/{r.json()['id']}/approve",json={}).status_code==409


def test_legacy_pending_revision_format_still_approves(workflow):
    clients,ids,pid,sessions=workflow;h,a=clients['host'],clients['admin']
    legacy=[{k:v for k,v in p.items() if k not in ('id','verified','documented','capabilities')} for p in h.get('/api/host/equipment').json()]
    with sessions() as db:
        payload=json.dumps({'company':'','weekly_hours':None,'printers':legacy})
        db.add(models.EquipmentRevision(user_id=ids['host'],status='pending',before=payload,proposal=json.dumps({'company':'','weekly_hours':None,'printers':[{**legacy[0],'quantity':2}]})));db.commit()
        rid=db.scalar(select(models.EquipmentRevision.id))
    assert a.post(f'/api/admin/equipment-revisions/{rid}/approve',json={}).status_code==200
    after=h.get('/api/host/equipment').json()[0]
    assert after['quantity']==2 and after['capabilities']==['PETG','PLA']


def test_migration_roundtrip_preserves_accounts_and_equipment(tmp_path):
    import os,subprocess,sqlite3,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1];path=tmp_path/'rollback.db'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(path),'PYTHONPATH':str(root)}
    def migrate(action,target):subprocess.run([sys.executable,'-m','alembic',action,target],cwd=root,env=env,check=True,capture_output=True)
    migrate('upgrade','64a_material_colors')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO users (id,email,password_hash,display_name,role,created_at,updated_at) VALUES (1,'preserved@example.org','hash','Existing','host',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO host_applications (id,user_id,name,contact,country,region,printers,technologies,materials,dimensions,capabilities,additional,status,rejection_reason,updated_at) VALUES (1,1,'Host','','','','','','','','','','approved','',CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO host_printers (user_id,manufacturer,model,technology,x,y,z,quantity,materials) VALUES (1,'Legacy','Printer','FDM',200,200,200,1,'[\"PLA\"]')")
    for action,target in [('upgrade','head'),('downgrade','64a_material_colors'),('upgrade','head')]:
        migrate(action,target)
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT role FROM users').fetchone()==('host',)
            assert db.execute('SELECT status FROM host_applications').fetchone()==('approved',)
            assert db.execute('SELECT manufacturer,x,materials FROM host_printers').fetchone()==('Legacy',200,'["PLA"]')
        if target=='head':
            with sqlite3.connect(path) as db:assert db.execute('SELECT capabilities FROM host_printers').fetchone()==('["PLA"]',)


def test_delete_draft_removes_only_the_draft(workflow):
    clients,ids,pid,sessions=workflow;h,a=clients['host'],clients['admin']
    original=h.get('/api/host/equipment').json()
    proposal=proposed(h);proposal['printers'][0]['quantity']=4
    saved=h.put('/api/host/equipment-application',json=proposal).json()
    assert saved['status']=='draft' and saved['updated_at']
    assert h.delete('/api/host/equipment-revision').json() is None
    with sessions() as db:assert db.scalar(select(models.EquipmentRevision))is None  # Record really deleted.
    assert h.get('/api/host/equipment').json()==original
    assert h.put('/api/host/equipment-application',json=proposal).status_code==200  # A new draft can start.
    rid=h.put('/api/host/equipment-application',json={**proposal,'submit':True}).json()['id']
    assert h.delete('/api/host/equipment-revision').status_code==409  # Pending revisions are protected.
    assert a.post(f'/api/admin/equipment-revisions/{rid}/reject',json={'reason':'Check calibration'}).status_code==200
    h.put('/api/host/equipment-application',json=proposal)
    after=h.delete('/api/host/equipment-revision').json()
    assert after['id']==rid and after['status']=='rejected'
    assert h.get('/api/host/equipment').json()==original
