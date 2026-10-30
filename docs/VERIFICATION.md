# Verification record

The final repository audit used synthetic records and disposable databases. Its baseline was commit `85d913aad2f4586573b3b31b7fe8c52c9edce914`. Existing local demos and their browser data were not migrated or modified. See [AUDIT.md](AUDIT.md) for findings, fixes and remaining integration checks.

| Check | Result |
| --- | --- |
| Python backend suite in the application container, with real PostgreSQL 17.11 | **289 passed**, no skips |
| JavaScript frontend suite on Node 22 in Linux | **48 passed**, no failures or skips |
| Planner conservation and input purity | **3,000 deterministic scenarios passed** |
| Browser/Python planner agreement | **1,600 exact comparisons passed**: 400 workspaces across four read models |
| Frozen planner compatibility fixtures | All 122 original synthetic cases passed; fixture inputs unchanged |
| Frontend handler/render coverage | All 13 pages, six report types, forecast summary/program/chart, monthly and cumulative modes; actual handlers tested with a minimal DOM adapter |
| Development Docker quickstart | Build, empty PostgreSQL initialization, Alembic migration job, readiness, frontend and API passed |
| Stop/start persistence | Canonical workspace, revision, audit and allocation/readiness state remained identical after restart |
| Production Compose template | Mounted file secrets, trusted-proxy authentication, separate owner/runtime DB roles, non-root application and disabled API documentation passed |
| HTTP authorization | Missing/wrong gateway token denied; unassigned groups denied; viewer/editor/admin restrictions enforced |
| Invalid inputs | Malformed Origin, nonfinite/huge prices, invalid Unicode, oversized indexed fields and malformed group claims rejected without partial saves or server errors |
| Concurrency | Repository and HTTP stale/concurrent writes preserve the winner and return 409 to the stale writer |
| Audit protection | Server actor/reason retained; submitted audit deletion ignored; PostgreSQL audit update/delete/truncate denied |
| Restricted runtime privileges | Normal application flow passed; eight prohibited database operations denied |
| PostgreSQL backup and restore | Actual dump restored into a separate database, runtime grants reapplied, exact workspace/revision/audit equality verified, including nonempty forecasts, recovery snapshots, price history and Unicode |
| Python dependency audit | 35 pinned runtime/test dependencies checked; zero known vulnerabilities reported at audit time |
| Initial migration | Unchanged; upgrade, downgrade/re-upgrade and schema-drift checks passed |

The backend suite reports one upstream Starlette/httpx TestClient deprecation warning. It does not fail tests or affect the deployed request handler; review it during the next dependency update.

Docker ran in a temporary local Lima 2.2.1 Linux ARM64 VM on the Mac, with Docker Engine 29.9.2 and Compose 5.6.1. The application image used Python 3.12.16 and UID 10001; PostgreSQL used UTF8 encoding. Development and production-template HTTP checks used loopback ports and isolated synthetic data. This verifies the container path locally; Docker Desktop and Linux x86-64 were not tested in this audit.

The earlier clean-install check at commit `200339217f120929e0f07010ad7f8255647197a4` verified the documented bootstrap and Docker startup/restart commands, plus hashed dependencies in a fresh Python 3.12 virtual environment. Runtime dependencies and the initial migration remain unchanged. Its historical test counts were 206 backend and 14 frontend; the current counts are those in the table above.

Earlier browser checks covered onboarding, requests, inventory, explicit allocation, transfers/receipts, forecast tabs, conflict handling and role controls. A fresh interactive visual pass for this audit could not run: the Mac was initially locked, and after it was unlocked the browser permission control denied access to the local test app. Current frontend rendering and event handlers were tested automatically, and real HTTP checks retrieved the HTML plus every referenced JavaScript/CSS asset. These checks do not replace a current browser layout/accessibility review.

The included GitHub workflow runs the backend, frontend and planner checks against PostgreSQL 17 and builds/starts the Compose stack. Its hosted run status was not independently verified. The hosting team should review allowed action versions and network/package access on internal runners; the supplied action majors use Node 24 and require a compatible runner.

Cisco SSO, internal DNS/TLS, registry/OS-image scanning, the hosting platform's secret store, production-scale load and restore procedures on the actual production platform remain rollout checks. The local PostgreSQL restore and proxy-header contract were tested; these external services are not provisioned by this package.

Run the reproducible test commands in [README.md](../README.md). Test credentials, databases, browser profiles and audit logs from the disposable environment are excluded from the source package.
