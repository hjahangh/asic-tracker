"""Storage integration against a real transaction-capable MongoDB replica set."""
from __future__ import annotations

import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
from threading import Barrier
import uuid

from bson import Binary
from pymongo.errors import OperationFailure
import pytest

from app.database import (COLLECTIONS, MAX_DOCUMENT_BYTES, READ_CONCERN,
    SCHEMA_COLLECTION, SCHEMA_DOCUMENT_ID, SCHEMA_VERSION, WRITE_CONCERN,
    bootstrap_database, check_ready)
from app.repository import (RevisionConflict, SchemaNotReadyError, StorageIntegrityError,
    StorageValidationError, empty_state, get_workspace, write_workspace)

pytestmark = pytest.mark.mongodb
ACTOR = {"subject": "test-editor", "display_name": "Test Editor", "role": "editor"}


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



def save(db, state, revision=0, **options):
    return write_workspace(db, state, expected_revision=revision, actor=ACTOR,
                           reason=options.pop("reason", "Test update"), **options)


def load(db):
    return get_workspace(db)


def test_empty_bootstrap_is_repeatable_without_sample_data(mongo_database):
    first, second = load(mongo_database), load(mongo_database)
    assert first == second
    assert first["revision"] == 0
    assert all(first["state"][key] == [] for key in ("asics", "projects", "projectFamilies", "events", "forecastVersions", "audit"))
    assert mongo_database.workspace_meta.count_documents({}) == 1


def test_document_roundtrip_retains_parts_prices_dates_and_legacy_metadata(mongo_database):
    result = save(mongo_database, sample_state())
    assert result["revision"] == 1
    state = load(mongo_database)["state"]
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
    assert mongo_database.asic.find_one({"_id": "asic-1"})["record"]["parts"][0]["mpn"] == "MPN-A"
    assert mongo_database.planning_event.count_documents({}) == 5
    assert "asics" not in mongo_database.workspace_meta.find_one({})["extra"]
    assert "businessEntityId" not in mongo_database.project.find_one({})["record"]


def test_legacy_flat_part_metadata_survives_import_without_invented_variants(mongo_database):
    from app.domain import validate_workspace

    state = sample_state()
    state["asics"][0].pop("parts")
    expected = {"mpns": ["Legacy-MPN-A", "Legacy-MPN-B"], "cpns": ["Legacy-CPN"],
                "plid": "Legacy PLID", "assembly": "Legacy assembly", "subtype": "Legacy subtype"}
    state["asics"][0].update(expected)
    first = save(mongo_database, validate_workspace(state))["state"]
    assert first["asics"][0]["parts"] == []
    assert {field: first["asics"][0][field] for field in expected} == expected
    second = save(mongo_database, first, revision=1)["state"]
    assert {field: second["asics"][0][field] for field in expected} == expected
    assert mongo_database.asic.find_one({})["record"].get("parts", []) == []


@pytest.mark.parametrize("default_transit", [None, "absent"])
def test_unspecified_project_transit_preserves_legacy_allocation_ship_date(mongo_database, default_transit):
    from app.domain import validate_workspace
    from app.planning import allocation_plan

    state = sample_state()
    state["projects"][0]["leadTimes"] = {}
    if default_transit == "absent":
        state["projects"][0].pop("leadDays")
    else:
        state["projects"][0]["leadDays"] = default_transit
    next(event for event in state["events"] if event["type"] == "expected_fulfilment").pop("availableShipDate")
    state = validate_workspace(state)
    before = allocation_plan(state, "2026-10-29")["allocations"][0]["shipBy"]
    result = save(mongo_database, state)["state"]
    assert before == "2026-11-04"
    assert allocation_plan(result, "2026-10-29")["allocations"][0]["shipBy"] == before
    assert result["projects"][0]["leadTimes"] == {"asic-1": 0}


def test_accepted_transit_configuration_for_unassociated_asic_is_not_dropped(mongo_database):
    from app.domain import validate_workspace

    state = sample_state()
    state["events"] = []
    state["projects"][0].update(asicIds=[], leadTimes={"asic-1": 9})
    result = save(mongo_database, validate_workspace(state))["state"]
    assert result["projects"][0]["asicIds"] == []
    assert result["projects"][0]["leadTimes"] == {"asic-1": 9}


