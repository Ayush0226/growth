"""Independent Google processing. Never invoked from the Meta worker loop."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException

from app.config import Settings
from app.database import db
from app.gbp import service
from app.gbp.provider import GoogleError, resource
from app.google_review_policy import ReviewRule, ReviewSnapshot, evaluate_review

RATINGS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def snapshot(workspace: str, location: str, review: dict):
    name = review.get("name") or f"{location}/reviews/{review['reviewId']}"
    resource(name, "review")
    if name.rsplit("/reviews/", 1)[0] != location:
        raise ValueError("Review location mismatch")
    return ReviewSnapshot(workspace_id=workspace, name=name, rating=RATINGS[review["starRating"]],
                          created_at=review["createTime"], updated_at=review.get("updateTime", review["createTime"]),
                          comment=review.get("comment", ""), has_reply=bool(review.get("reviewReply")))


def eligibility(rule: dict, review: dict):
    policy = ReviewRule(**{**rule, "location_name": rule["location_name"]})
    return evaluate_review(policy, snapshot(rule["workspace_id"], rule["location_name"], review),
                           now=datetime.now(UTC), connection_active=True,
                           delivery_owned=rule["delivery_owned"], reserved_today=0)


async def enqueue_review(rule: dict, review: dict):
    decision = eligibility(rule, review)
    if decision.action == "skip":
        return False
    item = snapshot(rule["workspace_id"], rule["location_name"], review)
    await service.execute(db().table("gbp_review_jobs").upsert({
        "workspace_id": rule["workspace_id"], "location_name": rule["location_name"],
        "review_name": item.name, "review_data": review, "status": "pending",
        "not_before": (decision.eligible_at or datetime.now(UTC)).isoformat(),
    }, on_conflict="review_name", ignore_duplicates=True))
    return True


async def poll_reviews(settings: Settings):
    rules = await service.execute(db().table("gbp_review_rules").select("*").eq("enabled", True).limit(100))
    enqueued, failed = 0, 0
    for rule in rules:
        try:
            await service.owned_location(rule["workspace_id"], rule["location_name"])
            async with service.connected(settings, rule["workspace_id"]) as (client, _connection):
                token = ""
                for _ in range(3):
                    page = await client.reviews(rule["location_name"], token)
                    for review in page.get("reviews", []):
                        enqueued += bool(await enqueue_review(rule, review))
                    token = page.get("nextPageToken", "")
                    if not token:
                        break
        except Exception:
            # One expired Google grant cannot stop other workspaces or Meta jobs.
            failed += 1
    return {"eligible_seen": enqueued, "location_failures": failed}


async def process_events(settings: Settings):
    events = await service.execute(db().table("gbp_events").select("*").eq("status", "pending")
                                   .order("received_at").limit(25))
    for event in events:
        try:
            payload = event["payload"]
            if payload.get("notificationType") not in {"NEW_REVIEW", "UPDATED_REVIEW"}:
                state = "processed"
            else:
                name = resource(payload.get("reviewName", ""), "review")
                location = name.rsplit("/reviews/", 1)[0]
                rules = await service.execute(db().table("gbp_review_rules").select("*")
                                              .eq("location_name", location).eq("enabled", True).limit(1))
                if rules:
                    rule = rules[0]
                    await service.owned_location(rule["workspace_id"], location)
                    async with service.connected(settings, rule["workspace_id"]) as (client, _connection):
                        await enqueue_review(rule, await client.review(name))
                state = "processed"
        except Exception:
            state = "failed" if event["attempts"] >= 4 else "pending"
        await service.execute(db().table("gbp_events").update({"status": state, "attempts": event["attempts"]+1})
                              .eq("event_id", event["event_id"]))


async def set_job(job: dict, status: str, **values):
    return await service.execute(db().table("gbp_review_jobs").update({"status": status, "updated_at": service.now(), **values})
                                 .eq("id", job["id"]).eq("workspace_id", job["workspace_id"]))


async def prepare_reply(settings: Settings, job: dict):
    holder = str(uuid4())
    claimed = await service.execute(db().table("gbp_review_jobs").update({
        "status": "generating", "lease_owner": holder,
        "lease_until": (datetime.now(UTC)+timedelta(minutes=5)).isoformat(),
    }).eq("id", job["id"]).eq("status", "pending"))
    if not claimed:
        return
    try:
        rules = await service.execute(db().table("gbp_review_rules").select("*")
                                      .eq("workspace_id", job["workspace_id"]).eq("location_name", job["location_name"]).limit(1))
        if not rules:
            await set_job(job, "skipped", error_code="rule_missing")
            return
        rule = rules[0]
        location = await service.owned_location(job["workspace_id"], job["location_name"])
        async with service.connected(settings, job["workspace_id"]) as (client, _connection):
            review = await client.review(job["review_name"])
        decision = eligibility(rule, review)
        if decision.action == "skip":
            await set_job(job, "skipped", error_code=decision.reason)
            return
        if decision.action == "wait":
            await set_job(job, "pending", not_before=decision.eligible_at.isoformat())
            return
        text = await service.generate_reply(settings, review, rule, location["title"])
        # Conditional update cannot resurrect a job cancelled by pause/disconnect.
        await service.execute(db().table("gbp_review_jobs").update({
            "reply_text": text, "review_data": review, "status": {"auto_publish": "ready"}.get(rule["mode"], rule["mode"]),
            "lease_owner": None, "lease_until": None, "updated_at": service.now(),
        }).eq("id", job["id"]).eq("status", "generating").eq("lease_owner", holder))
    except Exception:
        await service.execute(db().table("gbp_review_jobs").update({"status": "failed", "error_code": "preparation_failed"})
                              .eq("id", job["id"]).eq("status", "generating").eq("lease_owner", holder))


async def deliver_reply(settings: Settings, job: dict):
    holder = str(uuid4())
    claimed = await service.execute(db().rpc("gbp_claim_reply", {"p_job": job["id"], "p_holder": holder}))
    if not claimed:
        return {"status": "not_claimed"}
    attempted = False
    try:
        await service.owned_location(job["workspace_id"], job["location_name"])
        async with service.connected(settings, job["workspace_id"]) as (client, connection):
            review = await client.review(job["review_name"])
            replacing = bool(job["manual"] and job["review_data"].get("reviewReply"))
            if review.get("reviewReply") and not replacing:
                await set_job(job, "skipped", error_code="already_replied")
                return {"status": "skipped"}
            if replacing and review.get("reviewReply") != job["review_data"].get("reviewReply"):
                await set_job(job, "skipped", error_code="reply_changed")
                return {"status": "skipped"}
            if not job["manual"]:
                rules = await service.execute(db().table("gbp_review_rules").select("*")
                                              .eq("workspace_id", job["workspace_id"]).eq("location_name", job["location_name"]).limit(1))
                if not rules:
                    await set_job(job, "skipped", error_code="rule_missing")
                    return {"status": "skipped"}
                decision = eligibility(rules[0], review)
                if decision.action in {"skip", "wait"}:
                    await set_job(job, "skipped", error_code=decision.reason)
                    return {"status": "skipped"}
                if decision.action != "auto_publish":
                    await set_job(job, decision.action)
                    return {"status": decision.action}
                if review.get("updateTime") != job["review_data"].get("updateTime"):
                    await set_job(job, "pending", reply_text=None, review_data=review)
                    return {"status": "pending"}
            # Recheck connection revision and rule immediately before provider write.
            current = await service.execute(db().table("gbp_connections").select("status,revision")
                                            .eq("workspace_id", job["workspace_id"]).limit(1))
            if not current or current[0]["status"] != "active" or current[0]["revision"] != connection["revision"]:
                await set_job(job, "cancelled", error_code="connection_changed")
                return {"status": "cancelled"}
            if not job.get("reply_text"):
                raise ValueError("Empty reply")
            if not job["manual"]:
                still_enabled = await service.execute(db().table("gbp_review_rules").select("enabled,mode,delivery_owned")
                                                      .eq("location_name", job["location_name"]).eq("workspace_id", job["workspace_id"]).limit(1))
                if not still_enabled or not still_enabled[0]["enabled"] or not still_enabled[0]["delivery_owned"] or still_enabled[0]["mode"] != "auto_publish":
                    await set_job(job, "cancelled", error_code="rule_changed")
                    return {"status": "cancelled"}
            attempted = True
            result = await client.reply(job["review_name"], job["reply_text"])
            await set_job(job, "sent", provider_result=result, error_code=None)
        return {"status": "published"}
    except GoogleError as error:
        await set_job(job, "uncertain" if error.uncertain else "failed", error_code="google_delivery_unconfirmed" if error.uncertain else "google_rejected")
        return {"status": "uncertain" if error.uncertain else "failed"}
    except Exception:
        # Persisting success can fail after Google accepted the write. Never reopen it.
        if attempted:
            try:
                await set_job(job, "uncertain", error_code="delivery_unconfirmed")
            except Exception:
                pass  # publishing state stays held; expiry reconciliation must not resend.
        else:
            await set_job(job, "failed", error_code="preflight_failed")
        return {"status": "uncertain" if attempted else "failed"}


async def deliver_post(settings: Settings, post: dict):
    if datetime.fromisoformat(post["scheduled_for"]) < datetime.now(UTC)-timedelta(days=1):
        await service.execute(db().table("gbp_posts").update({"status": "failed", "error_code": "schedule_missed"})
                              .eq("id", post["id"]).eq("status", "scheduled"))
        return {"status": "failed"}
    claimed = await service.execute(db().rpc("gbp_claim_post", {"p_post": post["id"]}))
    if not claimed:
        return {"status": "not_claimed"}
    attempted = False
    try:
        await service.owned_location(post["workspace_id"], post["location_name"])
        async with service.connected(settings, post["workspace_id"]) as (client, connection):
            payload = dict(post["payload"])
            asset_id = payload.pop("_media_asset_id", None)
            if asset_id:
                assets = await service.execute(db().table("gbp_media_assets").select("storage_path")
                                               .eq("id", asset_id).eq("workspace_id", post["workspace_id"]).limit(1))
                if not assets:
                    raise ValueError("Media is unavailable")
                path = assets[0]["storage_path"]
                signed = await asyncio.to_thread(lambda: db().storage.from_("gbp-media").create_signed_url(path, 3600))
                payload["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": signed["signedURL"]}]
            current = await service.execute(db().table("gbp_connections").select("status,revision")
                                            .eq("workspace_id", post["workspace_id"]).limit(1))
            if not current or current[0]["status"] != "active" or current[0]["revision"] != connection["revision"]:
                raise ValueError("Connection changed")
            attempted = True
            result = await client.publish(post["location_name"], payload)
        status, error_code = "published", None
    except GoogleError as error:
        status = "uncertain" if error.uncertain else "failed"
        error_code, result = "google_delivery_error", None
    except Exception:
        status = "uncertain" if attempted else "failed"
        error_code, result = "delivery_unconfirmed" if attempted else "preflight_failed", None
    await service.execute(db().table("gbp_posts").update({"status": status, "error_code": error_code,
        "provider_result": result, "updated_at": service.now()}).eq("id", post["id"]).eq("status", "publishing"))
    return {"status": status}


async def run(settings: Settings):
    service.ready(settings)
    if not settings.google_worker_enabled:
        raise HTTPException(503, "Google worker is paused.")
    # Stale writes become uncertain, never eligible for blind replay.
    for table in ("gbp_review_jobs", "gbp_posts"):
        await service.execute(db().table(table).update({"status": "uncertain", "error_code": "worker_interrupted"})
                              .eq("status", "publishing").lt("lease_until", service.now()))
    await service.execute(db().table("gbp_review_jobs").update({"status": "pending"})
                          .eq("status", "generating").lt("lease_until", service.now()))
    await process_events(settings)
    result = await poll_reviews(settings)
    pending = await service.execute(db().table("gbp_review_jobs").select("*").eq("status", "pending")
                                    .lte("not_before", service.now()).limit(10))
    for job in pending:
        await prepare_reply(settings, job)
    ready = await service.execute(db().table("gbp_review_jobs").select("*").eq("status", "ready")
                                  .lte("not_before", service.now()).limit(10))
    result["replies"] = [await deliver_reply(settings, job) for job in ready]
    posts = await service.execute(db().table("gbp_posts").select("*").eq("status", "scheduled")
                                  .lte("scheduled_for", service.now()).limit(10))
    result["posts"] = [await deliver_post(settings, post) for post in posts]
    return result


async def worker_loop(settings: Settings):
    import logging
    logger = logging.getLogger(__name__)
    while True:
        try:
            await run(settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Google processing failed; inspect Google setup and delivery history")
        await asyncio.sleep(60)
