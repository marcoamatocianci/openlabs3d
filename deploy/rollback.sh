#!/usr/bin/env bash
# Return to the release that ran before the last deploy/deploy.sh. Uses its images if they still exist.
#
# The database stays as it is: OpenLabs3D migrations are additive, so the previous release runs on the newer
# schema. If a release notes a migration that is not (docs/deployment/PRODUCTION.md, "Rolling back"), restore
# the backup deploy.sh took before it instead: deploy/restore.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
previous=$(cat deploy/.previous-release 2>/dev/null) || { echo "No previous release recorded." >&2; exit 1; }
. deploy/lib.sh
prepare_secrets
git checkout --quiet --detach "$previous"
OPENLABS3D_RELEASE=$(git rev-parse --short=12 HEAD)
export OPENLABS3D_RELEASE
if docker image inspect "openlabs3d-web:$OPENLABS3D_RELEASE" >/dev/null 2>&1; then
  "${COMPOSE[@]}" up -d --remove-orphans
else
  "${COMPOSE[@]}" up -d --build --remove-orphans
fi
deploy/healthcheck.sh && echo "$OPENLABS3D_RELEASE" > deploy/.current-release && echo "Rolled back to $OPENLABS3D_RELEASE"
