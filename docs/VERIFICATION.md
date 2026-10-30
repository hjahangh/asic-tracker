# Verification record

Checked on 2026-10-29 using synthetic records only. The existing local demos and their browser data were not migrated or modified.

| Check | Result |
| --- | --- |
| Python 3.12 backend suite with real PostgreSQL 16.2 | **206 passed**, no skips |
| JavaScript frontend suite | **14 passed**, no failures |
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

Both Compose files were parsed and reviewed. Docker is unavailable on the authoring machine, so an image build and Compose execution were **not run locally**. The included GitHub workflow tests against PostgreSQL 17 and builds/starts the full Compose stack on a GitHub runner. That workflow has not been executed in a repository yet. The hosting team should review allowed action versions and network/package access on its internal runners; the supplied current action majors use Node 24 and require a compatible runner.

Cisco SSO, internal DNS/TLS, registry scanning, production PostgreSQL 17 operation, secret-store integration, production-scale load, and a production backup restore require verification on the hosting platform. These are integration and rollout tasks, not preconfigured services in this source package.

Run the reproducible test commands in [README.md](../README.md). Browser smoke evidence used an isolated Chrome profile and a disposable database; profiles, screenshots and test database contents are intentionally excluded from the upload.
