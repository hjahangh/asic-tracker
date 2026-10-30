# Repository audit

The application now targets MongoDB 8.0 with PyMongo. This document separates the current storage conversion from the earlier PostgreSQL audit. Synthetic data only is used for verification; existing demos, workbook records and browser storage are not moved automatically.

## MongoDB conversion

- Live entities use separate MongoDB collections. ASIC variants/prices and project associations/transit settings are embedded in their owning records. Forecast lines remain separate; recovery copies and large audit details are checksummed chunks.
- Replica-set transactions use snapshot reads, majority writes and a conditional workspace revision. Planning changes and the authenticated audit append commit together.
- A versioned owner-run Python job creates schema version `20261030_0001`. The runtime account has narrowly scoped collection access and find/insert only on audit entries/chunks; it does not need owner privileges.
- The API's version-2 JSON contract, family inheritance, permissions, allocation/shipment rules, planner results and frontend flows are retained. Dates and accepted historical metadata preserve their JSON representation.
- PostgreSQL, SQLAlchemy, psycopg and Alembic are removed from the runtime/setup path. Configuration uses `MONGODB_URI`/`MONGODB_URI_FILE` and `MONGODB_DATABASE`. Existing SQL files and dumps are not loaded into MongoDB; authenticated workspace JSON export/import is the reviewed transition.
- Hosting/operations instructions now require a replica set, separate database identities and a consistent backup boundary with traffic stopped.

## Current MongoDB verification

| Check | Result |
| --- | --- |
| Native backend suite with real MongoDB 8.0.34 replica set | 325 passed, no skips |
| Frontend suite | 48 passed, also verified on Linux/Node 22 |
| Frozen planner fixtures | All 122 original synthetic fixtures passed |
| Generated planner checks | 3,000 conservation/purity scenarios and 1,600 exact JS/Python read-model comparisons passed |
| Dependency audit | 31 pinned Python runtime/test dependencies; zero known vulnerabilities reported at audit time |
| Development Compose | Fresh bootstrap, authenticated MongoDB/schema setup, nonroot app, all 11 scripts/3 stylesheets, synthetic import, inherited ownership, stock/allocation totals, audit attribution and stale-write 409 passed |
| Retained-volume restart | Exact canonical state, revision, audit and all four availability read models survived documented down/up |
| Linux ARM64 backend | 325 passed, no skips |
| Production Compose | UID 10001/read-only runtime with no owner secret; HTTP roles/security/planning, explicit allocation, stale writes and audit history passed |
| Database recovery | Traffic-stopped 13-collection archive restored into a second authenticated replica set/new DB; all counts and exact canonical revision 6, audit, forecasts, recovery, parts/prices/Unicode and availability matched |
| App recreation | No automatic planning writes after app recreation with `--no-deps` |

Actual container testing corrected three startup issues: a block-scoped mongosh helper lost access to its database binding and was changed to a lexical arrow function; a temporary shell home was provided on the read-only setup container; and keyfile initialization now replaces its own existing file before applying permissions, so down/up works after the file is owned by MongoDB. The keyfile keeps mode 0400 inside its dedicated volume without adding capabilities. Full-suite container stress also exposed the default MongoDB file-descriptor limit of 1,024; the database service now explicitly sets soft/hard `nofile` to 64,000, and the complete Linux suite subsequently passed.

MongoDB 8.0.34 passed on Ubuntu 24.04/kernel 6.8.0-142 and refused startup on the tested Ubuntu 26.04/kernel 7.0.0-34. This qualifies the tested image/kernel pair; it is not a blanket limit for later releases. See the [upstream issue](https://jira.mongodb.org/browse/SERVER-121912).

Restore verification also caught a successful tool exit with zero documents when the tools URI contained `/admin`; the corrected URI omits its database path and the instructions require explicit count/state comparison.

Current conversion evidence is recorded in [VERIFICATION.md](VERIFICATION.md). Historical counts below do not establish MongoDB correctness.

## Historical PostgreSQL audit

The previous audit used baseline commit `85d913aad2f4586573b3b31b7fe8c52c9edce914`. It corrected the following application behaviors before this storage conversion:

- Exact request IDs take precedence over legacy aliases. FIFO creation-time and ID ordering agree across browser/API, including timezone offsets and missing timestamps.
- Explicit surplus shipments can close eligible dedicated allocations without overstating requests or stealing credited units. Baselines protect new allocations from historical shipments.
- Shipment/request links, allocation schedules, archived master metadata, part compatibility fields, legacy transit defaults and unused transit settings survive unrelated edits.
- Reviewed family mapping CSV preserves literal/padded values and safely handles spreadsheet formula prefixes. Malformed data produces controlled errors.
- Malformed origins, nonfinite/huge prices, unsafe Unicode and invalid group claims are rejected. Startup checks frontend assets.
- Pacific dates, early years, bounded weekly reports, numeric tooltips, CSV exports and backup-reader limits have regression coverage.

Historical verification at that PostgreSQL revision:

| Area | Historical evidence — not a MongoDB result |
| --- | --- |
| Backend | 289 passed against PostgreSQL 17.11, no skips |
| Frontend | 48 Node 22 tests passed, including handlers and 13 page renderers |
| Frozen planner fixtures | All 122 original synthetic fixtures passed |
| Generated planners | 3,000 conservation/purity cases and 1,600 exact JS/Python read-model comparisons passed |
| Containers | Development startup/restart and production proxy-secret/role checks passed |
| Database restrictions | Eight PostgreSQL prohibited operations denied |
| Recovery | PostgreSQL dump/restore retained canonical state, forecasts, snapshots, prices, Unicode and audit |
| Dependency audit | No known vulnerabilities reported among 35 pinned dependencies at that time |

The old Alembic/SQL commands are no longer active setup instructions. Current MongoDB evidence is listed above; historical database/grant/restore results and the old dependency audit do not verify the new storage stack.

## Reproducible checks and rollout limits

Use the current test commands and disposable MongoDB replica-set configuration in [README.md](../README.md). `scripts/check_planners.py` checks conservation and browser/API parity with reported seeds; `--node /path/to/node` or `NODE_BINARY` selects Node.

The hosting team must verify Cisco SSO, ingress/TLS/DNS, its secret store, image scans, production restore procedure and expected load. Local Linux ARM64 evidence does not establish Linux x86-64 or hosted GitHub Actions results. The complete-workspace API is intended for a small team; larger history/concurrency needs paginated history, entity APIs and measured load tests.

The previous fresh visual pass was blocked first by the locked Mac and then by a browser permission denial. Automated renderer/handler and HTTP asset checks are useful, but do not replace a current layout/accessibility review. No additional browser attempt is implied by this conversion.

No finite audit guarantees an absence of defects. [VERIFICATION.md](VERIFICATION.md) lists what was actually checked and the remaining integration work.
