import hashlib
import hmac
import json

import httpx
import pytest

from app.whatsapp import (
    WhatsAppAPIError,
    WhatsAppClient,
    WhatsAppDeliveryUncertain,
    decode_verified_webhook,
    parse_events,
)


def payload(messages=None, statuses=None):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "456"},
                            "messages": messages or [],
                            "statuses": statuses or [],
                        },
                    }
                ],
            }
        ],
    }


def message(**extra):
    return {
        "id": "wamid.test",
        "from": "919999999999",
        "timestamp": "1794061800",
        "type": "text",
        "text": {"body": "Hello"},
        **extra,
    }


def test_verified_webhook_normalizes_text_without_triggering_sends():
    body = json.dumps(payload([message()])).encode()
    signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    events = decode_verified_webhook(body, signature, "test-secret")
    assert events[0]["kind"] == "incoming"
    assert events[0]["phone_number_id"] == "456"
    assert events[0]["text"] == "Hello"
    assert len(events[0]["event_key"]) == 64
    assert events == decode_verified_webhook(body, signature, "test-secret")
    with pytest.raises(ValueError, match="signature"):
        decode_verified_webhook(body, bad_signature(signature), "test-secret")
    with pytest.raises(ValueError, match="limit"):
        decode_verified_webhook(b" " * (1024 * 1024 + 1), signature, "test-secret")


def bad_signature(signature):
    return signature[:-1] + ("0" if signature[-1] != "0" else "1")


def test_statuses_and_button_responses_are_separate_events():
    opening = message(
        type="interactive", interactive={"button_reply": {"id": "guide", "title": "Send guide"}}
    )
    receipt = {
        "id": "wamid.outgoing",
        "recipient_id": "919999999999",
        "timestamp": "1794061800",
        "status": "delivered",
    }
    events = parse_events(payload([opening], [receipt]))
    assert events[0]["choice_id"] == "guide"
    assert events[0]["text"] == "Send guide"
    assert events[1]["delivery_status"] == "delivered"
    assert events[0]["event_key"] != events[1]["event_key"]


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"object": "instagram"},
        {"object": "whatsapp_business_account", "entry": [None, 5]},
        payload([message(timestamp="bad")]),
        payload([message(type=None)]),
        payload([message(**{"from": "not-a-number"})]),
    ],
)
def test_unusable_events_are_ignored(bad):
    assert parse_events(bad) == []


@pytest.mark.asyncio
async def test_send_uses_bearer_header_and_never_retries():
    calls = []

    async def send(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer test-only-token"
        assert "test-only-token" not in str(request.url)
        assert json.loads(request.content)["messaging_product"] == "whatsapp"
        return httpx.Response(200, json={"messages": [{"id": "wamid.sent"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as http:
        client = WhatsAppClient("v24.0", http)
        assert (
            await client.send_text("456", "919999999999", "Hello", "test-only-token")
            == "wamid.sent"
        )
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "missing_id", "invalid_json"])
async def test_uncertain_sends_are_identified_and_not_replayed(failure):
    calls = []

    async def send(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("test")
        if failure == "invalid_json":
            return httpx.Response(200, text="unreadable")
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as http:
        with pytest.raises(WhatsAppDeliveryUncertain):
            await WhatsAppClient("v24.0", http).send_text(
                "456", "919999999999", "Hello", "test-only-token"
            )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_provider_rejection_does_not_expose_secrets():
    async def send(request):
        return httpx.Response(
            400, json={"error": {"message": "echoed-secret-token private customer text"}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as http:
        with pytest.raises(WhatsAppAPIError) as result:
            await WhatsAppClient("v24.0", http).send_text(
                "456", "919999999999", "Hello", "test-only-token"
            )
    assert "echoed-secret" not in str(result.value)
    assert "private customer" not in str(result.value)


def test_api_host_cannot_be_overridden_through_version():
    with pytest.raises(ValueError):
        WhatsAppClient("https://another-host")
