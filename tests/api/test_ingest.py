"""
Tests for /ingest endpoints.
"""

import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.models import Agent, AgentStatus, User


@pytest.fixture(autouse=True)
def developer_principal(test_user):
    test_user.roles = ["DEVELOPER"]


class TestIngestEndpoints:
    """Tests for ingestion endpoints."""

    @pytest.mark.asyncio
    async def test_agent_status_requires_auth(self, client_no_auth: AsyncClient):
        """Test /ingest/agent-status requires authentication."""
        response = await client_no_auth.post(
            "/v1/ingest/agent-status",
            json={
                "agent_id": str(uuid.uuid4()),
                "status": "running",
                "node_id": "test-node",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_agent_status_update_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test successful agent status update."""
        agent_id = uuid.uuid4()
        agent = Agent(
            id=agent_id,
            user_id=test_user.id,
            name="Test Agent",
            status=AgentStatus.CREATING.value,
        )
        db_session.add(agent)
        await db_session.commit()

        response = await client.post(
            "/v1/ingest/agent-status",
            json={
                "agent_id": str(agent_id),
                "status": "running",
                "node_id": "test-node",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"

    @pytest.mark.asyncio
    async def test_agent_status_update_not_found(self, client: AsyncClient, test_user: User):
        """Test agent status update returns 404 for unknown agent."""
        response = await client.post(
            "/v1/ingest/agent-status",
            json={
                "agent_id": str(uuid.uuid4()),
                "status": "running",
                "node_id": "test-node",
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_agent_status_update_hides_foreign_agent(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Foreign and missing agents both return the opaque not-found response."""
        other_user = User(
            id=uuid.uuid4(),
            email="other@example.com",
            password_hash="hash",
            name="Other User",
        )
        db_session.add(other_user)
        await db_session.commit()

        agent_id = uuid.uuid4()
        agent = Agent(
            id=agent_id,
            user_id=other_user.id,
            name="Other Agent",
            status=AgentStatus.CREATING.value,
        )
        db_session.add(agent)
        await db_session.commit()

        response = await client.post(
            "/v1/ingest/agent-status",
            json={
                "agent_id": str(agent_id),
                "status": "running",
                "node_id": "test-node",
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_agent_status_with_error_overrides_to_failed(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test that sending status=running with error_message overrides to FAILED."""
        from src.api.models.models import AgentLog
        from sqlalchemy import select

        agent_id = uuid.uuid4()
        agent = Agent(
            id=agent_id,
            user_id=test_user.id,
            name="Test Agent",
            status=AgentStatus.CREATING.value,
        )
        db_session.add(agent)
        await db_session.commit()

        response = await client.post(
            "/v1/ingest/agent-status",
            json={
                "agent_id": str(agent_id),
                "status": "running",
                "error_message": "Something went wrong",
                "node_id": "test-node",
            },
        )
        assert response.status_code == 200

        # Agent status should be FAILED, not running
        await db_session.refresh(agent)
        assert agent.status == AgentStatus.FAILED.value

        # The info log should record the FINAL status (failed), not the requested one (running)
        logs = (
            (
                await db_session.execute(
                    select(AgentLog)
                    .where(AgentLog.agent_id == agent_id, AgentLog.level == "info")
                    .order_by(AgentLog.timestamp.desc())
                )
            )
            .scalars()
            .all()
        )
        assert len(logs) >= 1
        info_log = logs[0]
        assert "failed" in info_log.message.lower()
        assert "running" not in info_log.message.lower()


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_triggers_heartbeat_webhook_without_status_change(
    client: AsyncClient, db_session, test_agent, monkeypatch
):
    from src.api.routes.agent_runtime import get_current_agent
    import src.api.routes.agent_runtime as agent_runtime_routes
    from src.api.models.models import AgentStatus

    test_agent.status = AgentStatus.RUNNING.value
    await db_session.commit()

    delivered: list[tuple[str, dict]] = []

    async def mock_trigger_webhook_event(db, user_id, event, payload):
        delivered.append((event, payload))
        return 1

    monkeypatch.setattr(agent_runtime_routes, "trigger_webhook_event", mock_trigger_webhook_event)
    client.app.dependency_overrides[get_current_agent] = lambda: test_agent

    response = await client.post(
        "/v1/agents/heartbeat",
        json={
            "agent_id": str(test_agent.id),
            "status": "running",
            "message": "still alive",
            "platform": "linux",
            "hostname": "agent-01",
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    assert response.status_code == 200
    assert [event for event, _ in delivered] == ["agent.heartbeat"]
    assert delivered[0][1]["agent_id"] == str(test_agent.id)
    assert delivered[0][1]["status"] == "running"
    assert delivered[0][1]["previous_status"] == "running"
    assert delivered[0][1]["message"] == "still alive"
    assert delivered[0][1]["platform"] == "linux"
    assert delivered[0][1]["hostname"] == "agent-01"
    assert delivered[0][1]["timestamp"]

    client.app.dependency_overrides.pop(get_current_agent, None)


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_returns_ok_when_webhook_dispatch_fails(
    client: AsyncClient, db_session, test_agent, monkeypatch
):
    from src.api.routes.agent_runtime import get_current_agent
    import src.api.routes.agent_runtime as agent_runtime_routes
    from src.api.models.models import AgentStatus

    test_agent.status = AgentStatus.CREATING.value
    await db_session.commit()

    emitted_events: list[str] = []

    async def mock_trigger_webhook_event(db, user_id, event, payload):
        emitted_events.append(event)
        raise RuntimeError("webhook dispatch unavailable")

    monkeypatch.setattr(agent_runtime_routes, "trigger_webhook_event", mock_trigger_webhook_event)
    client.app.dependency_overrides[get_current_agent] = lambda: test_agent

    response = await client.post(
        "/v1/agents/heartbeat",
        json={
            "agent_id": str(test_agent.id),
            "status": "running",
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    assert response.status_code == 200
    assert emitted_events == ["agent.heartbeat", "agent.status"]

    await db_session.refresh(test_agent)
    assert test_agent.status == AgentStatus.RUNNING.value
    assert test_agent.last_heartbeat is not None

    client.app.dependency_overrides.pop(get_current_agent, None)


class TestIngestAPIKeyAuth:
    """Tests for API key authentication on ingestion endpoints."""

    @pytest.mark.asyncio
    async def test_agent_status_update_with_api_key(
        self,
        client: AsyncClient,
        client_no_auth: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that an API key can be used to authenticate to /ingest/agent-status."""
        # First create an API key (requires auth)
        create_response = await client.post(
            "/v1/api-keys",
            json={"name": "ingest-key"},
        )
        assert create_response.status_code == 201
        api_key = create_response.json()["key"]

        # Create an agent for the test user
        agent_id = uuid.uuid4()
        agent = Agent(
            id=agent_id,
            user_id=test_user.id,
            name="Test Agent",
            status=AgentStatus.CREATING.value,
        )
        db_session.add(agent)
        await db_session.commit()

        # Use the API key to authenticate (without JWT)
        response = await client_no_auth.post(
            "/v1/ingest/agent-status",
            json={
                "agent_id": str(agent_id),
                "status": "running",
                "node_id": "test-node",
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"

    @pytest.mark.asyncio
    async def test_agent_status_update_with_invalid_api_key(
        self, client_no_auth: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test that an invalid API key is rejected."""
        # Create an agent for the test user
        agent_id = uuid.uuid4()
        agent = Agent(
            id=agent_id,
            user_id=test_user.id,
            name="Test Agent",
            status=AgentStatus.CREATING.value,
        )
        db_session.add(agent)
        await db_session.commit()

        # Use an invalid API key
        response = await client_no_auth.post(
            "/v1/ingest/agent-status",
            json={
                "agent_id": str(agent_id),
                "status": "running",
                "node_id": "test-node",
            },
            headers={"X-API-Key": "mutx_live_invalid_key"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_agent_status_update_with_revoked_api_key(
        self,
        client: AsyncClient,
        client_no_auth: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that a revoked API key is rejected."""
        # Create and then revoke an API key (requires auth)
        create_response = await client.post(
            "/v1/api-keys",
            json={"name": "revoked-key"},
        )
        assert create_response.status_code == 201
        api_key = create_response.json()["key"]
        key_id = create_response.json()["id"]

        # Revoke the key
        revoke_response = await client.delete(f"/v1/api-keys/{key_id}")
        assert revoke_response.status_code == 204

        # Create an agent for the test user
        agent_id = uuid.uuid4()
        agent = Agent(
            id=agent_id,
            user_id=test_user.id,
            name="Test Agent",
            status=AgentStatus.CREATING.value,
        )
        db_session.add(agent)
        await db_session.commit()

        # Use the revoked API key
        response = await client_no_auth.post(
            "/v1/ingest/agent-status",
            json={
                "agent_id": str(agent_id),
                "status": "running",
                "node_id": "test-node",
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 401
