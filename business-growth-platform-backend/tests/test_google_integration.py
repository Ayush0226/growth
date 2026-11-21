import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.config import get_settings
from app.gbp import jobs, service
from app.gbp.provider import GoogleClient, GoogleError
from app.routes import google
from app.security import CurrentUser, current_user


def run(coroutine):
    return asyncio.run(coroutine)


def test_provider_never_sends_token_to_unapproved_host():
    async def check():
        calls = []
        async def handler(request):
            calls.append(request)
            return httpx.Response(200, json={})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = GoogleClient("secret", http)
            with pytest.raises(ValueError):
                await client.call("GET", "attacker.example", "v1/anything")
            assert not calls
            with pytest.raises(ValueError):
                await client.review("accounts/a/locations/l/reviews/../../evil")
            assert not calls
    run(check())


@pytest.mark.parametrize("status,uncertain", [(400, False), (403, False), (408, True), (429, True), (500, True)])
def test_write_failure_classification(status, uncertain):
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(status,json={"token":"never expose"}))) as http:
            with pytest.raises(GoogleError) as error:
                await GoogleClient("secret", http).reply("accounts/a/locations/l/reviews/r", "Thank you")
            assert error.value.uncertain == uncertain
            assert "token" not in str(error.value)
    run(check())


def test_timeout_on_write_is_uncertain_and_not_retried():
    async def check():
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("secret upstream text")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(GoogleError) as error:
                await GoogleClient("secret", http).reply("accounts/a/locations/l/reviews/r", "Thank you")
            assert error.value.uncertain
            assert len(calls) == 1
            assert "secret" not in str(error.value)
    run(check())


def test_account_and_review_pagination_are_forwarded():
    async def check():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = GoogleClient("secret", http)
            await client.accounts("next-account")
            await client.reviews("accounts/a/locations/l", "next-review")
        assert calls[0].url.params["pageToken"] == "next-account"
        assert calls[1].url.params["pageToken"] == "next-review"
        assert all(r.headers["Authorization"] == "Bearer secret" for r in calls)
    run(check())


def test_review_name_must_belong_to_polled_location():
    review = {"name":"accounts/a/locations/other/reviews/r", "starRating":"FIVE", "createTime":"2026-11-21T00:00:00Z"}
    with pytest.raises(ValueError):
        jobs.snapshot("workspace", "accounts/a/locations/l", review)


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(google.router)
    app.dependency_overrides[current_user] = lambda: CurrentUser("owner", "owner@example.test")
    config = SimpleNamespace(google_enabled=True,google_client_id="client",google_client_secret="test",
                             google_redirect_uri="https://api.example.test/callback",google_worker_enabled=False)
    app.dependency_overrides[get_settings] = lambda: config
    monkeypatch.setattr(service, "workspace", AsyncMock(return_value="ours"))
    monkeypatch.setattr(service, "owned_location", AsyncMock(return_value={"name":"accounts/a/locations/l","title":"Business"}))
    return TestClient(app), config


def test_foreign_user_id_cannot_override_session(client):
    http, _ = client
    response = http.post("/api/google/locations",json={"user_id":"other", "provider_token":"arbitrary"})
    assert response.status_code == 403


def test_disabled_module_has_no_provider_side_effects(client,monkeypatch):
    http, config = client
    config.google_enabled = False
    start = AsyncMock()
    monkeypatch.setattr(service,"start_oauth",start)
    assert http.post("/api/gbp/connect").status_code == 503
    start.assert_not_called()


def test_location_ownership_checked_before_read(client,monkeypatch):
    http, _ = client
    monkeypatch.setattr(service,"owned_location",AsyncMock(side_effect=HTTPException(403,"Not yours")))
    connect = AsyncMock()
    monkeypatch.setattr(service,"connected",connect)
    assert http.post("/api/google/get-reviews",json={"location_name":"accounts/a/locations/l"}).status_code == 403
    connect.assert_not_called()


def test_rule_requires_exclusive_delivery_confirmation(client):
    http, _ = client
    response = http.put("/api/gbp/rules",json={"location_name":"accounts/a/locations/l","enabled":True})
    assert response.status_code == 409
    response = http.put("/api/gbp/rules",json={"location_name":"accounts/a/locations/l","enabled":True,"exclusive_delivery_confirmed":True})
    assert response.status_code == 409
    assert "paused" in response.json()["detail"]


def test_invalid_rule_rejected(client):
    http, _ = client
    assert http.put("/api/gbp/rules",json={"min_rating":5,"max_rating":1}).status_code == 422


def test_blank_reply_is_rejected_before_any_provider_work(client):
    http, _ = client
    assert http.post("/api/google/post-reply", json={
        "review_id": "accounts/a/locations/l/reviews/r", "reply_text": "   \n "
    }).status_code == 422


def test_scheduling_fails_closed_while_google_worker_is_paused(client):
    http, config = client
    config.google_worker_enabled = False
    assert http.post("/api/gbp/posts", json={
        "location_name": "accounts/a/locations/l", "summary": "Scheduled offer",
        "scheduled_for": "2099-01-01T12:00:00Z"
    }).status_code == 409
    assert http.post("/api/platform/campaigns/00000000-0000-4000-8000-000000000001/schedule",
        json={"publish_at": "2099-01-01T12:00:00Z"}).status_code == 409


def test_webhook_fails_closed_without_identity_configuration(client):
    http, config = client
    config.google_pubsub_audience = None
    config.google_pubsub_service_account = None
    assert http.post("/api/webhooks/google-reviews",json={}).status_code == 503


def test_manual_reply_cannot_write_without_atomic_claim(monkeypatch):
    monkeypatch.setattr(service,"execute",AsyncMock(return_value=False))
    connect = AsyncMock()
    monkeypatch.setattr(service,"connected",connect)
    assert run(jobs.deliver_reply(SimpleNamespace(),{"id":"job"})) == {"status":"not_claimed"}
    connect.assert_not_called()


def test_oauth_state_is_consumed_before_any_code_exchange(monkeypatch):
    monkeypatch.setattr(service,"ready",lambda s:None)
    execute = AsyncMock(return_value=[])
    monkeypatch.setattr(service,"execute",execute)
    with pytest.raises(HTTPException) as error:
        run(service.finish_oauth(SimpleNamespace(),"replayed-state","code"))
    assert error.value.status_code == 400
    assert execute.await_count == 1
