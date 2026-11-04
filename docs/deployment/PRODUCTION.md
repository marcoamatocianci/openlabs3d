# Production deployment

OpenLabs3D runs on one dedicated Linux machine (VPS or physical), independent of the development computer and of any
other website. Commands are in [deploy/README.md](../../deploy/README.md); this document explains the design.
Measurements behind the choices: [docs/architecture/PRODUCTION_REPORT.md](../architecture/PRODUCTION_REPORT.md).

## Architecture

```
            Internet
               │ 80, 443 (TCP), 443 (UDP, HTTP/3)
               ▼
   ┌──────── caddy ────────┐  network "edge"
   │ TLS, static frontend, │
   │ compression, headers  │
   └──────────┬────────────┘
              │ /api/*
              ▼
           backend  (FastAPI, one Uvicorn process; email sender thread)
              │                        ── edge: SMTP, Google sign-in
              │  network "internal" (no internet route)
      ┌───────┴────────┐
      ▼                ▼
     db             worker  (CAD analysis + Blender previews, one job at a time)
 (PostgreSQL 18)       │
      ▲                │
      └── job queue ───┘   (cad_jobs table, FOR UPDATE SKIP LOCKED)

 volumes: pg_data (database) · app_data (/app/data/uploads: CAD, previews, images) · caddy_data/config
```

Four containers, no Redis, no Celery, no PgBouncer:

- **Queue in PostgreSQL.** CAD jobs are rows in `cad_jobs`. The worker polls an indexed query every 2 s and claims a
  job with `FOR UPDATE SKIP LOCKED`. At this volume (a handful of uploads a day) a broker would add a service to
  run, secure and back up without improving anything measurable.
- **No PgBouncer.** The backend is one process with a pool of 8 (+8 overflow); the worker uses at most 3
  connections; `max_connections` is 60. An external pooler pays off with many processes or serverless clients.
- **One backend process.** Login rate limits are in memory and assume one process (see
  `docs/email/EMAIL_VERIFICATION.md`). A request is CPU-bound Python for about 5–25 ms; one process handles about 70
  page requests per second on two cores (measured). To scale out, move the rate limits into PostgreSQL first, then
  add `--workers`.

## Isolation and hardening

| Layer | Measure |
|---|---|
| Network | Only Caddy publishes ports. `db` and `worker` are on an `internal: true` network: no route to the internet (verified), so code running on an uploaded model cannot call out. |
| Containers | `no-new-privileges`, all Linux capabilities dropped (Caddy keeps `NET_BIND_SERVICE`), non-root user 10001, read-only root filesystem for the backend, memory/CPU limits on every service, rotated JSON logs. |
| Untrusted CAD | Parsed by `app/mesh.py` with size, member, ratio, triangle and nesting limits; XML declarations and entities refused; format decided by content. Blender only ever receives a numpy array of triangles, never the file, and runs niced with CPU-time limits inside the worker container (no network, no capabilities, 3 GB). Docker is one layer, not the only one. |
| Secrets | PostgreSQL password in `secrets/db_password`, mounted as a Docker secret: not in `.env`, the environment or `docker inspect`. `.env` (SMTP, OAuth) is `0600`. Neither is in Git. |
| HTTP | HTTPS only (HSTS), CSP, `X-Frame-Options DENY`, `nosniff`, Referrer and Permissions policies, Caddy admin API off, request bodies capped at 30 MB. Secure, HttpOnly session cookies and CSRF tokens (existing). API documentation is not served in production. Access logs omit query strings (OAuth codes). |
| Proxy | The backend trusts only `X-Real-IP`, which Caddy sets to the client address. The backend has no published port, so the header cannot be forged from outside. |
| Server | `deploy/server-setup.sh`: SSH by key only for one `deploy` user, no root login, ufw (22, 80, 443), fail2ban, automatic security updates (no automatic reboots), swap, journald limits. |
| Files | CAD originals are only served through authorization checks (owner/admin, or the host currently assigned to the job), are hashed on every manufacturing download and are never served statically. Previews of drafts are visible only to their owner and administrators. |

Docker's published ports bypass ufw. That is safe here because only Caddy publishes any; never add `ports:` to
`db`, `backend` or `worker`.

## Sizing

The limits in `compose.production.yaml` fit a 4-vCPU / 8-GB machine with headroom, and leave more room on 8 / 16:

