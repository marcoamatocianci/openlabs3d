"""Isolated official-collection fixtures for the catalogue browser tests (temporary database and files).
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/catalogue_preview.py
Serves http://127.0.0.1:18101 (CATALOGUE_QA_PORT). Accounts (password TestPassword2026): buyer, host,
other and admin @example.org. Products: the three Bridge racks and the DNA pipette stand, published,
with their CAD files and studio renders. Stock is fixed, so colour options are deterministic:
  host:  PLA cream, orange #e66100, signal-red, black #1b1b1b · PETG white, cream, signal-red · ABS cream, signal-red
  other: PLA black #2b2b2b (a second shade of "black", shown as two options)
"""
import json, os, runpy, shutil, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]; temp = tempfile.mkdtemp(prefix='ol3d-catalogue-')
os.environ.update(DATABASE_URL='sqlite:///' + temp + '/qa.db', UPLOAD_DIR=temp + '/uploads', APP_ENV='development', MAIL_TRANSPORT='file', SEED_OFFICIAL_COLLECTION='false')
sys.path.insert(0, str(root / 'backend'))
namespace = runpy.run_path(str(root / 'scripts/account_preview.py'))
from sqlalchemy import select
from app import config, models
from app.database import SessionLocal
from app.main import hasher
from app.equipment import seed_equipment
from app.seed_collection import seed
from app.attach_official_cad import PRODUCTS, attach, attach_kit

STOCK = {'host': {'PLA': {'cream': '#eeeecc', 'orange': '#e66100', 'signal-red': '#c1121f', 'black': '#1b1b1b'},
                  'PETG': {'white': '#ffffff', 'cream': '#eeeecc', 'signal-red': '#c1121f'},
                  'ABS': {'cream': '#eeeecc', 'signal-red': '#c1121f'}},
         'other': {'PLA': {'black': '#2b2b2b'}}}
with SessionLocal() as db:
    seed_equipment(db); users = {}
    for name, role in (('admin', 'admin'), ('buyer', 'buyer'), ('host', 'host'), ('other', 'host')):
        u = models.User(email=name + '@example.org', username=name, display_name=name.title(), password_hash=hasher.hash('TestPassword2026'), role=role, email_verified=True,
                        first_name='Test', last_name=name.title(), phone='+39 011 1234567', country='IT', city='Torino', street='Via Roma 1')
        db.add(u); db.flush(); users[name] = u
        if name in STOCK:
            db.add(models.HostApplication(user_id=u.id, status='approved'))
            materials = sorted(STOCK[name])
            db.add(models.HostPrinter(user_id=u.id, manufacturer='QA', model=name, technology='FDM', x=300, y=300, z=320, quantity=1,
                                      materials=json.dumps(materials), capabilities=json.dumps(materials), material_colors=json.dumps(STOCK[name])))
    seed(db, users['admin']); db.flush()
    # The pipette stand's placeholder rules also sell ABS; the racks sell PLA and PETG.
    attach(db)
    for key, (name, _) in PRODUCTS.items():
        product = db.scalar(select(models.Listing).where(models.Listing.collection_key == key))
        shutil.copytree(root / 'official_products' / name / 'renders', config.UPLOAD_DIR.parent / 'renders' / Path(product.cad_path).stem, dirs_exist_ok=True)
    attach_kit(db, 'dna-pipette-stand')
    db.commit()
print('QA_DATABASE=' + temp + '/qa.db', flush=True)
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(namespace['app'], host='127.0.0.1', port=int(os.getenv('CATALOGUE_QA_PORT', '18101')))
