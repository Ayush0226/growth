from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from pydantic import SecretStr
from test_automations import Store

from app import access, security
from app.config import get_settings
from app.routes import access as routes


@pytest.fixture
def client(monkeypatch):
    store = Store({})
    monkeypatch.setattr(access, "db", lambda: store)
    monkeypatch.setattr(routes, "db", lambda: store)
    app = FastAPI()
    app.include_router(routes.router)

    @app.get("/protected")
    def protected(user=Depends(security.current_user)):
        return {"user": user.id}

    app.dependency_overrides[security.authenticated_user] = lambda: security.CurrentUser(
        "new-user", None
    )
    config = SimpleNamespace(pilot_access_code=SecretStr("isolated-test-code"))
    app.dependency_overrides[get_settings] = lambda: config
    store.rpc = lambda *args: SimpleNamespace(execute=lambda: SimpleNamespace(data=True))
    return TestClient(app), store, config


def test_new_user_is_blocked_until_code_is_redeemed(client):
    http, store, _config = client
    assert http.get("/protected").status_code == 403
    assert http.get("/api/access").json()["approved"] is False
    assert http.post("/api/access/redeem", json={"code": "wrong"}).status_code == 403
    assert not store.data["pilot_access_grants"]
    assert http.post("/api/access/redeem", json={"code": "isolated-test-code"}).json()["approved"]
    assert http.get("/protected").status_code == 200
    # Approval belongs to the authenticated account and survives subsequent sessions.
    assert http.get("/api/access").json()["approved"]
    assert store.data["pilot_access_grants"][0]["user_id"] == "new-user"
    assert "code" not in store.data["pilot_access_grants"][0]


def test_user_cannot_supply_someone_elses_approval(client):
    http, store, _config = client
    store.data["pilot_access_grants"] = [{"user_id": "someone-else", "revoked_at": None}]
    assert http.get("/protected").status_code == 403
    assert (
        http.post(
            "/api/access/redeem", json={"code": "wrong", "user_id": "someone-else"}
        ).status_code
        == 403
    )


def test_revoked_access_cannot_be_restored_by_shared_code(client):
    http, store, _config = client
    store.data["pilot_access_grants"] = [{"user_id": "new-user", "revoked_at": "2026-01-01"}]
    assert http.get("/api/access").json()["revoked"]
    assert http.post("/api/access/redeem", json={"code": "isolated-test-code"}).status_code == 403
    assert http.get("/protected").status_code == 403


def test_attempt_budget_and_missing_server_code_fail_closed(client):
    http, store, config = client
    store.rpc = lambda *args: SimpleNamespace(execute=lambda: SimpleNamespace(data=False))
    response = http.post("/api/access/redeem", json={"code": "isolated-test-code"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "900"
    config.pilot_access_code = None
    assert http.get("/api/access").json()["setup_ready"] is False
    assert http.post("/api/access/redeem", json={"code": "isolated-test-code"}).status_code == 503


def test_migration_fallback_preserves_only_existing_workspaces(monkeypatch):
    class Missing(Store):
        def table(self, name):
            if name == "pilot_access_grants":
                raise APIError(
                    {"code": "PGRST205", "message": "missing", "details": "", "hint": ""}
                )
            return super().table(name)

    store = Missing({"workspace_members": [{"id": "member", "user_id": "old-user"}]})
    monkeypatch.setattr(access, "db", lambda: store)
    assert access.access_state("old-user") == (True, False, False)
    assert access.access_state("new-user") == (False, False, False)


def test_access_state_does_not_swallow_database_failures(monkeypatch):
    def failure():
        raise APIError({"code": "42501", "message": "denied", "details": "", "hint": ""})

    monkeypatch.setattr(access, "db", failure)
    with pytest.raises(APIError):
        access.access_state("user")


def test_access_code_is_redacted_in_model_representation():
    assert "isolated-test-code" not in repr(routes.AccessInput(code="isolated-test-code"))


def test_absent_authentication_cannot_read_or_redeem_access(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    http = TestClient(app)
    assert http.get("/api/access").status_code == 401
    assert http.post("/api/access/redeem", json={"code": "test"}).status_code == 401