def test_stale_revision_cannot_overwrite_or_create_an_audit(mongo_database):
    saved = save(mongo_database, sample_state())
    changed = copy.deepcopy(saved["state"])
    changed["asics"][0]["name"] = "Stale rename"
    with pytest.raises(RevisionConflict) as error:
        save(mongo_database, changed, revision=0)
    assert error.value.current_revision == 1
    actual = load(mongo_database)
    assert actual["state"]["asics"][0]["name"] == "ASIC One"
    assert actual["revision"] == 1
    assert len(actual["state"]["audit"]) == 1


def test_irrelevant_valid_date_metadata_roundtrips_after_event_type_change(mongo_database):
    state = sample_state()
    shipment = next(value for value in state["events"] if value["id"] == "shipment-1")
    shipment.update(requestedShipDate="2026-12-01", availableShipDate="2026-12-02")
    result = save(mongo_database, state)["state"]
    saved = next(value for value in result["events"] if value["id"] == "shipment-1")
    assert saved["requestedShipDate"] == "2026-12-01"
    assert saved["availableShipDate"] == "2026-12-02"


def test_repository_never_commits_caller_transaction(mongo_database):
    save(mongo_database, sample_state())
    changed = load(mongo_database)["state"]
    changed["asics"][0]["name"] = "Rolled back"
    with pytest.raises(RuntimeError):
        with mongo_database.client.start_session() as session, session.start_transaction(read_concern=READ_CONCERN, write_concern=WRITE_CONCERN):
            write_workspace(mongo_database, changed, expected_revision=1, actor=ACTOR, reason="Rollback", session=session)
            raise RuntimeError("Caller failed after persistence")
    actual = load(mongo_database)
    assert actual["revision"] == 1
    assert actual["state"]["asics"][0]["name"] == "ASIC One"
    assert len(actual["state"]["audit"]) == 1


def test_server_audit_attribution_cannot_be_forged_or_removed_by_client(mongo_database):
    first = save(mongo_database, sample_state())["state"]
    assert len(first["audit"]) == 1
    audit = first["audit"][0]
    assert audit["actor"] == ACTOR["subject"]
    assert audit["legacy"] is False
    assert "client-audit" not in {value["id"] for value in first["audit"]}
    first["audit"] = []
    second = save(mongo_database, first, revision=1)["state"]
    assert len(second["audit"]) == 2
    assert second["audit"][0]["id"] == audit["id"]
    assert all(value["actor"] == ACTOR["subject"] for value in second["audit"])


def test_imported_legacy_audits_have_unknown_actor_and_cannot_replace_server_rows(mongo_database):
    state = save(mongo_database, sample_state())["state"]
    original = copy.deepcopy(state["audit"][0])
    state["audit"][0].update(actor="forged-admin", detail="tampered")
    state["audit"].append(dict(id="legacy-source", date="2025-01-01", action="Old import", detail="Original detail",
                               actor="forged-admin", legacy=False))
    imported = save(mongo_database, state, revision=1, operation="import")["state"]
    preserved = next(value for value in imported["audit"] if value["id"] == original["id"])
    assert preserved == original
    legacy = next(value for value in imported["audit"] if value["id"] == "legacy-source")
    assert legacy["actor"] is None and legacy["legacy"] is True
    assert legacy["detail"] == "Original detail"


def test_family_ownership_is_derived_and_not_duplicated_on_projects(mongo_database):
    state = sample_state()
    state["projects"][0].update(businessEntityId="forged", fundingSourceId="forged", entity="Wrong", funding="Wrong")
    first = save(mongo_database, state)
    assert first["state"]["projects"][0]["entity"] == "Business"
    changed = first["state"]
    changed["businessEntities"].append({"id": "be-2", "name": "New Business", "description": ""})
    changed["fundingSources"].append({"id": "fund-2", "name": "New Funding", "description": ""})
    changed["projectFamilies"][0].update(businessEntityId="be-2", fundingSourceId="fund-2")
    second = save(mongo_database, changed, revision=1)["state"]["projects"][0]
    assert second["businessEntityId"] == "be-2"
    assert second["fundingSourceId"] == "fund-2"
    assert second["entity"] == "New Business" and second["funding"] == "New Funding"


