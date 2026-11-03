import logging
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.config import Settings, get_settings
from app.database import db, one
from app.meta import MVP_SCOPES, InstagramClient, MetaAPIError
from app.security import (
    CurrentUser,
    TokenCipher,
    current_user,
    generate_oauth_state,
    hash_oauth_state,
)

router = APIRouter(prefix="/api/integrations/instagram", tags=["instagram"])
logger = logging.getLogger(__name__)


def user_workspace(user_id: str) -> str:
    member = one(
        db()
        .table("workspace_members")
        .select("workspace_id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not member:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Create a workspace before connecting Instagram"
        )
    return member["workspace_id"]


@router.get("")
def connection_status(user: CurrentUser = Depends(current_user)) -> dict:
    workspace_id = user_workspace(user.id)
    connection = one(
        db()
        .table("social_connections")
        .select(
            "id,status,granted_scopes,token_expires_at,webhook_subscribed,webhook_error,active_account_id"
        )
        .eq("workspace_id", workspace_id)
        .eq("provider", "instagram")
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not connection:
        return {"connected": False}
    account = (
        one(
            db()
            .table("social_accounts")
            .select("username,account_type,provider_account_id")
            .eq("connection_id", connection["id"])
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        or {}
    )
    scopes = connection.get("granted_scopes") or []
    latest_event = one(
        db()
        .table("automation_events")
        .select("received_at")
        .eq("workspace_id", workspace_id)
        .eq("connection_id", connection["id"])
        .order("received_at", desc=True)
        .limit(1)
        .execute()
    )
    return {
        "connected": True,
        **account,
        "token_expires_at": connection.get("token_expires_at"),
        "webhook_subscribed": connection.get("webhook_subscribed", False),
        "last_event_received_at": latest_event.get("received_at") if latest_event else None,
        "webhook_error": connection.get("webhook_error"),
        "granted_permissions": scopes,
        "publishing_enabled": "instagram_business_content_publish" in scopes,
        "comments_enabled": "instagram_business_manage_comments" in scopes,
        "messages_enabled": "instagram_business_manage_messages" in scopes,
        "insights_enabled": "instagram_business_manage_insights" in scopes,
    }


@router.post("/connect")
def connect(
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
    include_insights: bool = False,
) -> dict:
    workspace_id = user_workspace(user.id)
    raw_state, state_hash = generate_oauth_state()
    db().table("oauth_states").insert(
        {
            "workspace_id": workspace_id,
            "user_id": user.id,
            "provider": "instagram",
            "state_hash": state_hash,
            "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        }
    ).execute()
    return {
        "authorization_url": InstagramClient(settings).authorization_url(
            raw_state, include_insights
        )
    }


@router.get("/configuration")
def configuration(
    user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)
):
    callback = str(settings.instagram_redirect_uri)
    return {
        "redirect_uri": callback,
        "webhook_url": callback.rsplit("/", 1)[0].replace("/integrations/instagram", "/instagram")
        + "/webhook",
        "requested_scopes": list(MVP_SCOPES),
        "scheduler_enabled": settings.scheduler_enabled,
    }


@router.post("/subscribe")
async def subscribe(
    user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)
):
    workspace = user_workspace(user.id)
    connection = one(
        db()
        .table("social_connections")
        .select("*")
        .eq("workspace_id", workspace)
        .eq("status", "active")
        .execute()
    )
    if not connection:
        raise HTTPException(409, "Connect Instagram first")
    account = one(
        db()
        .table("social_accounts")
        .select("provider_account_id")
        .eq("connection_id", connection["id"])
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    try:
        result = await InstagramClient(settings).subscribe(
            account["provider_account_id"],
            TokenCipher(settings.token_encryption_key).decrypt(
                connection["access_token_encrypted"]
            ),
            set(connection["granted_scopes"]),
        )
        if not result.get("success"):
            raise MetaAPIError("Instagram did not confirm the subscription")
    except (MetaAPIError, httpx.HTTPError):
        db().table("social_connections").update(
            {
                "webhook_subscribed": False,
                "webhook_error": "Check Meta Instagram webhook configuration and reconnect permissions.",
            }
        ).eq("id", connection["id"]).execute()
        raise HTTPException(
            409, "Instagram event subscription failed. Check Meta webhook settings and permissions."
        ) from None
    db().table("social_connections").update({"webhook_subscribed": True, "webhook_error": None}).eq(
        "id", connection["id"]
    ).execute()
    return {"subscribed": True}


@router.get("/callback")
async def callback(
    state: str,
    code: str | None = None,
    error: str | None = None,
    error_reason: str | None = None,
    settings: Settings = Depends(get_settings),
):
    frontend = str(settings.frontend_url).rstrip("/")
    query = (
        db()
        .table("oauth_states")
        .select("*")
        .eq("state_hash", hash_oauth_state(state))
        .eq("provider", "instagram")
        .is_("consumed_at", "null")
        .limit(1)
        .execute()
    )
    saved = one(query)
    if not saved or datetime.fromisoformat(saved["expires_at"]) < datetime.now(UTC):
        return RedirectResponse(f"{frontend}/settings/connections?instagram=invalid_state")
    consumed = (
        db()
        .table("oauth_states")
        .update({"consumed_at": datetime.now(UTC).isoformat()})
        .is_("consumed_at", "null")
        .eq("id", saved["id"])
        .execute()
    )
    if not consumed.data:
        return RedirectResponse(f"{frontend}/settings/connections?instagram=invalid_state")
    if error or not code:
        outcome = "cancelled" if error_reason == "user_denied" else "failed"
        return RedirectResponse(f"{frontend}/settings/connections?instagram={outcome}")
    client = InstagramClient(settings)
    try:
        short = await client.exchange_code(code)
        token, expires_in = await client.exchange_long_lived(short.access_token)
        profile = await client.profile(token)
        if short.permissions is not None:
            permissions = short.permissions
        else:
            try:
                permissions = await client.permissions(token)
            except MetaAPIError:
                permissions = set()
        cipher = TokenCipher(settings.token_encryption_key)
        expires_at = (
            (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat() if expires_in else None
        )
        connection_result = (
            db()
            .table("social_connections")
            .upsert(
                {
                    "workspace_id": saved["workspace_id"],
                    "provider": "instagram",
                    "status": "active",
                    "access_token_encrypted": cipher.encrypt(token),
                    "token_expires_at": expires_at,
                    "granted_scopes": sorted(permissions),
                    "connected_by": saved["user_id"],
                    "active_account_id": str(
                        profile.get("user_id") or profile.get("id") or short.user_id
                    ),
                },
                on_conflict="workspace_id,provider",
            )
            .execute()
        )
        connection = one(connection_result)
        if not connection:
            connection = one(
                db()
                .table("social_connections")
                .select("id")
                .eq("workspace_id", saved["workspace_id"])
                .eq("provider", "instagram")
                .execute()
            )
        db().table("social_accounts").upsert(
            {
                "workspace_id": saved["workspace_id"],
                "connection_id": connection["id"],
                "provider_account_id": str(
                    profile.get("user_id") or profile.get("id") or short.user_id
                ),
                "username": profile.get("username"),
                "account_type": profile.get("account_type"),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            on_conflict="connection_id,provider_account_id",
        ).execute()
        current_id = str(profile.get("user_id") or profile.get("id") or short.user_id)
        try:
            subscription = await client.subscribe(current_id, token, permissions)
            subscribed = subscription.get("success") is True
        except (MetaAPIError, httpx.HTTPError):
            subscribed = False
        db().table("social_connections").update(
            {
                "webhook_subscribed": subscribed,
                "webhook_error": None
                if subscribed
                else "Enable messages and comments webhooks in Meta, then retry event delivery.",
            }
        ).eq("id", connection["id"]).execute()
        permission_rows = [
            {
                "workspace_id": saved["workspace_id"],
                "connection_id": connection["id"],
                "permission": scope,
                "status": "granted" if scope in permissions else "declined",
            }
            for scope in MVP_SCOPES
        ]
        db().table("social_permissions").upsert(
            permission_rows, on_conflict="connection_id,permission"
        ).execute()
        db().table("audit_events").insert(
            {
                "workspace_id": saved["workspace_id"],
                "actor_user_id": saved["user_id"],
                "event_type": "instagram.connected",
                "metadata": {
                    "username": profile.get("username"),
                    "permissions": sorted(permissions),
                },
            }
        ).execute()
    except (MetaAPIError, httpx.HTTPError, KeyError, ValueError):
        logger.warning(
            "Instagram OAuth callback failed; check Meta configuration and database migrations"
        )
        return RedirectResponse(f"{frontend}/settings/connections?instagram=failed")
    outcome = "connected" if "instagram_business_content_publish" in permissions else "limited"
    return RedirectResponse(f"{frontend}/settings/connections?instagram={outcome}")


@router.post("/disconnect")
async def disconnect(
    user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)
) -> dict:
    workspace_id = user_workspace(user.id)
    connection = one(
        db()
        .table("social_connections")
        .select("*")
        .eq("workspace_id", workspace_id)
        .eq("provider", "instagram")
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not connection:
        return {"status": "already_disconnected"}
    db().table("automation_rules").update({"enabled": False}).eq(
        "workspace_id", workspace_id
    ).execute()
    db().table("automation_events").update(
        {"status": "ignored", "detail": "Instagram disconnected"}
    ).eq("workspace_id", workspace_id).eq("status", "pending").execute()
    db().table("publishing_jobs").update(
        {"status": "cancelled", "failure_code": "connection_disconnected"}
    ).eq("workspace_id", workspace_id).in_("status", ["scheduled", "processing"]).execute()
    try:
        await InstagramClient(settings).revoke(
            TokenCipher(settings.token_encryption_key).decrypt(connection["access_token_encrypted"])
        )
    except (MetaAPIError, httpx.HTTPError, ValueError):
        logger.warning("Meta revoke failed during disconnect")
    db().table("social_connections").update(
        {
            "status": "revoked",
            "access_token_encrypted": None,
            "token_expires_at": None,
            "disconnected_at": datetime.now(UTC).isoformat(),
            "webhook_subscribed": False,
        }
    ).eq("id", connection["id"]).execute()
    db().table("audit_events").insert(
        {
            "workspace_id": workspace_id,
            "actor_user_id": user.id,
            "event_type": "instagram.disconnected",
            "metadata": {},
        }
    ).execute()
    return {"status": "disconnected"}
