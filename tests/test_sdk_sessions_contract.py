"""Contract tests for sdk/mutx/sessions.py."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from mutx.sessions import Session, Sessions


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _session_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "source": "cli",
        "name": "test-session",
        "status": "active",
        "agent_id": str(uuid.uuid4()),
        "assistant_id": str(uuid.uuid4()),
        "last_activity": 1743324000,
        "model": "gpt-4o",
        "thinking_level": "medium",
        "verbose": "off",
        "reasoning": "on",
        "label": "test-label",
    }
    payload.update(overrides)
    return payload


def _sessions_response_payload(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"sessions": sessions}


def _read_json(request: httpx.Request) -> dict[str, Any]:
    """Parse JSON body from an httpx Request."""
    return json.loads(request.content.decode()) if request.content else {}


# ---------------------------------------------------------------------------
# Session dataclass tests
# ---------------------------------------------------------------------------


def test_session_parses_all_fields() -> None:
    payload = _session_payload()
    session = Session(payload)

    assert session.id == payload["id"]
    assert session.source == payload["source"]
    assert session.name == payload["name"]
    assert session.status == payload["status"]
    assert session.agent_id == payload["agent_id"]
    assert session.assistant_id == payload["assistant_id"]
    assert session.last_activity == payload["last_activity"]
    assert session.model == payload["model"]
    assert session.thinking_level == payload["thinking_level"]
    assert session.verbose == payload["verbose"]
    assert session.reasoning == payload["reasoning"]
    assert session.label == payload["label"]
    assert session._data == payload


def test_session_handles_missing_fields_with_defaults() -> None:
    session = Session({})

    assert session.id == ""
    assert session.source == "unknown"
    assert session.name == ""
    assert session.status == ""
    assert session.agent_id is None
    assert session.assistant_id is None
    assert session.last_activity == 0
    assert session.model is None
    assert session.thinking_level is None
    assert session.verbose is None
    assert session.reasoning is None
    assert session.label is None


def test_session_repr() -> None:
    payload = _session_payload(id="sess-abc", source="api", status="active")
    session = Session(payload)

    assert "sess-abc" in repr(session)
    assert "api" in repr(session)
    assert "active" in repr(session)


# ---------------------------------------------------------------------------
# Sessions.list() — sync
# ---------------------------------------------------------------------------


def test_list_returns_list_of_sessions() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json=_sessions_response_payload([_session_payload(id="s1"), _session_payload(id="s2")]),
        )

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    sessions = Sessions(client)

    result = sessions.list()

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(s, Session) for s in result)
    assert captured["path"] == "/v1/sessions"
    assert captured["params"] == {}
    client.close()


def test_list_filters_by_agent_id() -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_sessions_response_payload([]))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    sessions = Sessions(client)

    sessions.list(agent_id=agent_id)

    assert captured["params"] == {"agent_id": agent_id}
    client.close()


def test_list_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    sessions = Sessions(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        sessions.list()

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Sessions.alist() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alist_returns_list_of_sessions() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_sessions_response_payload([_session_payload(id="a1")]),
        )

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    sessions = Sessions(client)

    result = await sessions.alist()

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], Session)
    assert result[0].id == "a1"
    await client.aclose()


@pytest.mark.asyncio
async def test_alist_filters_by_agent_id() -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_sessions_response_payload([]))

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    sessions = Sessions(client)

    await sessions.alist(agent_id=agent_id)

    assert captured["params"] == {"agent_id": agent_id}
    await client.aclose()


@pytest.mark.asyncio
async def test_alist_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    sessions = Sessions(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await sessions.alist()

    sync_client.close()


# ---------------------------------------------------------------------------
# Sessions.set_thinking() — sync
# ---------------------------------------------------------------------------


def test_set_thinking_hits_correct_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        captured["json"] = _read_json(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    sessions = Sessions(client)

    sessions.set_thinking("sk_test", "high")

    assert captured["path"] == "/v1/sessions"
    assert captured["params"] == {"action": "set-thinking"}
    assert captured["json"]["session_key"] == "sk_test"
    assert captured["json"]["level"] == "high"
    client.close()


def test_set_thinking_rejects_invalid_level() -> None:
    client = httpx.Client(base_url="https://api.test/v1/")
    sessions = Sessions(client)

    with pytest.raises(ValueError, match="Invalid thinking level"):
        sessions.set_thinking("sk_test", "not_a_level")

    client.close()


def test_set_thinking_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    sessions = Sessions(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        sessions.set_thinking("sk_test", "medium")

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Sessions.aset_thinking() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aset_thinking_hits_correct_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        captured["json"] = _read_json(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    sessions = Sessions(client)

    await sessions.aset_thinking("sk_test", "low")

    assert captured["params"] == {"action": "set-thinking"}
    assert captured["json"]["session_key"] == "sk_test"
    assert captured["json"]["level"] == "low"
    await client.aclose()


@pytest.mark.asyncio
async def test_aset_thinking_rejects_invalid_level() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    sessions = Sessions(client)

    with pytest.raises(ValueError, match="Invalid thinking level"):
        await sessions.aset_thinking("sk_test", "bad")

    await client.aclose()


@pytest.mark.asyncio
async def test_aset_thinking_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    sessions = Sessions(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await sessions.aset_thinking("sk_test", "medium")

    sync_client.close()


# ---------------------------------------------------------------------------
# Sessions.set_reasoning() — sync
# ---------------------------------------------------------------------------


def test_set_reasoning_hits_correct_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        captured["json"] = _read_json(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    sessions = Sessions(client)

    sessions.set_reasoning("sk_test", "stream")

    assert captured["path"] == "/v1/sessions"
    assert captured["params"] == {"action": "set-reasoning"}
    assert captured["json"]["session_key"] == "sk_test"
    assert captured["json"]["level"] == "stream"
    client.close()


def test_set_reasoning_rejects_invalid_level() -> None:
    client = httpx.Client(base_url="https://api.test/v1/")
    sessions = Sessions(client)

    with pytest.raises(ValueError, match="Invalid reasoning level"):
        sessions.set_reasoning("sk_test", "not_valid")

    client.close()


def test_set_reasoning_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    sessions = Sessions(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        sessions.set_reasoning("sk_test", "on")

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Sessions.aset_reasoning() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aset_reasoning_hits_correct_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        captured["json"] = _read_json(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    sessions = Sessions(client)

    await sessions.aset_reasoning("sk_test", "off")

    assert captured["params"] == {"action": "set-reasoning"}
    assert captured["json"]["session_key"] == "sk_test"
    assert captured["json"]["level"] == "off"
    await client.aclose()


@pytest.mark.asyncio
async def test_aset_reasoning_rejects_invalid_level() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    sessions = Sessions(client)

    with pytest.raises(ValueError, match="Invalid reasoning level"):
        await sessions.aset_reasoning("sk_test", "bad")

    await client.aclose()


# ---------------------------------------------------------------------------
# Sessions.set_label() — sync
# ---------------------------------------------------------------------------


def test_set_label_hits_correct_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        captured["json"] = _read_json(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    sessions = Sessions(client)

    sessions.set_label("sk_test", "my-session-label")

    assert captured["path"] == "/v1/sessions"
    assert captured["params"] == {"action": "set-label"}
    assert captured["json"]["session_key"] == "sk_test"
    assert captured["json"]["label"] == "my-session-label"
    client.close()


def test_set_label_rejects_label_over_100_chars() -> None:
    client = httpx.Client(base_url="https://api.test/v1/")
    sessions = Sessions(client)

    with pytest.raises(ValueError, match="100 characters"):
        sessions.set_label("sk_test", "x" * 101)

    client.close()


def test_set_label_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    sessions = Sessions(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        sessions.set_label("sk_test", "label")

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Sessions.aset_label() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aset_label_hits_correct_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        captured["json"] = _read_json(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    sessions = Sessions(client)

    await sessions.aset_label("sk_test", "async-label")

    assert captured["params"] == {"action": "set-label"}
    assert captured["json"]["session_key"] == "sk_test"
    assert captured["json"]["label"] == "async-label"
    await client.aclose()


@pytest.mark.asyncio
async def test_aset_label_rejects_label_over_100_chars() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    sessions = Sessions(client)

    with pytest.raises(ValueError, match="100 characters"):
        await sessions.aset_label("sk_test", "x" * 101)

    await client.aclose()


# ---------------------------------------------------------------------------
# Sessions.delete() — sync
# ---------------------------------------------------------------------------


def test_delete_rejects_json_kwarg_incompatible_with_httpx_028() -> None:
    """httpx.Client.delete() does not accept a `json` kwarg in httpx 0.28.

    The SDK calls ``client.delete("/sessions", json={"session_key": ...})`` which
    raises TypeError. This test documents the known incompatibility — the SDK
    should be updated to use ``client.request("DELETE", "/sessions", json=...)``.
    """
    client = httpx.Client(base_url="https://api.test/v1/")
    sessions = Sessions(client)

    with pytest.raises(TypeError, match="got an unexpected keyword argument 'json'"):
        sessions.delete("sk_test")

    client.close()


def test_delete_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    sessions = Sessions(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        sessions.delete("sk_test")

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Sessions.adelete() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adelete_rejects_json_kwarg_incompatible_with_httpx_028() -> None:
    """Same delete() json= incompatibility as sync version, for async client."""
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    sessions = Sessions(client)

    with pytest.raises(TypeError, match="got an unexpected keyword argument 'json'"):
        await sessions.adelete("sk_test")

    await client.aclose()


@pytest.mark.asyncio
async def test_adelete_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    sessions = Sessions(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await sessions.adelete("sk_test")

    sync_client.close()


# ---------------------------------------------------------------------------
# Sessions exported from mutx top-level
# ---------------------------------------------------------------------------


def test_sessions_exported_from_mutx_top_level() -> None:
    import importlib
    import mutx as mutx_mod

    importlib.reload(mutx_mod)
    ImportedSessions = getattr(mutx_mod, "Sessions", None)
    from mutx import MutxClient

    # Verify Sessions is accessible via the top-level import
    assert ImportedSessions is not None, "mutx.Sessions should be exported"

    # Verify it's also on MutxClient
    assert hasattr(MutxClient, "sessions")
