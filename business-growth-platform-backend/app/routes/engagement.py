import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.automations import ingest, valid_signature
from app.chatbot import configuration, pause_contact
from app.config import Settings, get_settings
from app.database import db, one
from app.meta import InstagramClient, MetaAPIError
from app.read_cache import cached, invalidate, page
from app.routes.instagram import user_workspace
from app.security import CurrentUser, TokenCipher, current_user

router = APIRouter(prefix="/api/instagram", tags=["engagement"])
logger = logging.getLogger(__name__)


def connected(
    workspace_id: str, settings: Settings, scope: str | None = None
) -> tuple[InstagramClient, str, dict]:
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
    if scope and (not connection or scope not in (connection.get("granted_scopes") or [])):
        raise HTTPException(403, "Reconnect Instagram and approve the required permission")
    account = (
        one(
            db()
            .table("social_accounts")
            .select("*")
            .eq("workspace_id", workspace_id)
            .eq("connection_id", connection["id"])
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if connection
        else None
    )
    if not connection or not account:
        raise HTTPException(409, "Connect Instagram first")
    token = TokenCipher(settings.token_encryption_key).decrypt(connection["access_token_encrypted"])
    return InstagramClient(settings), token, account


def require(scope: str, workspace_id: str) -> None:
    row = one(
        db()
        .table("social_connections")
        .select("granted_scopes")
        .eq("workspace_id", workspace_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not row or scope not in (row.get("granted_scopes") or []):
        raise HTTPException(403, f"Reconnect Instagram and approve {scope}")


class MessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


async def read_connection(user, settings, request, scope=None):
    workspace_id = await asyncio.to_thread(user_workspace, user.id)
    client, token, account = await asyncio.to_thread(connected, workspace_id, settings, scope)
    client.http_client = getattr(request.app.state, "instagram_http", None)
    return workspace_id, client, token, account


@router.get("/media")
async def media(
    request: Request,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
    after: str | None = Query(default=None, max_length=4096),
    refresh: bool = False,
) -> dict:
    workspace, client, token, account = await read_connection(user, settings, request)

    async def load():
        return page(
            await client.get(
                "me/media",
                token,
                fields="id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,comments_count,like_count",
                limit=30,
                **({"after": after} if after else {}),
            )
        )

    return await cached(
        (workspace, account["connection_id"], account["provider_account_id"], "media", after),
        load,
        30,
        refresh,
    )


@router.get("/media/{media_id}/comments")
async def comments(
    media_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
    after: str | None = Query(default=None, max_length=4096),
    refresh: bool = False,
) -> dict:
    workspace, client, token, account = await read_connection(
        user, settings, request, "instagram_business_manage_comments"
    )

    async def load():
        result = page(
            await client.get(
                f"{media_id}/comments",
                token,
                fields="id,text,timestamp,username,from,like_count,hidden,replies{id,text,timestamp,username,from}",
                limit=30,
                **({"after": after} if after else {}),
            )
        )
        for comment in result.get("data", []):
            comment["username"] = comment.get("username") or (comment.get("from") or {}).get(
                "username"
            )
            for reply in (comment.get("replies") or {}).get("data", []):
                reply["username"] = reply.get("username") or (reply.get("from") or {}).get(
                    "username"
                )
        return result

    return await cached(
        (
            workspace,
            account["connection_id"],
            account["provider_account_id"],
            "comments",
            media_id,
            after,
        ),
        load,
        10,
        refresh,
    )


@router.post("/comments/{comment_id}/reply")
async def reply_comment(
    comment_id: str,
    payload: MessageBody,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    workspace_id = user_workspace(user.id)
    require("instagram_business_manage_comments", workspace_id)
    client, token, _ = connected(workspace_id, settings)
    invalidate(workspace_id)
    return await client.post(f"{comment_id}/replies", token, message=payload.message)


@router.post("/comments/{comment_id}/hide")
async def hide_comment(
    comment_id: str,
    hidden: bool = True,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    workspace_id = user_workspace(user.id)
    require("instagram_business_manage_comments", workspace_id)
    client, token, _ = connected(workspace_id, settings)
    invalidate(workspace_id)
    return await client.post(comment_id, token, hide=json.dumps(hidden))


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    workspace_id = user_workspace(user.id)
    require("instagram_business_manage_comments", workspace_id)
    client, token, _ = connected(workspace_id, settings)
    invalidate(workspace_id)
    return await client.delete(comment_id, token)


@router.get("/conversations")
async def conversations(
    request: Request,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
    after: str | None = Query(default=None, max_length=4096),
    refresh: bool = False,
) -> dict:
    workspace, client, token, account = await read_connection(
        user, settings, request, "instagram_business_manage_messages"
    )

    async def load():
        return page(
            await client.get(
                f"{account['provider_account_id']}/conversations",
                token,
                platform="instagram",
                fields="id,updated_time,participants,messages.limit(1){id,created_time,from,to,message}",
                limit=25,
                **({"after": after} if after else {}),
            )
        )

    return await cached(
        (
            workspace,
            account["connection_id"],
            account["provider_account_id"],
            "conversations",
            after,
        ),
        load,
        10,
        refresh,
    )


@router.get("/conversations/{conversation_id}/messages")
async def messages(
    conversation_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
    after: str | None = Query(default=None, max_length=4096),
    refresh: bool = False,
) -> dict:
    workspace, client, token, account = await read_connection(
        user, settings, request, "instagram_business_manage_messages"
    )

    async def load():
        params = {"limit": 30, **({"after": after} if after else {})}
        try:
            return page(
                await client.get(
                    f"{conversation_id}/messages",
                    token,
                    fields="id,created_time,from,to,message,attachments,shares",
                    **params,
                )
            )
        except MetaAPIError:
            result = page(
                await client.get(
                    f"{conversation_id}/messages",
                    token,
                    fields="id,created_time,from,to,message",
                    **params,
                )
            )
            result["attachments_unavailable"] = True
            return result

    return await cached(
        (
            workspace,
            account["connection_id"],
            account["provider_account_id"],
            "messages",
            conversation_id,
            after,
        ),
        load,
        5,
        refresh,
    )


@router.post("/messages/{recipient_id}")
async def send_message(
    recipient_id: str,
    payload: MessageBody,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    workspace_id = user_workspace(user.id)
    require("instagram_business_manage_messages", workspace_id)
    client, token, account = connected(workspace_id, settings)
    invalidate(workspace_id)
    bot, _ = configuration(workspace_id)
    if bot and bot["enabled"]:
        pause_contact(
            {
                "workspace_id": workspace_id,
                "connection_id": account["connection_id"],
                "sender_id": recipient_id,
            },
            "Team member replied manually; AI paused",
        )
    return await client.post(
        f"{account['provider_account_id']}/messages",
        token,
        recipient=json.dumps({"id": recipient_id}),
        message=json.dumps({"text": payload.message}),
    )


@router.get("/insights")
async def insights(
    request: Request,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
    refresh: bool = False,
) -> dict:
    workspace, client, token, account = await read_connection(
        user, settings, request, "instagram_business_manage_insights"
    )

    async def load():
        async def metrics():
            try:
                return await client.get(
                    f"{account['provider_account_id']}/insights",
                    token,
                    metric="reach,views,profile_views",
                    period="day",
                    metric_type="total_value",
                )
            except MetaAPIError:
                return {"data": []}

        profile, values = await asyncio.gather(
            client.get(
                account["provider_account_id"],
                token,
                fields="followers_count,follows_count,media_count,name,username",
            ),
            metrics(),
        )
        return {"profile": profile, "metrics": values.get("data", [])}

    return await cached(
        (workspace, account["connection_id"], account["provider_account_id"], "insights"),
        load,
        60,
        refresh,
    )


@router.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
    settings: Settings = Depends(get_settings),
):
    if hub_mode != "subscribe" or hub_verify_token != settings.instagram_webhook_verify_token:
        raise HTTPException(403, "Webhook verification failed")
    return PlainTextResponse(hub_challenge)


@router.post("/webhook")
async def receive_webhook(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1024 * 1024:
            raise HTTPException(413, "Webhook payload is too large")
    if not valid_signature(
        body,
        request.headers.get("x-hub-signature-256", ""),
        settings.meta_webhook_app_secret or settings.meta_app_secret,
    ):
        raise HTTPException(403, "Invalid webhook signature")
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise TypeError("Invalid webhook object")
        await asyncio.to_thread(ingest, payload)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise HTTPException(400, "Malformed Instagram event") from None
    except Exception:  # noqa: BLE001 - a failed durable write must trigger Meta redelivery
        logger.warning("Could not persist Instagram webhook event")
        raise HTTPException(503, "Event storage unavailable; retry delivery") from None
    return {"received": True}
