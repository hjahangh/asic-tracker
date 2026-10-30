"""MongoDB workspace persistence with snapshot reads and revision-serialized writes.

Every entity has its own document. Forecast rows and recovery/audit payloads are
split so the workspace never needs to fit in one BSON document. The runtime
account can only find/insert audit records; ordinary synchronization never edits
or deletes those collections.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from bson import BSON
from bson.errors import InvalidDocument
from pymongo import ReplaceOne

from .database import (CHUNK_BYTES, ENTITY_COLLECTIONS, MAX_DOCUMENT_BYTES,
                       ORDINARY_COLLECTIONS, SCHEMA_COLLECTION, SCHEMA_DOCUMENT_ID,
                       SCHEMA_VERSION, run_transaction)

STATE_ARRAYS = (
    "asics", "projects", "projectFamilies", "events", "businessEntities",
    "fundingSources", "forecastVersions", "snapshots", "audit",
)


class RevisionConflict(Exception):
    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__("The workspace changed. Reload the latest revision before retrying.")


class StorageValidationError(ValueError):
    """A workspace value cannot safely be represented in MongoDB."""


class StorageIntegrityError(RuntimeError):
    """Persisted chunk data is missing or corrupt."""


class SchemaNotReadyError(RuntimeError):
    """Owner bootstrap or a schema migration must run before serving data."""


def _copy(value: Any) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        encoded.encode("utf-8")
        return json.loads(encoded)
    except (ValueError, TypeError, UnicodeError, OverflowError) as error:
        raise StorageValidationError("The workspace contains a value that cannot be stored.") from error


def empty_state() -> dict[str, Any]:
    return {"version": 2, **{key: [] for key in STATE_ARRAYS}, "pendingRequests": []}


def _check_session(session):
    if not session.in_transaction:
        raise ValueError("The supplied MongoDB session must have an active transaction.")


def _documents(db, collection, session, cache):
    if collection not in cache:
        order = [("sequence", 1)] if collection == "audit_entry" else [("position", 1), ("_id", 1)]
        cache[collection] = list(db[collection].find({}, session=session).sort(order))
    return cache[collection]


def _decoded_chunks(documents, parent_field, identifier, count, digest):
    chunks = sorted((row for row in documents if row[parent_field] == identifier), key=lambda row: row["position"])
    if len(chunks) != count or [row["position"] for row in chunks] != list(range(count)):
        raise StorageIntegrityError("Stored history chunks are missing or out of order.")
    data = b"".join(bytes(row["data"]) for row in chunks)
    if hashlib.sha256(data).hexdigest() != digest:
        raise StorageIntegrityError("Stored history failed its integrity check.")
    try:
        return data.decode("utf-8")
    except UnicodeError as error:
        raise StorageIntegrityError("Stored history is not valid UTF-8.") from error


def _read_workspace(db, session, cache=None):
    cache = {} if cache is None else cache
    meta = db[SCHEMA_COLLECTION].find_one({"_id": SCHEMA_DOCUMENT_ID}, session=session)
    if not meta or meta.get("schema_version") != SCHEMA_VERSION:
        raise SchemaNotReadyError("The MongoDB schema must be bootstrapped before use.")
    state = empty_state()
    state.update(_copy(meta["extra"]))
    state["version"] = meta["version"]
    for array, collection in ENTITY_COLLECTIONS.items():
        state[array] = [_copy(row["record"]) for row in _documents(db, collection, session, cache)]
    for array in ("businessEntities", "fundingSources", "projectFamilies"):
        for record in state[array]:
            record.setdefault("description", "")
    families = {row["id"]: row for row in state["projectFamilies"]}
    entities = {row["id"]: row["name"] for row in state["businessEntities"]}
    funding = {row["id"]: row["name"] for row in state["fundingSources"]}
    for record in state["projects"]:
        try:
            family = families[record["projectFamilyId"]]
            record.update(businessEntityId=family["businessEntityId"], fundingSourceId=family["fundingSourceId"],
                          entity=entities[family["businessEntityId"]], funding=funding[family["fundingSourceId"]])
        except KeyError as error:
            raise StorageIntegrityError("A stored project has an incomplete family reference.") from error
        for field in ("key", "scpm", "platform", "parentId", "summary"):
            record.setdefault(field, "")
        record.setdefault("leadTimes", {})
        for identifier in record.get("asicIds", []):
            record["leadTimes"].setdefault(identifier, record.get("leadDays") or 0)
    for record in state["asics"]:
        record.setdefault("parts", [])
        record.setdefault("priceHistory", [])
        record.setdefault("price", None)
        for part in record["parts"]:
            for field in ("cpn", "plid", "assembly", "subtype"):
                part.setdefault(field, "")
        for field in ("marketing", "description"):
            record.setdefault(field, "")
        if record["parts"]:
            unique = lambda field: list(dict.fromkeys(part[field] for part in record["parts"] if part.get(field)))
            record.update(mpns=unique("mpn"), cpns=unique("cpn"), plid=", ".join(unique("plid")),
                          assembly=" | ".join(unique("assembly")), subtype=" | ".join(unique("subtype")))
        else:
            for field in ("mpns", "cpns"):
                record.setdefault(field, [])
            for field in ("plid", "assembly", "subtype"):
                record.setdefault(field, "")
    for record in state["events"]:
        for field in ("projectId", "eta", "requestId"):
            record.setdefault(field, "")
    lines = _documents(db, "forecast_line", session, cache)
    state["forecastVersions"] = []
    for row in _documents(db, "forecast_version", session, cache):
        record = _copy(row["record"])
        record.setdefault("note", "")
        record["lines"] = [_copy(line["record"]) for line in lines if line["forecast_version_id"] == row["_id"]]
        state["forecastVersions"].append(record)
    chunks = _documents(db, "snapshot_chunk", session, cache)
    state["snapshots"] = []
    for row in _documents(db, "recovery_snapshot", session, cache):
        raw = _decoded_chunks(chunks, "snapshot_id", row["_id"], row["chunk_count"], row["sha256"])
        try:
            data = json.loads(raw)
        except ValueError as error:
            raise StorageIntegrityError("Stored recovery history is not valid JSON.") from error
        state["snapshots"].append(dict(id=row["_id"], date=row["date"], label=row["label"], data=data))
    chunks = _documents(db, "audit_chunk", session, cache)
    state["audit"] = []
    for row in _documents(db, "audit_entry", session, cache):
        record = _copy(row["record"])
        if row["detail_chunk_count"]:
            record["detail"] = _decoded_chunks(chunks, "audit_id", row["_id"], row["detail_chunk_count"], row["detail_sha256"])
        elif hashlib.sha256(record["detail"].encode("utf-8")).hexdigest() != row["detail_sha256"]:
            raise StorageIntegrityError("Stored audit history failed its integrity check.")
        state["audit"].append(record)
    return {"revision": meta["revision"], "state": state}


def get_workspace(db, *, session=None, lock=False):
    """Read one coherent revision. lock is retained for old callers' compatibility."""
    if session is None:
        return run_transaction(db, lambda active: _read_workspace(db, active))
    _check_session(session)
    return _read_workspace(db, session)


