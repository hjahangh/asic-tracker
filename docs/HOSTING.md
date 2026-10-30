# Hosting handoff

## Deployment architecture

```mermaid
flowchart LR
    U[User browser] -->|HTTPS| G[Internal TLS and SSO gateway]
    G -->|Private upstream and verified identity headers| A[Application container]
    subgraph A[Application container: nonroot Python process]
      F[Static JavaScript frontend]
      P[FastAPI Python API]
    end
    P -->|SQLAlchemy and psycopg; TLS in production| D[(PostgreSQL)]
    M[One-time Alembic migration job] -->|Schema owner credential| D
    S[Platform secret store] -.-> G
    S -.-> P
    S -.-> M
    D --> B[Scheduled encrypted backups and restore verification]
```

The same application image serves the frontend and API on port 8000. PostgreSQL is a separate service or managed database. The frontend calls same-origin `/api` endpoints and never connects directly to PostgreSQL. The backend contains validation, role enforcement, allocation/readiness calculations, revision checks, and audit attribution. There is no CDN dependency or frontend build service.

## Inputs needed from the hosting team

| Input | Used for |
| --- | --- |
| Internal GitHub repository and approved container registry | Source review and approved image publication |
| Docker/Compose or orchestration platform and runner versions | Build, migration job, application rollout |
| Internal DNS hostname and TLS ingress | Browser access and `TRUSTED_HOSTS` |
| SSO gateway with authenticated subject/group claims | Identity headers and role mapping |
| PostgreSQL endpoint, database, CA and two database roles | Runtime access versus schema migrations |
| Platform secret store | DB URLs and gateway shared token |
| Backup/restore owners, retention, RPO/RTO | Recovery beyond in-app snapshots |
| Monitoring/logging destination and service owners | Health checks, incident handling and support |

Use organization-approved base images or mirrors if public image registries are unavailable. Pin the approved application image by digest in the platform's release configuration. The supplied Dockerfile uses `python:3.12-slim`; local development uses `postgres:17`. Major tags receive updates, so the hosting pipeline should build, scan, and promote a specific tested digest.

## Identity and access

Production uses `AUTH_MODE=proxy`. The gateway must authenticate the person, strip all browser-supplied `X-Authenticated-*` and `X-Proxy-Token` headers, and inject:

| Header | Required value |
| --- | --- |
| `X-Authenticated-User` | Stable authenticated subject, at most 200 characters |
| `X-Authenticated-Name` | Optional display name |
| `X-Authenticated-Groups` | JSON string array of verified groups, or comma-separated group names |
| `X-Proxy-Token` | Shared gateway secret, at least 32 characters |

The app compares the token and assigns the highest matching role from `ROLE_GROUPS` (`admin`, `editor`, `viewer`). Unrecognized groups receive 403. The shared token authenticates the gateway; it is not an end-user API key and must never reach browser JavaScript. It does not replace SSO authentication. Keep the backend private and restrict access to the gateway. The sample loopback mapping assumes the gateway runs on the host; containerized ingress may instead attach to a private network and omit host publication.

Forward the public `Host` and browser `Origin` unchanged through ingress. State-changing requests reject mismatched origins. Health endpoints need no identity. Static assets contain no workspace records, but the gateway should protect the whole site consistently. API calls and exports require identity. No application login/password database is included.

`AUTH_MODE=development` trusts `DEV_USER` and `DEV_ROLE` without login. It is intended only for the supplied loopback local setup, and must not be used in a shared deployment. The frontend displays a development badge when active.

## Database setup and grants

Create a dedicated PostgreSQL database and schema-owner/migration role. Create a distinct nonsuperuser runtime login role with no schema ownership, role management, or DDL privileges. Apply migrations with the schema-owner URL, then run `scripts/grant_runtime.sql` as the owner with the runtime role name. The script targets the tracker tables in the `public` schema; use a dedicated database and review it if adopting another schema.

```sh
# The hosting secret mechanism supplies these URL variables; do not put passwords in shell history.
cd backend
alembic upgrade head
alembic current
alembic check
cd ..
psql "$MIGRATION_PSQL_URL" -v runtime_role=asic_tracker_app -f scripts/grant_runtime.sql
```

