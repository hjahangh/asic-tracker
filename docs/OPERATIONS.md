# Operations

## Health and logs

`GET /health/live` reports that Python is responding. `GET /health/ready` verifies MongoDB access, replica-set transaction support, workspace metadata and schema version `20261030_0001`. Both are unauthenticated and return no planning data. The Docker health check uses readiness; configure separate platform liveness/readiness where supported. A standalone MongoDB server is unsupported.

Collect stdout/stderr through the platform with restricted access. Avoid logging identity headers, gateway tokens, MongoDB URIs, JSON bodies or exports. The append-only audit stores authenticated actor, operation reason and before/after changes. Imported legacy actors remain unknown.

## Release and schema sequence

1. Run CI and internal scans; build/promote an immutable image.
2. Take a recoverable database backup and review the schema change on a restored staging replica set.
3. Stop/drain application traffic and wait for in-flight transactions to finish when the release needs maintenance. Run one owner-credential `PYTHONPATH=backend python -m app.migrate` job. With production Compose, explicitly run `docker compose --env-file .env.production -f compose.production.yaml run --rm --no-deps migrate` for each release; a previously completed job is not automatically rerun on every deployment.
4. Review runtime grants when collections change, then reapply them with `mongosh --nodb --quiet --file scripts/setup_mongodb.js` using the database administrator credential and reviewed user/password secret inputs from [HOSTING.md](HOSTING.md). Run `PYTHONPATH=backend python -m app.migrate --check` with the owner credential and verify readiness with the restricted runtime credential.
5. Recreate the app with the approved image, smoke test authenticated roles and planning flows, then reopen traffic.

Application startup never creates collections or applies migrations. Setup is versioned Python code, not SQL/Alembic. Current version is `20261030_0001`; future changes must add reviewed versioned steps and update readiness expectations. Keep owner credentials out of the runtime container.

Rollback is safe only when the older image supports the current document schema. There is no automatic destructive downgrade. For database recovery, restore into an isolated environment, validate, then switch under the hosting team's procedure.

## Backups and restore

In-app recovery points and JSON exports help recover user mistakes and transfer planning state. They do not back up the complete MongoDB service, audit provenance, users or operational configuration.

Use the platform's consistent MongoDB snapshot/PITR service where available. For a logical `mongodump` of this multi-collection application, **stop all application replicas and every other writer to this application database**, including migration jobs and direct database tools, and wait for in-flight transactions to finish. Keep writes stopped until the dump completes. Without this maintenance boundary, a collection-by-collection dump can combine different workspace revisions. A single-member development replica set provides transaction support, not redundancy.

