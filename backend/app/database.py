"""Versioned MongoDB schema/bootstrap and transaction settings.

Business graph/name uniqueness is validated by the domain layer within the
workspace revision transaction. MongoDB validates document shapes and immutable
identifiers, with unique indexes for physical IDs and ordered history/chunks.
"""
from __future__ import annotations

from copy import deepcopy

from pymongo import ASCENDING, MongoClient, timeout
from pymongo.errors import CollectionInvalid, DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.read_preferences import ReadPreference
from pymongo.write_concern import WriteConcern

SCHEMA_VERSION = "20261030_0001"
SCHEMA_COLLECTION = "workspace_meta"
SCHEMA_DOCUMENT_ID = "workspace"
CHUNK_BYTES = 512 * 1024
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024 - 16 * 1024
READ_CONCERN = ReadConcern("snapshot")
WRITE_CONCERN = WriteConcern("majority", wtimeout=15000)

ENTITY_COLLECTIONS = {
    "businessEntities": "business_entity", "fundingSources": "funding_source",
    "projectFamilies": "project_family", "projects": "project", "asics": "asic",
    "events": "planning_event",
}
ORDINARY_COLLECTIONS = (*ENTITY_COLLECTIONS.values(), "forecast_version", "forecast_line",
                        "recovery_snapshot", "snapshot_chunk")
APPEND_ONLY_COLLECTIONS = ("audit_entry", "audit_chunk")
COLLECTIONS = (*ORDINARY_COLLECTIONS, SCHEMA_COLLECTION, *APPEND_ONLY_COLLECTIONS)

STRING = {"bsonType": "string"}
NONBLANK = {"bsonType": "string", "minLength": 1}
INTEGER = {"bsonType": ["int", "long"], "minimum": 0}
QUANTITY = {**INTEGER, "maximum": 9_007_199_254_740_991}
TYPES = ["expected_ship", "request", "expected_fulfilment", "actual_ship", "actual_fulfilment"]


def create_client(uri: str) -> MongoClient:
    return MongoClient(uri, appname="asic-tracker", serverSelectionTimeoutMS=5000,
                       connectTimeoutMS=5000, timeoutMS=30000, retryWrites=True)


def run_transaction(db, callback):
    with timeout(15), db.client.start_session() as session:
        return session.with_transaction(callback, read_concern=READ_CONCERN,
                                        write_concern=WRITE_CONCERN,
                                        read_preference=ReadPreference.PRIMARY,
                                        max_commit_time_ms=15000)


def _schema(required, properties, *, extra=False):
    return {"bsonType": "object", "required": list(required),
            "additionalProperties": extra, "properties": properties}


def _record(required, properties=None):
    return _schema(required, {"id": NONBLANK, **(properties or {})}, extra=True)


def _entity_validator(record):
    return {"$and": [{"$jsonSchema": _schema(("_id", "position", "record"),
                {"_id": NONBLANK, "position": INTEGER, "record": record})},
                {"$expr": {"$eq": ["$_id", "$record.id"]}}]}


def _chunk_validator(parent):
    return {"$jsonSchema": _schema(("_id", parent, "position", "data"),
        {"_id": NONBLANK, parent: NONBLANK, "position": INTEGER, "data": {"bsonType": "binData"}})}


