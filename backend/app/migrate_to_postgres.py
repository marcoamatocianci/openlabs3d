"""Copy an OpenLabs3D SQLite database into an empty PostgreSQL database, then prove the copy is exact.

    python -m app.migrate_to_postgres --source /app/data/openlabs3d.db [--target postgresql+psycopg://...]

Run with the application stopped (see docs/deployment/POSTGRESQL_MIGRATION.md). The target must already have
the schema (`alembic upgrade head`) and no rows. The tool:

1. snapshots the source through SQLite's online backup API and checks its integrity and foreign keys;
2. requires both databases to be at the same Alembic revision;
3. copies every table in foreign-key order, keeping every primary key, inside one PostgreSQL transaction;
4. moves each id sequence past the copied rows;
5. compares row counts and a SHA-256 of every table's normalized contents, read back from PostgreSQL;
6. commits only if everything matches. The source file is opened read-only and never changed.
"""
import argparse, hashlib, json, sqlite3, sys, tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine

IGNORED_SOURCE_TABLES = {'alembic_version', 'sqlite_sequence', 'sqlite_stat1'}
CHUNK = 1000

def normalize(value):
    if isinstance(value, datetime):
        # Every stored timestamp is UTC; SQLite returns it without a zone, PostgreSQL with one.
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    if isinstance(value, bool): return int(value)
    if isinstance(value, float): return repr(value)
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, bytes): return value.hex()
    return value

def table_digest(conn, table):
    order = list(table.primary_key.columns) or list(table.columns)
    digest, count = hashlib.sha256(), 0
    for row in conn.execute(select(table).order_by(*order)).yield_per(CHUNK):
        digest.update(json.dumps([normalize(v) for v in row], default=str).encode()); count += 1
    return count, digest.hexdigest()

def revision(conn):
    if not inspect(conn).has_table('alembic_version'): return None
    return conn.execute(text('SELECT version_num FROM alembic_version')).scalar()

def snapshot(source: Path, directory: str) -> Path:
    copy = Path(directory) / 'source.db'
    with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as src, sqlite3.connect(copy) as dst:
        src.backup(dst)
    with sqlite3.connect(copy) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise SystemExit('Source failed PRAGMA integrity_check')
        problems = db.execute('PRAGMA foreign_key_check').fetchall()
        if problems: raise SystemExit(f'Source has {len(problems)} foreign-key violations, e.g. {problems[:3]}')
    return copy

def migrate(source: Path, target: Engine, metadata, report=print):
    with tempfile.TemporaryDirectory(prefix='ol3d-migrate-') as temp:
        copy = snapshot(source, temp)
        src = create_engine(f'sqlite:///{copy}')
        with src.connect() as s, target.begin() as t:
            # A single transaction from the emptiness check to the verification: all or nothing.
            if t.dialect.name != 'postgresql': raise SystemExit('Target must be PostgreSQL')
            src_rev, dst_rev = revision(s), revision(t)
            if not dst_rev: raise SystemExit('Target has no schema. Run `alembic upgrade head` against it first.')
            if src_rev != dst_rev:
                raise SystemExit(f'Source is at {src_rev}, target at {dst_rev}. Upgrade the source with the same release first.')
            known = {table.name for table in metadata.sorted_tables}
            unknown = set(inspect(s).get_table_names()) - known - IGNORED_SOURCE_TABLES
            if unknown: raise SystemExit(f'Source has tables this release does not know: {sorted(unknown)}')
            occupied = [table.name for table in metadata.sorted_tables if t.execute(select(func.count()).select_from(table)).scalar()]
            if occupied: raise SystemExit(f'Target is not empty ({", ".join(occupied)}). This tool never overwrites data.')
            source_tables = set(inspect(s).get_table_names())
            expected = {}
            t.execute(text('SET CONSTRAINTS ALL DEFERRED'))
            for table in metadata.sorted_tables:
                if table.name not in source_tables:
                    expected[table.name] = (0, hashlib.sha256().hexdigest()); continue
                expected[table.name] = table_digest(s, table)
                batch = []
                for row in s.execute(select(table)).mappings().yield_per(CHUNK):
                    batch.append(dict(row))
                    if len(batch) == CHUNK: t.execute(table.insert(), batch); batch = []
                if batch: t.execute(table.insert(), batch)
                report(f'  copied {table.name}: {expected[table.name][0]} rows')
            for table in metadata.sorted_tables:
                pk = list(table.primary_key.columns)
                if len(pk) == 1 and pk[0].autoincrement in (True, 'auto') and pk[0].type.python_type is int:
                    t.execute(text("SELECT setval(pg_get_serial_sequence(:t, :c), COALESCE((SELECT MAX({c}) FROM {t}), 1), "
                                   "(SELECT MAX({c}) FROM {t}) IS NOT NULL)".format(c=pk[0].name, t=table.name)),
                              {'t': table.name, 'c': pk[0].name})
            mismatches = []
            for table in metadata.sorted_tables:
                actual = table_digest(t, table)
                if actual != expected[table.name]: mismatches.append((table.name, expected[table.name], actual))
            if mismatches:
                raise SystemExit('Verification failed, nothing was committed: ' + '; '.join(
                    f'{name}: expected {e[0]} rows {e[1][:12]}, got {a[0]} rows {a[1][:12]}' for name, e, a in mismatches))
        report(f'Verified and committed {sum(c for c, _ in expected.values())} rows in {len(expected)} tables '
               '(row counts and SHA-256 of contents match).')
        return expected

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, default=Path('/app/data/openlabs3d.db'))
    parser.add_argument('--target', help='PostgreSQL URL; defaults to DATABASE_URL')
    args = parser.parse_args(argv)
    if not args.source.is_file(): raise SystemExit(f'No SQLite database at {args.source}')
    from . import config, models  # noqa: F401  (registers every table)
    from .database import Base
    target = create_engine(args.target or config.DATABASE_URL, connect_args={'options': '-c timezone=UTC'})
    migrate(args.source, target, Base.metadata)

if __name__ == '__main__':
    sys.exit(main())
