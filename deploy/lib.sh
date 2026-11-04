# shellcheck shell=bash
# Shared by the deploy scripts. The production stack is compose.yaml + compose.production.yaml, configured by
# .env in the repository root. OPENLABS3D_COMPOSE_OVERRIDE adds one more file (rehearsals on another machine,
# e.g. different ports); COMPOSE_PROJECT_NAME and COMPOSE_ENV_FILES are honoured by Docker Compose itself.
COMPOSE=(docker compose -f compose.yaml -f compose.production.yaml)
if [ -n "${OPENLABS3D_COMPOSE_OVERRIDE:-}" ]; then COMPOSE+=(-f "$OPENLABS3D_COMPOSE_OVERRIDE"); fi

# Docker Compose bind-mounts file secrets with their host permissions, and the application runs as uid 10001
# inside its containers: the directory keeps other server users out (0700), the file is readable inside (0644).
prepare_secrets() {
  [ -s secrets/db_password ] || { echo "Missing secrets/db_password (deploy/README.md, 'First installation')." >&2; return 1; }
  chmod 700 secrets && chmod 644 secrets/db_password
}
