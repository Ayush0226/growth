from functools import lru_cache
from typing import Any

import httpx

from app.config import get_settings
from supabase import Client, ClientOptions, create_client


@lru_cache
def db() -> Client:
    settings = get_settings()
    return create_client(
        str(settings.supabase_url),
        settings.supabase_service_role_key,
        options=ClientOptions(
            postgrest_client_timeout=10,
            storage_client_timeout=20,
            httpx_client=httpx.Client(
                http2=False,
                timeout=10,
                limits=httpx.Limits(
                    max_connections=20, max_keepalive_connections=5, keepalive_expiry=15
                ),
            ),
        ),
    )


def one(result: Any) -> dict[str, Any] | None:
    data = result.data
    return data[0] if isinstance(data, list) and data else None
