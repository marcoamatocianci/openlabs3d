"""Isolated local verification server, never uses the deployment database."""
import os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ['DATABASE_URL']='sqlite:////tmp/openlabs-collection-preview.db'
os.environ['UPLOAD_DIR']='/tmp/openlabs-collection-preview-uploads'
sys.path.insert(0,str(ROOT/'backend'))
from app.main import app, hasher
from app.database import engine,Base,SessionLocal
from app.models import User
from app.seed_collection import seed
from sqlalchemy import select
from fastapi.staticfiles import StaticFiles
Base.metadata.create_all(engine)
with SessionLocal() as db:
    admin=db.scalar(select(User).where(User.email=='preview@example.org'))
    if not admin:
        admin=User(email='preview@example.org',display_name='Preview Admin',password_hash=hasher.hash('preview-only-password'),role='admin');db.add(admin);db.commit()
    seed(db,admin)
app.mount('/',StaticFiles(directory=ROOT,html=True),name='preview')
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8091)
