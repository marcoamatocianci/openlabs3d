"""Alembic environment for SQLite (development) and PostgreSQL (production).

The revisions up to 77a were written for SQLite and are only ever replayed there. A new, empty PostgreSQL
database is instead created from the models at the current head and stamped with it (bootstrap_postgresql);
tests/test_schema_parity.py proves those models equal the migrated schema. Every revision after 77a must
run on both dialects. Existing data is copied over with `python -m app.migrate_to_postgres`.
"""
from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import engine_from_config, inspect, pool, text
from app.database import Base
from app import models, config

config_obj = context.config
config_obj.set_main_option('sqlalchemy.url', config.DATABASE_URL.replace('%', '%%'))
target_metadata = Base.metadata

def bootstrap_postgresql(connection):
    """Create the head schema in an empty PostgreSQL database. Returns True when it did."""
    if connection.dialect.name != 'postgresql':
        return False
    tables = set(inspect(connection).get_table_names())
    if 'alembic_version' in tables:
        return False
    if tables:
        raise SystemExit('PostgreSQL database has tables but no alembic_version; refusing to touch it. '
                         'Restore it from a backup or drop it before migrating.')
    head = ScriptDirectory.from_config(config_obj).get_current_head()
    connection.execute(text('CREATE EXTENSION IF NOT EXISTS citext'))
    target_metadata.create_all(connection)
    connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
    connection.execute(text('INSERT INTO alembic_version (version_num) VALUES (:head)'), {'head': head})
    print(f'Created the PostgreSQL schema at revision {head}.')
    return True

if context.is_offline_mode():
    context.configure(url=config.DATABASE_URL, target_metadata=target_metadata, literal_binds=True, dialect_opts={'paramstyle':'named'})
    with context.begin_transaction(): context.run_migrations()
else:
    engine = engine_from_config(config_obj.get_section(config_obj.config_ini_section), prefix='sqlalchemy.', poolclass=pool.NullPool)
    with engine.connect() as connection:
        if connection.dialect.name == 'postgresql':
            # One migrator at a time, even if two containers start together.
            # Session-level lock: it outlives the commit below and ends with the connection.
            connection.execute(text('SELECT pg_advisory_lock(7710001)')); connection.commit()
            with connection.begin():
                bootstrap_postgresql(connection)
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction(): context.run_migrations()
