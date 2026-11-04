"""A fresh, isolated database per test, on the engine the suite runs against (SQLite file, or a disposable
PostgreSQL database when OPENLABS3D_TEST_POSTGRES_URL is set)."""
import os, secrets
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app import database

POSTGRES_URL = os.environ.get('OPENLABS3D_TEST_POSTGRES_URL')

def fresh_engine(tmp_path):
    if not POSTGRES_URL:
        engine = create_engine('sqlite:///' + str(tmp_path / 'isolated.db'), connect_args={'check_same_thread': False, 'timeout': 15})
        return engine, lambda: engine.dispose()
    name = 'ol3d_t_' + secrets.token_hex(4)
    admin = create_engine(POSTGRES_URL, isolation_level='AUTOCOMMIT')
    with admin.connect() as c: c.execute(text(f'CREATE DATABASE {name}'))
    engine = create_engine(make_url(POSTGRES_URL).set(database=name), pool_size=10, connect_args={'options': '-c timezone=UTC'})
    with engine.begin() as c: c.execute(text('CREATE EXTENSION IF NOT EXISTS citext'))
    def drop():
        engine.dispose()
        with admin.connect() as c: c.execute(text(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'))
        admin.dispose()
    return engine, drop

def isolate(tmp_path, monkeypatch):
    """Point the application at a fresh database. Returns (engine, SessionLocal, cleanup)."""
    engine, cleanup = fresh_engine(tmp_path)
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, 'engine', engine); monkeypatch.setattr(database, 'SessionLocal', factory)
    return engine, factory, cleanup
