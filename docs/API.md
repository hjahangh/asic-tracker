# API contract

The Python service serves the frontend and API on the same origin. One PostgreSQL workspace is shared by all authorized users. All business writes replace a validated workspace in one transaction; a revision prevents overwriting another user's changes. The API starts empty and creates no demonstration records.

## Endpoints

| Method and path | Access | Response |
| --- | --- | --- |
| `GET /health/live` | Public | `{"status":"up"}` |
| `GET /health/ready` | Public | `{"status":"ready"}` only when PostgreSQL and the expected Alembic migration are available; otherwise 503 |
| `GET /api/me` | Assigned role | Authenticated identity and role |
| `GET /api/workspace` | Viewer, editor, admin | `{revision,state}` plus a quoted revision `ETag` |
| `PUT /api/workspace` | Editor or admin, subject to rules below | Committed `{revision,state}` and new `ETag` |
| `GET /api/availability?as_of=2026-10-29` | Viewer, editor, admin | Server-calculated readiness, allocations, inventory lots and totals |
| `GET /api/openapi.json` | Assigned role; optional | OpenAPI specification when `ENABLE_API_DOCS=true` |
| `GET /api/docs` | Assigned role; optional | Local API reference when `ENABLE_API_DOCS=true`; no external assets |

Liveness and readiness also have `/api/health/live` and `/api/health/ready` aliases. Readiness requires migration `20261029_0001`. Health responses disclose no connection details or credentials.

## Workspace reads and writes

An empty workspace response is:

```json
{
  "revision": 0,
  "state": {
    "version": 2,
    "asics": [],
    "projects": [],
    "projectFamilies": [],
    "businessEntities": [],
    "fundingSources": [],
    "events": [],
    "forecastVersions": [],
    "snapshots": [],
    "audit": [],
    "pendingRequests": []
  }
}
```

To write, read the current envelope, edit its state, and submit the entire state with its original revision:

```json
{
  "revision": 12,
  "state": {"version": 2},
  "reason": "Change requested ASIC quantity",
  "operation": "edit"
}
```

The abbreviated `state` above illustrates the envelope only. Actual writes must include the complete required collections from the GET response. A successful write increments the revision and returns the canonical stored state, including inherited ownership, server-established shipment baselines and server audit entries. The client must replace its local state with that response. The supplied revision, rather than `If-Match`, controls concurrency.

`operation` is `edit` by default. Explicit `import`, `restore` and `reset` operations require an administrator. `reason` is a nonempty string of at most 200 characters. A missing, invalid or stale submission saves no partial changes. Default body limit is 12 MiB, enforced before parsing both fixed-length and chunked requests.

Reads and writes hold the workspace revision row lock while serializing the relational records. The returned state and revision describe one coherent committed workspace.

## Availability

`as_of` is an optional valid `YYYY-MM-DD`; it defaults to today's date in `America/Los_Angeles`. The response shape is:

```json
{
  "revision": 12,
  "asOf": "2026-10-29",
  "requests": [],
  "allocations": [],
  "supply": [],
  "inventory": []
}
```

Arrays use the frontend's existing camelCase fields. Request rows include `eventId`, `requestId`, `asicId`, `projectId`, `qty`, `shipBy`, `arrivalDate`, `shippedQty`, `remainingQty`, `allocatedQty`, `allocatedAvailableByShipBy`, `availableByShipBy`, `shortfallQty`, `expectedAvailableDate` and `status` (`shipped`, `on-time`, `late`, `shortfall`). Allocation rows include quantities shipped, remaining, backed by supply and unbacked. Supply rows identify available/incoming lots and their consumed, on-hand, reserved and free quantities. Inventory totals group those quantities by ASIC, with incoming, overdue and stock-gap quantities.

Free inventory forecast to cover a request does not create an allocation. Actual shipments consume stock once. Recorded overdue incoming supply remains visible but is excluded from expected coverage until its date/status is corrected or receipt is recorded. Previously completed shipments cannot be credited to a new normal allocation. Existing allocation assignments cannot be changed in place: reallocation reduces the source and creates a new target allocation with a fresh baseline, retaining any shipped quantity on the source.

The frontend uses server calculations only when both the response revision and as-of date match its loaded workspace. Browser calculations support unsaved previews. The Python planner is independently tested against 122 synthetic cases captured from the demo's JavaScript regression suites.

Within an ASIC/project, an exact request event ID takes precedence over a colliding legacy request alias. Shared legacy aliases retain FIFO behavior. Equal-deadline requests use actual creation-time order across timezone offsets, with missing/date-only history preserved, then a deterministic ID tie break shared by the browser and API. If an explicitly linked shipment exceeds its request quantity, excess units can close eligible dedicated allocation commitments without overstating request fulfillment or consuming another request's credited units.

## Data rules

