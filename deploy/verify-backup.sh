#!/usr/bin/env bash
# Prove a backup restores, without touching production: restores the dump into a throwaway PostgreSQL
# container (no network, deleted afterwards), counts every table, checks the schema revision, and tests
# the file archives. Run it on any machine with Docker; the monthly timer runs it on the server.
#
#   deploy/verify-backup.sh /var/backups/openlabs3d/20261104T030000Z
set -euo pipefail
source=$(cd "${1:?Usage: deploy/verify-backup.sh BACKUP_DIRECTORY}" && pwd)
( cd "$source" && sha256sum --check --quiet SHA256SUMS )
name=ol3d-verify-$RANDOM
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$name" --network none -e POSTGRES_USER=openlabs3d -e POSTGRES_PASSWORD=verify \
  -e POSTGRES_DB=openlabs3d -v "$source:/backup:ro" postgres:18.6-alpine >/dev/null
until docker exec "$name" pg_isready -U openlabs3d -d openlabs3d >/dev/null 2>&1; do sleep 1; done
sleep 2
docker exec "$name" pg_restore -U openlabs3d -d openlabs3d --no-owner --exit-on-error /backup/openlabs3d.dump
echo "Schema revision: $(docker exec "$name" psql -U openlabs3d -d openlabs3d -Atc 'SELECT version_num FROM alembic_version')"
docker exec "$name" psql -U openlabs3d -d openlabs3d -Atc "
  SELECT format('%-24s %s', table_name, (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I', table_name), false, true, '')))[1]::text)
  FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
docker exec "$name" psql -U openlabs3d -d openlabs3d -Atc "SELECT 'users with password hashes: ' || count(*) FROM users WHERE password_hash LIKE '\$argon2%'"
files=$(zstd -dc "$source/uploads.tar.zst" | tar -tf - | grep -vc '/$')
echo "Files in uploads archive: $files"
cad=$(zstd -dc "$source/uploads.tar.zst" | tar -tf - | grep -c '^uploads/cad/[0-9a-f]\{48\}\.\(stl\|3mf\)$' || true)
echo "CAD files: $cad"
zstd -t -q "$source/config.tar.zst" 2>/dev/null && echo "Configuration archive: ok" || echo "Configuration archive: missing or unreadable"
echo "Backup verified: $source"
