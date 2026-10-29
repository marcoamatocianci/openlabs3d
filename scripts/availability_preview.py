"""Temporary, isolated fixtures for tests/availability_browser.js. No development data is changed."""
import os,sys,runpy,tempfile,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];temp=tempfile.mkdtemp(prefix='ol3d-browser-')
os.environ.update(DATABASE_URL='sqlite:///'+temp+'/qa.db',UPLOAD_DIR=temp+'/uploads',APP_ENV='development',MAIL_TRANSPORT='file',SEED_OFFICIAL_COLLECTION='false')
sys.path.insert(0,str(root/'backend'))
namespace=runpy.run_path(str(root/'scripts/account_preview.py'))
from app.database import SessionLocal
from app import models
from app.main import hasher
from app.equipment import seed_equipment
with SessionLocal() as db:
    seed_equipment(db)
    for name,role in [('buyer','buyer'),('host','host'),('other','host')]:
        user=models.User(email=name+'@example.org',username=name,display_name=name,password_hash=hasher.hash('TestPassword2026'),role=role,email_verified=True,first_name='Test',last_name='User',phone='+39 011 1234567',country='IT',city='Torino')
        db.add(user);db.flush()
        if role=='host':
            db.add(models.HostApplication(user_id=user.id,status='approved'))
            colors={'PLA':{'black':'#000000','red':'#ff0000'},'PETG':{'black':'#000000'}} if name=='host' else {'PLA':{'blue':'#0000ff'},'PETG':{'white':'#ffffff'}}
            db.add(models.HostPrinter(user_id=user.id,manufacturer='QA',model=name,technology='FDM',x=200,y=200,z=200,quantity=1,materials='["PLA","PETG"]',material_colors=json.dumps(colors)))
        else:buyer=user.id
    p=models.Listing(owner_id=buyer,title='Availability QA Rack',description='Isolated browser test product',category='Tube racks',material='PLA',dimensions='100 × 100 × 100 mm',cad_dimensions='[100,100,100]',configuration='{"materials":{"PLA":10000,"PETG":12000}}',price_cents=1000,status='approved')
    db.add(p);db.commit()
print('QA_DATABASE='+temp+'/qa.db',flush=True)
import uvicorn
uvicorn.run(namespace['app'],host='0.0.0.0',port=int(os.getenv("AVAILABILITY_QA_PORT","18097")))
