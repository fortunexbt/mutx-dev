"""
SDK contract tests for scheduler module.
Tests verify that the SDK correctly maps to the /scheduler backend API contract.

Note: Scheduler is planned for v1.3. These methods currently return 503 errors
when called against a real backend, but contract tests use mock transport.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from mutx.scheduler import Scheduler, SchedulerTask


def _task_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "name": "test-task",
        "enabled": True,
        "schedule": "0 * * * *",
        "last_run": 1712000000,
        "next_run": 1712003600,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# SchedulerTask data class
# ---------------------------------------------------------------------------


def test_scheduler_task_parses_required_fields() -> None:
    task = SchedulerTask(_task_payload())

    assert task.id is not None
    assert task.name == "test-task"
    assert task.enabled is True


def test_scheduler_task_parses_optional_fields() -> None:
    task = SchedulerTask(
        _task_payload(
            schedule="0 9 * * *",
            last_run=1712000000,
            next_run=1712003600,
        )
    )

    assert task.schedule == "0 9 * * *"
    assert task.last_run == 1712000000
    assert task.next_run == 1712003600


def test_scheduler_task_repr_includes_id_and_name() -> None:
    task = SchedulerTask(_task_payload(id="task-123", name="nightly-export"))

    repr_str = repr(task)
    assert "task-123" in repr_str
    assert "nightly-export" in repr_str


def test_scheduler_task_omitted_optional_fields_default_to_none() -> None:
    task = SchedulerTask(
        {
            "id": "bare-task",
            "name": "bare",
            "enabled": False,
        }
    )

    assert task.schedule is None
    assert task.last_run is None
    assert task.next_run is None


def test_scheduler_task_raw_data_preserved() -> None:
    payload = _task_payload()
    task = SchedulerTask(payload)

    assert task._data == payload


# ---------------------------------------------------------------------------
# Scheduler — sync client enforcement
# ---------------------------------------------------------------------------


def test_scheduler_rejects_async_client_for_sync_methods() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    scheduler = Scheduler(client)

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        scheduler.get_status()

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        scheduler.trigger_task(task_id="any-id")


def test_scheduler_works_with_sync_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    scheduler = Scheduler(client)

    result = scheduler.get_status()
    assert result == {"status": "ok"}


# ---------------------------------------------------------------------------
# Scheduler — route + method verification
# ---------------------------------------------------------------------------


def test_scheduler_get_status_hits_correct_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"status": "scheduling"})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    scheduler = Scheduler(client)

    scheduler.get_status()

    assert captured["path"] == "/v1/scheduler"
    assert captured["method"] == "GET"


def test_scheduler_trigger_task_hits_bodyless_task_route() -> None:
    captured: dict[str, Any] = {}
    task_id = str(uuid.uuid4())

    def transport_handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["content"] = request.content
        captured["content_type"] = request.headers.get("content-type")
        return httpx.Response(200, json={"triggered": task_id})

    client = httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(transport_handler)
    )
    scheduler = Scheduler(client)

    scheduler.trigger_task(task_id=task_id)

    assert captured["path"] == f"/v1/scheduler/{task_id}/trigger"
    assert captured["method"] == "POST"
    assert captured["content"] == b""
    assert captured["content_type"] is None


def test_scheduler_get_status_raises_on_503() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "not implemented"})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    scheduler = Scheduler(client)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        scheduler.get_status()

    assert exc_info.value.response.status_code == 503


def test_scheduler_trigger_task_raises_on_503() -> None:
    task_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "not implemented"})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    scheduler = Scheduler(client)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        scheduler.trigger_task(task_id=task_id)

    assert exc_info.value.response.status_code == 503


# ---------------------------------------------------------------------------
# Scheduler — async methods
# ---------------------------------------------------------------------------


def test_scheduler_aget_status_rejects_sync_client() -> None:
    client = httpx.Client(base_url="https://api.test/v1/")
    scheduler = Scheduler(client)

    with pytest.raises(RuntimeError, match="async resource helper requires an async"):
        import asyncio

        asyncio.run(scheduler.aget_status())


def test_scheduler_atrigger_task_rejects_sync_client() -> None:
    client = httpx.Client(base_url="https://api.test/v1/")
    scheduler = Scheduler(client)

    with pytest.raises(RuntimeError, match="async resource helper requires an async"):
        import asyncio

        asyncio.run(scheduler.atrigger_task(task_id="any-id"))


def test_scheduler_aget_status_hits_correct_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"status": "scheduling"})

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    scheduler = Scheduler(client)

    import asyncio

    result = asyncio.run(scheduler.aget_status())

    assert captured["path"] == "/v1/scheduler"
    assert captured["method"] == "GET"
    assert result == {"status": "scheduling"}


def test_scheduler_atrigger_task_hits_bodyless_task_route() -> None:
    captured: dict[str, Any] = {}
    task_id = str(uuid.uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["content"] = request.content
        captured["content_type"] = request.headers.get("content-type")
        return httpx.Response(200, json={"triggered": task_id})

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    scheduler = Scheduler(client)

    import asyncio

    result = asyncio.run(scheduler.atrigger_task(task_id=task_id))

    assert captured["path"] == f"/v1/scheduler/{task_id}/trigger"
    assert captured["method"] == "POST"
    assert captured["content"] == b""
    assert captured["content_type"] is None
    assert result == {"triggered": task_id}
