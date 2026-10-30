# Operations

## Health and logs

`GET /health/live` reports that the Python process is responding. `GET /health/ready` checks database access, workspace metadata, and the expected Alembic revision. Both are unauthenticated and return no planning data. The Docker health check uses readiness. Configure platform liveness/readiness separately where supported.

The service logs to stdout/stderr. Collect logs through the platform, restrict access, and avoid logging identity headers, gateway tokens, DB URLs, JSON request bodies, or exports. The database stores the authenticated actor, operation reason, and a before/after change summary in its append-only audit. Imported legacy audit entries are marked as legacy with unknown actor; they cannot become authenticated server audit entries.

## Release and migration sequence

1. Run CI and required internal scans. Build/promote an immutable application image.
2. Take a recoverable database backup and confirm its restore procedure. Review the migration on a restored staging database.
3. Stop or drain writes if the migration is not backward compatible. Run one `alembic upgrade head` job with the migration-owner credential. For the supplied Compose deployment, run `docker compose --env-file .env.production -f compose.production.yaml run --rm --no-deps migrate` explicitly for each release; do not rely on a previously completed job container being rerun automatically.
4. Update the explicit table list in `scripts/grant_runtime.sql` when tables change, then reapply reviewed runtime grants. Check `alembic current`, `alembic check`, and readiness using the new image.
5. Roll out/recreate the app with the approved image. Perform an authenticated smoke test, then reopen traffic.

Application startup never runs migrations. Every deployment must coordinate the migration job. There is one initial revision, `20261029_0001`; future schema changes must add a new revision and update the backend readiness revision expectation. Never edit an already deployed migration.

Application rollback is safe only when the older app is compatible with the current schema. Alembic downgrade commands may destroy data; do not use downgrade as an unattended rollback mechanism. If recovery needs a database restore, restore into an isolated database first, validate it, and switch over under the hosting team's approved procedure.

## Backups and restore

In-app recovery snapshots capture planning state for user mistake recovery. They share the same database and are not a backup of the service, its audit trail, or the PostgreSQL cluster. Browser JSON exports are also not a substitute for database backups.

Use your platform's PostgreSQL backup/PITR service, or scheduled encrypted `pg_dump` custom-format backups with retention and access control. Back up schema/migration state, planning rows, forecasts, recovery snapshots, and audit. Save role/grant configuration separately. Use a client version compatible with the server. For example, with the backup URL injected securely by the platform and a protected destination directory:

```sh
pg_dump --dbname="$BACKUP_PSQL_URL" --format=custom --no-owner --no-acl --file=/secure-backups/asic-tracker.dump
pg_restore --list /secure-backups/asic-tracker.dump
```

Test restores regularly into a newly provisioned isolated database:

```sh
pg_restore --dbname="$RESTORE_TEST_PSQL_URL" --no-owner --no-acl --exit-on-error /secure-backups/asic-tracker.dump
```

The restore URL must name that empty test database, never the live database. Reapply reviewed runtime grants, verify the migration revision and record totals, and smoke test a separate app instance. Record restore duration and compare it to agreed RPO/RTO. There is deliberately no destructive restore script with a default target in this package.

## Conflicts and failed saves

A stale revision returns HTTP 409. The frontend retains the draft and offers Download draft/Load latest; it does not silently retry or overwrite newer data. Preserve the draft, load the latest workspace, and reapply the intended change. An interrupted response may occur after a server commit; load latest before retrying instead of assuming the save failed.

Database integrity/validation failures return 422 without a partial update. Database outages return 503. Once connectivity recovers, reload authoritative state before resuming edits. There is no offline browser-write queue or local-storage fallback.

## History growth and retention

Audit history is retained, and saved forecasts remain until an administrator explicitly deletes or replaces them through an authorized workflow. Recovery points rotate at a documented maximum of 30; the oldest point is removed when a new point exceeds that count. Complete retained state is currently sent in the workspace envelope and used by optimistic saves. Monitor workspace JSON size, row counts, request latency, lock waits, connection usage, storage, backup duration, and 409/413/422/503 rates. Audit diffs and recovery copies may dominate storage over time. Plan paginated history and smaller entity APIs before volume exceeds measured limits.

The default upload limit is 12 MiB; increasing it is a short-term operational choice within the supported maximum of 32 MiB, not a retention strategy. Do not truncate audit or frozen forecasts to bypass the limit. Agree on an explicit archival policy and implement/test it as a migration or supported API change.

## Secrets and access changes

Rotate gateway and DB credentials through the platform secret store, coordinate gateway/app rollout, and verify access after rotation. Remove access through SSO group membership. All users within a role share the workspace; record-level business entity restrictions would require an application change. Changing a family’s business/funding ownership changes its projects’ current reporting ownership; immutable forecast names and captured records remain historical snapshots.
