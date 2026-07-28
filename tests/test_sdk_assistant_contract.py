"""Contract tests for sdk/mutx/assistant.py."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from mutx.assistant import (
    Assistant,
    AssistantChannel,
    AssistantHealth,
    AssistantOverview,
    AssistantSession,
    AssistantSkill,
    AssistantWakeup,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _skill_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "name": "test-skill",
        "description": "A test skill",
        "version": "1.0.0",
        "installed": False,
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def _channel_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "name": "test-channel",
        "type": "discord",
        "status": "active",
        "config": {},
    }
    payload.update(overrides)
    return payload


def _wakeup_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "phrase": "hey assistant",
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def _health_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "status": "ok",
        "version": "1.2.3",
        "uptime_seconds": 3600.0,
        "gateway_url": "https://gateway.example.com",
        "last_check": "2026-04-03T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def _session_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "session_id": str(uuid.uuid4()),
        "assistant_id": str(uuid.uuid4()),
        "status": "active",
        "model": "gpt-4o",
        "created_at": "2026-04-03T09:00:00Z",
        "last_activity": "2026-04-03T09:30:00Z",
    }
    payload.update(overrides)
    return payload


def _overview_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "has_assistant": True,
        "recommended_template_id": None,
        "assistant": {"id": str(uuid.uuid4()), "name": "my-assistant"},
    }
    payload.update(overrides)
    return payload


def _read_json(request: httpx.Request) -> dict[str, Any]:
    """Parse JSON body from an httpx Request."""
    return json.loads(request.content.decode()) if request.content else {}


# ---------------------------------------------------------------------------
# Dataclass tests — AssistantSkill
# ---------------------------------------------------------------------------


def test_assistant_skill_parses_all_fields() -> None:
    payload = _skill_payload()
    skill = AssistantSkill(payload)

    assert skill.id == payload["id"]
    assert skill.name == payload["name"]
    assert skill.description == payload["description"]
    assert skill.version == payload["version"]
    assert skill.installed == payload["installed"]
    assert skill.enabled == payload["enabled"]
    assert skill._data == payload


def test_assistant_skill_handles_missing_fields_with_defaults() -> None:
    # id is required; other fields fall back to defaults
    skill = AssistantSkill({"id": ""})

    assert skill.id == ""
    assert skill.name == ""
    assert skill.description == ""
    assert skill.version == ""
    assert skill.installed is False
    assert skill.enabled is True


def test_assistant_skill_repr() -> None:
    skill = AssistantSkill(_skill_payload(id="sk-abc", installed=True))
    assert "sk-abc" in repr(skill)
    assert "True" in repr(skill)


# ---------------------------------------------------------------------------
# Dataclass tests — AssistantChannel
# ---------------------------------------------------------------------------


def test_assistant_channel_parses_all_fields() -> None:
    config = {"token": "abc123"}
    payload = _channel_payload(config=config)
    channel = AssistantChannel(payload)

    assert channel.id == payload["id"]
    assert channel.name == payload["name"]
    assert channel.type == payload["type"]
    assert channel.status == payload["status"]
    assert channel.config == config
    assert channel._data == payload


def test_assistant_channel_handles_missing_fields_with_defaults() -> None:
    # id is required; other fields fall back to defaults
    channel = AssistantChannel({"id": ""})

    assert channel.id == ""
    assert channel.name == ""
    assert channel.type == ""
    assert channel.status == ""
    assert channel.config == {}


# ---------------------------------------------------------------------------
# Dataclass tests — AssistantWakeup
# ---------------------------------------------------------------------------


def test_assistant_wakeup_parses_all_fields() -> None:
    payload = _wakeup_payload()
    wakeup = AssistantWakeup(payload)

    assert wakeup.id == payload["id"]
    assert wakeup.phrase == payload["phrase"]
    assert wakeup.enabled == payload["enabled"]
    assert wakeup._data == payload


def test_assistant_wakeup_handles_missing_fields_with_defaults() -> None:
    # id is required; other fields fall back to defaults
    wakeup = AssistantWakeup({"id": ""})

    assert wakeup.id == ""
    assert wakeup.phrase == ""
    assert wakeup.enabled is True


# ---------------------------------------------------------------------------
# Dataclass tests — AssistantHealth
# ---------------------------------------------------------------------------


def test_assistant_health_parses_all_fields() -> None:
    payload = _health_payload()
    health = AssistantHealth(payload)

    assert health.status == payload["status"]
    assert health.version == payload["version"]
    assert health.uptime_seconds == payload["uptime_seconds"]
    assert health.gateway_url == payload["gateway_url"]
    assert health.last_check == payload["last_check"]
    assert health._data == payload


def test_assistant_health_handles_missing_fields_with_defaults() -> None:
    health = AssistantHealth({})

    assert health.status == "unknown"
    assert health.version is None
    assert health.uptime_seconds is None
    assert health.gateway_url is None
    assert health.last_check is None


# ---------------------------------------------------------------------------
# Dataclass tests — AssistantSession
# ---------------------------------------------------------------------------


def test_assistant_session_parses_all_fields() -> None:
    payload = _session_payload()
    session = AssistantSession(payload)

    assert session.session_id == payload["session_id"]
    assert session.assistant_id == payload["assistant_id"]
    assert session.status == payload["status"]
    assert session.model == payload["model"]
    assert session.created_at == payload["created_at"]
    assert session.last_activity == payload["last_activity"]
    assert session._data == payload


def test_assistant_session_handles_missing_fields_with_defaults() -> None:
    session = AssistantSession({})

    assert session.session_id == ""
    assert session.assistant_id == ""
    assert session.status == ""
    assert session.model is None
    assert session.created_at is None
    assert session.last_activity is None


# ---------------------------------------------------------------------------
# Dataclass tests — AssistantOverview
# ---------------------------------------------------------------------------


def test_assistant_overview_parses_all_fields() -> None:
    assistant_data = {"id": "ast-123", "name": "test"}
    payload = _overview_payload(assistant=assistant_data)
    overview = AssistantOverview(payload)

    assert overview.has_assistant is True
    assert overview.recommended_template_id is None
    assert overview.assistant == assistant_data
    assert overview._data == payload


def test_assistant_overview_handles_missing_fields_with_defaults() -> None:
    overview = AssistantOverview({})

    assert overview.has_assistant is False
    assert overview.recommended_template_id is None
    assert overview.assistant is None


# ---------------------------------------------------------------------------
# Assistant.overview() — sync
# ---------------------------------------------------------------------------


def test_overview_returns_assistant_overview() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_overview_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    assistant = Assistant(client)

    result = assistant.overview()

    assert isinstance(result, AssistantOverview)
    assert captured["path"] == "/v1/assistant/overview"
    assert captured["params"] == {}
    client.close()


def test_overview_passes_agent_id_param() -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_overview_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    assistant = Assistant(client)

    assistant.overview(agent_id=agent_id)

    assert captured["params"] == {"agent_id": agent_id}
    client.close()


def test_overview_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    assistant = Assistant(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        assistant.overview()

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Assistant.aoverview() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aoverview_returns_assistant_overview() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_overview_payload(has_assistant=True))

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    assistant = Assistant(client)

    result = await assistant.aoverview()

    assert isinstance(result, AssistantOverview)
    assert result.has_assistant is True
    await client.aclose()


@pytest.mark.asyncio
async def test_aoverview_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    assistant = Assistant(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await assistant.aoverview()

    sync_client.close()


# ---------------------------------------------------------------------------
# Assistant.skills() — sync
# ---------------------------------------------------------------------------


def test_skills_returns_list_of_assistant_skills() -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=[_skill_payload(id="sk1"), _skill_payload(id="sk2")])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    assistant = Assistant(client)

    result = assistant.skills(agent_id)

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(s, AssistantSkill) for s in result)
    assert captured["path"] == f"/v1/assistant/{agent_id}/skills"
    client.close()


def test_skills_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    assistant = Assistant(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        assistant.skills(str(uuid.uuid4()))

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Assistant.askills() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_askills_returns_list_of_assistant_skills() -> None:
    agent_id = str(uuid.uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_skill_payload(id="ask1")])

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    assistant = Assistant(client)

    result = await assistant.askills(agent_id)

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], AssistantSkill)
    await client.aclose()


@pytest.mark.asyncio
async def test_askills_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    assistant = Assistant(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await assistant.askills(str(uuid.uuid4()))

    sync_client.close()


# ---------------------------------------------------------------------------
# Assistant.install_skill() — sync
# ---------------------------------------------------------------------------


def test_install_skill_returns_updated_skills_list() -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())
    skill_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=[_skill_payload(id=skill_id, installed=True)])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    assistant = Assistant(client)

    result = assistant.install_skill(agent_id, skill_id)

    assert isinstance(result, list)
    assert all(isinstance(s, AssistantSkill) for s in result)
    assert captured["path"] == f"/v1/assistant/{agent_id}/skills/{skill_id}"
    assert captured["method"] == "POST"
    client.close()


def test_install_skill_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    assistant = Assistant(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        assistant.install_skill(str(uuid.uuid4()), str(uuid.uuid4()))

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Assistant.ainstall_skill() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ainstall_skill_returns_updated_skills_list() -> None:
    agent_id = str(uuid.uuid4())
    skill_id = str(uuid.uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_skill_payload(id=skill_id, installed=True)])

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    assistant = Assistant(client)

    result = await assistant.ainstall_skill(agent_id, skill_id)

    assert isinstance(result, list)
    assert isinstance(result[0], AssistantSkill)
    await client.aclose()


@pytest.mark.asyncio
async def test_ainstall_skill_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    assistant = Assistant(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await assistant.ainstall_skill(str(uuid.uuid4()), str(uuid.uuid4()))

    sync_client.close()


# ---------------------------------------------------------------------------
# Assistant.uninstall_skill() — sync
# ---------------------------------------------------------------------------


def test_uninstall_skill_returns_updated_skills_list() -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())
    skill_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=[])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    assistant = Assistant(client)

    result = assistant.uninstall_skill(agent_id, skill_id)

    assert isinstance(result, list)
    assert captured["path"] == f"/v1/assistant/{agent_id}/skills/{skill_id}"
    assert captured["method"] == "DELETE"
    client.close()


def test_uninstall_skill_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    assistant = Assistant(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        assistant.uninstall_skill(str(uuid.uuid4()), str(uuid.uuid4()))

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Assistant.auninstall_skill() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auninstall_skill_returns_updated_skills_list() -> None:
    agent_id = str(uuid.uuid4())
    skill_id = str(uuid.uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    assistant = Assistant(client)

    result = await assistant.auninstall_skill(agent_id, skill_id)

    assert isinstance(result, list)
    await client.aclose()


@pytest.mark.asyncio
async def test_auninstall_skill_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    assistant = Assistant(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await assistant.auninstall_skill(str(uuid.uuid4()), str(uuid.uuid4()))

    sync_client.close()


# ---------------------------------------------------------------------------
# Assistant.channels() — sync
# ---------------------------------------------------------------------------


def test_channels_returns_list_of_assistant_channels() -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=[_channel_payload(id="ch1"), _channel_payload(id="ch2")])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    assistant = Assistant(client)

    result = assistant.channels(agent_id)

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(c, AssistantChannel) for c in result)
    assert captured["path"] == f"/v1/assistant/{agent_id}/channels"
    client.close()


def test_channels_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    assistant = Assistant(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        assistant.channels(str(uuid.uuid4()))

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Assistant.achannels() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_achannels_returns_list_of_assistant_channels() -> None:
    agent_id = str(uuid.uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_channel_payload(id="ach1")])

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    assistant = Assistant(client)

    result = await assistant.achannels(agent_id)

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], AssistantChannel)
    await client.aclose()


@pytest.mark.asyncio
async def test_achannels_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    assistant = Assistant(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await assistant.achannels(str(uuid.uuid4()))

    sync_client.close()


# ---------------------------------------------------------------------------
# Assistant.wakeups() — sync
# ---------------------------------------------------------------------------


def test_wakeups_returns_list_of_assistant_wakeups() -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=[_wakeup_payload(id="wk1"), _wakeup_payload(id="wk2")])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    assistant = Assistant(client)

    result = assistant.wakeups(agent_id)

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(w, AssistantWakeup) for w in result)
    assert captured["path"] == f"/v1/assistant/{agent_id}/wakeups"
    client.close()


def test_wakeups_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    assistant = Assistant(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        assistant.wakeups(str(uuid.uuid4()))

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Assistant.awakeups() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_awakeups_returns_list_of_assistant_wakeups() -> None:
    agent_id = str(uuid.uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_wakeup_payload(id="awk1")])

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    assistant = Assistant(client)

    result = await assistant.awakeups(agent_id)

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], AssistantWakeup)
    await client.aclose()


@pytest.mark.asyncio
async def test_awakeups_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    assistant = Assistant(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await assistant.awakeups(str(uuid.uuid4()))

    sync_client.close()


# ---------------------------------------------------------------------------
# Assistant.health() — sync
# ---------------------------------------------------------------------------


def test_health_returns_assistant_health() -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_health_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    assistant = Assistant(client)

    result = assistant.health(agent_id)

    assert isinstance(result, AssistantHealth)
    assert result.status == "ok"
    assert result.version == "1.2.3"
    assert captured["path"] == f"/v1/assistant/{agent_id}/health"
    client.close()


def test_health_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    assistant = Assistant(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        assistant.health(str(uuid.uuid4()))

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Assistant.ahealth() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ahealth_returns_assistant_health() -> None:
    agent_id = str(uuid.uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_health_payload(status="degraded"))

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    assistant = Assistant(client)

    result = await assistant.ahealth(agent_id)

    assert isinstance(result, AssistantHealth)
    assert result.status == "degraded"
    await client.aclose()


@pytest.mark.asyncio
async def test_ahealth_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    assistant = Assistant(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await assistant.ahealth(str(uuid.uuid4()))

    sync_client.close()


# ---------------------------------------------------------------------------
# Assistant.sessions() — sync
# ---------------------------------------------------------------------------


def test_sessions_returns_list_of_assistant_sessions() -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json=[_session_payload(id="s1"), _session_payload(id="s2")],
        )

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    assistant = Assistant(client)

    result = assistant.sessions(agent_id)

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(s, AssistantSession) for s in result)
    assert captured["path"] == f"/v1/assistant/{agent_id}/sessions"
    client.close()


def test_sessions_requires_sync_client() -> None:
    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    assistant = Assistant(async_client)

    with pytest.raises(RuntimeError, match="sync"):
        assistant.sessions(str(uuid.uuid4()))

    import asyncio

    asyncio.run(async_client.aclose())


# ---------------------------------------------------------------------------
# Assistant.asessions() — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asessions_returns_list_of_assistant_sessions() -> None:
    agent_id = str(uuid.uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_session_payload(id="as1")])

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    )
    assistant = Assistant(client)

    result = await assistant.asessions(agent_id)

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], AssistantSession)
    await client.aclose()


@pytest.mark.asyncio
async def test_asessions_requires_async_client() -> None:
    sync_client = httpx.Client(base_url="https://api.test/v1/")
    assistant = Assistant(sync_client)

    with pytest.raises(RuntimeError, match="async"):
        await assistant.asessions(str(uuid.uuid4()))

    sync_client.close()