| Service | Limit | Measured |
|---|---|---|
| db | 2 CPU, 2 GB (`shared_buffers` 512 MB) | 80 MB idle with the current data |
| backend | 2 CPU, 1 GB | 96 MB idle; ~80% of one core at 70 req/s |
| worker | 2 CPU, 3 GB | 95 MB idle; Blender peaks at 1.7–1.95 GB (84k–266k triangles, 1200 px) |
| caddy | 1 CPU, 256 MB | 14 MB |

A preview takes about 60 s of two cores and happens once per unique model, so a 4-vCPU VPS with shared cores is
enough. On shared ("burstable") vCPUs, keep `CAD_RENDER_THREADS=2`: renders take longer but the site stays
responsive. The 2 GB swap file absorbs a Blender peak rather than having the kernel kill a process.

Disk: the database is under 1 MB today. Uploads are about 63 MB (CAD 34 MB, previews 32 MB). Plan for CAD plus
about 1 MB of previews per unique model, plus 7 local backups.

## Monitoring

- `deploy/healthcheck.sh`: all containers healthy and the API answering through Caddy.
- Docker health checks: backend `/api/health`, database `pg_isready`, worker heartbeat (fails if the loop stalls
  for 15 minutes), Caddy → backend.
- PostgreSQL logs statements slower than 500 ms, lock waits and temporary files (`docker compose … logs db`).
- `python -m app.cad_worker --status` shows the queue; failed jobs keep their error in `cad_jobs.last_error`.
- An external uptime check on `https://<domain>/api/health` (any uptime service) catches a whole-machine outage,
  which nothing on the machine can report.

## Deploying and rolling back

`deploy/deploy.sh` refuses to run over local changes. It backs up, checks out the release, builds images tagged
with the commit (`openlabs3d-web:<sha>`, `openlabs3d-worker:<sha>`), starts them and waits for health.
`deploy/rollback.sh` starts the previous release's images again.

Rolling back keeps the database as it is. Migrations are additive (new tables, new nullable columns, widened
types), so the previous release runs on the newer schema. If a future migration is not additive, its release notes
must say so; roll back by restoring the backup `deploy.sh` took just before (`deploy/restore.sh` on a clean
volume).

The frontend files are bind-mounted from the checkout, so `git checkout` changes them immediately. Caddy then needs
`docker compose … restart caddy` for the single-file mounts (`deploy.sh` recreates the containers anyway).

## Backups and recovery

| What | How | Where |
|---|---|---|
| PostgreSQL | `pg_dump --format=custom` (a consistent snapshot of a running database), listed by `pg_restore` before it counts | `/var/backups/openlabs3d/<stamp>/` |
| Uploads (CAD, previews, images, attachments) | tar + zstd of `/app/data/uploads` (files are immutable once written) | same |
| Configuration | `.env` and `secrets/` | same, inside the encrypted off-server copy |
| Off-server | restic (encrypted, deduplicated): 14 daily, 8 weekly, 12 monthly; a 5% data check each run | any restic backend (S3-compatible, B2, SFTP) set in `deploy/backup.env` |

The timer runs `deploy/backup.sh` daily at 03:15 UTC. Once a month, `deploy/verify-backup.sh` restores the newest
backup into a throwaway PostgreSQL container with no network, counts every table and tests the archives.
`deploy/restore.sh` rebuilds a clean server from a backup and refuses to overwrite existing data. All three were
run end to end on a rehearsal stack (PRODUCTION_REPORT.md, "Backups").

A VPS snapshot is a convenience, not the backup: it lives with the same provider and account.

Logical daily dumps lose at most a day of data. When orders become valuable enough that a day matters, add WAL
archiving for point-in-time recovery (e.g. pgBackRest or WAL-G to the same object storage). The database volume and
`postgres -c archive_mode=on` are the only changes it needs.

## Development and production stay separate

- Development: `docker compose up -d --build` uses SQLite and Mailpit, port 8080 on your computer.
- Production: the server's checkout, `.env`, `secrets/` and volumes. No script copies a database or uploads in
  either direction. `restore.sh` and `migrate_to_postgres` refuse to write into non-empty targets.
- Workflow: develop and test locally → commit → push → `deploy/deploy.sh` on the server → `deploy/healthcheck.sh`,
  logs → `deploy/rollback.sh` if needed.
