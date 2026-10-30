"""Repository checks use SQLite locally, or a fresh isolated PostgreSQL test schema.

TEST_DATABASE_URL must point at a disposable test database. Each test creates its
own random schema; existing application tables are never dropped or truncated.
"""
from __future__ import annotations

import copy
import json
import os
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import (
    ASIC, ASICPart, AuditEntry, Base, ForecastLine, PlanningEvent,
    ProjectASIC, WorkspaceMeta,
)
from app.repository import RevisionConflict, empty_state, get_workspace, write_workspace


ACTOR = {"subject": "test-editor", "display_name": "Test Editor", "role": "editor"}


@pytest.fixture
def db_engine():
    url = os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    if url.startswith("sqlite"):
        engine = create_engine(url, poolclass=StaticPool, connect_args={"check_same_thread": False})
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(engine)
        yield engine
    else:
        raw = create_engine(url)
        schema = "tracker_test_" + uuid.uuid4().hex
        with raw.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = raw.execution_options(schema_translate_map={None: schema})
        Base.metadata.create_all(engine)
        try:
            yield engine
        finally:
            with raw.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            raw.dispose()
    engine.dispose()


def sample_state():
    state = empty_state()
    state["businessEntities"] = [{"id": "be-1", "name": "Business", "description": ""}]
    state["fundingSources"] = [{"id": "fund-1", "name": "Funding", "description": ""}]
    state["projectFamilies"] = [{"id": "family-1", "name": "Family", "businessEntityId": "be-1",
                                  "fundingSourceId": "fund-1", "description": ""}]
    state["asics"] = [{"id": "asic-1", "name": "ASIC One", "owner": "Owner", "marketing": "Market",
                       "description": "Catalog", "price": 50.25, "historicalPriceUnknown": False,
                       "parts": [{"id": "part-1", "mpn": "MPN-A", "cpn": "CPN-A", "plid": "PLID-A",
                                  "assembly": "Assembly A", "subtype": "Switch"}],
                       "priceHistory": [{"quarter": "2026-Q4", "price": 50.25}],
                       "mpns": ["MPN-A"], "cpns": ["CPN-A"], "plid": "PLID-A", "assembly": "Assembly A", "subtype": "Switch"}]
    state["projects"] = [{"id": "project-1", "name": "Project One", "projectFamilyId": "family-1",
                          "manager": "EPM", "key": "", "scpm": "SCPM", "platform": "Platform",
                          "parentId": "", "summary": "Summary", "phase": "Prototype",
                          "businessEntityId": "be-1", "fundingSourceId": "fund-1", "entity": "Business", "funding": "Funding",
                          "asicIds": ["asic-1"], "leadTimes": {"asic-1": 3}, "leadDays": 7}]
    common = {"asicId": "asic-1", "projectId": "project-1", "shipDays": 3, "note": "Note",
              "createdAt": "2026-10-29", "updatedAt": "2026-10-29T12:00:00Z", "eta": "", "requestId": ""}
    state["events"] = [
        dict(common, id="supply-1", type="expected_ship", projectId="", qty=30, date="2026-10-01", shipDays=0,
             supplyStatus="available", supplyReference="Receipt A"),
        dict(common, id="request-1", type="request", qty=10, date="2026-11-04", requestedShipDate="2026-11-01", requestId="request-alias"),
        dict(common, id="allocation-1", type="expected_fulfilment", qty=8, date="2026-11-04", availableShipDate="2026-11-01",
             requestId="request-alias", priorShipmentIds=["old-shipment"]),
        dict(common, id="shipment-1", type="actual_ship", qty=2, date="2026-11-01", eta="2026-11-04", requestId="request-1"),
        dict(common, id="arrival-1", type="actual_fulfilment", qty=2, date="2026-11-04"),
    ]
    state["forecastVersions"] = [{"id": "forecast-1", "month": "2026-10", "name": "October plan",
                                   "createdAt": "2026-10-29T12:00:00Z", "note": "Frozen", "lines": [{
                                       "asicId": "asic-1", "asicName": "Historical ASIC", "projectId": "project-1",
                                       "projectName": "Historical Project", "category": "Business", "phase": "Prototype",
                                       "type": "request", "month": "2026-11", "qty": 10, "sourceEventId": "request-1"}]}]
    state["source"] = {"name": "Synthetic test fixture"}
    state["audit"] = [{"id": "client-audit", "date": "2026-10-29T12:00:00Z", "action": "Client action", "detail": "Untrusted client context"}]
    return state


def save(engine, state, revision=0, **options):
    with Session(engine) as session, session.begin():
        return write_workspace(session, state, expected_revision=revision, actor=ACTOR,
                               reason=options.pop("reason", "Test update"), **options)


