# PostgreSQL: schema, migration of existing data, local use

## How the schema is managed

- **SQLite** databases (development, tests, an existing deployment) replay every Alembic revision.
- **PostgreSQL** databases are created from the SQLAlchemy models at the current head and stamped with it, on the
  first `alembic upgrade head` against an empty database (`backend/migrations/env.py`). The 24 revisions up to `77a`
  were written for SQLite: some rebuild tables in ways that are fragile on PostgreSQL, and replaying them there would
  only recreate what the models already describe.
- That is sound only while the models equal the migrated schema. `backend/tests/test_schema_parity.py` checks it on
  both engines in every test run. On SQLite the only differences are unenforced `VARCHAR` lengths and unique
  constraints reflected as unique indexes.
- From `78a` on, every revision must run on both engines (see `78a_cad_assets.py` for the pattern).
- A PostgreSQL database that has tables but no `alembic_version` is refused rather than touched.

Types: money is integer cents (exact, unchanged). Timestamps are `timestamptz`, and sessions are pinned to UTC.
Usernames are `citext`: case-insensitive like SQLite's `NOCASE`, keeping the case they were typed in. Partial
unique indexes (one default address, one open equipment revision) exist on both engines.

## Concurrency guarantees

Every mutating request (POST, PUT, PATCH, DELETE) takes the database's writer lock before its first read and holds
it until commit or rollback (`app/database.py: write_lock`):

- SQLite: `BEGIN IMMEDIATE`, as before.
- PostgreSQL: `pg_advisory_xact_lock`, a transaction-scoped lock that orders mutating requests the same way while
  reads (GET) carry on against MVCC snapshots.

Checkout, job acceptance, equipment and stock changes, suspensions and approvals were written against "nothing
changes between my checks and my commit". They keep that guarantee without being rewritten. Inside it, the
existing defences still apply:

- Job acceptance is a conditional `UPDATE … WHERE status='available' AND host_id IS NULL …` (one winner).
- Orders are unique on `(buyer_id, idempotency_key)`, and a duplicate submission returns the first order.
- `uq_cad_job_stage` makes queueing a CAD stage idempotent.

`tests/test_concurrency.py` runs real threads on both engines:
- six hosts accept one job at the same instant → exactly one 200, five 409s, one `job.accepted` event;
- four simultaneous submissions of one checkout → one order and one job;
- a read during a held write returns immediately with the committed data.

Writes are short (milliseconds), so one ordered writer is not a bottleneck at this scale. If it ever is, the lock
can be narrowed per resource (for example per listing or per job) without touching the callers.

## Moving an existing SQLite deployment

On the production server, from the repository root, with `secrets/db_password` in place:

```sh
deploy/cutover-to-postgres.sh
```

1. Stops Caddy, the worker and the backend, so nothing can write.
2. Snapshots the SQLite file with SQLite's backup API, to `/app/data/backups/` in the volume and to
   `/var/backups/openlabs3d/` on the host.
3. Upgrades the SQLite schema to this release (`alembic upgrade head`, additive) and creates the PostgreSQL schema.
4. `python -m app.migrate_to_postgres`:
   - checks the snapshot (`integrity_check`, `foreign_key_check`) and that both databases are at the same revision;
   - refuses a non-empty target;
   - copies every table in foreign-key order with all primary keys and moves each id sequence past them;
   - recomputes row counts and a SHA-256 of every table's normalized contents from PostgreSQL;
   - commits only if all match. One transaction: a failure leaves PostgreSQL empty.
5. Starts everything on PostgreSQL and waits for health. The worker then registers the CAD files and adopts their
   existing previews, so nothing is rendered again.

Rehearsed on a copy of the development database (5 users, 19 orders, 26 jobs, 650 rows): 43 s end to end, all
checksums matched, Argon2 sign-ins worked afterwards (PRODUCTION_REPORT.md).

**The SQLite file is never modified or deleted.** To go back before new orders arrive, stop the stack, check out
the previous release and start it: it reads the same file. After new orders exist on PostgreSQL, going back would
lose them. Keep the snapshot until a PostgreSQL backup has been taken and verified
(`deploy/backup.sh && deploy/verify-backup.sh …`).

## Local PostgreSQL (optional)

Development uses SQLite by default. To try PostgreSQL locally:

```sh
docker compose --profile postgres up -d db
DATABASE_URL=postgresql+psycopg://openlabs3d:development-only@db:5432/openlabs3d \
  docker compose --profile postgres up -d --build backend worker
```

Running the test suite against PostgreSQL (any reachable server where the user may create databases):

```sh
docker run -d --name ol3d-pgtest -e POSTGRES_USER=ol3d -e POSTGRES_PASSWORD=test -e POSTGRES_DB=ol3d_test \
  -p 127.0.0.1:55432:5432 postgres:18.6-alpine
cd backend && OPENLABS3D_TEST_POSTGRES_URL=postgresql+psycopg://ol3d:test@127.0.0.1:55432/ol3d_test \
  uv run --no-project --python 3.12 --with-requirements requirements.txt --with httpx --with pytest python -m pytest -q tests/
```
