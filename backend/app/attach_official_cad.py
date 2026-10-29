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
# Multi-part products: hosts download the kit 3MF (one object per printable part), while the stored
# renders come from the assembled model. cad_dimensions is the per-axis maximum over the sorted part
# envelopes, so printer matching requires every part to fit, not the assembly.
KITS={'dna-pipette-stand':'dna_pipette_stand_6'}
def attach_kit(db,key,root=None):
    import shutil
    from .mesh import inspect_mesh
    folder=(root or Path(__file__).resolve().parents[2]/'official_products')/KITS[key]
    product=db.scalar(select(models.Listing).where(models.Listing.collection_key==key,models.Listing.listing_type=='official'))
    if product is None:raise ValueError('Existing official product missing: '+key)
    data=(folder/(folder.name+'.3mf')).read_bytes();inspect_mesh(data,'.3mf')
    dims=json.loads((folder/'validation.json').read_text())['host_cad_dimensions_mm']
    if json.loads((folder/'renders'/'status.json').read_text()).get('status')!='ready':raise ValueError('Render assets not ready: '+key)
    digest=hashlib.sha256(data).hexdigest()[:48]
    (config.UPLOAD_DIR.parent/'cad').mkdir(parents=True,exist_ok=True);(config.UPLOAD_DIR.parent/'cad'/(digest+'.3mf')).write_bytes(data)
    shutil.copytree(folder/'renders',config.UPLOAD_DIR.parent/'renders'/digest,dirs_exist_ok=True)
    product.cad_path=digest+'.3mf';product.cad_dimensions=json.dumps(dims);db.commit()
    return product
if __name__=='__main__':
    with SessionLocal() as db:
        attach(db)
        for key in KITS:attach_kit(db,key)
