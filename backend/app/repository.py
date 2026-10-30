"""Atomic relational persistence for the browser's workspace transaction API.

The caller owns the SQLAlchemy transaction. The singleton revision row serializes
writes; stale revisions raise RevisionConflict before any business row is changed.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .models import (
    ASIC, ASICPart, ASICPriceHistory, AuditEntry, BusinessEntity, ForecastLine,
    ForecastVersion, FundingSource, PlanningEvent, Project, ProjectASIC,
    ProjectFamily, RecoverySnapshot, WorkspaceMeta,
)


STATE_ARRAYS = (
    "asics", "projects", "projectFamilies", "events", "businessEntities",
    "fundingSources", "forecastVersions", "snapshots", "audit",
)


class RevisionConflict(Exception):
    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__("The workspace changed. Reload the latest revision before retrying.")


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def empty_state() -> dict[str, Any]:
    return {"version": 2, **{key: [] for key in STATE_ARRAYS}, "pendingRequests": []}


def ensure_meta(session: Session) -> None:
    """Race-safe first-use bootstrap; this creates no sample business records."""
    values = {"id": 1, "revision": 0, "version": 2, "extra": {"pendingRequests": []}}
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        statement = pg_insert(WorkspaceMeta).values(**values).on_conflict_do_nothing(index_elements=["id"])
    elif dialect == "sqlite":
        statement = sqlite_insert(WorkspaceMeta).values(**values).on_conflict_do_nothing(index_elements=["id"])
    else:
        raise RuntimeError("Tracker persistence supports PostgreSQL; SQLite is reserved for unit tests.")
    session.execute(statement)


def _all(session: Session, model: type, *order: Any) -> list[Any]:
    return list(session.scalars(select(model).order_by(*(order or (model.position,)))))


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _date(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def _timestamp(value: Any) -> datetime | None:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None


def _iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _extra(record: dict[str, Any], known: set[str]) -> dict[str, Any]:
    return _copy({key: value for key, value in record.items() if key not in known})


def _asic_extra(record: dict[str, Any]) -> dict[str, Any]:
    known = {"id", "name", "owner", "marketing", "price", "historicalPriceUnknown", "description",
             "parts", "priceHistory", "archivedAt"}
    if record.get("parts"):
        # Structured variants are authoritative when present. Older backups may
        # instead contain only flat lists/labels, whose pairings cannot be guessed.
        known.update({"mpns", "cpns", "plid", "assembly", "subtype"})
    return _extra(record, known)


def _project_extra(record: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(record, {"id", "name", "key", "projectFamilyId", "manager", "scpm", "platform", "prototype",
                            "parentId", "summary", "businessEntityId", "fundingSourceId", "entity", "funding",
                            "asicIds", "leadTimes", "archivedAt"})
    # Live association transit stays relational. Retain accepted legacy settings
    # for unassociated ASICs until an explicit edit removes them.
    unused_transit = {identifier: days for identifier, days in record.get("leadTimes", {}).items()
                      if identifier not in record.get("asicIds", [])}
    if unused_transit:
        extra["leadTimes"] = unused_transit
    return extra


def _master_record(row: Any, identifier: str) -> dict[str, Any]:
    record = _copy(row.extra or {})
    record.update(id=getattr(row, identifier), name=row.name, description=row.description)
    if row.archived_at is not None:
        record["archivedAt"] = _iso(row.archived_at)
    return record


def get_workspace(session: Session, *, lock: bool = False) -> dict[str, Any]:
    ensure_meta(session)
    statement = select(WorkspaceMeta).where(WorkspaceMeta.id == 1)
    if lock:
        statement = statement.with_for_update()
    meta = session.scalar(statement)
    assert meta is not None
    state = empty_state()
    state.update(_copy(meta.extra or {}))
    state["version"] = meta.version
    entities = _all(session, BusinessEntity)
    funding = _all(session, FundingSource)
    families = _all(session, ProjectFamily)
    asics = _all(session, ASIC)
    projects = _all(session, Project)
    parts = _all(session, ASICPart)
    prices = _all(session, ASICPriceHistory)
    associations = _all(session, ProjectASIC)
    state["businessEntities"] = [_master_record(row, "business_entity_id") for row in entities]
    state["fundingSources"] = [_master_record(row, "funding_source_id") for row in funding]
    state["projectFamilies"] = []
    for row in families:
        record = _master_record(row, "project_family_id")
        record.update(businessEntityId=row.business_entity_id, fundingSourceId=row.funding_source_id)
        state["projectFamilies"].append(record)
    entity_names = {row.business_entity_id: row.name for row in entities}
    funding_names = {row.funding_source_id: row.name for row in funding}
    families_by_id = {row.project_family_id: row for row in families}
    state["projects"] = []
    for row in projects:
        family = families_by_id[row.project_family_id]
        pairs = [pair for pair in associations if pair.project_id == row.project_id]
        record = _copy(row.extra or {})
        record.update(
            id=row.project_id, name=row.project_name, key=row.project_key or "",
            projectFamilyId=row.project_family_id, manager=row.engineering_project_manager,
            scpm=row.supply_chain_program_manager, platform=row.platform,
            parentId=row.parent_project_id or "", summary=row.description,
            businessEntityId=family.business_entity_id, fundingSourceId=family.funding_source_id,
            entity=entity_names[family.business_entity_id], funding=funding_names[family.funding_source_id],
            asicIds=[pair.asic_id for pair in pairs],
            leadTimes={**record.get("leadTimes", {}), **{pair.asic_id: pair.shipping_time_days for pair in pairs}},
        )
        if row.prototype is not None:
            record["prototype"] = row.prototype
        if row.archived_at is not None:
            record["archivedAt"] = _iso(row.archived_at)
        state["projects"].append(record)
    state["asics"] = []
    for row in asics:
        variants = []
        for part in parts:
            if part.asic_id == row.asic_id:
                value = _copy(part.extra or {})
                value.update(id=part.part_id, mpn=part.mpn, cpn=part.customer_part_number,
                             plid=part.plid, assembly=part.component_assembly_description,
                             subtype=part.component_sub_type)
                variants.append(value)
        history = []
        for price in prices:
            if price.asic_id == row.asic_id:
                value = _copy(price.extra or {})
                value.update(quarter=price.effective_quarter, price=float(price.unit_price))
                history.append(value)
        unique = lambda key: list(dict.fromkeys(part[key] for part in variants if part.get(key)))
        record = _copy(row.extra or {})
        record.update(id=row.asic_id, name=row.asic_name,
                      owner=row.si_ops_supply_chain_project_manager, marketing=row.marketing_name,
                      description=row.description, price=None if row.unit_price is None else float(row.unit_price),
                      parts=variants, priceHistory=history,
                      mpns=unique("mpn") if variants else record.get("mpns", []),
                      cpns=unique("cpn") if variants else record.get("cpns", []),
                      plid=", ".join(unique("plid")) if variants else record.get("plid", ""),
                      assembly=" | ".join(unique("assembly")) if variants else record.get("assembly", ""),
                      subtype=" | ".join(unique("subtype")) if variants else record.get("subtype", ""))
        if row.historical_price_unknown is not None:
            record["historicalPriceUnknown"] = row.historical_price_unknown
        if row.archived_at is not None:
            record["archivedAt"] = _iso(row.archived_at)
        state["asics"].append(record)
    state["events"] = []
    for row in _all(session, PlanningEvent):
        record = _copy(row.extra or {})
        record.update(id=row.event_id, type=row.event_type, asicId=row.asic_id,
                      projectId=row.project_id or "", qty=row.quantity, date=_iso(row.event_date))
        for field, value in (("shipDays", row.ship_days), ("requestedShipDate", _iso(row.requested_ship_date)),
                             ("availableShipDate", _iso(row.available_ship_date)),
                             ("createdAt", row.created_at_text), ("updatedAt", row.updated_at_text)):
            if value is not None:
                record[field] = value
        # The current editor writes empty ETA/reference strings; retain that API shape.
        record["eta"] = _iso(row.eta) or ""
        record["requestId"] = row.request_reference or ""
        state["events"].append(record)
    lines = _all(session, ForecastLine, ForecastLine.forecast_version_id, ForecastLine.position)
    state["forecastVersions"] = []
    for row in _all(session, ForecastVersion):
        record = _copy(row.extra or {})
        record.update(id=row.forecast_version_id, month=row.version_month, name=row.name,
                      createdAt=row.created_at_text, note=row.note, lines=[])
        for line in lines:
            if line.forecast_version_id == row.forecast_version_id:
                value = _copy(line.extra or {})
                value.update(asicId=line.asic_id, asicName=line.asic_name, projectId=line.project_id,
                             projectName=line.project_name, category=line.category, phase=line.phase,
                             type=line.event_type, month=line.period_month, qty=line.quantity)
                if line.source_event_id is not None:
                    value["sourceEventId"] = line.source_event_id
                record["lines"].append(value)
        state["forecastVersions"].append(record)
    state["snapshots"] = [dict(id=row.snapshot_id, date=row.captured_at_text, label=row.label,
                               data=_copy(row.data)) for row in _all(session, RecoverySnapshot)]
    state["audit"] = []
    for row in _all(session, AuditEntry, AuditEntry.sequence):
        state["audit"].append(dict(id=row.audit_id, date=row.occurred_at_text, action=row.action,
                                   detail=row.detail, actor=row.actor_subject,
                                   actorName=row.actor_display_name, actorRole=row.actor_role,
                                   legacy=row.is_legacy, revision=row.workspace_revision))
    return {"revision": meta.revision, "state": state}


def _key(row: Any, fields: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(getattr(row, name) for name in fields)


def _sync(session: Session, model: type, values: list[dict[str, Any]],
          key_fields: tuple[str, ...]) -> list[Any]:
    existing = {_key(row, key_fields): row for row in session.scalars(select(model))}
    retained = set()
    for value in values:
        key = tuple(value[name] for name in key_fields)
        retained.add(key)
        row = existing.get(key)
        if row is None:
            row = model(**value)
            session.add(row)
        else:
            for name, item in value.items():
                setattr(row, name, item)
    session.flush()
    return [row for key, row in existing.items() if key not in retained]


def _preclear_uniques(session: Session, state: dict[str, Any]) -> None:
    """Allow atomic name/key swaps and import replacements without transient collisions."""
    for model, array, key_attr, name_attr, source_name in (
        (BusinessEntity, "businessEntities", "business_entity_id", "name", "name"),
        (FundingSource, "fundingSources", "funding_source_id", "name", "name"),
        (ProjectFamily, "projectFamilies", "project_family_id", "name", "name"),
        (Project, "projects", "project_id", "project_name", "name"),
        (ASIC, "asics", "asic_id", "asic_name", "name"),
    ):
        desired = {value["id"]: value for value in state[array]}
        for row in session.scalars(select(model)):
            value = desired.get(getattr(row, key_attr))
            if value is None or value[source_name] != getattr(row, name_attr):
                setattr(row, name_attr, "transition-" + uuid.uuid4().hex)
            if model is Project and (value is None or (value.get("key") or None) != row.project_key):
                row.project_key = None
    desired_parts = {part["id"]: (asic["id"], part) for asic in state["asics"] for part in asic.get("parts", [])}
    for row in session.scalars(select(ASICPart)):
        desired = desired_parts.get(row.part_id)
        if desired is None or desired[0] != row.asic_id or desired[1]["mpn"] != row.mpn:
            row.mpn = "transition-" + uuid.uuid4().hex
    desired_versions = {value["id"]: value for value in state.get("forecastVersions", [])}
    rows = list(session.scalars(select(ForecastVersion)))
    used = {row.version_month for row in rows} | {value["month"] for value in desired_versions.values()}
    candidates = (f"{year:04d}-{month:02d}" for year in range(1, 10000) for month in range(1, 13))
    for row in rows:
        desired = desired_versions.get(row.forecast_version_id)
        if desired is None or desired["month"] != row.version_month:
            temporary = next(value for value in candidates if value not in used)
            used.add(temporary)
            row.version_month = temporary
    session.flush()


def _audit_value(collection: str, value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None or collection not in {"snapshots", "forecastVersions"}:
        return value
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return {"id": value["id"], "name": value.get("name", value.get("label")),
            "month": value.get("month"), "lineCount": len(value.get("lines", [])),
            "sha256": hashlib.sha256(data.encode()).hexdigest()}


def _changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for collection in STATE_ARRAYS:
        if collection == "audit":
            continue
        old = {value["id"]: value for value in before.get(collection, [])}
        new = {value["id"]: value for value in after.get(collection, [])}
        for identifier in sorted(old.keys() | new.keys()):
            if old.get(identifier) != new.get(identifier):
                result.append({"collection": collection, "id": identifier,
                               "before": _audit_value(collection, old.get(identifier)),
                               "after": _audit_value(collection, new.get(identifier))})
    return result


def write_workspace(session: Session, state: dict[str, Any], *, expected_revision: int,
                    actor: dict[str, Any], reason: str, operation: str = "edit") -> dict[str, Any]:
    current = get_workspace(session, lock=True)
    if current["revision"] != expected_revision:
        raise RevisionConflict(current["revision"])
    state = _copy(state)
    for collection in STATE_ARRAYS:
        state.setdefault(collection, [])
    _preclear_uniques(session, state)
    stale: dict[type, list[Any]] = {}
    master_known = {"id", "name", "description", "archivedAt"}
    for array, model, identifier in (("businessEntities", BusinessEntity, "business_entity_id"),
                                    ("fundingSources", FundingSource, "funding_source_id")):
        stale[model] = _sync(session, model, [dict(
            **{identifier: value["id"]}, name=value["name"], description=value.get("description", ""),
            archived_at=_timestamp(value.get("archivedAt")), position=index,
            extra=_extra(value, master_known)) for index, value in enumerate(state[array])], (identifier,))
    stale[ASIC] = _sync(session, ASIC, [dict(
        asic_id=value["id"], asic_name=value["name"], si_ops_supply_chain_project_manager=value["owner"],
        marketing_name=value.get("marketing", ""), unit_price=_decimal(value.get("price")),
        historical_price_unknown=value.get("historicalPriceUnknown"), description=value.get("description", ""),
        archived_at=_timestamp(value.get("archivedAt")), position=index,
        extra=_asic_extra(value))
        for index, value in enumerate(state["asics"])], ("asic_id",))
    stale[ProjectFamily] = _sync(session, ProjectFamily, [dict(
        project_family_id=value["id"], name=value["name"], business_entity_id=value["businessEntityId"],
        funding_source_id=value["fundingSourceId"], description=value.get("description", ""), position=index,
        archived_at=_timestamp(value.get("archivedAt")),
        extra=_extra(value, master_known | {"businessEntityId", "fundingSourceId"}))
        for index, value in enumerate(state["projectFamilies"])], ("project_family_id",))
    stale[Project] = _sync(session, Project, [dict(
        project_id=value["id"], project_name=value["name"], project_key=value.get("key") or None,
        project_family_id=value["projectFamilyId"], engineering_project_manager=value["manager"],
        supply_chain_program_manager=value.get("scpm", ""), platform=value.get("platform", ""),
        prototype=value.get("prototype"), parent_project_id=value.get("parentId") or None,
        description=value.get("summary", ""), archived_at=_timestamp(value.get("archivedAt")), position=index,
        extra=_project_extra(value))
        for index, value in enumerate(state["projects"])], ("project_id",))
    part_values, price_values, pair_values = [], [], []
    for asic in state["asics"]:
        for index, part in enumerate(asic.get("parts", [])):
            part_values.append(dict(part_id=part["id"], asic_id=asic["id"], mpn=part["mpn"],
                                    customer_part_number=part.get("cpn", ""), plid=part.get("plid", ""),
                                    component_assembly_description=part.get("assembly", ""),
                                    component_sub_type=part.get("subtype", ""), position=index,
                                    extra=_extra(part, {"id", "mpn", "cpn", "plid", "assembly", "subtype"})))
        for index, price in enumerate(asic.get("priceHistory", [])):
            price_values.append(dict(asic_id=asic["id"], effective_quarter=price["quarter"],
                                     unit_price=_decimal(price["price"]), position=index,
                                     extra=_extra(price, {"quarter", "price"})))
    for project in state["projects"]:
        for index, asic_id in enumerate(project.get("asicIds", [])):
            pair_values.append(dict(project_id=project["id"], asic_id=asic_id, position=index,
                                    shipping_time_days=project.get("leadTimes", {}).get(asic_id, project.get("leadDays") or 0)))
    stale[ASICPart] = _sync(session, ASICPart, part_values, ("part_id",))
    stale[ASICPriceHistory] = _sync(session, ASICPriceHistory, price_values, ("asic_id", "effective_quarter"))
    stale[ProjectASIC] = _sync(session, ProjectASIC, pair_values, ("project_id", "asic_id"))
    requests = [value for value in state["events"] if value["type"] == "request"]
    event_values = []
    for index, value in enumerate(state["events"]):
        reference = value.get("requestId") or None
        matching = [request for request in requests if request["asicId"] == value["asicId"]
                    and request["projectId"] == value.get("projectId")
                    and reference in (request["id"], request.get("requestId"))] if reference else []
        exact = next((request for request in matching if request["id"] == reference), None)
        canonical = exact or (matching[0] if len(matching) == 1 else None)
        event_values.append(dict(event_id=value["id"], event_type=value["type"], asic_id=value["asicId"],
                                 project_id=value.get("projectId") or None, quantity=value["qty"],
                                 event_date=_date(value["date"]), ship_days=value.get("shipDays"),
                                 requested_ship_date=_date(value.get("requestedShipDate")),
                                 available_ship_date=_date(value.get("availableShipDate")), eta=_date(value.get("eta")),
                                 request_reference=reference,
                                 canonical_request_id=canonical["id"] if canonical and value["type"] != "request" else None,
                                 created_at_text=value.get("createdAt"), updated_at_text=value.get("updatedAt"), position=index,
                                 extra=_extra(value, {"id", "type", "asicId", "projectId", "qty", "date", "shipDays",
                                                     "requestedShipDate", "availableShipDate", "eta", "requestId", "createdAt", "updatedAt"})))
    stale[PlanningEvent] = _sync(session, PlanningEvent, event_values, ("event_id",))
    version_values, line_values = [], []
    for index, version in enumerate(state.get("forecastVersions", [])):
        version_values.append(dict(forecast_version_id=version["id"], version_month=version["month"],
                                   name=version["name"], created_at_text=version["createdAt"], note=version.get("note", ""),
                                   position=index, extra=_extra(version, {"id", "month", "name", "createdAt", "note", "lines"})))
        for position, line in enumerate(version.get("lines", [])):
            line_values.append(dict(forecast_version_id=version["id"], position=position, asic_id=line["asicId"],
                                    asic_name=line["asicName"], project_id=line.get("projectId", ""), project_name=line["projectName"],
                                    category=line["category"], phase=line["phase"], event_type=line["type"], period_month=line["month"],
                                    quantity=line["qty"], source_event_id=line.get("sourceEventId"),
                                    extra=_extra(line, {"asicId", "asicName", "projectId", "projectName", "category", "phase",
                                                       "type", "month", "qty", "sourceEventId"})))
    stale[ForecastVersion] = _sync(session, ForecastVersion, version_values, ("forecast_version_id",))
    stale[ForecastLine] = _sync(session, ForecastLine, line_values, ("forecast_version_id", "position"))
    stale[RecoverySnapshot] = _sync(session, RecoverySnapshot, [dict(
        snapshot_id=value["id"], captured_at_text=value["date"], label=value["label"], data=_copy(value["data"]), position=index)
        for index, value in enumerate(state.get("snapshots", []))], ("snapshot_id",))
    # Remove children before parents. The two self-referential FKs are deferred.
    for model in (PlanningEvent, ProjectASIC, ASICPriceHistory, ASICPart, ForecastLine, ForecastVersion,
                  RecoverySnapshot, Project, ProjectFamily, ASIC, BusinessEntity, FundingSource):
        for row in stale.get(model, []):
            session.delete(row)
        session.flush()
    meta = session.get(WorkspaceMeta, 1)
    assert meta is not None
    meta.version = 2
    meta.extra = _extra(state, set(STATE_ARRAYS) | {"version", "storageNotice"})
    meta.extra.setdefault("pendingRequests", [])
    meta.revision += 1
    sequence = int(session.scalar(select(func.max(AuditEntry.sequence))) or 0)
    if operation == "import":
        existing_audit_ids = set(session.scalars(select(AuditEntry.audit_id)))
        for entry in state.get("audit", []):
            if entry["id"] not in existing_audit_ids:
                sequence += 1
                session.add(AuditEntry(audit_id=entry["id"], sequence=sequence, workspace_revision=None,
                                       occurred_at_text=entry["date"], action=entry["action"], detail=entry["detail"],
                                       actor_subject=None, actor_display_name=None, actor_role=None, is_legacy=True))
                existing_audit_ids.add(entry["id"])
    changes = _changes(current["state"], state)
    detail: dict[str, Any] = {"revision": meta.revision, "operation": operation,
                             "changeCount": len(changes), "changes": changes}
    if len(changes) == 1:
        detail.update(before=changes[0]["before"], after=changes[0]["after"])
    session.add(AuditEntry(audit_id="server-" + str(uuid.uuid4()), sequence=sequence + 1,
                           workspace_revision=meta.revision, occurred_at_text=_iso(datetime.now(timezone.utc)),
                           action=((reason or "").strip() or "Update workspace")[:200],
                           detail=json.dumps(detail, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
                           actor_subject=actor["subject"], actor_display_name=actor.get("display_name"),
                           actor_role=actor.get("role"), is_legacy=False))
    session.flush()
    return get_workspace(session)
