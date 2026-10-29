"""Explicit development-only update of existing official rack material prices."""
import json
from sqlalchemy import select
from . import config, models
from .database import SessionLocal
KEYS=('microtube-rack','15ml-rack','50ml-rack')
def update(db):
    rows=db.scalars(select(models.Listing).where(models.Listing.listing_type=='official',models.Listing.collection_key.in_(KEYS))).all()
    if len(rows)!=3: raise ValueError('Expected all three existing official racks')
    for p in rows:
        rules=json.loads(p.configuration or '{}')
        materials=rules.get('materials') or {p.material:10000}
        if 'PETG' not in materials: raise ValueError('Missing PETG pricing')
        rules['materials']={**materials,'PLA':materials['PETG']}
        p.configuration=json.dumps(rules)
    db.commit()
if __name__=='__main__':
    if config.APP_ENV!='development':raise SystemExit('Development only')
    with SessionLocal() as db:update(db)
