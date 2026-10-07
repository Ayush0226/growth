import io
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.database import db, one
from app.publishing import publish_job
from app.routes.instagram import user_workspace
from app.security import CurrentUser, current_user

router = APIRouter(prefix="/api", tags=["content"])


@router.post("/media", status_code=status.HTTP_201_CREATED)
async def upload_media(file: UploadFile = File(...), user: CurrentUser = Depends(current_user)) -> dict:
    workspace_id = user_workspace(user.id)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(422, "Image must be 10 MB or smaller")
    if file.content_type not in {"image/jpeg", "image/jpg"}:
        raise HTTPException(422, "The MVP currently accepts JPEG images only")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(422, "The uploaded file is not a valid JPEG") from exc
    ratio = width / height
    errors = []
    if width < 320 or height < 320:
        errors.append("Image dimensions must be at least 320×320")
    if not 0.8 <= ratio <= 1.91:
        errors.append("Aspect ratio must be between 4:5 and 1.91:1")
    if errors:
        raise HTTPException(422, errors)
    asset_id = str(uuid.uuid4())
    path = f"{workspace_id}/{asset_id}/original.jpg"
    db().storage.from_("instagram-media").upload(path, content, {"content-type": "image/jpeg", "upsert": "false"})
    row = one(db().table("media_assets").insert({"id": asset_id, "workspace_id": workspace_id, "created_by": user.id, "original_storage_path": path, "prepared_storage_path": path, "media_type": "image", "mime_type": "image/jpeg", "bytes": len(content), "width": width, "height": height, "validation_status": "valid"}).execute())
    return row


class DraftCreate(BaseModel):
    caption: str = Field(max_length=2200)
    media_asset_id: str
    scheduled_for: datetime | None = None
    timezone: str = "UTC"
    approved: bool = True
    publish_now: bool = False


class ScheduleUpdate(BaseModel):
    caption: str | None = Field(default=None, max_length=2200)
    scheduled_for: datetime | None = None


@router.post("/content/posts", status_code=status.HTTP_201_CREATED)
async def create_post(payload: DraftCreate, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)) -> dict:
    workspace_id = user_workspace(user.id)
    asset = one(db().table("media_assets").select("id").eq("id", payload.media_asset_id).eq("workspace_id", workspace_id).eq("validation_status", "valid").execute())
    if not asset:
        raise HTTPException(422, "Select a valid uploaded image")
    account = one(db().table("social_accounts").select("id").eq("workspace_id", workspace_id).limit(1).execute())
    if not account:
        raise HTTPException(409, "Connect Instagram before creating a post")
    draft_status = "approved" if payload.approved else "draft"
    draft = one(db().table("content_drafts").insert({"workspace_id": workspace_id, "created_by": user.id, "post_type": "photo", "caption": payload.caption, "status": draft_status, "approved_by": user.id if payload.approved else None, "approved_at": datetime.now(UTC).isoformat() if payload.approved else None}).execute())
    db().table("content_draft_media").insert({"workspace_id": workspace_id, "draft_id": draft["id"], "media_asset_id": payload.media_asset_id, "position": 0}).execute()
    scheduled_for = payload.scheduled_for or datetime.now(UTC)
    target = one(db().table("content_targets").insert({"workspace_id": workspace_id, "draft_id": draft["id"], "social_account_id": account["id"], "scheduled_for": scheduled_for.isoformat(), "timezone": payload.timezone}).execute())
    job = one(db().table("publishing_jobs").insert({"workspace_id": workspace_id, "content_target_id": target["id"], "status": "scheduled", "scheduled_for": scheduled_for.isoformat()}).execute())
    if payload.publish_now:
        try:
            job = await publish_job(job["id"], workspace_id, settings)
        except Exception as exc:
            raise HTTPException(502, str(exc)) from exc
    return {"draft": draft, "job": job}


@router.get("/content/calendar")
def calendar(user: CurrentUser = Depends(current_user)) -> dict:
    workspace_id = user_workspace(user.id)
    rows = db().table("publishing_jobs").select("id,status,scheduled_for,published_at,provider_permalink,failure_message,content_targets!inner(draft_id,timezone,content_drafts!inner(caption,post_type))").eq("workspace_id", workspace_id).order("scheduled_for").execute().data
    return {"items": rows}


@router.patch("/content/calendar/{job_id}")
def update_calendar_item(job_id: str, payload: ScheduleUpdate, user: CurrentUser = Depends(current_user)) -> dict:
    workspace_id = user_workspace(user.id)
    job = one(db().table("publishing_jobs").select("id,status,content_target_id").eq("id", job_id).eq("workspace_id", workspace_id).execute())
    if not job:
        raise HTTPException(404, "Calendar item not found")
    if job["status"] not in {"scheduled", "failed"}:
        raise HTTPException(409, "Only scheduled or failed posts can be edited")
    target = one(db().table("content_targets").select("draft_id").eq("id", job["content_target_id"]).execute())
    if payload.caption is not None:
        db().table("content_drafts").update({"caption": payload.caption, "updated_at": datetime.now(UTC).isoformat()}).eq("id", target["draft_id"]).execute()
    updates = {"updated_at": datetime.now(UTC).isoformat()}
    if payload.scheduled_for is not None:
        updates["scheduled_for"] = payload.scheduled_for.isoformat()
        db().table("content_targets").update({"scheduled_for": payload.scheduled_for.isoformat()}).eq("id", job["content_target_id"]).execute()
    return one(db().table("publishing_jobs").update(updates).eq("id", job_id).execute())


@router.delete("/content/calendar/{job_id}")
def cancel_calendar_item(job_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    workspace_id = user_workspace(user.id)
    job = one(db().table("publishing_jobs").select("id,status").eq("id", job_id).eq("workspace_id", workspace_id).execute())
    if not job:
        raise HTTPException(404, "Calendar item not found")
    if job["status"] not in {"scheduled", "failed"}:
        raise HTTPException(409, "This post can no longer be cancelled")
    return one(db().table("publishing_jobs").update({"status": "cancelled", "updated_at": datetime.now(UTC).isoformat()}).eq("id", job_id).execute())


@router.post("/publishing/jobs/{job_id}/publish")
async def publish(job_id: str, user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings)) -> dict:
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
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(401, "Invalid scheduler secret")
    due = (
        db()
        .table("publishing_jobs")
        .select("id,workspace_id")
        .eq("status", "scheduled")
        .lte("scheduled_for", datetime.now(UTC).isoformat())
        .order("scheduled_for")
        .limit(10)
        .execute()
        .data
    )
    results = []
    for job in due:
        try:
            await publish_job(job["id"], job["workspace_id"], settings)
            results.append({"id": job["id"], "status": "published"})
        except Exception:  # noqa: BLE001 - one failed job must not stop the scheduler batch
            results.append({"id": job["id"], "status": "failed"})
    return {"processed": len(results), "results": results}
