# Repository audit

Reviewed the frontend, Python API/domain/planners, relational persistence, migrations, conversion tools, container configuration, CI and hosting documentation against baseline commit `85d913aad2f4586573b3b31b7fe8c52c9edce914`. Fixes include targeted regression tests. Verification used synthetic data only.

## Findings corrected

### Shipment and allocation accounting

- Exact request event IDs now take precedence over colliding legacy aliases. Shared historical aliases retain FIFO behavior. Browser and API use matching creation-time and ID ordering across timezone offsets and missing historical timestamps.
- An explicitly linked shipment larger than its request can close eligible dedicated allocation commitments without overstating request fulfillment or taking units credited to another request. Already shipped units remain the minimum allocation quantity.
- New allocations cannot exclude arbitrary future shipments from their shipment baseline. Available inventory still does not create allocations automatically.
- Editing shipment/request links retains the correct target. Editing allocation notes or quantity preserves the recorded arrival/transit values unless the dispatch date is explicitly changed.

### Data preservation and imports

- Unstructured legacy ASIC part metadata, part compatibility fields, archived master metadata, absent/zero legacy transit defaults and unused per-ASIC transit settings survive unrelated edits and database round trips.
- Request edits preserve missing historical timestamps instead of inventing new FIFO priority. Recovery restores correctly handle absent source metadata and optional pending-request collections.
- Reviewed project-family CSV mappings round-trip padded names and literal values. Spreadsheet formula prefixes are escaped reversibly. Malformed family data now produces an actionable conversion error.
- Audit reasons are stripped, validated and retained up to the documented 200-character limit.

### Validation and startup failures

- Malformed Origin URLs, oversized numeric prices, nonfinite JSON values, invalid group claims and unsafe Unicode return controlled validation/authentication errors instead of server exceptions.
- Indexed project keys and part MPNs are bounded by UTF-8 byte length before PostgreSQL writes. Invalid timezone offsets are rejected consistently.
- Configured frontend directories must contain the HTML and referenced local JavaScript/CSS assets at startup. An explicitly API-only application remains supported.

### Reports and date handling

- Pacific-date behavior is consistent for quarter selection, backup names and date-only recovery records. Valid four-digit years no longer encounter the date picker's former 2040 cutoff.
- Very long weekly reports retain the latest 5,300 weeks through the selected cutoff, include earlier demand/allocations in the opening balance and explain the window. CSV labels match that range.
- Backup file reading supports the documented 32 MiB client limit while explaining the server's separate request-body limit.

## Verification

| Area | Evidence |
| --- | --- |
| Backend | 289 tests passed with real PostgreSQL 17.11; no skips |
| Frontend | 48 Node 22 tests passed, including actual event handlers and all 13 page renderers |
| Compatibility | All 122 frozen legacy planner fixtures still pass |
| Generated scenarios | 3,000 conservation/purity cases plus 1,600 exact browser/Python read-model comparisons passed |
| Development container | Bootstrap/build/migration, served assets, onboarding, request coverage, explicit allocation, stale writes and restart persistence passed |
| Production template | Real HTTP role/token checks, mounted secrets, non-root runtime, separate migration/runtime database identities passed |
| Database restrictions | Eight prohibited operations denied, including audit tampering, persistent DDL and migration-table writes |
| Recovery | PostgreSQL dump/restore retained the exact canonical state, frozen forecasts, recovery snapshots, price history, Unicode and audit records |
| Dependencies | PyPA pip-audit reported no known vulnerabilities among 35 pinned runtime/test dependencies at audit time |

The initial Alembic migration and relational models are unchanged, so these fixes require no new schema migration. The application remains a shared workspace with optimistic revision checks, family-inherited ownership, explicit allocation and append-only server audit. [API.md](API.md) and [README.md](../README.md) describe its validation and size limits.

The deterministic planner checker is included in CI and can be run from the repository root after installing the test dependencies:

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
node --test frontend/tests/*.test.cjs
.venv/bin/python scripts/check_planners.py
```

Set `TEST_DATABASE_URL` to a disposable PostgreSQL database to include all database tests. The planner checker accepts `--node /path/to/node` or `NODE_BINARY` and reports seeds and failing inputs if a scenario fails. Its default seeds are `20261029` for conservation and `20261030` for parity.

## Remaining integration checks

- A fresh interactive browser layout/accessibility pass was initially blocked by the locked Mac. After unlock, the browser permission control denied access to the local test app. Automated source/handler rendering and live HTTP asset checks passed. Earlier browser workflow checks are recorded in [VERIFICATION.md](VERIFICATION.md).
- Local container checks ran on Linux ARM64. Hosted GitHub Actions status and Linux x86-64 behavior were not independently verified.
- The hosting team must connect and test Cisco SSO, internal ingress/TLS/DNS, the production secret store and database operations, image scanning and production backup/restore procedures. Local proxy authentication and PostgreSQL restore have been exercised.
- The shared-workspace API is intended for a small internal team. Entity-level endpoints, pagination and load testing should precede high concurrency or large history volumes. Current limits are explicit in the README.
- One upstream Starlette/httpx test-client deprecation warning remains; it is not a test failure. The dependency audit covers known Python vulnerabilities, not operating-system image vulnerabilities or future advisories.

No finite audit can guarantee the absence of defects. These results establish the checked behaviors and make the remaining deployment and visual checks explicit.
