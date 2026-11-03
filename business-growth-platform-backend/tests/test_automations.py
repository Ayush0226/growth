import hashlib
import hmac
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.automations as engine
from app.config import Settings, get_settings
from app.routes import engagement
from app.routes.automations import RuleInput
from app.routes.content import DraftCreate, ScheduleUpdate
from app.security import TokenCipher


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        meta_app_id="app",
        meta_app_secret="test-secret",
        meta_graph_api_version="v24.0",
        instagram_redirect_uri="https://api.example.test/callback",
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="test-only",
        token_encryption_key="test-key-for-isolated-tests-123456789",
        frontend_url="https://example.test",
        scheduler_enabled=False,
    )


class Query:
    def __init__(self, store, table):
        self.store = store
        self.name = table
        self.rows = store.setdefault(table, [])
        self.filters = []
        self.operation = "select"
        self.payload = None
        self.conflict = "id"
        self.max_rows = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, k, v):
        self.filters.append(lambda r: r.get(k) == v)
        return self

    def in_(self, k, v):
        self.filters.append(lambda r: r.get(k) in v)
        return self

    def gte(self, k, v):
        self.filters.append(lambda r: r.get(k, "") >= v)
        return self

    def lte(self, k, v):
        self.filters.append(lambda r: r.get(k, "") <= v)
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, n):
        self.max_rows = n
        return self

    def update(self, data):
        self.operation = "update"
        self.payload = data
        return self

    def upsert(self, data, on_conflict="id", ignore_duplicates=False):
        self.operation = "upsert"
        self.payload = data
        self.conflict = on_conflict
        return self

    def execute(self):
        if self.operation == "upsert":
            keys = self.conflict.split(",")
            if any(all(r.get(k) == self.payload.get(k) for k in keys) for r in self.rows):
                return SimpleNamespace(data=[], count=0)
            row = {
                "id": str(uuid4()),
                "created_at": datetime.now(UTC).isoformat(),
                "status": "sending",
                **self.payload,
            }
            self.rows.append(row)
            return SimpleNamespace(data=[deepcopy(row)], count=1)
        matched = [r for r in self.rows if all(f(r) for f in self.filters)]
        if self.operation == "update":
            for r in matched:
                r.update(self.payload)
        if self.operation == "delete":
            self.rows[:] = [row for row in self.rows if row not in matched]
        count = len(matched)
        return SimpleNamespace(
            data=deepcopy(matched[: self.max_rows] if self.max_rows else matched), count=count
        )


class Store:
    def __init__(self, data):
        self.data = data

    def table(self, name):
        return Query(self.data, name)


@pytest.fixture
def context(monkeypatch, settings):
    event = {
        "id": "event-1",
        "connection_id": "conn",
        "workspace_id": "workspace",
        "account_id": "ig-own",
        "event_key": "dm:one",
        "kind": "dm",
        "sender_id": "customer",
        "text": "Hello",
        "occurred_at": datetime.now(UTC).isoformat(),
        "status": "pending",
    }
    rule = {
        "id": "rule",
        "workspace_id": "workspace",
        "trigger": "welcome",
        "enabled": True,
        "reply_text": "Welcome!",
        "keywords": [],
        "media_ids": [],
        "daily_limit": 20,
        "cooldown_minutes": 60,
    }
    store = Store(
        {
            "automation_events": [event],
            "automation_rules": [rule],
            "social_connections": [
                {
                    "id": "conn",
                    "workspace_id": "workspace",
                    "status": "active",
                    "active_account_id": "ig-own",
                    "granted_scopes": [
                        "instagram_business_manage_messages",
                        "instagram_business_manage_comments",
                    ],
                    "access_token_encrypted": TokenCipher(settings.token_encryption_key).encrypt(
                        "test-token"
                    ),
                }
            ],
        }
    )
    monkeypatch.setattr(engine, "db", lambda: store)
    sent = []

    async def send(self, path, token, **body):
        sent.append((path, json.loads(body["recipient"]), json.loads(body["message"])))
        return {"message_id": "outgoing-1"}

    monkeypatch.setattr(engine.InstagramClient, "post", send)
    return store, event, rule, sent


def test_keywords_are_case_insensitive_complete_words_and_phrases():
    assert engine.matches_keyword("Please send PRICE details", ["price"])
    assert engine.matches_keyword("SEND MENU, please", ["send menu"])
    assert not engine.matches_keyword("This is nice", ["hi"])
    assert not engine.matches_keyword("priceless", ["price"])


def test_parser_ignores_echoes_and_unrelated_notifications():
    base = {
        "sender": {"id": "customer"},
        "recipient": {"id": "own"},
        "timestamp": 1700000000000,
        "message": {"mid": "one", "text": "hello"},
    }
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "own",
                "messaging": [
                    base,
                    {**base, "message": {**base["message"], "is_echo": True}},
                    {**base, "sender": {"id": "own"}},
                    {**base, "recipient": {"id": "different"}},
                ],
            }
        ],
    }
    events = engine.parse_events(payload)
    assert len(events) == 1
    assert events[0]["event_key"] == "dm:one"
    assert events[0]["occurred_at"].startswith("2023-11-14")


