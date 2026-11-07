from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import Settings

MVP_SCOPES = (
    "instagram_business_basic",
    "instagram_business_content_publish",
    "instagram_business_manage_comments",
    "instagram_business_manage_messages",
)


@dataclass
class InstagramToken:
    access_token: str
    user_id: str
    permissions: set[str] | None = None


class MetaAPIError(RuntimeError):
    pass


class InstagramClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.http_client = http_client

    def authorization_url(self, state: str, include_insights: bool = False) -> str:
        query = urlencode(
            {
                "client_id": self.settings.meta_app_id,
                "redirect_uri": str(self.settings.instagram_redirect_uri),
                "response_type": "code",
                "scope": ",".join(
                    (*MVP_SCOPES, "instagram_business_manage_insights")
                    if include_insights
                    else MVP_SCOPES
                ),
                "state": state,
                "enable_fb_login": "0",
                "force_authentication": "1",
            }
        )
        return f"https://www.instagram.com/oauth/authorize?{query}"

    async def exchange_code(self, code: str) -> InstagramToken:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": self.settings.meta_app_id,
                    "client_secret": self.settings.meta_app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": str(self.settings.instagram_redirect_uri),
                    "code": code,
                },
            )
        data = self._json(response)
        if (
            "access_token" not in data
            and isinstance(data.get("data"), list)
            and len(data["data"]) == 1
        ):
            data = data["data"][0]
        raw_permissions = (
            data.get("permissions") or data.get("scope") or data.get("granted_permissions")
        )
        if isinstance(raw_permissions, str):
            permissions = {item for item in raw_permissions.split(",") if item}
        elif isinstance(raw_permissions, list):
            permissions = set(raw_permissions)
        else:
            permissions = None
        return InstagramToken(
            access_token=data["access_token"],
            user_id=str(data["user_id"]),
            permissions=permissions,
        )

    async def exchange_long_lived(self, short_token: str) -> tuple[str, int | None]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": self.settings.meta_app_secret,
                    "access_token": short_token,
                },
            )
        data = self._json(response)
        return data["access_token"], data.get("expires_in")

    async def profile(self, token: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://graph.instagram.com/{self.settings.meta_graph_api_version}/me",
                params={
                    "fields": "user_id,username,account_type,profile_picture_url",
                    "access_token": token,
                },
            )
        return self._json(response)

    async def get(self, path: str, token: str, **params) -> dict:
        if self.http_client is not None:
            response = await self.http_client.get(
                f"https://graph.instagram.com/{self.settings.meta_graph_api_version}/{path.lstrip('/')}",
                params={**params, "access_token": token},
            )
            return self._json(response)
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(
                f"https://graph.instagram.com/{self.settings.meta_graph_api_version}/{path.lstrip('/')}",
                params={**params, "access_token": token},
            )
        return self._json(response)

    async def post(self, path: str, token: str, **data) -> dict:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                f"https://graph.instagram.com/{self.settings.meta_graph_api_version}/{path.lstrip('/')}",
                data={**data, "access_token": token},
            )
        return self._json(response)

    async def delete(self, path: str, token: str) -> dict:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.delete(
                f"https://graph.instagram.com/{self.settings.meta_graph_api_version}/{path.lstrip('/')}",
                params={"access_token": token},
            )
        return self._json(response)

    async def revoke(self, token: str) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.delete(
                f"https://graph.instagram.com/{self.settings.meta_graph_api_version}/me/permissions",
                params={"access_token": token},
            )
        if response.status_code >= 400:
            raise MetaAPIError("Meta authorization could not be revoked")

    async def permissions(self, token: str) -> set[str]:
        result = await self.get("me/permissions", token)
        return {
            item["permission"]
            for item in result.get("data", [])
            if item.get("status") == "granted" and item.get("permission")
        }

    async def subscribe(self, account_id: str, token: str, permissions: set[str]) -> dict:
        fields = []
        if "instagram_business_manage_messages" in permissions:
            fields.append("messages")
        if "instagram_business_manage_comments" in permissions:
            fields.append("comments")
        if not fields:
            raise MetaAPIError("Messaging or comment permission is required for events")
        return await self.post(
            f"{account_id}/subscribed_apps", token, subscribed_fields=",".join(fields)
        )

    @staticmethod
    def _json(response: httpx.Response) -> dict:
        try:
            data = response.json()
        except ValueError as exc:
            raise MetaAPIError("Meta returned an unreadable response") from exc
        if response.status_code >= 400 or "error" in data:
            error = data.get("error", {})
            raise MetaAPIError(error.get("message", "Meta request failed"))
        return data
