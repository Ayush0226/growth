import asyncio
import secrets
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from app.config import Settings, get_settings
from app.database import db, one
from app.images import MAX_SOURCE_BYTES, prepare_image
from app.publishing import publish_job
from app.routes.instagram import user_workspace
from app.security import CurrentUser, current_user

router = APIRouter(prefix="/api", tags=["content"])
image_preparation = asyncio.Semaphore(1)


@router.post("/media", status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...), user: CurrentUser = Depends(current_user)
) -> dict:
    workspace_id = await asyncio.to_thread(user_workspace, user.id)
    # Decode one image at a time; move CPU and storage work off the API event loop.
    async with image_preparation:
        content = await file.read(MAX_SOURCE_BYTES + 1)
        content, width, height = await asyncio.to_thread(prepare_image, content)
        return await asyncio.to_thread(store_image, workspace_id, user.id, content, width, height)


def store_image(workspace_id: str, user_id: str, content: bytes, width: int, height: int):
    asset_id = str(uuid.uuid4())
    path = f"{workspace_id}/{asset_id}/original.jpg"
    db().storage.from_("instagram-media").upload(
        path, content, {"content-type": "image/jpeg", "upsert": "false"}
    )
    row = one(
        db()
        .table("media_assets")
        .insert(
            {
                "id": asset_id,
                "workspace_id": workspace_id,
                "created_by": user_id,
                "original_storage_path": path,
                "prepared_storage_path": path,
                "media_type": "image",
                "mime_type": "image/jpeg",
                "bytes": len(content),
                "width": width,
                "height": height,
                "validation_status": "valid",
            }
        )
        .execute()
    )
    return row


class DraftCreate(BaseModel):
    caption: str = Field(max_length=2200)
    media_asset_id: str | None = None
    media_asset_ids: list[str] = Field(default_factory=list, max_length=10)
    request_id: uuid.UUID | None = None
    enqueue_only: bool = False
    scheduled_for: AwareDatetime | None = None
    timezone: str = "UTC"
    approved: bool = False
    publish_now: bool = False

    @model_validator(mode="after")
    def valid_media(self):
        if self.media_asset_id and self.media_asset_ids:
            raise ValueError("Choose either one image or an image list")
        ids = self.asset_ids
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Choose between one and ten different images")
        return self

    @property
    def asset_ids(self) -> list[str]:
        return [self.media_asset_id] if self.media_asset_id else self.media_asset_ids

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose a valid IANA timezone") from None
        return value


class ScheduleUpdate(BaseModel):
    caption: str | None = Field(default=None, max_length=2200)
    scheduled_for: AwareDatetime | None = None

    @field_validator("scheduled_for")
    @classmethod
    def future_time(cls, value):
        if value is not None and value <= datetime.now(UTC):
            raise ValueError("Choose a future schedule time")
        return value


