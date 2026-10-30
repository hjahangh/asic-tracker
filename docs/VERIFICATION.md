# Verification record

This record distinguishes MongoDB conversion checks from the historical PostgreSQL release. Tests use synthetic records and disposable infrastructure. Existing local demos, data files and browser profiles are not migrated or modified.

## MongoDB conversion

The current target is MongoDB 8.0 replica-set transactions, PyMongo and schema `20261030_0001`. The following conversion checks used synthetic data. Historical PostgreSQL results below are separate.

| Check | Current result |
| --- | --- |
| Native Python backend with real MongoDB 8.0.34 replica set | **325 passed**, no skips |
| Linux ARM64 container backend suite with real MongoDB replica set | **325 passed**, no skips |
| Frontend suite, including Linux/Node 22.23.4 | **48 passed** |
| Frozen planner fixtures | All 122 cases passed |
| Planner conservation and input purity | **3,000 deterministic scenarios passed** |
| JS/Python planner agreement | **1,600 exact comparisons passed**: 400 workspaces × four read models |
| Python dependency audit | **31 pinned dependencies**, zero known vulnerabilities reported at audit time |
| Development Compose quickstart | Fresh bootstrap, authenticated replica-set/users, schema job, readiness and UID 10001 app passed |
| Served assets | HTML, all 11 scripts and three stylesheets passed real HTTP retrieval |
| Planning/import smoke | Empty workspace, known synthetic version-2 import, stable IDs, family inheritance, request25/allocation15/inventory100, audit actor and stale revision 409 passed |
| Stop/start persistence | Complete canonical workspace/revision/audit and all four availability read models exactly matched after retained-volume down/up |
| Production Compose isolation | UID 10001, read-only runtime, separate owner/runtime credentials and no owner secret in the app passed |
| Production HTTP security/planning | Forged identity/token checks, roles, no implicit allocation, explicit allocation, stale 409 and retained audit history passed |
| MongoDB logical dump | All writers stopped; all 13 collections archived successfully |
| MongoDB isolated restore/equality | Restored into a second authenticated replica set/new database; setup roles, readiness, all 13 collection counts and exact canonical revision 6/state/audit/forecasts/recovery/parts/prices/Unicode/availability matched |
| App recreation | Recreating the app with `--no-deps` caused no automatic planning writes |
| CI startup commands | Exact authenticated Compose startup, inline environment generation, schema bootstrap/check, runtime writes, unauthenticated-read/audit-delete denials and nofile 64,000 passed in a separate disposable project |

The development container ran in an isolated Lima 2.2.1 Linux ARM64 VM with Ubuntu 24.04/kernel 6.8.0-142, Docker 29.9.2, Compose 5.6.1 and MongoDB 8.0.34. Startup testing found and corrected mongosh helper scoping, temporary shell storage and repeat keyfile initialization. The tested MongoDB binary refused Ubuntu 26.04/kernel 7.0.0-34 with a compatibility guard; the successful older-kernel test does not establish compatibility for every future image/kernel combination. See [HOSTING.md](HOSTING.md).

See [README.md](../README.md) for executable tests and [OPERATIONS.md](OPERATIONS.md) for the traffic-stopped backup/restore procedure. The restored deployment used a separate `restore-rs` replica set. An initial tools URI containing `/admin` filtered the archive to zero documents despite a successful exit; count assertions caught it. Removing the URI database path produced the verified full restore. The operations instructions require that URI form and count/canonical-state validation.

## Historical PostgreSQL release

The previous audit baseline was `85d913aad2f4586573b3b31b7fe8c52c9edce914`; its database checks apply to that earlier implementation only.

| Historical check | Result at that PostgreSQL revision |
| --- | --- |
| Python backend on PostgreSQL 17.11 | 289 passed, no skips |
| JavaScript frontend on Node 22/Linux | 48 passed |
| Planner conservation and input purity | 3,000 deterministic scenarios passed |
| JS/Python planner agreement | 1,600 exact comparisons: 400 workspaces × four read models |
| Frozen compatibility fixtures | All 122 cases passed |
| Handler/render coverage | 13 pages, six reports and forecast tabs/modes |
| Development Docker | Bootstrap, Alembic setup, readiness, frontend/API and restart persistence passed |
| Production template | File secrets, trusted proxy roles, owner/runtime separation and nonroot runtime passed |
| HTTP authorization/validation | Token/group/role checks, malformed inputs and conflict handling passed |
| PostgreSQL protections | Eight prohibited operations denied, including audit mutation and schema writes |
| PostgreSQL backup/restore | Exact workspace/revision/audit equality, forecasts, recovery, prices and Unicode retained |
| Prior Python dependency audit | 35 dependencies checked; no known vulnerabilities reported at that time |

That environment used a temporary Lima 2.2.1 Linux ARM64 VM, Docker Engine 29.9.2, Compose 5.6.1 and Python 3.12.16/UID 10001. The earlier clean-install check at `200339217f120929e0f07010ad7f8255647197a4` reported 206 backend/14 frontend tests. Neither historical count verifies MongoDB dependencies, privileges or recovery.

## External checks

The included workflow is configured for the current database and tests; its hosted GitHub Actions run status is not independently established by local commands. Internal runner compatibility and network/package access require hosting-team review.

Earlier browser checks covered onboarding, inventory, requests, explicit allocations, transfers/receipts, forecasts, conflicts and role controls. A fresh visual pass was blocked by local browser permissions. Current automated source/handler rendering does not replace layout/accessibility review.

Cisco SSO, internal DNS/TLS, production secret injection, registry/OS scans, Linux x86-64, production-scale load and restore on the actual hosting platform remain rollout checks. See [AUDIT.md](AUDIT.md) for scope and limitations. Disposable credentials, databases and local test logs are excluded from source.
