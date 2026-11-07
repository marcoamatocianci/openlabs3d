"""Test accounts, hosts and stock for a disposable QA database: python -m app.seed_rack_fixtures

Refuses to run without OPENLABS3D_QA_FIXTURES=yes, because it adds hosts that would then receive real jobs. Used by
scripts/rack_preview.py and the isolated Compose stack in docs/features/PARAMETRIC_RACK_CONFIGURATOR.md.
"""
import json, os
from sqlalchemy import select
from .main import hasher       # first: it completes the application's import order
from . import models
from .availability import set_host_inventory
from .equipment import seed_equipment

PASSWORD = 'Preview-only-1'
STOCK = {'PLA': {'black': '#1f2328', 'signal-red': '#d9424d', 'aqua-blue': '#429fb7', 'cream': '#e7d9bc'}, 'PETG': {'black': '#1f2328', 'orange': '#e66a3c'}}

def seed(db):
    seed_equipment(db)
    if db.scalar(select(models.User).where(models.User.email == 'buyer@example.org')): return
    ids = {}
    for name, role in (('admin', 'admin'), ('buyer', 'buyer'), ('host', 'host'), ('smallhost', 'host')):
        user = models.User(email=f'{name}@example.org', password_hash=hasher.hash(PASSWORD), display_name=name, username=name, role=role, email_verified=True, first_name='Test', last_name=name.title(), phone='+39 011 1234567', country='IT', city='Torino', street='Via Roma 1', postal_code='10100', region='TO')
        db.add(user); db.flush(); ids[name] = user.id
        if role == 'host': db.add(models.HostApplication(user_id=user.id, status='approved', name=name))
        db.add(models.UserAddress(user_id=user.id, label='Lab', first_name='Test', last_name=name.title(), phone='+39 011 1234567', country='IT', city='Torino', region='TO', postal_code='10100', street='Via Roma 1', is_default=True))
    db.add(models.HostPrinter(user_id=ids['host'], manufacturer='Bambu Lab', model='P1S', technology='FDM', x=256, y=256, z=256, quantity=1, capabilities=json.dumps(['PLA', 'PETG'])))
    db.add(models.HostPrinter(user_id=ids['smallhost'], manufacturer='Bambu Lab', model='A1 mini', technology='FDM', x=180, y=180, z=180, quantity=1, capabilities=json.dumps(['PLA'])))
    set_host_inventory(db, ids['host'], STOCK); set_host_inventory(db, ids['smallhost'], {'PLA': {'black': '#1f2328'}})

if __name__ == '__main__':
    if os.environ.get('OPENLABS3D_QA_FIXTURES') != 'yes': raise SystemExit('Set OPENLABS3D_QA_FIXTURES=yes, and only on a disposable database.')
    from .database import SessionLocal
    with SessionLocal() as session:
        seed(session); session.commit()
    print('QA fixtures ready')