@router.post("/content/posts", status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: DraftCreate,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    workspace_id = user_workspace(user.id)
    if not payload.approved:
        raise HTTPException(422, "Approve the image and caption before publishing or scheduling")
    asset_ids = payload.asset_ids
    post_type = "carousel" if len(asset_ids) > 1 else "photo"
    request_id = str(payload.request_id or uuid.uuid4())
    draft_id = str(uuid.uuid5(uuid.NAMESPACE_URL, workspace_id + request_id + ":draft"))
    target_id = str(uuid.uuid5(uuid.NAMESPACE_URL, workspace_id + request_id + ":target"))
    job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, workspace_id + request_id + ":job"))
    existing_draft = one(
        db()
        .table("content_drafts")
        .select("*")
        .eq("id", draft_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    if existing_draft:
        links = (
            db()
            .table("content_draft_media")
            .select("media_asset_id")
            .eq("draft_id", draft_id)
            .order("position")
            .execute()
            .data
        )
        if (
            existing_draft["caption"] != payload.caption
            or existing_draft["post_type"] != post_type
            or (links and [item["media_asset_id"] for item in links] != asset_ids)
        ):
            raise HTTPException(
                409, "This request already belongs to a different post. Start a new post."
            )
        existing_job = one(
            db()
            .table("publishing_jobs")
            .select("*")
            .eq("id", job_id)
            .eq("workspace_id", workspace_id)
            .execute()
        )
        if existing_job:
            return {"draft": existing_draft, "job": existing_job}
    if not payload.publish_now and (
        payload.scheduled_for is None or payload.scheduled_for <= datetime.now(UTC)
    ):
        raise HTTPException(422, "Choose a future schedule time")
    connection = one(
        db()
        .table("social_connections")
        .select("id,granted_scopes")
        .eq("workspace_id", workspace_id)
        .eq("status", "active")
        .execute()
    )
    if not connection or "instagram_business_content_publish" not in connection["granted_scopes"]:
        raise HTTPException(409, "Connect Instagram and grant publishing permission first")
    assets = (
        db()
        .table("media_assets")
        .select("id,width,height,media_type")
        .in_("id", asset_ids)
        .eq("workspace_id", workspace_id)
        .eq("validation_status", "valid")
        .execute()
        .data
    )
    if {asset["id"] for asset in assets} != set(asset_ids) or any(
        asset["media_type"] != "image" for asset in assets
    ):
        raise HTTPException(422, "Choose valid uploaded images from this workspace")
    if post_type == "carousel":
        ratios = [asset["width"] / asset["height"] for asset in assets]
        if max(ratios) - min(ratios) > 0.01:
            raise HTTPException(
                422,
                "Use the same image proportions for every carousel slide. Separate posts can use different proportions.",
            )
    account = one(
        db()
        .table("social_accounts")
        .select("id")
        .eq("workspace_id", workspace_id)
        .eq("connection_id", connection["id"])
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    if not account:
        raise HTTPException(409, "Connect Instagram before creating a post")
    db().table("content_drafts").upsert(
        {
            "id": draft_id,
            "workspace_id": workspace_id,
            "created_by": user.id,
            "post_type": post_type,
            "caption": payload.caption,
            "status": "approved",
            "approved_by": user.id,
            "approved_at": datetime.now(UTC).isoformat(),
        },
        on_conflict="id",
        ignore_duplicates=True,
    ).execute()
    db().table("content_draft_media").upsert(
        [
            {
                "workspace_id": workspace_id,
                "draft_id": draft_id,
                "media_asset_id": asset_id,
                "position": position,
            }
            for position, asset_id in enumerate(asset_ids)
        ],
        on_conflict="draft_id,position",
        ignore_duplicates=True,
    ).execute()
    scheduled_for = datetime.now(UTC) if payload.publish_now else payload.scheduled_for
    db().table("content_targets").upsert(
        {
            "id": target_id,
            "workspace_id": workspace_id,
            "draft_id": draft_id,
            "social_account_id": account["id"],
            "scheduled_for": scheduled_for.isoformat(),
            "timezone": payload.timezone,
        },
        on_conflict="id",
        ignore_duplicates=True,
    ).execute()
    db().table("publishing_jobs").upsert(
        {
            "id": job_id,
            "idempotency_key": request_id,
            "workspace_id": workspace_id,
            "content_target_id": target_id,
            "status": "scheduled",
            "scheduled_for": scheduled_for.isoformat(),
        },
        on_conflict="id",
        ignore_duplicates=True,
    ).execute()
    job = one(
        db()
        .table("publishing_jobs")
        .select("*")
        .eq("id", job_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    draft = one(
        db()
        .table("content_drafts")
        .select("*")
        .eq("id", draft_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    if payload.publish_now and not payload.enqueue_only and job["status"] == "scheduled":
        try:
            job = await publish_job(job["id"], workspace_id, settings)
        except Exception:  # noqa: BLE001 - preserve an uncertain public publishing result
            raise HTTPException(
                502, "Publishing needs attention. Check this post in Calendar before retrying."
            ) from None
    return {"draft": draft, "job": job}


@router.get("/content/calendar")
def calendar(user: CurrentUser = Depends(current_user)) -> dict:
    workspace_id = user_workspace(user.id)
    rows = (
        db()
        .table("publishing_jobs")
        .select(
            "id,status,scheduled_for,published_at,provider_permalink,failure_message,content_targets!inner(draft_id,timezone,content_drafts!inner(caption,post_type))"
        )
        .eq("workspace_id", workspace_id)
        .order("scheduled_for")
        .execute()
        .data
    )
    return {"items": rows}


@router.patch("/content/calendar/{job_id}")
def update_calendar_item(
    job_id: str, payload: ScheduleUpdate, user: CurrentUser = Depends(current_user)
) -> dict:
    workspace_id = user_workspace(user.id)
    job = one(
        db()
        .table("publishing_jobs")
        .select("id,status,content_target_id")
        .eq("id", job_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    if not job:
        raise HTTPException(404, "Calendar item not found")
    if job["status"] not in {"scheduled", "failed"}:
        raise HTTPException(409, "Only scheduled or failed posts can be edited")
    target = one(
        db()
        .table("content_targets")
        .select("draft_id")
        .eq("id", job["content_target_id"])
        .execute()
    )
    if payload.caption is not None:
        db().table("content_drafts").update(
            {"caption": payload.caption, "updated_at": datetime.now(UTC).isoformat()}
        ).eq("id", target["draft_id"]).execute()
    updates = {"updated_at": datetime.now(UTC).isoformat()}
    if payload.scheduled_for is not None:
        updates["scheduled_for"] = payload.scheduled_for.isoformat()
        db().table("content_targets").update(
            {"scheduled_for": payload.scheduled_for.isoformat()}
        ).eq("id", job["content_target_id"]).execute()
    return one(db().table("publishing_jobs").update(updates).eq("id", job_id).execute())


@router.delete("/content/calendar/{job_id}")
def cancel_calendar_item(job_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    workspace_id = user_workspace(user.id)
    job = one(
        db()
        .table("publishing_jobs")
        .select("id,status")
        .eq("id", job_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    if not job:
        raise HTTPException(404, "Calendar item not found")
    if job["status"] not in {"scheduled", "failed"}:
        raise HTTPException(409, "This post can no longer be cancelled")
    cancelled = one(
        db()
        .table("publishing_jobs")
        .update({"status": "cancelled", "updated_at": datetime.now(UTC).isoformat()})
        .eq("id", job_id)
        .eq("workspace_id", workspace_id)
        .in_("status", ["scheduled", "failed"])
        .execute()
    )
    if not cancelled:
        raise HTTPException(409, "This post started processing and cannot be cancelled")
    return cancelled


@router.post("/publishing/jobs/{job_id}/publish")
async def publish(
    job_id: str,
    user: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    workspace_id = user_workspace(user.id)
    try:
        return await publish_job(job_id, workspace_id, settings)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/internal/publishing/run")
async def run_due_jobs(
    x_cron_secret: str = Header(), settings: Settings = Depends(get_settings)
) -> dict:
    if not secrets.compare_digest(x_cron_secret, settings.cron_secret):
        scheduler = one(
            db().table("scheduler_configuration").select("secret").eq("name", "mvp").execute()
        )
        if not scheduler or not secrets.compare_digest(x_cron_secret, scheduler["secret"]):
            raise HTTPException(401, "Invalid scheduler secret")
    from app.worker import run_pending

    return await run_pending(settings)
