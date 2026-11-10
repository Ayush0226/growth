"""Delivery, tenancy, consent and billing boundaries; no real Meta calls."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import whatsapp_service as service
from app.config import Settings, get_settings
from app.routes import whatsapp as routes
from app.security import CurrentUser, TokenCipher, current_user
from app.whatsapp import WhatsAppAPIError, WhatsAppClient, WhatsAppDeliveryUncertain


class Query:
    def __init__(self, store, table):
        self.store, self.table = store, table
        self.filters, self.sort = [], []
        self.operation, self.values, self.columns = "select", None, "*"
        self.offset, self.end, self.maximum = 0, None, None

    def select(self, columns="*", **_):
        self.columns = columns
        return self

    def eq(self, key, value):
        self.filters.append(lambda row: row.get(key) == value)
        return self

    def in_(self, key, values):
        self.filters.append(lambda row: row.get(key) in values)
        return self

    def is_(self, key, value):
        self.filters.append(
            lambda row: row.get(key) is None if value == "null" else row.get(key) == value
        )
        return self

    def gte(self, key, value):
        self.filters.append(lambda row: row.get(key) is not None and row[key] >= value)
        return self

    def lte(self, key, value):
        self.filters.append(lambda row: row.get(key) is not None and row[key] <= value)
        return self

    def lt(self, key, value):
        self.filters.append(lambda row: row.get(key) is not None and row[key] < value)
        return self

    def gt(self, key, value):
        self.filters.append(lambda row: row.get(key) is not None and row[key] > value)
        return self

    def order(self, key, desc=False):
        self.sort.append((key, desc))
        return self

    def range(self, start, end):
        self.offset, self.end = start, end + 1
        return self

    def limit(self, value):
        self.maximum = value
        return self

    def update(self, values):
        self.operation, self.values = "update", values
        return self

    def insert(self, values):
        self.operation, self.values = "insert", values
        return self

    def upsert(self, values, on_conflict="id", ignore_duplicates=False):
        self.operation, self.values = "upsert", values
        self.keys, self.ignore = on_conflict.split(","), ignore_duplicates
        return self

    def execute(self):
        rows = self.store.tables.setdefault(self.table, [])
        if self.operation in {"upsert", "insert"}:
            returned = []
            for value in self.values if isinstance(self.values, list) else [self.values]:
                existing = next(
                    (
                        r
                        for r in rows
                        if self.operation == "upsert"
                        and all(r.get(k) == value.get(k) for k in self.keys)
                    ),
                    None,
                )
                if existing:
                    if self.ignore:
                        continue
                    existing.update(deepcopy(value))
                    returned.append(existing)
                    continue
                item = {
                    "id": str(uuid4()),
                    "created_at": service.now_iso(),
                    "updated_at": service.now_iso(),
                    "occurred_at": service.now_iso(),
                    "received_at": service.now_iso(),
                    "status": "pending" if self.table == "whatsapp_events" else "draft",
                    "opted_in": False,
                    "opted_out": False,
                    "automation_paused": False,
                    "purpose": "manual",
                    "category": "service",
                    "parameters": [],
                    **deepcopy(value),
                }
                rows.append(item)
                returned.append(item)
            return SimpleNamespace(data=deepcopy(returned), count=len(returned))
        matched = [r for r in rows if all(f(r) for f in self.filters)]
        if self.operation == "update":
            for row in matched:
                row.update(deepcopy(self.values))
        for key, reverse in reversed(self.sort):
            matched.sort(key=lambda r: r.get(key, ""), reverse=reverse)
        count = len(matched)
        matched = matched[self.offset : self.end]
        if self.maximum is not None:
            matched = matched[: self.maximum]
        if self.columns != "*":
            matched = [{key: r.get(key) for key in self.columns.split(",")} for r in matched]
        return SimpleNamespace(data=deepcopy(matched), count=count)


class Store:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return Query(self, name)


@pytest.fixture
def env(monkeypatch):
    settings = Settings(
        _env_file=None,
        meta_app_id="123",
        meta_app_secret="test-secret",
        meta_graph_api_version="v24.0",
        instagram_redirect_uri="https://example.test/callback",
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="test-only",
        token_encryption_key="test-key-for-isolated-tests-123456789",
        frontend_url="https://example.test",
        scheduler_enabled=False,
        whatsapp_enabled=True,
    )
    conn = {
        "id": str(uuid4()),
        "workspace_id": "workspace",
        "phone_number_id": "456",
        "waba_id": "789",
        "status": "active",
        "billing_acknowledged": True,
        "ai_enabled": False,
        "connected_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "access_token_encrypted": TokenCipher(settings.token_encryption_key).encrypt("test-token"),
    }
    person = {
        "id": "person",
        "workspace_id": "workspace",
        "connection_id": conn["id"],
        "wa_id": "919876543210",
        "opted_in": True,
        "opted_out": False,
        "automation_paused": False,
    }
    inbound = {
        "id": "inbound",
        "connection_id": conn["id"],
        "workspace_id": "workspace",
        "direction": "inbound",
        "contact_wa_id": person["wa_id"],
        "status": "received",
        "occurred_at": service.now_iso(),
        "created_at": service.now_iso(),
    }
    store = Store(
        {
            "whatsapp_connections": [conn],
            "whatsapp_contacts": [person],
            "whatsapp_messages": [inbound],
        }
    )
    monkeypatch.setattr(service, "db", lambda: store)
    monkeypatch.setattr(routes, "db", lambda: store)
    return settings, conn, person, store


@pytest.mark.asyncio
async def test_manual_reply_is_idempotent_and_worker_claim_prevents_double_send(env, monkeypatch):
    settings, conn, person, store = env
    payload = routes.MessageInput(request_id=uuid4(), text="Hello")
    first = routes.reply(person["wa_id"], payload, conn)
    assert routes.reply(person["wa_id"], payload, conn)["id"] == first["id"]
    assert person["automation_paused"]
    calls = []

    async def send(*args):
        calls.append(args)
        return "wamid.outgoing"

    monkeypatch.setattr(WhatsAppClient, "send_text", send)
    await service.deliver(first, settings)
    await service.deliver(first, settings)
    assert len(calls) == 1
    assert store.tables["whatsapp_messages"][-1]["status"] == "sent"
    with pytest.raises(HTTPException) as error:
        routes.reply(
            person["wa_id"],
            routes.MessageInput(request_id=payload.request_id, text="Different"),
            conn,
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["optout", "window", "billing", "disconnected", "renewed"])
async def test_delivery_rechecks_eligibility_after_queueing(env, monkeypatch, reason):
    settings, conn, person, store = env
    row = service.queue_message(conn, person["wa_id"], str(uuid4()), "Hello")
    if reason == "optout":
        person["opted_out"] = True
    elif reason == "window":
        store.tables["whatsapp_messages"][0]["occurred_at"] = (
            datetime.now(UTC) - timedelta(hours=25)
        ).isoformat()
    elif reason == "billing":
        conn["billing_acknowledged"] = False
    elif reason == "disconnected":
        conn["status"] = "revoked"
    else:
        conn["connected_at"] = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()

    async def forbidden(*_):
        raise AssertionError("No provider send should be attempted")

    monkeypatch.setattr(WhatsAppClient, "send_text", forbidden)
    await service.deliver(row, settings)
    assert store.tables["whatsapp_messages"][-1]["status"] == "failed"


@pytest.mark.asyncio
async def test_uncertain_send_never_retries(env, monkeypatch):
    settings, conn, person, store = env
    row = service.queue_message(conn, person["wa_id"], str(uuid4()), "Hello")
    calls = []

    async def uncertain(*args):
        calls.append(args)
        raise WhatsAppDeliveryUncertain("Unconfirmed")

    monkeypatch.setattr(WhatsAppClient, "send_text", uncertain)
    await service.deliver(row, settings)
    await service.deliver(row, settings)
    assert len(calls) == 1
    assert store.tables["whatsapp_messages"][-1]["status"] == "uncertain"


def test_webhook_routing_requires_both_business_and_number_and_deduplicates(env):
    _, conn, person, store = env
    event = {
        "phone_number_id": conn["phone_number_id"],
        "account_id": conn["waba_id"],
        "event_key": "unique",
        "contact_wa_id": person["wa_id"],
        "kind": "incoming",
    }
    assert service.ingest([{**event, "account_id": "another-business"}]) == 0
    assert service.ingest([event]) == 1
    assert service.ingest([event]) == 0
    assert store.tables["whatsapp_events"][0]["workspace_id"] == "workspace"


def test_receipts_cannot_downgrade_read_or_cross_connections(env):
    _, conn, person, store = env
    row = service.queue_message(conn, person["wa_id"], str(uuid4()), "Hello")
    actual = store.tables["whatsapp_messages"][-1]
    actual.update(provider_message_id="wamid.out", status="read")
    receipt = {
        "provider_message_id": "wamid.out",
        "contact_wa_id": person["wa_id"],
        "delivery_status": "delivered",
        "occurred_at": service.now_iso(),
        "pricing": {"category": "service", "billable": False, "type": "free_customer_service"},
    }
    assert not service.apply_receipt({**conn, "id": "another-connection"}, receipt)
    assert service.apply_receipt(conn, receipt)
    assert actual["status"] == "read"
    assert actual["pricing_billable"] is False
    assert actual["id"] == row["id"]
    assert service.apply_receipt(conn, receipt)
    assert len(store.tables["whatsapp_messages"]) == 2


@pytest.mark.asyncio
async def test_optout_and_human_handoff_suppress_automation(env):
    settings, conn, person, store = env
    event = {
        "id": str(uuid4()),
        "workspace_id": "workspace",
        "connection_id": conn["id"],
        "status": "pending",
        "received_at": service.now_iso(),
        "event": {
            "kind": "incoming",
            "contact_wa_id": person["wa_id"],
            "provider_message_id": "wamid.stop",
            "message_type": "text",
            "text": "STOP",
            "occurred_at": service.now_iso(),
        },
    }
    store.tables["whatsapp_events"] = [event]
    await service.process_event(deepcopy(event), settings)
    assert person["opted_out"] and not person["opted_in"] and person["automation_paused"]
    assert not [r for r in store.tables["whatsapp_messages"] if r["direction"] == "outbound"]
    with pytest.raises(HTTPException):
        routes.contact_control(person["wa_id"], routes.ContactControl(paused=False), conn)


@pytest.mark.asyncio
async def test_keyword_rule_priority_and_cooldown(env):
    settings, conn, person, store = env
    since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    rule = {
        "id": "keyword-rule",
        "connection_id": conn["id"],
        "trigger": "keyword",
        "enabled": True,
        "keywords": ["hours"],
        "reply_text": "10 AM to 6 PM",
        "updated_at": since,
        "created_at": since,
        "daily_limit": 10,
        "cooldown_minutes": 60,
    }
    store.tables["whatsapp_rules"] = [rule]
    for n in range(2):
        event = {
            "id": str(uuid4()),
            "workspace_id": "workspace",
            "connection_id": conn["id"],
            "status": "pending",
            "received_at": service.now_iso(),
            "event": {
                "kind": "incoming",
                "contact_wa_id": person["wa_id"],
                "provider_message_id": f"wamid.hours.{n}",
                "message_type": "text",
                "text": "Your hours?",
                "occurred_at": service.now_iso(),
            },
        }
        store.tables.setdefault("whatsapp_events", []).append(event)
        await service.process_event(deepcopy(event), settings)
    outgoing = [r for r in store.tables["whatsapp_messages"] if r["direction"] == "outbound"]
    assert len(outgoing) == 1
    assert outgoing[0]["text"] == "10 AM to 6 PM"


def test_validation_does_not_treat_import_as_consent_or_allow_duplicate_campaign_recipients():
    with pytest.raises(ValidationError):
        routes.ContactInput(wa_id="919876543210", opted_in=True)
    with pytest.raises(ValidationError):
        routes.CampaignInput(
            request_id=uuid4(),
            name="Test",
            template_id="123",
            recipients=[{"wa_id": "919876543210"}, {"wa_id": "919876543210"}],
        )
    with pytest.raises(ValidationError):
        routes.TemplateInput(
            name="valid", language="en", category="MARKETING", body="Hello {{2}}", examples=["Name"]
        )
    for template, expected in [
        ({"status": "APPROVED", "components": [{"type": "BODY", "text": "Hi {{1}}"}]}, (True, 1)),
        ({"status": "PENDING", "components": [{"type": "BODY", "text": "Hi"}]}, (False, 0)),
        (
            {
                "status": "APPROVED",
                "components": [
                    {"type": "BODY", "text": "Hi"},
                    {"type": "HEADER", "format": "IMAGE"},
                ],
            },
            (False, 0),
        ),
    ]:
        assert service.template_shape(template) == expected


@pytest.mark.asyncio
async def test_campaign_requires_owned_contacts_with_recorded_consent(env, monkeypatch):
    settings, conn, person, _ = env
    template = {"id": "123", "sendable": True, "parameter_count": 0}

    async def templates(*_):
        return [template]

    monkeypatch.setattr(routes, "sync_templates", templates)
    payload = routes.CampaignInput(
        request_id=uuid4(), name="Test", template_id="123", recipients=[{"wa_id": person["wa_id"]}]
    )
    person["opted_in"] = False
    with pytest.raises(HTTPException) as error:
        await routes.create_campaign(payload, conn, settings)
    assert error.value.status_code == 409
    person["opted_in"] = True
    first = await routes.create_campaign(payload, conn, settings)
    assert first["status"] == "draft"
    assert (await routes.create_campaign(payload, conn, settings))["id"] == first["id"]


def test_public_status_redacts_token_and_does_not_invent_wallet(env, monkeypatch):
    settings, _, _, _ = env
    monkeypatch.setattr(routes, "user_workspace", lambda _: "workspace")
    result = routes.status(CurrentUser("user", None), settings)
    assert result["connected"]
    assert "access_token_encrypted" not in result["connection"]
    assert result["usage"]["authoritative_balance_available"] is False
    assert "balance" not in result
    assert result["allowance"]["includes_templates"] is False


@pytest.mark.asyncio
async def test_unreadable_provider_500_is_uncertain_not_retryable():
    async def response(_request):
        return httpx.Response(500, text="server failed")

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        with pytest.raises(WhatsAppDeliveryUncertain):
            await WhatsAppClient("v24.0", http).send_text("456", "919876543210", "Hi", "token")


@pytest.mark.asyncio
async def test_connection_requires_same_app_and_phone_membership():
    async def response(request):
        if "debug_token" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "is_valid": True,
                        "app_id": "123",
                        "scopes": ["whatsapp_business_management", "whatsapp_business_messaging"],
                    }
                },
            )
        return httpx.Response(200, json={"data": [{"id": "some-other-number"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        with pytest.raises(WhatsAppAPIError, match="does not belong"):
            await WhatsAppClient("v24.0", http).validate_connection(
                "789", "456", "token", "123", "secret"
            )


def test_webhook_can_be_verified_before_messaging_is_enabled(env):
    settings, _, _, _ = env
    settings.whatsapp_enabled = False
    settings.whatsapp_webhook_verify_token = "test-webhook-verification"
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        response = client.get(
            "/api/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test-webhook-verification",
                "hub.challenge": "verify-this-callback",
            },
        )
        assert response.status_code == 200
        assert response.text == "verify-this-callback"
        assert response.headers["content-type"].startswith("text/plain")
        assert (
            client.get(
                "/api/whatsapp/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "incorrect",
                    "hub.challenge": "verify-this-callback",
                },
            ).status_code
            == 403
        )


def test_routes_mount_and_reject_unsigned_webhooks(env):
    settings, _, _, _ = env
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[current_user] = lambda: CurrentUser("user", None)
    with TestClient(app) as client:
        assert client.post("/api/whatsapp/webhook", json={}).status_code == 400
        assert (
            client.get("/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=no").status_code
            == 403
        )


@pytest.mark.asyncio
async def test_paused_campaign_queue_does_not_starve_manual_replies(env, monkeypatch):
    settings, conn, person, store = env
    campaign = {"id": str(uuid4()), "status": "paused"}
    store.tables["whatsapp_campaigns"] = [campaign]
    for _ in range(30):
        service.queue_message(
            conn, person["wa_id"], str(uuid4()), "", purpose="campaign", campaign_id=campaign["id"]
        )
    manual = service.queue_message(conn, person["wa_id"], str(uuid4()), "Manual reply")
    calls = []

    async def send(*args):
        calls.append(args)
        return "wamid.manual"

    monkeypatch.setattr(WhatsAppClient, "send_text", send)
    await service.run_pending(settings)
    assert len(calls) == 1
    assert (
        next(m for m in store.tables["whatsapp_messages"] if m["id"] == manual["id"])["status"]
        == "sent"
    )
    assert all(
        m["status"] == "queued" for m in store.tables["whatsapp_messages"] if m.get("campaign_id")
    )


@pytest.mark.asyncio
async def test_campaign_rechecks_revoked_consent_and_never_sends_twice(env, monkeypatch):
    settings, conn, person, store = env
    template = {
        "id": "123",
        "name": "offer",
        "language": "en",
        "category": "MARKETING",
        "status": "APPROVED",
        "sendable": True,
        "parameter_count": 0,
        "components": [{"type": "BODY", "text": "Our seasonal offer. Reply STOP to opt out."}],
    }
    campaign = {
        "id": str(uuid4()),
        "workspace_id": "workspace",
        "connection_id": conn["id"],
        "status": "scheduled",
        "template": template,
        "recipients": [{"wa_id": person["wa_id"], "parameters": []}],
        "scheduled_for": service.now_iso(),
        "created_at": service.now_iso(),
    }
    store.tables["whatsapp_campaigns"] = [campaign]

    async def templates(*_):
        return [template]

    async def forbidden(*_):
        raise AssertionError("Consent was revoked before dispatch")

    monkeypatch.setattr(service, "sync_templates", templates)
    monkeypatch.setattr(WhatsAppClient, "send_template", forbidden)
    person["opted_in"] = False
    await service.run_pending(settings)
    await service.run_pending(settings)
    outgoing = [r for r in store.tables["whatsapp_messages"] if r["direction"] == "outbound"]
    assert len(outgoing) == 1 and outgoing[0]["status"] == "failed"


def test_bulk_import_cannot_reverse_optout_without_explicit_fresh_consent(env):
    _, conn, person, _ = env
    person["opted_out"] = True
    routes.import_contacts(
        routes.ContactImport(items=[{"wa_id": person["wa_id"], "name": "Customer"}]), conn
    )
    assert person["opted_out"]
    routes.import_contacts(
        routes.ContactImport(
            items=[
                {
                    "wa_id": person["wa_id"],
                    "opted_in": True,
                    "consent_source": "Customer requested appointment reminders through our website today.",
                }
            ]
        ),
        conn,
    )
    assert person["opted_out"] is False and person["opted_in"] is True


@pytest.mark.asyncio
async def test_recipient_pacing_leaves_second_message_queued(env, monkeypatch):
    settings, conn, person, store = env
    first = service.queue_message(conn, person["wa_id"], str(uuid4()), "First")
    second = service.queue_message(conn, person["wa_id"], str(uuid4()), "Second")
    calls = []

    async def send(*args):
        calls.append(args)
        return "wamid.first"

    monkeypatch.setattr(WhatsAppClient, "send_text", send)
    await service.deliver(first, settings)
    await service.deliver(second, settings)
    assert len(calls) == 1
    assert next(m for m in store.tables["whatsapp_messages"] if m["id"] == second["id"])["status"] == "queued"


@pytest.mark.asyncio
async def test_embedded_signup_code_exchange_uses_customer_scoped_token():
    async def response(request):
        assert request.method == "GET"
        assert request.url.path.endswith("/oauth/access_token")
        assert request.url.params["code"] == "test-code"
        assert request.headers["authorization"] == "Bearer 123|test-secret"
        return httpx.Response(200, json={"access_token": "customer-scoped-test-token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        token = await WhatsAppClient("v24.0", http).exchange_code("test-code", "123", "test-secret")
    assert token == "customer-scoped-test-token"
