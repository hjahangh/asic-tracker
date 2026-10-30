# Hosting handoff

## Deployment architecture

```mermaid
flowchart LR
    U[User browser] -->|HTTPS| G[Internal TLS and SSO gateway]
    G -->|Private upstream and verified identity headers| P
    subgraph APP["Application container: nonroot Python process"]
      F[Static frontend assets]
      P[FastAPI Python API]
      P -->|Serves| F
    end
    P -->|PyMongo transactions; TLS in production| D[(MongoDB 8.0 replica set)]
    M[One-time Python schema job] -->|Collection owner credential| D
    S[Platform secret store] -.-> G
    S -.-> P
    S -.-> M
    D --> B[Scheduled encrypted backups and restore verification]
```

The same application image serves the frontend and API on port 8000. MongoDB is a separate authenticated replica set or managed replica-set service. The frontend calls same-origin `/api` endpoints and never connects directly to MongoDB. The backend contains validation, role enforcement, allocation/readiness calculations, revision checks, and audit attribution. There is no CDN dependency or frontend build service.

## Inputs needed from the hosting team

| Input | Used for |
| --- | --- |
| Internal GitHub repository and approved container registry | Source review and approved image publication |
| Docker/Compose or orchestration platform and runner versions | Build, migration job, application rollout |
| Internal DNS hostname and TLS ingress | Browser access and `TRUSTED_HOSTS` |
| SSO gateway with authenticated subject/group claims | Identity headers and role mapping |
| MongoDB 8.0 replica-set endpoints, set name, database, CA and separate owner/runtime accounts | Multi-document transactions and restricted runtime access |
| Platform secret store | MongoDB URIs and gateway shared token |
| Backup/restore owners, retention, RPO/RTO | Recovery beyond in-app snapshots |
| Monitoring/logging destination and service owners | Health checks, incident handling and support |

Use organization-approved base images or mirrors if public image registries are unavailable. Pin the approved application image by digest in the platform's release configuration. The supplied Dockerfile uses `python:3.12-slim`; local development uses `mongo:8.0`. The verified image resolved to MongoDB 8.0.34 on Ubuntu 24.04/kernel 6.8.0-142. The same image refused to start on Ubuntu 26.04/kernel 7.0.0-34 with its kernel compatibility guard. Validate the approved image and Docker host kernel together; this observed restriction must be reevaluated for later MongoDB/kernel patches. See the [upstream kernel/rseq issue](https://jira.mongodb.org/browse/SERVER-121912). Major tags receive updates, so the hosting pipeline should build, scan, and promote a specific tested digest.

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

## Database setup and privileges

Provision a dedicated MongoDB 8.0 replica set with authentication and TLS. A standalone server is unsupported because workspace saves span multiple documents/collections. The backend also accepts a transaction-capable sharded MongoDB cluster through a router, but this audit exercised a replica set only. The local database service explicitly sets soft/hard `nofile` limits to 64,000; the hosting database operator must configure appropriate MongoDB file-descriptor limits on the actual production platform. A full-suite container run exhausted the default 1,024 limit, so do not rely on that default for this deployment. The supplied local single-member set enables development transactions; shared production needs the hosting team's resilient replica-set topology, storage, monitoring and backup policy. Confirm compatibility if using a managed MongoDB-compatible service; transaction and validator support cannot be assumed from protocol compatibility.

Provision the database identities with the reviewed helper below, then use the separate schema-owner account to run `PYTHONPATH=backend python -m app.migrate`. The versioned job creates collections, validators, indexes and initial workspace metadata. Run `PYTHONPATH=backend python -m app.migrate --check` to inspect the expected version `20261030_0001`. These source commands assume Python 3.12 with backend requirements; the supplied migration container runs them without a host Python installation.

