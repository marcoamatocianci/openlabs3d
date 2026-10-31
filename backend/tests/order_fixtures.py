import json
CONTACT=json.dumps({'first_name':'Test','last_name':'Buyer','phone':'+39 011 1234567'})
ADDRESS=json.dumps({'country':'IT','city':'Torino','street':'Test address'})

def provision_test_host(db):
    """Explicit capabilities for purchase fixtures; never seed application inventory."""
    import uuid
    from app.models import User,HostApplication,HostPrinter
    host=User(email=uuid.uuid4().hex+'@example.org',display_name='Fixture host',password_hash='unused',role='host',email_verified=True)
    db.add(host);db.flush();db.add(HostApplication(user_id=host.id,status='approved'))
    colors={'black':'#000000','cream':'#e7d9bc','signal-red':'#d9424d','aqua-blue':'#429fb7'}
    from app.availability import set_host_inventory
    db.add(HostPrinter(user_id=host.id,manufacturer='Fixture',model='Printer',technology='FDM',x=500,y=500,z=500,quantity=1,capabilities=json.dumps(['PLA','PETG','ABS'])))
    set_host_inventory(db,host.id,{m:colors for m in ['PLA','PETG','ABS']})

def with_confirmation(client, body):
    """Add the lines a checkout page submits: each with the unit price shown to the buyer. Prices
    come from the server (quote or basket), exactly as the page displays them."""
    if body.get('direct'):
        line = body['direct']
        response = client.post(f"/api/listings/{line['listing_id']}/quote", json={k: line[k] for k in ('material', 'color', 'quantity') if k in line})
        lines = [{**line, 'unit_price_cents': response.json()['unit_price_cents'] if response.status_code == 200 else 0}]
    else:
        lines = [{**{k: row[k] for k in ('listing_id', 'material', 'color', 'quantity')}, 'unit_price_cents': row.get('unit_price_cents', 0)} for row in client.get('/api/cart').json()]
    return {**body, 'confirmed': lines or [{'listing_id': 1, 'material': '', 'color': '', 'quantity': 1, 'unit_price_cents': 0}]}