def load(engine):
    with Session(engine) as session, session.begin():
        return get_workspace(session)


def test_empty_bootstrap_is_repeatable_without_sample_data(db_engine):
    first, second = load(db_engine), load(db_engine)
    assert first == second
    assert first["revision"] == 0
    assert all(first["state"][key] == [] for key in ("asics", "projects", "projectFamilies", "events", "forecastVersions", "audit"))
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(WorkspaceMeta)) == 1


def test_relational_roundtrip_retains_parts_prices_dates_and_legacy_metadata(db_engine):
    result = save(db_engine, sample_state())
    assert result["revision"] == 1
    state = load(db_engine)["state"]
    asic = state["asics"][0]
    assert asic["price"] == 50.25
    assert asic["parts"][0] == sample_state()["asics"][0]["parts"][0]
    assert asic["priceHistory"] == [{"quarter": "2026-Q4", "price": 50.25}]
    assert asic["mpns"] == ["MPN-A"]
    assert state["projects"][0]["leadTimes"] == {"asic-1": 3}
    assert state["projects"][0]["businessEntityId"] == "be-1"
    allocation = next(value for value in state["events"] if value["id"] == "allocation-1")
    assert allocation["createdAt"] == "2026-10-29"
    assert allocation["requestId"] == "request-alias"
    assert allocation["priorShipmentIds"] == ["old-shipment"]
    assert state["source"] == {"name": "Synthetic test fixture"}
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ASICPart)) == 1
        assert session.scalar(select(func.count()).select_from(PlanningEvent)) == 5
        assert session.get(PlanningEvent, "allocation-1").canonical_request_id == "request-1"
        assert "asics" not in session.get(WorkspaceMeta, 1).extra
        assert "projects" not in session.get(WorkspaceMeta, 1).extra


def test_stale_revision_cannot_overwrite_or_create_an_audit(db_engine):
    saved = save(db_engine, sample_state())
    changed = copy.deepcopy(saved["state"])
    changed["asics"][0]["name"] = "Stale rename"
    with pytest.raises(RevisionConflict) as error:
        save(db_engine, changed, revision=0)
    assert error.value.current_revision == 1
    actual = load(db_engine)
    assert actual["state"]["asics"][0]["name"] == "ASIC One"
    assert actual["revision"] == 1
    assert len(actual["state"]["audit"]) == 1


def test_irrelevant_valid_date_metadata_roundtrips_after_event_type_change(db_engine):
    state = sample_state()
    shipment = next(value for value in state["events"] if value["id"] == "shipment-1")
    shipment.update(requestedShipDate="2026-12-01", availableShipDate="2026-12-02")
    result = save(db_engine, state)["state"]
    saved = next(value for value in result["events"] if value["id"] == "shipment-1")
    assert saved["requestedShipDate"] == "2026-12-01"
    assert saved["availableShipDate"] == "2026-12-02"


def test_repository_never_commits_caller_transaction(db_engine):
    save(db_engine, sample_state())
    changed = load(db_engine)["state"]
    changed["asics"][0]["name"] = "Rolled back"
    with pytest.raises(RuntimeError):
        with Session(db_engine) as session, session.begin():
            write_workspace(session, changed, expected_revision=1, actor=ACTOR, reason="Rollback")
            raise RuntimeError("Caller failed after persistence")
    actual = load(db_engine)
    assert actual["revision"] == 1
    assert actual["state"]["asics"][0]["name"] == "ASIC One"
    assert len(actual["state"]["audit"]) == 1


def test_server_audit_attribution_cannot_be_forged_or_removed_by_client(db_engine):
    first = save(db_engine, sample_state())["state"]
    assert len(first["audit"]) == 1
    audit = first["audit"][0]
    assert audit["actor"] == ACTOR["subject"]
    assert audit["legacy"] is False
    assert "client-audit" not in {value["id"] for value in first["audit"]}
    first["audit"] = []
    second = save(db_engine, first, revision=1)["state"]
    assert len(second["audit"]) == 2
    assert second["audit"][0]["id"] == audit["id"]
    assert all(value["actor"] == ACTOR["subject"] for value in second["audit"])


def test_imported_legacy_audits_have_unknown_actor_and_cannot_replace_server_rows(db_engine):
    state = save(db_engine, sample_state())["state"]
    original = copy.deepcopy(state["audit"][0])
    state["audit"][0].update(actor="forged-admin", detail="tampered")
    state["audit"].append(dict(id="legacy-source", date="2025-01-01", action="Old import", detail="Original detail",
                               actor="forged-admin", legacy=False))
    imported = save(db_engine, state, revision=1, operation="import")["state"]
    preserved = next(value for value in imported["audit"] if value["id"] == original["id"])
    assert preserved == original
    legacy = next(value for value in imported["audit"] if value["id"] == "legacy-source")
    assert legacy["actor"] is None and legacy["legacy"] is True
    assert legacy["detail"] == "Original detail"


