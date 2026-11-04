#!/usr/bin/env bash
# Deploy a release on the production server, from the repository checkout there.
#
#   deploy/deploy.sh [GIT_REF]        # default: origin/main
#   deploy/rollback.sh                # back to the release that was running before
#
# Takes a backup first (SKIP_BACKUP=1 to skip), builds images tagged with the commit, starts them, waits for
# health. The database is never replaced: migrations only move it forward (alembic upgrade head at start).
set -euo pipefail
cd "$(dirname "$0")/.."
ref=${1:-origin/main}
. deploy/lib.sh
prepare_secrets
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "The server checkout has local changes; refusing to deploy over them." >&2; git status --short >&2; exit 1
fi
current=$(git rev-parse HEAD)
# A backup before every deploy, once there is something to back up (not on the first installation).
if [ "${SKIP_BACKUP:-0}" != 1 ] && "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx db; then
  deploy/backup.sh
fi
git fetch --tags --quiet origin
git checkout --quiet --detach "$ref"
release=$(git rev-parse --short=12 HEAD)
echo "$current" > deploy/.previous-release
export OPENLABS3D_RELEASE=$release
echo "Building $release"
"${COMPOSE[@]}" build --pull
"${COMPOSE[@]}" up -d --remove-orphans
if deploy/healthcheck.sh; then
  echo "$release" > deploy/.current-release
  echo "Deployed $release (previous: ${current:0:12}). Logs: ${COMPOSE[*]} logs -f --tail=100"
  docker image prune -f --filter "until=720h" >/dev/null
else
  echo "Release $release is not healthy. Inspect: ${COMPOSE[*]} logs --tail=200 backend worker" >&2
  echo "Roll back with: deploy/rollback.sh" >&2
  exit 1
fi
