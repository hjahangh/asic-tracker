# ASIC Tracker

Source package for an internal shared ASIC planning application: a JavaScript frontend, a Python FastAPI backend, and PostgreSQL. The database starts empty. No workbook records, browser backups, credentials, or Cisco SSO configuration are included.

The frontend retains the demo's Cisco color scheme and views for Overview, ASICs/DD details, Project Families, Projects, Business Entities, Funding Sources, Requests, Allocations, Supply, Forecasts, Reports, and Recovery. PostgreSQL replaces browser-local storage. Every save is validated by the API and checked against a workspace revision to prevent one user's stale screen from overwriting another user's changes.

## Run locally

Requires Python 3 for the setup helper and Docker Engine/Desktop with Docker Compose v2.

```sh
python3 scripts/bootstrap_dev.py
docker compose up --build --wait
```

Open **http://localhost:8080**. The local setup uses an explicit development administrator identity; the app displays that identity. Onboarding order: Business Entity and Funding Source → Project Family → ASIC → Project → Request/Supply → Allocation.

```sh
docker compose logs -f app
docker compose down
```

The named PostgreSQL volume survives `down`. Use `down -v` only when deliberately deleting this local development database. Production uses a separate configuration below.

## What to upload to GitHub

Upload the **contents of this directory** into the repository root, including hidden `.github`, `.gitignore`, and `.dockerignore` files. The supplied ZIP contains this directory as its top-level folder; extract it before uploading. Git is preferable to browser upload so hidden files are included.

For a new repository, after the hosting team gives you its URL:

```sh
git init -b main
git add .
git commit -m "Add ASIC Tracker frontend, Python API, and PostgreSQL deployment"
git remote add origin <repository-url-from-hosting-team>
git push -u origin main
```

Do not commit the generated `.env`, production secret files, database dumps, or exported workspaces; the ignore rules cover their designated directories.

## Package layout

| Path | Purpose |
| --- | --- |
| `frontend/` | HTML, CSS, JavaScript, API client, frontend tests; no Node build required |
| `backend/app/` | FastAPI routes, authentication, validation, planner, ORM, transactional repository |
| `backend/migrations/` | Versioned Alembic PostgreSQL migrations |
| `backend/requirements*.txt`, `backend/uv.lock` | Pinned, hashed runtime/test dependencies and dependency lock |
| `Dockerfile` | One nonroot application image serving frontend and backend |
| `compose.yaml` | Local app, one-time migration job, persistent PostgreSQL 17 |
| `compose.production.yaml` | Standalone template for an internal image, external PostgreSQL, trusted SSO gateway |
| `.github/workflows/ci.yml` | Backend/frontend tests, PostgreSQL migration check, Docker Compose smoke |
| `scripts/` | Local setup, runtime grants, reviewed legacy-family conversion |
| `docs/` | Hosting, operations, data model, API, verification record |

## Hosting handoff

Start with [HOSTING.md](docs/HOSTING.md). The team must supply the internal repository/registry, database, TLS hostname, SSO gateway, approved role groups, secret injection, backups, and monitoring. The production API defaults to trusted-proxy authentication and refuses to start without its gateway secret. Cisco identity integration is an explicit hosting task.

The standalone production Compose template uses different migration-owner and runtime database credentials. It does not inherit the local development identity. Run migrations once per deployment before accepting traffic; replicas must not independently run migrations at startup.

## Importing an existing demo backup

Existing projects need reviewed Project Family assignments. Export JSON from the old demo's Recovery page; keep the original export outside this repository.

```sh
python3 scripts/convert_legacy_backup.py /secure/old-backup.json --template --output /secure/family-map.csv
# Complete and approve each project's proposed family and existing business/funding IDs in the CSV.
python3 scripts/convert_legacy_backup.py /secure/old-backup.json --mapping /secure/family-map.csv --output /secure/converted.json
```

An administrator can import `converted.json` through Recovery. The converter preserves event IDs, shipment baselines, forecasts, and parts. It puts old recovery snapshots unchanged into `converted.legacy-recovery.json` and clears the live recovery list because deleted historical projects may lack a reviewed family assignment. Keep that sidecar and original backup securely; neither is uploaded to GitHub. Changes in ownership require resolution notes; every mapping requires an approver and approval date. No families are invented automatically.

## Development and tests

Python 3.12 and Node.js 22+ are used for tests. There are no frontend package-install or build steps. From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r backend/requirements-dev.txt
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
node --test frontend/tests/*.test.cjs
```

For PostgreSQL tests, set `TEST_DATABASE_URL` to a **disposable test database**, using `postgresql+psycopg://...`. Tests create/drop isolated schemas and need permission to do so; never point them at the production database. Without it, repository tests use SQLite and PostgreSQL-only checks skip. CI supplies PostgreSQL 17 and runs migrations plus both test suites.

For native development, apply `alembic upgrade head` from `backend/` with `DATABASE_URL` set, then start `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` with `AUTH_MODE=development`. Install runtime requirements in the active environment first. Normal production execution uses the container and proxy authentication.

Update dependencies through `backend/pyproject.toml`, run `uv lock` in `backend/`, then regenerate both exports with `uv export --locked --no-dev --no-emit-project --format requirements-txt --output-file requirements.txt` and the same command with `--extra test --output-file requirements-dev.txt`. Review and commit the lock and exports together.

## Scope and operational limits

This release supports one shared planning workspace using a transactionally saved workspace document mapped into relational tables. Reads and writes briefly lock the revision row; concurrent stale writes return HTTP 409 and preserve the user's draft. It is suitable for a small internal team. Large workspaces or heavy concurrency call for entity-level APIs, paginated history, load testing, and measured database tuning before rollout. Retained audit/forecast history and up to 30 rotating recovery points grow the workspace payload; uploads default to 12 MiB. Audit/forecast history is never automatically truncated to fit that limit.

Viewers can inspect/export. Editors can update planning records. Administrators manage families, delete records, and import/restore/reset. A transfer that removes an entire allocation also requires an administrator. Group access is application-wide, without per-business-entity row security. Allocations may be unbacked commitments and do not create stock; coverage and shortfalls remain visible separately.

See [data model](docs/DATA_MODEL.md), [API](docs/API.md), [operations](docs/OPERATIONS.md), and [verification](docs/VERIFICATION.md). No license is assigned to the internal application source by this package; confirm ownership and distribution policy with the hosting team.
