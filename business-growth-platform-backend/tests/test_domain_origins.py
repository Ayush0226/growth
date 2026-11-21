import pytest

from app.config import Settings


def settings(**overrides):
    return Settings(_env_file=None, meta_app_id="test", meta_app_secret="test",
                    meta_graph_api_version="v26.0", instagram_redirect_uri="https://api.example.com/callback",
                    supabase_url="https://example.supabase.co", supabase_service_role_key="test",
                    token_encryption_key="test-only-encryption-key-at-least-32-characters",
                    frontend_url="https://growthboard-web.onrender.com", **overrides)


def test_preserves_existing_site_and_allows_new_exact_origins():
    config = settings(additional_frontend_origins="https://growboard.in, https://www.growboard.in/,https://growboard.in")
    assert config.cors_origins() == ["https://growthboard-web.onrender.com", "https://growboard.in", "https://www.growboard.in"]


@pytest.mark.parametrize("origin", ["*", "https://*.example.com", "https://example.com/path",
                                  "https://user:password@example.com", "https://example.com?x=1",
                                  "javascript:alert(1)"])
def test_rejects_unsafe_or_non_origin_values(origin):
    with pytest.raises(ValueError):
        settings(additional_frontend_origins=origin).cors_origins()
