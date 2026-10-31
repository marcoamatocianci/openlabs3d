import io,json,struct
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select,func
from test_marketplace import app,register,headers,SessionLocal,User,hasher
from app import models

STL=b'test'.ljust(80,b'\0')+struct.pack('<I',1)+struct.pack('<12fH',0,0,1,0,0,0,10,0,0,0,10,10,0)
PDF=b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'
def admin_client():
    # A dedicated administrator: other modules create admin@example.org themselves.
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email=='cr-admin@example.org')):
            db.add(User(email='cr-admin@example.org',username='cr_admin',display_name='Requests admin',password_hash=hasher.hash('admin test password'),role='admin',email_verified=True));db.commit()
    client=TestClient(app);r=client.post('/api/auth/login',json={'email':'cr-admin@example.org','password':'admin test password'})
    return client,r.json()['csrf_token']
def photo():
    f=io.BytesIO();image=Image.new('RGB',(40,30),'teal');exif=Image.Exif();exif[0x010F]='Camera maker';image.save(f,format='JPEG',exif=exif);return f.getvalue()
def payload(key,**extra):
    return {'idempotency_key':key,'title':'Rack for cryovials','application':'Hold twelve 2 mL cryovials upright inside a -80 °C freezer box.',
            'dimensions':'Fits a 133 × 133 × 50 mm freezer box','compatibility':'Corning 2 mL cryovials','quantity':4,'material':'',
            'conditions':['cold','cleaning'],'requirements':'Wiped with 70% ethanol',**extra}
def submit(client,token,body,files=()):
    return client.post('/api/custom-requests',data={'payload':json.dumps(body)},files=[('files',f) for f in files],headers=headers(token))
def counts():
    with SessionLocal() as db:return tuple(db.scalar(select(func.count()).select_from(m)) for m in (models.Order,models.PrintingJob,models.Listing))

def test_buyer_submits_request_with_reference_files():
    buyer=TestClient(app);token=register(buyer,'cr-buyer@example.org');before=counts()
    r=submit(buyer,token,payload('request_key_buyer_0001'),[('rack.stl',STL,'model/stl'),('photo.jpg',photo(),'image/jpeg'),('spec.pdf',PDF,'application/pdf')])
    assert r.status_code==201,r.text
    data=r.json()
    assert data['status']=='submitted' and data['reference']==f"CR-{data['id']:05d}" and data['quantity']==4
    assert [f['kind'] for f in data['files']]==['model','image','document'] and 'admin_notes' not in data and 'user' not in data
    assert counts()==before, 'A custom request must not create orders, jobs or listings'
    # Persisted and listed for its owner.
    assert [x['id'] for x in buyer.get('/api/custom-requests').json()]==[data['id']]
    assert buyer.get(f"/api/custom-requests/{data['id']}").json()['conditions']==['cold','cleaning']
    model,image,document=data['files']
    stored=buyer.get(model['url'])
    assert stored.status_code==200 and stored.content==STL and stored.headers['content-disposition'].startswith('attachment')
    shown=buyer.get(image['url'])
    assert shown.headers['content-type']=='image/jpeg' and shown.headers['content-disposition'].startswith('inline')
    with Image.open(io.BytesIO(shown.content)) as im:assert 0x010F not in im.getexif(), 'Image metadata must be removed'
    assert buyer.get(image['url']+'?download=true').headers['content-disposition'].startswith('attachment')
    assert buyer.get(document['url']).content==PDF

def test_double_submission_returns_the_same_request():
    buyer=TestClient(app);token=register(buyer,'cr-twice@example.org')
    first=submit(buyer,token,payload('request_key_twice_0001'));second=submit(buyer,token,payload('request_key_twice_0001'))
    assert first.status_code==201 and second.status_code==200 and first.json()['id']==second.json()['id']
    assert len(buyer.get('/api/custom-requests').json())==1

def test_host_can_request_as_a_customer():
    host=TestClient(app);token=register(host,'cr-host@example.org',host=True)
    with SessionLocal() as db:
        if not db.get(models.Material,'PETG'):db.add(models.Material(name='PETG',technology='FDM'));db.commit()
    r=submit(host,token,payload('request_key_host_00001',material='PETG',conditions=['heat']))
    assert r.status_code==201,r.text
    assert host.get('/api/custom-requests').json()[0]['material']=='PETG'
    assert host.get('/api/auth/me').json()['user']['role']=='host'

