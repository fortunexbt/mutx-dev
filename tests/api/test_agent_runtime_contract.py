from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture(autouse=True)
async def developer_principals(db_session, test_user, other_user):
    test_user.roles = ["DEVELOPER"]
    other_user.roles = ["DEVELOPER"]
    await db_session.commit()


@pytest.mark.asyncio
async def test_registered_agent_api_key_authenticates_runtime_status_and_heartbeat(
    client: AsyncClient, db_session, test_user
):
    register_response = await client.post(
        "/v1/agents/register",
        json={
            "name": "runtime-auth-contract",
            "description": "runtime auth contract coverage",
            "metadata": {"demo": True},
            "capabilities": ["heartbeat"],
        },
    )

    assert register_response.status_code == 200
    payload = register_response.json()
    agent_id = payload["agent_id"]
    api_key = payload["api_key"]
    assert api_key.startswith("mutx_agent_")

    runtime_headers = {"Authorization": f"Bearer {api_key}"}

    status_response = await client.get(f"/v1/agents/{agent_id}/status", headers=runtime_headers)
    assert status_response.status_code == 200
    assert status_response.json()["agent_id"] == agent_id
    assert status_response.json()["status"] == "running"

    heartbeat_response = await client.post(
        "/v1/agents/heartbeat",
        headers=runtime_headers,
        json={
            "agent_id": agent_id,
            "status": "running",
            "message": "contract ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["agent_id"] == agent_id


@pytest.mark.asyncio
async def test_agent_status_requires_runtime_auth_not_just_agent_id(
    client_no_auth: AsyncClient, test_agent
):
    unauthenticated_response = await client_no_auth.get(f"/v1/agents/{test_agent.id}/status")

    assert unauthenticated_response.status_code == 401
    assert unauthenticated_response.json()["detail"] == "Missing authorization header"


@pytest.mark.asyncio
async def test_agent_commands_static_route_is_not_shadowed(client: AsyncClient):
    register_response = await client.post(
        "/v1/agents/register",
        json={
            "name": "commands-route-contract",
            "description": "static route ordering coverage",
            "metadata": {},
            "capabilities": ["commands"],
        },
    )
    assert register_response.status_code == 200
    agent = register_response.json()

    response = await client.get(
        "/v1/agents/commands",
        params={"agent_id": agent["agent_id"]},
        headers={"Authorization": f"Bearer {agent['api_key']}"},
    )

    assert response.status_code == 200
    assert response.json() == {"commands": []}


@pytest.mark.asyncio
async def test_connected_agent_runtime_sdk_uses_status_auth_contract(client: AsyncClient):
    import importlib.util

    module_path = Path(__file__).resolve().parents[2] / "sdk" / "mutx" / "agent_runtime.py"
    spec = importlib.util.spec_from_file_location("mutx_agent_runtime_module", module_path)
    agent_runtime_module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(agent_runtime_module)
    MutxAgentClient = agent_runtime_module.MutxAgentClient

    register_response = await client.post(
        "/v1/agents/register",
        json={
            "name": "sdk-connect-contract",
            "description": "sdk connect contract coverage",
            "metadata": {"demo": True},
            "capabilities": ["heartbeat"],
        },
    )

    assert register_response.status_code == 200
    payload = register_response.json()

    sdk_client = MutxAgentClient(mutx_url="http://testserver")

    transport = client._transport
    sdk_client._client = __import__("httpx").AsyncClient(
        transport=transport,
        base_url=sdk_client.api_base_url,
        timeout=sdk_client.timeout,
        headers={"Content-Type": "application/json"},
    )

    connected = await sdk_client.connect(payload["agent_id"], payload["api_key"])

    assert connected is True
    assert sdk_client.is_registered is True

    heartbeat_response = await sdk_client.heartbeat(status="running", message="sdk connect ok")
    assert heartbeat_response["agent_id"] == payload["agent_id"]

    await sdk_client.close()


@pytest.mark.asyncio
async def test_agent_status_auth_rejects_other_agent_api_key(client: AsyncClient):
    first = await client.post(
        "/v1/agents/register",
        json={
            "name": "owner-a",
            "description": "ownership check a",
            "metadata": {"demo": True},
            "capabilities": ["heartbeat"],
        },
    )
    second = await client.post(
        "/v1/agents/register",
        json={
            "name": "owner-b",
            "description": "ownership check b",
            "metadata": {"demo": True},
            "capabilities": ["heartbeat"],
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200

    first_payload = first.json()
    second_payload = second.json()

    wrong_auth_response = await client.get(
        f"/v1/agents/{second_payload['agent_id']}/status",
        headers={"Authorization": f"Bearer {first_payload['api_key']}"},
    )

    assert wrong_auth_response.status_code == 403
    assert wrong_auth_response.json()["detail"] == "Agent ID mismatch"


@pytest.mark.asyncio
async def test_heartbeat_event_payload_shape_and_timing_contract(client: AsyncClient, monkeypatch):
    emitted_events = []

    async def fake_trigger_webhook_event(*args, **kwargs):
        # Preserve call shape: (db, user_id, event, payload)
        emitted_events.append((args[2], args[3]))
        return 1

    monkeypatch.setattr(
        "src.api.routes.agent_runtime.trigger_webhook_event", fake_trigger_webhook_event
    )

    register_response = await client.post(
        "/v1/agents/register",
        json={
            "name": "runtime-heartbeat-shape",
            "description": "heartbeat contract coverage",
            "metadata": {"contract": True},
            "capabilities": ["heartbeat"],
        },
    )
    assert register_response.status_code == 200
    payload = register_response.json()
    agent_id = payload["agent_id"]
    api_key = payload["api_key"]

    # 1) first heartbeat keeps status unchanged => only heartbeat event
    heartbeat_response = await client.post(
        "/v1/agents/heartbeat",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "agent_id": agent_id,
            "status": "running",
            "message": "still running",
            "timestamp": "2026-03-14T14:00:00Z",
            "platform": "test-platform",
            "hostname": "test-host",
        },
    )
    assert heartbeat_response.status_code == 200

    body = heartbeat_response.json()
    assert body["status"] == "ok"
    assert body["agent_id"] == agent_id
    assert "timestamp" in body

    assert len(emitted_events) == 1
    event_name, event_payload = emitted_events.pop(0)
    assert event_name == "agent.heartbeat"
    assert event_payload == {
        "agent_id": agent_id,
        "agent_name": "runtime-heartbeat-shape",
        "status": "running",
        "previous_status": "running",
        "message": "still running",
        "platform": "test-platform",
        "hostname": "test-host",
        "timestamp": body["timestamp"],
    }

    # 2) status change emits heartbeat + status event with identical timestamp
    emitted_events.clear()

    status_change_response = await client.post(
        "/v1/agents/heartbeat",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "agent_id": agent_id,
            "status": "failed",
            "message": "stopped by policy",
            "timestamp": "2026-03-14T14:01:00Z",
            "platform": "test-platform",
            "hostname": "test-host",
        },
    )
    assert status_change_response.status_code == 200

    status_body = status_change_response.json()

    assert len(emitted_events) == 2
    heartbeat_event_name, heartbeat_event_payload = emitted_events[0]
    status_event_name, status_event_payload = emitted_events[1]

    assert heartbeat_event_name == "agent.heartbeat"
    assert status_event_name == "agent.status"
    assert heartbeat_event_payload["agent_id"] == agent_id
    assert status_event_payload["agent_id"] == agent_id
    assert heartbeat_event_payload["timestamp"] == status_body["timestamp"]
    assert status_event_payload["timestamp"] == status_body["timestamp"]
    assert status_event_payload["old_status"] == "running"
    assert status_event_payload["new_status"] == "failed"


@pytest.mark.asyncio
async def test_heartbeat_webhook_failure_does_not_fail_heartbeat_response(
    client: AsyncClient, monkeypatch
):
    call_log = {
        "agent.heartbeat": 0,
        "agent.status": 0,
    }

    async def flaky_trigger_webhook_event(*args, **kwargs):
        # Preserve call shape: (db, user_id, event, payload)
        event_name = args[2]
        call_log[event_name] = call_log.get(event_name, 0) + 1

        if event_name == "agent.heartbeat":
            raise RuntimeError("webhook transport unavailable")

        return 1

    monkeypatch.setattr(
        "src.api.routes.agent_runtime.trigger_webhook_event", flaky_trigger_webhook_event
    )

    register_response = await client.post(
        "/v1/agents/register",
        json={
            "name": "runtime-heartbeat-failure",
            "description": "heartbeat failure coverage",
            "metadata": {"contract": "failure"},
            "capabilities": ["heartbeat"],
        },
    )
    assert register_response.status_code == 200
    payload = register_response.json()
    agent_id = payload["agent_id"]
    api_key = payload["api_key"]

    response = await client.post(
        "/v1/agents/heartbeat",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "agent_id": agent_id,
            "status": "running",
            "message": "heartbeat still accepted despite webhook failure",
            "platform": "test-platform",
            "hostname": "test-host",
            "timestamp": "2026-03-14T14:02:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["agent_id"] == agent_id
    assert "timestamp" in body

    assert call_log["agent.heartbeat"] == 1
    assert call_log["agent.status"] == 0
