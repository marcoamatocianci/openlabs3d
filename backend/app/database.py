from sqlalchemy import create_engine, event, text
from fastapi import Request
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False, 'timeout': 15} if DATABASE_URL.startswith('sqlite') else {})
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def configure_sqlite(connection, _):
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA busy_timeout=15000')
        cursor.close()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
class Base(DeclarativeBase):
    pass

def get_db(request: Request):
    with SessionLocal() as db:
        # SQLite is the deployed database. Reserve the writer before auth/eligibility
        # reads, so equipment edits, suspensions, checkout and assignment serialize.
        # The reservation survives validation until the endpoint commits or rolls back.
        if engine.dialect.name == 'sqlite' and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            db.execute(text('BEGIN IMMEDIATE'))
        yield db
