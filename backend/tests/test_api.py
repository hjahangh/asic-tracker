from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from app.auth import Actor, actor_for_request
from app.config import Settings
from app.domain import capture_forecast_lines, empty_state
from app.main import create_app
from app.models import Base
from sqlalchemy import text


@pytest.fixture
def api():
    app = create_app(Settings(database_url="sqlite+pysqlite://", auth_mode="development", frontend_dir=None, require_migrations=False))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        yield app, client


def put(client, state, revision=None, **extra):
    if revision is None:
        revision = client.get("/api/workspace").json()["revision"]
    return client.put("/api/workspace", json={"revision": revision, "state": state, "reason": "Test transaction", **extra})


def test_empty_shared_workspace_and_health(api):
    app, client = api
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    result = client.get("/api/workspace")
    assert result.status_code == 200
    assert result.json()["state"]["projects"] == []
    assert result.headers["etag"] == '"0"'
    assert client.get("/api/me").json()["auth_mode"] == "development"


def test_relational_round_trip_and_server_audit(api, workspace):
    app, client = api
    response = put(client, workspace)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["revision"] == 1
    project = result["state"]["projects"][0]
    assert project["projectFamilyId"] == "family"
    assert project["businessEntityId"] == "be"
    assert result["state"]["asics"][0]["parts"][0]["cpn"] == "CPN-A"
    assert result["state"]["asics"][0]["priceHistory"][0]["price"] == 12.25
    assert result["state"]["audit"]
    assert client.get("/api/workspace").json() == result


def test_stale_client_cannot_overwrite_newer_changes(api, workspace):
    app, client = api
    assert put(client, workspace, revision=0).status_code == 200
    stale = deepcopy(workspace)
    stale["projects"][0]["name"] = "Stale overwrite"
    rejected = put(client, stale, revision=0)
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "revision_conflict"
    latest = client.get("/api/workspace").json()
    assert latest["revision"] == 1
    assert latest["state"]["projects"][0]["name"] == "Project"


def test_invalid_transaction_rolls_back_without_partial_data(api, workspace):
    app, client = api
    assert put(client, workspace).status_code == 200
    bad = deepcopy(workspace)
    bad["asics"][0]["name"] = "Must not save"
    bad["projects"][0]["projectFamilyId"] = "missing"
    assert put(client, bad).status_code == 422
    latest = client.get("/api/workspace").json()
    assert latest["revision"] == 1
    assert latest["state"]["asics"][0]["name"] == "ASIC A"


def test_authoritative_availability_includes_revision_and_distinguishes_coverage(api, workspace, event):
    app, client = api
    workspace["events"] = [event("s", "expected_ship", 10, "2026-11-01", supplyStatus="incoming"), event("r", "request", 10, "2026-11-24")]
    assert put(client, workspace).status_code == 200
    result = client.get("/api/availability?as_of=2026-10-29")
    assert result.status_code == 200
    data = result.json()
    assert data["revision"] == 1 and data["asOf"] == "2026-10-29"
    assert data["requests"][0]["allocatedQty"] == 0
    assert data["requests"][0]["availableByShipBy"] == 10
    assert client.get("/api/availability?as_of=2026-02-30").status_code == 422


def test_viewer_can_read_but_cannot_write(api, workspace):
    app, client = api
    app.dependency_overrides[actor_for_request] = lambda: Actor("viewer", "Viewer", "viewer", "proxy")
    assert client.get("/api/workspace").status_code == 200
    assert put(client, workspace).status_code == 403
    assert client.get("/api/workspace").json()["revision"] == 0


def test_editor_cannot_change_family_or_disguise_deletion_as_edit(api, workspace):
    app, client = api
    assert put(client, workspace).status_code == 200
    app.dependency_overrides[actor_for_request] = lambda: Actor("editor", "Editor", "editor", "proxy")
    changed = deepcopy(workspace)
    changed["projectFamilies"][0]["name"] = "Different family"
    assert put(client, changed).status_code == 403
    assert put(client, empty_state(), operation="edit").status_code == 403
    assert put(client, workspace, operation="restore").status_code == 403
    changed = deepcopy(workspace)
    changed["projects"][0]["name"] = "Allowed project edit"
    assert put(client, changed).status_code == 200


def test_caller_cannot_forge_audit_actor_or_erase_server_audit(api, workspace):
    app, client = api
    first = put(client, workspace).json()
    audit_ids = {entry["id"] for entry in first["state"]["audit"]}
    changed = deepcopy(first["state"])
    changed["audit"] = [{"id": "forged", "date": "2026-10-01T12:00:00Z", "action": "Pretend admin", "detail": "forged", "actor": "someone-else"}]
    changed["projects"][0]["name"] = "Audited edit"
    saved = put(client, changed).json()
    assert audit_ids <= {entry["id"] for entry in saved["state"]["audit"]}
    assert "forged" not in {entry["id"] for entry in saved["state"]["audit"]}


