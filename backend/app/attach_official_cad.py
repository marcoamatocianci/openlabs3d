"""Attach generated STL assets to existing official records; creates no products.
Run explicitly with the intended local DATABASE_URL and UPLOAD_DIR:
python -m app.attach_official_cad
python -m app.attach_official_cad --listing ID --kit FOLDER [--root DIR]   (one kit onto one official listing)
"""
import hashlib,json
from pathlib import Path
from sqlalchemy import select
from . import config,models
from .database import SessionLocal
ROOT=Path(__file__).resolve().parents[2]/'official_products'
PRODUCTS={'microtube-rack':('microtube_rack_24',[118,82,32]),'15ml-rack':('centrifuge_rack_15ml_12',[110,85,52]),'50ml-rack':('centrifuge_rack_50ml_6',[124,86,62])}
def attach(db,root=None):
    root=root or ROOT
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
    product=db.scalar(select(models.Listing).where(models.Listing.collection_key==key,models.Listing.listing_type=='official'))
    if product is None:raise ValueError('Existing official product missing: '+key)
    return attach_kit_files(db,product,(root or ROOT)/KITS[key])
def attach_kit_files(db,product,folder,describe=False):
    """Store the kit as the listing's CAD and its assembly renders as the listing's visuals. Orders keep the
    model they were sold with (see manufacturing.py); the listing version advances with this change.
    describe also sets the listing's dimensions text from the assembled size."""
    import shutil
    from .mesh import inspect_mesh
    data=(folder/(folder.name+'.3mf')).read_bytes();inspect_mesh(data,'.3mf')
    report=json.loads((folder/'validation.json').read_text())
    if json.loads((folder/'renders'/'status.json').read_text()).get('status')!='ready':raise ValueError('Render assets not ready: '+folder.name)
    digest=hashlib.sha256(data).hexdigest()[:48]
    (config.UPLOAD_DIR.parent/'cad').mkdir(parents=True,exist_ok=True);(config.UPLOAD_DIR.parent/'cad'/(digest+'.3mf')).write_bytes(data)
    shutil.copytree(folder/'renders',config.UPLOAD_DIR.parent/'renders'/digest,dirs_exist_ok=True)
    product.cad_path=digest+'.3mf';product.cad_dimensions=json.dumps(report['host_cad_dimensions_mm'])
    if describe:
        x,y,z=(round(v) for v in report['assembled_dimensions_mm'])
        product.dimensions=f"{x} × {y} × {z} mm (assembled, {len(report['parts'])} printed parts)"
    db.commit()
    return product
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--listing',type=int,help='official listing id to receive one kit')
    parser.add_argument('--kit',help='kit folder name under the root, e.g. pipette_holder')
    parser.add_argument('--root',type=Path,default=ROOT,help='folder holding the official products')
    args=parser.parse_args()
    if bool(args.listing)!=bool(args.kit):parser.error('--listing and --kit go together')
    with SessionLocal() as db:
        if args.listing:
            product=db.get(models.Listing,args.listing)
            if product is None or product.listing_type!='official' or product.removed or product.status=='archived':
                raise SystemExit('An existing, non-archived official listing is required')
            attach_kit_files(db,product,args.root/args.kit,describe=True)
            db.add(models.Activity(action='product.cad_attached',subject=f'listing:{product.id}',detail=f'kit {args.kit} -> {product.cad_path}'));db.commit()
            print(f'listing {product.id}: {product.cad_path} {product.cad_dimensions} "{product.dimensions}" version {product.version} status {product.status}')
        else:
            attach(db)
            for key in KITS:attach_kit(db,key)
