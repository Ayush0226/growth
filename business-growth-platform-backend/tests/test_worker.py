from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from test_automations import Store

from app import worker


@pytest.mark.asyncio
async def test_resuming_does_not_publish_old_scheduled_content(monkeypatch):
    now = datetime.now(UTC)
    old = {
        "id": "old",
        "workspace_id": "workspace",
        "status": "scheduled",
        "scheduled_for": (now - timedelta(days=20)).isoformat(),
    }
    fresh = {
        "id": "fresh",
        "workspace_id": "workspace",
        "status": "scheduled",
        "scheduled_for": (now - timedelta(minutes=2)).isoformat(),
    }
    store = Store({"publishing_jobs": [old, fresh], "scheduler_configuration": [{"name": "mvp"}]})
    store.rpc = lambda *a, **kw: SimpleNamespace(execute=lambda: SimpleNamespace(data=True))
    monkeypatch.setattr(worker, "db", lambda: store)
    published = []

    async def publish(job_id, workspace, settings):
        published.append(job_id)
        return {"status": "published"}

    monkeypatch.setattr(worker, "publish_job", publish)
    result = await worker.run_pending(SimpleNamespace())
    assert published == ["fresh"]
    assert old["status"] == "failed"
    assert old["failure_code"] == "schedule_missed"
    assert result["published"] == 1
    assert result["failures"] == 1
    assert store.data["scheduler_configuration"][0]["last_finished_at"]


@pytest.mark.asyncio
async def test_overlapping_worker_does_not_process_any_queue(monkeypatch):
    store = Store({})
    store.rpc = lambda *a, **kw: SimpleNamespace(execute=lambda: SimpleNamespace(data=False))
    monkeypatch.setattr(worker, "db", lambda: store)
    result = await worker.run_pending(SimpleNamespace())
    assert result["status"] == "busy"
    assert store.data == {}
