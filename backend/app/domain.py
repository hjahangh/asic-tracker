"""Validate the complete shared planning transaction and preserve model semantics."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
import re

from .planning import PACIFIC, allocation_plan, allocation_ship_by, creation_priority, matching_requests, request_ship_by, today_pacific, valid_date

MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_INDEXED_TEXT_BYTES = 2_000
CORE_COLLECTIONS = ("asics", "projects", "projectFamilies", "events", "businessEntities", "fundingSources")
EVENT_TYPES = {"request", "expected_ship", "expected_fulfilment", "actual_ship", "actual_fulfilment"}
ID = re.compile(r"^[A-Za-z0-9_-]+$")
MONTH = re.compile(r"^(?!0000)[0-9]{4}-(?:0[1-9]|1[0-2])$")
QUARTER = re.compile(r"^(?!0000)[0-9]{4}-Q[1-4]$")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9]))?$")
INVALID_TEXT = re.compile(r"[\x00\ud800-\udfff]")


class DomainError(ValueError):
    def __init__(self, errors: list[str] | str):
        self.errors = [errors] if isinstance(errors, str) else list(dict.fromkeys(errors))[:100]
        super().__init__("; ".join(self.errors[:5]))


def empty_state() -> dict:
    return {"version": 2, **{key: [] for key in CORE_COLLECTIONS}, "forecastVersions": [],
        "snapshots": [], "audit": [], "pendingRequests": []}


def valid_id(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 200 and bool(ID.fullmatch(value)) and value not in {"__proto__", "prototype", "constructor"}


def valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value) or not valid_date(value[:10]):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed.astimezone(timezone.utc)
            parsed.astimezone(PACIFIC)
        return True
    except (ValueError, OverflowError):
        return False


def integer(value: object, minimum: int = 0, maximum: int = MAX_SAFE_INTEGER) -> bool:
    return type(value) is int and minimum <= value <= maximum


def price_valid(value: object, nullable: bool = True) -> bool:
    if value is None:
        return nullable
    if isinstance(value, bool) or not isinstance(value, (int, float)) or isinstance(value, float) and not math.isfinite(value):
        return False
    try:
        amount = Decimal(str(value))
        return Decimal(0) <= amount <= Decimal("9999999999.99") and amount == amount.quantize(Decimal("0.01"))
    except InvalidOperation:
        return False


def _safe_json(value: object, depth: int = 0, path: tuple = ()) -> None:
    if depth > 32:
        raise DomainError("Workspace nesting exceeds the supported limit.")
    if isinstance(value, dict):
        if any(isinstance(key, str) and INVALID_TEXT.search(key) for key in value):
            raise DomainError("Workspace text must be valid Unicode without null characters.")
        if any(key in {"__proto__", "constructor"} for key in value):
            raise DomainError("Workspace contains a reserved object key.")
        for key, item in value.items():
            if key == "prototype" and not (len(path) >= 2 and path[-2] == "projects" and isinstance(path[-1], int) and (item is None or type(item) is bool)):
                raise DomainError("Only the scalar project prototype flag may use the prototype field name.")
            _safe_json(item, depth + 1, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _safe_json(item, depth + 1, path + (index,))
    elif isinstance(value, float) and not math.isfinite(value):
        raise DomainError("Workspace numbers must be finite.")
    elif isinstance(value, str) and INVALID_TEXT.search(value):
        # Keep the portable workspace text contract valid for BSON and UTF-8.
        # Reject NUL/unpaired surrogates before storage or response encoding.
        raise DomainError("Workspace text must be valid Unicode without null characters.")


def validate_workspace(payload: dict, *, _snapshot: bool = False) -> dict:
    """Return a detached normalized copy. Never invent family membership."""
    if not isinstance(payload, dict):
        raise DomainError("Workspace must be an object.")
    _safe_json(payload)
    try:
        state = json.loads(json.dumps(payload, allow_nan=False))
    except (ValueError, TypeError) as error:
        raise DomainError("Workspace must contain JSON values only.") from error
    errors = []
    if _snapshot:
        state.setdefault("version", 2)
    if state.get("version") != 2 or isinstance(state.get("version"), bool):
        errors.append("Workspace version must be 2.")
    for key in ("asics", "projects", "events", "businessEntities", "fundingSources", "audit"):
        if not isinstance(state.get(key), list):
            errors.append(f"{key} must be an array.")
    for key in ("projectFamilies", "forecastVersions", "pendingRequests"):
        state.setdefault(key, [])
        if not isinstance(state[key], list):
            errors.append(f"{key} must be an array.")
    if errors:
        raise DomainError(errors)
    if any(len(state[key]) > 10_000 for key in CORE_COLLECTIONS):
        raise DomainError("A planning collection exceeds 10,000 records; split or archive the workspace before import.")
    if len(state["audit"]) > 100_000:
        raise DomainError("Audit import exceeds the supported limit.")

    def text(record: dict, fields: tuple[str, ...], label: str) -> None:
        for field in fields:
            if field in record and not isinstance(record[field], str):
                errors.append(f"{label}: {field} must be text.")

    def masters(key: str, label: str) -> dict:
        records, ids, names = {}, set(), set()
        for index, item in enumerate(state[key]):
            if not isinstance(item, dict):
                errors.append(f"{label} {index + 1} must be an object.")
                continue
            identifier = item.get("id")
            if not valid_id(identifier) or identifier in ids:
                errors.append(f"{label} {index + 1} needs a unique valid ID.")
                continue
            ids.add(identifier)
            name = item.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 500 or name.strip().casefold() in names:
                errors.append(f"{label} {index + 1} needs a unique nonblank name.")
            else:
                item["name"] = name.strip()
                names.add(item["name"].casefold())
            text(item, ("description",), label)
            if item.get("archivedAt") is not None and (not valid_timestamp(item["archivedAt"]) or "T" not in item["archivedAt"]):
                errors.append(f"{label}: archivedAt must be an ISO timestamp with a timezone.")
            records[identifier] = item
        return records

    asics = masters("asics", "ASIC")
    projects = masters("projects", "Project")
    business = masters("businessEntities", "Business entity")
    funding = masters("fundingSources", "Funding source")
    families = masters("projectFamilies", "Project family")
    for family in families.values():
        if not isinstance(family.get("businessEntityId"), str) or family["businessEntityId"] not in business:
            errors.append(f"{family.get('name')}: choose an existing business entity.")
        if not isinstance(family.get("fundingSourceId"), str) or family["fundingSourceId"] not in funding:
            errors.append(f"{family.get('name')}: choose an existing funding source.")
    part_ids = set()
    for asic in asics.values():
        label = asic.get("name", "ASIC")
        if not isinstance(asic.get("owner"), str) or not asic["owner"].strip():
            errors.append(f"{label}: supply-chain owner is required.")
        else:
            asic["owner"] = asic["owner"].strip()
        text(asic, ("marketing", "plid", "assembly", "subtype", "description"), label)
        if not price_valid(asic.get("price")):
            errors.append(f"{label}: price must be blank or finite nonnegative USD with at most two decimals.")
        for field in ("mpns", "cpns"):
            values = asic.get(field)
            if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values) or len(values) != len(set(values)):
                errors.append(f"{label}: {field} must contain unique nonblank strings.")
        history = asic.get("priceHistory")
        if not isinstance(history, list):
            errors.append(f"{label}: priceHistory must be an array.")
            history = []
        quarters = set()
        for item in history:
            if not isinstance(item, dict) or not QUARTER.fullmatch(str(item.get("quarter", ""))) or not price_valid(item.get("price"), nullable=False):
                errors.append(f"{label}: quarterly price history is invalid.")
                continue
            if item["quarter"] in quarters:
                errors.append(f"{label}: duplicate price-history quarter.")
            quarters.add(item["quarter"])
        parts = asic.get("parts", [])
        if not isinstance(parts, list):
            errors.append(f"{label}: parts must be an array.")
            parts = []
        mpns = set()
        for part in parts:
            if not isinstance(part, dict):
                errors.append(f"{label}: part variant must be an object.")
                continue
            if not valid_id(part.get("id")) or part["id"] in part_ids:
                errors.append(f"{label}: part IDs must be valid and unique across the workspace.")
            else:
                part_ids.add(part["id"])
            text(part, ("mpn", "cpn", "plid", "assembly", "subtype"), label)
            mpn = part.get("mpn", "")
            if not isinstance(mpn, str) or not mpn.strip():
                errors.append(f"{label}: each populated part row needs an MPN.")
            elif len(mpn.strip().lower().encode("utf-8")) > MAX_INDEXED_TEXT_BYTES:
                # Retain the portable workspace format's bounded MPN keys.
                errors.append(f"{label}: each part MPN must fit within {MAX_INDEXED_TEXT_BYTES} UTF-8 bytes after lowercase normalization.")
            elif mpn.strip().casefold() in mpns:
                errors.append(f"{label}: part MPNs must be unique within this ASIC.")
            else:
                part["mpn"] = mpn.strip()
                mpns.add(part["mpn"].casefold())
        if "historicalPriceUnknown" in asic and not isinstance(asic["historicalPriceUnknown"], bool):
            errors.append(f"{label}: historicalPriceUnknown must be boolean.")
    keys = set()
    for project in projects.values():
        label = project.get("name", "Project")
        text(project, ("manager", "scpm", "key", "platform", "phase", "summary", "parentId", "projectFamilyId"), label)
        if not isinstance(project.get("manager"), str) or not project["manager"].strip():
            errors.append(f"{label}: EPM is required.")
        else:
            project["manager"] = project["manager"].strip()
        family = families.get(project.get("projectFamilyId")) if isinstance(project.get("projectFamilyId"), str) else None
        if not family:
            errors.append(f"{label}: assign projectFamilyId to an existing project family before import. Family membership is never guessed.")
        elif isinstance(family.get("businessEntityId"), str) and isinstance(family.get("fundingSourceId"), str) and family["businessEntityId"] in business and family["fundingSourceId"] in funding:
            project.update(businessEntityId=family["businessEntityId"], fundingSourceId=family["fundingSourceId"],
                entity=business[family["businessEntityId"]]["name"], funding=funding[family["fundingSourceId"]]["name"])
        key = project.get("key", "")
        if isinstance(key, str):
            project["key"] = key.strip()
        if isinstance(key, str) and project["key"]:
            if len(project["key"].encode("utf-8")) > MAX_INDEXED_TEXT_BYTES:
                errors.append(f"{label}: project key must fit within {MAX_INDEXED_TEXT_BYTES} UTF-8 bytes.")
            if project["key"] in keys:
                errors.append(f"{label}: project key must be unique when set.")
            keys.add(project["key"])
        if any(field in project for field in ("location", "shippingLocation", "actualShippingLocation", "shipLocation")):
            errors.append(f"{label}: shipping-location fields are not supported.")
        associated = project.get("asicIds")
        if not isinstance(associated, list) or any(not isinstance(item, str) or item not in asics for item in associated) or len(set(associated)) != len(associated):
            errors.append(f"{label}: associated ASICs must be unique existing IDs.")
        lead_times = project.get("leadTimes", {})
        if not isinstance(lead_times, dict) or any(identifier not in asics or not integer(days, 0, 36500) for identifier, days in lead_times.items()):
            errors.append(f"{label}: per-ASIC transit times must be nonnegative whole days (at most 36500).")
        if project.get("leadDays") is not None and not integer(project["leadDays"], 0, 36500):
            errors.append(f"{label}: default transit time is invalid.")
        if "prototype" in project and project["prototype"] is not None and not isinstance(project["prototype"], bool):
            errors.append(f"{label}: prototype must be boolean or null.")
        parent = project.get("parentId")
        seen = {project["id"]}
        while parent:
            if not isinstance(parent, str) or parent not in projects:
                errors.append(f"{label}: parent project does not exist.")
                break
            if parent in seen:
                errors.append(f"{label}: parent-project hierarchy contains a cycle.")
                break
            seen.add(parent)
            parent = projects[parent].get("parentId")
    event_ids = set()
    total_qty = 0
    for event in state["events"]:
        if not isinstance(event, dict):
            errors.append("Every planning event must be an object.")
            continue
        label = str(event.get("id", "Event"))
        if not valid_id(event.get("id")) or event["id"] in event_ids:
            errors.append(f"{label}: event ID must be valid and unique.")
        else:
            event_ids.add(event["id"])
        kind = event.get("type")
        if not isinstance(kind, str) or kind not in EVENT_TYPES:
            errors.append(f"{label}: unsupported event type.")
        if not isinstance(event.get("asicId"), str) or event["asicId"] not in asics:
            errors.append(f"{label}: existing ASIC is required.")
        if not valid_date(event.get("date")):
            errors.append(f"{label}: valid event date is required.")
        if not integer(event.get("qty"), 1):
            errors.append(f"{label}: quantity must be a positive safe whole number.")
        else:
            total_qty += event["qty"]
        if kind == "expected_ship" and event.get("projectId"):
            errors.append(f"{label}: supply must be unallocated.")
        elif kind != "expected_ship" and (not isinstance(event.get("projectId"), str) or event["projectId"] not in projects):
            errors.append(f"{label}: existing project is required.")
        text(event, ("projectId", "eta", "note", "requestId", "createdAt", "updatedAt", "phase", "mpn"), label)
        if "shipDays" in event and not integer(event["shipDays"], 0, 36500):
            errors.append(f"{label}: transit days must be a nonnegative whole number.")
        if kind == "request" and "shipDays" not in event:
            errors.append(f"{label}: request transit days are required.")
        for field in ("createdAt", "updatedAt"):
            if field in event and not valid_timestamp(event[field]):
                errors.append(f"{label}: {field} must be a valid ISO timestamp or calendar date.")
        for field in ("requestedShipDate", "availableShipDate"):
            if field in event and (not valid_date(event[field]) or valid_date(event.get("date")) and event[field] > event["date"]):
                errors.append(f"{label}: {field} must be on or before arrival date.")
        if event.get("eta") and not valid_date(event["eta"]):
            errors.append(f"{label}: ETA must be a valid date.")
        if kind == "actual_ship" and (not valid_date(event.get("eta")) or valid_date(event.get("date")) and event["eta"] < event["date"]):
            errors.append(f"{label}: shipment ETA must be on or after shipping.")
        if kind == "expected_ship":
            if "supplyStatus" in event and event["supplyStatus"] not in ("available", "incoming"):
                errors.append(f"{label}: supply status is invalid.")
            text(event, ("supplyReference",), label)
        if "priorShipmentIds" in event:
            baseline = event["priorShipmentIds"]
            if not isinstance(baseline, list) or any(not valid_id(identifier) for identifier in baseline) or len(set(baseline)) != len(baseline):
                errors.append(f"{label}: prior shipment baseline must contain unique valid IDs.")
        if "unitPriceVerified" in event and not isinstance(event["unitPriceVerified"], bool):
            errors.append(f"{label}: unitPriceVerified must be boolean.")
        if event.get("unitPriceVerified") is True and not price_valid(event.get("unitPrice"), nullable=False):
            errors.append(f"{label}: verified unit price is invalid.")
    if total_qty > MAX_SAFE_INTEGER:
        errors.append("Aggregate event quantities exceed the safe whole-number limit.")
    audit_ids = set()
    for entry in state["audit"]:
        if not isinstance(entry, dict) or not valid_id(entry.get("id")) or entry["id"] in audit_ids or not valid_timestamp(entry.get("date")) or not isinstance(entry.get("action"), str) or not entry["action"].strip() or not isinstance(entry.get("detail"), str):
            errors.append("Audit entry is invalid.")
        else:
            audit_ids.add(entry["id"])
    _validate_forecasts(state["forecastVersions"], errors)
    if not _snapshot:
        snapshots = state.get("snapshots")
        if not isinstance(snapshots, list) or len(snapshots) > 30:
            errors.append("snapshots must be an array with at most 30 recovery points.")
            snapshots = []
        snapshot_ids = set()
        for snapshot in snapshots:
            if not isinstance(snapshot, dict) or not valid_id(snapshot.get("id")) or snapshot["id"] in snapshot_ids or not valid_timestamp(snapshot.get("date")) or not isinstance(snapshot.get("label"), str) or not snapshot["label"].strip() or not isinstance(snapshot.get("data"), dict):
                errors.append("Recovery snapshot is invalid.")
                continue
            snapshot_ids.add(snapshot["id"])
            try:
                # Do not discard frozen labels, baseline metadata or original IDs.
                normalized = validate_workspace(snapshot["data"], _snapshot=True)
                normalized.pop("snapshots", None)
                snapshot["data"] = normalized
            except DomainError as error:
                errors.append(f"Snapshot {snapshot['label']}: {error.errors[0]}")
    if errors:
        raise DomainError(errors)
    # Calendar subtraction must also remain inside Python/browser's shared
    # supported years. Valid input dates alone do not prevent underflow.
    for event in state["events"]:
        try:
            if event["type"] == "request":
                request_ship_by(event)
            elif event["type"] == "expected_fulfilment":
                allocation_ship_by(state, event)
        except (ValueError, OverflowError) as error:
            raise DomainError(f"Event {event['id']}: calculated ship date is outside years 0001 through 9999.") from error
    return state


def _validate_forecasts(versions: list, errors: list[str]) -> None:
    if len(versions) > 120:
        errors.append("Keep at most 120 saved monthly forecast versions.")
    ids, months = set(), set()
    for version in versions:
        if not isinstance(version, dict):
            errors.append("Forecast version must be an object.")
            continue
        identifier, month = version.get("id"), version.get("month")
        if not valid_id(identifier) or identifier == "live" or identifier in ids:
            errors.append("Forecast version ID must be unique and valid.")
        if not isinstance(month, str) or not MONTH.fullmatch(month) or month in months:
            errors.append("Forecast version month must be valid and unique.")
        ids.add(identifier if isinstance(identifier, str) else "")
        months.add(month if isinstance(month, str) else "")
        if not isinstance(version.get("name"), str) or not version["name"].strip() or not valid_timestamp(version.get("createdAt")):
            errors.append("Forecast version name and creation timestamp are required.")
        if "note" in version and not isinstance(version["note"], str):
            errors.append("Forecast version note must be text.")
        lines = version.get("lines")
        if not isinstance(lines, list) or len(lines) > 50_000:
            errors.append("Forecast lines must be an array with at most 50,000 records.")
            continue
        total = 0
        for line in lines:
            if not isinstance(line, dict):
                errors.append("Forecast line must be an object.")
                continue
            if not valid_id(line.get("asicId")) or not isinstance(line.get("projectId"), str) or line["projectId"] and not valid_id(line["projectId"]):
                errors.append("Forecast snapshot identifiers are invalid.")
            if not isinstance(line.get("type"), str) or line["type"] not in EVENT_TYPES or line["type"] == "expected_ship" and line.get("projectId") or line["type"] != "expected_ship" and not line.get("projectId"):
                errors.append("Forecast line measure and project relationship are invalid.")
            if not isinstance(line.get("month"), str) or not MONTH.fullmatch(line["month"]) or not integer(line.get("qty")):
                errors.append("Forecast line month or quantity is invalid.")
            else:
                total += line["qty"]
            if any(not isinstance(line.get(key), str) or not line[key].strip() for key in ("asicName", "projectName", "category", "phase")):
                errors.append("Forecast snapshot labels must be nonblank text.")
            if "sourceEventId" in line and not valid_id(line["sourceEventId"]):
                errors.append("Forecast source event ID is invalid.")
        if total > MAX_SAFE_INTEGER:
            errors.append("Forecast aggregate quantity exceeds the safe whole-number limit.")


def requires_admin(before: dict, after: dict, operation: str) -> bool:
    if operation != "edit":
        return True
    if before.get("projectFamilies", []) != after.get("projectFamilies", []):
        return True
    # Automatic bounded snapshot rotation accompanies ordinary edits. The
    # privileged restore/reset/import operation remains checked above.
    for key in (*CORE_COLLECTIONS, "forecastVersions"):
        old_ids = {item["id"] for item in before.get(key, [])}
        new_ids = {item["id"] for item in after.get(key, [])}
        if old_ids - new_ids:
            return True
    return False


def validate_transition(before: dict, after: dict, *, operation: str = "edit", as_of: str | None = None) -> dict:
    """Protect shipped allocations and establish server-owned creation baselines."""
    if operation in {"restore", "reset", "import"}:
        return after
    as_of = as_of or today_pacific()
    old_events = {event["id"]: event for event in before.get("events", [])}
    new_events = {event["id"]: event for event in after["events"]}
    shipped = {row["eventId"]: row["shippedQty"] for row in allocation_plan(before, as_of)["allocations"]}
    completed_before = {event["id"] for event in before.get("events", []) if event["type"] == "actual_ship" and event["date"] <= as_of}
    requests_before = sorted((event for event in before.get("events", []) if event["type"] == "request"),
        key=lambda event: (request_ship_by(event), creation_priority(event.get("createdAt", "")), event["id"]))
    requests_after = sorted((event for event in after["events"] if event["type"] == "request"),
        key=lambda event: (request_ship_by(event), creation_priority(event.get("createdAt", "")), event["id"]))
    remaining_request_ids = {event["id"] for event in requests_after}

    def bound_request(record: dict, requests: list[dict]) -> str | None:
        matches = matching_requests(requests, record.get("requestId", ""), record["asicId"], record["projectId"], identifier_key="id")
        return matches[0]["id"] if matches else None

    errors = []
    for identifier, event in new_events.items():
        old = old_events.get(identifier)
        if old and old["type"] != event["type"]:
            errors.append(f"Event {identifier}: event type cannot be changed; create a separate record.")
        if event["type"] != "expected_fulfilment":
            continue
        if old:
            count = shipped.get(identifier, 0)
            if event["qty"] < count:
                errors.append(f"Allocation {identifier}: quantity cannot be below {count} already shipped units.")
            old_reference, new_reference = old.get("requestId", ""), event.get("requestId", "")
            old_bound, new_bound = bound_request(old, requests_before), bound_request(event, requests_after)
            # Retain a deleted request's literal historical reference, just as
            # an exact-ID link already does. Do not let alias edits silently
            # reassign allocations to another still-live request.
            deleted_link = old_reference == new_reference and old_bound is not None and old_bound not in remaining_request_ids and new_bound is None
            reassigned = (old_bound or old_reference) != (new_bound or new_reference) and not deleted_link
            if old["asicId"] != event["asicId"] or old["projectId"] != event["projectId"] or reassigned:
                errors.append(f"Allocation {identifier}: units must remain with their original assignment; use Reallocate to create a new allocation with a fresh shipment baseline.")
            # A caller cannot rewrite shipment credit or creation priority on an
            # existing allocation by modifying hidden fields.
            if old.get("priorShipmentIds", []) != event.get("priorShipmentIds", []):
                errors.append(f"Allocation {identifier}: prior-shipment baseline is immutable.")
            if old.get("createdAt", "") != event.get("createdAt", ""):
                errors.append(f"Allocation {identifier}: creation timestamp is immutable.")
        else:
            # Only completed, previously stored shipments establish a new
            # allocation's baseline. A client cannot pre-exclude future units.
            event["priorShipmentIds"] = sorted(completed_before)
    # History may reference masters that were later removed. Preserve its frozen
    # labels and quantities, while verifying new captures against the live plan.
    old_versions = {version["id"]: version for version in before.get("forecastVersions", [])}
    captured_lines = None
    for version in after.get("forecastVersions", []):
        old_version = old_versions.get(version["id"])
        if old_version is not None:
            if version != old_version:
                errors.append(f"Forecast {version['id']}: saved versions are immutable; capture a new version.")
        else:
            if captured_lines is None:
                captured_lines = capture_forecast_lines(after)
            if version["lines"] != captured_lines:
                errors.append(f"Forecast {version['id']}: new forecast lines must exactly capture the current workspace.")
    old_snapshots = {snapshot["id"]: snapshot for snapshot in before.get("snapshots", [])}
    previous_data = None
    for snapshot in after.get("snapshots", []):
        old_snapshot = old_snapshots.get(snapshot["id"])
        if old_snapshot is not None:
            if snapshot != old_snapshot:
                errors.append(f"Snapshot {snapshot['id']}: saved recovery points are immutable.")
        else:
            if previous_data is None:
                previous_data = deepcopy({key: before[key] for key in (*CORE_COLLECTIONS, "audit", "forecastVersions", "pendingRequests") if key in before})
                # Empty JSON objects/arrays are truthy in the browser and are
                # included by its snapshot capture; retain that compatibility
                # metadata rather than rejecting the otherwise exact capture.
                if before.get("source") or isinstance(before.get("source"), (dict, list)):
                    previous_data["source"] = deepcopy(before["source"])
                previous_data = validate_workspace(previous_data, _snapshot=True)
            if snapshot["data"] != previous_data:
                errors.append(f"Snapshot {snapshot['id']}: new recovery points must capture the previous server workspace.")
    if errors:
        raise DomainError(errors)
    return after


def capture_forecast_lines(state: dict) -> list[dict]:
    """Capture the same frozen labels and periods as the browser forecast view."""
    asics = {item["id"]: item for item in state["asics"]}
    projects = {item["id"]: item for item in state["projects"]}
    entities = {item["id"]: item for item in state["businessEntities"]}

    def text(value, fallback):
        return value.strip() if isinstance(value, str) and value.strip() else fallback

    lines = []
    for event in state["events"]:
        project = projects.get(event.get("projectId"), {})
        entity = entities.get(project.get("businessEntityId"), {})
        period = request_ship_by(event) if event["type"] == "request" else allocation_ship_by(state, event) if event["type"] == "expected_fulfilment" else event["date"]
        lines.append({"asicId": event["asicId"], "asicName": asics[event["asicId"]]["name"],
            "projectId": event.get("projectId") or "", "projectName": project.get("name") or ("Unallocated supply" if event["type"] == "expected_ship" else "Unknown project"),
            "category": text(entity.get("name"), text(project.get("entity"), "Unassigned")),
            "phase": text(event.get("phase"), text(project.get("phase"), "Unspecified")),
            "type": event["type"], "month": period[:7], "qty": event["qty"], "sourceEventId": event["id"]})
    return lines