`DATABASE_URL` for the Python API/migrator uses SQLAlchemy syntax, for example `postgresql+psycopg://user:encoded-password@database-host:5432/asic_tracker?sslmode=verify-full&sslrootcert=/run/secrets/postgres_ca.crt`. `psql` and `pg_dump` use `postgresql://` instead. URL-encode password special characters. Configure the platform's CA mount and network/TLS policy; the production Compose template must be extended with a CA secret mount if that path is needed. The application runtime needs its restricted database URL and network access to PostgreSQL. Keep database credentials out of the browser, avoid publishing the database port to users, and give migration credentials only to the migration job.

The runtime needs transactional reads and planning writes, read/insert audit access, and read access to Alembic's revision table. The migration applies an audit update/delete trigger; database grants also prevent direct audit mutation. Owners/superusers remain operationally privileged and must be controlled separately. Update the explicit table list in `scripts/grant_runtime.sql` and reapply reviewed grants after migrations introduce new tables.

## Production Compose template

This is a standalone deployment template; do not merge it with the local `compose.yaml`.

1. Build and scan the source, then publish to the approved internal registry through the hosting pipeline.
2. Provision the database and runtime role/grants above.
3. Copy `.env.production.example` to `.env.production` and set the approved image, hostname, group mappings, and secret-file paths.
4. Populate the three secret files through the hosting secret system: runtime DB URL, migration-owner DB URL, and gateway token. Files contain only the value. Ensure the container user (UID/GID 10001) can read mounted secrets under your runtime's secret-file permissions.
5. Run `docker compose --env-file .env.production -f compose.production.yaml up -d`. The migration job must finish successfully before the app starts. For subsequent releases, follow the migration/release sequence in OPERATIONS.md.
6. Configure gateway, TLS and private upstream routing; verify login/role behavior with real test identities before admitting users.

The production app runs read-only with a temporary `/tmp`, drops Linux capabilities, and uses a nonroot process. The runtime gets only its DB secret and gateway secret; only the one-time migration job gets the owner credential. In a platform deployment, prefer a release migration job separated from long-running services. Do not mount the source tree, user Downloads, or old demo data into the image.

## Configuration reference

| Variable | Default / meaning |
| --- | --- |
| `DATABASE_URL` or `DATABASE_URL_FILE` | Required PostgreSQL SQLAlchemy URL; use exactly one |
| `AUTH_MODE` | `proxy`; local-only alternative `development` |
| `PROXY_SHARED_SECRET` or `PROXY_SHARED_SECRET_FILE` | Required in proxy mode, at least 32 characters; use exactly one |
| `ROLE_GROUPS` | JSON role-to-group arrays; see `.env.production.example` |
| `TRUSTED_HOSTS` | Explicit comma-separated permitted hostnames; no `*` |
| `FRONTEND_DIR` | `/app/frontend` inside the Docker image |
| `ENABLE_API_DOCS` | `false`; optional authenticated `/api/docs` and `/api/openapi.json` |
| `MAX_BODY_BYTES` | `12582912` (12 MiB), supported 1 KiB–32 MiB |
| `DEV_USER`, `DEV_ROLE` | Used only in development mode; defaults local-developer/admin |

Set the ingress body limit at least as high as the API's chosen value. Never set an empty direct secret variable alongside its `_FILE` alternative. The application intentionally rejects that ambiguous configuration.

## Acceptance before shared rollout

Verify authenticated viewer/editor/admin sessions, denied unassigned groups, rejected direct API spoofing, request/supply/allocation math, family inheritance, concurrent 409 behavior, the expected migration revision, and a database restore into an isolated environment. Run image/dependency scans required by your platform. Confirm backup and incident ownership.

The current transaction model serializes workspace operations and sends complete history. Establish expected record counts, active users, upload size, and latency targets, then load test those sizes. This package does not implement tenant isolation, per-business access rules, fine-grained row endpoints, or a Cisco-specific identity adapter.

Implementation references: [FastAPI container deployment](https://fastapi.tiangolo.com/deployment/docker/), [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/), [PostgreSQL privileges](https://www.postgresql.org/docs/current/ddl-priv.html).