Use MongoDB Database Tools compatible with MongoDB 8.0; use the same tools version for dump and restore, and matching server major/feature compatibility versions. Keep credentials in a protected tools YAML file supplied by the secret store, separate from the application runtime secret. For example, `/run/secrets/mongodb-backup.yaml` contains a `uri` and, if needed, a separate `password`; do not put credentials on the command line. See [Database Tools configuration](https://www.mongodb.com/docs/database-tools/mongodump/) and [restore compatibility](https://www.mongodb.com/docs/database-tools/mongodump/mongodump-behavior/).

With traffic stopped and a protected, nonexisting output path:

```sh
mongodump --config=/run/secrets/mongodb-backup.yaml --db=asic_tracker --archive=/secure-backups/asic-tracker.archive.gz --gzip
```

Use a dedicated backup identity, retention, encryption and access controls. Capture all application collections, including schema/workspace metadata, both audit collections and snapshot chunks. Save database users/roles, replica-set/TLS settings, approved image digest and secret references separately. The single-database archive does not constitute a cluster/configuration backup.

Test a restore into a **new isolated replica set/database** with a separate restore credential, not the live endpoint. The following example maps the source database `asic_tracker` to the fresh database `asic_tracker_restore`:

```sh
mongorestore --config=/run/secrets/mongodb-restore-test.yaml --archive=/secure-backups/asic-tracker.archive.gz --gzip --nsInclude='asic_tracker.*' --nsFrom='asic_tracker.*' --nsTo='asic_tracker_restore.*' --stopOnError
```

The restore YAML must point only at the isolated test deployment. **Omit the database path from the tools URI** when using archive namespace filters/remapping: use `mongodb://RESTORE_USER@restore-host:27017/?authSource=admin&replicaSet=rs0&tls=true`, with the password in the protected YAML `password` field. Set the actual authentication database through `authSource`; do not put `/admin` or an application database before `?`. This differs from an application URI, which may include a database path. The archive source and destination are selected by `--nsInclude`/`--nsFrom`/`--nsTo`. In testing, a URI with `/admin` silently filtered this archive to zero restored documents even though the tool exited successfully. Confirm the target name before execution. No `--drop` is needed for a new database. Restore collection options/indexes, apply reviewed runtime roles separately, and check the schema with `MONGODB_DATABASE=asic_tracker_restore`. Require the expected nonzero collection/document counts; a zero exit code alone does not establish a successful restore. Start a separate app against it and compare exact canonical state, revision, audit sequences/details, checksummed chunks, forecasts and recovery points. Record restore time against RPO/RTO. Reopen original traffic only after the backup succeeds; switching to restored data requires a separate approved cutover.

These commands assume the database is named `asic_tracker`; substitute the configured name in every namespace if different. The hosting team must validate its managed-service backup/restore permissions and tooling. See [mongorestore options](https://www.mongodb.com/docs/database-tools/mongorestore/).

## Conflicts and failed saves

A stale revision returns HTTP 409. The frontend retains a downloadable draft and requires loading latest; it does not silently retry or overwrite. Preserve the draft, reload authoritative data, and reapply the intended change. An interrupted response can occur after commit; reload before assuming the write failed.

Validation/integrity failures return 422 without partial changes. Database outages return 503. Once connectivity recovers, reload before editing. There is no offline write queue or browser-local authority.

## History growth and retention

Audit and saved forecast history are retained. Recovery points rotate at 30. Complete retained state is exchanged in the workspace envelope. Monitor JSON size, document/collection sizes, transaction duration/retries, connection/file-descriptor usage, backup duration and 409/413/422/503 rates. The development MongoDB container sets soft/hard `nofile` to 64,000 after stress testing exhausted the default 1,024; production MongoDB operators must set and monitor suitable limits separately from the application container. Audit diffs and recovery copies can dominate storage. Plan entity-level APIs and paginated history before large volumes.

Uploads default to 12 MiB, configurable up to 32 MiB. Individual BSON documents remain limited to 16 MiB; forecast lines, recovery copies and large audit details are stored separately/chunked. Raising HTTP limits is not a retention strategy. Do not erase audit or frozen forecasts to work around limits; implement reviewed archival through supported APIs/schema changes.

## Secrets and access changes

Rotate gateway/MongoDB credentials through the secret store and verify after rollout. Remove application access through SSO groups. Database owner, runtime, backup and restore identities have separate purposes; runtime audit access remains find/insert only. Users share the workspace, so per-business-entity access would need an application change. Changing a family's ownership changes current projects' reporting ownership; frozen forecast labels remain historical.

## Moving from PostgreSQL

Keep the previous service and its backup available until a reviewed cutover succeeds. Export version-2 workspace JSON through its authenticated Recovery page; retain the original securely. Import the JSON into the empty MongoDB application as an administrator, compare planning totals, IDs, forecasts and recovery points, and validate roles before switching traffic. Existing client-import rules preserve server history and mark newly imported historical audit as legacy; a JSON transfer does not recreate the old database's authenticated audit provenance. Keep the old database backup for that record.

Older demos without project families need the reviewed converter in [README.md](../README.md). SQL dumps and schema files are not accepted by MongoDB. This package neither connects to nor alters an existing PostgreSQL deployment automatically.
