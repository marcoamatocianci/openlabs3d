#!/usr/bin/env bash
# Restore a backup made by deploy/backup.sh into a CLEAN production environment (new server, or after the
# volumes were deliberately removed). Refuses to touch a database or upload volume that already holds data.
#
#   deploy/restore.sh /var/backups/openlabs3d/20261104T030000Z
#   (from restic first:  restic restore latest --tag openlabs3d --target /tmp/restore)
set -euo pipefail
cd "$(dirname "$0")/.."
source=${1:?Usage: deploy/restore.sh BACKUP_DIRECTORY}
. deploy/lib.sh
( cd "$source" && sha256sum --check --quiet SHA256SUMS )
if [ ! -f secrets/db_password ] && [ -f "$source/config.tar.zst" ]; then
  echo "Restoring .env and secrets/ from the backup"; zstd -dc "$source/config.tar.zst" | tar -xf -
fi

"${COMPOSE[@]}" up -d db
until "${COMPOSE[@]}" exec -T db pg_isready -U openlabs3d -d openlabs3d >/dev/null 2>&1; do sleep 2; done
tables=$("${COMPOSE[@]}" exec -T db psql -U openlabs3d -d openlabs3d -Atc "SELECT count(*) FROM pg_tables WHERE schemaname='public'")
if [ "$tables" != "0" ]; then
  echo "The database already has $tables tables. Restore only into an empty database; nothing was changed." >&2; exit 1
fi
prepare_secrets
echo "Restoring the database"
"${COMPOSE[@]}" exec -T db pg_restore -U openlabs3d -d openlabs3d --no-owner --exit-on-error < "$source/openlabs3d.dump"

echo "Restoring files"
"${COMPOSE[@]}" run --rm --no-deps -T --entrypoint sh backend -c \
  '[ -z "$(ls -A /app/data/uploads 2>/dev/null)" ] || { echo "Uploads volume is not empty; refusing." >&2; exit 1; }; tar -C /app/data -xf -' \
  < <(zstd -dc "$source/uploads.tar.zst")

echo "Starting the site"
"${COMPOSE[@]}" up -d
deploy/healthcheck.sh
echo "Restored the backup of revision $(cat "$source/revision" 2>/dev/null || echo unknown). The CAD worker re-registers files on start."
