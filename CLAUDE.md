# CLAUDE.md

Conventions for AI assistants (Claude Code, Codex) working in this repository.
If an `AGENTS.md` file exists at the repository root, read it too and follow it: both files describe the same conventions, and if they ever disagree, ask before proceeding.

## Project

OpenLabs3D: a marketplace that connects laboratories with 3D-printing hosts.

- Backend: FastAPI + SQLAlchemy 2 + Alembic on SQLite (`backend/app`, `backend/migrations`).
- Frontend: vanilla HTML/CSS/JS (`index.html`, `app.js`, `style.css`, `marketplace.js`, `operations.js`, `assets/*.js`), Three.js vendored in `assets/vendor/three/`.
- Served by Caddy via Docker Compose (`compose.yaml`, `compose.production.yaml`). README.md is mostly in Italian.

## Ground rules

1. **Branches.** Never commit or push directly to `v3`. Work on a branch named `claude/<short-topic>` and merge only through a pull request the maintainer approves.
   This checkout uses a fork: `origin` is `marcoamatocianci/openlabs3d` (read-only for this account; fetch and rebase from it) and `fork` is `nicola-barroero/openlabs3d` (push here). Push with `git push -u fork claude/<topic>` and open PRs with `gh pr create --repo marcoamatocianci/openlabs3d --base v3 --head nicola-barroero:claude/<topic>`.
2. **Stay current.** Before starting any task, `git fetch --all --prune` and rebase the working branch on the latest `origin/v3`.
3. **Migrations.** Ask the maintainer before creating any Alembic migration. A collaborator also creates migrations, and the chain must always have exactly one head (`alembic heads`).
4. **Shared hotspots.** `backend/app/main.py`, `backend/app/operations.py`, `app.js`, `style.css` and `index.html` are edited by several people. Keep changes there small and list them in the PR description.
5. **Pricing.** Server-side pricing (`backend/app/pricing.py`) is the source of truth. Never move price logic to the frontend; the frontend only displays server quotes.
6. **Tests.** Run the backend test suite before every commit.
7. **Never commit** databases (`*.db`, `data/`), Docker volumes, `.env` files or backups (`backups/`, `*.tar.gz`).

## Local setup and commands

```bash
# one-time setup
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest httpx

# migrations against a local SQLite database (run from backend/)
export DATABASE_URL="sqlite:///$PWD/data/openlabs3d.db" UPLOAD_DIR="$PWD/data/uploads"
mkdir -p data/uploads
.venv/bin/alembic heads          # must print exactly one head
.venv/bin/alembic upgrade head

# dev server (run from backend/; the frontend needs Caddy or another proxy forwarding /api/*)
.venv/bin/uvicorn app.main:app --reload

# tests (run from the repository root; they use their own temporary database)
PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests
```

Full stack with Docker: `cp .env.example .env && docker compose up -d --build`, then open http://localhost:8080.
