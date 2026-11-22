import asyncio
import base64
import hmac
import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import RedirectResponse, Response
from pydantic import AwareDatetime, BaseModel, Field, HttpUrl, model_validator, field_validator

from app.config import Settings, get_settings
from app.database import db
from app.gbp import jobs, service
from app.gbp.provider import GoogleError, resource
from app.google_review_policy import ReviewRule
from app.security import CurrentUser, current_user

router = APIRouter(tags=["Google Business Profile"])


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
async def mcp_metadata(settings: Settings = Depends(get_settings)):
    if not settings.google_enabled or not settings.google_mcp_enabled:
        raise HTTPException(503, "Growboard MCP linking is not enabled.")
    return {"resource": str(settings.google_mcp_resource_url).rstrip("/"),
            "authorization_servers": [str(settings.supabase_url).rstrip("/")+"/auth/v1"],
            "scopes_supported": ["openid","email","profile","offline_access"], "bearer_methods_supported": ["header"],
            "resource_name": "Growboard Google Business Profile", "resource_documentation": "https://growboard.in/privacy"}


class LocationInput(BaseModel):
    location_name: str = ""
    location_id: str | None = None
    user_id: str | None = None
    # Accepted for request compatibility, but never trusted or used for authorization.
    provider_token: str | None = Field(default=None, exclude=True, repr=False)


async def context(payload: LocationInput | None, user: CurrentUser, settings: Settings, *, owner=False):
    service.ready(settings)
    if payload and payload.user_id and payload.user_id != user.id:
        raise HTTPException(403, "You cannot access another user's account.")
    ws = await service.workspace(user.id, owner=owner)
    if not payload:
        return ws, None
    name = payload.location_name or payload.location_id or ""
    if name.startswith("locations/"):
        rows = await service.execute(db().table("gbp_locations").select("name").eq("workspace_id", ws).eq("active", True))
        matches = [row["name"] for row in rows if row["name"].endswith("/"+name)]
        if len(matches) != 1:
            raise HTTPException(403, "Connect this Google location before continuing.")
        name = matches[0]
    try:
        resource(name, "location")
    except ValueError:
        raise HTTPException(422, "A valid Google location is required.") from None
    return ws, await service.owned_location(ws, name)


