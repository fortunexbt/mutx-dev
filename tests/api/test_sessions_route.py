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
async def test_sessions_route_is_mounted_and_returns_valid_state(client: AsyncClient):
    response = await client.get("/v1/sessions")

    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)
    for session in data["sessions"]:
        assert "id" in session
        assert "source" in session


@pytest.mark.asyncio
async def test_sessions_route_requires_auth(client_no_auth: AsyncClient):
    response = await client_no_auth.get("/v1/sessions")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_session_action_requires_auth(client_no_auth: AsyncClient):
    response = await client_no_auth.post(
        "/v1/sessions?action=set-thinking",
        json={"session_key": "test-session", "level": "high"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_session_action_validates_verbose_level(client: AsyncClient, db_session, test_user):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    response = await client.post(
        "/v1/sessions?action=set-verbose",
        json={"session_key": "test-session", "level": "loud"},
    )

    assert response.status_code == 400
    assert "Invalid verbose level" in response.json()["detail"]


@pytest.mark.asyncio
async def test_session_action_validates_reasoning_level(
    client: AsyncClient,
    db_session,
    test_user,
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    response = await client.post(
        "/v1/sessions?action=set-reasoning",
        json={"session_key": "test-session", "level": "deep"},
    )

    assert response.status_code == 400
    assert "Invalid reasoning level" in response.json()["detail"]


@pytest.mark.asyncio
async def test_session_action_validates_label_length(client: AsyncClient, db_session, test_user):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    response = await client.post(
        "/v1/sessions?action=set-label",
        json={"session_key": "test-session", "label": "x" * 101},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Label must be a string up to 100 characters"


@pytest.mark.asyncio
async def test_session_action_forwards_label_to_gateway(
    client: AsyncClient,
    monkeypatch,
    db_session,
    test_user,
    test_agent,
):
    captured: dict[str, object] = {}

    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        captured.update({"method": method, "path": path, "json": json, "params": params})
        return {"detail": "label updated"}

    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)
    session = await _bind_owned_session(db_session, test_user, test_agent)
    monkeypatch.setattr(sessions_mod, "list_gateway_sessions", lambda assistant_id=None: [session])

    response = await client.post(
        "/v1/sessions?action=set-label",
        json={"session_key": "test-session", "label": "Primary lane"},
    )

    assert response.status_code == 200
    assert captured == {
        "method": "PATCH",
        "path": "/api/sessions/label",
        "json": {"session": "test-session", "label": "Primary lane"},
        "params": None,
    }
    assert response.json() == {
        "session_key": "test-session",
        "action": "set-label",
        "applied": True,
        "detail": "label updated",
    }


@pytest.mark.asyncio
async def test_delete_session_surfaces_gateway_error(
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

    response = await client.request(
        "DELETE",
        "/v1/sessions",
        json={"session_key": "test-session"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "gateway offline"