def test_validation_and_access_rules():
    buyer,other,anonymous=TestClient(app),TestClient(app),TestClient(app)
    token=register(buyer,'cr-rules@example.org');other_token=register(other,'cr-other@example.org')
    assert anonymous.post('/api/custom-requests',data={'payload':'{}'}).status_code==401
    assert anonymous.get('/api/custom-requests').status_code==401
    assert buyer.post('/api/custom-requests',data={'payload':json.dumps(payload('request_key_rules_0000'))}).status_code==403, 'CSRF token required'
    for bad in ({'quantity':0},{'quantity':-3},{'quantity':10001},{'application':'too short'},{'title':''},{'dimensions':''},{'conditions':['lava']},{'conditions':['heat','heat']},{'unknown':'field'}):
        r=submit(buyer,token,payload('request_key_rules_0001',**bad));assert r.status_code==422,(bad,r.text)
    assert submit(buyer,token,payload('request_key_rules_0002',material='Unobtainium')).status_code==422
    assert buyer.post('/api/custom-requests',data={'payload':'not json'},headers=headers(token)).status_code==422
    assert submit(buyer,token,payload('request_key_rules_0003'),[('run.exe',b'MZ','application/octet-stream')]).status_code==422
    assert submit(buyer,token,payload('request_key_rules_0004'),[('fake.pdf',b'hello','application/pdf')]).status_code==422
    assert submit(buyer,token,payload('request_key_rules_0005'),[('fake.png',b'not an image','image/png')]).status_code==422
    assert submit(buyer,token,payload('request_key_rules_0006'),[('broken.stl',b'solid x','model/stl')]).status_code==422
    assert submit(buyer,token,payload('request_key_rules_0007'),[(f'{n}.pdf',PDF,'application/pdf') for n in range(7)]).status_code==422
    assert submit(buyer,token,payload('request_key_rules_0008'),[('huge.pdf',b'%PDF-'+b'0'*(10*1024*1024)+b'%%EOF','application/pdf')]).status_code==413
    assert buyer.get('/api/custom-requests').json()==[], 'Rejected submissions must not be stored'
    mine=submit(buyer,token,payload('request_key_rules_0009'),[('photo.jpg',photo(),'image/jpeg')]).json()
    # Another account sees neither the request nor its files, and cannot use admin endpoints.
    assert other.get(f"/api/custom-requests/{mine['id']}").status_code==404
    assert other.get(mine['files'][0]['url']).status_code==404
    assert other.get('/api/custom-requests').json()==[]
    assert other.get('/api/admin/custom-requests').status_code==403
    assert other.patch(f"/api/admin/custom-requests/{mine['id']}",json={'status':'quoted'},headers=headers(other_token)).status_code==403
    assert buyer.patch(f"/api/admin/custom-requests/{mine['id']}",json={'status':'quoted'},headers=headers(token)).status_code==403
    assert buyer.get(f"/api/custom-requests/{mine['id']}/files/999999").status_code==404

def test_unverified_accounts_and_administrators_cannot_submit():
    fresh=TestClient(app)
    r=fresh.post('/api/auth/register',json={'email':'cr-unverified@example.org','password':'LongPasswordForTest2026','username':'cr_unverified'})
    assert submit(fresh,r.json()['csrf_token'],payload('request_key_unverified1')).status_code==403
    admin,admin_token=admin_client()
    assert submit(admin,admin_token,payload('request_key_admin_00001')).status_code==403

def test_administrator_reviews_requests():
    buyer=TestClient(app);token=register(buyer,'cr-review@example.org')
    created=submit(buyer,token,payload('request_key_review_0001'),[('spec.pdf',PDF,'application/pdf')]).json()
    admin,admin_token=admin_client()
    new=admin.get('/api/admin/overview').json()['custom_requests_new']
    listed=admin.get('/api/admin/custom-requests?status=submitted').json()
    item=next(x for x in listed if x['id']==created['id'])
    assert item['user']['email']=='cr-review@example.org' and item['admin_notes']=='' and len(listed)==new
    assert admin.get(item['files'][0]['url']).content==PDF
    assert admin.get('/api/admin/custom-requests?status=unknown').status_code==422
    r=admin.patch(f"/api/admin/custom-requests/{created['id']}",json={'status':'under_review','admin_notes':' Check freezer box drawing '},headers=headers(admin_token))
    assert r.status_code==200 and r.json()['status']=='under_review' and r.json()['admin_notes']=='Check freezer box drawing'
    assert admin.patch(f"/api/admin/custom-requests/{created['id']}",json={'status':'archived'},headers=headers(admin_token)).status_code==422
    assert admin.patch('/api/admin/custom-requests/999999',json={'status':'closed'},headers=headers(admin_token)).status_code==404
    assert admin.get('/api/admin/overview').json()['custom_requests_new']==new-1
    # The owner sees the new status but never the internal notes.
    own=buyer.get(f"/api/custom-requests/{created['id']}").json()
    assert own['status']=='under_review' and 'admin_notes' not in own
    events=admin.get('/api/admin/activity').json()
    assert any(e['action']=='request.updated' and e['subject']==f"request:{created['id']}" for e in events)

def test_account_with_requests_is_retained():
    buyer=TestClient(app);token=register(buyer,'cr-delete@example.org')
    assert submit(buyer,token,payload('request_key_delete_0001')).status_code==201
    r=buyer.request('DELETE','/api/profile',json={'password':'LongPasswordForTest2026'},headers=headers(token))
    assert r.status_code==409 and 'custom requests' in r.json()['detail']
    with SessionLocal() as db:assert db.scalar(select(User).where(User.email=='cr-delete@example.org'))
