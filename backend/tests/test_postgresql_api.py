"""HTTP integration against real Alembic migrations in a disposable PG schema."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from pathlib import Path
from threading import Barrier
import uuid

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.domain import capture_forecast_lines
from app.main import create_app


@pytest.fixture
def migrated_api(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        pytest.skip("Requires disposable PostgreSQL TEST_DATABASE_URL")
    raw = create_engine(database_url)
    schema = "tracker_api_" + uuid.uuid4().hex
    with raw.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = make_url(database_url).update_query_dict({"options": "-csearch_path=" + schema}).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", scoped_url)
    monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    app = None
    try:
        command.upgrade(config, "head")
        app = create_app(Settings(database_url=scoped_url, auth_mode="proxy", proxy_shared_secret="integration-secret-" + "s" * 32, frontend_dir=None))
        with TestClient(app) as client:
            yield app, client
    finally:
        if app is not None:
            app.state.engine.dispose()
        with raw.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        raw.dispose()


def headers(role="admin", subject="integration-reviewer"):
    return {"X-Proxy-Token": "integration-secret-" + "s" * 32, "X-Authenticated-User": subject,
        "X-Authenticated-Groups": "asic-tracker-" + role + "s"}


@pytest.mark.postgres
def test_migrated_postgresql_http_workflow_retains_frozen_history(migrated_api, workspace, event):
    app, client = migrated_api
    assert client.get("/health/ready").status_code == 200
    assert client.get("/api/workspace").status_code == 401
    workspace["events"] = [event("s", "expected_ship", 30, "2026-10-01", supplyStatus="available"),
        event("r", "request", 20, "2026-11-01", createdAt="2026-10-29", requestId="request-alias"),
        event("a1", "expected_fulfilment", 15, "2026-11-01", requestId="r", createdAt="2026-10-29", availableShipDate="2026-10-29")]
    response = client.put("/api/workspace", headers=headers(), json={"revision": 0, "state": workspace, "reason": "Set up shared plan"})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["state"]["events"][2]["createdAt"] == "2026-10-29"
    availability = client.get("/api/availability?as_of=2026-10-29", headers=headers("viewer")).json()
    assert availability["revision"] == 1
    assert availability["requests"][0]["allocatedQty"] == 15
    assert availability["inventory"][0]["onHandQty"] == 30
    changed = deepcopy(saved["state"])
    changed["forecastVersions"] = [{"id": "v", "month": "2026-10", "name": "October", "createdAt": "2026-10-29", "note": "", "lines": capture_forecast_lines(changed)}]
    response = client.put("/api/workspace", headers=headers("editor"), json={"revision": 1, "state": changed, "reason": "Capture forecast"})
    assert response.status_code == 200, response.text
    saved = response.json()
    frozen = deepcopy(saved["state"]["forecastVersions"])
    changed = deepcopy(saved["state"])
    changed["projects"][0]["name"] = "Current renamed project"
    previous = deepcopy(saved["state"])
    previous.pop("snapshots")
    changed["snapshots"] = [{"id": "snapshot", "date": "2026-10-29", "label": "Before rename", "data": previous}]
    response = client.put("/api/workspace", headers=headers("editor"), json={"revision": 2, "state": changed, "reason": "Rename project"})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["state"]["forecastVersions"] == frozen
    assert saved["state"]["snapshots"][0]["data"]["projects"][0]["name"] == "Project"
    assert saved["state"]["audit"][-1]["actor"] == "integration-reviewer"
    forged = deepcopy(saved["state"])
    forged["forecastVersions"][0]["lines"][0]["qty"] = 999
    rejected = client.put("/api/workspace", headers=headers("editor"), json={"revision": 3, "state": forged})
    assert rejected.status_code == 422
    assert client.get("/api/workspace", headers=headers()).json() == saved


@pytest.mark.postgres
def test_concurrent_http_writers_receive_conflict_without_losing_winner(migrated_api, workspace):
    app, client = migrated_api
    response = client.put("/api/workspace", headers=headers(), json={"revision": 0, "state": workspace})
    assert response.status_code == 200, response.text
    initial = response.json()["state"]
    barrier = Barrier(2)

    def writer(subject):
        changed = deepcopy(initial)
        changed["projects"][0]["name"] = "Project " + subject
        barrier.wait(timeout=10)
        response = client.put("/api/workspace", headers=headers("editor", subject), json={"revision": 1, "state": changed, "reason": "Concurrent project edit"})
        return subject, response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(writer, ["writer-a", "writer-b"]))
    assert sorted(result[1] for result in results) == [200, 409]
    winner = next(result[0] for result in results if result[1] == 200)
    conflict = next(result[2] for result in results if result[1] == 409)
    assert conflict["detail"]["code"] == "revision_conflict"
    assert conflict["detail"]["current_revision"] == 2
    final = client.get("/api/workspace", headers=headers()).json()
    assert final["revision"] == 2
    assert final["state"]["projects"][0]["name"] == "Project " + winner
    assert final["state"]["audit"][-1]["actor"] == winner