def test_name_key_and_part_swaps_are_atomic(mongo_database):
    state = sample_state()
    state["businessEntities"].append({"id": "be-2", "name": "Other", "description": ""})
    state["asics"][0]["parts"].append({"id": "part-2", "mpn": "MPN-B", "cpn": "", "plid": "", "assembly": "", "subtype": ""})
    first = save(mongo_database, state)["state"]
    first["businessEntities"][0]["name"], first["businessEntities"][1]["name"] = "Other", "Business"
    first["asics"][0]["parts"][0]["mpn"], first["asics"][0]["parts"][1]["mpn"] = "MPN-B", "MPN-A"
    second = save(mongo_database, first, revision=1)["state"]
    assert [row["name"] for row in second["businessEntities"]] == ["Other", "Business"]
    assert [row["mpn"] for row in second["asics"][0]["parts"]] == ["MPN-B", "MPN-A"]


def test_forecast_version_can_be_replaced_with_same_month_without_unique_collision(mongo_database):
    state = save(mongo_database, sample_state())["state"]
    state["forecastVersions"][0]["id"] = "replacement-forecast"
    state["forecastVersions"][0]["name"] = "Replacement"
    result = save(mongo_database, state, revision=1)["state"]
    assert result["forecastVersions"][0]["id"] == "replacement-forecast"
    assert result["forecastVersions"][0]["month"] == "2026-10"
    assert mongo_database.forecast_line.count_documents({}) == 1


def test_delete_masters_retains_frozen_history_and_recovery_payload(mongo_database):
    state = save(mongo_database, sample_state())["state"]
    frozen = copy.deepcopy(state["forecastVersions"])
    snapshot_data = {key: copy.deepcopy(value) for key, value in state.items() if key != "snapshots"}
    state["snapshots"] = [{"id": "recovery-1", "date": "2026-10-29T13:00:00Z", "label": "Before delete", "data": snapshot_data}]
    state["events"] = []
    state["asics"] = []
    state["projects"][0].update(asicIds=[], leadTimes={})
    result = save(mongo_database, state, revision=1)["state"]
    assert result["forecastVersions"] == frozen
    assert result["snapshots"][0]["data"]["asics"][0]["name"] == "ASIC One"
    assert mongo_database.asic.count_documents({}) == 0
    assert mongo_database.forecast_line.count_documents({}) == 1


def test_referenced_request_can_be_deleted_without_losing_legacy_binding_text(mongo_database):
    state = save(mongo_database, sample_state())["state"]
    state["events"] = [value for value in state["events"] if value["id"] != "request-1"]
    result = save(mongo_database, state, revision=1)["state"]
    allocation = next(value for value in result["events"] if value["id"] == "allocation-1")
    assert allocation["requestId"] == "request-alias"


def test_audit_diff_contains_before_after_event_quantities(mongo_database):
    state = save(mongo_database, sample_state())["state"]
    state["events"][2]["qty"] = 9
    result = save(mongo_database, state, revision=1, reason="Change allocation")["state"]
    audit = result["audit"][-1]
    detail = json.loads(audit["detail"])
    event = next(change for change in detail["changes"] if change["id"] == "allocation-1")
    assert event["before"]["qty"] == 8 and event["after"]["qty"] == 9
    assert audit["actor"] == "test-editor" and audit["action"] == "Change allocation"


@pytest.mark.parametrize("reason,expected", [(" \t ", "Update workspace"), (" " * 200 + "Meaningful action", "Meaningful action")])
def test_server_audit_action_is_nonblank_even_for_internal_whitespace_reason(mongo_database, reason, expected):
    from app.domain import validate_workspace

    result = save(mongo_database, sample_state(), reason=reason)["state"]
    assert result["audit"][-1]["action"] == expected
    assert validate_workspace(result)["audit"][-1]["action"] == expected


def test_audit_retains_full_200_character_accepted_reason(mongo_database):
    reason = "A" * 180 + "Z" * 20
    result = save(mongo_database, sample_state(), reason=reason)["state"]
    assert result["audit"][-1]["action"] == reason
    assert load(mongo_database)["state"]["audit"][-1]["action"] == reason



def test_schema_bootstrap_is_idempotent_and_concurrent_without_demo_data(mongo_database):
    client = mongo_database.client
    db = client["tracker_bootstrap_" + uuid.uuid4().hex]
    barrier = Barrier(2)
    def initialize(_):
        barrier.wait(timeout=10)
        return bootstrap_database(db)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(initialize, range(2)))
        assert all(result["schema_version"] == SCHEMA_VERSION for result in results)
        assert set(db.list_collection_names()) == set(COLLECTIONS)
        assert get_workspace(db) == {"revision": 0, "state": empty_state()}
        assert bootstrap_database(db)["status"] == "ready"
    finally:
        client.drop_database(db.name)


