#!/usr/bin/env bash
# Wait until every production service reports healthy and the API answers through Caddy (max ~3 minutes).
set -euo pipefail
cd "$(dirname "$0")/.."
. deploy/lib.sh
for _ in $(seq 1 36); do
  unhealthy=$("${COMPOSE[@]}" ps --format '{{.Service}} {{.Health}}' | awk '$2 != "healthy" {print $1}')
  if [ -z "$unhealthy" ] && "${COMPOSE[@]}" exec -T caddy wget -q -O /dev/null http://backend:8000/api/health; then
    "${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}'; exit 0
  fi
  sleep 5
done
echo "Not healthy: ${unhealthy:-api}" >&2
"${COMPOSE[@]}" ps >&2
exit 1
