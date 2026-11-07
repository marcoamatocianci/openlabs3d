"""Developer tool only: an isolated preview with its own temporary database and files, never the development data.
The feature itself needs none of this: it runs in the normal application at http://localhost:8080.

    python scripts/rack_preview.py [PORT] [DATA_DIR]

Creates test accounts, approved printing hosts with stock, and runs the CAD worker's rack queue in the background, so a
rack can go from design to host download in one process. Needs requirements-cad.txt for real CAD. Development only.
"""
import json, os, sys, tempfile, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8094
DATA = Path(sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp(prefix='ol3d-rack-'))
DATA.mkdir(parents=True, exist_ok=True)
os.environ['DATABASE_URL'] = f'sqlite:///{DATA}/preview.db'; os.environ['UPLOAD_DIR'] = str(DATA / 'uploads'); os.environ['APP_ENV'] = 'development'; os.environ['MAIL_TRANSPORT'] = 'file'
os.environ['SEED_OFFICIAL_COLLECTION'] = 'true'
sys.path.insert(0, str(ROOT / 'backend')); os.chdir(ROOT / 'backend')
from fastapi.staticfiles import StaticFiles
from app.main import app
from app.database import Base, SessionLocal, engine
from app import seed_rack_fixtures
from app.rack import queue

Base.metadata.create_all(engine)
with SessionLocal() as db:
    seed_rack_fixtures.seed(db); db.commit()
PASSWORD = seed_rack_fixtures.PASSWORD

def worker():
    while True:
        try:
            if not queue.work_once(): time.sleep(.4)
        except Exception as exc:
            print('rack worker:', exc, flush=True); time.sleep(2)
threading.Thread(target=worker, daemon=True).start()
app.mount('/', StaticFiles(directory=ROOT, html=True), name='preview')
if __name__ == '__main__':
    import uvicorn
    print(f'http://127.0.0.1:{PORT}/#design-rack  data: {DATA}  accounts: buyer@example.org, host@example.org, admin@example.org / {PASSWORD}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning')
