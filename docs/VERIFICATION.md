# Verification record

Checked on 2026-10-29 using synthetic records only. The existing local demos and their browser data were not migrated or modified.

| Check | Result |
| --- | --- |
| Python 3.12 backend suite with real PostgreSQL 16.2 | **206 passed**, no skips |
| JavaScript frontend suite | **14 passed**, no failures |
| Fresh native install from the published source | Hashed requirements installed in a new Python 3.12 virtual environment; `pip check` passed; no editable application install required |
| Documented Docker quickstart from an empty environment | **Passed**: bootstrap, image build, PostgreSQL 17 initialization, Alembic migration job, app health, served frontend and API |
| Docker stop/start persistence | **Passed**: complete canonical workspace, revision, audit, allocation backing and request readiness unchanged after `docker compose down` and `docker compose up --build --wait`; credentials unchanged |
| Planner compatibility | 122 exact-output cases captured from the original demo's 108 request/allocation/supply assertions; inputs unchanged |
| Alembic | Fresh upgrade, downgrade/re-upgrade, expected readiness revision, and no schema drift |
| Concurrency | Repository and HTTP concurrent writes produce one successful save and one 409; winning data retained |
| Authentication and roles | Trusted-proxy token/identity, viewer/editor/admin, denied unassigned access, development badge |
| Audit protection | Actor supplied by server; legacy actor marked unknown; PostgreSQL row update/delete blocked |
| Restricted runtime role | Insert/update/delete planning flow, audit appends, readiness reads; nine prohibited privilege operations denied |
| Browser against fresh migrated PostgreSQL | Onboarding → request → inventory → explicit allocation → forecast → reload persistence; no browser errors |
| Additional browser workflows | Quantity edit, partial transfer, partial receipt, forecast tabs, all views, conflict draft/reload actions, viewer/editor controls |
| No implicit allocation | Confirmed a covered request remains allocated at zero until the user creates an allocation |
| Legacy converter | Reviewed CSV assignments, ownership-conflict handling, protected input/output, preserved historical snapshots in a sidecar |
| Dependency/source packaging | Pinned hashed requirements, uv lock, no live data/secrets, local setup refuses to overwrite credentials |

The backend suite reports one upstream Starlette/httpx TestClient deprecation warning. It does not fail tests or affect the deployed request handler; review it during the next dependency update.

The local quickstart was exercised from a clean copy whose checksums matched published commit `200339217f120929e0f07010ad7f8255647197a4`. Commands tested were `python3 scripts/bootstrap_dev.py`, `docker compose up --build --wait`, readiness at `http://localhost:8080/health/ready`, `docker compose down`, and another startup without regenerating credentials. A missing Docker installation was the host prerequisite issue; the README now explains installation/startup checks, getting into the repository directory, restart behavior, and focused troubleshooting. No application-code changes were required.

Docker ran in a temporary local Lima 2.2.1 Linux ARM64 VM on the Mac, with Docker Engine 29.9.2 and Compose 5.6.1. The application image used Python 3.12.16 and ran as UID 10001; PostgreSQL was 17.11 with UTF8 encoding. The web port was bound to `127.0.0.1:8080`. This verifies the container path locally; it does not mean Docker Desktop was installed or tested on the host. The test VM and synthetic database were stopped and removed afterward.

The container smoke also verified all frontend JavaScript/CSS assets, development identity, initial empty state, family inheritance, inventory coverage with zero implicit allocation, explicit allocation backing, and stale-write rejection. A separate clean native installation passed 206 tests against PostgreSQL 16.2 and 14 frontend tests, plus native startup/restart checks. Without a PostgreSQL test URL, the documented test command passed 202 tests with four PostgreSQL-only skips.

Both Compose files were parsed and reviewed. The included GitHub workflow tests against PostgreSQL 17 and builds/starts the full Compose stack on a GitHub runner; its hosted run status was not independently verified. The hosting team should review allowed action versions and network/package access on its internal runners; the supplied current action majors use Node 24 and require a compatible runner.

Cisco SSO, internal DNS/TLS, registry scanning, production PostgreSQL operation, secret-store integration, production-scale load, and a production backup restore require verification on the hosting platform. These are integration and rollout tasks, not preconfigured services in this source package.

Run the reproducible test commands in [README.md](../README.md). Browser smoke evidence used an isolated Chrome profile and a disposable database; profiles, screenshots and test database contents are intentionally excluded from the upload.
