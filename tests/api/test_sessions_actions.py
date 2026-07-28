"""Tests for /v1/sessions route — list, scoping, action forwarding, delete."""

import json
import uuid

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

import src.api.routes.sessions as sessions_mod
from src.api.services.session_ownership import filter_and_claim_owned_sessions


async def _bind_owned_session(db_session, test_user, test_agent, session_key="test-session"):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    session = {
        "id": session_key,
        "key": session_key,
        "agent_id": str(test_agent.id),
        "source": "openclaw",
    }
    await filter_and_claim_owned_sessions(
        db_session,
        user=test_user,
        sessions=[session],
    )
    return session


@pytest.mark.asyncio
async def test_list_sessions_returns_owned_merged_sources_sorted(
    client: AsyncClient,
    monkeypatch,
    test_agent,
):
    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: [
            {
                "id": "gateway-1",
                "agent_id": str(test_agent.id),
                "source": "openclaw",
                "last_activity": 30,
            },
        ],
    )
    monkeypatch.setattr(
        sessions_mod,
        "get_local_claude_sessions",
        lambda: [
            {
                "id": "claude-1",
                "agent_id": str(test_agent.id),
                "source": "claude",
                "last_activity": 10,
            }
        ],
    )
    monkeypatch.setattr(
        sessions_mod,
        "get_local_codex_sessions",
        lambda: [
            {
                "id": "codex-1",
                "agent_id": str(test_agent.id),
                "source": "codex",
                "last_activity": 40,
            }
        ],
    )
    monkeypatch.setattr(
        sessions_mod,
        "get_local_hermes_sessions",
        lambda: [
            {
                "id": "hermes-1",
                "agent_id": str(test_agent.id),
                "source": "hermes",
                "last_activity": 20,
            }
        ],
    )

    response = await client.get("/v1/sessions")

    assert response.status_code == 200
    data = response.json()
    assert [item["id"] for item in data["sessions"]] == [
        "codex-1",
        "gateway-1",
        "hermes-1",
        "claude-1",
    ]


@pytest.mark.asyncio
async def test_list_sessions_with_agent_id_scopes_to_gateway_sessions_only(
    client: AsyncClient,
    monkeypatch,
    test_agent,
):
    captured: dict[str, str | None] = {}

    def fake_list_gateway_sessions(*, assistant_id=None):
        captured["assistant_id"] = assistant_id
        return [
            {
                "id": "agent-session",
                "agent_id": str(test_agent.id),
                "source": "openclaw",
                "last_activity": 50,
            }
        ]

    monkeypatch.setattr(sessions_mod, "list_gateway_sessions", fake_list_gateway_sessions)
    monkeypatch.setattr(
        sessions_mod,
        "get_local_claude_sessions",
        lambda: [{"id": "claude-1", "source": "claude", "last_activity": 10}],
    )
    monkeypatch.setattr(
        sessions_mod,
        "get_local_codex_sessions",
        lambda: [{"id": "codex-1", "source": "codex", "last_activity": 40}],
    )
    monkeypatch.setattr(
        sessions_mod,
        "get_local_hermes_sessions",
        lambda: [{"id": "hermes-1", "source": "hermes", "last_activity": 20}],
    )

    response = await client.get("/v1/sessions", params={"agent_id": str(test_agent.id)})

    assert response.status_code == 200
    assert response.json()["sessions"] == [
        {
            "id": "agent-session",
            "agent_id": str(test_agent.id),
            "source": "openclaw",
            "last_activity": 50,
        }
    ]
    assert captured["assistant_id"] is None


@pytest.mark.asyncio
async def test_list_sessions_with_unknown_agent_id_returns_404(client: AsyncClient):
    response = await client.get(
        "/v1/sessions",
        params={"agent_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions_with_foreign_agent_id_returns_indistinguishable_404(
    other_user_client: AsyncClient,
    test_agent,
):
    response = await other_user_client.get(
        "/v1/sessions",
        params={"agent_id": str(test_agent.id)},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions_uses_local_openclaw_session_store_when_gateway_unavailable(
    client: AsyncClient,
    db_session,
    monkeypatch,
    test_user,
    test_agent,
    tmp_path,
):
    test_agent.name = "Ops Assistant"
    test_agent.config = json.dumps({"assistant_id": "ops-assistant"})
    await db_session.commit()

    openclaw_home = tmp_path / "openclaw-home"
    sessions_dir = openclaw_home / "agents" / "ops-assistant" / "sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "sessions.json").write_text(
        json.dumps(
            {
                "session-key-1": {
                    "sessionId": "session-123",
                    "updatedAt": 1_700_000_100,
                    "createdAt": 1_700_000_000,
                    "chatType": "webchat",
                    "model": "openai/gpt-5",
                    "totalTokens": 20,
                    "deliveryContext": {"channel": "webchat"},
                }
            }
        )
    )

    monkeypatch.setenv("OPENCLAW_HOME", str(openclaw_home))
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane._request_gateway_json",
        lambda _paths: None,
    )
    await filter_and_claim_owned_sessions(
        db_session,
        user=test_user,
        sessions=[
            {
                "id": "session-123",
                "key": "session-key-1",
                "agent_id": str(test_agent.id),
                "source": "openclaw-local",
            }
        ],
    )

    response = await client.get("/v1/sessions", params={"agent_id": str(test_agent.id)})

    assert response.status_code == 200
    payload = response.json()["sessions"]
    assert len(payload) == 1
    assert payload[0]["id"] == "session-123"
    assert payload[0]["agent"] == "ops-assistant"
    assert payload[0]["channel"] == "webchat"
    assert payload[0]["tokens"] == "20"
    assert payload[0]["source"] == "openclaw-local"


