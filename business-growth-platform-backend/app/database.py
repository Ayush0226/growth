from functools import lru_cache
from typing import Any

from app.config import get_settings
from supabase import Client, ClientOptions, create_client


@lru_cache
def db() -> Client:
    settings = get_settings()
    return create_client(
        str(settings.supabase_url),
        settings.supabase_service_role_key,
        options=ClientOptions(postgrest_client_timeout=10, storage_client_timeout=20),
    )


def one(result: Any) -> dict[str, Any] | None:
    data = result.data
    return data[0] if isinstance(data, list) and data else None
