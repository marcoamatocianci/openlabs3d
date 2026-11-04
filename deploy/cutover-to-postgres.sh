#!/usr/bin/env bash
# One-time move of a running SQLite deployment to PostgreSQL, on the production server.
# See docs/deployment/POSTGRESQL_MIGRATION.md. Downtime: the time to copy (seconds for thousands of rows).
#
#   deploy/cutover-to-postgres.sh
#
# 1. stops everything that writes (Caddy first, so visitors get a clean error, then backend and worker);
# 2. snapshots the SQLite file (SQLite backup API) into the data volume and onto the host;
# 3. upgrades the SQLite schema to this release, creates the PostgreSQL schema;
# 4. copies and verifies every row (python -m app.migrate_to_postgres: one transaction, checksums);
# 5. starts the site on PostgreSQL.
# The SQLite file is never modified or removed. To go back before any new orders arrive: stop the stack,
# check out the previous release and start it (it reads the same SQLite file).
set -euo pipefail
cd "$(dirname "$0")/.."
. deploy/lib.sh
SQLITE=/app/data/openlabs3d.db
SQLITE_URL=sqlite:///$SQLITE
stamp=$(date -u +%Y%m%dT%H%M%SZ)
host_copy=${BACKUP_DIR:-/var/backups/openlabs3d}/pre-postgres-$stamp.db

prepare_secrets
if [ "${1:-}" != "--yes" ]; then
  read -r -p "This stops the site and copies its SQLite database into PostgreSQL. Type 'migrate' to continue: " answer
  [ "$answer" = migrate ] || { echo "Cancelled."; exit 1; }
fi

echo "1/5 stopping writers"
"${COMPOSE[@]}" stop caddy worker backend

echo "2/5 snapshot"
"${COMPOSE[@]}" run --rm --no-deps -T -e DATABASE_URL="$SQLITE_URL" backend python - "$stamp" <<'PY'
import sqlite3, sys
from pathlib import Path
source = Path('/app/data/openlabs3d.db')
if not source.is_file(): sys.exit('No SQLite database at /app/data/openlabs3d.db: nothing to migrate.')
target = Path(f'/app/data/backups/pre-postgres-{sys.argv[1]}.db'); target.parent.mkdir(exist_ok=True)
with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as src, sqlite3.connect(target) as dst: src.backup(dst)
print('snapshot', target, target.stat().st_size, 'bytes')
PY
mkdir -p "$(dirname "$host_copy")"
"${COMPOSE[@]}" run --rm --no-deps -T backend cat "/app/data/backups/pre-postgres-$stamp.db" > "$host_copy"
echo "host copy: $host_copy"

echo "3/5 schemas"
"${COMPOSE[@]}" run --rm --no-deps -T -e DATABASE_URL="$SQLITE_URL" backend alembic upgrade head
"${COMPOSE[@]}" up -d db
until "${COMPOSE[@]}" exec -T db pg_isready -U openlabs3d -d openlabs3d >/dev/null 2>&1; do sleep 2; done
"${COMPOSE[@]}" run --rm --no-deps -T backend alembic upgrade head

echo "4/5 copy and verify"
"${COMPOSE[@]}" run --rm --no-deps -T backend python -m app.migrate_to_postgres --source "$SQLITE"

echo "5/5 starting on PostgreSQL"
"${COMPOSE[@]}" up -d
deploy/healthcheck.sh
echo "Done. Keep $host_copy until you have verified the site and taken a PostgreSQL backup (deploy/backup.sh)."