def validators():
    result = {}
    for collection in ("business_entity", "funding_source"):
        result[collection] = _entity_validator(_record(("id", "name"), {"name": NONBLANK}))
    result["project_family"] = _entity_validator(_record(("id", "name", "businessEntityId", "fundingSourceId"),
        {"name": NONBLANK, "businessEntityId": NONBLANK, "fundingSourceId": NONBLANK}))
    result["project"] = _entity_validator(_record(("id", "name", "manager", "projectFamilyId", "asicIds"),
        {"name": NONBLANK, "manager": NONBLANK, "projectFamilyId": NONBLANK,
         "asicIds": {"bsonType": "array", "items": NONBLANK}, "leadTimes": {"bsonType": "object"}}))
    result["asic"] = _entity_validator(_record(("id", "name", "owner"),
        {"name": NONBLANK, "owner": NONBLANK, "parts": {"bsonType": "array"}, "priceHistory": {"bsonType": "array"}}))
    result["planning_event"] = _entity_validator(_record(("id", "type", "asicId", "qty", "date"),
        {"type": {"enum": TYPES}, "asicId": NONBLANK, "qty": {**QUANTITY, "minimum": 1},
         "date": {"bsonType": "string", "pattern": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}}))
    result["forecast_version"] = _entity_validator(_record(("id", "month", "name", "createdAt"),
        {"month": NONBLANK, "name": NONBLANK, "createdAt": NONBLANK}))
    result["forecast_line"] = {"$jsonSchema": _schema(("_id", "forecast_version_id", "position", "record"),
        {"_id": NONBLANK, "forecast_version_id": NONBLANK, "position": INTEGER,
         "record": _schema(("asicId", "asicName", "projectId", "projectName", "type", "month", "qty"),
             {"asicId": NONBLANK, "asicName": NONBLANK, "projectId": STRING, "projectName": NONBLANK,
              "type": {"enum": TYPES}, "month": NONBLANK, "qty": QUANTITY}, extra=True)})}
    result["recovery_snapshot"] = {"$jsonSchema": _schema(("_id", "position", "date", "label", "chunk_count", "sha256"),
        {"_id": NONBLANK, "position": INTEGER, "date": NONBLANK, "label": NONBLANK,
         "chunk_count": {**INTEGER, "minimum": 1}, "sha256": {"bsonType": "string", "pattern": "^[a-f0-9]{64}$"}})}
    result["snapshot_chunk"] = _chunk_validator("snapshot_id")
    result["audit_chunk"] = _chunk_validator("audit_id")
    result["audit_entry"] = {"$and": [{"$jsonSchema": _schema(
        ("_id", "sequence", "workspace_revision", "record", "detail_chunk_count", "detail_sha256"),
        {"_id": NONBLANK, "sequence": {**INTEGER, "minimum": 1},
         "workspace_revision": {"bsonType": ["int", "long", "null"]},
         "record": _record(("id", "date", "action", "actor", "legacy", "revision"),
             {"date": NONBLANK, "action": NONBLANK, "legacy": {"bsonType": "bool"}, "detail": STRING}),
         "detail_chunk_count": INTEGER, "detail_sha256": {"bsonType": "string", "pattern": "^[a-f0-9]{64}$"}})},
        {"$expr": {"$eq": ["$_id", "$record.id"]}},
        {"$or": [{"detail_chunk_count": 0, "record.detail": {"$type": "string"}},
                 {"detail_chunk_count": {"$gt": 0}, "record.detail": {"$exists": False}}]}]}
    result[SCHEMA_COLLECTION] = {"$jsonSchema": _schema(
        ("_id", "schema_version", "revision", "version", "audit_sequence", "extra"),
        {"_id": {"enum": [SCHEMA_DOCUMENT_ID]}, "schema_version": {"enum": [SCHEMA_VERSION]},
         "revision": INTEGER, "version": {"enum": [2]}, "audit_sequence": INTEGER,
         "extra": {"bsonType": "object"}})}
    return deepcopy(result)


INDEXES = {collection: [("position_order", [("position", ASCENDING), ("_id", ASCENDING)], False)]
           for collection in (*ENTITY_COLLECTIONS.values(), "forecast_version", "recovery_snapshot")}