def test_family_ownership_is_derived_and_not_duplicated_on_projects(db_engine):
    state = sample_state()
    state["projects"][0].update(businessEntityId="forged", fundingSourceId="forged", entity="Wrong", funding="Wrong")
    first = save(db_engine, state)
    assert first["state"]["projects"][0]["entity"] == "Business"
    changed = first["state"]
    changed["businessEntities"].append({"id": "be-2", "name": "New Business", "description": ""})
    changed["fundingSources"].append({"id": "fund-2", "name": "New Funding", "description": ""})
    changed["projectFamilies"][0].update(businessEntityId="be-2", fundingSourceId="fund-2")
    second = save(db_engine, changed, revision=1)["state"]["projects"][0]
    assert second["businessEntityId"] == "be-2"
    assert second["fundingSourceId"] == "fund-2"
    assert second["entity"] == "New Business" and second["funding"] == "New Funding"


def test_name_key_and_part_swaps_are_atomic(db_engine):
    state = sample_state()
    state["businessEntities"].append({"id": "be-2", "name": "Other", "description": ""})
    state["asics"][0]["parts"].append({"id": "part-2", "mpn": "MPN-B", "cpn": "", "plid": "", "assembly": "", "subtype": ""})
    first = save(db_engine, state)["state"]
    first["businessEntities"][0]["name"], first["businessEntities"][1]["name"] = "Other", "Business"
    first["asics"][0]["parts"][0]["mpn"], first["asics"][0]["parts"][1]["mpn"] = "MPN-B", "MPN-A"
    second = save(db_engine, first, revision=1)["state"]
    assert [row["name"] for row in second["businessEntities"]] == ["Other", "Business"]
    assert [row["mpn"] for row in second["asics"][0]["parts"]] == ["MPN-B", "MPN-A"]


def test_forecast_version_can_be_replaced_with_same_month_without_unique_collision(db_engine):
    state = save(db_engine, sample_state())["state"]
    state["forecastVersions"][0]["id"] = "replacement-forecast"
    state["forecastVersions"][0]["name"] = "Replacement"
    result = save(db_engine, state, revision=1)["state"]
    assert result["forecastVersions"][0]["id"] == "replacement-forecast"
    assert result["forecastVersions"][0]["month"] == "2026-10"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ForecastLine)) == 1


def test_delete_masters_retains_frozen_history_and_recovery_payload(db_engine):
    state = save(db_engine, sample_state())["state"]
    frozen = copy.deepcopy(state["forecastVersions"])
    snapshot_data = {key: copy.deepcopy(value) for key, value in state.items() if key != "snapshots"}
    state["snapshots"] = [{"id": "recovery-1", "date": "2026-10-29T13:00:00Z", "label": "Before delete", "data": snapshot_data}]
    state["events"] = []
    state["asics"] = []
    state["projects"][0].update(asicIds=[], leadTimes={})
    result = save(db_engine, state, revision=1)["state"]
    assert result["forecastVersions"] == frozen
    assert result["snapshots"][0]["data"]["asics"][0]["name"] == "ASIC One"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ASIC)) == 0
        assert session.scalar(select(func.count()).select_from(ASICPart)) == 0
        assert session.scalar(select(func.count()).select_from(ProjectASIC)) == 0
        assert session.scalar(select(func.count()).select_from(ForecastLine)) == 1


def test_referenced_request_can_be_deleted_without_losing_legacy_binding_text(db_engine):
    state = save(db_engine, sample_state())["state"]
    state["events"] = [value for value in state["events"] if value["id"] != "request-1"]
    result = save(db_engine, state, revision=1)["state"]
    allocation = next(value for value in result["events"] if value["id"] == "allocation-1")
    assert allocation["requestId"] == "request-alias"
    with Session(db_engine) as session:
        assert session.get(PlanningEvent, "allocation-1").canonical_request_id is None


def test_child_foreign_keys_and_price_checks_are_database_enforced(db_engine):
    save(db_engine, sample_state())
    with pytest.raises(IntegrityError):
        with Session(db_engine) as session, session.begin():
            session.add(ProjectASIC(project_id="missing", asic_id="asic-1", shipping_time_days=3, position=0))
            session.flush()
    with pytest.raises(IntegrityError):
        with Session(db_engine) as session, session.begin():
            row = session.get(ASIC, "asic-1")
            row.unit_price = -1
            session.flush()
    with pytest.raises(IntegrityError):
        with Session(db_engine) as session, session.begin():
            row = session.get(PlanningEvent, "request-1")
            row.quantity = 0
            session.flush()
    assert load(db_engine)["revision"] == 1


