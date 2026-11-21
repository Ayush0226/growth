import asyncio
import time
from types import SimpleNamespace

import jwt
import pytest

pytest.importorskip("mcp.server.mcpserver", reason="This port targets the pinned MCP 2 SDK")
from app.gbp import mcp as module
from test_domain_origins import settings


def test_mcp_registers_all_twenty_tools_without_provider_token_inputs():
    server, _app = module.create_server(settings())
    tools = asyncio.run(server.list_tools())
    assert len(tools) == 20
    names = {tool.name for tool in tools}
    assert {"list_locations", "publish_review_reply", "schedule_post", "generate_local_rank_report",
            "configure_review_automation_rule", "create_content_campaign"} <= names
    for tool in tools:
        fields = tool.input_schema.get("properties", {})
        assert not ({"user_id", "access_token", "provider_token", "refresh_token"} & fields.keys())
    public_write = next(tool for tool in tools if tool.name == "publish_review_reply")
    assert public_write.annotations.read_only_hint is False
    public_read = next(tool for tool in tools if tool.name == "list_locations")
    assert public_read.annotations.read_only_hint is True
    assert public_read.annotations.open_world_hint is False


def test_mcp_rejects_browser_tokens_and_rechecks_pilot_access(monkeypatch):
    user = SimpleNamespace(id="owner", email="owner@example.test")
    monkeypatch.setattr(module,"db",lambda:SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=user))))
    monkeypatch.setattr(module,"access_state",lambda user_id:(True,False,False))
    secret="test-only-secret-for-token-fixture"
    browser=jwt.encode({"exp":int(time.time())+300},secret,algorithm="HS256")
    oauth=jwt.encode({"exp":int(time.time())+300,"client_id":"approved-client"},secret,algorithm="HS256")
    assert asyncio.run(module.Verifier().verify_token(browser)) is None
    assert asyncio.run(module.Verifier().verify_token(oauth)).subject == "owner"
    monkeypatch.setattr(module,"access_state",lambda user_id:(False,False,False))
    assert asyncio.run(module.Verifier().verify_token(oauth)) is None