def test_cross_origin_writes_and_oversized_bodies_rejected(api):
    app, client = api
    response = client.put("/api/workspace", json={"revision": 0, "state": empty_state()}, headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403
    response = client.put("/api/workspace", content=b"x" * (12 * 1024 * 1024 + 1), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert client.get("/api/workspace").json()["revision"] == 0


@pytest.mark.parametrize("origin", ["http://[", "https://[::1"])
def test_malformed_origin_is_rejected_without_server_error(api, origin):
    app, client = api
    response = client.put("/api/workspace", json={"revision": 0, "state": empty_state()}, headers={"Origin": origin})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "cross_origin_write"
    assert client.get("/api/workspace").json()["revision"] == 0


@pytest.mark.parametrize("invalid", [10**500, "NUL\x00name", "invalid\ud800name"])
def test_unstorable_client_values_return_validation_error_and_preserve_state(api, workspace, invalid):
    app, client = api
    first = put(client, workspace).json()
    changed = deepcopy(first["state"])
    changed["asics"][0]["price" if isinstance(invalid, int) else "name"] = invalid
    # ensure_ascii exposes the same escaped-Unicode JSON a browser/API client can
    # send, instead of failing inside this test client's own UTF-8 serializer.
    response = client.put("/api/workspace", content=json.dumps({"revision": first["revision"], "state": changed}).encode(), headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_workspace"
    assert client.get("/api/workspace").json() == first


@pytest.mark.parametrize("reason", ["   ", "\t\n", "bad\x00reason", "bad\ud800reason"])
def test_invalid_operation_reason_cannot_poison_the_server_audit(api, workspace, reason):
    app, client = api
    response = client.put("/api/workspace", content=json.dumps({"revision": 0, "state": workspace, "reason": reason}).encode(), headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert client.get("/api/workspace").json()["revision"] == 0


def test_operation_reason_is_trimmed_before_length_and_audit_storage(api, workspace):
    app, client = api
    response = client.put("/api/workspace", json={"revision": 0, "state": workspace, "reason": " " * 170 + "A valid change"})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["state"]["audit"][-1]["action"] == "A valid change"
    # A malformed server-generated audit action previously prevented every
    # subsequent ordinary save; explicitly verify this workspace remains usable.
    assert put(client, saved["state"], revision=saved["revision"]).status_code == 200


@pytest.mark.parametrize("invalid", [{"revision": float("nan")}, {"revision": float("inf")}, {"unexpected": {"secret": "bad\ud800text"}}, {"bad\ud800key": "extra"}])
def test_invalid_envelope_values_cannot_break_validation_error_serialization(api, invalid):
    app, client = api
    body = {"revision": 0, "state": empty_state(), **invalid}
    response = client.put("/api/workspace", content=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert errors and all("msg" in error and "loc" in error and "input" not in error for error in errors)
    assert client.get("/api/workspace").json()["revision"] == 0


def test_chunked_body_limit_is_enforced_without_content_length():
    app = create_app(Settings(database_url="sqlite+pysqlite://", auth_mode="development", frontend_dir=None, require_migrations=False, max_body_bytes=1024))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        result = client.put("/api/workspace", content=iter([b"x" * 800, b"x" * 800]), headers={"Content-Type": "application/json"})
        assert result.status_code == 413


def test_proxy_authentication_requires_gateway_secret_and_assigned_group():
    app = create_app(Settings(database_url="sqlite+pysqlite://", auth_mode="proxy", proxy_shared_secret="s" * 32, frontend_dir=None, require_migrations=False))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        assert client.get("/api/me").status_code == 401
        assert client.get("/api/me", headers={"X-Authenticated-User": "forged", "X-Authenticated-Groups": "asic-tracker-admins"}).status_code == 401
        trusted = {"X-Proxy-Token": "s" * 32, "X-Authenticated-User": "authenticated-subject"}
        assert client.get("/api/me", headers=trusted).status_code == 403
        result = client.get("/api/me", headers={**trusted, "X-Authenticated-Groups": '["asic-tracker-viewers", "asic-tracker-editors"]'})
        assert result.status_code == 200
        assert result.json()["role"] == "editor"
        assert client.get("/health/live").status_code == 200


def test_proxy_json_group_claim_accepts_whitespace_and_rejects_parser_limits():
    app = create_app(Settings(database_url="sqlite+pysqlite://", auth_mode="proxy", proxy_shared_secret="s" * 32, frontend_dir=None, require_migrations=False))
    Base.metadata.create_all(app.state.engine)
    trusted = {"X-Proxy-Token": "s" * 32, "X-Authenticated-User": "authenticated-subject"}
    with TestClient(app) as client:
        result = client.get("/api/me", headers={**trusted, "X-Authenticated-Groups": '  ["asic-tracker-viewers"] '})
        assert result.status_code == 200 and result.json()["role"] == "viewer"
        for malformed in ("[" + "1" * 5000 + "]", "[" * 4000 + "]" * 4000):
            result = client.get("/api/me", headers={**trusted, "X-Authenticated-Groups": malformed})
            assert result.status_code == 403
            assert result.json()["detail"]["code"] == "invalid_groups"


def test_missing_proxy_secret_fails_closed_at_startup():
    app = create_app(Settings(database_url="sqlite+pysqlite://", auth_mode="proxy", frontend_dir=None, require_migrations=False))
    with pytest.raises(ValueError, match="PROXY_SHARED_SECRET"):
        with TestClient(app):
            pass


def test_security_headers_and_optional_docs_have_no_external_assets(api):
    app, client = api
    response = client.get("/api/me")
    assert response.headers["x-frame-options"] == "DENY"
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/docs").status_code == 404


def test_forecast_and_recovery_history_are_verified_after_relational_round_trip(api, workspace, event):
    app, client = api
    workspace["events"] = [event("r", "request", 5, "2026-11-01")]
    first = put(client, workspace).json()
    captured = deepcopy(first["state"])
    captured["forecastVersions"] = [{"id": "v", "month": "2026-10", "name": "October", "createdAt": "2026-10-29T12:00:00Z", "note": "", "lines": capture_forecast_lines(captured)}]
    response = put(client, captured)
    assert response.status_code == 200, response.text
    captured = response.json()["state"]
    saved = deepcopy(captured)
    saved.pop("snapshots")
    changed = deepcopy(captured)
    changed["snapshots"] = [{"id": "s", "date": "2026-10-29T12:00:00Z", "label": "Before rename", "data": saved}]
    changed["projects"][0]["name"] = "Renamed project"
    response = put(client, changed)
    assert response.status_code == 200, response.text
    committed = response.json()
    forged = deepcopy(committed["state"])
    forged["forecastVersions"][0]["lines"][0]["qty"] = 999
    assert put(client, forged).status_code == 422
    forged = deepcopy(committed["state"])
    forged["snapshots"][0]["label"] = "Edited frozen history"
    assert put(client, forged).status_code == 422
    assert client.get("/api/workspace").json() == committed


def test_readiness_rejects_stale_migration_revision():
    app = create_app(Settings(database_url="sqlite+pysqlite://", auth_mode="development", frontend_dir=None))
    Base.metadata.create_all(app.state.engine)
    with app.state.engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('stale-revision')"))
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 503
        with app.state.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = '20261029_0001'"))
        assert client.get("/health/ready").status_code == 200


@pytest.mark.parametrize("missing", ["directory", "index", "script", "stylesheet"])
def test_missing_configured_frontend_fails_startup(tmp_path, missing):
    frontend = tmp_path / "frontend"
    if missing != "directory":
        frontend.mkdir()
    if missing not in {"directory", "index"}:
        (frontend / "index.html").write_text('<script src="app.js"></script><link rel="stylesheet" href="styles.css">')
        if missing != "script":
            (frontend / "app.js").write_text("/* app */")
        if missing != "stylesheet":
            (frontend / "styles.css").write_text("body {}")
    app = create_app(Settings(database_url="sqlite+pysqlite://", auth_mode="development", frontend_dir=frontend, require_migrations=False))
    with pytest.raises(ValueError, match="FRONTEND_DIR"):
        with TestClient(app):
            pass


def test_complete_frontend_and_api_only_configuration_still_start(tmp_path):
    (tmp_path / "index.html").write_text('<script src="app.js?v=1"></script><link rel="stylesheet" href="styles.css">')
    (tmp_path / "app.js").write_text("/* app */")
    (tmp_path / "styles.css").write_text("body {}")
    app = create_app(Settings(database_url="sqlite+pysqlite://", auth_mode="development", frontend_dir=tmp_path, require_migrations=False))
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/app.js?v=1").status_code == 200
        assert client.get("/health/live").status_code == 200
    app = create_app(Settings(database_url="sqlite+pysqlite://", auth_mode="development", frontend_dir=None, require_migrations=False))
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/").status_code == 404
