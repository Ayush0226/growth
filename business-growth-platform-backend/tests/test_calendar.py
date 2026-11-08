from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routes import calendar
from app.security import CurrentUser, current_user


def test_calendar_bounds_use_local_midnights_and_dst():
    since, until, _ = calendar.bounds(date(2026, 11, 1), date(2026, 11, 2), "America/New_York")
    assert (
        datetime.fromisoformat(until) - datetime.fromisoformat(since)
    ).total_seconds() == 25 * 3600
    since, until, _ = calendar.bounds(date(2026, 11, 8), date(2026, 11, 9), "Asia/Kolkata")
    assert since.startswith("2026-11-07T18:30") and until.startswith("2026-11-08T18:30")


@pytest.mark.parametrize(
    "start,end,zone",
    [
        (date(2026, 1, 1), date(2026, 1, 1), "UTC"),
        (date(2026, 1, 1), date(2026, 3, 1), "UTC"),
        (date(2026, 1, 1), date(2026, 1, 2), "invalid"),
    ],
)
def test_invalid_calendar_ranges(start, end, zone):
    with pytest.raises(HTTPException) as error:
        calendar.bounds(start, end, zone)
    assert error.value.status_code == 422


def test_day_route_derives_workspace_and_pages_without_leaking_other_fields(monkeypatch):
    app = FastAPI()
    app.include_router(calendar.router)
    app.dependency_overrides[current_user] = lambda: CurrentUser("user", None)
    monkeypatch.setattr(calendar, "user_workspace", lambda user: "owned-" + user)
    calls = []

    def rows(*args):
        calls.append(args)
        return [{"id": str(i), "status": "generated"} for i in range(51)]

    monkeypatch.setattr(calendar, "rows", rows)
    with TestClient(app) as client:
        result = client.get(
            "/api/calendar/day?on=2026-11-08&kind=ai&timezone=Asia/Kolkata&offset=50"
        )
        assert result.status_code == 200
        assert len(result.json()["items"]) == 50
        assert result.json()["has_more"] and result.json()["next_offset"] == 100
        assert calls[0][0] == "owned-user"
        assert calls[0][4] == "id,status,purpose,created_at"
        assert calls[0][-2:] == (50, 51)
        assert client.get("/api/calendar/day?on=9999-12-31&kind=ai").status_code == 422
        assert client.get("/api/calendar/day?on=2026-11-08&kind=secrets").status_code == 422


def test_rows_always_scope_workspace_and_half_open_date_range(monkeypatch):
    calls = []

    class Query:
        def __getattr__(self, name):
            def invoke(*args):
                calls.append((name, args))
                return SimpleNamespace(data=[]) if name == "execute" else self

            return invoke

    monkeypatch.setattr(calendar, "db", lambda: Query())
    calendar.rows("owned", "automation", "since", "until", "id,received_at", 0, 500)
    assert ("eq", ("workspace_id", "owned")) in calls
    assert ("gte", ("received_at", "since")) in calls
    assert ("lt", ("received_at", "until")) in calls
    assert ("range", (0, 499)) in calls


def test_summary_groups_by_business_timezone_and_returns_empty_days(monkeypatch):
    def rows(workspace, kind, *args):
        assert workspace == "owned"
        if kind == "ai":
            return [{"id": "a", "created_at": "2026-11-07T19:00:00Z"}]
        return []

    monkeypatch.setattr(calendar, "rows", rows)
    start, end, zone = calendar.bounds(date(2026, 11, 8), date(2026, 11, 10), "Asia/Kolkata")
    result = calendar.summarize("owned", start, end, zone, date(2026, 11, 8), date(2026, 11, 10))
    assert result["days"]["2026-11-08"]["ai"] == 1
    assert result["days"]["2026-11-09"]["ai"] == 0
    assert result["truncated_categories"] == []
