"""Isolated order-history QA fixtures; never opens the development database.
Statuses cycle pending, accepted, printing, ready, shipped, completed, cancelled (order 15: mixed jobs).
Orders 8+ carry checkout colour snapshots; earlier ones are legacy lines without one."""
import json, os, runpy, sys, tempfile, shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone
root=Path(__file__).resolve().parents[1]
temp=Path(tempfile.mkdtemp(prefix='ol3d-orders-'))
os.environ.update(DATABASE_URL='sqlite:///'+str(temp/'qa.db'),UPLOAD_DIR=str(temp/'uploads'),APP_ENV='development',MAIL_TRANSPORT='file',SEED_OFFICIAL_COLLECTION='false')
sys.path.insert(0,str(root/'backend'))
namespace=runpy.run_path(str(root/'scripts/account_preview.py'))
from app.database import SessionLocal
from app import models
from app.main import hasher
with SessionLocal() as db:
    users={}
    for name,role in [('buyer','buyer'),('other','buyer'),('empty','buyer'),('host','host')]:
        u=models.User(email=name+'@example.org',username=name,display_name=name.title(),password_hash=hasher.hash('TestPassword2026'),role=role,email_verified=True)
        db.add(u);db.flush();users[name]=u.id
    revision='a'*48
    folder=temp/'uploads'/'renders'/revision;folder.mkdir(parents=True)
    shutil.copy(root/'official_products/centrifuge_rack_15ml_12/renders/thumb.webp',folder/'thumb.webp')
    (folder/'status.json').write_text('{"status":"ready"}')
    listing=models.Listing(owner_id=users['host'],title='Updated catalogue product',price_cents=9900,material='PETG',status='approved',cad_path=revision+'.stl',configuration='{}')
    archived=models.Listing(owner_id=users['host'],title='Removed product',price_cents=9900,material='PETG',status='archived',removed=True)
    db.add_all([listing,archived]);db.flush()
    contact=json.dumps({'first_name':'Ada','last_name':'Lovelace','email':'order-contact@example.org','phone':'+39 011 1234567'})
    address=json.dumps({'street':'Via Laboratory 12','city':'Torino','country':'IT','postal_code':'10100'})
    for n in range(16):
        status=['pending','accepted','printing','ready','shipped','completed','cancelled'][n%7]
        o=models.Order(buyer_id=users['other'] if n==0 else users['buyer'],reference=f'OL3D-QA-{1000+n}',idempotency_key=f'orders-preview-{n}',contact=contact,address=address,status=status,total_cents=2400,created_at=datetime(2026,10,1,tzinfo=timezone.utc)+timedelta(days=n))
        db.add(o);db.flush()
        count=3 if n==15 else 1
        o.total_cents=2400*count
        for ix in range(count):
            item=models.OrderItem(order_id=o.id,listing_id=archived.id if ix==2 else listing.id,title=['12-position tube rack','Pipette holder','Archived sample rack'][ix],material='PLA',color=['orange','black','custom violet'][ix],color_hex=(['#e66100','#1b1b1b',''][ix] if n>=8 else ''),quantity=2,price_cents=1200,dimensions='100 × 70 × 30 mm',manufacturing_dimensions='[100,70,30]')
            db.add(item);db.flush()
            job_status='available' if status=='pending' else status
            if n==15: job_status=['printing','completed','available'][ix];o.status='printing'
            shipment=dict(carrier='DHL Express',tracking_number=f'JD{1000+n}{ix}',tracking_url=f'https://www.dhl.com/track?id=JD{1000+n}{ix}',shipping_note='Left with reception' if n==4 else '',shipped_at=o.created_at+timedelta(days=1)) if job_status in ('shipped','completed') else {}
            job=models.PrintingJob(order_id=o.id,item_id=item.id,host_id=None if job_status in ('available','cancelled') else users['host'],status=job_status,**shipment)
            db.add(job)
        db.add(models.Activity(actor_id=users['buyer'],action='order.created',subject=f'order:{o.id}',created_at=o.created_at))
    db.commit()
print('QA_DATABASE='+str(temp/'qa.db'),flush=True)
if __name__=='__main__':
    import uvicorn
    uvicorn.run(namespace['app'],host='127.0.0.1',port=18100)
