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
    db.add(HostPrinter(user_id=host.id,manufacturer='Fixture',model='Printer',technology='FDM',x=500,y=500,z=500,quantity=1,materials=json.dumps(['PLA','PETG','ABS']),capabilities=json.dumps(['PLA','PETG','ABS']),material_colors=json.dumps({m:colors for m in ['PLA','PETG','ABS']})))
