import asyncio
import logging
import traceback
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from app.automations import process_event
from app.config import Settings
from app.database import db, one
from app.publishing import publish_job

logger = logging.getLogger(__name__)


def acquire_lease(holder: str) -> bool:
    now = datetime.now(UTC)
    values = {"holder": holder, "expires_at": (now + timedelta(minutes=2)).isoformat()}
    # Both writes are atomic. A lost response can leave only a two-minute lease.
    # The previous RPC installed a twenty-minute lease before its response arrived.
    replaced = (
        db()
        .table("scheduler_leases")
        .update(values)
        .eq("name", "mvp")
        .lt("expires_at", now.isoformat())
        .execute()
        .data
    )
    if replaced:
        return True
    return bool(
        db()
        .table("scheduler_leases")
        .upsert({"name": "mvp", **values}, on_conflict="name", ignore_duplicates=True)
        .execute()
        .data
    )


def renew_lease(holder: str) -> bool:
    return bool(
        db()
        .table("scheduler_leases")
        .update({"expires_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat()})
        .eq("name", "mvp")
        .eq("holder", holder)
        .execute()
        .data
    )


async def keep_lease(holder: str, lost: asyncio.Event):
    while True:
        await asyncio.sleep(20)
        try:
            if not await asyncio.to_thread(renew_lease, holder):
                lost.set()
                return
        except Exception:  # noqa: BLE001 - losing a lease must stop new queue claims
            # Stop claiming new work when ownership cannot be confirmed.
            lost.set()
            logger.warning("Worker lease renewal failed")
            return


def finish_interrupted(event: dict, exc: Exception):
    delivery = one(
        db()
        .table("automation_deliveries")
        .select("id,status")
        .eq("event_id", event["id"])
        .limit(1)
        .execute()
    )
    sent = delivery and delivery["status"] == "sent"
    if delivery and delivery["status"] == "sending":
        db().table("automation_deliveries").update(
            {
                "status": "uncertain",
                "detail": "Processing stopped before delivery could be confirmed. Check Instagram before sending again.",
            }
        ).eq("id", delivery["id"]).eq("status", "sending").execute()
    db().table("automation_events").update(
        {
            "status": "processed" if sent else "failed",
            "detail": "Reply sent"
            if sent
            else (
                "Processing interrupted; check reply deliveries before sending again"
                if delivery
                else "Processing was interrupted before a reply was created. Send a new message or comment to try again."
            ),
            "processed_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", event["id"]).execute()
    # Include the exception type and locations, never exception text, tokens or request URLs.
    locations = [(frame.name, frame.lineno) for frame in traceback.extract_tb(exc.__traceback__)]
    logger.warning("Event %s failed: %s at %s", event["id"], type(exc).__name__, locations)


async def run_pending(settings: Settings) -> dict:
    holder = str(uuid.uuid4())
    result = {"status": "completed", "published": 0, "events": 0, "failures": 0}
    lost = asyncio.Event()
    heartbeat = None
    try:
        if not await asyncio.to_thread(acquire_lease, holder):
            return {"status": "busy", "published": 0, "events": 0}
        if not await asyncio.to_thread(renew_lease, holder):
            return {"status": "busy", "published": 0, "events": 0}
        heartbeat = asyncio.create_task(keep_lease(holder, lost))
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
            if lost.is_set():
                result["status"] = "interrupted"
                break
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
                await asyncio.to_thread(
                    lambda job=job: asyncio.run(
                        publish_job(job["id"], job["workspace_id"], settings)
                    )
                )
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
            if lost.is_set():
                result["status"] = "interrupted"
                break
            try:
                await asyncio.to_thread(
                    lambda event=event: asyncio.run(process_event(event, settings))
                )
                result["events"] += 1
            except Exception as exc:  # noqa: BLE001 - reconcile without replaying public sends
                await asyncio.to_thread(finish_interrupted, event, exc)
                result["failures"] += 1
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
        if heartbeat:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
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
