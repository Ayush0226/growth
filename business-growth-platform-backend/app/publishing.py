import asyncio
from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.database import db, one
from app.meta import MetaAPIError
from app.security import TokenCipher


async def publish_job(job_id: str, workspace_id: str, settings: Settings) -> dict:
    job = one(db().table("publishing_jobs").select("*").eq("id", job_id).eq("workspace_id", workspace_id).limit(1).execute())
    if not job:
        raise ValueError("Publishing job not found")
    if job["status"] == "published":
        return job
    if job["status"] == "processing":
        raise ValueError("Publishing job is already processing")

    claimed = db().table("publishing_jobs").update({"status": "processing", "locked_at": datetime.now(UTC).isoformat(), "locked_by": "api", "attempt_count": job["attempt_count"] + 1}).eq("id", job_id).in_("status", ["draft", "scheduled", "failed"]).execute()
    if not claimed.data:
        raise ValueError("Publishing job could not be claimed")

    try:
        target = one(db().table("content_targets").select("draft_id,social_account_id").eq("id", job["content_target_id"]).execute())
        draft = one(db().table("content_drafts").select("caption,status").eq("id", target["draft_id"]).execute())
        if draft["status"] != "approved":
            raise ValueError("Post must be approved before publishing")
        account = one(db().table("social_accounts").select("provider_account_id,connection_id").eq("id", target["social_account_id"]).execute())
        connection = one(db().table("social_connections").select("access_token_encrypted,status,granted_scopes").eq("id", account["connection_id"]).execute())
        if connection["status"] != "active":
            raise ValueError("Instagram connection expired")
        if "instagram_business_content_publish" not in connection["granted_scopes"]:
            raise ValueError("Publishing permission missing")
        link = one(db().table("content_draft_media").select("media_asset_id").eq("draft_id", target["draft_id"]).order("position").limit(1).execute())
        asset = one(db().table("media_assets").select("prepared_storage_path,original_storage_path,validation_status").eq("id", link["media_asset_id"]).execute())
        if asset["validation_status"] != "valid":
            raise ValueError("Media format unsupported")
        path = asset["prepared_storage_path"] or asset["original_storage_path"]
        signed = db().storage.from_("instagram-media").create_signed_url(path, 3600)
        image_url = signed.get("signedURL") or signed.get("signed_url")
        token = TokenCipher(settings.token_encryption_key).decrypt(connection["access_token_encrypted"])
        base = f"https://graph.instagram.com/{settings.meta_graph_api_version}"
        async with httpx.AsyncClient(timeout=30) as client:
            container_id = job.get("provider_container_id")
            if not container_id:
                response = await client.post(f"{base}/{account['provider_account_id']}/media", data={"image_url": image_url, "caption": draft["caption"], "access_token": token})
                data = response.json()
                if response.status_code >= 400 or "error" in data:
                    raise MetaAPIError(data.get("error", {}).get("message", "Instagram container creation failed"))
                container_id = data["id"]
                db().table("publishing_jobs").update({"provider_container_id": container_id}).eq("id", job_id).execute()
            for _ in range(10):
                status_response = await client.get(f"{base}/{container_id}", params={"fields": "status_code,status", "access_token": token})
                status_data = status_response.json()
                if status_data.get("status_code") == "FINISHED":
                    break
                if status_data.get("status_code") in {"ERROR", "EXPIRED"}:
                    raise MetaAPIError("Instagram processing failed")
                await asyncio.sleep(2)
            else:
                raise MetaAPIError("Instagram processing timed out")
            publish_response = await client.post(f"{base}/{account['provider_account_id']}/media_publish", data={"creation_id": container_id, "access_token": token})
            publish_data = publish_response.json()
            if publish_response.status_code >= 400 or "error" in publish_data:
                raise MetaAPIError(publish_data.get("error", {}).get("message", "Instagram publish failed"))
            media_id = publish_data["id"]
            detail_response = await client.get(f"{base}/{media_id}", params={"fields": "id,permalink", "access_token": token})
            detail = detail_response.json() if detail_response.status_code < 400 else {}
        updated = one(db().table("publishing_jobs").update({"status": "published", "provider_media_id": media_id, "provider_permalink": detail.get("permalink"), "published_at": datetime.now(UTC).isoformat(), "locked_at": None, "locked_by": None, "failure_code": None, "failure_message": None, "retryable": False}).eq("id", job_id).execute())
        db().table("audit_events").insert({"workspace_id": workspace_id, "event_type": "instagram.published", "subject_type": "publishing_job", "subject_id": job_id, "metadata": {"media_id": media_id}}).execute()
        return updated or {"id": job_id, "status": "published", "provider_media_id": media_id}
    except Exception as exc:
        retryable = isinstance(exc, (httpx.HTTPError, MetaAPIError))
        db().table("publishing_jobs").update({"status": "failed", "failure_code": "temporary_meta_error" if retryable else "validation_error", "failure_message": str(exc)[:500], "retryable": retryable, "locked_at": None, "locked_by": None}).eq("id", job_id).execute()
        raise
