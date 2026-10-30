"""HTTP integration coverage using isolated marketplace fixtures."""
import json
import pytest
from sqlalchemy import select
from test_availability_integration import workflow, checkout_body
from app import models


def proposed(client):
    result = {'printers':[{k:v for k,v in p.items() if k not in ('id','verified')} for p in client.get('/api/host/equipment').json()]}
    for p in result['printers']:p['materials']=sorted(p['materials'])
    return result


def test_draft_review_rejection_and_resubmission(workflow):
    clients,ids,pid,sessions=workflow
    host,admin,buyer=clients['host'],clients['admin'],clients['buyer']
    original=host.get('/api/host/equipment').json()
    proposal=proposed(host)
    proposal['printers'][0]['material_colors']['PLA']['cream']='#eeeecc'
    draft=host.put('/api/host/equipment-application',json=proposal)
    assert draft.status_code==200,draft.text
    assert draft.json()['status']=='draft'
    assert admin.get('/api/admin/equipment-revisions').json()==[]
    assert host.get('/api/host/equipment').json()==original
    assert host.get('/api/host/equipment-revision').json()['proposal']['printers']==proposal['printers']
    assert host.get('/api/auth/me').json()['user']['role']=='host'
    assert host.get('/api/host/application').json()['status']=='approved'
    assert 'cream' not in buyer.get(f'/api/listings/{pid}/availability').json()['colors']
    proposal['printers'][0]['model']='Latest unsaved printer'
    pending=host.put('/api/host/equipment-application',json={**proposal,'submit':True})
    assert pending.status_code==200,pending.text
    rid=pending.json()['id']
    assert rid==draft.json()['id']
    assert pending.json()['proposal']['printers']==proposal['printers']
    assert host.get('/api/host/equipment-revision').json()['status']=='pending'
    queue=admin.get('/api/admin/equipment-revisions').json()
    assert queue[0]['before']['printers'][0]['material_colors']!=queue[0]['proposal']['printers'][0]['material_colors']
    assert host.put('/api/host/equipment-application',json=proposal).status_code==409
    assert buyer.post(f'/api/admin/equipment-revisions/{rid}/approve',json={}).status_code==403
    assert admin.post(f'/api/admin/equipment-revisions/{rid}/reject',json={}).status_code==422
    assert admin.post(f'/api/admin/equipment-revisions/{rid}/reject',json={'reason':'Check calibration'}).status_code==200
    assert host.get('/api/host/equipment').json()==original
    assert host.get('/api/auth/me').json()['user']['role']=='host'
    assert host.get('/api/host/equipment-revision').json()['rejection_reason']=='Check calibration'
    pending=host.put('/api/host/equipment-application',json={**proposal,'submit':True})
    rid=pending.json()['id']
    assert admin.post(f'/api/admin/equipment-revisions/{rid}/approve',json={}).status_code==200
    assert admin.post(f'/api/admin/equipment-revisions/{rid}/approve',json={}).status_code==409
    assert host.get('/api/host/application').json()['status']=='approved'
    assert 'cream' in buyer.get(f'/api/listings/{pid}/availability').json()['colors']


def test_active_job_blocks_removal_until_completion(workflow):
    clients,ids,pid,sessions=workflow
    h,a,b=clients['host'],clients['admin'],clients['buyer']
    assert b.post('/api/checkout',json=checkout_body(pid,'red')).status_code==201
    job=h.get('/api/host/jobs').json()[0]
    assert h.post(f"/api/host/jobs/{job['id']}/accept").status_code==200
    original=h.get('/api/host/equipment').json()
    proposal=proposed(h);proposal['printers'][0]['material_colors']['PLA'].pop('red')
    r=h.put('/api/host/equipment-application',json={**proposal,'submit':True});assert r.status_code==200,r.text
    rid=r.json()['id']
    blocked=a.post(f'/api/admin/equipment-revisions/{rid}/approve',json={})
    assert blocked.status_code==409,blocked.text
    assert h.get('/api/host/equipment').json()==original
    with sessions() as db:
        j=db.get(models.PrintingJob,job['id']);assert j.host_id==ids['host']
        assert json.loads(j.item.manufacturing_dimensions)==[100,100,100]
        j.status='completed';db.commit()
    assert a.post(f'/api/admin/equipment-revisions/{rid}/approve',json={}).status_code==200
    assert h.get('/api/auth/me').json()['user']['role']=='host'


def test_add_printer_preserves_unrelated_ids_and_discard(workflow):
    clients,ids,pid,sessions=workflow;h,a=clients['host'],clients['admin']
    original=h.get('/api/host/equipment').json()
    proposal=proposed(h);proposal['printers'].append({**proposal['printers'][0],'model':'New printer'})
    assert h.put('/api/host/equipment-application',json=proposal).status_code==200
    assert h.delete('/api/host/equipment-revision').status_code==200
    assert h.get('/api/host/equipment-revision').json()['proposal']['printers']==proposed(h)['printers']
    r=h.put('/api/host/equipment-application',json={**proposal,'submit':True})
    assert h.delete('/api/host/equipment-revision').status_code==409
    assert a.post(f"/api/admin/equipment-revisions/{r.json()['id']}/approve",json={}).status_code==200
    approved=h.get('/api/host/equipment').json()
    assert len(approved)==2 and approved[0]==original[0]


def test_material_build_volume_and_new_printer_stay_inactive(workflow):
    clients,ids,pid,sessions=workflow;h,a,b=clients['host'],clients['admin'],clients['buyer']
    proposal=proposed(h)
    proposal['printers'][0]['materials'].append('ABS')
    proposal['printers'][0]['material_colors']['ABS']={'orange':'#ff8800'}
    proposal['printers'][0]['x']=50
    # A large new printer provides ABS, while the existing one becomes too small.
    proposal['printers'].append({**proposal['printers'][0],'model':'Large ABS','x':200,'materials':['ABS'],'material_colors':{'ABS':{'orange':'#ff8800'}}})
    r=h.put('/api/host/equipment-application',json={**proposal,'submit':True})
    assert r.status_code==200,r.text
    from app.availability import combinations
    with sessions() as db:
        assert 'ABS' not in combinations(db.get(models.Listing,pid),ids['host'])
        assert 'PLA' in combinations(db.get(models.Listing,pid),ids['host'])
    assert a.post(f"/api/admin/equipment-revisions/{r.json()['id']}/approve",json={}).status_code==200
    with sessions() as db:
        assert combinations(db.get(models.Listing,pid),ids['host'])=={'ABS':{'orange':'#ff8800'}}


def test_removing_last_printer_preserves_account_and_suspension_is_explicit(workflow):
    clients,ids,pid,sessions=workflow;h,a=clients['host'],clients['admin']
    r=h.put('/api/host/equipment-application',json={'printers':[],'submit':True})
    assert r.status_code==200,r.text
    rid=r.json()['id']
    assert a.post(f'/api/admin/equipment-revisions/{rid}/approve',json={}).status_code==200
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
    proposal=proposed(h);proposal['printers'].append({**proposal['printers'][0],'model':'Extra'})
    r=h.put('/api/host/equipment-application',json={**proposal,'submit':True})
    assert a.post(f"/api/admin/equipment-revisions/{r.json()['id']}/approve",json={}).status_code==200
    proposal=proposed(h);proposal['printers']=proposal['printers'][1:]
    r=h.put('/api/host/equipment-application',json={**proposal,'submit':True})
    assert a.post(f"/api/admin/equipment-revisions/{r.json()['id']}/approve",json={}).status_code==409


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
