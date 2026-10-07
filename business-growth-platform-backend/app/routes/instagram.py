import logging
from datetime import UTC, datetime, timedelta

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
        .select("id,status,granted_scopes")
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
            .select("username,account_type")
            .eq("connection_id", connection["id"])
            .limit(1)
            .execute()
        )
        or {}
    )
    scopes = connection.get("granted_scopes") or []
    return {
        "connected": True,
        **account,
        "granted_permissions": scopes,
        "publishing_enabled": "instagram_business_content_publish" in scopes,
        "comments_enabled": "instagram_business_manage_comments" in scopes,
        "messages_enabled": "instagram_business_manage_messages" in scopes,
        "insights_enabled": "instagram_business_manage_insights" in scopes,
    }


@router.post("/connect")
def connect(
    user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)
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
    return {"authorization_url": InstagramClient(settings).authorization_url(raw_state)}


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
    db().table("oauth_states").update({"consumed_at": datetime.now(UTC).isoformat()}).eq(
        "id", saved["id"]
    ).execute()
    if error or not code:
        outcome = "cancelled" if error_reason == "user_denied" else "failed"
        return RedirectResponse(f"{frontend}/settings/connections?instagram={outcome}")
    client = InstagramClient(settings)
    try:
        short = await client.exchange_code(code)
        token, expires_in = await client.exchange_long_lived(short.access_token)
        profile = await client.profile(token)
        permissions = short.permissions or set(MVP_SCOPES)
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
            },
            on_conflict="connection_id,provider_account_id",
        ).execute()
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
    except (MetaAPIError, KeyError, ValueError):
        logger.exception("Instagram OAuth callback failed")
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
    db().table("publishing_jobs").update(
        {"status": "cancelled", "failure_code": "connection_disconnected"}
    ).eq("workspace_id", workspace_id).in_("status", ["scheduled", "processing"]).execute()
    try:
        await InstagramClient(settings).revoke(
            TokenCipher(settings.token_encryption_key).decrypt(connection["access_token_encrypted"])
        )
    except (MetaAPIError, ValueError):
        logger.warning("Meta revoke failed during disconnect", exc_info=True)
    db().table("social_connections").update(
        {
            "status": "revoked",
            "access_token_encrypted": None,
            "token_expires_at": None,
            "disconnected_at": datetime.now(UTC).isoformat(),
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
