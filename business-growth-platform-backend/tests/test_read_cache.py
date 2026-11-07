import asyncio

import pytest

from app.read_cache import cached, invalidate, page


@pytest.mark.asyncio
async def test_cache_deduplicates_and_isolates_workspaces():
    calls = []

    async def load():
        calls.append(True)
        await asyncio.sleep(0)
        return {"data": [{"id": "one"}]}

    key = ("cache-test-one", "connection", "media")
    first, second = await asyncio.gather(cached(key, load, 10), cached(key, load, 10))
    assert len(calls) == 1
    first["data"].clear()
    assert second["data"]
    assert (await cached(key, load, 10))["data"]
    await cached(("cache-test-two", "connection", "media"), load, 10)
    assert len(calls) == 2
    invalidate(key[0])
    await cached(key, load, 10)
    assert len(calls) == 3
    await cached(key, load, 10, refresh=True)
    assert len(calls) == 4


def test_provider_paging_tokens_are_removed_recursively():
    output = page(
        {
            "data": [
                {
                    "replies": {
                        "data": [],
                        "paging": {
                            "next": "https://provider?access_token=secret",
                            "cursors": {"after": "cursor"},
                        },
                    }
                }
            ],
            "paging": {"next": "secret", "previous": "secret", "cursors": {"after": "cursor"}},
        }
    )
    assert "secret" not in str(output)
    assert output["paging"] == {"has_more": True, "cursors": {"after": "cursor"}}
    assert output["data"][0]["replies"]["paging"]["has_more"]
