"""One engine and connection pool per process, for SQLite (development, tests) or PostgreSQL (production).

Write serialization is the same on both: a mutating request holds the database's single writer lock from
before its authentication and eligibility reads until it commits or rolls back. Checkout, job acceptance,
equipment edits, suspensions and stock changes were written against that guarantee (see write_lock).
"""
import os
from sqlalchemy import create_engine, event, text
from fastapi import Request
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import DATABASE_URL

IS_SQLITE = DATABASE_URL.startswith('sqlite')
# Arbitrary constant naming the one application-wide writer lock (pg_advisory_xact_lock key).
WRITER_LOCK_KEY = 0x0153_D3D0

def _engine():
    if IS_SQLITE:
        return create_engine(DATABASE_URL, connect_args={'check_same_thread': False, 'timeout': 15})
    # Sized for one Uvicorn process (40 threadpool threads, most requests never touch the pool for long) plus
    # the email thread. The CAD worker is a separate process with its own small pool.
    return create_engine(
        DATABASE_URL,
        pool_size=int(os.getenv('DB_POOL_SIZE', '8')),
        max_overflow=int(os.getenv('DB_MAX_OVERFLOW', '8')),
        pool_timeout=15,
        pool_pre_ping=True,            # survives a PostgreSQL restart without failing the first request
        pool_recycle=1800,
        connect_args={
            # UTC sessions: stored timestamps are timestamptz and the code compares them with aware UTC datetimes.
            # lock_timeout matches SQLite's busy timeout; the others stop a stuck request holding locks forever.
            'options': '-c timezone=UTC -c lock_timeout=15000 -c statement_timeout=30000 '
                       '-c idle_in_transaction_session_timeout=60000',
            'application_name': os.getenv('DB_APPLICATION_NAME', 'openlabs3d-web'),
        },
    )

engine = _engine()
if IS_SQLITE:
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

def write_lock(db):
    """Take the writer lock for the rest of this transaction; it is released by commit or rollback.

    SQLite: BEGIN IMMEDIATE reserves its only writer. PostgreSQL: a transaction-scoped advisory lock gives
    the same ordering between mutating requests, while reads (GET) and row-level work elsewhere carry on."""
    if db.get_bind().dialect.name == 'sqlite':
        db.execute(text('BEGIN IMMEDIATE'))
    else:
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': WRITER_LOCK_KEY})

def get_db(request: Request):
    with SessionLocal() as db:
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            write_lock(db)
        yield db
