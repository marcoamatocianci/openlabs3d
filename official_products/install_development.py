"""Install already validated Bridge assets into existing development records only.

Run with PYTHONPATH=backend; accepts --models and --renders directories.
Preserves all other listing fields and stores previous CAD references for rollback.
"""
import argparse, hashlib, json, shutil
from pathlib import Path
from sqlalchemy import select
from app import config, models
from app.database import SessionLocal
from app.mesh import inspect_mesh
from app.attach_official_cad import PRODUCTS

def install(root, renders):
    if config.APP_ENV != 'development':
        raise RuntimeError('Development environment required')
    data=config.UPLOAD_DIR.parent
    archive=data/'cad_backups'/'bridge_v3_finish.json'
    with SessionLocal() as db:
        pending=[]
        for key,(name,dimensions) in PRODUCTS.items():
            product=db.scalar(select(models.Listing).where(models.Listing.collection_key==key,models.Listing.listing_type=='official'))
            if product is None: raise ValueError('Missing existing product: '+key)
            payload=(root/name/(name+'.stl')).read_bytes()
            actual=inspect_mesh(payload,'.stl')
            if actual!=dimensions: raise ValueError('Changed product envelope')
            render=renders/name
            status=json.loads((render/'status.json').read_text())
            if status['status']!='ready' or status['dimensions_mm']!=dimensions: raise ValueError('Render not ready')
            for filename in ('render.png','thumb.webp','model.glb'):
                if not (render/filename).is_file(): raise ValueError('Missing render asset')
            before={c.name:getattr(product,c.name) for c in models.Listing.__table__.columns}
            pending.append((product,payload,render,before))
        if not archive.exists():
            archive.parent.mkdir(parents=True,exist_ok=True)
            archive.write_text(json.dumps([p[3] for p in pending],default=str,indent=2))
        for product,payload,render,before in pending:
            digest=hashlib.sha256(payload).hexdigest()[:48]
            (data/'cad').mkdir(exist_ok=True)
            (data/'cad'/(digest+'.stl')).write_bytes(payload)
            shutil.copytree(render,data/'renders'/digest,dirs_exist_ok=True)
            product.cad_path=digest+'.stl'
            for field,value in before.items():
                if field!='cad_path': assert getattr(product,field)==value
            print(product.id,product.collection_key,digest)
        db.flush()
        for product,payload,render,before in pending:
            for field,value in before.items():
                if field not in ('cad_path','version','updated_at'):
                    assert getattr(product,field)==value, field
        db.commit()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--models',type=Path,required=True);parser.add_argument('--renders',type=Path,required=True)
    args=parser.parse_args();install(args.models,args.renders)
