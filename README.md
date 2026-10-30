# ASIC Tracker

Source package for an internal shared ASIC planning application: a JavaScript frontend, a Python FastAPI backend, and MongoDB 8.0. MongoDB must support multi-document transactions: use a replica set, or a compatible sharded cluster for hosting. The supplied development setup uses a replica set. The database starts empty. No workbook records, browser backups, credentials, or Cisco SSO configuration are included.

The frontend retains the demo's Cisco color scheme and views for Overview, ASICs/DD details, Project Families, Projects, Business Entities, Funding Sources, Requests, Allocations, Supply, Forecasts, Reports, and Recovery. MongoDB replaces browser-local storage. Every save is validated by the API and checked against a workspace revision to prevent one user's stale screen from overwriting another user's changes.

## Run locally

Get the code and enter the repository directory:

```sh
git clone https://github.com/hjahangh/asic-tracker.git
cd asic-tracker
```

Alternatively, open the repository on GitHub, choose **Code → Download ZIP**, extract it, and open a terminal in the extracted folder containing `compose.yaml`.

Install your organization's approved Docker Desktop on macOS or Windows, then start it and wait until the engine is running. On Linux, install and start Docker Engine with the Docker Compose plugin (v2 or newer). Python 3 is also required for the setup helper. Check these prerequisites from the repository directory:

```sh
python3 --version
docker info
docker compose version
```

On Windows PowerShell, use `py -3` instead of `python3`, and `curl.exe` instead of `curl` in the commands below.

For the first start, generate local credentials and the replica-set keyfile once, then build and start the services:

```sh
python3 scripts/bootstrap_dev.py
docker compose up --build --wait
```

The helper writes ignored `.env` and `secrets/mongodb-keyfile`. Compose initializes an authenticated single-member replica set (`tracker-rs`), creates separate owner/runtime users, runs the schema job and starts the app. The database is not published on a host port.

Check that the API is ready:

```sh
curl --fail http://localhost:8080/health/ready
```

It should return `{"status":"ready"}`. Open **http://localhost:8080** in your browser. The local setup uses an explicit development administrator identity; the app displays that identity. Onboarding order: Business Entity and Funding Source → Project Family → ASIC → Project → Request/Supply → Allocation.

To stop the services:

```sh
docker compose down
```

To start again, run `docker compose up --build --wait` from the same directory. Skip the bootstrap command when `.env` already exists; its refusal to overwrite that file is expected. Keep the existing credentials and keyfile with the existing database volume. Existing database-user passwords are not automatically rotated by rerunning setup.

Do not commit the generated `.env`, production secret files, database dumps, or exported workspaces; the ignore rules cover their designated directories.

The named MongoDB data volume and replica-set configuration survive `down`. Use `down -v` only when deliberately deleting this local development database. Production uses a separate configuration below.

If startup fails:

- **`docker: command not found` / missing `compose`:** install the approved Docker package and Compose plugin (v2 or newer), then reopen the terminal and repeat the prerequisite checks.
- **Cannot connect to the Docker daemon:** start Docker Desktop or the Linux Docker service and wait for `docker info` to succeed.
- **Port 8080 is already in use:** change `HTTP_PORT=8080` to `HTTP_PORT=8081` in `.env`, rerun the startup command, and use port 8081 in the browser and health-check URL.
- **MongoDB refuses the Docker host kernel:** the tested MongoDB 8.0.34 image rejected Ubuntu 26.04/kernel 7.0.0-34; Ubuntu 24.04/kernel 6.8.0-142 passed. Use an approved compatible host/VM kernel and review the [MongoDB advisory](https://jira.mongodb.org/browse/SERVER-121912). This is a finding for the tested image/kernel pair, not a restriction on every future MongoDB release.
- **Migration failure or app not healthy:** inspect `docker compose ps -a` and `docker compose logs keyfile-init setup-db migrate app db`. Fix the reported issue and rerun startup; do not delete the volume or regenerate credentials as a first troubleshooting step.

## Package layout

| Path | Purpose |
| --- | --- |
| `frontend/` | HTML, CSS, JavaScript, API client, frontend tests; no Node build required |
| `backend/app/` | FastAPI routes, authentication, validation, planner, MongoDB schema bootstrap and transactional PyMongo repository |
| `backend/app/migrate.py`, `backend/app/schema.py` | Versioned MongoDB collection validators and indexes; separate owner-run bootstrap |
| `backend/requirements*.txt`, `backend/uv.lock` | Pinned, hashed runtime/test dependencies and dependency lock |
| `Dockerfile` | One nonroot application image serving frontend and backend |
| `compose.yaml` | Local app, one-time migration job, persistent MongoDB 8.0 development replica set |
| `compose.production.yaml` | Standalone template for an internal image, external MongoDB replica set, trusted SSO gateway |
| `.github/workflows/ci.yml` | Backend/frontend tests, MongoDB schema/transaction checks, Docker Compose smoke |
| `scripts/` | Local setup, MongoDB role provisioning, reviewed legacy-family conversion |
| `docs/` | Hosting, operations, data model, API, verification record |

The local single-member replica set enables transactions for development; it does not provide production redundancy. Use an internally managed, authenticated and TLS-protected replica set for shared hosting.

## Hosting handoff

Start with [HOSTING.md](docs/HOSTING.md). The team must supply the internal repository/registry, database, TLS hostname, SSO gateway, approved role groups, secret injection, backups, and monitoring. The production API defaults to trusted-proxy authentication and refuses to start without its gateway secret. Cisco identity integration is an explicit hosting task.

The standalone production Compose template uses different migration-owner and runtime database credentials. It does not inherit the local development identity. Run migrations once per deployment before accepting traffic; replicas must not independently run migrations at startup.

## Importing an existing workspace

A workspace exported from the PostgreSQL-backed application remains a portable version-2 JSON backup. Export it through **Data & recovery → Export JSON** while the old application is available, then import it into this MongoDB version as an administrator. Database dumps and the old SQL schema cannot be loaded directly into MongoDB. Keep the original export and a separate database backup securely; no existing database is converted automatically.

If this checkout still has a PostgreSQL-era `.env`, keep it and any database backup securely outside the repository before generating new MongoDB development credentials. The helper refuses to overwrite it. The new MongoDB volume is independent of prior PostgreSQL volumes; do not delete the old data as a startup workaround.

Older demo exports with projects that do not yet have families need reviewed Project Family assignments. Export JSON from the old demo's Recovery page; keep the original export outside this repository.

```sh
python3 scripts/convert_legacy_backup.py /secure/old-backup.json --template --output /secure/family-map.csv
# Complete and approve each project's proposed family and existing business/funding IDs in the CSV.
python3 scripts/convert_legacy_backup.py /secure/old-backup.json --mapping /secure/family-map.csv --output /secure/converted.json
```

An administrator can import `converted.json` through Recovery. The converter preserves event IDs, shipment baselines, forecasts, and parts. It puts old recovery snapshots unchanged into `converted.legacy-recovery.json` and clears the live recovery list because deleted historical projects may lack a reviewed family assignment. Keep that sidecar, the original backup, and the approved family-map CSV securely; none belongs in GitHub. The CSV is the review/approval record and is not embedded in the imported workspace. Changes in ownership require resolution notes; every mapping requires an approver and approval date. No families are invented automatically.

## Development and tests

Python 3.12 and Node.js 22+ are used for tests. There are no frontend package-install or build steps. The following commands use macOS/Linux shell syntax. From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r backend/requirements-dev.txt
# Set TEST_MONGODB_URI securely to a disposable replica set for integration tests.
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
node --test frontend/tests/*.test.cjs
.venv/bin/python scripts/check_planners.py
```

The planner check runs 3,000 deterministic stock/shipment conservation scenarios and 400 browser/API comparisons across four read models. It requires Node 22 or newer on `PATH`; use `--node /path/to/node` or `NODE_BINARY` to select another installed executable.

Set `TEST_MONGODB_URI` to a **disposable, authenticated MongoDB 8.0 replica set**; never use a production URI. The test account must create/drop isolated databases, create collections/validators/indexes, and create/remove test users and roles for permission checks. Use a disposable database administrator credential, not the application's runtime account. Without the test URI, MongoDB integration tests skip; domain/planner tests can still run. There is no SQLite or in-memory substitute for transaction verification. CI supplies an authenticated replica set and runs schema/transaction checks plus both test suites.

For native development, first create the virtual environment above and provide `MONGODB_URI` or `MONGODB_URI_FILE` and `MONGODB_DATABASE` for a dedicated development replica set. Use an owner credential for the bootstrap command and a separately restricted runtime credential for the API. Provision the database users/roles as described in [HOSTING.md](docs/HOSTING.md). A standalone `mongod` does not support this application. From the repository root:

```sh
# Configure the owner MONGODB_URI(_FILE) for this command.
PYTHONPATH=backend .venv/bin/python -m app.migrate
# Switch MONGODB_URI(_FILE) to the restricted runtime credential before starting the API.
AUTH_MODE=development PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000`. These commands do not require activating the virtual environment. Normal production execution uses the container and proxy authentication.

Current conversion checks: 325 backend tests passed in each of the native and Linux ARM64 runs against a real MongoDB 8.0.34 replica set, 48 frontend tests passed (also on Linux/Node 22), and the planner checker passed 3,000 conservation scenarios plus 1,600 cross-engine read-model comparisons. Fresh Compose startup, retained-volume restart, production-template security/planning checks and a full restore into a separate authenticated MongoDB replica set passed. See [VERIFICATION.md](docs/VERIFICATION.md) for evidence and outstanding checks.

Update dependencies through `backend/pyproject.toml`, run `uv lock` in `backend/`, then regenerate both exports with `uv export --locked --no-dev --no-emit-project --format requirements-txt --output-file requirements.txt` and the same command with `--extra test --output-file requirements-dev.txt`. Review and commit the lock and exports together.

## Scope and operational limits

This release supports one shared planning workspace stored in per-entity MongoDB collections. Snapshot reads return a coherent revision and state; a transactional conditional revision update serializes writes. Concurrent writes with a stale revision return HTTP 409 and preserve the user's draft. It is suitable for a small internal team. Large workspaces or heavy concurrency call for entity-level APIs, paginated history, load testing, and measured database tuning before rollout. Retained audit/forecast history and up to 30 rotating recovery points grow the workspace payload; uploads default to 12 MiB. Audit/forecast history is never automatically truncated to fit that limit.

Submitted workspaces allow at most 10,000 records per core planning collection, 100,000 audit entries, 120 saved monthly forecasts, and 50,000 lines per forecast. Individual BSON entity/metadata documents must fit MongoDB’s 16 MiB limit; forecasts, recovery copies and large audit details use separate records/chunks. Backup files may be read up to 32 MiB, but the complete import request must still fit the server's configured body limit. Weekly reports show at most the latest 5,300 weeks, carry older demand/allocations into the opening balance, and display a notice when that window applies. Plan explicit archival or API changes before reaching these limits; do not erase audit records to work around them.

Viewers can inspect/export. Editors can update planning records. Administrators manage families, delete records, and import/restore/reset. A transfer that removes an entire allocation also requires an administrator. Group access is application-wide, without per-business-entity document security. Allocations may be unbacked commitments and do not create stock; coverage and shortfalls remain visible separately.

See [data model](docs/DATA_MODEL.md), [API](docs/API.md), [operations](docs/OPERATIONS.md), [verification](docs/VERIFICATION.md), and [repository audit](docs/AUDIT.md). No license is assigned to the internal application source by this package; confirm ownership and distribution policy with the hosting team.
