import asyncio
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.chatbot import ChatbotError, configuration, generate
from app.config import Settings, get_settings
from app.database import db, one
from app.routes.engagement import connected
from app.routes.instagram import user_workspace
from app.security import CurrentUser, current_user

router = APIRouter(prefix="/api/chatbot", tags=["business chatbot"])


class BotInput(BaseModel):
    business_name: str = Field(min_length=1, max_length=120)
    role: Literal["support", "sales", "feedback"] = "support"
    knowledge: str = Field(min_length=20, max_length=12000)
    instructions: str = Field(default="", max_length=2000)
    handoff_message: str = Field(
        default="Thanks! A team member will help you here shortly.", min_length=1, max_length=500
    )
    daily_limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def trim(self):
        self.business_name = self.business_name.strip()
        self.knowledge = self.knowledge.strip()
        self.handoff_message = self.handoff_message.strip()
        if not self.business_name or len(self.knowledge) < 20 or not self.handoff_message:
            raise ValueError(
                "Add the business name, at least 20 characters of business information, and a handoff message"
            )
        return self


def available(workspace: str):
    config, ready = configuration(workspace)
    if not ready:
        raise HTTPException(
            503,
            "AI setup is being completed by your administrator. Your existing automations still work.",
        )
    return config


@router.get("")
def status(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    workspace = user_workspace(user.id)
    config, ready = configuration(workspace)
    contacts = (
        db()
        .table("chatbot_contacts")
        .select("connection_id,sender_id,reason,updated_at")
        .eq("workspace_id", workspace)
        .eq("paused", True)
        .order("updated_at", desc=True)
        .limit(50)
        .execute()
        .data
        if ready
        else []
    )
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = {}
    for purpose in ("live", "preview"):
        used[purpose] = (
            (
                db()
                .table("chatbot_runs")
                .select("id", count="exact")
                .eq("workspace_id", workspace)
                .eq("purpose", purpose)
                .gte("created_at", today)
                .execute()
                .count
                or 0
            )
            if ready
            else 0
        )
    return {
        "config": config,
        "setup_ready": ready,
        "provider_ready": bool(settings.groq_api_key),
        "provider": "Groq",
        "paused_contacts": contacts,
        "usage": used,
    }


@router.put("")
def save(payload: BotInput, user: CurrentUser = Depends(current_user)):
    workspace = user_workspace(user.id)
    available(workspace)
    # Editing always pauses live replies, including requests from modified clients.
    return one(
        db()
        .table("business_chatbots")
        .upsert(
            {
                **payload.model_dump(),
                "workspace_id": workspace,
                "enabled": False,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            on_conflict="workspace_id",
        )
        .execute()
    )


class Toggle(BaseModel):
    enabled: bool
    updated_at: str


@router.post("/enabled")
def enable(
    payload: Toggle,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    workspace = user_workspace(user.id)
    config = available(workspace)
    if not config:
        raise HTTPException(409, "Save your business information first")
    if payload.enabled:
        if not settings.groq_api_key:
            raise HTTPException(409, "Groq setup is incomplete. Contact your administrator.")
        _, _, account = connected(workspace, settings, "instagram_business_manage_messages")
        conn = one(
            db()
            .table("social_connections")
            .select("webhook_subscribed")
            .eq("id", account["connection_id"])
            .execute()
        )
        if not conn or not conn.get("webhook_subscribed"):
            raise HTTPException(409, "Check your Instagram connection before enabling AI replies")
    updated = one(
        db()
        .table("business_chatbots")
        .update({"enabled": payload.enabled, "updated_at": datetime.now(UTC).isoformat()})
        .eq("workspace_id", workspace)
        .eq("updated_at", payload.updated_at)
        .execute()
    )
    if not updated:
        raise HTTPException(409, "The business settings changed. Refresh and review them again.")
    return updated


class Preview(BotInput):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/preview")
async def preview(
    payload: Preview,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    workspace = await asyncio.to_thread(user_workspace, user.id)
    await asyncio.to_thread(available, workspace)
    if not settings.groq_api_key:
        raise HTTPException(409, "Groq setup is incomplete. Contact your administrator.")
    run = await asyncio.to_thread(
        lambda: (
            db()
            .rpc(
                "reserve_chatbot_run",
                {"p_workspace": workspace, "p_purpose": "preview", "p_event": None},
            )
            .execute()
            .data
        )
    )
    if not run:
        raise HTTPException(
            429, "Today's 20 AI previews have been used. Try again after midnight UTC."
        )
    try:
        answer = await generate(payload.model_dump(), payload.text, settings)
    except ChatbotError as exc:
        await asyncio.to_thread(
            lambda: db().table("chatbot_runs").update({"status": "failed"}).eq("id", run).execute()
        )
        raise HTTPException(502, str(exc)) from exc
    await asyncio.to_thread(
        lambda: db().table("chatbot_runs").update({"status": "generated"}).eq("id", run).execute()
    )
    return {**answer, "sends_message": False}


class Contact(BaseModel):
    connection_id: str = Field(max_length=100)
    sender_id: str = Field(max_length=100)


@router.post("/contacts/resume")
def resume(payload: Contact, user: CurrentUser = Depends(current_user)):
    workspace = user_workspace(user.id)
    available(workspace)
    db().table("chatbot_contacts").update(
        {"paused": False, "updated_at": datetime.now(UTC).isoformat()}
    ).eq("workspace_id", workspace).eq("connection_id", payload.connection_id).eq(
        "sender_id", payload.sender_id
    ).execute()
    return {"resumed": True}
