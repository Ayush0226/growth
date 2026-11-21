from functools import lru_cache

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    meta_app_id: str
    meta_app_secret: str
    meta_webhook_app_secret: str | None = None
    meta_graph_api_version: str
    instagram_redirect_uri: HttpUrl
    supabase_url: HttpUrl
    supabase_service_role_key: str
    token_encryption_key: str = Field(min_length=32)
    frontend_url: HttpUrl
    additional_frontend_origins: str = ""

    def cors_origins(self) -> list[str]:
        from urllib.parse import urlsplit

        origins = [str(self.frontend_url).rstrip("/")]
        for raw in self.additional_frontend_origins.split(","):
            origin = raw.strip().rstrip("/")
            if not origin:
                continue
            parsed = urlsplit(origin)
            if (parsed.scheme not in {"https", "http"} or not parsed.hostname
                    or parsed.username or parsed.password or parsed.path
                    or parsed.query or parsed.fragment or "*" in origin):
                raise ValueError("Additional frontend origins must be exact HTTP(S) origins")
            origins.append(origin)
        return list(dict.fromkeys(origins))

    cron_secret: str = "development-only"
    instagram_webhook_verify_token: str = "growthboard-webhook"
    ai_provider_api_key: str | None = None
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    pilot_access_code: SecretStr | None = None
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = Field(default=30, ge=10, le=300)
    whatsapp_enabled: bool = False
    whatsapp_app_id: str | None = None
    whatsapp_app_secret: str | None = None
    whatsapp_signup_config_id: str | None = None
    whatsapp_webhook_verify_token: str | None = None
    google_enabled: bool = False
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    google_redirect_uri: HttpUrl | None = None
    google_frontend_url: HttpUrl = "https://growboard.in"
    google_worker_enabled: bool = False
    google_mcp_enabled: bool = False
    google_mcp_resource_url: HttpUrl = "https://business-growth-platform-api.onrender.com/mcp"
    google_pubsub_audience: str | None = None
    google_pubsub_service_account: str | None = None
    serpapi_key: SecretStr | None = None
    cloudflare_account_id: str | None = None
    cloudflare_api_token: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
