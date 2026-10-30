"""Authoritative, deterministic supply allocation and request readiness read model.

The browser retains the equivalent calculation for immediate previews. This
implementation runs on validated server data and never changes persisted events.
Unbacked allocation promises remain visible; they do not manufacture inventory.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def today_pacific() -> str:
    return datetime.now(PACIFIC).date().isoformat()


def valid_date(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def creation_date(value: str | None) -> str:
    if not value or valid_date(value):
        return value or ""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(PACIFIC).date().isoformat()


def creation_priority(value: str | None) -> tuple[str, int, str]:
    """Order actual instants consistently with browser millisecond precision.

    Undated imports remain oldest. A calendar-only legacy creation value denotes
    its recorded Pacific day with unknown time, before known instants that day.
    """
    day = creation_date(value)
    if not value or valid_date(value):
        return day, 0, ""
    instant = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return day, 1, instant.isoformat(timespec="milliseconds")


def request_ship_by(event: dict) -> str:
    if valid_date(event.get("requestedShipDate")):
        return event["requestedShipDate"]
    return (date.fromisoformat(event["date"]) - timedelta(days=event.get("shipDays", 0))).isoformat()


def allocation_ship_by(state: dict, event: dict) -> str:
    if valid_date(event.get("availableShipDate")):
        return event["availableShipDate"]
    project = next((p for p in state["projects"] if p["id"] == event.get("projectId")), {})
    days = project.get("leadTimes", {}).get(event["asicId"], project.get("leadDays", 0)) or 0
    return (date.fromisoformat(event["date"]) - timedelta(days=days)).isoformat()


def matching_requests(requests: list[dict], reference: str, asic_id: str, project_id: str,
                      *, identifier_key: str = "eventId") -> list[dict]:
    """Resolve within one ASIC/project; a real event ID always beats an alias.

    Caller ordering retains legacy FIFO behavior for nonunique imported aliases.
    The repository records a canonical FK only when the reference is unambiguous.
    """
    if not reference:
        return []
    matches = [row for row in requests if row["asicId"] == asic_id and row["projectId"] == project_id
               and reference in (row[identifier_key], row.get("requestId"))]
    exact = [row for row in matches if row[identifier_key] == reference]
    return exact or matches


def allocation_plan(state: dict, as_of: str | None = None) -> dict:
    as_of = as_of or today_pacific()
    if not valid_date(as_of):
        raise ValueError("Availability needs a valid as-of date.")
    order = lambda row: (row["shipBy"], creation_priority(row["createdAt"]), row["eventId"])
    requests = sorted(({
        "eventId": e["id"], "requestId": e.get("requestId") or e["id"],
        "asicId": e["asicId"], "projectId": e["projectId"], "qty": e["qty"],
        "shipBy": request_ship_by(e), "arrivalDate": e["date"], "createdAt": e.get("createdAt", ""),
        "shippedQty": 0, "shippedByShipBy": 0, "lastShippedDate": None,
        "remainingQty": e["qty"], "availableByShipBy": 0, "shortfallQty": e["qty"],
        "expectedAvailableDate": None, "status": "shortfall", "allocatedQty": 0,
        "allocatedAvailableByShipBy": 0,
    } for e in state["events"] if e["type"] == "request"), key=order)
    allocations = []
    for event in (e for e in state["events"] if e["type"] == "expected_fulfilment"):
        matches = matching_requests(requests, event.get("requestId", ""), event["asicId"], event["projectId"])
        request = matches[0] if matches else None
        allocations.append({
            "eventId": event["id"], "requestId": event.get("requestId", ""),
            "asicId": event["asicId"], "projectId": event["projectId"], "qty": event["qty"],
            "shipBy": allocation_ship_by(state, event), "arrivalDate": event["date"],
            "createdAt": event.get("createdAt", ""), "shippedQty": 0,
            "remainingQty": event["qty"], "reservedSupplyQty": 0, "unbackedQty": event["qty"],
            "boundRequestId": request["eventId"] if request else "", "lots": [],
        })
    allocations.sort(key=order)
    request_created = {r["eventId"]: creation_date(r["createdAt"]) for r in requests}
    allocation_created = {r["eventId"]: creation_date(r["createdAt"]) for r in allocations}
    baselines = {e["id"]: set(e.get("priorShipmentIds", [])) for e in state["events"] if e["type"] == "expected_fulfilment"}
    credit_allocations = sorted(allocations, key=lambda r: (creation_priority(r["createdAt"]), r["eventId"]))
    shipments = sorted((e for e in state["events"] if e["type"] == "actual_ship" and e["date"] <= as_of),
        key=lambda e: (e["date"], e["id"]))
    completed = [e for e in shipments if e.get("requestId")] + [e for e in shipments if not e.get("requestId")]
    shipment_credits = {}
    for shipment in completed:
        uncredited, credits = shipment["qty"], []
        candidates = matching_requests(requests, shipment["requestId"], shipment["asicId"], shipment["projectId"]) if shipment.get("requestId") else [
            row for row in requests if row["asicId"] == shipment["asicId"] and row["projectId"] == shipment["projectId"]
            and request_created[row["eventId"]] <= shipment["date"]]
        for row in candidates:
            quantity = min(uncredited, row["remainingQty"])
            if not quantity:
                continue
            row["shippedQty"] += quantity
            row["remainingQty"] -= quantity
            uncredited -= quantity
            credits.append({"eventId": row["eventId"], "qty": quantity})
            if shipment["date"] <= row["shipBy"]:
                row["shippedByShipBy"] += quantity
            row["lastShippedDate"] = max(row["lastShippedDate"] or shipment["date"], shipment["date"])
            if not uncredited:
                break
        shipment_credits[shipment["id"]] = credits
    for shipment in completed:
        uncredited = shipment["qty"]
        for credit in shipment_credits[shipment["id"]]:
            remaining = credit["qty"]
            for allocation in credit_allocations:
                if not (allocation["asicId"] == shipment["asicId"] and allocation["projectId"] == shipment["projectId"]
                    and allocation["boundRequestId"] == credit["eventId"] and shipment["id"] not in baselines[allocation["eventId"]]
                    and (shipment.get("requestId") or allocation_created[allocation["eventId"]] <= shipment["date"])):
                    continue
                quantity = min(remaining, allocation["remainingQty"])
                allocation["shippedQty"] += quantity
                allocation["remainingQty"] -= quantity
                uncredited -= quantity
                remaining -= quantity
                if not remaining:
                    break
        # A dedicated promise can exceed its request. Explicit dispatches that
        # exceed still-open demand satisfy that promise too, without reusing
        # units already credited to another request under a shared legacy alias.
        surplus = shipment["qty"] - sum(credit["qty"] for credit in shipment_credits[shipment["id"]])
        if shipment.get("requestId") and surplus:
            targets = {row["eventId"] for row in matching_requests(
                requests, shipment["requestId"], shipment["asicId"], shipment["projectId"])}
            for allocation in credit_allocations:
                if not (allocation["asicId"] == shipment["asicId"] and allocation["projectId"] == shipment["projectId"]
                    and allocation["boundRequestId"] in targets
                    and shipment["id"] not in baselines[allocation["eventId"]]):
                    continue
                quantity = min(surplus, uncredited, allocation["remainingQty"])
                allocation["shippedQty"] += quantity
                allocation["remainingQty"] -= quantity
                uncredited -= quantity
                surplus -= quantity
                if not surplus:
                    break
        for allocation in credit_allocations:
            if not (allocation["asicId"] == shipment["asicId"] and allocation["projectId"] == shipment["projectId"]
                and not allocation["boundRequestId"] and shipment["id"] not in baselines[allocation["eventId"]]
                and allocation_created[allocation["eventId"]] <= shipment["date"]):
                continue
            quantity = min(uncredited, allocation["remainingQty"])
            allocation["shippedQty"] += quantity
            allocation["remainingQty"] -= quantity
            uncredited -= quantity
            if not uncredited:
                break
    supply = []
    for event in sorted((e for e in state["events"] if e["type"] == "expected_ship"), key=lambda e: (e["date"], e["id"])):
        supply.append({"eventId": event["id"], "asicId": event["asicId"], "qty": event["qty"], "date": event["date"],
            "status": "incoming" if event.get("supplyStatus") == "incoming" or event["date"] > as_of else "available",
            "overdue": event.get("supplyStatus") == "incoming" and event["date"] < as_of,
            "consumedQty": 0, "onHandQty": 0, "reservedQty": 0, "freeQty": 0,
            "reference": event.get("supplyReference", ""), "note": event.get("note", "")})
    supply_by_id = {row["eventId"]: row for row in supply}
    pools = defaultdict(list)
    for row in supply:
        if not row["overdue"]:
            pools[row["asicId"]].append({"eventId": row["eventId"], "sourceDate": row["date"],
                "date": max(row["date"], as_of), "qty": row["qty"], "onHand": row["status"] == "available" and row["date"] <= as_of})
    for pool in pools.values():
        pool.sort(key=lambda lot: (lot["date"], not lot["onHand"], lot["sourceDate"], lot["eventId"]))
    shipped_by_asic = defaultdict(int)
    for event in shipments:
        shipped_by_asic[event["asicId"]] += event["qty"]
    for asic_id, pool in pools.items():
        consumed = shipped_by_asic[asic_id]
        for lot in [p for p in pool if p["onHand"]] + [p for p in pool if not p["onHand"]]:
            quantity = min(consumed, lot["qty"])
            lot["qty"] -= quantity
            consumed -= quantity
            supply_by_id[lot["eventId"]]["consumedQty"] += quantity
            if not consumed:
                break
    for row in supply:
        if row["status"] == "available" and row["date"] <= as_of:
            row["onHandQty"] = row["qty"] - row["consumedQty"]
    for allocation in allocations:
        needed = allocation["remainingQty"]
        for lot in pools[allocation["asicId"]]:
            quantity = min(needed, lot["qty"])
            if not quantity:
                continue
            lot["qty"] -= quantity
            needed -= quantity
            allocation["lots"].append({"date": max(lot["date"], allocation["shipBy"], as_of), "qty": quantity})
            if lot["onHand"]:
                supply_by_id[lot["eventId"]]["reservedQty"] += quantity
            allocation["reservedSupplyQty"] += quantity
            if not needed:
                break
        allocation["unbackedQty"] = needed
    for row in supply:
        row["freeQty"] = row["onHandQty"] - row["reservedQty"]
    reserved_for_request = {r["eventId"]: [] for r in requests}
    for allocation in [a for a in allocations if a["boundRequestId"]] + [a for a in allocations if not a["boundRequestId"]]:
        unassigned = allocation["remainingQty"]
        for row in requests:
            if not (row["asicId"] == allocation["asicId"] and row["projectId"] == allocation["projectId"]
                and (not allocation["boundRequestId"] or allocation["boundRequestId"] == row["eventId"])):
                continue
            quantity = min(unassigned, row["remainingQty"] - row["allocatedQty"])
            if not quantity:
                continue
            row["allocatedQty"] += quantity
            unassigned -= quantity
            to_reserve = quantity
            for lot in allocation["lots"]:
                reserved = min(to_reserve, lot["qty"])
                if not reserved:
                    continue
                lot["qty"] -= reserved
                to_reserve -= reserved
                reserved_for_request[row["eventId"]].append({"date": lot["date"], "qty": reserved})
                if lot["date"] <= row["shipBy"]:
                    row["allocatedAvailableByShipBy"] += reserved
                if not to_reserve:
                    break
            if not unassigned:
                break
    for row in requests:
        if not row["remainingQty"]:
            row.update(shortfallQty=0, status="shipped")
            continue
        needed, last_date = row["remainingQty"], None
        for lot in reserved_for_request[row["eventId"]] + pools[row["asicId"]]:
            quantity = min(needed, lot["qty"])
            if not quantity:
                continue
            lot["qty"] -= quantity
            needed -= quantity
            last_date = max(last_date or lot["date"], lot["date"])
            if lot["date"] <= row["shipBy"]:
                row["availableByShipBy"] += quantity
            if not needed:
                break
        row["shortfallQty"] = row["remainingQty"] - row["availableByShipBy"]
        row["expectedAvailableDate"] = None if needed else last_date
        row["status"] = "shortfall" if needed else "on-time" if last_date <= row["shipBy"] else "late"
    for allocation in allocations:
        del allocation["boundRequestId"]
        del allocation["lots"]
    inventory = {}
    ids = dict.fromkeys([a["id"] for a in state["asics"]] + [e["asicId"] for e in state["events"]])
    for asic_id in ids:
        inventory[asic_id] = {"asicId": asic_id, "receivedQty": 0, "shippedQty": shipped_by_asic[asic_id],
            "onHandQty": 0, "reservedQty": 0, "freeQty": 0, "incomingQty": 0, "overdueQty": 0, "stockGapQty": 0}
    for row in supply:
        total = inventory[row["asicId"]]
        total["receivedQty" if row["status"] == "available" and row["date"] <= as_of else "incomingQty"] += row["qty"]
        if row["overdue"]:
            total["overdueQty"] += row["qty"]
        for key in ("onHandQty", "reservedQty", "freeQty"):
            total[key] += row[key]
    for total in inventory.values():
        total["stockGapQty"] = max(0, total["shippedQty"] - total["receivedQty"])
    return {"requests": requests, "allocations": allocations, "supply": supply, "inventory": list(inventory.values())}


def supply_summary(state: dict, as_of: str | None = None) -> list[dict]:
    return allocation_plan(state, as_of)["inventory"]
