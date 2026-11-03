import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.automations import process_event
from app.config import Settings
from app.database import db
from app.publishing import publish_job

logger = logging.getLogger(__name__)


async def run_pending(settings: Settings) -> dict:
    holder = str(uuid.uuid4())
    acquired = await asyncio.to_thread(
        lambda: db().rpc("acquire_growthboard_lease", {"lease_holder": holder}).execute().data
    )
    if acquired is not True:
        return {"status": "busy", "published": 0, "events": 0}
    result = {"status": "completed", "published": 0, "events": 0, "failures": 0}
    try:
        jobs = await asyncio.to_thread(
            lambda: (
                db()
                .table("publishing_jobs")
                .select("id,workspace_id,scheduled_for")
                .eq("status", "scheduled")
                .lte("scheduled_for", datetime.now(UTC).isoformat())
                .order("scheduled_for")
                .limit(3)
                .execute()
                .data
            )
        )
        for job in jobs:
            if datetime.fromisoformat(job["scheduled_for"]) < datetime.now(UTC) - timedelta(days=1):
                await asyncio.to_thread(
                    lambda job=job: (
                        db()
                        .table("publishing_jobs")
                        .update(
                            {
                                "status": "failed",
                                "failure_code": "schedule_missed",
                                "failure_message": "This schedule was missed by more than 24 hours. Review the post, then reschedule or retry manually.",
                                "retryable": False,
                            }
                        )
                        .eq("id", job["id"])
                        .eq("status", "scheduled")
                        .execute()
                    )
                )
                result["failures"] += 1
                continue
            try:
                await publish_job(job["id"], job["workspace_id"], settings)
                result["published"] += 1
            except Exception:  # noqa: BLE001 - persist per-job failures without stopping the batch
                result["failures"] += 1
                logger.warning("Scheduled publication failed for job %s", job["id"])
        events = await asyncio.to_thread(
            lambda: (
                db()
                .table("automation_events")
                .select("*")
                .eq("status", "pending")
                .order("received_at")
                .limit(10)
                .execute()
                .data
            )
        )
        for event in events:
            try:
                await asyncio.to_thread(
                    lambda event=event: asyncio.run(process_event(event, settings))
                )
                result["events"] += 1
            except Exception:  # noqa: BLE001 - do not replay interrupted public sends
                # A persisted delivery may already exist. Never retry blindly.
                await asyncio.to_thread(
                    lambda event=event: (
                        db()
                        .table("automation_events")
                        .update(
                            {
                                "status": "failed",
                                "detail": "Processing interrupted; inspect delivery activity before retrying",
                            }
                        )
                        .eq("id", event["id"])
                        .execute()
                    )
                )
                result["failures"] += 1
                logger.warning("Automation processing failed for event %s", event["id"])
        await asyncio.to_thread(
            lambda: (
                db()
                .table("scheduler_configuration")
                .update({"last_finished_at": datetime.now(UTC).isoformat(), "last_result": result})
                .eq("name", "mvp")
                .execute()
            )
        )
        return result
    finally:
        await asyncio.to_thread(
            lambda: (
                db()
                .table("scheduler_leases")
                .delete()
                .eq("name", "mvp")
                .eq("holder", holder)
                .execute()
            )
        )


async def worker_loop(settings: Settings):
    while True:
        try:
            await run_pending(settings)
        except Exception:  # noqa: BLE001 - worker survives transient database/network failures
            logger.warning(
                "Background worker unavailable; check migrations and database configuration"
            )
        await asyncio.sleep(settings.scheduler_interval_seconds)
