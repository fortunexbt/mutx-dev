"""Contract tests for sdk/mutx/usage.py — no API keys needed."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
import pytest

from mutx.usage import UsageEvents, UsageEvent


def _event_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "event_type": "api_call",
        "resource_type": "agent",
        "resource_id": str(uuid.uuid4()),
        "credits_used": 1.5,
        "metadata": {"model": "gpt-4o"},
        "created_at": "2026-03-12T09:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def _events_page_payload(items: list[dict[str, Any]], total: int) -> dict[str, Any]:
    return {"items": items, "total": total}


# -----------------------------------------------------------------
# UsageEvent dataclass
# -----------------------------------------------------------------


def test_usage_event_parses_required_fields() -> None:
    raw = _event_payload(event_type="api_call", credits_used=2.0)
    event = UsageEvent(raw)

    assert event.id == UUID(raw["id"])
    assert event.event_type == "api_call"
    assert event.credits_used == 2.0
    assert event.created_at == datetime.fromisoformat(raw["created_at"])


def test_usage_event_handles_optional_fields() -> None:
    raw = _event_payload(resource_type=None, resource_id=None, metadata={})
    event = UsageEvent(raw)

    assert event.resource_type is None
    assert event.resource_id is None
    assert event.metadata == {}


def test_usage_event_repr() -> None:
    raw = _event_payload()
    event = UsageEvent(raw)
    assert "UsageEvent" in repr(event)
    assert raw["event_type"] in repr(event)


def test_usage_event_defaults() -> None:
    raw = {
        "id": str(uuid.uuid4()),
        "event_type": "starter_deployment_create",
        "created_at": "2026-03-12T09:00:00+00:00",
    }
    event = UsageEvent(raw)
    assert event.credits_used == 0.0
    assert event.metadata == {}


# -----------------------------------------------------------------
# UsageEvents.create_event
# -----------------------------------------------------------------


def test_create_event_sends_correct_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_event_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    events = UsageEvents(client)

    events.create_event(
        event_type="api_call",
        resource_type="agent",
        resource_id="550e8400-e29b-41d4-a716-446655440000",
        credits_used=1.5,
        metadata={"model": "gpt-4o"},
    )

    assert captured["path"] == "/v1/usage/events"
    assert captured["json"]["event_type"] == "api_call"
    assert captured["json"]["resource_type"] == "agent"
    assert captured["json"]["resource_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert captured["json"]["credits_used"] == 1.5
    assert captured["json"]["metadata"]["model"] == "gpt-4o"


def test_create_event_returns_usage_event() -> None:
    raw = _event_payload(event_type="api_call")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=raw)

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    events = UsageEvents(client)

    result = events.create_event(event_type="api_call")

    assert isinstance(result, UsageEvent)
    assert result.event_type == "api_call"


# -----------------------------------------------------------------
# UsageEvents.acreate_event
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_acreate_event_sends_correct_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_event_payload())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        events = UsageEvents(client)
        await events.acreate_event(
            event_type="starter_deployment_create",
            credits_used=0.5,
        )

    assert captured["path"] == "/v1/usage/events"
    assert captured["json"]["event_type"] == "starter_deployment_create"
    assert captured["json"]["credits_used"] == 0.5


@pytest.mark.asyncio
async def test_acreate_event_returns_usage_event() -> None:
    raw = _event_payload(event_type="api_call")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=raw)

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        events = UsageEvents(client)
        result = await events.acreate_event(event_type="api_call")

    assert isinstance(result, UsageEvent)
    assert result.event_type == "api_call"


# -----------------------------------------------------------------
# UsageEvents.list
# -----------------------------------------------------------------


def test_list_returns_tuple_of_events_and_total() -> None:
    items = [_event_payload(), _event_payload(event_type="api_call")]
    total = 42

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_events_page_payload(items, total))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    events = UsageEvents(client)

    result, result_total = events.list(skip=10, limit=5, event_type="api_call")

    assert isinstance(result, list)
    assert all(isinstance(e, UsageEvent) for e in result)
    assert result_total == total


def test_list_passes_query_params() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_events_page_payload([], 0))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    events = UsageEvents(client)

    events.list(
        skip=20,
        limit=10,
        event_type="api_call",
        resource_id="550e8400-e29b-41d4-a716-446655440000",
    )

    assert captured["params"]["skip"] == "20"
    assert captured["params"]["limit"] == "10"
    assert captured["params"]["event_type"] == "api_call"
    assert captured["params"]["resource_id"] == "550e8400-e29b-41d4-a716-446655440000"


# -----------------------------------------------------------------
# UsageEvents.alist
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_alist_returns_tuple_of_events_and_total() -> None:
    items = [_event_payload(event_type="api_call")]
    total = 7

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_events_page_payload(items, total))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        events = UsageEvents(client)
        result, result_total = await events.alist(event_type="api_call")

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], UsageEvent)
    assert result_total == total


# -----------------------------------------------------------------
# UsageEvents.get
# -----------------------------------------------------------------


def test_get_returns_usage_event() -> None:
    raw = _event_payload(event_type="api_call")
    event_id = raw["id"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    events = UsageEvents(client)

    result = events.get(event_id)

    assert isinstance(result, UsageEvent)
    assert result.event_type == "api_call"


# -----------------------------------------------------------------
# UsageEvents.aget
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_aget_returns_usage_event() -> None:
    raw = _event_payload(event_type="starter_deployment_create")
    event_id = raw["id"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        events = UsageEvents(client)
        result = await events.aget(event_id)

    assert isinstance(result, UsageEvent)
    assert result.event_type == "starter_deployment_create"


# -----------------------------------------------------------------
# Sync client required enforcement
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rejects_async_client() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_events_page_payload([], 0))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        events = UsageEvents(client)
        with pytest.raises(RuntimeError, match="sync"):
            events.list()


@pytest.mark.asyncio
async def test_create_event_rejects_async_client() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_event_payload())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        events = UsageEvents(client)
        with pytest.raises(RuntimeError, match="sync"):
            events.create_event(event_type="api_call")


@pytest.mark.asyncio
async def test_get_rejects_async_client() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_event_payload())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        events = UsageEvents(client)
        with pytest.raises(RuntimeError, match="sync"):
            events.get("some-id")


# -----------------------------------------------------------------
# Async client required enforcement
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_alist_rejects_sync_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_events_page_payload([], 0))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    events = UsageEvents(client)
    with pytest.raises(RuntimeError, match="async"):
        await events.alist()


@pytest.mark.asyncio
async def test_acreate_event_rejects_sync_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_event_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    events = UsageEvents(client)
    with pytest.raises(RuntimeError, match="async"):
        await events.acreate_event(event_type="api_call")


@pytest.mark.asyncio
async def test_aget_rejects_sync_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_event_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    events = UsageEvents(client)
    with pytest.raises(RuntimeError, match="async"):
        await events.aget("some-id")
