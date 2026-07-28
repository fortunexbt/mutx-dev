from datetime import datetime, timezone
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select


@pytest_asyncio.fixture(autouse=True)
async def developer_principals(db_session, test_user, other_user):
    test_user.roles = ["DEVELOPER"]
    other_user.roles = ["DEVELOPER"]
    await db_session.commit()


@pytest.mark.asyncio
async def test_agent_status_requires_agent_auth(client, test_agent):
    response = await client.get(f"/v1/agents/{test_agent.id}/status")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing authorization header"


@pytest.mark.asyncio
async def test_agent_status_returns_authenticated_agent_status(client, db_session, test_agent):
    test_agent.api_key = "mutx_agent_status_test_key"
    test_agent.status = "running"
    test_agent.last_heartbeat = datetime.now(timezone.utc)
    await db_session.commit()

    response = await client.get(
        f"/v1/agents/{test_agent.id}/status",
        headers={"Authorization": f"Bearer {test_agent.api_key}"},
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["agent_id"] == str(test_agent.id)
    assert payload["status"] == "running"
    assert payload["last_heartbeat"] is not None
    assert payload["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_agent_status_rejects_requests_for_other_agents(
    client, db_session, other_user, test_agent
):
    from src.api.models.models import Agent, AgentStatus

    other_agent = Agent(
        id=uuid.UUID("55555555-5555-4555-a555-555555555555"),
        name="other-agent",
        description="Another test agent",
        config='{"model": "gpt-4"}',
        user_id=other_user.id,
        status=AgentStatus.RUNNING,
        api_key="mutx_agent_other_status_key",
    )
    db_session.add(other_agent)
    await db_session.commit()

    response = await client.get(
        f"/v1/agents/{test_agent.id}/status",
        headers={"Authorization": f"Bearer {other_agent.api_key}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Agent ID mismatch"


@pytest.mark.asyncio
async def test_runtime_registered_agent_round_trips_metadata_as_json(client):
    metadata = {
        "provider": "openclaw",
        "model": "gpt-4.1-mini",
        "flags": {"webhooks": True},
    }

    register_response = await client.post(
        "/v1/agents/register",
        json={
            "name": "runtime-json-agent",
            "description": "runtime-created agent",
            "metadata": metadata,
            "capabilities": ["heartbeat"],
        },
    )

    assert register_response.status_code == 200
    agent_id = register_response.json()["agent_id"]

    detail_response = await client.get(f"/v1/agents/{agent_id}")

    assert detail_response.status_code == 200
    assert detail_response.json()["config"] == metadata


@pytest.mark.asyncio
async def test_runtime_registered_agent_api_key_authenticates_status_and_heartbeat(client):
    register_response = await client.post(
        "/v1/agents/register",
        json={
            "name": "runtime-auth-agent",
            "description": "runtime-created agent",
            "metadata": {"provider": "openclaw"},
            "capabilities": ["heartbeat"],
        },
    )

    assert register_response.status_code == 200
    payload = register_response.json()
    agent_id = payload["agent_id"]
    api_key = payload["api_key"]

    status_response = await client.get(
        f"/v1/agents/{agent_id}/status",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert status_response.status_code == 200
    assert status_response.json()["agent_id"] == agent_id

    heartbeat_response = await client.post(
        "/v1/agents/heartbeat",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "agent_id": agent_id,
            "status": "running",
            "message": "demo heartbeat",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["agent_id"] == agent_id


@pytest.mark.asyncio
async def test_heartbeat_promotes_latest_deploying_deployment_to_running(client, db_session):
    from src.api.models import Deployment, DeploymentEvent

    register_response = await client.post(
        "/v1/agents/register",
        json={
            "name": "runtime-deployment-promote",
            "description": "runtime deployment promote coverage",
            "metadata": {"provider": "openclaw"},
            "capabilities": ["heartbeat"],
        },
    )

    assert register_response.status_code == 200
    payload = register_response.json()
    agent_id = payload["agent_id"]
    api_key = payload["api_key"]

    deployment = Deployment(
        agent_id=uuid.UUID(agent_id),
        status="deploying",
        replicas=1,
        started_at=None,
    )
    db_session.add(deployment)
    await db_session.commit()

    heartbeat_response = await client.post(
        "/v1/agents/heartbeat",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "agent_id": agent_id,
            "status": "running",
            "message": "runtime healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    assert heartbeat_response.status_code == 200

    await db_session.refresh(deployment)
    assert deployment.status == "running"
    assert deployment.started_at is not None
    assert deployment.ended_at is None

    events = (
        (
            await db_session.execute(
                select(DeploymentEvent).where(DeploymentEvent.deployment_id == deployment.id)
            )
        )
        .scalars()
        .all()
    )
    assert any(event.event_type == "heartbeat_running" for event in events)


@pytest.mark.asyncio
async def test_agent_log_submission_persists_metadata_as_json(client, db_session, test_agent):
    from src.api.models.models import AgentLog

    api_key = f"mutx_agent_{test_agent.id.hex}_{uuid.uuid4().hex[:24]}"
    test_agent.api_key = api_key
    await db_session.commit()

    metadata = {
        "provider": "openclaw",
        "attempt": 3,
        "flags": {"self_heal": True},
    }

    response = await client.post(
        "/v1/agents/logs",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "agent_id": str(test_agent.id),
            "level": "info",
            "message": "runtime log",
            "metadata": metadata,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    assert response.status_code == 200

    result = await db_session.execute(select(AgentLog).where(AgentLog.agent_id == test_agent.id))
    log_entry = result.scalar_one()
    assert log_entry.meta_data == metadata
