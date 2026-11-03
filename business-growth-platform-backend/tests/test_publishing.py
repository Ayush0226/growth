from types import SimpleNamespace

import httpx
import pytest
from test_automations import Store

from app import publishing
from app.config import Settings
from app.meta import InstagramClient, MetaAPIError
from app.security import TokenCipher


@pytest.fixture
def publishing_context(monkeypatch):
    settings = Settings(
        _env_file=None,
        meta_app_id="app",
        meta_app_secret="secret",
        meta_graph_api_version="v24.0",
        instagram_redirect_uri="https://example.test/callback",
        frontend_url="https://example.test",
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="test",
        token_encryption_key="isolated-test-key-12345678901234567890",
    )
    store = Store(
        {
            "publishing_jobs": [
                {
                    "id": "job",
                    "workspace_id": "workspace",
                    "status": "scheduled",
                    "attempt_count": 0,
                    "content_target_id": "target",
                }
            ],
            "content_targets": [
                {"id": "target", "draft_id": "draft", "social_account_id": "account"}
            ],
            "content_drafts": [
                {"id": "draft", "caption": "An approved post", "status": "approved"}
            ],
            "social_accounts": [
                {"id": "account", "connection_id": "connection", "provider_account_id": "ig"}
            ],
            "social_connections": [
                {
                    "id": "connection",
                    "status": "active",
                    "active_account_id": "ig",
                    "granted_scopes": ["instagram_business_content_publish"],
                    "access_token_encrypted": TokenCipher(settings.token_encryption_key).encrypt(
                        "test-token"
                    ),
                }
            ],
            "content_draft_media": [
                {"draft_id": "draft", "media_asset_id": "asset", "position": 0}
            ],
            "media_assets": [
                {"id": "asset", "validation_status": "valid", "prepared_storage_path": "image.jpg"}
            ],
        }
    )
    store.storage = SimpleNamespace(
        from_=lambda name: SimpleNamespace(
            create_signed_url=lambda *a: {"signedURL": "https://example.test/image.jpg"}
        )
    )
    monkeypatch.setattr(publishing, "db", lambda: store)
    return store, settings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["success", "permalink_timeout", "publish_timeout", "create_failure"]
)
async def test_publication_result_survives_optional_failure_and_uncertainty_is_not_retried(
    publishing_context, monkeypatch, mode
):
    store, settings = publishing_context
    attempts = []

    def transport(request):
        path = request.url.path
        if path.endswith("/media"):
            if mode == "create_failure":
                return httpx.Response(
                    503, json={"error": {"message": "Temporary creation failure"}}
                )
            return httpx.Response(200, json={"id": "container"})
        if path.endswith("/container"):
            return httpx.Response(200, json={"status_code": "FINISHED"})
        if path.endswith("/media_publish"):
            attempts.append("publication")
            if mode == "publish_timeout":
                raise httpx.ReadTimeout("Uncertain response", request=request)
            return httpx.Response(200, json={"id": "published-media"})
        if mode == "permalink_timeout":
            raise httpx.ReadTimeout("Metadata unavailable", request=request)
        return httpx.Response(
            200, json={"id": "published-media", "permalink": "https://instagram.com/p/example"}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        publishing.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(transport)),
    )
    if mode in {"create_failure", "publish_timeout"}:
        with pytest.raises((httpx.ReadTimeout, MetaAPIError)):
            await publishing.publish_job("job", "workspace", settings)
    else:
        result = await publishing.publish_job("job", "workspace", settings)
        assert result["status"] == "published"
        await publishing.publish_job("job", "workspace", settings)
        assert attempts == ["publication"]
    job = store.data["publishing_jobs"][0]
    if mode == "publish_timeout":
        assert job["status"] == "processing"
        assert job["failure_code"] == "publication_uncertain"
        with pytest.raises(ValueError):
            await publishing.publish_job("job", "workspace", settings)
        assert len(attempts) == 1
    if mode == "create_failure":
        assert job["status"] == "failed"
        assert not attempts


def test_default_oauth_requests_core_permissions_and_exact_redirect(publishing_context):
    from urllib.parse import parse_qs, urlparse

    _, settings = publishing_context
    client = InstagramClient(settings)
    query = parse_qs(urlparse(client.authorization_url("random-state")).query)
    assert query["redirect_uri"] == ["https://example.test/callback"]
    assert "instagram_business_manage_messages" in query["scope"][0]
    assert "instagram_business_manage_insights" not in query["scope"][0]
    assert (
        "instagram_business_manage_insights"
        in parse_qs(urlparse(client.authorization_url("random-state", True)).query)["scope"][0]
    )