@pytest.mark.asyncio
async def test_session_action_invalid_action(client: AsyncClient, db_session, test_user):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    response = await client.post(
        "/v1/sessions?action=bogus",
        json={"session_key": "test-session"},
    )
    assert response.status_code == 400
    assert "Invalid action" in response.json()["detail"]


@pytest.mark.asyncio
async def test_session_action_set_thinking_invalid_level(
    client: AsyncClient,
    db_session,
    test_user,
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    response = await client.post(
        "/v1/sessions?action=set-thinking",
        json={"session_key": "test-session", "level": "superultra"},
    )
    assert response.status_code == 400
    assert "Invalid thinking level" in response.json()["detail"]


@pytest.mark.asyncio
async def test_session_action_forwards_to_gateway(
    client: AsyncClient,
    monkeypatch,
    db_session,
    test_user,
    test_agent,
):
    captured: dict[str, object] = {}

    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        captured.update({"method": method, "path": path, "json": json, "params": params})
        return {"message": "thinking updated"}

    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)
    session = await _bind_owned_session(db_session, test_user, test_agent)
    monkeypatch.setattr(sessions_mod, "list_gateway_sessions", lambda assistant_id=None: [session])

    response = await client.post(
        "/v1/sessions?action=set-thinking",
        json={"session_key": "test-session", "level": "high"},
    )

    assert response.status_code == 200
    assert captured == {
        "method": "PATCH",
        "path": "/api/sessions/thinking",
        "json": {"session": "test-session", "level": "high"},
        "params": None,
    }
    assert response.json() == {
        "session_key": "test-session",
        "action": "set-thinking",
        "applied": True,
        "detail": "thinking updated",
    }


@pytest.mark.asyncio
async def test_session_action_surfaces_gateway_error(
    client: AsyncClient,
    monkeypatch,
    db_session,
    test_user,
    test_agent,
):
    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        raise HTTPException(status_code=503, detail="gateway offline")

    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)
    session = await _bind_owned_session(db_session, test_user, test_agent)
    monkeypatch.setattr(sessions_mod, "list_gateway_sessions", lambda assistant_id=None: [session])

    response = await client.post(
        "/v1/sessions?action=set-verbose",
        json={"session_key": "test-session", "level": "on"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "gateway offline"


@pytest.mark.asyncio
async def test_delete_session_forwards_to_gateway(
    client: AsyncClient,
    monkeypatch,
    db_session,
    test_user,
    test_agent,
):
    captured: dict[str, object] = {}

    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        captured.update({"method": method, "path": path, "json": json, "params": params})
        return {"status": 204}

    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)
    session = await _bind_owned_session(db_session, test_user, test_agent)
    monkeypatch.setattr(sessions_mod, "list_gateway_sessions", lambda assistant_id=None: [session])

    response = await client.request(
        "DELETE",
        "/v1/sessions",
        json={"session_key": "test-session"},
    )

    assert response.status_code == 200
    assert captured == {
        "method": "DELETE",
        "path": "/api/sessions/test-session",
        "json": None,
        "params": None,
    }
    assert response.json() == {
        "session_key": "test-session",
        "action": "delete",
        "applied": True,
        "detail": None,
    }


@pytest.mark.asyncio
async def test_delete_session_surfaces_gateway_not_found(
    client: AsyncClient,
    monkeypatch,
    db_session,
    test_user,
    test_agent,
):
    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        raise HTTPException(status_code=404, detail="Session not found on gateway")

    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)
    session = await _bind_owned_session(db_session, test_user, test_agent)
    monkeypatch.setattr(sessions_mod, "list_gateway_sessions", lambda assistant_id=None: [session])

    response = await client.request(
        "DELETE",
        "/v1/sessions",
        json={"session_key": "test-session"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found on gateway"
