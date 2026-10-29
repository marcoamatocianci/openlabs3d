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
        db.add(Listing(owner_id=admin.id,collection_key=key,model_url='/assets/models/'+key+'.glb',title=title,price_cents=price,category='Tube racks',compatibility=compat,dimensions=dims,material='PETG',configuration='{"materials":{"PLA":10000,"PETG":10000}}',listing_type='official',status='approved',featured=True,approved_by=admin.id,published_at=now(),description='OpenLabs3D rack concept with rounded edges, a perforated upper deck, structural end walls and a stable base. Procedural 3D rendering; tube fit, printing tolerances and laboratory suitability require validation before manufacture.'))
    seed_pipette_stand(db, admin)
    db.commit()

# Geometry: official_products/dna_pipette_stand_6. Pipette fit dimensions there are UNVERIFIED.
PIPETTE_STAND = 'dna-pipette-stand'
def seed_pipette_stand(db, admin):
    if not db.scalar(select(Category).where(Category.name=='Pipette holders')): db.add(Category(name='Pipette holders',active=True))
    if db.scalar(select(Listing).where(Listing.collection_key==PIPETTE_STAND)): return
    db.add(Listing(owner_id=admin.id,collection_key=PIPETTE_STAND,model_url='/assets/models/'+PIPETTE_STAND+'.glb',
        title='Rotating Pipette Stand — DNA Helix',
        # PLACEHOLDER pricing: base price and material factors are not final.
        price_cents=2900,configuration='{"materials":{"PLA":10000,"PETG":10000,"ABS":10000}}',
        category='Pipette holders',compatibility='Single-channel pipettes · 6 positions · universal knob hangers (fit unverified)',
        dimensions='190 × 190 × 288 mm (assembled)',material='PETG',listing_type='official',status='approved',featured=True,
        approved_by=admin.id,published_at=now(),
        description='A rotating bench stand for six single-channel pipettes. A double-helix tower with nucleotide rungs turns on its wide foot, '
            'and each pipette hangs by its finger hook from a knob hanger under the OpenLabs3D finial. Printed in four parts '
            '(foot, lower and upper tower, crown) with keyed joints and a printed bearing: no hardware or supports needed. '
            'The universal hanger dimensions have not yet been verified against specific pipette brands; check the fit before relying on it. '
            'Inspired by "DNA pipette stand / holder, customizable" by pixel on Printables '
            '(https://www.printables.com/model/1332410-dna-pipette-stand-holder-customizable); the geometry is an original OpenLabs3D design.'))
if __name__=='__main__':
    with SessionLocal() as db:
        admin=db.scalar(select(User).where(User.email==sys.argv[1],User.role=='admin'))
        if not admin: raise SystemExit('Existing administrator email required')
        seed(db,admin)
