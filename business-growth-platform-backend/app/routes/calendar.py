"""Workspace activity grouped by the business's selected local calendar dates."""

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import db
from app.read_cache import cached
from app.routes.instagram import user_workspace
from app.security import CurrentUser, current_user

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
Kind = Literal["posts", "published", "automation", "deliveries", "ai"]
POST_FIELDS = "id,status,scheduled_for,published_at,provider_permalink,failure_message,content_targets!inner(timezone,content_drafts!inner(caption,post_type))"
SOURCES = {
    "posts": ("publishing_jobs", "scheduled_for"),
    "published": ("publishing_jobs", "published_at"),
    "automation": ("automation_events", "received_at"),
    "deliveries": ("automation_deliveries", "created_at"),
    "ai": ("chatbot_runs", "created_at"),
}
DETAIL_FIELDS = {
    "posts": POST_FIELDS,
    "published": POST_FIELDS,
    "automation": "id,kind,status,detail,received_at,processed_at",
    "deliveries": "id,status,reply_text,detail,created_at,rule_id",
    "ai": "id,status,purpose,created_at",
}


def bounds(start: date, end: date, timezone: str):
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Choose a valid timezone") from None
    if not 1 <= (end - start).days <= 42:
        raise HTTPException(422, "Choose a calendar range of 1 to 42 days")
    try:
        return (
            datetime.combine(start, time.min, zone).astimezone(UTC).isoformat(),
            datetime.combine(end, time.min, zone).astimezone(UTC).isoformat(),
            zone,
        )
    except (OverflowError, ValueError):
        raise HTTPException(422, "Choose a supported date range") from None


def rows(workspace, kind, start, end, fields, offset, limit):
    table, timestamp = SOURCES[kind]
    return (
        db()
        .table(table)
        .select(fields)
        .eq("workspace_id", workspace)
        .gte(timestamp, start)
        .lt(timestamp, end)
        .order(timestamp)
        .order("id")
        .range(offset, offset + limit - 1)
        .execute()
        .data
    )


def summarize(workspace, start, end, zone, day_start, day_end):
    days = {}
    current = day_start
    while current < day_end:
        days[current.isoformat()] = dict.fromkeys(SOURCES, 0)
        current += timedelta(days=1)
    truncated = []
    for kind, (_table, timestamp) in SOURCES.items():
        # Explicit cap keeps a busy account from monopolizing a free API process.
        # Day details remain paginated and are not limited by this overview cap.
        for offset in range(0, 5000, 500):
            batch = rows(workspace, kind, start, end, f"id,{timestamp}", offset, 500)
            for row in batch:
                day = datetime.fromisoformat(row[timestamp]).astimezone(zone).date().isoformat()
                if day in days:
                    days[day][kind] += 1
            if len(batch) < 500:
                break
        else:
            truncated.append(kind)
    return {"days": days, "truncated_categories": truncated, "timezone": str(zone)}


@router.get("/summary")
async def summary(
    start: date,
    end: date,
    timezone: str = Query(default="UTC", max_length=80),
    refresh: bool = False,
    user: CurrentUser = Depends(current_user),
):
    since, until, zone = bounds(start, end, timezone)
    workspace = await asyncio.to_thread(user_workspace, user.id)

    async def load():
        return await asyncio.to_thread(summarize, workspace, since, until, zone, start, end)

    return await cached(
        (workspace, "calendar-summary", str(start), str(end), timezone), load, 30, refresh
    )


@router.get("/day")
async def day_activity(
    on: date,
    kind: Kind,
    timezone: str = Query(default="UTC", max_length=80),
    offset: int = Query(default=0, ge=0, le=100000),
    user: CurrentUser = Depends(current_user),
):
    if on.year >= 9999:
        raise HTTPException(422, "Choose a supported date")
    since, until, _zone = bounds(on, on + timedelta(days=1), timezone)
    workspace = await asyncio.to_thread(user_workspace, user.id)
    items = await asyncio.to_thread(
        rows, workspace, kind, since, until, DETAIL_FIELDS[kind], offset, 51
    )
    return {"items": items[:50], "has_more": len(items) > 50, "next_offset": offset + 50}