def test_audit_diff_contains_before_after_event_quantities(db_engine):
    state = save(db_engine, sample_state())["state"]
    state["events"][2]["qty"] = 9
    result = save(db_engine, state, revision=1, reason="Change allocation")["state"]
    audit = result["audit"][-1]
    detail = json.loads(audit["detail"])
    event = next(change for change in detail["changes"] if change["id"] == "allocation-1")
    assert event["before"]["qty"] == 8 and event["after"]["qty"] == 9
    assert audit["actor"] == "test-editor" and audit["action"] == "Change allocation"


def test_frozen_migration_roundtrip_does_not_load_application_auth(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    backend = Path(__file__).resolve().parents[1]
    url = "sqlite+pysqlite:///" + str(tmp_path / "migration.sqlite3")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
    monkeypatch.setenv("AUTH_MODE", "proxy")
    monkeypatch.delenv("PROXY_TOKEN", raising=False)
    config = Config(str(backend / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    expected = set(Base.metadata.tables)
    assert set(inspect(engine).get_table_names()) == expected | {"alembic_version"}
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261029_0001"
        expression_indexes = set(connection.scalars(text(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'uq_%_ci'")))
        assert expression_indexes == {"uq_business_entity_name_ci", "uq_funding_source_name_ci",
                                      "uq_project_family_name_ci", "uq_project_name_ci", "uq_asic_name_ci",
                                      "uq_asic_mpn_per_asic_ci"}
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) == expected | {"alembic_version"}
    engine.dispose()


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
                    reason="Requires the disposable PostgreSQL integration database")
def test_postgresql_migration_enforces_append_only_audit(monkeypatch):
    from alembic import command
    from alembic.config import Config
    raw = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "tracker_migration_" + uuid.uuid4().hex
    with raw.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(os.environ["TEST_DATABASE_URL"]).update_query_dict({"options": "-csearch_path=" + schema})
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = create_engine(url)
    try:
        command.upgrade(config, "head")
        command.check(config)
        assert set(inspect(engine).get_table_names(schema=schema)) == set(Base.metadata.tables) | {"alembic_version"}
        with engine.begin() as connection:
            connection.execute(text("""INSERT INTO audit_entry
                (audit_id,sequence,workspace_revision,occurred_at_text,action,detail,actor_subject,is_legacy)
                VALUES ('audit-guard',1,0,'2026-10-29T12:00:00Z','Test','Original','test-actor',false)"""))
        for sql in ("UPDATE audit_entry SET detail='tampered' WHERE audit_id='audit-guard'",
                    "DELETE FROM audit_entry WHERE audit_id='audit-guard'"):
            with pytest.raises(DBAPIError, match="append-only"):
                with engine.begin() as connection:
                    connection.execute(text(sql))
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT detail FROM audit_entry WHERE audit_id='audit-guard'")) == "Original"
        with Session(engine) as session, session.begin():
            result = write_workspace(session, sample_state(), expected_revision=0, actor=ACTOR, reason="PostgreSQL write")
            assert result["revision"] == 1
        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names(schema=schema)) == {"alembic_version"}
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261029_0001"
    finally:
        engine.dispose()
        with raw.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        raw.dispose()


def test_postgresql_concurrent_writers_cannot_overwrite_each_other(db_engine):
    if db_engine.dialect.name != "postgresql":
        pytest.skip("Row locking is verified against PostgreSQL, not SQLite")
    state = save(db_engine, sample_state())["state"]
    ready = Barrier(2)
    def writer(subject):
        candidate = copy.deepcopy(state)
        candidate["asics"][0]["name"] = "ASIC-" + subject
        ready.wait(timeout=10)
        try:
            with Session(db_engine) as session, session.begin():
                result = write_workspace(session, candidate, expected_revision=1,
                                         actor={"subject": subject, "display_name": subject, "role": "editor"},
                                         reason="Concurrent edit")
                return "saved", result["revision"], subject
        except RevisionConflict as error:
            return "conflict", error.current_revision, subject
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(writer, ["writer-a", "writer-b"]))
    assert sorted(result[0] for result in results) == ["conflict", "saved"]
    assert all(result[1] == 2 for result in results)
    winner = next(result[2] for result in results if result[0] == "saved")
    final = load(db_engine)
    assert final["revision"] == 2
    assert final["state"]["asics"][0]["name"] == "ASIC-" + winner
    assert len(final["state"]["audit"]) == 2
    assert final["state"]["audit"][-1]["actor"] == winner
