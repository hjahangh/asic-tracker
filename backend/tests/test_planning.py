from copy import deepcopy

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
