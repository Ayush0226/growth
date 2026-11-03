from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.automations import matches_keyword
from app.config import Settings, get_settings
from app.database import db, one
from app.routes.engagement import connected, require
from app.routes.instagram import user_workspace
from app.security import CurrentUser, current_user

router = APIRouter(prefix="/api/automations", tags=["automations"])


class RuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    trigger: Literal["welcome", "dm_keyword", "comment_keyword"]
    keywords: list[str] = Field(default_factory=list, max_length=20)
    media_ids: list[str] = Field(default_factory=list, max_length=50)
    reply_text: str = Field(min_length=1, max_length=1000)
    enabled: bool = False
    daily_limit: int = Field(default=20, ge=1, le=100)
    cooldown_minutes: int = Field(default=60, ge=1, le=1440)

    @model_validator(mode="after")
    def validate_rule(self):
        self.name = self.name.strip()
        self.reply_text = self.reply_text.strip()
        self.keywords = list(
            dict.fromkeys(x.strip().casefold() for x in self.keywords if x.strip())
        )
        self.media_ids = list(dict.fromkeys(self.media_ids))
        if not self.name or not self.reply_text:
            raise ValueError("Name and reply cannot be blank")
        if any(len(word) > 80 for word in self.keywords):
            raise ValueError("Each keyword must be 80 characters or fewer")
        if self.trigger != "welcome" and not self.keywords:
            raise ValueError("Add at least one keyword")
        if self.trigger == "comment_keyword" and not self.media_ids:
            raise ValueError("Select at least one Instagram post for comment-to-DM")
        if any(not item.isdigit() for item in self.media_ids):
            raise ValueError("Select a valid Instagram media ID")
        return self


@router.get("")
def list_rules(user: CurrentUser = Depends(current_user)):
    workspace = user_workspace(user.id)
    return {
        "items": db()
        .table("automation_rules")
        .select("*")
        .eq("workspace_id", workspace)
        .order("created_at")
        .execute()
        .data
    }


async def save_rule(
    payload: RuleInput, user: CurrentUser, settings: Settings, rule_id: str | None = None
):
    workspace = user_workspace(user.id)
    existing = (
        one(
            db()
            .table("automation_rules")
            .select("id")
            .eq("workspace_id", workspace)
            .eq("trigger", "welcome")
            .execute()
        )
        if payload.trigger == "welcome"
        else None
    )
    if existing and existing["id"] != rule_id:
        raise HTTPException(409, "Edit the existing welcome rule; only one welcome rule is allowed")
    if rule_id and not one(
        db()
        .table("automation_rules")
        .select("id")
        .eq("id", rule_id)
        .eq("workspace_id", workspace)
        .execute()
    ):
        raise HTTPException(404, "Rule not found")
    if payload.enabled:
        require("instagram_business_manage_messages", workspace)
        client, token, account = connected(workspace, settings)
        if payload.trigger == "comment_keyword":
            require("instagram_business_manage_comments", workspace)
            media = await client.get("me/media", token, fields="id", limit=100)
            if not set(payload.media_ids).issubset(
                {str(item["id"]) for item in media.get("data", [])}
            ):
                raise HTTPException(
                    422, "Selected posts must belong to the connected Instagram account"
                )
        connection = one(
            db()
            .table("social_connections")
            .select("webhook_subscribed")
            .eq("id", account["connection_id"])
            .execute()
        )
        if not connection or not connection.get("webhook_subscribed"):
            raise HTTPException(
                409, "Enable Instagram event delivery in Connections before enabling a rule"
            )
    values = {**payload.model_dump(), "updated_at": datetime.now(UTC).isoformat()}
    if rule_id:
        return one(
            db()
            .table("automation_rules")
            .update(values)
            .eq("id", rule_id)
            .eq("workspace_id", workspace)
            .execute()
        )
    return one(
        db().table("automation_rules").insert({**values, "workspace_id": workspace}).execute()
    )


@router.post("", status_code=201)
async def create_rule(
    payload: RuleInput,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    return await save_rule(payload, user, settings)


@router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    payload: RuleInput,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    return await save_rule(payload, user, settings, rule_id)


class PreviewInput(BaseModel):
    text: str = Field(max_length=2000)
    keywords: list[str] = Field(max_length=20)


@router.post("/preview")
def preview(payload: PreviewInput, user: CurrentUser = Depends(current_user)):
    return {"matched": matches_keyword(payload.text, payload.keywords), "sends_message": False}


@router.get("/activity")
def activity(user: CurrentUser = Depends(current_user)):
    workspace = user_workspace(user.id)
    return {
        "events": db()
        .table("automation_events")
        .select("id,kind,status,detail,received_at,processed_at")
        .eq("workspace_id", workspace)
        .order("received_at", desc=True)
        .limit(50)
        .execute()
        .data,
        "deliveries": db()
        .table("automation_deliveries")
        .select("id,rule_id,status,reply_text,detail,created_at")
        .eq("workspace_id", workspace)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data,
    }