def _check_document(collection, document):
    try:
        size = len(BSON.encode(document))
    except (InvalidDocument, OverflowError, UnicodeError) as error:
        raise StorageValidationError("A workspace record contains a value that cannot be stored.") from error
    if size > MAX_DOCUMENT_BYTES:
        raise StorageValidationError("A single workspace record exceeds MongoDB's 16 MiB document limit.")


def _chunks(identifier, parent_field, data):
    return [{"_id": f"{identifier}:{index}", parent_field: identifier, "position": index,
             "data": data[start:start + CHUNK_BYTES]}
            for index, start in enumerate(range(0, len(data), CHUNK_BYTES))]


def _ordinary_documents(state):
    result = {collection: [] for collection in ORDINARY_COLLECTIONS}
    for array, collection in ENTITY_COLLECTIONS.items():
        for index, value in enumerate(state[array]):
            record = _copy(value)
            if array == "projects":
                for field in ("businessEntityId", "fundingSourceId", "entity", "funding"):
                    record.pop(field, None)
            result[collection].append(dict(_id=value["id"], position=index, record=record))
    for index, value in enumerate(state["forecastVersions"]):
        record = _copy({key: item for key, item in value.items() if key != "lines"})
        result["forecast_version"].append(dict(_id=value["id"], position=index, record=record))
        for position, line in enumerate(value.get("lines", [])):
            result["forecast_line"].append(dict(_id=f"{value['id']}:{position}", forecast_version_id=value["id"],
                                                position=position, record=_copy(line)))
    for index, value in enumerate(state["snapshots"]):
        data = json.dumps(value["data"], ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        chunks = _chunks(value["id"], "snapshot_id", data)
        result["snapshot_chunk"].extend(chunks)
        result["recovery_snapshot"].append(dict(_id=value["id"], position=index, date=value["date"], label=value["label"],
                                                 chunk_count=len(chunks), sha256=hashlib.sha256(data).hexdigest()))
    return result


def _audit_value(collection, value):
    if value is None or collection not in {"snapshots", "forecastVersions"}:
        return value
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return {"id": value["id"], "name": value.get("name", value.get("label")), "month": value.get("month"),
            "lineCount": len(value.get("lines", [])), "sha256": hashlib.sha256(data.encode()).hexdigest()}


def _changes(before, after):
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


def _audit_document(record, sequence):
    record = _copy(record)
    detail = record["detail"].encode("utf-8")
    chunks = _chunks(record["id"], "audit_id", detail) if len(detail) > CHUNK_BYTES else []
    if chunks:
        record.pop("detail")
    return dict(_id=record["id"], sequence=sequence, workspace_revision=record["revision"], record=record,
                detail_chunk_count=len(chunks), detail_sha256=hashlib.sha256(detail).hexdigest()), chunks


def _synchronize(db, collection, desired, session, cache):
    existing = {row["_id"]: row for row in _documents(db, collection, session, cache)}
    wanted = {row["_id"]: row for row in desired}
    writes = [ReplaceOne({"_id": key}, value, upsert=True) for key, value in wanted.items() if existing.get(key) != value]
    if writes:
        db[collection].bulk_write(writes, ordered=True, session=session)
    removed = list(existing.keys() - wanted.keys())
    for start in range(0, len(removed), 500):
        db[collection].delete_many({"_id": {"$in": removed[start:start + 500]}}, session=session)


def _write_workspace(db, state, *, expected_revision, actor, reason, operation, session):
    cache = {}
    current = _read_workspace(db, session, cache)
    if current["revision"] != expected_revision:
        raise RevisionConflict(current["revision"])
    state = _copy(state)
    for collection in STATE_ARRAYS:
        state.setdefault(collection, [])
    ordinary = _ordinary_documents(state)
    meta = db[SCHEMA_COLLECTION].find_one({"_id": SCHEMA_DOCUMENT_ID}, session=session)
    sequence = meta["audit_sequence"]
    audit, chunks = [], []
    if operation == "import":
        known = {row["_id"] for row in cache["audit_entry"]}
        for entry in state["audit"]:
            if entry["id"] not in known:
                sequence += 1
                record = dict(id=entry["id"], date=entry["date"], action=entry["action"], detail=entry["detail"],
                              actor=None, actorName=None, actorRole=None, legacy=True, revision=None)
                document, pieces = _audit_document(record, sequence)
                audit.append(document)
                chunks.extend(pieces)
                known.add(entry["id"])
    changes = _changes(current["state"], state)
    revision = expected_revision + 1
    detail = dict(revision=revision, operation=operation, changeCount=len(changes), changes=changes)
    if len(changes) == 1:
        detail.update(before=changes[0]["before"], after=changes[0]["after"])
    record = dict(id="server-" + str(uuid.uuid4()), date=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                  action=((reason or "").strip() or "Update workspace")[:200],
                  detail=json.dumps(detail, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
                  actor=actor["subject"], actorName=actor.get("display_name"), actorRole=actor.get("role"),
                  legacy=False, revision=revision)
    document, pieces = _audit_document(record, sequence + 1)
    audit.append(document)
    chunks.extend(pieces)
    extra = {key: value for key, value in state.items() if key not in set(STATE_ARRAYS) | {"version", "storageNotice"}}
    extra.setdefault("pendingRequests", [])
    next_meta = dict(_id=SCHEMA_DOCUMENT_ID, schema_version=SCHEMA_VERSION, revision=revision,
                     version=2, audit_sequence=sequence + 1, extra=extra)
    # Complete BSON serialization/size checks before the first write. The entire
    # operation also rolls back for any later server-side validation failure.
    for collection, documents in {**ordinary, "audit_entry": audit, "audit_chunk": chunks, SCHEMA_COLLECTION: [next_meta]}.items():
        for value in documents:
            _check_document(collection, value)
    updated = db[SCHEMA_COLLECTION].update_one({"_id": SCHEMA_DOCUMENT_ID, "revision": expected_revision},
        {"$set": {key: value for key, value in next_meta.items() if key != "_id"}}, session=session)
    if updated.matched_count != 1:
        latest = db[SCHEMA_COLLECTION].find_one({"_id": SCHEMA_DOCUMENT_ID}, session=session)
        raise RevisionConflict(latest["revision"])
    for collection, desired in ordinary.items():
        _synchronize(db, collection, desired, session, cache)
    if chunks:
        db.audit_chunk.insert_many(chunks, ordered=True, session=session)
    db.audit_entry.insert_many(audit, ordered=True, session=session)
    return _read_workspace(db, session)


def write_workspace(db, state, *, expected_revision, actor, reason, operation="edit", session=None):
    callback = lambda active: _write_workspace(db, state, expected_revision=expected_revision, actor=actor,
                                              reason=reason, operation=operation, session=active)
    if session is None:
        return run_transaction(db, callback)
    _check_session(session)
    return callback(session)