The helper creates a [collection-scoped custom runtime role](https://www.mongodb.com/docs/manual/core/collection-level-access-control/); its collection grants may be provisioned before the owner creates the collections. It grants `find`, `insert`, `update` and `remove` on the ten mutable planning/recovery collections; `workspace_meta` has only `find`/`update`; `audit_entry` and `audit_chunk` have only `find`/`insert`. Database-scoped `listCollections` and `listIndexes` support schema-readiness checks. It must not inherit broad `readWrite`, `dbOwner` or administrative roles. Do not grant collection/index creation, collection modification/drop, validator bypass or user/role management. Keep owner credentials only in the release job and operational tooling. Review/reapply the explicit grants when schema versions introduce collections. Database administrators remain privileged and require separate controls.

Run the provisioning helper from the repository root with `mongosh` available:

```sh
# The hosting secret store supplies MONGODB_ADMIN_URI or MONGODB_ADMIN_URI_FILE,
# MONGODB_DATABASE, MONGODB_OWNER_USER, MONGODB_OWNER_PASSWORD or its _FILE,
# and MONGODB_RUNTIME_USER, MONGODB_RUNTIME_PASSWORD or its _FILE.
mongosh --nodb --quiet --file scripts/setup_mongodb.js
```

The administrator URI is for this tool only. The local Compose setup additionally uses `MONGODB_INIT_REPLICA_SET=true` and `MONGODB_REPLICA_MEMBER=db:27017` to initialize `tracker-rs`; do not use this local initialization mode to reconfigure an existing managed set. The helper does not automatically rotate existing user passwords. Coordinate password rotation explicitly through MongoDB administration and the secret store.

Use `MONGODB_URI` or `MONGODB_URI_FILE`, exactly one, and `MONGODB_DATABASE` for both API and migration job, with distinct credentials. The Compose `*_SECRET_FILE` values are host secret paths; inside the containers they map to `MONGODB_URI_FILE`. For a conventional replica set, a connection string has this shape:

```text
mongodb://USER:URL_ENCODED_PASSWORD@mongo1.internal:27017,mongo2.internal:27017,mongo3.internal:27017/?replicaSet=rs0&authSource=admin&tls=true
```

Use the actual authentication database and set name. URL-encode credential special characters. The URI can also specify a platform-mounted `tlsCAFile`; extend the production template to mount that CA when necessary. The API does not expose DB credentials to the browser. Keep database ports private and supply URI files through the secret store. Snapshot read concern and majority write concern are set by the transaction code; do not replace the deployment with a standalone server to simplify setup.

The production template does not provision MongoDB, replica membership, users or TLS; run the provisioning helper or equivalent reviewed platform administration first. Those are hosting tasks. See [MongoDB transaction requirements](https://www.mongodb.com/docs/v8.0/core/transactions-production-consideration/) and the least-privilege role instructions supplied with the source.

## Production Compose template

This is a standalone deployment template; do not merge it with the local `compose.yaml`.

1. Build and scan the source, then publish to the approved internal registry through the hosting pipeline.
2. Provision the database and runtime role/grants above.
3. Copy `.env.production.example` to `.env.production` and set the approved image, hostname, group mappings, `MONGODB_DATABASE`, and secret-file paths (`MONGODB_URI_SECRET_FILE`, `MONGODB_MIGRATION_URI_SECRET_FILE`, `PROXY_SHARED_SECRET_FILE`).
4. Populate the three secret files through the hosting secret system: runtime MongoDB URI, migration-owner MongoDB URI, and gateway token. Files contain only the value. Ensure the container user (UID/GID 10001) can read mounted secrets under your runtime's secret-file permissions.
5. Run `docker compose --env-file .env.production -f compose.production.yaml up -d`. The migration job must finish successfully before the app starts. For subsequent releases, follow the migration/release sequence in OPERATIONS.md.
6. Configure gateway, TLS and private upstream routing; verify login/role behavior with real test identities before admitting users.

The production app runs read-only with a temporary `/tmp`, drops Linux capabilities, and uses a nonroot process. The runtime gets only its DB secret and gateway secret; only the one-time migration job gets the owner credential. In a platform deployment, prefer a release migration job separated from long-running services. Do not mount the source tree, user Downloads, or old demo data into the image.

## Configuration reference

| Variable | Default / meaning |
| --- | --- |
| `MONGODB_URI` or `MONGODB_URI_FILE` | Required MongoDB URI with transaction-capable topology; use exactly one |
| `MONGODB_DATABASE` | API default `asic_tracker`; required by production Compose; keep identical across migration/runtime jobs |
| `AUTH_MODE` | `proxy`; local-only alternative `development` |
| `PROXY_SHARED_SECRET` or `PROXY_SHARED_SECRET_FILE` | Required in proxy mode, at least 32 characters; use exactly one |
| `ROLE_GROUPS` | JSON role-to-group arrays; see `.env.production.example` |
| `TRUSTED_HOSTS` | Explicit comma-separated permitted hostnames; no `*` |
| `FRONTEND_DIR` | `/app/frontend` inside the Docker image; startup checks the directory, index, and referenced local JS/CSS files |
| `ENABLE_API_DOCS` | `false`; optional authenticated `/api/docs` and `/api/openapi.json` |
| `MAX_BODY_BYTES` | `12582912` (12 MiB), supported 1 KiB–32 MiB |
| `DEV_USER`, `DEV_ROLE` | Used only in development mode; defaults local-developer/admin |

Set the ingress body limit at least as high as the API's chosen value. Never set an empty direct secret variable alongside its `_FILE` alternative. The application intentionally rejects that ambiguous configuration.

## Acceptance before shared rollout

Verify authenticated viewer/editor/admin sessions, denied unassigned groups, rejected direct API spoofing, request/supply/allocation math, family inheritance, concurrent 409 behavior, the expected MongoDB schema version, and a database restore into an isolated environment. Run image/dependency scans required by your platform. Confirm backup and incident ownership.

The current transaction model uses a shared revision to coordinate workspace writes and sends complete history. Establish expected record counts, active users, upload size, and latency targets, then load test those sizes. This package does not implement tenant isolation, per-business access rules, fine-grained entity endpoints, or a Cisco-specific identity adapter.

Implementation references: [FastAPI container deployment](https://fastapi.tiangolo.com/deployment/docker/), [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/), [MongoDB privileges](https://www.mongodb.com/docs/manual/core/authorization/).
