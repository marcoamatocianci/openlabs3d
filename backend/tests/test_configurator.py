import test_marketplace
from app.pricing import quote,options
from app.models import Listing
import pytest,json

def test_integer_quotes_and_validation():
    p=Listing(price_cents=1500,material='PETG',collection_key='microtube-rack',configuration=json.dumps({'materials':{'PLA':10000,'PETG':12000,'ABS':13500},'discounts':{'5':500,'10':1000,'20':1500},'max_quantity':30}),model_url='/assets/models/microtube-rack.glb',currency='EUR')
    q=quote(p,'PETG','cream',10)
    assert q['unit_price_cents']==1620 and q['total_cents']==16200
    assert quote(p,'PLA','cream',1)['total_cents']==1500
    assert quote(p,'ABS','cream',1)['total_cents']==2025
    for m,c,n in [('bad','cream',1),('PETG','bad',1),('PETG','cream',31),('PETG','cream',0)]:
        with pytest.raises(Exception):quote(p,m,c,n)
    p.configuration='{}'
    assert options(p)['materials']=={'PETG':10000}
from test_z_collection import collection
from fastapi.testclient import TestClient
from app.main import app
import uuid

def test_quotes_checkout_security_and_snapshot(collection):
    c=collection;p=c.get('/api/listings?featured=true').json()['items'][0];id=p['id']
    rules={'materials':{'PLA':10000,'PETG':12000,'ABS':13500},'discounts':{'10':1000},'max_quantity':30}
    assert c.put(f'/api/listings/{id}/pricing',json=rules).status_code==200
    public=TestClient(app)
    assert public.put(f'/api/listings/{id}/pricing',json=rules).status_code==401
    conf={'material':'PETG','color':'cream','quantity':10}
    q=c.post(f'/api/listings/{id}/quote',json=conf).json()
    for patch in [{'material':'WOOD'},{'color':'unknown'},{'quantity':0},{'quantity':1.5},{'quantity':31},{'price_cents':1}]:
        assert c.post(f'/api/listings/{id}/quote',json={**conf,**patch}).status_code==422
    body={'idempotency_key':uuid.uuid4().hex,'contact':'QA','address':'QA','items':[dict(listing_id=id,expected_price_cents=1,**conf)]}
    assert c.post('/api/orders',json=body).status_code==409
    body['items'][0]['expected_price_cents']=q['unit_price_cents']
    order=c.post('/api/orders',json=body);assert order.status_code==201,order.text
    data=order.json();assert data['total_cents']==q['total_cents']
    assert data['items'][0]['material']=='PETG' and data['jobs'][0]['item']['color']=='cream'
    c.put(f'/api/listings/{id}/pricing',json={'materials':{'PETG':20000}})
    assert c.get('/api/orders').json()[0]['items'][0]['price_cents']==q['unit_price_cents']
