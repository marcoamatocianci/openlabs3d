"""Idempotent official collection. Run explicitly: python -m app.seed_collection ADMIN_EMAIL.
Only inserts missing collection keys; never edits user listings or existing orders.
"""
import sys
from sqlalchemy import select
from .database import SessionLocal
from .models import Listing, User, Category, now

def seed(db, admin):
    if admin.role != 'admin': raise ValueError('Administrator required')
    if not db.scalar(select(Category).where(Category.name=='Tube racks')): db.add(Category(name='Tube racks',active=True))
    for key,title,price,compat,dims in [
        ('microtube-rack','Microtube Rack — 1.5/2 mL',1800,'1.5/2 mL microtubes · 24 positions','118 × 82 × 32 mm'),
        ('15ml-rack','Centrifuge Tube Rack — 15 mL',2200,'15 mL conical tubes · 12 positions','110 × 85 × 52 mm'),
        ('50ml-rack','Centrifuge Tube Rack — 50 mL',2400,'50 mL conical tubes · 6 positions','124 × 86 × 62 mm')]:
        if db.scalar(select(Listing).where(Listing.collection_key==key)): continue
        db.add(Listing(owner_id=admin.id,collection_key=key,model_url='/assets/models/'+key+'.glb',title=title,price_cents=price,category='Tube racks',compatibility=compat,dimensions=dims,material='PETG',listing_type='official',status='approved',featured=True,approved_by=admin.id,published_at=now(),description='OpenLabs3D rack concept with rounded edges, a perforated upper deck, structural end walls and a stable base. Procedural 3D rendering; tube fit, printing tolerances and laboratory suitability require validation before manufacture.'))
    db.commit()
if __name__=='__main__':
    with SessionLocal() as db:
        admin=db.scalar(select(User).where(User.email==sys.argv[1],User.role=='admin'))
        if not admin: raise SystemExit('Existing administrator email required')
        seed(db,admin)
