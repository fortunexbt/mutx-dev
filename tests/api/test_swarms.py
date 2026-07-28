"""
Tests for /swarms endpoints.
"""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_blueprints_includes_multimodal_review_loop(client: AsyncClient):
    response = await client.get("/v1/swarms/blueprints")

    assert response.status_code == 200
    blueprint_ids = {item["id"] for item in response.json()}
    assert "multimodal-review-loop" in blueprint_ids


class TestListSwarms:
    """Tests for GET /swarms endpoint."""

    @pytest.mark.asyncio
    async def test_list_swarms_empty(self, client: AsyncClient):
        """Test listing swarms when none exist."""
        response = await client.get("/v1/swarms")
        assert response.status_code == 200
        data = response.json()
        # Response is wrapped in {"items": [...], "total": N}
        assert data["items"] == []
        assert data["total"] == 0
        assert "has_more" in data
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_swarms_after_create(self, client: AsyncClient, test_agent):
        """Test listing swarms after creating one."""
        # Create a swarm
        create_response = await client.post(
            "/v1/swarms",
            json={
                "name": "test-swarm-list",
                "description": "A test swarm",
                "agent_ids": [str(test_agent.id)],
                "min_replicas": 1,
                "max_replicas": 5,
            },
        )
        assert create_response.status_code == 201

        # List swarms - should have at least our swarm
        response = await client.get("/v1/swarms")
        assert response.status_code == 200
        data = response.json()
        # Find our swarm
        swarms = [s for s in data["items"] if s["name"] == "test-swarm-list"]
        assert len(swarms) == 1
        assert swarms[0]["description"] == "A test swarm"


class TestCreateSwarm:
    """Tests for POST /swarms endpoint."""

    @pytest.mark.asyncio
    async def test_create_swarm_success(self, client: AsyncClient, test_agent):
        """Test creating a swarm successfully."""
        response = await client.post(
            "/v1/swarms",
            json={
                "name": "my-swarm-create",
                "description": "My first swarm",
                "agent_ids": [str(test_agent.id)],
                "min_replicas": 2,
                "max_replicas": 10,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "my-swarm-create"
        assert data["description"] == "My first swarm"
        assert len(data["agent_ids"]) == 1
        assert data["min_replicas"] == 2
        assert data["max_replicas"] == 10
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_swarm_minimal(self, client: AsyncClient, test_agent):
        """Test creating a swarm with minimal data."""
        response = await client.post(
            "/v1/swarms",
            json={
                "name": "minimal-swarm",
                "agent_ids": [str(test_agent.id)],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "minimal-swarm"
        assert data["min_replicas"] == 1  # default
        assert data["max_replicas"] == 10  # default

    @pytest.mark.asyncio
    async def test_create_swarm_with_nonexistent_agent(self, client: AsyncClient):
        """Test creating a swarm with non-existent agent fails."""
        fake_agent_id = uuid.uuid4()
        response = await client.post(
            "/v1/swarms",
            json={
                "name": "bad-agent-swarm",
                "agent_ids": [str(fake_agent_id)],
            },
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_swarm_empty_agent_ids(self, client: AsyncClient):
        """Test creating a swarm with empty agent_ids fails."""
        response = await client.post(
            "/v1/swarms",
            json={
                "name": "empty-swarm",
                "agent_ids": [],
            },
        )
        assert response.status_code == 422


class TestGetSwarm:
    """Tests for GET /swarms/{swarm_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_swarm_success(self, client: AsyncClient, test_agent):
        """Test getting a specific swarm."""
        # Create a swarm first
        create_response = await client.post(
            "/v1/swarms",
            json={
                "name": "get-test-swarm",
                "description": "For get test",
                "agent_ids": [str(test_agent.id)],
            },
        )
        swarm_id = create_response.json()["id"]

        # Get the swarm
        response = await client.get(f"/v1/swarms/{swarm_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == swarm_id
        assert data["name"] == "get-test-swarm"

    @pytest.mark.asyncio
    async def test_get_swarm_not_found(self, client: AsyncClient):
        """Test getting a non-existent swarm returns 404."""
        fake_id = uuid.uuid4()
        response = await client.get(f"/v1/swarms/{fake_id}")
        assert response.status_code == 404


class TestScaleSwarm:
    """Tests for POST /swarms/{swarm_id}/scale endpoint."""

    @pytest.mark.asyncio
    async def test_scale_swarm_success(self, client: AsyncClient, test_agent):
        """Test scaling a swarm."""
        # Create a swarm first
        create_response = await client.post(
            "/v1/swarms",
            json={
                "name": "scale-test-swarm",
                "agent_ids": [str(test_agent.id)],
                "min_replicas": 1,
                "max_replicas": 10,
            },
        )
        swarm_id = create_response.json()["id"]

        # Scale the swarm
        response = await client.post(
            f"/v1/swarms/{swarm_id}/scale",
            json={"replicas": 5},
        )
        assert response.status_code == 200
        data = response.json()
        # The response is the full swarm object
        assert "replicas" not in data  # Swarm doesn't have replicas at top level
        assert data["min_replicas"] == 1
        assert data["max_replicas"] == 10

    @pytest.mark.asyncio
    async def test_scale_swarm_not_found(self, client: AsyncClient):
        """Test scaling a non-existent swarm returns 404."""
        fake_id = uuid.uuid4()
        response = await client.post(
            f"/v1/swarms/{fake_id}/scale",
            json={"replicas": 3},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_scale_swarm_invalid_replicas(self, client: AsyncClient, test_agent):
        """Test scaling with invalid replica count outside range."""
        # Create a swarm first with specific limits
        create_response = await client.post(
            "/v1/swarms",
            json={
                "name": "invalid-scale-swarm",
                "agent_ids": [str(test_agent.id)],
                "min_replicas": 2,
                "max_replicas": 5,
            },
        )
        swarm_id = create_response.json()["id"]

        # Try to scale below min_replicas
        response = await client.post(
            f"/v1/swarms/{swarm_id}/scale",
            json={"replicas": 1},  # Below min of 2
        )
        assert response.status_code == 400
        assert "replicas must be between" in response.json()["detail"].lower()
