# ruff: noqa: F811 -- imported pytest fixtures are intentionally injected by name
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from postgrest.exceptions import APIError
from test_automations import Store, context, settings  # noqa: F401

from app import chatbot
from app.automations import process_event
from app.routes import chatbot as routes
from app.security import CurrentUser


def bot_config():
    return {
        "workspace_id": "workspace",
        "business_name": "Test Studio",
        "knowledge": "Hours: Monday to Friday, 10am to 6pm.",
        "instructions": "Be brief.",
        "role": "support",
        "handoff_message": "Our team will help.",
        "daily_limit": 20,
        "enabled": True,
        "updated_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    }


def test_saving_business_information_always_pauses_live_replies(monkeypatch):
    store = Store({})
    monkeypatch.setattr(routes, "db", lambda: store)
    monkeypatch.setattr(routes, "user_workspace", lambda _: "workspace")
    monkeypatch.setattr(routes, "available", lambda _: None)
    payload = routes.BotInput(**bot_config())
    result = routes.save(payload, CurrentUser("user", None))
    assert result["enabled"] is False
    assert result["workspace_id"] == "workspace"


def test_business_information_requires_real_facts():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        routes.BotInput(business_name=" ", knowledge="This has enough characters but no name")
    with pytest.raises(ValidationError):
        routes.BotInput(business_name="Studio", knowledge="Short")


@pytest.mark.parametrize(
    "text", ["human", "Please talk to a person", "stop", "unsubscribe", "I need an agent"]
)
def test_human_request(text):
    assert chatbot.human_request(text)


def test_missing_migration_is_optional_but_other_database_errors_surface(monkeypatch):
    def unavailable(*args):
        raise APIError({"code": "PGRST205", "message": "table missing", "details": "", "hint": ""})

    monkeypatch.setattr(chatbot, "db", unavailable)
    assert chatbot.configuration("workspace") == (None, False)

    def denied(*args):
        raise APIError({"code": "42501", "message": "access denied", "details": "", "hint": ""})

    monkeypatch.setattr(chatbot, "db", denied)
    with pytest.raises(APIError):
        chatbot.configuration("workspace")


@pytest.mark.asyncio
async def test_groq_payload_is_business_scoped_and_preview_does_not_send(monkeypatch, settings):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"reply": "We open at 10am.", "handoff": False})
                        }
                    }
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        chatbot.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler)),
    )
    settings.groq_api_key = "test-key"
    result = await chatbot.generate(bot_config(), "When do you open?", settings)
    assert result == {"reply": "We open at 10am.", "handoff": False}
    assert str(requests[0].url) == "https://api.groq.com/openai/v1/chat/completions"
    payload = json.loads(requests[0].content)
    assert payload["response_format"]["type"] == "json_object"
    assert "Never invent prices" in payload["messages"][0]["content"]
    assert payload["messages"][-1]["content"] == "When do you open?"


@pytest.mark.asyncio
async def test_provider_error_never_exposes_response_content(monkeypatch, settings):
    async def handler(request):
        return httpx.Response(401, text="secret-key private customer information")

    original = httpx.AsyncClient
    monkeypatch.setattr(
        chatbot.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler)),
    )
    settings.groq_api_key = "test-key"
    with pytest.raises(chatbot.ChatbotError) as error:
        await chatbot.generate(bot_config(), "Hello", settings)
    assert "secret-key" not in str(error.value)
    assert "private customer" not in str(error.value)


def setup_ai(context, monkeypatch):
    store, event, rule, sent = context
    rule["enabled"] = False
    store.data["business_chatbots"] = [bot_config()]
    store.rpc = lambda *args: SimpleNamespace(execute=lambda: SimpleNamespace(data="run-1"))
    monkeypatch.setattr(chatbot, "db", lambda: store)
    return store, event, sent


@pytest.mark.asyncio
async def test_ai_only_sends_once_and_never_handles_comments(context, monkeypatch, settings):
    store, event, sent = setup_ai(context, monkeypatch)
    settings.groq_api_key = "test-key"

    async def answer(*args):
        return {"reply": "Our opening time is 10am.", "handoff": False}

    monkeypatch.setattr(chatbot, "generate", answer)
    await process_event(dict(event), settings)
    await process_event(dict(event), settings)
    assert len(sent) == 1
    assert event["detail"] == "AI reply sent"
    assert store.data["automation_deliveries"][0]["dedupe_key"] == "dm:one"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["paused", "old", "no_key", "limit", "customer_paused", "human"])
async def test_ineligible_ai_cannot_send(context, monkeypatch, settings, case):
    store, event, sent = setup_ai(context, monkeypatch)
    settings.groq_api_key = "test-key"
    if case == "paused":
        store.data["business_chatbots"][0]["enabled"] = False
    if case == "old":
        event["occurred_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    if case == "no_key":
        settings.groq_api_key = None
    if case == "limit":
        store.rpc = lambda *args: SimpleNamespace(execute=lambda: SimpleNamespace(data=None))
    if case == "customer_paused":
        store.data["chatbot_contacts"] = [
            {"connection_id": "conn", "sender_id": "customer", "paused": True}
        ]
    if case == "human":
        event["text"] = "talk to a person"

    async def forbidden(*args):
        raise AssertionError("AI must not be called")

    monkeypatch.setattr(chatbot, "generate", forbidden)
    await process_event(dict(event), settings)
    assert not sent


@pytest.mark.asyncio
async def test_pausing_during_generation_stops_delivery(context, monkeypatch, settings):
    store, event, sent = setup_ai(context, monkeypatch)
    settings.groq_api_key = "test-key"

    async def answer(*args):
        store.data["business_chatbots"][0]["enabled"] = False
        return {"reply": "A draft", "handoff": False}

    monkeypatch.setattr(chatbot, "generate", answer)
    await process_event(dict(event), settings)
    assert not sent
    assert event["status"] == "ignored"


@pytest.mark.asyncio
async def test_keyword_rule_keeps_priority_over_ai(context, monkeypatch, settings):
    store, event, rule, sent = context
    store.data["business_chatbots"] = [bot_config()]
    settings.groq_api_key = "test-key"

    async def forbidden(*args):
        raise AssertionError("Keyword rules must take priority")

    monkeypatch.setattr(chatbot, "generate", forbidden)
    await process_event(dict(event), settings)
    assert sent[0][2]["text"] == rule["reply_text"]