def test_schema_bootstrap_refuses_unknown_version_and_readiness_checks_indexes(mongo_database):
    db = mongo_database
    assert check_ready(db) == {"status": "ready"}
    db.planning_event.drop_index("asic_project_date")
    assert check_ready(db)["reason"] == "schema_indexes_required"
    bootstrap_database(db)
    db.command({"collMod": "planning_event", "validationAction": "warn"})
    assert check_ready(db)["reason"] == "schema_validation_required"
    bootstrap_database(db)
    # Owner-only bypass simulates an older schema on disk. Ordinary runtime
    # credentials do not have bypassDocumentValidation.
    db.workspace_meta.update_one({"_id": SCHEMA_DOCUMENT_ID}, {"$set": {"schema_version": "older"}}, bypass_document_validation=True)
    assert check_ready(db)["reason"] == "schema_bootstrap_required"
    with pytest.raises(ValueError, match="unsupported schema version"):
        bootstrap_database(db)
    with pytest.raises(SchemaNotReadyError):
        get_workspace(db)
    assert db.workspace_meta.find_one({})["schema_version"] == "older"


def test_database_document_validators_reject_invalid_quantities_and_identity(mongo_database):
    saved = save(mongo_database, sample_state())
    for update in ({"record.qty": 0}, {"record.qty": 1.5}, {"record.id": "different-id"}, {"record.type": "unknown"}):
        with pytest.raises(OperationFailure) as error:
            mongo_database.planning_event.update_one({"_id": "request-1"}, {"$set": update})
        assert error.value.code == 121
    with pytest.raises(OperationFailure) as error:
        mongo_database.workspace_meta.update_one({"_id": SCHEMA_DOCUMENT_ID}, {"$set": {"schema_version": "forged"}})
    assert error.value.code == 121
    assert load(mongo_database) == saved


def test_server_validation_failure_rolls_back_revision_entities_and_audit(mongo_database):
    saved = save(mongo_database, sample_state())
    changed = copy.deepcopy(saved["state"])
    changed["asics"][0]["name"] = "Must roll back"
    changed["events"][1]["qty"] = 0
    with pytest.raises(OperationFailure) as error:
        save(mongo_database, changed, revision=1)
    assert error.value.details["writeErrors"][0]["code"] == 121
    assert load(mongo_database) == saved


def test_concurrent_repository_writers_receive_one_revision_conflict(mongo_database):
    initial = save(mongo_database, sample_state())["state"]
    barrier = Barrier(2)
    def writer(subject):
        state = copy.deepcopy(initial)
        state["asics"][0]["name"] = subject
        barrier.wait(timeout=10)
        try:
            result = write_workspace(mongo_database, state, expected_revision=1,
                actor={"subject": subject, "role": "editor"}, reason="Concurrent edit")
            return "saved", result["revision"], subject
        except RevisionConflict as error:
            return "conflict", error.current_revision, subject
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(writer, ("writer-a", "writer-b")))
    assert sorted(result[0] for result in results) == ["conflict", "saved"]
    assert all(result[1] == 2 for result in results)
    winner = next(result[2] for result in results if result[0] == "saved")
    saved = load(mongo_database)
    assert saved["state"]["asics"][0]["name"] == winner
    assert saved["state"]["audit"][-1]["actor"] == winner
    assert len(saved["state"]["audit"]) == 2


def test_snapshot_reader_keeps_one_revision_while_writer_commits(mongo_database):
    first = save(mongo_database, sample_state())
    changed = copy.deepcopy(first["state"])
    changed["asics"][0]["name"] = "Later"
    with mongo_database.client.start_session() as session:
        session.start_transaction(read_concern=READ_CONCERN, write_concern=WRITE_CONCERN)
        try:
            assert get_workspace(mongo_database, session=session) == first
            second = save(mongo_database, changed, revision=1)
            assert get_workspace(mongo_database, session=session) == first
        finally:
            session.abort_transaction()
    assert load(mongo_database) == second


def test_oversized_single_record_fails_before_any_mutation(mongo_database):
    saved = save(mongo_database, sample_state())
    state = copy.deepcopy(saved["state"])
    state["asics"][0]["name"] = "Must not save"
    state["businessEntities"][0]["largeMetadata"] = "x" * MAX_DOCUMENT_BYTES
    with pytest.raises(StorageValidationError, match="16 MiB"):
        save(mongo_database, state, revision=1)
    assert load(mongo_database) == saved


