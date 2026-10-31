"""Isolated account QA server; run with development dependencies installed."""
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/ol-accounts-preview.db')
os.environ.setdefault('UPLOAD_DIR','/tmp/ol-accounts-preview-uploads')
os.environ.setdefault('PUBLIC_BASE_URL','http://localhost:8096')
os.environ['MAIL_TRANSPORT']='file'
sys.path.insert(0,str(ROOT/'backend'))
from alembic.config import Config
from alembic import command
cfg=Config(str(ROOT/'backend/alembic.ini'));cfg.set_main_option('script_location',str(ROOT/'backend/migrations'))
command.upgrade(cfg,'head')
from app.main import app
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
app.mount('/assets',StaticFiles(directory=ROOT/'assets'),name='assets')
@app.get('/')
def index(): return FileResponse(ROOT/'index.html',headers={'Cache-Control':'no-store'})
@app.get('/{filename}')
def public_file(filename:str):
    from fastapi import HTTPException
    if filename not in ('app.js','marketplace.js','operations.js','collection.js','style.css','index.html'):raise HTTPException(404)
    return FileResponse(ROOT/filename,headers={"Cache-Control":"no-store"})
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8096)
