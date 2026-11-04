# Production commands

Everything here runs **on the production server**, as the `deploy` user, from `/srv/openlabs3d` (a clone of this
repository). Your own computer stays the development environment: nothing here copies a development database or
development uploads to the server, and nothing in development touches production.

Background and reasoning: [docs/deployment/PRODUCTION.md](../docs/deployment/PRODUCTION.md).

## First installation

```sh
# 1. As root, on a fresh Ubuntu Server LTS machine (firewall, SSH keys only, Docker, updates, swap, timers):
DEPLOY_SSH_KEY="ssh-ed25519 AAAA… you@laptop" bash server-setup.sh     # copy deploy/server-setup.sh there first

# 2. As deploy:
git clone <repository-url> /srv/openlabs3d && cd /srv/openlabs3d
cp .env.example .env && chmod 600 .env          # set APP_ENV=production, SITE_DOMAIN, APP_PUBLIC_URL, SMTP_*
mkdir -m 700 secrets && openssl rand -base64 32 | tr -d '\n' > secrets/db_password && chmod 644 secrets/db_password
cp deploy/backup.env.example deploy/backup.env && chmod 600 deploy/backup.env   # off-server backup target

# 3. As root again, so the backup timers get installed from the clone:
bash /srv/openlabs3d/deploy/server-setup.sh

# 4. Point DNS at the server (A/AAAA records), then start:
deploy/deploy.sh HEAD          # builds, starts, waits for health; Caddy obtains the certificate
```

`secrets/` is `0700` (only `deploy` can enter it) and the file inside is `0644` so that the application's
unprivileged container user can read it. Keep a copy of the password, `.env` and `deploy/backup.env` in your password
manager: they are what a rebuild needs besides the backup itself.

## Moving an existing SQLite site to PostgreSQL (once)

```sh
deploy/cutover-to-postgres.sh       # asks for confirmation; stops the site, copies, verifies, restarts
deploy/backup.sh                    # first PostgreSQL backup
```

Details, timing and how to go back: [docs/deployment/POSTGRESQL_MIGRATION.md](../docs/deployment/POSTGRESQL_MIGRATION.md).

## Everyday

| Task | Command |
|---|---|
| Deploy `origin/main` (backup first) | `deploy/deploy.sh` |
| Deploy a tag or commit | `deploy/deploy.sh v7.0.0` |
| Roll back to the previous release | `deploy/rollback.sh` |
| Status and health | `deploy/healthcheck.sh` |
| Logs (all, or one service) | `docker compose -f compose.yaml -f compose.production.yaml logs -f --tail=200 [backend\|worker\|db\|caddy]` |
| Restart one service | `docker compose -f compose.yaml -f compose.production.yaml restart backend` |
| CAD queue | `docker compose -f compose.yaml -f compose.production.yaml exec worker python -m app.cad_worker --status` |
| Storage report | `docker compose -f compose.yaml -f compose.production.yaml exec worker python -m app.cad_worker --storage-report` |
| Re-render after a studio look change | `… exec worker python -m app.cad_worker --rerender` |
| Database shell | `docker compose -f compose.yaml -f compose.production.yaml exec db psql -U openlabs3d` |
| Backup now | `deploy/backup.sh` |
| Prove a backup restores (throwaway database) | `deploy/verify-backup.sh /var/backups/openlabs3d/<stamp>` |
| Restore onto a clean server | `deploy/restore.sh /var/backups/openlabs3d/<stamp>` |

Tip: `alias dc='docker compose -f compose.yaml -f compose.production.yaml'`.

## What never happens automatically

- No script copies a database or uploads between development and production.
- `restore.sh` refuses a database or upload volume that already holds data.
- `migrate_to_postgres` refuses a PostgreSQL database that already holds rows, and commits only after row counts
  and checksums of every table match.
- Original CAD files are never deleted by any script; the storage report lists unreferenced ones for you to decide.
- DNS is never changed by these scripts.