def test_invalid_bson_value_has_sanitized_error_and_no_partial_write(mongo_database):
    state = sample_state()
    state["businessEntities"][0]["secretMetadata"] = 2 ** 80
    with pytest.raises(StorageValidationError) as error:
        save(mongo_database, state)
    assert str(2 ** 80) not in str(error.value)
    assert "secretMetadata" not in str(error.value)
    assert get_workspace(mongo_database)["revision"] == 0


def test_workspace_audit_and_recovery_can_exceed_one_bson_document(mongo_database):
    state = sample_state()
    # Each master fits BSON; their audit delta and the full recovery payload both
    # exceed 16 MiB. No collection contains a giant workspace document.
    payload = "Large fixture " + "x" * (600 * 1024)
    state["businessEntities"].extend({"id": f"large-{index}", "name": f"Large {index}", "description": payload} for index in range(28))
    state["snapshots"] = [{"id": "large-recovery", "date": "2026-10-29", "label": "Large recovery", "data": {"fixture": payload * 28}}]
    saved = save(mongo_database, state)
    assert saved["state"]["snapshots"] == state["snapshots"]
    assert saved["state"]["businessEntities"] == state["businessEntities"]
    assert mongo_database.snapshot_chunk.count_documents({}) > 32
    assert mongo_database.audit_chunk.count_documents({}) > 32
    audit = mongo_database.audit_entry.find_one({})
    assert "detail" not in audit["record"]
    assert len(saved["state"]["audit"][0]["detail"].encode()) > 16 * 1024 * 1024
    assert load(mongo_database) == saved


@pytest.mark.parametrize("collection", ["snapshot_chunk", "audit_chunk"])
@pytest.mark.parametrize("mutation", ["missing", "payload"])
def test_chunk_corruption_is_detected(collection, mutation, mongo_database):
    state = sample_state()
    state["businessEntities"][0]["description"] = "y" * (600 * 1024)
    state["snapshots"] = [{"id": "recovery", "date": "2026-10-29", "label": "Recovery", "data": {"note": "x" * (600 * 1024)}}]
    save(mongo_database, state)
    row = mongo_database[collection].find_one({})
    assert row is not None
    if mutation == "missing":
        mongo_database[collection].delete_one({"_id": row["_id"]})
    else:
        mongo_database[collection].update_one({"_id": row["_id"]}, {"$set": {"data": Binary(b"corrupt")}})
    with pytest.raises(StorageIntegrityError):
        load(mongo_database)


def test_forecast_lines_are_stored_individually_and_order_is_preserved(mongo_database):
    state = sample_state()
    original = state["forecastVersions"][0]["lines"][0]
    state["forecastVersions"][0]["lines"] = [dict(original, qty=index + 1) for index in range(110)]
    saved = save(mongo_database, state)
    assert saved["state"]["forecastVersions"] == state["forecastVersions"]
    assert mongo_database.forecast_line.count_documents({}) == 110
    header = mongo_database.forecast_version.find_one({})
    assert "lines" not in header["record"]
    assert [line["qty"] for line in saved["state"]["forecastVersions"][0]["lines"]] == list(range(1, 111))


