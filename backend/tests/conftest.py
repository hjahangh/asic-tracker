from copy import deepcopy

import pytest

from app.domain import empty_state


@pytest.fixture
def workspace():
    state = empty_state()
    state["businessEntities"] = [{"id": "be", "name": "Business", "description": ""}]
    state["fundingSources"] = [{"id": "fund", "name": "Funding", "description": ""}]
    state["projectFamilies"] = [{"id": "family", "name": "Family", "businessEntityId": "be", "fundingSourceId": "fund", "description": ""}]
    state["asics"] = [{"id": "a", "name": "ASIC A", "owner": "Supply owner", "marketing": "", "description": "",
        "price": 12.25, "priceHistory": [{"quarter": "2026-Q1", "price": 12.25}],
        "parts": [{"id": "part", "mpn": "MPN-A", "cpn": "CPN-A", "plid": "PLID", "assembly": "Assembly", "subtype": "Switch"}],
        "mpns": ["MPN-A"], "cpns": ["CPN-A"], "plid": "PLID", "assembly": "Assembly", "subtype": "Switch"}]
    state["projects"] = [{"id": "p", "name": "Project", "projectFamilyId": "family", "manager": "EPM", "key": "",
        "parentId": "", "scpm": "", "platform": "Platform", "phase": "", "summary": "", "asicIds": ["a"], "leadTimes": {"a": 7}, "leadDays": 7}]
    return deepcopy(state)


@pytest.fixture
def event():
    def make(identifier, kind, quantity, day, **extra):
        record = {"id": identifier, "type": kind, "qty": quantity, "date": day, "asicId": "a", "projectId": "" if kind == "expected_ship" else "p", "note": "", "eta": ""}
        if kind == "request":
            record["shipDays"] = 0
        if kind == "actual_ship":
            record["eta"] = day
        record.update(extra)
        return record
    return make


@pytest.fixture
def mongo_database():
    """Real replica-set MongoDB only; each test owns a disposable database."""
    import os
    import uuid
    from app.database import bootstrap_database, create_client

    uri = os.environ.get("TEST_MONGODB_URI", "")
    if not uri:
        pytest.skip("Requires a disposable replica-set TEST_MONGODB_URI")
    client = create_client(uri)
    database = client["tracker_test_" + uuid.uuid4().hex]
    try:
        bootstrap_database(database)
        yield database
    finally:
        client.drop_database(database.name)
        client.close()
