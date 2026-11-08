from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.meta import MetaAPIError
from app.read_cache import invalidate
from app.routes import engagement
from app.security import CurrentUser, current_user


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(engagement.router)
    user = CurrentUser("test-user", None)
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace()
    monkeypatch.setattr(engagement, "user_workspace", lambda _id: "route-test-workspace")
    invalidate("route-test-workspace")
    return TestClient(app), user


def test_comments_cursors_names_and_cache_remain_account_scoped(client, monkeypatch):
    http, _user = client
    calls = []
    account = {"connection_id": "connection", "provider_account_id": "own-account"}
    class Provider:
        async def get(self, path, token, **params):
            calls.append(params)
            return {"data": [{"id": "comment", "from": {"username": "customer"}}], "paging": {"next": "https://meta?access_token=secret", "cursors": {"after": "next-page"}}}
    monkeypatch.setattr(engagement, "connected", lambda *args: (Provider(), "test-token", account))
    first = http.get('/api/instagram/media/123/comments?after=cursor')
    assert first.status_code == 200
    assert first.json()["data"][0]["username"] == "customer"
    assert first.json()["paging"]["has_more"]
    assert "secret" not in first.text
    assert calls[0]["after"] == "cursor"
    http.get('/api/instagram/media/123/comments?after=cursor')
    assert len(calls) == 1
    account["provider_account_id"] = "other-account"
    http.get('/api/instagram/media/123/comments?after=cursor')
    assert len(calls) == 2
    http.get('/api/instagram/media/123/comments?after=cursor&refresh=true')
    assert len(calls) == 3


def test_message_history_keeps_text_when_attachment_fields_are_unavailable(client, monkeypatch):
    http, _user = client
    fields = []
    class Provider:
        async def get(self, path, token, **params):
            fields.append(params["fields"])
            assert params["after"] == "older-cursor"
            if "attachments" in params["fields"]:
                raise MetaAPIError("Unsupported optional field")
            return {"data": [{"id": "old", "message": "An older message"}]}
    monkeypatch.setattr(engagement, "connected", lambda *args: (Provider(), "test-token", {"connection_id": "conn", "provider_account_id": "own"}))
    response = http.get('/api/instagram/conversations/thread/messages?after=older-cursor')
    assert response.status_code == 200
    assert response.json()["data"][0]["message"] == "An older message"
    assert response.json()["attachments_unavailable"]
    assert len(fields) == 2


def test_daily_insights_passes_local_date_bounds_and_uses_date_scoped_cache(client, monkeypatch):
    http, _user = client
    calls = []
    class Provider:
        async def get(self, path, token, **params):
            calls.append((path, params))
            return {"data": [{"name": "reach", "total_value": {"value": 4}}]} if path.endswith('/insights') else {"followers_count": 10}
    monkeypatch.setattr(engagement, "connected", lambda *args: (Provider(), "test-token", {"connection_id": "daily", "provider_account_id": "own"}))
    first = http.get('/api/instagram/insights?on=2020-01-02&timezone=Asia/Kolkata')
    assert first.status_code == 200
    assert first.json()['requested_date'] == '2020-01-02'
    assert first.json()['metrics_status'] == 'available'
    params = next(params for path, params in calls if path.endswith('/insights'))
    from datetime import UTC, datetime
    assert params['since'] == int(datetime(2020, 1, 1, 18, 30, tzinfo=UTC).timestamp())
    assert params['until'] - params['since'] == 86400
    before = len(calls)
    http.get('/api/instagram/insights?on=2020-01-02&timezone=Asia/Kolkata')
    assert len(calls) == before
    http.get('/api/instagram/insights?on=2020-01-03&timezone=Asia/Kolkata')
    assert len(calls) == before + 2


def test_future_insights_do_not_fetch_provider_and_invalid_zone_is_rejected(client, monkeypatch):
    http, _user = client
    monkeypatch.setattr(engagement, 'read_connection', lambda *args: (_ for _ in ()).throw(AssertionError('No future provider fetch')))
    response = http.get('/api/instagram/insights?on=2090-01-01&timezone=UTC')
    assert response.status_code == 200 and response.json()['metrics_status'] == 'future'
    assert http.get('/api/instagram/insights?on=2020-01-01&timezone=invalid').status_code == 422