INDEXES.update({
    "planning_event": INDEXES["planning_event"] + [
        ("asic_project_date", [("record.asicId", 1), ("record.projectId", 1), ("record.date", 1)], False)],
    "forecast_version": INDEXES["forecast_version"] + [("version_month", [("record.month", 1)], False)],
    "forecast_line": [("version_position", [("forecast_version_id", 1), ("position", 1)], True)],
    "snapshot_chunk": [("snapshot_position", [("snapshot_id", 1), ("position", 1)], True)],
    "audit_entry": [("audit_sequence", [("sequence", 1)], True),
                    ("workspace_revision", [("workspace_revision", 1)], False)],
    "audit_chunk": [("audit_position", [("audit_id", 1), ("position", 1)], True)],
    SCHEMA_COLLECTION: [],
})


def _topology_ready(db):
    hello = db.client.admin.command("hello")
    return bool((hello.get("setName") or hello.get("msg") == "isdbgrid")
                and hello.get("logicalSessionTimeoutMinutes") is not None)


def check_ready(db):
    try:
        db.command("ping")
        if not _topology_ready(db):
            return {"status": "not_ready", "reason": "transactions_require_replica_set"}
        meta = db[SCHEMA_COLLECTION].find_one({"_id": SCHEMA_DOCUMENT_ID})
        if not meta or meta.get("schema_version") != SCHEMA_VERSION:
            return {"status": "not_ready", "reason": "schema_bootstrap_required"}
        expected = validators()
        actual = {row["name"]: row for row in db.list_collections(filter={"name": {"$in": list(COLLECTIONS)}})}
        for collection in COLLECTIONS:
            options = actual.get(collection, {}).get("options", {})
            if options.get("validator") != expected[collection] or options.get("validationLevel", "strict") != "strict" or options.get("validationAction", "error") != "error":
                return {"status": "not_ready", "reason": "schema_validation_required"}
            indexes = {item["name"]: item for item in db[collection].list_indexes()}
            for name, keys, unique in INDEXES[collection]:
                found = indexes.get(name, {})
                if list(found.get("key", {}).items()) != keys or bool(found.get("unique", False)) != unique:
                    return {"status": "not_ready", "reason": "schema_indexes_required"}
        return {"status": "ready"}
    except PyMongoError:
        return {"status": "not_ready", "reason": "database_or_schema_unavailable"}


def bootstrap_database(db):
    """Idempotent owner-only bootstrap; never populate planning/demo records."""
    if not _topology_ready(db):
        raise ValueError("MongoDB must be a replica set or sharded cluster with transaction support.")
    previous = db[SCHEMA_COLLECTION].find_one({"_id": SCHEMA_DOCUMENT_ID})
    if previous and previous.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("This database has an unsupported schema version; an explicit migration is required.")
    for collection, validator in validators().items():
        try:
            db.create_collection(collection, validator=validator, validationLevel="strict", validationAction="error")
        except CollectionInvalid:
            db.command({"collMod": collection, "validator": validator,
                        "validationLevel": "strict", "validationAction": "error"})
        except PyMongoError as error:
            if getattr(error, "code", None) != 48:
                raise
            db.command({"collMod": collection, "validator": validator,
                        "validationLevel": "strict", "validationAction": "error"})
        for name, keys, unique in INDEXES[collection]:
            db[collection].create_index(keys, name=name, unique=unique)
    values = {"_id": SCHEMA_DOCUMENT_ID, "schema_version": SCHEMA_VERSION, "revision": 0,
              "version": 2, "audit_sequence": 0, "extra": {"pendingRequests": []}}
    try:
        db[SCHEMA_COLLECTION].update_one({"_id": SCHEMA_DOCUMENT_ID}, {"$setOnInsert": values}, upsert=True)
    except DuplicateKeyError:
        # Another owner bootstrap may have won the first-use insert race.
        if not db[SCHEMA_COLLECTION].find_one({"_id": SCHEMA_DOCUMENT_ID}):
            raise
    result = check_ready(db)
    if result["status"] != "ready":
        raise ValueError("MongoDB schema bootstrap verification failed: " + result["reason"])
    return {"status": "ready", "schema_version": SCHEMA_VERSION, "collections": list(COLLECTIONS)}
