from copy import deepcopy

import pytest

from app.planning import allocation_plan, creation_date


def test_free_forecast_does_not_create_allocation(workspace, event):
    workspace["events"] = [event("s", "expected_ship", 10, "2026-11-01", supplyStatus="incoming"), event("r", "request", 10, "2026-11-24")]
    plan = allocation_plan(workspace, "2026-10-29")
    row = plan["requests"][0]
    assert row["availableByShipBy"] == 10
    assert row["allocatedQty"] == 0
    assert plan["allocations"] == []


def test_partial_shipment_consumes_stock_once(workspace, event):
    workspace["events"] = [event("s", "expected_ship", 20, "2026-10-01", supplyStatus="available"), event("r", "request", 10, "2026-11-01"),
        event("a", "expected_fulfilment", 10, "2026-10-01", requestId="r"), event("ship", "actual_ship", 4, "2026-10-20", requestId="r")]
    plan = allocation_plan(workspace, "2026-10-29")
    assert plan["inventory"][0]["onHandQty"] == 16
    assert plan["inventory"][0]["reservedQty"] == 6
    assert plan["allocations"][0]["remainingQty"] == 6
    assert plan["requests"][0]["remainingQty"] == 6


def test_overdue_incoming_is_visible_but_cannot_back_a_request(workspace, event):
    workspace["events"] = [event("s", "expected_ship", 10, "2026-10-01", supplyStatus="incoming"), event("r", "request", 10, "2026-11-01")]
    plan = allocation_plan(workspace, "2026-10-29")
    assert plan["inventory"][0]["incomingQty"] == plan["inventory"][0]["overdueQty"] == 10
    assert plan["requests"][0]["expectedAvailableDate"] is None


def test_date_only_and_pacific_timestamp_boundaries_are_distinct():
    assert creation_date("2026-11-01") == "2026-11-01"
    assert creation_date("2026-11-01T02:00:00Z") == "2026-10-31"


def test_allocation_dates_do_not_move_completed_credit(workspace, event):
    workspace["events"] = [event("r", "request", 20, "2026-11-01"),
        event("a-old", "expected_fulfilment", 10, "2026-11-05", createdAt="2026-10-01T12:00:00Z"),
        event("a-new", "expected_fulfilment", 10, "2026-10-20", createdAt="2026-10-02T12:00:00Z"),
        event("ship", "actual_ship", 5, "2026-10-20")]
    plan = allocation_plan(workspace, "2026-10-29")
    assert next(row for row in plan["allocations"] if row["eventId"] == "a-old")["shippedQty"] == 5
    assert next(row for row in plan["allocations"] if row["eventId"] == "a-new")["shippedQty"] == 0


def test_planning_is_pure_and_future_actual_shipments_are_ignored(workspace, event):
    workspace["events"] = [event("s", "expected_ship", 10, "2026-10-01", supplyStatus="available"), event("r", "request", 10, "2026-11-01"), event("ship", "actual_ship", 5, "2026-11-01")]
    before = deepcopy(workspace)
    plan = allocation_plan(workspace, "2026-10-29")
    assert workspace == before
    assert plan["inventory"][0]["onHandQty"] == 10
    assert plan["requests"][0]["shippedQty"] == 0


def test_exact_request_id_beats_an_earlier_request_alias_for_stock_and_shipments(workspace, event):
    workspace["events"] = [
        event("alias-owner", "request", 10, "2026-11-01", requestId="target"),
        event("target", "request", 10, "2026-11-02", requestId="target-alias"),
        event("supply", "expected_ship", 10, "2026-10-01", supplyStatus="available"),
        event("allocation", "expected_fulfilment", 10, "2026-10-29", requestId="target"),
        event("shipment", "actual_ship", 5, "2026-10-29", requestId="target"),
    ]
    plan = allocation_plan(workspace, "2026-10-29")
    rows = {row["eventId"]: row for row in plan["requests"]}
    assert rows["alias-owner"]["shippedQty"] == rows["alias-owner"]["allocatedQty"] == 0
    assert rows["target"]["shippedQty"] == rows["target"]["allocatedQty"] == 5
    assert plan["allocations"][0]["shippedQty"] == 5
    assert plan["inventory"][0]["onHandQty"] == 5


def test_request_id_resolution_is_scoped_to_the_allocation_project(workspace, event):
    workspace["events"] = [
        event("other", "request", 10, "2026-11-01", projectId="other-project"),
        event("local", "request", 10, "2026-11-02", requestId="other"),
        event("supply", "expected_ship", 10, "2026-10-01", supplyStatus="available"),
        event("allocation", "expected_fulfilment", 10, "2026-10-29", requestId="other"),
    ]
    plan = allocation_plan(workspace, "2026-10-29")
    rows = {row["eventId"]: row for row in plan["requests"]}
    assert rows["other"]["allocatedQty"] == 0
    assert rows["local"]["allocatedQty"] == 10


def test_duplicate_imported_aliases_keep_legacy_fifo_credit(workspace, event):
    workspace["events"] = [
        event("first", "request", 5, "2026-11-01", requestId="legacy-alias"),
        event("second", "request", 10, "2026-11-02", requestId="legacy-alias"),
        event("shipment", "actual_ship", 8, "2026-10-29", requestId="legacy-alias"),
    ]
    rows = allocation_plan(workspace, "2026-10-29")["requests"]
    assert [row["shippedQty"] for row in rows] == [5, 3]


