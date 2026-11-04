#!/usr/bin/env bash
# Consistent backup of production: PostgreSQL (pg_dump custom format, a transactionally consistent snapshot
# taken while the site runs), every uploaded and generated file, and the configuration needed to rebuild.
# Then, if RESTIC_REPOSITORY is set (deploy/backup.env), an encrypted, deduplicated copy off this server.
#
#   deploy/backup.sh                 # from the repository root on the server; run daily by the systemd timer
#
# Local copies: BACKUP_DIR (default /var/backups/openlabs3d), the newest KEEP_LOCAL (default 7) are kept.
# Off-server retention: restic forget --keep-daily 14 --keep-weekly 8 --keep-monthly 12.
# Restore: deploy/restore.sh. Verify a backup without touching production: deploy/verify-backup.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f deploy/backup.env ] && set -a && . deploy/backup.env && set +a
. deploy/lib.sh
BACKUP_DIR=${BACKUP_DIR:-/var/backups/openlabs3d}
KEEP_LOCAL=${KEEP_LOCAL:-7}
stamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$BACKUP_DIR/$stamp"
umask 077
mkdir -p "$target"

echo "[$stamp] database"
"${COMPOSE[@]}" exec -T db pg_dump -U openlabs3d -d openlabs3d --format=custom --compress=zstd:6 --no-owner > "$target/openlabs3d.dump"
# A dump that pg_restore cannot list is not a backup.
"${COMPOSE[@]}" exec -T db pg_restore --list < "$target/openlabs3d.dump" > /dev/null
"${COMPOSE[@]}" exec -T db psql -U openlabs3d -d openlabs3d -AtF, -c \
  "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname" > "$target/row-estimates.csv"

echo "[$stamp] files"
# Files are immutable once written (content-addressed CAD, preview directories, images), so a copy taken
# while the site runs is consistent; files newer than the dump are simply unreferenced in it.
"${COMPOSE[@]}" exec -T backend tar -C /app/data -cf - uploads | zstd -q -6 -T2 -o "$target/uploads.tar.zst"

echo "[$stamp] configuration"
tar -cf - .env secrets 2>/dev/null | zstd -q -o "$target/config.tar.zst" || true
git rev-parse HEAD > "$target/revision"
( cd "$target" && sha256sum openlabs3d.dump uploads.tar.zst config.tar.zst revision > SHA256SUMS )

if [ -n "${RESTIC_REPOSITORY:-}" ]; then
  echo "[$stamp] off-server copy to $RESTIC_REPOSITORY"
  restic snapshots --latest 1 >/dev/null 2>&1 || restic init
  restic backup --tag openlabs3d --host openlabs3d "$target"
  restic forget --tag openlabs3d --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune
  restic check --read-data-subset=5%
else
  echo "WARNING: RESTIC_REPOSITORY is not set: this backup exists only on this server." >&2
fi

ls -1d "$BACKUP_DIR"/*/ 2>/dev/null | sort | head -n -"$KEEP_LOCAL" | xargs -r rm -rf
du -sh "$target"
echo "[$stamp] done: $target"
