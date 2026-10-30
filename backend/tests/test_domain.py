from copy import deepcopy

import pytest

from app.domain import DomainError, capture_forecast_lines, empty_state, requires_admin, validate_transition, validate_workspace


def test_empty_workspace_is_valid():
    assert validate_workspace(empty_state())["projects"] == []


def test_family_inheritance_is_authoritative_and_detached(workspace):
    workspace["projects"][0]["businessEntityId"] = "forged"
    result = validate_workspace(workspace)
    assert result["projects"][0]["businessEntityId"] == "be"
    assert result["projects"][0]["entity"] == "Business"
    assert workspace["projects"][0]["businessEntityId"] == "forged"


def test_family_mapping_is_never_invented(workspace):
    del workspace["projects"][0]["projectFamilyId"]
    with pytest.raises(DomainError, match="Family membership is never guessed"):
        validate_workspace(workspace)


def test_parent_cycle_rejected(workspace):
    child = deepcopy(workspace["projects"][0])
    child.update(id="child", name="Child", parentId="p")
    workspace["projects"][0]["parentId"] = "child"
    workspace["projects"].append(child)
    with pytest.raises(DomainError, match="cycle"):
        validate_workspace(workspace)


@pytest.mark.parametrize("price", [-1, float("nan"), float("inf"), 1.001, True, 10000000000])
def test_invalid_prices_rejected_without_rounding(workspace, price):
    workspace["asics"][0]["price"] = price
    with pytest.raises(DomainError):
        validate_workspace(workspace)


def test_part_ids_must_be_unique_globally(workspace):
    other = deepcopy(workspace["asics"][0])
    other.update(id="b", name="ASIC B")
    workspace["asics"].append(other)
    with pytest.raises(DomainError, match="part IDs"):
        validate_workspace(workspace)


@pytest.mark.parametrize("field,value", [("qty", True), ("qty", 0), ("qty", 2**53), ("asicId", []), ("type", []), ("projectId", {})])
def test_malformed_events_are_validation_errors(workspace, event, field, value):
    record = event("r", "request", 5, "2026-11-01")
    record[field] = value
    workspace["events"] = [record]
    with pytest.raises(DomainError):
        validate_workspace(workspace)


def test_snapshot_requires_explicit_family_mapping(workspace):
    saved = deepcopy(workspace)
    saved.pop("snapshots")
    saved["projects"][0].pop("projectFamilyId")
    workspace["snapshots"] = [{"id": "snap", "label": "Legacy", "date": "2026-10-29T12:00:00Z", "data": saved}]
    with pytest.raises(DomainError, match="Snapshot Legacy"):
        validate_workspace(workspace)


def test_frozen_history_is_independent_of_live_masters():
    state = empty_state()
    state["forecastVersions"] = [{"id": "v", "month": "2026-10", "name": "October", "createdAt": "2026-10-29T12:00:00Z", "note": "",
        "lines": [{"asicId": "deleted-asic", "asicName": "Frozen ASIC", "projectId": "deleted-project", "projectName": "Frozen project", "category": "Original entity", "phase": "Pilot", "type": "request", "month": "2027-01", "qty": 10}]}]
    assert validate_workspace(state)["forecastVersions"][0]["lines"][0]["asicName"] == "Frozen ASIC"


def test_duplicate_forecast_months_rejected():
    state = empty_state()
    version = {"id": "v", "month": "2026-10", "name": "October", "createdAt": "2026-10-29T12:00:00Z", "lines": []}
    state["forecastVersions"] = [version, {**version, "id": "v2"}]
    with pytest.raises(DomainError, match="month"):
        validate_workspace(state)


def test_admin_policy_checks_data_not_only_operation(workspace):
    after = deepcopy(workspace)
    after["projectFamilies"][0]["name"] = "Changed ownership group"
    assert requires_admin(workspace, after, "edit")
    after = deepcopy(workspace)
    after["events"] = []
    assert not requires_admin(workspace, after, "edit")
    after["asics"] = []
    assert requires_admin(workspace, after, "edit")
    assert requires_admin(workspace, workspace, "import")


def test_shipped_allocation_cannot_move_or_reduce(workspace, event):
    workspace["events"] = [event("s", "expected_ship", 20, "2026-10-01", supplyStatus="available"),
        event("r", "request", 10, "2026-10-10", requestId="alias"),
        event("a", "expected_fulfilment", 10, "2026-10-10", requestId="r", availableShipDate="2026-10-10"),
        event("ship", "actual_ship", 4, "2026-10-10", requestId="r")]
    after = deepcopy(workspace)
    after["events"][2]["qty"] = 3
    with pytest.raises(DomainError, match="already shipped"):
        validate_transition(workspace, after, as_of="2026-10-29")
    after = deepcopy(workspace)
    after["events"][2]["projectId"] = "another"
    with pytest.raises(DomainError, match="original assignment"):
        validate_transition(workspace, after, as_of="2026-10-29")


