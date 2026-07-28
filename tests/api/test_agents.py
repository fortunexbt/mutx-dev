"""
Tests for /agents endpoints.
"""

import json
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.models import Agent, AgentStatus, Deployment, UsageEvent


@pytest_asyncio.fixture(autouse=True)
async def developer_principals(db_session, test_user, other_user):
    test_user.roles = ["DEVELOPER"]
    other_user.roles = ["DEVELOPER"]
    await db_session.commit()


class TestCreateAgent:
    """Tests for POST /agents endpoint."""

    @pytest.mark.asyncio
    async def test_create_agent_success(self, client: AsyncClient, test_user):
        """Test creating an agent successfully."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "new-agent",
                "description": "A new test agent",
                "type": "openai",
                "config": {"model": "gpt-4o", "temperature": 0.7},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new-agent"
        assert data["description"] == "A new test agent"
        assert data["type"] == "openai"
        assert data["status"] == "creating"
        assert data["config_version"] == 1

    @pytest.mark.asyncio
    async def test_create_agent_missing_name(self, client: AsyncClient):
        """Test creating an agent without name returns validation error."""
        response = await client.post(
            "/v1/agents",
            json={
                "description": "Agent without name",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_agent_empty_name(self, client: AsyncClient):
        """Test creating an agent with empty name returns validation error."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_agent_name_too_long(self, client: AsyncClient):
        """Test creating an agent with name exceeding max length returns validation error."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "a" * 256,  # max_length is 255
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_agent_description_too_long(self, client: AsyncClient):
        """Test creating an agent with description exceeding max length returns validation error."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "valid-name",
                "description": "d" * 1001,  # max_length is 1000
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_agent_anthropic_type(self, client: AsyncClient):
        """Test creating an agent with anthropic type."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "anthropic-agent",
                "type": "anthropic",
                "config": {"model": "claude-3-5-sonnet-20241022", "temperature": 0.7},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "anthropic-agent"
        assert data["type"] == "anthropic"

    @pytest.mark.asyncio
    async def test_create_agent_langchain_type(self, client: AsyncClient):
        """Test creating an agent with langchain type."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "langchain-agent",
                "type": "langchain",
                "config": {"chain_id": "test-chain", "parameters": {}},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "langchain-agent"
        assert data["type"] == "langchain"

    @pytest.mark.asyncio
    async def test_create_agent_custom_type(self, client: AsyncClient):
        """Test creating an agent with custom type."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "custom-agent",
                "type": "custom",
                "config": {"image": "custom-image:latest", "command": [], "env": {}},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "custom-agent"
        assert data["type"] == "custom"

    @pytest.mark.asyncio
    async def test_create_agent_openclaw_type(self, client: AsyncClient):
        response = await client.post(
            "/v1/agents",
            json={
                "name": "Personal Assistant",
                "type": "openclaw",
                "config": {
                    "assistant_id": "personal-assistant",
                    "workspace": "personal-assistant",
                    "channels": {
                        "webchat": {
                            "label": "WebChat",
                            "enabled": True,
                            "mode": "pairing",
                            "allow_from": [],
                        }
                    },
                    "skills": ["web_search"],
                },
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "openclaw"
        assert data["config"]["template"] == "personal_assistant"
        assert data["config"]["assistant_id"] == "personal-assistant"

    @pytest.mark.asyncio
    async def test_create_agent_with_config_as_json_string(self, client: AsyncClient):
        """Test creating an agent with config as JSON string."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "json-string-config-agent",
                "type": "openai",
                "config": json.dumps({"model": "gpt-4o", "temperature": 0.5}),
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["config"]["model"] == "gpt-4o"
        assert data["config"]["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_create_agent_invalid_config_json_string(self, client: AsyncClient):
        """Test creating an agent with invalid JSON in config string."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "invalid-json-agent",
                "type": "openai",
                "config": "not-valid-json{",
            },
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_agent_invalid_type(self, client: AsyncClient):
        """Test creating an agent with invalid type returns validation error."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "invalid-type-agent",
                "type": "invalid_type",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_agent_duplicate_name_allowed(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test that creating agents with duplicate names is allowed."""
        # Create first agent
        response = await client.post(
            "/v1/agents",
            json={"name": "duplicate-name-test"},
        )
        assert response.status_code == 201

        # Create second agent with same name - should succeed
        response = await client.post(
            "/v1/agents",
            json={"name": "duplicate-name-test"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "duplicate-name-test"
        # Should have different IDs
        agents = await client.get("/v1/agents")
        agent_list = agents.json()
        assert len(agent_list["items"]) == 2

    @pytest.mark.asyncio
    async def test_create_agent_unauthorized(self, client_no_auth: AsyncClient):
        """Test that creating an agent without authentication returns 401."""
        response = await client_no_auth.post(
            "/v1/agents",
            json={"name": "unauthorized-agent"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_agent_invalid_config(self, client: AsyncClient):
        """Test creating an agent with invalid config schema."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "invalid-config-agent",
                "type": "openai",
                "config": {"model": "gpt-4o", "temperature": 5.0},  # Invalid temperature > 2.0
            },
        )
        assert response.status_code == 422
        assert "Configuration validation failed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_agent_with_minimal_data(self, client: AsyncClient):
        """Test creating an agent with minimal data."""
        response = await client.post(
            "/v1/agents",
            json={
                "name": "minimal-agent",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "minimal-agent"
        assert data["config"]["name"] == "minimal-agent"
        assert data["config_version"] == 1

    @pytest.mark.asyncio
    async def test_create_agent_succeeds_when_usage_tracking_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch,
    ):
        async def raise_usage_failure(*_args, **_kwargs):
            raise RuntimeError("usage unavailable")

        monkeypatch.setattr("src.api.services.usage.track_usage", raise_usage_failure)

        response = await client.post(
            "/v1/agents",
            json={"name": "usage-failure-agent"},
        )

        assert response.status_code == 201
        created_id = uuid.UUID(response.json()["id"])
        persisted = await db_session.get(Agent, created_id)
        assert persisted is not None
        assert persisted.name == "usage-failure-agent"

    @pytest.mark.asyncio
    async def test_create_agent_records_single_usage_event(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        response = await client.post(
            "/v1/agents",
            json={"name": "single-usage-agent"},
        )

        assert response.status_code == 201
        created_id = response.json()["id"]
        usage_events = (
            (await db_session.execute(select(UsageEvent).where(UsageEvent.user_id == test_user.id)))
            .scalars()
            .all()
        )

        assert [event.event_type for event in usage_events] == ["agent_create"]
        assert usage_events[0].resource_id == created_id


class TestListAgents:
    """Tests for GET /agents endpoint."""

    @pytest.mark.asyncio
    async def test_list_agents_empty(self, client: AsyncClient):
        """Test listing agents when none exist."""
        response = await client.get("/v1/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_agents_with_data(self, client: AsyncClient, test_agent):
        """Test listing agents returns user's agents."""
        response = await client.get("/v1/agents")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == str(test_agent.id)
        assert data["total"] == 1
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_agents_pagination(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test agent listing pagination."""
        # Create multiple agents
        for i in range(5):
            agent = Agent(
                name=f"agent-{i}",
                description=f"Agent {i}",
                config="{}",
                user_id=test_user.id,
                status=AgentStatus.CREATING,
            )
            db_session.add(agent)
        await db_session.commit()

        response = await client.get("/v1/agents?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["has_more"] is True

    @pytest.mark.asyncio
    async def test_list_agents_scoped_to_authenticated_user(
        self, client: AsyncClient, test_agent, other_user_client: AsyncClient
    ):
        """Test listing agents always uses the authenticated user scope."""
        # Test user can see their own agents
        response = await client.get("/v1/agents")
        assert len(response.json()["items"]) == 1

        # Other user sees empty list
        response = await other_user_client.get("/v1/agents")
        assert len(response.json()["items"]) == 0

        # Supplying user_id in query must not expand access scope
        response = await other_user_client.get(f"/v1/agents?user_id={test_agent.user_id}")
        assert response.status_code == 200
        assert response.json()["items"] == []


class TestAgentAuthorization:
    """Authorization guardrails for /agents endpoints."""

    @pytest.mark.asyncio
    async def test_list_agents_requires_authentication(self, client_no_auth: AsyncClient):
        response = await client_no_auth.get("/v1/agents")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_agent_requires_authentication(self, client_no_auth: AsyncClient, test_agent):
        response = await client_no_auth.get(f"/v1/agents/{test_agent.id}")
        assert response.status_code == 401


class TestGetAgent:
    """Tests for GET /agents/{agent_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_agent_success(self, client: AsyncClient, test_agent):
        """Test getting a specific agent."""
        response = await client.get(f"/v1/agents/{test_agent.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_agent.id)
        assert data["name"] == test_agent.name

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, client: AsyncClient):
        """Test getting non-existent agent returns 404."""
        response = await client.get("/v1/agents/00000000-0000-0000-0000-999999999999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_agent_other_user_forbidden(
        self, client: AsyncClient, test_agent, other_user_client: AsyncClient
    ):
        """Test that users cannot access other users' agents."""
        response = await other_user_client.get(f"/v1/agents/{test_agent.id}")
        assert response.status_code == 404


class TestDeleteAgent:
    """Tests for DELETE /agents/{agent_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_agent_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test deleting an agent."""
        # Create agent to delete
        agent = Agent(
            name="to-delete",
            description="Will be deleted",
            config="{}",
            user_id=test_user.id,
            status=AgentStatus.CREATING,
        )
        db_session.add(agent)
        await db_session.commit()
        await db_session.refresh(agent)

        response = await client.delete(f"/v1/agents/{agent.id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_agent_not_found(self, client: AsyncClient):
        """Test deleting non-existent agent returns 404."""
        response = await client.delete("/v1/agents/00000000-0000-0000-0000-999999999999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_agent_other_user_forbidden(
        self, client: AsyncClient, test_agent, other_user_client: AsyncClient
    ):
        """Test that users cannot delete other users' agents."""
        response = await other_user_client.delete(f"/v1/agents/{test_agent.id}")
        assert response.status_code == 404


class TestAgentConfig:
    """Tests for /agents/{agent_id}/config endpoints."""

    @pytest.mark.asyncio
    async def test_get_agent_config_success(self, client: AsyncClient, test_agent):
        response = await client.get(f"/v1/agents/{test_agent.id}/config")
        assert response.status_code == 200

        data = response.json()
        assert data["agent_id"] == str(test_agent.id)
        assert data["type"] == "openai"
        assert data["config"]["model"] == "gpt-4"
        assert data["config"]["temperature"] == 0.7
        assert data["config_version"] == 1

    @pytest.mark.asyncio
    async def test_update_agent_config_success(self, client: AsyncClient, test_agent):
        response = await client.patch(
            f"/v1/agents/{test_agent.id}/config",
            json={"config": {"model": "gpt-4o-mini", "temperature": 0.2, "max_tokens": 256}},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["config"]["name"] == test_agent.name
        assert data["config"]["model"] == "gpt-4o-mini"
        assert data["config"]["temperature"] == 0.2
        assert data["config"]["max_tokens"] == 256
        assert data["config"]["version"] == 2
        assert data["config_version"] == 2

    @pytest.mark.asyncio
    async def test_update_agent_config_accepts_json_string(self, client: AsyncClient, test_agent):
        response = await client.patch(
            f"/v1/agents/{test_agent.id}/config",
            json={"config": json.dumps({"model": "gpt-4o", "temperature": 0.1})},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["config"]["model"] == "gpt-4o"
        assert data["config"]["temperature"] == 0.1
        assert data["config"]["version"] == 2

    @pytest.mark.asyncio
    async def test_update_agent_config_invalid_config(self, client: AsyncClient, test_agent):
        response = await client.patch(
            f"/v1/agents/{test_agent.id}/config",
            json={"config": {"model": "gpt-4o", "temperature": 3.5}},
        )
        assert response.status_code == 422
        assert "Configuration validation failed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_agent_config_other_user_forbidden(
        self, other_user_client: AsyncClient, test_agent
    ):
        response = await other_user_client.patch(
            f"/v1/agents/{test_agent.id}/config",
            json={"config": {"model": "gpt-4o", "temperature": 0.3}},
        )
        assert response.status_code == 404


class TestDeployAgent:
    """Tests for POST /agents/{agent_id}/deploy endpoint."""

    @pytest.mark.asyncio
    async def test_deploy_agent_success(
        self, client: AsyncClient, test_agent, db_session: AsyncSession
    ):
        """Test deploying an agent."""
        response = await client.post(f"/v1/agents/{test_agent.id}/deploy")
        assert response.status_code == 200
        data = response.json()
        assert "deployment_id" in data
        assert data["status"] == "deploying"

        deployment = await db_session.get(Deployment, uuid.UUID(data["deployment_id"]))
        assert deployment is not None
        assert deployment.started_at is not None
        assert deployment.started_at.tzinfo is None

        # Verify agent status changed
        await db_session.refresh(test_agent)
        assert test_agent.status == AgentStatus.RUNNING

    @pytest.mark.asyncio
    async def test_deploy_agent_not_found(self, client: AsyncClient):
        """Test deploying non-existent agent returns 404."""
        response = await client.post("/v1/agents/00000000-0000-0000-0000-999999999999/deploy")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_deploy_agent_other_user_forbidden(
        self, client: AsyncClient, test_agent, other_user_client: AsyncClient
    ):
        """Test that users cannot deploy other users' agents."""
        response = await other_user_client.post(f"/v1/agents/{test_agent.id}/deploy")
        assert response.status_code == 404


class TestStopAgent:
    """Tests for POST /agents/{agent_id}/stop endpoint."""

    @pytest.mark.asyncio
    async def test_stop_agent_success(
        self, client: AsyncClient, test_agent, test_deployment, db_session: AsyncSession
    ):
        """Test stopping an agent."""
        # First deploy to have running deployment
        test_agent.status = AgentStatus.RUNNING
        test_deployment.status = "running"
        await db_session.commit()

        response = await client.post(f"/v1/agents/{test_agent.id}/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_agent_not_found(self, client: AsyncClient):
        """Test stopping non-existent agent returns 404."""
        response = await client.post("/v1/agents/00000000-0000-0000-0000-999999999999/stop")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_stop_agent_other_user_forbidden(
        self, other_user_client: AsyncClient, test_agent
    ):
        """Test that users cannot stop other users' agents."""
        response = await other_user_client.post(f"/v1/agents/{test_agent.id}/stop")
        assert response.status_code == 404


class TestAgentLogs:
    """Tests for GET /agents/{agent_id}/logs endpoint."""

    @pytest.mark.asyncio
    async def test_get_agent_logs_success(self, client: AsyncClient, test_agent):
        """Test getting agent logs."""
        response = await client.get(f"/v1/agents/{test_agent.id}/logs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "items" in data
        assert "total" in data
        assert "has_more" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_get_agent_logs_not_found(self, client: AsyncClient):
        """Test getting logs for non-existent agent returns 404."""
        response = await client.get("/v1/agents/00000000-0000-0000-0000-999999999999/logs")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_agent_logs_other_user_forbidden(
        self, client: AsyncClient, test_agent, other_user_client: AsyncClient
    ):
        """Test that users cannot access other users' agent logs."""
        response = await other_user_client.get(f"/v1/agents/{test_agent.id}/logs")
        assert response.status_code == 404


class TestAgentMetrics:
    """Tests for GET /agents/{agent_id}/metrics endpoint."""

    @pytest.mark.asyncio
    async def test_get_agent_metrics_success(self, client: AsyncClient, test_agent):
        """Test getting agent metrics."""
        response = await client.get(f"/v1/agents/{test_agent.id}/metrics")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "items" in data
        assert "total" in data
        assert "has_more" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_get_agent_metrics_not_found(self, client: AsyncClient):
        """Test getting metrics for non-existent agent returns 404."""
        response = await client.get("/v1/agents/00000000-0000-0000-0000-999999999999/metrics")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_agent_metrics_other_user_forbidden(
        self, other_user_client: AsyncClient, test_agent
    ):
        """Test that users cannot access other users' agent metrics."""
        response = await other_user_client.get(f"/v1/agents/{test_agent.id}/metrics")
        assert response.status_code == 404
