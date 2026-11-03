import asyncio
import logging
from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.database import db, one
from app.meta import InstagramClient, MetaAPIError
from app.security import TokenCipher

logger = logging.getLogger(__name__)


async def publish_job(job_id: str, workspace_id: str, settings: Settings) -> dict:
    job = one(
        db()
        .table("publishing_jobs")
        .select("*")
        .eq("id", job_id)
        .eq("workspace_id", workspace_id)
        .limit(1)
        .execute()
    )
    if not job:
        raise ValueError("Publishing job not found")
    if job["status"] == "published":
        return job
    if job["status"] == "processing":
        raise ValueError("Publishing job is already processing")

    claimed = (
        db()
        .table("publishing_jobs")
        .update(
            {
                "status": "processing",
                "locked_at": datetime.now(UTC).isoformat(),
                "locked_by": "api",
                "attempt_count": job["attempt_count"] + 1,
            }
        )
        .eq("id", job_id)
        .in_("status", ["draft", "scheduled", "failed"])
        .execute()
    )
    if not claimed.data:
        raise ValueError("Publishing job could not be claimed")

    token = ""
    publication_started = False
    published = False
    try:
        target = one(
            db()
            .table("content_targets")
            .select("draft_id,social_account_id")
            .eq("id", job["content_target_id"])
            .execute()
        )
        draft = one(
            db()
            .table("content_drafts")
            .select("caption,status,post_type")
            .eq("id", target["draft_id"])
            .execute()
        )
        if draft["status"] != "approved":
            raise ValueError("Post must be approved before publishing")
        account = one(
            db()
            .table("social_accounts")
            .select("provider_account_id,connection_id")
            .eq("id", target["social_account_id"])
            .execute()
        )
        connection = one(
            db()
            .table("social_connections")
            .select("access_token_encrypted,status,granted_scopes,active_account_id")
            .eq("id", account["connection_id"])
            .execute()
        )
        if connection["status"] != "active":
            raise ValueError("Instagram connection expired")
        if (
            connection.get("active_account_id")
            and connection["active_account_id"] != account["provider_account_id"]
        ):
            raise ValueError("This post belongs to a previously connected Instagram account")
        if "instagram_business_content_publish" not in connection["granted_scopes"]:
            raise ValueError("Publishing permission missing")
        links = (
            db()
            .table("content_draft_media")
            .select("media_asset_id,position")
            .eq("draft_id", target["draft_id"])
            .order("position")
            .limit(10)
            .execute()
            .data
        )
        carousel = draft.get("post_type") == "carousel"
        if (
            not links
            or (carousel and not 2 <= len(links) <= 10)
            or (not carousel and len(links) != 1)
        ):
            raise ValueError("The post has an invalid number of images")
        image_urls = []
        for link in links:
            asset = one(
                db()
                .table("media_assets")
                .select("prepared_storage_path,original_storage_path,validation_status")
                .eq("id", link["media_asset_id"])
                .execute()
            )
            if not asset or asset["validation_status"] != "valid":
                raise ValueError("Media format unsupported")
            path = asset["prepared_storage_path"] or asset["original_storage_path"]
            signed = db().storage.from_("instagram-media").create_signed_url(path, 3600)
            image_url = signed.get("signedURL") or signed.get("signed_url")
            if not image_url:
                raise ValueError("An image could not be prepared for Instagram")
            image_urls.append(image_url)
        token = TokenCipher(settings.token_encryption_key).decrypt(
            connection["access_token_encrypted"]
        )
        base = f"https://graph.instagram.com/{settings.meta_graph_api_version}"
        async with httpx.AsyncClient(timeout=30) as client:
            container_id = job.get("provider_container_id")
            if not container_id:
                if carousel:
                    children = []
                    for image_url in image_urls:
                        child_response = await client.post(
                            f"{base}/{account['provider_account_id']}/media",
                            data={
                                "image_url": image_url,
                                "is_carousel_item": "true",
                                "access_token": token,
                            },
                        )
                        child = InstagramClient._json(child_response)
                        for _ in range(10):
                            child_status = InstagramClient._json(
                                await client.get(
                                    f"{base}/{child['id']}",
                                    params={"fields": "status_code", "access_token": token},
                                )
                            )
                            if child_status.get("status_code") == "FINISHED":
                                break
                            if child_status.get("status_code") in {"ERROR", "EXPIRED", "PUBLISHED"}:
                                raise MetaAPIError("Instagram could not prepare a carousel slide")
                            await asyncio.sleep(2)
                        else:
                            raise MetaAPIError("A carousel slide took too long to prepare")
                        children.append(child["id"])
                    container_data = {
                        "media_type": "CAROUSEL",
                        "children": ",".join(children),
                        "caption": draft["caption"],
                        "access_token": token,
                    }
                else:
                    container_data = {
                        "image_url": image_urls[0],
                        "caption": draft["caption"],
                        "access_token": token,
                    }
                response = await client.post(
                    f"{base}/{account['provider_account_id']}/media",
                    data=container_data,
                )
                data = InstagramClient._json(response)
                container_id = data["id"]
                db().table("publishing_jobs").update({"provider_container_id": container_id}).eq(
                    "id", job_id
                ).execute()
            for _ in range(10):
                status_response = await client.get(
                    f"{base}/{container_id}",
                    params={"fields": "status_code,status", "access_token": token},
                )
                status_data = InstagramClient._json(status_response)
                if status_data.get("status_code") == "PUBLISHED":
                    publication_started = True
                    raise MetaAPIError(
                        "This Instagram container is already published; verify its result before retrying"
                    )
                if status_data.get("status_code") == "FINISHED":
                    break
                if status_data.get("status_code") in {"ERROR", "EXPIRED"}:
                    raise MetaAPIError("Instagram processing failed")
                await asyncio.sleep(2)
            else:
                raise MetaAPIError("Instagram processing timed out")
            publication_started = True
            publish_response = await client.post(
                f"{base}/{account['provider_account_id']}/media_publish",
                data={"creation_id": container_id, "access_token": token},
            )
            publish_data = publish_response.json()
            if publish_response.status_code >= 400 or "error" in publish_data:
                raise MetaAPIError(
                    publish_data.get("error", {}).get("message", "Instagram publish failed")
                )
            media_id = publish_data["id"]
            updated = one(
                db()
                .table("publishing_jobs")
                .update(
                    {
                        "status": "published",
                        "provider_media_id": media_id,
                        "published_at": datetime.now(UTC).isoformat(),
                        "locked_at": None,
                        "locked_by": None,
                        "failure_code": None,
                        "failure_message": None,
                        "retryable": False,
                    }
                )
                .eq("id", job_id)
                .execute()
            )
            published = True
            try:
                detail_response = await client.get(
                    f"{base}/{media_id}", params={"fields": "id,permalink", "access_token": token}
                )
                detail = detail_response.json() if detail_response.status_code < 400 else {}
                if detail.get("permalink"):
                    db().table("publishing_jobs").update(
                        {"provider_permalink": detail["permalink"]}
                    ).eq("id", job_id).execute()
                    if updated:
                        updated["provider_permalink"] = detail["permalink"]
                db().table("audit_events").insert(
                    {
                        "workspace_id": workspace_id,
                        "event_type": "instagram.published",
                        "subject_type": "publishing_job",
                        "subject_id": job_id,
                        "metadata": {"media_id": media_id},
                    }
                ).execute()
            except Exception:  # noqa: BLE001 - optional metadata must not turn a published post into a retry
                logger.warning(
                    "Post published; optional permalink or audit lookup failed for job %s", job_id
                )
        return updated or {"id": job_id, "status": "published", "provider_media_id": media_id}
    except Exception as exc:
        if published:
            raise
        retryable = isinstance(exc, (httpx.HTTPError, MetaAPIError))
        # After media_publish is attempted, a timeout cannot prove that nothing was published.
        db().table("publishing_jobs").update(
            {
                "status": "processing" if publication_started else "failed",
                "failure_code": "publication_uncertain"
                if publication_started
                else ("temporary_meta_error" if retryable else "validation_error"),
                "failure_message": "Check Instagram before retrying; publication could not be confirmed."
                if publication_started
                else (str(exc).replace(token, "[redacted]") if token else str(exc))[:500],
                "retryable": retryable and not publication_started,
                "locked_at": None,
                "locked_by": None,
            }
        ).eq("id", job_id).execute()
        raise
