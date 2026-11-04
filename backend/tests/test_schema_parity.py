"""The models equal the migrated schema, on both databases, and existing SQLite data moves to PostgreSQL exactly.

PostgreSQL databases are created from the models at head (migrations/env.py: bootstrap_postgresql), while
SQLite databases replay every revision. That is only sound while the two agree, which this file proves.
The PostgreSQL parts run when OPENLABS3D_TEST_POSTGRES_URL is set.
"""
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app import models
from app.database import Base

BACKEND = Path(__file__).resolve().parents[1]
POSTGRES_URL = os.environ.get('OPENLABS3D_TEST_POSTGRES_URL')
# Equivalent on SQLite, where VARCHAR lengths are not enforced and a UNIQUE column is reflected as an index.
SQLITE_EQUIVALENT = {('modify_type', 'cart_items', 'color'), ('modify_type', 'order_items', 'color'),
                     ('modify_type', 'orders', 'contact'), ('modify_type', 'orders', 'address'),
                     ('remove_index', 'ix_listing_collection'), ('add_constraint', 'collection_key'),
                     ('remove_index', 'uq_users_username'), ('add_constraint', 'username')}

def upgrade(url, revision='head'):
    env = {**os.environ, 'DATABASE_URL': url, 'PYTHONPATH': str(BACKEND)}
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', revision], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-3000:]

def differences(url):
    engine = create_engine(url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection, opts={'compare_type': True}), Base.metadata)
    engine.dispose()
    flat = [d[0] if isinstance(d, list) else d for d in diff]
    def key(d):
        kind = d[0]
        if kind == 'modify_type': return (kind, d[2], d[3])
        if kind == 'remove_index': return (kind, d[1].name)
        if kind == 'add_constraint': return (kind, next(iter(d[1].columns)).name)
        return (kind, str(d[1:]))
    return {key(d) for d in flat}

def test_sqlite_migration_chain_matches_the_models(tmp_path):
    url = 'sqlite:///' + str(tmp_path / 'chain.db')
    upgrade(url)
    assert differences(url) <= SQLITE_EQUIVALENT

@pytest.fixture
def postgres_database():
    if not POSTGRES_URL: pytest.skip('OPENLABS3D_TEST_POSTGRES_URL not set')
    import secrets
    name = 'ol3d_parity_' + secrets.token_hex(4)
    admin = create_engine(POSTGRES_URL, isolation_level='AUTOCOMMIT')
    with admin.connect() as c: c.execute(text(f'CREATE DATABASE {name}'))
    yield make_url(POSTGRES_URL).set(database=name).render_as_string(hide_password=False)
    with admin.connect() as c: c.execute(text(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'))
    admin.dispose()

def test_postgresql_bootstrap_matches_the_models_and_is_idempotent(postgres_database):
    upgrade(postgres_database); upgrade(postgres_database)
    assert differences(postgres_database) == set()

def test_sqlite_data_moves_to_postgresql_exactly(tmp_path, postgres_database):
    from app.migrate_to_postgres import migrate
    from sqlalchemy.orm import Session
    source = tmp_path / 'source.db'; upgrade('sqlite:///' + str(source)); upgrade(postgres_database)
    sqlite = create_engine('sqlite:///' + str(source))
    long_contact = json.dumps({'first_name': 'Ada' * 40, 'last_name': 'Bench', 'phone': '+39', 'email': 'a@example.org'})
    with Session(sqlite) as db:
        users = [models.User(id=40 + i, email=f'u{i}@example.org', display_name='U', username=f'MixedCase{i}', password_hash='$argon2id$v=19$x',
                             role=('buyer', 'host', 'admin')[i], email_verified=bool(i % 2), created_at=datetime(2026, 1, 2, 3, 4, 5, 6789, tzinfo=timezone.utc)) for i in range(3)]
        db.add_all(users); db.flush()
        db.add(models.Listing(id=7, owner_id=41, title='Rack', status='approved', price_cents=1999, cad_dimensions='[1, 2, 3]'))
        db.add(models.HostPrinter(user_id=41, manufacturer='Q', model='A', technology='FDM', x=220.5, y=220, z=250, quantity=2))
        db.add(models.Order(id=90, reference='OL3D-X', buyer_id=40, idempotency_key='k', contact=long_contact, address='{}', total_cents=1999))
        db.commit()
    target = create_engine(postgres_database, connect_args={'options': '-c timezone=UTC'})
    copied = migrate(source, target, Base.metadata, report=lambda *_: None)
    assert copied['users'][0] == 3 and copied['orders'][0] == 1
    with Session(target) as db:
        assert db.get(models.User, 41).username == 'MixedCase1' and db.get(models.User, 40).created_at == datetime(2026, 1, 2, 3, 4, 5, 6789, tzinfo=timezone.utc)
        assert db.get(models.Order, 90).contact == long_contact and db.get(models.Listing, 7).price_cents == 1999
        assert db.scalar(select(models.User.id).where(models.User.username == 'mixedcase2')) == 42, 'usernames stay case-insensitive'
        db.add(models.User(email='new@example.org', display_name='N', username='Fresh', password_hash='x')); db.commit()
        assert db.scalar(select(func.max(models.User.id))) == 43, 'sequences continue after the copied ids'
    with pytest.raises(SystemExit, match='not empty'):
        migrate(source, target, Base.metadata, report=lambda *_: None)
    target.dispose(); sqlite.dispose()