@router.get("/api/gbp/status")
async def status(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws = await service.workspace(user.id)
    setup = bool(settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri)
    if not settings.google_enabled:
        return {"enabled": False, "setup_ready": setup, "connected": False, "worker_enabled": False,
                "rank_provider_ready": bool(settings.serpapi_key),
                "message": "Google integration is being prepared. Existing GBP AutoMaster remains available."}
    rows = await service.execute(db().table("gbp_connections").select("email,status,connected_at").eq("workspace_id", ws).limit(1))
    return {"enabled": True, "setup_ready": setup, "worker_enabled": settings.google_worker_enabled,
            "rank_provider_ready": bool(settings.serpapi_key),
            "connected": bool(rows and rows[0]["status"] == "active"), "connection": rows[0] if rows else None}


@router.post("/api/gbp/connect")
async def connect(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    service.ready(settings)
    ws = await service.workspace(user.id, owner=True)
    return {"authorization_url": await service.start_oauth(settings, ws, user.id)}


@router.get("/api/integrations/google/callback")
async def callback(state: str = Query(max_length=200), code: str = Query(default="", max_length=8192),
                   error: str | None = Query(default=None, max_length=200), settings: Settings = Depends(get_settings)):
    success = await service.finish_oauth(settings, state, code, error)
    return RedirectResponse(str(settings.google_frontend_url).rstrip("/")+"/google?connection="+("connected" if success else "cancelled"),
                            status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.post("/api/gbp/disconnect")
async def disconnect(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    service.ready(settings)
    ws = await service.workspace(user.id, owner=True)
    await service.execute(db().rpc("gbp_disconnect", {"p_workspace": ws}))
    await service.audit(ws, user.id, "google_disconnected")
    return {"status": "disconnected"}


@router.get("/api/gbp/locations")
async def locations(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings)
    return {"locations": await service.execute(db().table("gbp_locations").select("name,title,account_name,account_display_name,active")
                                                .eq("workspace_id", ws).eq("active", True))}


@router.post("/api/google/locations")
async def sync(payload: LocationInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    if payload.user_id and payload.user_id != user.id:
        raise HTTPException(403, "You cannot access another user's account.")
    ws, _ = await context(None, user, settings, owner=True)
    async with service.connected(settings, ws) as (client, _connection):
        rows = await service.sync_locations(client, ws)
    await service.audit(ws, user.id, "locations_synced")
    return {"status": "success", "locations": [{**row, "id": row["name"].split("/", 2)[2],
              "account_id": row["account_name"], "name": row["title"], "resource_name": row["name"]} for row in rows]}


class ReviewsInput(LocationInput):
    page_token: str = Field(default="", max_length=4096)


@router.post("/api/google/get-reviews")
async def reviews(payload: ReviewsInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, location = await context(payload, user, settings)
    async with service.connected(settings, ws) as (client, _connection):
        page = await client.reviews(location["name"], payload.page_token)
    rows = page.get("reviews", [])
    return {"status": "success", "reviews": [{
        "id": review.get("name") or f"{location['name']}/reviews/{review['reviewId']}",
        "reviewer": review.get("reviewer", {}).get("displayName", "Anonymous"), "rating": review.get("starRating"),
        "comment": review.get("comment", ""), "createTime": review.get("createTime", ""),
        "has_reply": bool(review.get("reviewReply")), "reply_comment": review.get("reviewReply", {}).get("comment", ""),
    } for review in rows], "totalReviewCount": page.get("totalReviewCount", len(rows)),
        "averageRating": page.get("averageRating", 0), "recentAnswered": sum(bool(r.get("reviewReply")) for r in rows),
        "totalFetched": len(rows), "nextPageToken": page.get("nextPageToken")}


class ReplyInput(BaseModel):
    review_id: str
    reply_text: str = Field(min_length=1, max_length=4096)
    provider_token: str | None = Field(default=None, exclude=True, repr=False)

    @field_validator("reply_text")
    @classmethod
    def nonblank_reply(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reply text cannot be blank.")
        return value


@router.post("/api/google/post-reply")
async def reply(payload: ReplyInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    try:
        resource(payload.review_id, "review")
    except ValueError:
        raise HTTPException(422, "Invalid review resource.") from None
    ws, location = await context(LocationInput(location_name=payload.review_id.rsplit("/reviews/", 1)[0]), user, settings, owner=True)
    async with service.connected(settings, ws) as (client, _connection):
        review = await client.review(payload.review_id)
    if review.get("reviewReply", {}).get("comment") == payload.reply_text.strip():
        return {"status": "success", "message": "This reply is already published."}
    old = await service.execute(db().table("gbp_review_jobs").select("*").eq("workspace_id", ws).eq("review_name", payload.review_id).limit(1))
    if old:
        previous = old[0]
        if previous["status"] in {"publishing", "uncertain", "generating", "ready", "pending"}:
            raise HTTPException(409, "A delivery is active or unconfirmed. Inspect reply history before changing it.")
        await service.audit(ws, user.id, "manual_reply_revised", payload.review_id)
        await service.execute(db().table("gbp_review_jobs").update({"status": "ready", "manual": True,
            "reply_text": payload.reply_text.strip(), "review_data": review, "not_before": service.now()})
            .eq("id", previous["id"]).eq("status", previous["status"]).eq("updated_at", previous["updated_at"]))
    await service.execute(db().table("gbp_review_jobs").upsert({
        "workspace_id": ws, "location_name": location["name"], "review_name": payload.review_id,
        "review_data": review, "reply_text": payload.reply_text.strip(), "manual": True, "status": "ready",
    }, on_conflict="review_name", ignore_duplicates=True))
    rows = await service.execute(db().table("gbp_review_jobs").select("*").eq("workspace_id", ws).eq("review_name", payload.review_id).limit(1))
    if not rows or rows[0]["status"] != "ready" or rows[0]["reply_text"] != payload.reply_text.strip() or not rows[0]["manual"]:
        raise HTTPException(409, "This review already has a delivery record. Inspect reply history before retrying.")
    result = await jobs.deliver_reply(settings, rows[0])
    if result["status"] != "published":
        raise HTTPException(409, f"Reply result: {result['status']}. Inspect history before retrying.")
    await service.audit(ws, user.id, "review_replied", payload.review_id)
    return {"status": "success", "message": "Reply posted successfully!"}


class DraftReplyInput(LocationInput):
    review_name: str
    tone: str = Field(default="friendly professional", max_length=100)
    language: str = Field(default="English", max_length=40)


@router.post("/api/gbp/draft-reply")
async def draft_reply(payload: DraftReplyInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    try:
        resource(payload.review_name, "review")
    except ValueError:
        raise HTTPException(422, "Invalid review resource.") from None
    ws, location = await context(LocationInput(location_name=payload.review_name.rsplit("/reviews/",1)[0]), user, settings, owner=True)
    async with service.connected(settings, ws) as (client, _connection):
        review = await client.review(payload.review_name)
    text = await service.generate_reply(settings, review, {"tone":payload.tone,"language":payload.language}, location["title"])
    return {"status": "success", "draft_text": text, "sends_reply": False}


@router.get("/api/gbp/rules")
async def rules(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings)
    return {"rules": await service.execute(db().table("gbp_review_rules").select("*").eq("workspace_id", ws))}


class RuleInput(LocationInput):
    enabled: bool = False
    mode: Literal["draft", "approval", "auto_publish"] = "draft"
    min_rating: int = Field(default=4, ge=1, le=5)
    max_rating: int = Field(default=5, ge=1, le=5)
    tone: str = Field(default="friendly professional", min_length=1, max_length=100)
    language: str = Field(default="English", min_length=2, max_length=40)
    custom_instructions: str = Field(default="", max_length=2000)
    business_context: str = Field(default="", max_length=4000)
    delay_minutes: int = Field(default=0, ge=0, le=10080)
    daily_limit: int = Field(default=20, ge=1, le=500)
    blocked_terms: list[str] = Field(default_factory=list, max_length=100)
    exclusive_delivery_confirmed: bool = False

    @model_validator(mode="after")
    def valid_range(self):
        if self.min_rating > self.max_rating or any(len(term) > 200 for term in self.blocked_terms):
            raise ValueError("Invalid rating range or blocked term")
        return self


@router.put("/api/gbp/rules")
async def save_rule(payload: RuleInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, location = await context(payload, user, settings, owner=True)
    if payload.enabled and not payload.exclusive_delivery_confirmed:
        raise HTTPException(409, "Confirm Growboard is the only automatic reply sender for this location before enabling.")
    if payload.enabled and not settings.google_worker_enabled:
        raise HTTPException(409, "Google automation delivery is still paused for setup and testing.")
    old = await service.execute(db().table("gbp_review_rules").select("enabled,enabled_at").eq("workspace_id", ws).eq("location_name", location["name"]).limit(1))
    enabled_at = (old[0]["enabled_at"] if old and old[0]["enabled"] else service.now()) if payload.enabled else None
    values = payload.model_dump(exclude={"location_id", "location_name", "user_id", "provider_token", "exclusive_delivery_confirmed", "min_rating", "max_rating"})
    values.update({"workspace_id": ws, "location_name": location["name"], "rating_min": payload.min_rating,
                   "rating_max": payload.max_rating, "delivery_owned": payload.exclusive_delivery_confirmed,
                   "enabled_at": enabled_at, "enabled_by": user.id if payload.enabled else None, "updated_at": service.now()})
    ReviewRule(**values)
    await service.execute(db().table("gbp_review_rules").upsert(values, on_conflict="location_name"))
    if not payload.enabled:
        await service.execute(db().table("gbp_review_jobs").update({"status": "cancelled"})
                              .eq("workspace_id", ws).eq("location_name", location["name"]).eq("manual", False)
                              .in_("status", ["pending", "generating", "ready"]))
    await service.audit(ws, user.id, "review_rule_enabled" if payload.enabled else "review_rule_saved", location["name"])
    return {"status": "saved"}


@router.get("/api/gbp/review-jobs")
async def review_jobs(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings)
    return {"jobs": await service.execute(db().table("gbp_review_jobs").select("id,location_name,review_name,review_data,reply_text,status,error_code,created_at,updated_at")
                                          .eq("workspace_id", ws).order("created_at", desc=True).limit(100))}


@router.post("/api/gbp/review-jobs/{job_id}/approve")
async def approve(job_id: UUID, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings, owner=True)
    rows = await service.execute(db().table("gbp_review_jobs").update({"status": "ready", "manual": True, "not_before": service.now()})
                                 .eq("id", str(job_id)).eq("workspace_id", ws).in_("status", ["draft", "approval"]))
    if not rows:
        raise HTTPException(409, "This job cannot be approved in its current state.")
    return await jobs.deliver_reply(settings, rows[0])


@router.post("/api/gbp/review-jobs/{job_id}/cancel")
async def cancel_reply(job_id: UUID, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings, owner=True)
    rows = await service.execute(db().table("gbp_review_jobs").update({"status": "cancelled"}).eq("id", str(job_id))
                                 .eq("workspace_id", ws).in_("status", ["pending", "generating", "draft", "approval", "ready"]))
    if not rows:
        raise HTTPException(409, "Delivery has started or this job cannot be cancelled.")
    return {"status": "cancelled"}


@router.post("/api/gbp/review-jobs/{job_id}/reconcile")
async def reconcile_reply(job_id: UUID, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings, owner=True)
    rows = await service.execute(db().table("gbp_review_jobs").select("*").eq("id", str(job_id))
                                 .eq("workspace_id", ws).eq("status", "uncertain").limit(1))
    if not rows:
        raise HTTPException(409, "This job is not awaiting reconciliation.")
    job = rows[0]
    await service.owned_location(ws, job["location_name"])
    async with service.connected(settings, ws) as (client, _connection):
        review = await client.review(job["review_name"])
    reply = review.get("reviewReply")
    if not reply:
        return {"status": "uncertain", "message": "Google has not returned a reply. The job remains held; nothing was resent."}
    state = "sent" if reply.get("comment")==job["reply_text"] else "skipped"
    await service.execute(db().table("gbp_review_jobs").update({"status": state, "provider_result": reply,
        "error_code": None if state=="sent" else "different_reply_present"}).eq("id", str(job_id)).eq("status", "uncertain").eq("workspace_id", ws))
    await service.audit(ws, user.id, "review_delivery_reconciled", job["review_name"])
    return {"status": state}


class CallToAction(BaseModel):
    actionType: Literal["BOOK", "ORDER", "SHOP", "LEARN_MORE", "SIGN_UP", "CALL"]
    url: HttpUrl | None = None


class PostContent(BaseModel):
    summary: str = Field(min_length=1, max_length=1500)
    language_code: str = Field(default="en", min_length=2, max_length=12)
    topic_type: Literal["STANDARD", "EVENT", "OFFER"] = "STANDARD"
    call_to_action: CallToAction | None = None
    event_details: dict | None = None
    offer_details: dict | None = None
    media_asset_id: UUID | None = None

    @model_validator(mode="after")
    def valid_post(self):
        if self.topic_type in {"EVENT", "OFFER"} and not self.event_details:
            raise ValueError("Event title and schedule are required")
        if self.topic_type == "OFFER" and not self.offer_details:
            raise ValueError("Offer details are required")
        if len(json.dumps(self.event_details or {}))>8000 or len(json.dumps(self.offer_details or {}))>8000:
            raise ValueError("Event or offer details are too large")
        return self

    def google_payload(self):
        data = {"languageCode": self.language_code, "summary": self.summary, "topicType": self.topic_type}
        if self.call_to_action:
            data["callToAction"] = self.call_to_action.model_dump(mode="json", exclude_none=True)
        if self.event_details:
            data["event"] = self.event_details
        if self.offer_details:
            data["offer"] = self.offer_details
        if self.media_asset_id:
            data["_media_asset_id"] = str(self.media_asset_id)
        return data


class PostInput(LocationInput, PostContent):
    request_id: UUID = Field(default_factory=uuid4)
    scheduled_for: AwareDatetime | None = None


@router.post("/api/gbp/posts")
async def create_post(payload: PostInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    if payload.scheduled_for and payload.scheduled_for > datetime.now(UTC) and not settings.google_worker_enabled:
        raise HTTPException(409, "Google scheduled delivery is paused. Publish now or enable the Google worker first.")
    ws, location = await context(payload, user, settings, owner=True)
    when = payload.scheduled_for or datetime.now(UTC)
    data = payload.google_payload()
    if payload.media_asset_id:
        await media_asset(ws, str(payload.media_asset_id))
    await service.execute(db().table("gbp_posts").upsert({"workspace_id": ws, "location_name": location["name"],
        "request_key": str(payload.request_id), "payload": data, "scheduled_for": when.isoformat(), "status": "scheduled"},
        on_conflict="workspace_id,request_key,location_name", ignore_duplicates=True))
    rows = await service.execute(db().table("gbp_posts").select("*").eq("workspace_id", ws).eq("request_key", str(payload.request_id))
                                 .eq("location_name", location["name"]).limit(1))
    if not rows or rows[0]["payload"] != data:
        raise HTTPException(409, "This request ID already belongs to different content.")
    if when <= datetime.now(UTC) and rows[0]["status"] == "scheduled":
        result = await jobs.deliver_post(settings, rows[0])
        return {"id": rows[0]["id"], **result}
    return {"id": rows[0]["id"], "status": rows[0]["status"]}


@router.get("/api/gbp/posts")
async def posts(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings)
    return {"posts": await service.execute(db().table("gbp_posts").select("*").eq("workspace_id", ws).order("created_at", desc=True).limit(100))}


async def media_asset(ws: str, asset_id: str):
    rows = await service.execute(db().table("gbp_media_assets").select("*").eq("workspace_id", ws)
                                 .eq("id", asset_id).limit(1))
    if not rows:
        raise HTTPException(403, "Select a validated image from your workspace media library.")
    return rows[0]


@router.get("/api/gbp/media")
async def media(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings)
    rows = await service.execute(db().table("gbp_media_assets").select("id,mime_type,bytes,width,height,created_at")
                                 .eq("workspace_id", ws).order("created_at", desc=True).limit(100))
    return {"assets": rows}


@router.post("/api/gbp/media/upload")
async def upload_media(file: UploadFile = File(...), user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    from app.gbp.media import normalize_photo, store_photo
    ws, _ = await context(None, user, settings, owner=True)
    raw = await file.read(8*1024*1024+1)
    photo, width, height = await asyncio.to_thread(normalize_photo, raw)
    return {"asset": await asyncio.to_thread(store_photo, ws, user.id, photo, width, height)}


class ImageInput(BaseModel):
    request_id: UUID
    prompt: str = Field(min_length=5, max_length=2000)


@router.get("/api/images/providers")
async def image_providers(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    await context(None, user, settings)
    return {"cloudflare_available": bool(settings.cloudflare_account_id and settings.cloudflare_api_token),
            "pollinations_available": False}


@router.post("/api/images/generate")
async def image_generate(payload: ImageInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    from app.gbp.media import generate_image
    ws, _ = await context(None, user, settings, owner=True)
    return await generate_image(settings, ws, user.id, str(payload.request_id), payload.prompt)


class CampaignInput(PostContent):
    title: str = Field(min_length=1, max_length=160)
    location_ids: list[str] = Field(min_length=1, max_length=100)
    timezone: str = "Asia/Kolkata"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(value)
        except (KeyError, ValueError):
            raise ValueError("Choose an IANA timezone") from None
        return value


@router.post("/api/platform/campaigns")
async def create_campaign(payload: CampaignInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings, owner=True)
    targets = []
    for name in dict.fromkeys(payload.location_ids):
        _, location = await context(LocationInput(location_name=name), user, settings, owner=True)
        targets.append(location["name"])
    if payload.media_asset_id:
        await media_asset(ws, str(payload.media_asset_id))
    campaign_id = str(uuid4())
    await service.execute(db().rpc("gbp_create_campaign", {"p_workspace": ws, "p_id": campaign_id,
        "p_title": payload.title, "p_timezone": payload.timezone, "p_locations": targets, "p_payload": payload.google_payload()}))
    await service.audit(ws, user.id, "campaign_created", campaign_id)
    return {"campaign_id": campaign_id, "status": "draft", "location_count": len(targets)}


@router.get("/api/platform/campaigns")
async def campaigns(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings)
    rows = await service.execute(db().table("gbp_campaigns").select("*").eq("workspace_id", ws).order("created_at", desc=True).limit(100))
    children = await service.execute(db().table("gbp_posts").select("*").eq("workspace_id", ws).in_("campaign_id", [r["id"] for r in rows])) if rows else []
    return {"campaigns": [{**row, "locations": [child for child in children if child["campaign_id"]==row["id"]]} for row in rows]}


class CampaignSchedule(BaseModel):
    publish_at: AwareDatetime


@router.post("/api/platform/campaigns/{campaign_id}/schedule")
async def schedule_campaign(campaign_id: UUID, payload: CampaignSchedule, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    if not settings.google_worker_enabled:
        raise HTTPException(409, "Google scheduled delivery is paused. Enable the Google worker first.")
    ws, _ = await context(None, user, settings, owner=True)
    if payload.publish_at<=datetime.now(UTC):
        raise HTTPException(422, "Choose a future publication time.")
    saved = await service.execute(db().rpc("gbp_control_campaign", {"p_workspace": ws, "p_id": str(campaign_id),
        "p_action": "schedule", "p_when": payload.publish_at.isoformat()}))
    if not saved:
        raise HTTPException(409, "This campaign cannot be scheduled in its current state.")
    return {"status": "scheduled", "campaign_id": str(campaign_id)}


@router.post("/api/platform/campaigns/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: UUID, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings, owner=True)
    saved = await service.execute(db().rpc("gbp_control_campaign", {"p_workspace": ws, "p_id": str(campaign_id),
        "p_action": "cancel", "p_when": None}))
    if not saved:
        raise HTTPException(409, "Delivery has started or this campaign cannot be cancelled.")
    return {"status": "cancelled", "campaign_id": str(campaign_id)}


@router.post("/api/google/analytics")
async def analytics(payload: LocationInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    from datetime import timedelta
    ws, location = await context(payload, user, settings)
    end = datetime.now(UTC).date()-timedelta(days=1)
    start = end-timedelta(days=29)
    params = {"dailyMetrics": ["WEBSITE_CLICKS", "CALL_CLICKS", "BUSINESS_DIRECTION_REQUESTS",
               "BUSINESS_IMPRESSIONS_DESKTOP_MAPS", "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
               "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH", "BUSINESS_IMPRESSIONS_MOBILE_SEARCH"]}
    for prefix, date in (("startDate", start), ("endDate", end)):
        params.update({f"dailyRange.{prefix}.year": date.year, f"dailyRange.{prefix}.month": date.month,
                       f"dailyRange.{prefix}.day": date.day})
    short = location["name"].split("/", 2)[2]
    async with service.connected(settings, ws) as (client, _connection):
        result = await client.call("GET", "businessprofileperformance.googleapis.com", f"v1/{short}:fetchMultiDailyMetricsTimeSeries", params=params)
    return {"status": "success", "analytics": result}


@router.post("/api/google/search-keywords")
async def keywords(payload: LocationInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    from datetime import timedelta
    ws, location = await context(payload, user, settings)
    end = datetime.now(UTC).date().replace(day=1)-timedelta(days=1)
    start = (end.replace(day=1)-timedelta(days=60)).replace(day=1)
    params = {"monthlyRange.startMonth.year": start.year, "monthlyRange.startMonth.month": start.month,
              "monthlyRange.endMonth.year": end.year, "monthlyRange.endMonth.month": end.month,
              "pageSize": 100}
    rows, token = [], ""
    short = location["name"].split("/", 2)[2]
    async with service.connected(settings, ws) as (client, _connection):
        for _ in range(10):
            page = await client.call("GET", "businessprofileperformance.googleapis.com",
                                     f"v1/{short}/searchkeywords/impressions/monthly", params={**params, "pageToken": token})
            rows.extend(page.get("searchKeywordsMonthlyImpressions", []))
            token = page.get("nextPageToken", "")
            if not token:
                break
    return {"status": "success", "keywords": rows, "truncated": bool(token)}


class RankKeywordsInput(LocationInput):
    keywords: list[str] = Field(max_length=10)

    @field_validator("keywords")
    @classmethod
    def unique_keywords(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()) for value in values]
        if any(not value or len(value) > 120 for value in normalized):
            raise ValueError("Each keyword must contain 1 to 120 characters.")
        if len({value.casefold() for value in normalized}) != len(normalized):
            raise ValueError("Each keyword must be unique.")
        return normalized


async def rank_keyword_state(ws: str, location: str, keywords: list[str]):
    rows = await service.execute(db().table("gbp_rank_reports").select("id,keyword,report,status,created_at")
        .eq("workspace_id", ws).eq("location_name", location).in_("keyword", keywords)
        .order("created_at", desc=True).limit(200)) if keywords else []
    latest, completed = {}, {}
    for row in rows:
        latest.setdefault(row["keyword"], row)
        if row["status"] == "completed":
            completed.setdefault(row["keyword"], row)
    reports = []
    for keyword in keywords:
        if keyword not in latest:
            continue
        row = completed.get(keyword, latest[keyword])
        reports.append({**(row.get("report") or {}), "id": row["id"], "keyword": keyword,
                        "status": row["status"], "created_at": row["created_at"],
                        "latest_attempt_status": latest[keyword]["status"]})
    return {"keywords": keywords, "reports": reports}


@router.get("/api/gbp/rank-keywords")
async def get_rank_keywords(location_name: str, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, location = await context(LocationInput(location_name=location_name), user, settings)
    rows = await service.execute(db().table("gbp_rank_keyword_sets").select("keywords")
                                .eq("workspace_id", ws).eq("location_name", location["name"]).limit(1))
    return await rank_keyword_state(ws, location["name"], rows[0]["keywords"] if rows else [])


@router.put("/api/gbp/rank-keywords")
async def save_rank_keywords(payload: RankKeywordsInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, location = await context(payload, user, settings, owner=True)
    await service.execute(db().table("gbp_rank_keyword_sets").upsert({"workspace_id": ws,
        "location_name": location["name"], "keywords": payload.keywords, "updated_at": service.now()},
        on_conflict="location_name"))
    return await rank_keyword_state(ws, location["name"], payload.keywords)


class RankInput(LocationInput):
    keyword: str = Field(min_length=1, max_length=120)
    request_id: UUID

    @field_validator("keyword")
    @classmethod
    def clean_keyword(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("A keyword is required.")
        return value


@router.post("/api/rank/generate-report")
async def rank(payload: RankInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    from app.gbp.rank_service import run_local_rank_scan
    ws, location = await context(payload, user, settings, owner=True)
    if not settings.serpapi_key:
        raise HTTPException(503, "Measured rank reports require the search provider configuration.")
    key = str(payload.request_id)
    existing = await service.execute(db().table("gbp_rank_reports").select("*").eq("workspace_id", ws).eq("request_key", key).limit(1))
    if existing:
        row = existing[0]
        if row["keyword"] != payload.keyword.strip() or row["location_name"] != location["name"]:
            raise HTTPException(409, "This request ID belongs to a different report.")
        if row["status"] != "completed":
            raise HTTPException(409, "This report is processing or failed. Inspect history before creating another.")
        return {"status": "success", "id": row["id"], **row["report"]}
    record_id = str(uuid4())
    saved = await service.execute(db().table("gbp_rank_reports").upsert({"id": record_id, "workspace_id": ws,
        "location_name": location["name"], "request_key": key, "keyword": payload.keyword.strip()},
        on_conflict="workspace_id,request_key", ignore_duplicates=True))
    if not saved:
        raise HTTPException(409, "This report is already being generated.")
    try:
        async with service.connected(settings, ws) as (client, _connection):
            report = await asyncio.to_thread(run_local_rank_scan, location_id=location["name"].split("/", 2)[2],
                                             keyword=payload.keyword.strip(), google_access_token=client.token,
                                             serpapi_key=settings.serpapi_key.get_secret_value())
        await service.execute(db().table("gbp_rank_reports").update({"status": "completed", "report": report})
                              .eq("id", record_id).eq("workspace_id", ws))
    except Exception:
        await service.execute(db().table("gbp_rank_reports").update({"status": "failed"}).eq("id", record_id).eq("workspace_id", ws))
        raise HTTPException(502, "The measured rank report could not be completed. No simulated rank is returned.") from None
    return {"status": "success", "id": record_id, **report}


@router.get("/api/gbp/rank-reports/{report_id}/pdf")
async def rank_pdf(report_id: UUID, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    from app.gbp.rank_service import render_rank_report_pdf
    ws, _ = await context(None, user, settings)
    rows = await service.execute(db().table("gbp_rank_reports").select("report").eq("workspace_id", ws)
                                 .eq("id", str(report_id)).eq("status", "completed").limit(1))
    if not rows:
        raise HTTPException(404, "Report not found.")
    return Response(await asyncio.to_thread(render_rank_report_pdf, rows[0]["report"]), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="Growboard-rank-report.pdf"', "Cache-Control": "private, no-store"})


class DeleteReplyInput(BaseModel):
    review_id: str
    provider_token: str | None = Field(default=None, exclude=True, repr=False)


@router.post("/api/google/delete-reply")
async def delete_reply(payload: DeleteReplyInput, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    try:
        resource(payload.review_id, "review")
    except ValueError:
        raise HTTPException(422, "Invalid review resource.") from None
    ws, _ = await context(LocationInput(location_name=payload.review_id.rsplit("/reviews/", 1)[0]), user, settings, owner=True)
    async with service.connected(settings, ws) as (client, _connection):
        review = await client.review(payload.review_id)
        if not review.get("reviewReply"):
            return {"status": "success", "message": "This review has no reply."}
        version = json.dumps(review["reviewReply"], sort_keys=True)
        key = "delete:"+hashlib.sha256((payload.review_id+version).encode()).hexdigest()
        claimed = await service.execute(db().table("gbp_operations").upsert({"operation_key": key, "workspace_id": ws},
            on_conflict="operation_key", ignore_duplicates=True))
        if not claimed:
            raise HTTPException(409, "This deletion was already attempted. Inspect the Google review before retrying.")
        try:
            await client.delete_reply(payload.review_id)
            state = "completed"
        except GoogleError as error:
            state = "uncertain" if error.uncertain else "failed"
        await service.execute(db().table("gbp_operations").update({"status": state}).eq("operation_key", key).eq("workspace_id", ws))
    if state != "completed":
        raise HTTPException(409, "Deletion is unconfirmed or rejected. Inspect Google before retrying.")
    await service.audit(ws, user.id, "review_reply_deleted", payload.review_id)
    return {"status": "success", "message": "Reply deleted successfully!"}


@router.post("/api/gbp/posts/{post_id}/cancel")
async def cancel_post(post_id: UUID, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings, owner=True)
    rows = await service.execute(db().table("gbp_posts").update({"status": "cancelled"}).eq("id", str(post_id))
                                 .eq("workspace_id", ws).in_("status", ["draft", "scheduled"]))
    if not rows:
        raise HTTPException(409, "This post cannot be cancelled after delivery starts.")
    return {"status": "cancelled"}


@router.get("/api/gbp/audit")
async def audit(user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)):
    ws, _ = await context(None, user, settings)
    return {"events": await service.execute(db().table("gbp_audit").select("action,resource,created_at,user_id")
                                            .eq("workspace_id", ws).order("created_at", desc=True).limit(100))}


@router.post("/api/internal/google/run")
async def run(request: Request, settings: Settings = Depends(get_settings)):
    supplied = request.headers.get("authorization", "")
    if settings.cron_secret == "development-only" or not hmac.compare_digest(supplied, "Bearer "+settings.cron_secret):
        raise HTTPException(401, "Invalid worker authorization.")
    return await jobs.run(settings)


@router.post("/api/webhooks/google-reviews")
async def webhook(request: Request, settings: Settings = Depends(get_settings)):
    service.ready(settings)
    if not settings.google_pubsub_audience or not settings.google_pubsub_service_account:
        raise HTTPException(503, "Google notification authentication is not configured.")
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "Missing Google notification identity.")
    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token
        claims = await asyncio.to_thread(id_token.verify_oauth2_token, header[7:], GoogleRequest(), settings.google_pubsub_audience)
        if claims.get("email") != settings.google_pubsub_service_account or claims.get("email_verified") is not True:
            raise ValueError()
    except Exception:
        raise HTTPException(401, "Invalid Google notification identity.") from None
    if len(await request.body()) > 65536:
        raise HTTPException(413, "Notification is too large.")
    try:
        message = (await request.json())["message"]
        payload = json.loads(base64.b64decode(message["data"], validate=True))
        event_id = message["messageId"]
        if not isinstance(payload, dict) or not isinstance(event_id, str) or len(event_id)>200:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise HTTPException(422, "Invalid Google notification.") from None
    await service.execute(db().table("gbp_events").upsert({"event_id": event_id, "payload": payload}, on_conflict="event_id", ignore_duplicates=True))
    return {"status": "accepted"}