@pytest.mark.asyncio
async def test_welcome_is_once_per_contact_and_duplicate_is_not_resent(context, settings):
    store, event, _rule, sent = context
    await engine.process_event(deepcopy(event), settings)
    await engine.process_event(deepcopy(event), settings)
    later = {**event, "id": "event-2", "event_key": "dm:two", "status": "pending"}
    store.data["automation_events"].append(later)
    await engine.process_event(deepcopy(later), settings)
    assert len(sent) == 1
    assert sent[0][1] == {"id": "customer"}
    assert store.data["automation_deliveries"][0]["status"] == "sent"
    assert later["status"] == "ignored"


@pytest.mark.asyncio
async def test_keyword_rule_takes_precedence_over_welcome(context, settings):
    store, event, rule, sent = context
    event["text"] = "price please"
    store.data["automation_rules"].append(
        {
            **rule,
            "id": "keyword",
            "trigger": "dm_keyword",
            "keywords": ["price"],
            "reply_text": "Our prices",
        }
    )
    await engine.process_event(deepcopy(event), settings)
    assert sent[0][2] == {"text": "Our prices"}


@pytest.mark.asyncio
async def test_comment_rules_require_selected_media_and_send_private_reply(context, settings):
    store, event, rule, sent = context
    rule.update(trigger="comment_keyword", media_ids=["post-1"], keywords=["menu"])
    event.update(kind="comment", comment_id="comment-1", media_id="post-1", text="Menu please")
    await engine.process_event(deepcopy(event), settings)
    assert sent[0][1] == {"comment_id": "comment-1"}
    other = {
        **event,
        "id": "event-2",
        "event_key": "comment:two",
        "media_id": "post-2",
        "status": "pending",
    }
    store.data["automation_events"].append(other)
    await engine.process_event(deepcopy(other), settings)
    assert len(sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["expired", "disabled", "disconnected", "no_scope", "other_workspace"]
)
async def test_ineligible_events_never_send(context, settings, change):
    store, event, rule, sent = context
    if change == "expired":
        event["occurred_at"] = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    if change == "disabled":
        rule["enabled"] = False
    if change == "disconnected":
        store.data["social_connections"][0]["status"] = "revoked"
    if change == "no_scope":
        store.data["social_connections"][0]["granted_scopes"] = []
    if change == "other_workspace":
        rule["workspace_id"] = "other"
    await engine.process_event(deepcopy(event), settings)
    assert not sent
    assert event["status"] == "ignored"


@pytest.mark.asyncio
async def test_daily_limit_prevents_a_public_send(context, settings):
    store, event, rule, sent = context
    rule["daily_limit"] = 1
    store.data["automation_deliveries"] = [
        {
            "id": "old",
            "rule_id": "rule",
            "status": "sent",
            "recipient_id": "different",
            "created_at": datetime.now(UTC).isoformat(),
        }
    ]
    await engine.process_event(deepcopy(event), settings)
    assert not sent
    assert event["detail"] == "Rule daily limit reached"


@pytest.mark.asyncio
async def test_network_timeout_is_uncertain_and_never_automatically_replayed(
    context, settings, monkeypatch
):
    store, event, _rule, sent = context

    async def timeout(*args, **kwargs):
        sent.append("attempt")
        raise httpx.ReadTimeout("test-only")

    monkeypatch.setattr(engine.InstagramClient, "post", timeout)
    await engine.process_event(deepcopy(event), settings)
    await engine.process_event(deepcopy(event), settings)
    assert len(sent) == 1
    assert store.data["automation_deliveries"][0]["status"] == "uncertain"
    assert event["status"] == "failed"


def test_rule_input_requires_explicit_valid_content_and_selected_media():
    with pytest.raises(ValidationError):
        RuleInput(name="x", trigger="comment_keyword", keywords=["price"], reply_text="Details")
    with pytest.raises(ValidationError):
        RuleInput(name="x", trigger="dm_keyword", reply_text="Details")
    assert not RuleInput(name="Welcome", trigger="welcome", reply_text="Hello").enabled
    assert not DraftCreate(caption="caption", media_asset_id="asset").approved
    with pytest.raises(ValidationError):
        ScheduleUpdate(scheduled_for="2020-01-01T10:00:00")
    with pytest.raises(ValidationError):
        ScheduleUpdate(scheduled_for="2020-01-01T10:00:00Z")


def test_webhook_rejects_forgery_and_does_not_acknowledge_failed_storage(monkeypatch, settings):
    app = FastAPI()
    app.include_router(engagement.router)
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    body = b'{"object":"instagram","entry":[]}'
    called = []
    monkeypatch.setattr(engagement, "ingest", lambda payload: called.append(payload))
    assert client.post("/api/instagram/webhook", content=body).status_code == 403
    assert not called
    signature = (
        "sha256=" + hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    )
    headers = {"x-hub-signature-256": signature}
    assert client.post("/api/instagram/webhook", content=body, headers=headers).status_code == 200
    assert len(called) == 1

    def unavailable(payload):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(engagement, "ingest", unavailable)
    assert client.post("/api/instagram/webhook", content=body, headers=headers).status_code == 503
    assert (
        client.post("/api/instagram/webhook", content=body + b" ", headers=headers).status_code
        == 403
    )