def test_scarce_supply_uses_creation_instants_instead_of_timestamp_spelling(workspace, event):
    workspace["events"] = [
        event("later", "request", 10, "2026-11-01", createdAt="2026-10-29T11:00:00-07:00"),
        event("earlier", "request", 10, "2026-11-01", createdAt="2026-10-29T12:00:00Z"),
        event("supply", "expected_ship", 10, "2026-10-01", supplyStatus="available"),
    ]
    rows = allocation_plan(workspace, "2026-10-29")["requests"]
    assert [(row["eventId"], row["availableByShipBy"]) for row in rows] == [("earlier", 10), ("later", 0)]


def test_completed_credit_uses_actual_allocation_creation_order(workspace, event):
    workspace["events"] = [
        event("request", "request", 20, "2026-11-01"),
        event("later", "expected_fulfilment", 10, "2026-10-29", createdAt="2026-10-29T11:00:00-07:00"),
        event("earlier", "expected_fulfilment", 10, "2026-10-29", createdAt="2026-10-29T12:00:00Z"),
        event("shipment", "actual_ship", 5, "2026-10-29"),
    ]
    rows = {row["eventId"]: row for row in allocation_plan(workspace, "2026-10-29")["allocations"]}
    assert rows["earlier"]["shippedQty"] == 5
    assert rows["later"]["shippedQty"] == 0


@pytest.mark.parametrize("first,second", [
    ("2026-10-29T02:00:00Z", "2026-10-29"),  # The instant was the previous Pacific day.
    ("2026-10-29", "2026-10-29T08:00:00Z"),  # Unknown time precedes instants on that recorded day.
    (None, "2026-10-29T08:00:00Z"),  # Undated legacy records remain oldest.
])
def test_legacy_creation_days_and_known_instants_have_consistent_priority(workspace, event, first, second):
    a = event("first", "request", 10, "2026-11-01")
    b = event("second", "request", 10, "2026-11-01", createdAt=second)
    if first is not None:
        a["createdAt"] = first
    workspace["events"] = [b, a, event("supply", "expected_ship", 10, "2026-10-01", supplyStatus="available")]
    assert allocation_plan(workspace, "2026-10-29")["requests"][0]["eventId"] == "first"


@pytest.mark.parametrize("created_a,created_z", [
    ("2026-10-29T19:00:00+02:00", "2026-10-29T17:00:00Z"),
    ("2026-10-29T17:00:00.0009Z", "2026-10-29T17:00:00.0001Z"),
])
def test_equivalent_browser_millisecond_instants_use_stable_id_tiebreak(workspace, event, created_a, created_z):
    workspace["events"] = [event("z", "request", 10, "2026-11-01", createdAt=created_z),
        event("a", "request", 10, "2026-11-01", createdAt=created_a),
        event("supply", "expected_ship", 10, "2026-10-01", supplyStatus="available")]
    rows = allocation_plan(workspace, "2026-10-29")["requests"]
    assert [(row["eventId"], row["availableByShipBy"]) for row in rows] == [("a", 10), ("z", 0)]


def test_explicit_overshipment_fulfils_excess_dedicated_commitment(workspace, event):
    workspace["events"] = [event("r", "request", 20, "2026-11-01"),
        event("a1", "expected_fulfilment", 100, "2026-10-29", requestId="r"),
        event("supply", "expected_ship", 100, "2026-10-01", supplyStatus="available"),
        event("shipment", "actual_ship", 100, "2026-10-29", requestId="r")]
    plan = allocation_plan(workspace, "2026-10-29")
    assert plan["requests"][0]["shippedQty"] == 20
    assert plan["allocations"][0]["shippedQty"] == 100
    assert plan["allocations"][0]["remainingQty"] == plan["allocations"][0]["unbackedQty"] == 0
    assert plan["inventory"][0]["onHandQty"] == plan["inventory"][0]["reservedQty"] == 0


def test_excess_dedicated_credit_respects_prior_shipment_baseline(workspace, event):
    workspace["events"] = [event("r", "request", 20, "2026-11-01"),
        event("a1", "expected_fulfilment", 100, "2026-10-29", requestId="r", priorShipmentIds=["shipment"]),
        event("shipment", "actual_ship", 100, "2026-10-29", requestId="r")]
    row = allocation_plan(workspace, "2026-10-29")["allocations"][0]
    assert row["shippedQty"] == 0
    assert row["remainingQty"] == 100


def test_unlinked_overshipment_does_not_guess_a_dedicated_allocation(workspace, event):
    workspace["events"] = [event("r", "request", 20, "2026-11-01"),
        event("a1", "expected_fulfilment", 100, "2026-10-29", requestId="r"),
        event("shipment", "actual_ship", 100, "2026-10-29")]
    row = allocation_plan(workspace, "2026-10-29")["allocations"][0]
    assert row["shippedQty"] == 20
    assert row["remainingQty"] == 80


def test_ambiguous_alias_surplus_never_steals_other_requests_shipment_credit(workspace, event):
    workspace["events"] = [event("first", "request", 20, "2026-11-01", requestId="shared"),
        event("second", "request", 60, "2026-11-02", requestId="shared"),
        event("dedicated", "expected_fulfilment", 100, "2026-10-29", requestId="first"),
        event("pool", "expected_fulfilment", 100, "2026-10-29"),
        event("shipment", "actual_ship", 100, "2026-10-29", requestId="shared")]
    plan = allocation_plan(workspace, "2026-10-29")
    allocations = {row["eventId"]: row for row in plan["allocations"]}
    assert [row["shippedQty"] for row in plan["requests"]] == [20, 60]
    assert allocations["dedicated"]["shippedQty"] == 40
    assert allocations["pool"]["shippedQty"] == 60
    assert sum(row["shippedQty"] for row in plan["allocations"]) == 100