def test_new_allocation_cannot_claim_prior_shipments(workspace, event):
    workspace["events"] = [event("r", "request", 20, "2026-10-10"), event("ship", "actual_ship", 4, "2026-10-10")]
    after = deepcopy(workspace)
    after["events"].append(event("new-allocation", "expected_fulfilment", 16, "2026-10-12"))
    result = validate_transition(workspace, after, as_of="2026-10-29")
    assert result["events"][-1]["priorShipmentIds"] == ["ship"]


def test_import_preserves_existing_historical_baselines(workspace, event):
    workspace["events"] = [event("ship", "actual_ship", 4, "2026-10-10")]
    after = deepcopy(workspace)
    after["events"].append(event("imported", "expected_fulfilment", 4, "2026-10-10"))
    result = validate_transition(workspace, after, operation="import", as_of="2026-10-29")
    assert "priorShipmentIds" not in result["events"][-1]


def test_project_prototype_boolean_is_safe_and_nested_object_is_rejected(workspace):
    workspace["projects"][0]["prototype"] = True
    assert validate_workspace(workspace)["projects"][0]["prototype"] is True
    workspace["projects"][0]["prototype"] = {"polluted": True}
    with pytest.raises(DomainError, match="scalar project prototype"):
        validate_workspace(workspace)


@pytest.mark.parametrize("stamp", ["0001-01-01T00:00:00Z", "9999-12-31T23:59:59-14:00"])
def test_timestamp_timezone_conversion_stays_within_supported_calendar(workspace, event, stamp):
    workspace["events"] = [event("r", "request", 1, "2026-11-01", createdAt=stamp)]
    with pytest.raises(DomainError, match="valid ISO timestamp"):
        validate_workspace(workspace)


def test_invalid_family_identifier_is_a_validation_error(workspace):
    workspace["projectFamilies"][0]["businessEntityId"] = []
    with pytest.raises(DomainError, match="existing business entity"):
        validate_workspace(workspace)


@pytest.mark.parametrize("value", ["not-a-date", "2026-10-29", "2026-10-29T01:00:00"])
def test_archive_timestamp_requires_timezone(workspace, value):
    workspace["asics"][0]["archivedAt"] = value
    with pytest.raises(DomainError, match="archivedAt"):
        validate_workspace(workspace)


@pytest.mark.parametrize("kind", ["request", "expected_fulfilment"])
def test_calculated_ship_dates_cannot_underflow(workspace, event, kind):
    workspace["projects"][0]["leadTimes"] = {"a": 7}
    workspace["events"] = [event("early", kind, 1, "0001-01-01", shipDays=7)]
    with pytest.raises(DomainError, match="calculated ship date"):
        validate_workspace(workspace)


def test_unshipped_allocation_binding_cannot_be_rewritten(workspace, event):
    workspace["events"] = [event("a1", "expected_fulfilment", 5, "2026-11-01")]
    after = deepcopy(workspace)
    after["events"][0]["requestId"] = "a-different-request"
    with pytest.raises(DomainError, match="Reallocate"):
        validate_transition(workspace, after, as_of="2026-10-29")


def test_new_forecast_is_verified_and_then_frozen(workspace, event):
    before = validate_workspace(workspace)
    after = deepcopy(before)
    after["events"] = [event("request", "request", 8, "2026-11-01", requestedShipDate="2026-10-30")]
    after["forecastVersions"] = [{"id": "v", "month": "2026-10", "name": "October", "createdAt": "2026-10-29T12:00:00Z", "note": "", "lines": capture_forecast_lines(after)}]
    assert validate_transition(before, validate_workspace(after))["forecastVersions"][0]["lines"][0]["month"] == "2026-10"
    forged = deepcopy(after)
    forged["forecastVersions"][0]["lines"][0]["qty"] = 900
    with pytest.raises(DomainError, match="exactly capture"):
        validate_transition(before, forged)
    with pytest.raises(DomainError, match="immutable"):
        validate_transition(after, forged)
    assert validate_transition(after, forged, operation="import") is forged


def test_recovery_point_verifies_prior_server_state_and_is_frozen(workspace):
    before = validate_workspace(workspace)
    saved = deepcopy(before)
    saved.pop("snapshots")
    after = deepcopy(before)
    after["projects"][0]["name"] = "Changed after snapshot"
    after["snapshots"] = [{"id": "s", "date": "2026-10-29T12:00:00Z", "label": "Before editing", "data": saved}]
    after = validate_workspace(after)
    validate_transition(before, after)
    forged = deepcopy(after)
    forged["snapshots"][0]["data"]["projects"][0]["name"] = "Forged history"
    with pytest.raises(DomainError, match="previous server workspace"):
        validate_transition(before, forged)
    with pytest.raises(DomainError, match="immutable"):
        validate_transition(after, forged)
