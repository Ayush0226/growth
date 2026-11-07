"""Small, account-scoped cache for read-only Instagram responses."""

import asyncio
import copy
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

_values: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
_pending: dict[tuple, asyncio.Task] = {}
_versions: dict[str, int] = {}


def invalidate(workspace_id: str):
    _versions[workspace_id] = _versions.get(workspace_id, 0) + 1
    for key in list(_values):
        if key[0] == workspace_id:
            _values.pop(key, None)


async def cached(key: tuple, loader: Callable[[], Awaitable[dict]], ttl: int, refresh=False):
    key = (*key, _versions.get(key[0], 0))
    value = _values.get(key)
    if not refresh and value and value[0] > time.monotonic():
        _values.move_to_end(key)
        return copy.deepcopy(value[1])
    task = _pending.get(key)
    if not task:
        task = asyncio.create_task(loader())
        _pending[key] = task
    try:
        result = await asyncio.shield(task)
        _values[key] = (time.monotonic() + ttl, copy.deepcopy(result))
        _values.move_to_end(key)
        while len(_values) > 128:
            _values.popitem(last=False)
        return copy.deepcopy(result)
    finally:
        if task.done() and _pending.get(key) is task:
            _pending.pop(key, None)


def page(result: dict) -> dict:
    """Never forward provider pagination URLs containing an access token."""

    def clean(value):
        if isinstance(value, list):
            return [clean(item) for item in value]
        if not isinstance(value, dict):
            return value
        output = {key: clean(item) for key, item in value.items() if key != "paging"}
        if "paging" in value:
            paging = value.get("paging") or {}
            output["paging"] = {
                "cursors": paging.get("cursors") or {},
                "has_more": bool(paging.get("next")),
            }
        return output

    result = clean(result)
    return result
