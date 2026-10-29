"""Attach generated STL assets to existing official records; creates no products.
Run explicitly with the intended local DATABASE_URL and UPLOAD_DIR:
python -m app.attach_official_cad
"""
import hashlib,json
from pathlib import Path
from sqlalchemy import select
from . import config,models
from .database import SessionLocal
PRODUCTS={'microtube-rack':('microtube_rack_24',[118,82,32]),'15ml-rack':('centrifuge_rack_15ml_12',[110,85,52]),'50ml-rack':('centrifuge_rack_50ml_6',[124,86,62])}
def attach(db,root=None):
    root=root or Path(__file__).resolve().parents[2]/'official_products'
    products=[]
    for key,(name,dims) in PRODUCTS.items():
        product=db.scalar(select(models.Listing).where(models.Listing.collection_key==key,models.Listing.listing_type=='official'))
        if product is None:raise ValueError('Existing official product missing: '+key)
        data=(root/name/(name+'.stl')).read_bytes()
        products.append((product,data,dims))
    directory=config.UPLOAD_DIR.parent/'cad';directory.mkdir(parents=True,exist_ok=True)
    for product,data,dims in products:
        filename=hashlib.sha256(data).hexdigest()[:48]+'.stl'
        (directory/filename).write_bytes(data)
        product.cad_path=filename;product.cad_dimensions=json.dumps(dims)
    db.commit()
if __name__=='__main__':
    with SessionLocal() as db:attach(db)
