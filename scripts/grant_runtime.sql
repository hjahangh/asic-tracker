-- Run as the schema owner AFTER alembic upgrade head, in the target database.
-- Supply the already-created runtime role; no passwords belong in this file.
-- Use a dedicated, unprivileged role that does not own the database or tables.
-- Example: psql "$MIGRATION_PSQL_URL" -v runtime_role=asic_tracker_app -f scripts/grant_runtime.sql
-- psql URLs use postgresql://, not SQLAlchemy's postgresql+psycopg://.
\set ON_ERROR_STOP on
BEGIN;
SELECT set_config('asic_tracker.runtime_role', :'runtime_role', true);
REVOKE CREATE ON SCHEMA public FROM :"runtime_role";
GRANT USAGE ON SCHEMA public TO :"runtime_role";
-- Reset direct privileges only on this application's tables. Never grant access
-- to unrelated tables or sequences in a shared schema.
REVOKE ALL PRIVILEGES ON TABLE
    public.business_entity, public.funding_source, public.project_family,
    public.project, public.asic, public.asic_mpn, public.asic_price_history,
    public.project_asic, public.planning_event, public.forecast_version,
    public.forecast_line, public.recovery_snapshot, public.workspace_meta,
    public.audit_entry, public.alembic_version
FROM :"runtime_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.business_entity, public.funding_source, public.project_family,
    public.project, public.asic, public.asic_mpn, public.asic_price_history,
    public.project_asic, public.planning_event, public.forecast_version,
    public.forecast_line, public.recovery_snapshot, public.workspace_meta
TO :"runtime_role";
GRANT SELECT, INSERT ON TABLE public.audit_entry TO :"runtime_role";
GRANT SELECT ON TABLE public.alembic_version TO :"runtime_role";
-- The repository supplies all IDs and audit sequence numbers; it does not need
-- privileges on workspace_meta's technical sequence or any other sequence.
DO $$
DECLARE
    app_role text := current_setting('asic_tracker.runtime_role');
    app_oid oid;
BEGIN
    SELECT oid INTO app_oid FROM pg_roles WHERE rolname = app_role;
    IF app_oid IS NULL THEN
        RAISE EXCEPTION 'Runtime role does not exist';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles r
        WHERE (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls)
          AND pg_has_role(app_oid, r.oid, 'MEMBER')
    ) OR has_schema_privilege(app_oid, 'public', 'CREATE') THEN
        RAISE EXCEPTION 'Runtime role must be unprivileged and must not inherit public schema CREATE';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname IN ('business_entity', 'funding_source', 'project_family', 'project',
              'asic', 'asic_mpn', 'asic_price_history', 'project_asic', 'planning_event',
              'forecast_version', 'forecast_line', 'recovery_snapshot', 'workspace_meta',
              'audit_entry', 'alembic_version')
          AND pg_has_role(app_oid, c.relowner, 'MEMBER')
    ) OR has_table_privilege(app_oid, 'public.audit_entry', 'UPDATE,DELETE,TRUNCATE')
      OR has_table_privilege(app_oid, 'public.alembic_version', 'INSERT,UPDATE,DELETE,TRUNCATE') THEN
        RAISE EXCEPTION 'Runtime role owns tracker tables or inherits forbidden audit/migration privileges';
    END IF;
END $$;
COMMIT;
-- Update the explicit table list and re-run when migrations add tables.
-- No CREATE/schema ownership, DDL,
-- superuser or role administration is required by the application process.
-- Existing PUBLIC or inherited role privileges are not revoked globally here;
-- failed assertions require the DBA to correct role/schema provisioning first.
