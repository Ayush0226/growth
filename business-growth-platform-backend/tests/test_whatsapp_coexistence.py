"""Coexistence lifecycle and messaging boundaries; fixtures only, no Meta sends."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from test_whatsapp_product import env as base_env

from app import whatsapp_service as service
from app.routes import whatsapp as routes
from app.whatsapp import WhatsAppAPIError, WhatsAppClient, parse_events

env = base_env


def payload(field, value):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "789",
                "changes": [
                    {
                        "field": field,
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "456"},
                            **value,
                        },
                    }
                ],
            }
        ],
    }


def test_pin_cannot_register_coexistence_number():
    with pytest.raises(ValidationError):
        routes.SignupComplete(
            state="a" * 25,
            code="test",
            waba_id="789",
            connection_mode="coexistence",
            registration_pin="123456",
        )
    with pytest.raises(ValidationError):
        routes.SignupComplete(
            state="a" * 25, code="test", waba_id="789", connection_mode="new_number"
        )


@pytest.mark.asyncio
async def test_coexistence_resolves_missing_phone_and_never_registers(env, monkeypatch):
    settings, conn, _person, _store = env
    conn.update(contacts_sync_status="not_started", history_sync_status="not_started")
    calls = []

    async def resolve(*args):
        return "456"

    async def validate(*args):
        return {"display_phone_number": "123"}

    async def forbidden(*args):
        raise AssertionError("Must not register an existing app number")

    async def sync(self, phone, token, kind):
        calls.append(kind)
        return {"request_id": kind}

    monkeypatch.setattr(WhatsAppClient, "coexistence_phone", resolve)
    monkeypatch.setattr(WhatsAppClient, "validate_connection", validate)
    monkeypatch.setattr(WhatsAppClient, "register_number", forbidden)
    monkeypatch.setattr(WhatsAppClient, "sync_app_data", sync)
    for _ in range(2):
        await routes.store_connection(
            "workspace",
            routes.CurrentUser("owner", None),
            "789",
            None,
            "test-token",
            settings,
            connection_mode="coexistence",
        )
    assert calls == ["smb_app_state_sync", "history"]
    assert conn["connection_mode"] == "coexistence"


@pytest.mark.asyncio
async def test_history_is_idempotent_never_opens_reply_window_or_queues_reply(env):
    settings, conn, person, store = env
    conn.update(connection_mode="coexistence", history_sync_progress=0)
    store.tables["whatsapp_messages"] = []
    event = parse_events(
        payload(
            "history",
            {
                "history": [
                    {
                        "metadata": {"progress": 100},
                        "threads": [
                            {
                                "id": person["wa_id"],
                                "messages": [
                                    {
                                        "id": "old",
                                        "from": person["wa_id"],
                                        "type": "text",
                                        "text": {"body": "hello"},
                                        "timestamp": str(int(datetime.now(UTC).timestamp())),
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        )
    )
    assert service.ingest(event) == 1
    assert service.ingest(event) == 0
    for row in list(store.tables["whatsapp_events"]):
        await service.process_event(row, settings)
    assert len(store.tables["whatsapp_messages"]) == 1
    assert store.tables["whatsapp_messages"][0]["is_history"]
    assert service.service_window(conn, person["wa_id"]) is None
    assert conn["history_sync_progress"] == 100


@pytest.mark.asyncio
async def test_phone_app_echo_is_outbound_and_pauses_automation(env):
    settings, conn, person, store = env
    conn["connection_mode"] = "coexistence"
    events = parse_events(
        payload(
            "smb_message_echoes",
            {
                "message_echoes": [
                    {
                        "id": "echo",
                        "to": person["wa_id"],
                        "from": "123",
                        "type": "text",
                        "text": {"body": "Staff reply"},
                        "timestamp": "1795410000",
                    }
                ]
            },
        )
    )
    service.ingest(events)
    await service.process_event(store.tables["whatsapp_events"][0], settings)
    assert person["automation_paused"]
    assert store.tables["whatsapp_messages"][-1]["direction"] == "outbound"
    assert not store.tables["whatsapp_messages"][-1]["is_history"]


def test_contacts_preserve_optout_and_do_not_grant_consent(env):
    _, conn, person, _store = env
    person.update(opted_out=True, opted_in=False)
    rows = parse_events(
        payload(
            "smb_app_state_sync",
            {
                "state_sync": [
                    {
                        "type": "contact",
                        "action": "add",
                        "metadata": {"timestamp": "1795410000"},
                        "contact": {"phone_number": person["wa_id"], "full_name": "Test"},
                    }
                ]
            },
        )
    )
    service.process_coexistence(conn, rows[0]["items"])
    assert person["name"] == "Test"
    assert person["opted_out"] and not person["opted_in"]


def test_history_decline_and_unsupported_identities_are_explicit(env):
    _, conn, _, _ = env
    events = parse_events(payload("history", {"history": [{"errors": [{"code": 2593109}]}]}))
    service.process_coexistence(conn, events[0]["items"])
    assert conn["history_sync_status"] == "declined"
    events = parse_events(
        payload(
            "smb_app_state_sync",
            {"state_sync": [{"type": "contact", "action": "add", "contact": {"user_id": "bsuid"}}]},
        )
    )
    service.process_coexistence(conn, events[0]["items"])
    assert conn["sync_warning"]


@pytest.mark.asyncio
async def test_offboarding_clears_credentials_and_stops_delivery(env):
    settings, conn, _, store = env
    service.ingest(parse_events(payload("account_update", {"event": "ACCOUNT_OFFBOARDED"})))
    await service.process_event(store.tables["whatsapp_events"][0], settings)
    assert conn["status"] == "revoked" and conn["access_token_encrypted"] == ""


def test_foreign_account_cannot_inject_sync_into_workspace(env):
    _, _, _, _store = env
    body = payload("history", {"history": [{"errors": [{"code": 2593109}]}]})
    body["entry"][0]["id"] = "999"
    assert service.ingest(parse_events(body)) == 0


@pytest.mark.asyncio
async def test_ambiguous_business_app_numbers_are_not_guessed(monkeypatch):
    async def rows(*args, **kwargs):
        return [{"id": "1", "is_on_biz_app": True}, {"id": "2", "is_on_biz_app": True}]

    monkeypatch.setattr(WhatsAppClient, "rows", rows)
    with pytest.raises(WhatsAppAPIError):
        await WhatsAppClient("v26.0").coexistence_phone("789", None, "test")
