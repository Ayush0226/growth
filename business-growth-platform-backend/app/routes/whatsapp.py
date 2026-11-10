"""Customer-authorized WhatsApp connections, inbox, automations and campaigns."""

import hmac
import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from app.config import Settings, get_settings
from app.database import db, one
from app.routes.instagram import user_workspace
from app.security import (
    CurrentUser,
    TokenCipher,
    current_user,
    generate_oauth_state,
    hash_oauth_state,
)
from app.whatsapp import WhatsAppClient, decode_verified_webhook
from app.whatsapp_service import (
    BILLING_URL,
    PRICING_URL,
    PUBLIC_CONNECTION,
    available,
    client_token,
    connection,
    contact,
    fingerprint,
    ingest,
    now_iso,
    queue_message,
    service_window,
    sync_templates,
)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def workspace(user: CurrentUser, settings: Settings) -> str:
    available(settings)
    return user_workspace(user.id)


def connected(
    user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)
):
    return connection(workspace(user, settings), private=True)


@router.get("")
def status(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    result = {
        "enabled": settings.whatsapp_enabled,
        "connected": False,
        "setup_ready": False,
        "signup_ready": bool(settings.whatsapp_enabled and settings.whatsapp_signup_config_id),
        "app_id": settings.whatsapp_app_id or settings.meta_app_id,
        "config_id": settings.whatsapp_signup_config_id,
        "graph_version": settings.meta_graph_api_version,
        "billing_url": BILLING_URL,
        "pricing_url": PRICING_URL,
        "ai_ready": bool(settings.groq_api_key),
        "allowance": {
            "service_messages": 1000,
            "scope": "per business number per month",
            "policy_checked": "2026-11-10",
            "includes_templates": False,
        },
    }
    if not settings.whatsapp_enabled:
        return result
    try:
        ws = user_workspace(user.id)
        conn = one(
            db()
            .table("whatsapp_connections")
            .select(PUBLIC_CONNECTION)
            .eq("workspace_id", ws)
            .execute()
        )
        db().table("whatsapp_templates").select("id").limit(0).execute()
    except APIError as exc:
        if exc.code in {"PGRST205", "42703", "42P01", "PGRST204"}:
            return result
        raise
    result.update(
        setup_ready=True, connected=bool(conn and conn["status"] == "active"), connection=conn
    )
    if conn:
        month = (
            datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        )
        total = (
            db()
            .table("whatsapp_messages")
            .select("id", count="exact")
            .eq("connection_id", conn["id"])
        )
        total = (
            total.eq("direction", "outbound")
            .eq("category", "service")
            .gte("delivered_at", month)
            .limit(0)
            .execute()
        )
        result["usage"] = {
            "tracked_service_deliveries": total.count or 0,
            "period_start": month,
            "authoritative_balance_available": False,
            "note": "Growthboard-captured deliveries this UTC month. Meta is authoritative; other integrations can also use the allowance.",
        }
    return result


@router.post("/signup/start")
def signup_start(
    user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)
):
    ws = workspace(user, settings)
    if not settings.whatsapp_signup_config_id:
        raise HTTPException(503, "Meta customer connection is being configured.")
    raw, digest = generate_oauth_state()
    db().table("whatsapp_signup_sessions").insert(
        {
            "workspace_id": ws,
            "user_id": user.id,
            "state_hash": digest,
            "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        }
    ).execute()
    return {"state": raw}


class SignupComplete(BaseModel):
    state: str = Field(min_length=20, max_length=200)
    code: SecretStr
    waba_id: str = Field(pattern=r"^\d{1,40}$")
    phone_number_id: str = Field(pattern=r"^\d{1,40}$")
    registration_pin: SecretStr | None = None

    @field_validator("registration_pin")
    @classmethod
    def pin(cls, value):
        if value is not None and not re.fullmatch(r"\d{6}", value.get_secret_value()):
            raise ValueError("New-number registration requires a six-digit verification PIN")
        return value


async def store_connection(ws, user, waba, phone, token, settings, registration_pin=None):
    prior = one(
        db()
        .table("whatsapp_connections")
        .select("waba_id,phone_number_id")
        .eq("workspace_id", ws)
        .execute()
    )
    if prior and (prior["waba_id"] != waba or prior["phone_number_id"] != phone):
        raise HTTPException(
            409,
            "This workspace is assigned to another WhatsApp number. Contact support before switching.",
        )
    other = one(
        db()
        .table("whatsapp_connections")
        .select("workspace_id")
        .eq("phone_number_id", phone)
        .execute()
    )
    if other and other["workspace_id"] != ws:
        raise HTTPException(409, "This number is already assigned to another workspace.")
    details = await WhatsAppClient(settings.meta_graph_api_version).validate_connection(
        waba,
        phone,
        token,
        settings.whatsapp_app_id or settings.meta_app_id,
        settings.whatsapp_app_secret or settings.meta_app_secret,
    )
    if registration_pin:
        # Explicitly requested only for new Cloud API numbers; never deregister an existing app.
        await WhatsAppClient(settings.meta_graph_api_version).register_number(
            phone, registration_pin.get_secret_value(), token
        )
    db().table("whatsapp_connections").upsert(
        {
            "workspace_id": ws,
            "connected_by": user.id,
            "waba_id": waba,
            "phone_number_id": phone,
            "status": "active",
            "display_phone_number": details.get("display_phone_number"),
            "verified_name": details.get("verified_name"),
            "access_token_encrypted": TokenCipher(settings.token_encryption_key).encrypt(token),
            "ai_enabled": False,
            "connected_at": now_iso(),
            "updated_at": now_iso(),
        },
        on_conflict="workspace_id",
    ).execute()
    conn = connection(ws)
    db().table("whatsapp_rules").update({"enabled": False}).eq(
        "connection_id", conn["id"]
    ).execute()
    db().table("whatsapp_campaigns").update(
        {"status": "paused", "detail": "Connection renewed; review before resuming."}
    ).eq("connection_id", conn["id"]).in_("status", ["scheduled", "running"]).execute()
    return conn


@router.post("/signup/complete")
async def signup_complete(
    payload: SignupComplete,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    ws = workspace(user, settings)
    claimed = (
        db()
        .table("whatsapp_signup_sessions")
        .update({"consumed": True})
        .eq("workspace_id", ws)
        .eq("user_id", user.id)
        .eq("state_hash", hash_oauth_state(payload.state))
        .eq("consumed", False)
        .gt("expires_at", now_iso())
        .execute()
        .data
    )
    if not claimed:
        raise HTTPException(409, "Connection session expired or was already used. Start again.")
    token = await WhatsAppClient(settings.meta_graph_api_version).exchange_code(
        payload.code.get_secret_value(),
        settings.whatsapp_app_id or settings.meta_app_id,
        settings.whatsapp_app_secret or settings.meta_app_secret,
    )
    return await store_connection(
        ws,
        user,
        payload.waba_id,
        payload.phone_number_id,
        token,
        settings,
        payload.registration_pin,
    )


class TestConnection(BaseModel):
    waba_id: str = Field(pattern=r"^\d{1,40}$")
    phone_number_id: str = Field(pattern=r"^\d{1,40}$")
    access_token: SecretStr


@router.post("/test-connection")
async def test_connection(
    payload: TestConnection,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    ws = workspace(user, settings)
    if settings.environment == "production":
        raise HTTPException(403, "Use Connect WhatsApp to authorize production accounts.")
    return await store_connection(
        ws,
        user,
        payload.waba_id,
        payload.phone_number_id,
        payload.access_token.get_secret_value(),
        settings,
    )


@router.post("/disconnect")
def disconnect(conn: dict = Depends(connected)):
    db().table("whatsapp_connections").update(
        {
            "status": "revoked",
            "access_token_encrypted": "",
            "ai_enabled": False,
            "billing_acknowledged": False,
            "updated_at": now_iso(),
        }
    ).eq("id", conn["id"]).execute()
    db().table("whatsapp_rules").update({"enabled": False}).eq(
        "connection_id", conn["id"]
    ).execute()
    db().table("whatsapp_campaigns").update({"status": "cancelled"}).eq(
        "connection_id", conn["id"]
    ).in_("status", ["draft", "scheduled", "running", "paused"]).execute()
    db().table("whatsapp_messages").update(
        {"status": "failed", "detail": "Disconnected before sending"}
    ).eq("connection_id", conn["id"]).eq("status", "queued").execute()
    return {"status": "disconnected"}


class BillingInput(BaseModel):
    acknowledged: bool


@router.post("/billing")
def billing(payload: BillingInput, conn: dict = Depends(connected)):
    db().table("whatsapp_connections").update({"billing_acknowledged": payload.acknowledged}).eq(
        "id", conn["id"]
    ).execute()
    return {
        "acknowledged": payload.acknowledged,
        "verified_payment": False,
        "billing_url": BILLING_URL,
    }


@router.get("/contacts")
def contacts(offset: int = Query(0, ge=0), conn: dict = Depends(connected)):
    items = (
        db()
        .table("whatsapp_contacts")
        .select("*")
        .eq("connection_id", conn["id"])
        .order("updated_at", desc=True)
        .range(offset, offset + 99)
        .execute()
        .data
    )
    for item in items:
        end = service_window(conn, item["wa_id"])
        item["window_ends_at"] = end.isoformat() if end else None
    return {"items": items, "has_more": len(items) == 100}


class ContactInput(BaseModel):
    wa_id: str = Field(pattern=r"^\d{7,15}$")
    name: str = Field(default="", max_length=100)
    opted_in: bool = False
    consent_source: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def consent(self):
        if self.opted_in and len(self.consent_source.strip()) < 10:
            raise ValueError(
                "Record where and when the customer agreed to these WhatsApp messages."
            )
        return self


@router.post("/contacts")
def save_contact(payload: ContactInput, conn: dict = Depends(connected)):
    values = {
        **payload.model_dump(),
        "workspace_id": conn["workspace_id"],
        "connection_id": conn["id"],
        "updated_at": now_iso(),
    }
    if payload.opted_in:
        values.update(opted_in_at=now_iso(), opted_out=False)
    return one(
        db().table("whatsapp_contacts").upsert(values, on_conflict="connection_id,wa_id").execute()
    )


class ContactControl(BaseModel):
    paused: bool


class ContactImport(BaseModel):
    items: list[ContactInput] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique(self):
        if len({p.wa_id for p in self.items}) != len(self.items):
            raise ValueError("Remove duplicate contact numbers before importing")
        return self


@router.post("/contacts/import")
def import_contacts(payload: ContactImport, conn: dict = Depends(connected)):
    values = []
    for item in payload.items:
        value = {
            **item.model_dump(),
            "workspace_id": conn["workspace_id"],
            "connection_id": conn["id"],
            "updated_at": now_iso(),
        }
        # Explicitly recorded fresh permission can reverse an opt-out; importing a list alone cannot.
        if item.opted_in:
            value.update(opted_in_at=now_iso(), opted_out=False)
        values.append(value)
    # Different key sets must be sent separately so omitted opt-out fields are never defaulted.
    for has_consent in (False, True):
        batch = [row for row in values if row["opted_in"] == has_consent]
        if batch:
            db().table("whatsapp_contacts").upsert(
                batch, on_conflict="connection_id,wa_id"
            ).execute()
    return {"imported": len(values)}


@router.post("/contacts/{wa_id}/automation")
def contact_control(wa_id: str, payload: ContactControl, conn: dict = Depends(connected)):
    person = contact(conn, wa_id)
    if not person:
        raise HTTPException(404, "Contact not found")
    if person["opted_out"] and not payload.paused:
        raise HTTPException(
            409, "Record fresh customer consent before resuming an opted-out contact."
        )
    return one(
        db()
        .table("whatsapp_contacts")
        .update({"automation_paused": payload.paused, "updated_at": now_iso()})
        .eq("id", person["id"])
        .execute()
    )


@router.get("/messages/{wa_id}")
def messages(wa_id: str, offset: int = Query(0, ge=0), conn: dict = Depends(connected)):
    items = (
        db()
        .table("whatsapp_messages")
        .select("*")
        .eq("connection_id", conn["id"])
        .eq("contact_wa_id", wa_id)
        .order("occurred_at", desc=True)
        .range(offset, offset + 49)
        .execute()
        .data
    )
    end = service_window(conn, wa_id)
    return {
        "items": items,
        "has_more": len(items) == 50,
        "window_ends_at": end.isoformat() if end else None,
    }


class MessageInput(BaseModel):
    request_id: UUID
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a reply")
        return value.strip()


@router.post("/messages/{wa_id}")
def reply(wa_id: str, payload: MessageInput, conn: dict = Depends(connected)):
    person = contact(conn, wa_id)
    if not person or person["opted_out"]:
        raise HTTPException(409, "Contact is unavailable or has opted out.")
    if not conn["billing_acknowledged"]:
        raise HTTPException(409, "Acknowledge Meta charges in Connection & billing first.")
    if not service_window(conn, wa_id):
        raise HTTPException(409, "The service window is closed. Use an approved template campaign.")
    db().table("whatsapp_contacts").update({"automation_paused": True, "updated_at": now_iso()}).eq(
        "id", person["id"]
    ).execute()
    return queue_message(conn, wa_id, str(payload.request_id), payload.text, purpose="manual")


class RuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    trigger: Literal["welcome", "keyword"]
    keywords: list[str] = Field(default_factory=list, max_length=20)
    reply_text: str = Field(min_length=1, max_length=1000)
    daily_limit: int = Field(default=50, ge=1, le=200)
    cooldown_minutes: int = Field(default=60, ge=1, le=1440)

    @model_validator(mode="after")
    def clean(self):
        self.name, self.reply_text = self.name.strip(), self.reply_text.strip()
        self.keywords = list(
            dict.fromkeys(s.strip().casefold() for s in self.keywords if s.strip())
        )
        if (
            not self.name
            or not self.reply_text
            or (self.trigger == "keyword" and not self.keywords)
            or any(len(k) > 80 for k in self.keywords)
        ):
            raise ValueError("Enter a name, reply and valid keywords for keyword rules.")
        return self


@router.get("/rules")
def rules(conn: dict = Depends(connected)):
    return {
        "items": db()
        .table("whatsapp_rules")
        .select("*")
        .eq("connection_id", conn["id"])
        .order("created_at")
        .execute()
        .data
    }


@router.post("/rules")
@router.put("/rules/{rule_id}")
def save_rule(payload: RuleInput, rule_id: UUID | None = None, conn: dict = Depends(connected)):
    values = {**payload.model_dump(), "enabled": False, "updated_at": now_iso()}
    if payload.trigger == "welcome":
        prior = one(
            db()
            .table("whatsapp_rules")
            .select("id")
            .eq("connection_id", conn["id"])
            .eq("trigger", "welcome")
            .execute()
        )
        if prior and prior["id"] != str(rule_id):
            raise HTTPException(409, "Edit the existing welcome rule; only one is allowed.")
    if rule_id:
        row = one(
            db()
            .table("whatsapp_rules")
            .update(values)
            .eq("id", str(rule_id))
            .eq("connection_id", conn["id"])
            .execute()
        )
        if not row:
            raise HTTPException(404, "Rule not found")
        return row
    return one(
        db()
        .table("whatsapp_rules")
        .insert({**values, "workspace_id": conn["workspace_id"], "connection_id": conn["id"]})
        .execute()
    )


class EnableInput(BaseModel):
    enabled: bool
    updated_at: str


@router.post("/rules/{rule_id}/enabled")
def enable_rule(rule_id: UUID, payload: EnableInput, conn: dict = Depends(connected)):
    if payload.enabled and not conn["billing_acknowledged"]:
        raise HTTPException(409, "Acknowledge Meta charges in Connection & billing first.")
    row = one(
        db()
        .table("whatsapp_rules")
        .update({"enabled": payload.enabled, "updated_at": now_iso()})
        .eq("connection_id", conn["id"])
        .eq("id", str(rule_id))
        .eq("updated_at", payload.updated_at)
        .execute()
    )
    if not row:
        raise HTTPException(409, "Rule changed. Refresh and review again.")
    return row


class AIInput(BaseModel):
    business_name: str = Field(min_length=1, max_length=100)
    knowledge: str = Field(min_length=20, max_length=20000)
    instructions: str = Field(default="", max_length=2000)
    handoff_message: str = Field(min_length=1, max_length=900)
    ai_daily_limit: int = Field(default=50, ge=1, le=200)

    @field_validator("business_name", "knowledge", "handoff_message")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("Enter business information")
        return value.strip()


@router.put("/ai")
def save_ai(payload: AIInput, conn: dict = Depends(connected)):
    db().table("whatsapp_connections").update(
        {**payload.model_dump(), "ai_enabled": False, "updated_at": now_iso()}
    ).eq("id", conn["id"]).execute()
    return {"saved": True, "enabled": False}


@router.post("/ai/enabled")
def enable_ai(
    payload: EnableInput,
    conn: dict = Depends(connected),
    settings: Settings = Depends(get_settings),
):
    if payload.enabled and (
        not settings.groq_api_key
        or len(conn["knowledge"].strip()) < 20
        or not conn["billing_acknowledged"]
    ):
        raise HTTPException(
            409, "Save business facts, configure AI and acknowledge Meta charges first."
        )
    row = one(
        db()
        .table("whatsapp_connections")
        .update(
            {"ai_enabled": payload.enabled, "ai_enabled_at": now_iso(), "updated_at": now_iso()}
        )
        .eq("id", conn["id"])
        .eq("updated_at", payload.updated_at)
        .execute()
    )
    if not row:
        raise HTTPException(409, "Business information changed. Refresh and review again.")
    return {"enabled": payload.enabled}


@router.get("/templates")
def templates(conn: dict = Depends(connected)):
    return {
        "items": db()
        .table("whatsapp_templates")
        .select("*")
        .eq("connection_id", conn["id"])
        .order("name")
        .execute()
        .data
    }


@router.post("/templates/sync")
async def template_sync(
    conn: dict = Depends(connected), settings: Settings = Depends(get_settings)
):
    return {"items": await sync_templates(conn, settings)}


class TemplateInput(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    language: str = Field(pattern=r"^[a-z]{2,3}(?:_[A-Z]{2})?$")
    category: Literal["UTILITY", "MARKETING"]
    body: str = Field(min_length=1, max_length=1024)
    examples: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def placeholders(self):
        indices = {int(n) for n in re.findall(r"\{\{(\d+)\}\}", self.body)}
        if (
            indices != set(range(1, len(self.examples) + 1))
            or re.search(r"\{\{[^}]+\}\}", re.sub(r"\{\{\d+\}\}", "", self.body))
            or any(not e.strip() or len(e) > 200 for e in self.examples)
            or not self.body.strip()
        ):
            raise ValueError("Use consecutive {{1}}, {{2}} fields and supply one sample for each.")
        return self


@router.post("/templates")
async def submit_template(
    payload: TemplateInput,
    conn: dict = Depends(connected),
    settings: Settings = Depends(get_settings),
):
    client, token = client_token(conn, settings)
    body = {"type": "BODY", "text": payload.body}
    if payload.examples:
        body["example"] = {"body_text": [payload.examples]}
    result = await client.create_template(
        conn["waba_id"],
        {
            "name": payload.name,
            "language": payload.language,
            "category": payload.category,
            "components": [body],
        },
        token,
    )
    return {
        "id": result.get("id"),
        "status": result.get("status", "PENDING"),
        "detail": "Submitted to Meta. Sync templates to check approval.",
    }


class Recipient(BaseModel):
    wa_id: str = Field(pattern=r"^\d{7,15}$")
    parameters: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("parameters")
    @classmethod
    def values(cls, values):
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("Template values must be 1–500 characters")
        return values


class CampaignInput(BaseModel):
    request_id: UUID
    name: str = Field(min_length=1, max_length=100)
    template_id: str = Field(pattern=r"^\d{1,40}$")
    recipients: list[Recipient] = Field(min_length=1, max_length=1000)
    scheduled_for: datetime | None = None

    @model_validator(mode="after")
    def unique(self):
        if not self.name.strip() or len({r.wa_id for r in self.recipients}) != len(self.recipients):
            raise ValueError("Enter a campaign name and remove duplicate recipients")
        if self.scheduled_for and self.scheduled_for.tzinfo is None:
            raise ValueError("Schedule must include a timezone")
        return self


@router.post("/campaigns")
async def create_campaign(
    payload: CampaignInput,
    conn: dict = Depends(connected),
    settings: Settings = Depends(get_settings),
):
    digest = fingerprint(payload.model_dump(mode="json"))
    prior = one(
        db()
        .table("whatsapp_campaigns")
        .select("*")
        .eq("workspace_id", conn["workspace_id"])
        .eq("request_id", str(payload.request_id))
        .execute()
    )
    if prior:
        if prior["request_hash"] != digest:
            raise HTTPException(409, "Request already used for another campaign")
        return prior
    items = await sync_templates(conn, settings)
    template = next((t for t in items if t["id"] == payload.template_id and t["sendable"]), None)
    if not template:
        raise HTTPException(
            409, "Select a current approved text template supported by Growthboard."
        )
    ids = [r.wa_id for r in payload.recipients]
    people = (
        db()
        .table("whatsapp_contacts")
        .select("wa_id")
        .eq("connection_id", conn["id"])
        .in_("wa_id", ids)
        .eq("opted_in", True)
        .eq("opted_out", False)
        .limit(1000)
        .execute()
        .data
    )
    if {p["wa_id"] for p in people} != set(ids):
        raise HTTPException(
            409, "Every recipient needs recorded consent and must not have opted out."
        )
    if any(len(r.parameters) != template["parameter_count"] for r in payload.recipients):
        raise HTTPException(422, "Every recipient needs the template's exact number of values.")
    values = {
        "workspace_id": conn["workspace_id"],
        "connection_id": conn["id"],
        "request_id": str(payload.request_id),
        "request_hash": digest,
        "name": payload.name.strip(),
        "template": template,
        "recipients": [r.model_dump() for r in payload.recipients],
        "scheduled_for": payload.scheduled_for.astimezone(UTC).isoformat()
        if payload.scheduled_for
        else now_iso(),
    }
    db().table("whatsapp_campaigns").upsert(
        values, on_conflict="workspace_id,request_id", ignore_duplicates=True
    ).execute()
    row = one(
        db()
        .table("whatsapp_campaigns")
        .select("*")
        .eq("workspace_id", conn["workspace_id"])
        .eq("request_id", str(payload.request_id))
        .execute()
    )
    if row["request_hash"] != digest:
        raise HTTPException(409, "Request already used for another campaign")
    return row


@router.get("/campaigns")
def campaigns(offset: int = Query(0, ge=0), conn: dict = Depends(connected)):
    items = (
        db()
        .table("whatsapp_campaigns")
        .select("*")
        .eq("connection_id", conn["id"])
        .order("created_at", desc=True)
        .range(offset, offset + 19)
        .execute()
        .data
    )
    for item in items:
        rows = (
            db()
            .table("whatsapp_messages")
            .select("status")
            .eq("campaign_id", item["id"])
            .limit(1000)
            .execute()
            .data
        )
        item["counts"] = {
            state: sum(m["status"] == state for m in rows)
            for state in ("queued", "sending", "sent", "delivered", "read", "failed", "uncertain")
        }
        item["recipient_count"] = len(item["recipients"])
    return {"items": items, "has_more": len(items) == 20}


class CampaignControl(BaseModel):
    action: Literal["approve", "pause", "resume", "cancel"]


@router.post("/campaigns/{campaign_id}/control")
def campaign_control(campaign_id: UUID, payload: CampaignControl, conn: dict = Depends(connected)):
    campaign = one(
        db()
        .table("whatsapp_campaigns")
        .select("*")
        .eq("id", str(campaign_id))
        .eq("connection_id", conn["id"])
        .execute()
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    allowed = {
        "approve": {"draft"},
        "resume": {"paused"},
        "pause": {"scheduled", "running"},
        "cancel": {"draft", "scheduled", "running", "paused"},
    }
    if campaign["status"] not in allowed[payload.action]:
        raise HTTPException(409, "Campaign state changed. Refresh before continuing.")
    values = {"updated_at": now_iso()}
    if payload.action in {"approve", "resume"}:
        if not conn["billing_acknowledged"]:
            raise HTTPException(
                409, "Acknowledge direct Meta charges before approving this campaign."
            )
        values.update(status="scheduled", approved_at=now_iso(), detail="")
        if payload.action == "resume":
            values["scheduled_for"] = now_iso()
    else:
        values["status"] = "paused" if payload.action == "pause" else "cancelled"
    row = one(
        db()
        .table("whatsapp_campaigns")
        .update(values)
        .eq("id", str(campaign_id))
        .eq("status", campaign["status"])
        .execute()
    )
    if not row:
        raise HTTPException(409, "Campaign state changed. Refresh before continuing.")
    if payload.action == "cancel":
        db().table("whatsapp_messages").update(
            {"status": "failed", "detail": "Campaign cancelled before sending"}
        ).eq("campaign_id", str(campaign_id)).eq("status", "queued").execute()
    return row


@router.get("/activity")
def activity(conn: dict = Depends(connected)):
    return {
        "messages": db()
        .table("whatsapp_messages")
        .select(
            "id,contact_wa_id,direction,text,message_type,status,detail,created_at,purpose,campaign_id"
        )
        .eq("connection_id", conn["id"])
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data,
        "events": db()
        .table("whatsapp_events")
        .select("id,status,detail,received_at")
        .eq("connection_id", conn["id"])
        .order("received_at", desc=True)
        .limit(30)
        .execute()
        .data,
    }


@router.get("/webhook", response_class=PlainTextResponse)
def webhook_challenge(request: Request, settings: Settings = Depends(get_settings)):
    params = request.query_params
    if (
        not settings.whatsapp_webhook_verify_token
        or params.get("hub.mode") != "subscribe"
        or not hmac.compare_digest(
            params.get("hub.verify_token", ""), settings.whatsapp_webhook_verify_token
        )
    ):
        raise HTTPException(403, "Verification failed")
    return params.get("hub.challenge", "")


@router.post("/webhook")
async def webhook(request: Request, settings: Settings = Depends(get_settings)):
    available(settings)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 1024 * 1024:
            raise HTTPException(413, "Event exceeds intake limit")
        body.extend(chunk)
    try:
        events = decode_verified_webhook(
            bytes(body),
            request.headers.get("x-hub-signature-256", ""),
            settings.whatsapp_app_secret or settings.meta_app_secret,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Invalid signed WhatsApp event") from exc
    return {"received": ingest(events)}