def test_migration_cli_bootstraps_checks_and_does_not_load_proxy_auth(mongo_database, tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = "tracker_cli_" + uuid.uuid4().hex
    secret_file = tmp_path / "mongo-uri"
    secret_file.write_text(os.environ["TEST_MONGODB_URI"], encoding="utf-8")
    env = {**os.environ, "MONGODB_DATABASE": database, "MONGODB_URI_FILE": str(secret_file),
           "AUTH_MODE": "proxy", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("MONGODB_URI", None)
    env.pop("PROXY_SHARED_SECRET", None)
    env.pop("PROXY_SHARED_SECRET_FILE", None)
    try:
        for args, status in [(["--check"], 1), ([], 0), (["--check"], 0), ([], 0)]:
            result = subprocess.run([sys.executable, "-m", "app.migrate", *args], cwd=backend, env=env, capture_output=True, text=True, timeout=30)
            assert result.returncode == status, result.stderr
            output = json.loads(result.stdout)
            assert output["status"] == ("ready" if status == 0 else "not_ready")
        assert get_workspace(mongo_database.client[database]) == {"revision": 0, "state": empty_state()}
        env["MONGODB_URI"] = ""
        rejected = subprocess.run([sys.executable, "-m", "app.migrate"], cwd=backend, env=env, capture_output=True, text=True, timeout=30)
        assert rejected.returncode == 1
        assert "not both" in rejected.stderr
        assert os.environ["TEST_MONGODB_URI"] not in rejected.stdout + rejected.stderr
    finally:
        mongo_database.client.drop_database(database)

def test_runtime_role_can_write_workspace_but_cannot_mutate_audit_or_schema(mongo_database):
    """Exercise actual server authorization, not a mocked permission check.

    Privileges mirror setup_mongodb.js; root's deployment check also executes
    that shipped bootstrap script with distinct owner/runtime accounts.
    """
    from pymongo import MongoClient
    from app.database import ORDINARY_COLLECTIONS

    db = mongo_database
    privileges = [
        {"resource": {"db": db.name, "collection": ""}, "actions": ["listCollections", "listIndexes"]},
        *[{"resource": {"db": db.name, "collection": collection}, "actions": ["find", "insert", "update", "remove"]}
          for collection in ORDINARY_COLLECTIONS],
        {"resource": {"db": db.name, "collection": "workspace_meta"}, "actions": ["find", "update"]},
        *[{"resource": {"db": db.name, "collection": collection}, "actions": ["find", "insert"]}
          for collection in ("audit_entry", "audit_chunk")],
    ]
    role, user, password = "asicTrackerRuntime", "runtime_test", uuid.uuid4().hex + uuid.uuid4().hex
    db.command("createRole", role, privileges=privileges, roles=[])
    db.command("createUser", user, pwd=password, roles=[{"role": role, "db": db.name}])
    runtime = MongoClient(os.environ["TEST_MONGODB_URI"], username=user, password=password,
                          authSource=db.name, serverSelectionTimeoutMS=5000, timeoutMS=15000)
    try:
        restricted = runtime[db.name]
        assert check_ready(restricted) == {"status": "ready"}
        state = sample_state()
        state["businessEntities"][0]["description"] = "immutable audit fixture" * 30000
        first = save(restricted, state)
        assert restricted.audit_chunk.count_documents({}) > 0
        changed = copy.deepcopy(first["state"])
        changed["asics"][0]["name"] = "Runtime edit"
        saved = save(restricted, changed, revision=1)
        for collection in ("audit_entry", "audit_chunk"):
            for operation in (lambda: restricted[collection].update_one({}, {"$set": {"tampered": True}}),
                              lambda: restricted[collection].delete_one({}),
                              lambda: restricted[collection].delete_many({})):
                with pytest.raises(OperationFailure) as error:
                    operation()
                assert error.value.code == 13
        for operation in (
            lambda: restricted.planning_event.drop_index("asic_project_date"),
            lambda: restricted.planning_event.drop(),
            lambda: restricted.command({"collMod": "planning_event", "validationAction": "warn"}),
            lambda: restricted.workspace_meta.delete_one({}),
            lambda: restricted.workspace_meta.update_one({}, {"$set": {"schema_version": "forged"}}, bypass_document_validation=True),
        ):
            with pytest.raises(OperationFailure) as error:
                operation()
            assert error.value.code == 13
        with pytest.raises(OperationFailure) as error:
            restricted.workspace_meta.update_one({}, {"$set": {"schema_version": "forged"}})
        assert error.value.code == 121
        assert load(restricted) == saved
    finally:
        runtime.close()
        db.command("dropUser", user)
        db.command("dropRole", role)


def test_optional_part_fields_keep_the_browser_read_contract(mongo_database):
    state = sample_state()
    state["asics"][0]["parts"] = [{"id": "part-1", "mpn": "MPN-A"}]
    result = save(mongo_database, state)["state"]["asics"][0]
    assert result["parts"][0] == {"id": "part-1", "mpn": "MPN-A", "cpn": "", "plid": "", "assembly": "", "subtype": ""}
    assert result["mpns"] == ["MPN-A"] and result["cpns"] == []


@pytest.mark.parametrize("metadata_id", [None, "", 7])
def test_forecast_line_unknown_id_metadata_keeps_domain_contract(mongo_database, metadata_id):
    from app.domain import validate_workspace

    state = sample_state()
    state["forecastVersions"][0]["lines"][0]["id"] = metadata_id
    state = validate_workspace(state)
    saved = save(mongo_database, state)
    assert saved["state"]["forecastVersions"][0]["lines"][0]["id"] == metadata_id
    assert load(mongo_database) == saved