- Each project belongs to one project family. Each family has exactly one business entity and one funding source. Project ownership IDs and display labels are derived from its family on every write. Legacy projects require an explicit mapping; imports never guess families.
- IDs remain stable. Part IDs are globally unique, project parent relationships cannot cycle, and referenced live records must exist. Quantities are positive safe whole numbers; totals cannot exceed JavaScript's safe integer range. Dates, transit days and calculated ship dates are bounded.
- USD prices fit PostgreSQL `NUMERIC(12,2)`: finite nonnegative values with at most two decimal places. The server rejects values requiring database rounding.
- Indexed project keys and lowercase part MPNs are limited to 2,000 UTF-8 bytes to fit PostgreSQL indexes; master names remain limited to 500 characters. Descriptions are not subjected to these index limits. Text must be valid Unicode without NUL or unpaired surrogate characters.
- Existing planning event types and allocation creation/baseline fields are immutable during normal edits. Allocation quantity cannot fall below already shipped units.
- Saved forecast versions and recovery points are immutable during normal edits. New forecast lines must capture the current server-validated plan; new recovery data must capture the prior server workspace. Frozen forecast labels/IDs remain valid after live masters are deleted. Explicit administrator import/restore preserves reviewed historical records.
- Normal writes ignore client audit additions, deletions and actor fields. The server appends a record with the authenticated actor, revision and before/after changes. Imported legacy entries are marked as legacy with an unknown original actor. PostgreSQL rejects audit updates/deletions.

## Identity and authorization

Production defaults to `AUTH_MODE=proxy` and fails startup without a configured shared gateway secret of at least 32 characters. The hosting team's authenticated ingress must strip these headers from incoming browser requests and inject verified values on its private connection to the backend:

| Header | Meaning |
| --- | --- |
| `X-Proxy-Token` | Gateway shared secret; never expose it to browser JavaScript |
| `X-Authenticated-User` | Stable authenticated subject, required |
| `X-Authenticated-Name` | Optional display name |
| `X-Authenticated-Groups` | JSON array or comma-separated verified group names |

The backend compares the gateway token in constant time. A caller with identity headers but no valid token receives 401. A valid authenticated subject with no mapped role receives 403. `ROLE_GROUPS` maps explicit group names to `viewer`, `editor` and `admin`; the highest matching role applies. Default groups are `asic-tracker-viewers`, `asic-tracker-editors` and `asic-tracker-admins`.

| Role | Permitted actions |
| --- | --- |
| Viewer | Read workspace, availability and own identity; export through frontend |
| Editor | Create/edit planning records, ASICs, regular projects and business/funding masters; capture forecasts and recovery points |
| Admin | Editor actions plus project-family changes, record deletion, import, restore and reset |

Deletion is detected by comparing IDs, so labeling a deletion as an ordinary edit cannot bypass authorization. Automatic rotation of the bounded 30 recovery points accompanies normal edits. All family changes require admin because projects inherit ownership. Explicit imports/restores/resets also require admin even if the resulting data would otherwise look like an ordinary edit.

`GET /api/me` returns `subject`, `display_name`, `role` and `auth_mode`. `AUTH_MODE=development` is an explicit local-only mode using `DEV_USER` and `DEV_ROLE`; it is visibly indicated in the frontend. It does not authenticate a person. This package provides a trusted gateway integration contract; the hosting team must connect its approved Cisco identity provider and keep the backend unreachable from untrusted clients. There are no application password, cookie-login or logout endpoints.

The frontend and API use the same origin; no wildcard CORS is enabled. Write requests with a different Origin host are rejected. Explicit allowed hosts, no-store responses, a self-only script policy, framing restrictions and bounded uploads are enforced. See [HOSTING.md](HOSTING.md) for ingress and deployment requirements.

## Errors

Application errors use a structured `detail` object:

```json
{
  "detail": {
    "code": "revision_conflict",
    "message": "Another user updated the workspace. Load the latest data and retry your change.",
    "current_revision": 13
  }
}
```

| Status | Common code/meaning | Client action |
| --- | --- | --- |
| 401 | `authentication_required`, `invalid_identity` | Enter through the approved authenticated gateway |
| 403 | `read_only`, `admin_required`, `access_not_assigned`, `cross_origin_write` | Check assigned role or ingress configuration |
| 409 | `revision_conflict` | Reload current state and review/reapply the change; do not silently overwrite |
| 413 | `payload_too_large` | Reduce/archive the upload or review the configured limit |
| 422 | `invalid_workspace` with optional `errors` array; `invalid_date`; `integrity_conflict` | Correct data; no partial update was saved |
| 503 | `database_unavailable`, `database_unconfigured` | Hosting team checks DB connectivity/configuration |

Framework envelope-validation errors use FastAPI's standard `detail` array, including the invalid field location. Database errors never return raw SQL, connection credentials or stack traces. Unknown API paths return 404.
