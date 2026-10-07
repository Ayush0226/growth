from functools import lru_cache

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    meta_app_id: str
    meta_app_secret: str
    meta_graph_api_version: str
    instagram_redirect_uri: HttpUrl
    supabase_url: HttpUrl
    supabase_service_role_key: str
    token_encryption_key: str = Field(min_length=32)
    frontend_url: HttpUrl
    cron_secret: str = "development-only"
    instagram_webhook_verify_token: str = "growthboard-webhook"
    ai_provider_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
