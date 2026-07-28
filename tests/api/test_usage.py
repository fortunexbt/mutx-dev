"""
Tests for /usage endpoints.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.api.models.models import UsageEvent


@pytest.fixture(autouse=True)
def developer_principal(test_user):
    test_user.roles = ["DEVELOPER"]


class TestCreateUsageEvent:
    """Tests for POST /usage/events."""

    @pytest.mark.asyncio
    async def test_create_usage_event_success(self, client: AsyncClient):
        """Test creating a usage event."""
        response = await client.post(
            "/v1/usage/events",
            json={
                "event_type": "agent_create",
                "resource_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "agent_create"
        assert "id" in data
        assert "user_id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_usage_event_with_metadata(self, client: AsyncClient):
        """Test creating a usage event with metadata."""
        response = await client.post(
            "/v1/usage/events",
            json={
                "event_type": "deployment_create",
                "resource_id": str(uuid.uuid4()),
                "metadata": {"replicas": 2, "region": "us-east-1"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "deployment_create"
        # Check the computed_field metadata is properly deserialized
        assert data["metadata"] == {"replicas": 2, "region": "us-east-1"}

    @pytest.mark.asyncio
    async def test_create_usage_event_round_trips_resource_type_and_credits(
        self,
        client: AsyncClient,
    ):
        response = await client.post(
            "/v1/usage/events",
            json={
                "event_type": "deployment_create",
                "resource_type": "deployment",
                "resource_id": str(uuid.uuid4()),
                "credits_used": 2.5,
                "metadata": {"replicas": 2},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["resource_type"] == "deployment"
        assert data["credits_used"] == 2.5
        assert data["metadata"] == {"replicas": 2}

    @pytest.mark.asyncio
    async def test_create_usage_event_requires_auth(self, client_no_auth: AsyncClient):
        """Test that creating a usage event requires authentication."""
        response = await client_no_auth.post(
            "/v1/usage/events",
            json={
                "event_type": "agent_create",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_usage_event_minimal_data(self, client: AsyncClient):
        """Test creating a usage event with minimal required fields."""
        response = await client.post(
            "/v1/usage/events",
            json={
                "event_type": "api_call",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "api_call"


class TestListUsageEvents:
    """Tests for GET /usage/events."""

    @pytest.mark.asyncio
    async def test_list_usage_events_empty(self, client: AsyncClient):
        """Test listing usage events when none exist."""
        response = await client.get("/v1/usage/events")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "has_more" in data
        assert data["has_more"] is False
        assert len(data["items"]) == 0

    @pytest.mark.asyncio
    async def test_list_usage_events_with_data(
        self, client: AsyncClient, test_user, db_session: AsyncSession
    ):
        """Test listing usage events for the authenticated user."""
        # Create some usage events for the test user
        event1 = UsageEvent(
            id=uuid.uuid4(),
            user_id=test_user.id,
            event_type="agent_create",
            resource_id=str(uuid.uuid4()),
        )
        event2 = UsageEvent(
            id=uuid.uuid4(),
            user_id=test_user.id,
            event_type="deployment_create",
            resource_id=str(uuid.uuid4()),
        )
        db_session.add(event1)
        db_session.add(event2)
        await db_session.commit()

        response = await client.get("/v1/usage/events")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_usage_events_filter_by_event_type(
        self, client: AsyncClient, test_user, db_session: AsyncSession
    ):
        """Test filtering usage events by event_type."""
        # Create events with different types
        event1 = UsageEvent(
            id=uuid.uuid4(),
            user_id=test_user.id,
            event_type="agent_create",
            resource_id=str(uuid.uuid4()),
        )
        event2 = UsageEvent(
            id=uuid.uuid4(),
            user_id=test_user.id,
            event_type="deployment_create",
            resource_id=str(uuid.uuid4()),
        )
        db_session.add(event1)
        db_session.add(event2)
        await db_session.commit()

        response = await client.get("/v1/usage/events?event_type=agent_create")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["event_type"] == "agent_create"

    @pytest.mark.asyncio
    async def test_list_usage_events_pagination(
        self, client: AsyncClient, test_user, db_session: AsyncSession
    ):
        """Test pagination of usage events."""
        # Create multiple events
        for i in range(15):
            event = UsageEvent(
                id=uuid.uuid4(),
                user_id=test_user.id,
                event_type=f"api_call_{i}",
                resource_id=str(uuid.uuid4()),
            )
            db_session.add(event)
        await db_session.commit()

        # Test limit
        response = await client.get("/v1/usage/events?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["limit"] == 5
        assert data["has_more"] is True

        # Test offset
        response = await client.get("/v1/usage/events?skip=10&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_usage_events_requires_auth(self, client_no_auth: AsyncClient):
        """Test that listing usage events requires authentication."""
        response = await client_no_auth.get("/v1/usage/events")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_usage_events_only_shows_own_events(
        self, client: AsyncClient, test_user, db_session: AsyncSession
    ):
        """Test that users only see their own usage events."""
        # Create event for another user
        other_user_id = uuid.uuid4()
        other_event = UsageEvent(
            id=uuid.uuid4(),
            user_id=other_user_id,
            event_type="agent_create",
            resource_id=str(uuid.uuid4()),
        )
        db_session.add(other_event)
        await db_session.commit()

        # Create event for test user
        own_event = UsageEvent(
            id=uuid.uuid4(),
            user_id=test_user.id,
            event_type="deployment_create",
            resource_id=str(uuid.uuid4()),
        )
        db_session.add(own_event)
        await db_session.commit()

        response = await client.get("/v1/usage/events")
        assert response.status_code == 200
        data = response.json()
        # Should only see own event
        assert data["total"] == 1
        assert data["items"][0]["event_type"] == "deployment_create"


class TestGetUsageEvent:
    """Tests for GET /usage/events/{event_id}."""

    @pytest.mark.asyncio
    async def test_get_usage_event_success(
        self, client: AsyncClient, test_user, db_session: AsyncSession
    ):
        """Test getting a specific usage event."""
        event = UsageEvent(
            id=uuid.uuid4(),
            user_id=test_user.id,
            event_type="agent_create",
            resource_id=str(uuid.uuid4()),
        )
        db_session.add(event)
        await db_session.commit()

        response = await client.get(f"/v1/usage/events/{event.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["event_type"] == "agent_create"

    @pytest.mark.asyncio
    async def test_get_usage_event_not_found(self, client: AsyncClient):
        """Test getting a non-existent usage event."""
        response = await client.get(f"/v1/usage/events/{uuid.uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_usage_event_other_user_forbidden(
        self, client: AsyncClient, test_user, db_session: AsyncSession
    ):
        """Test that users cannot access other users' events."""
        # Create event for another user
        other_user_id = uuid.uuid4()
        other_event = UsageEvent(
            id=uuid.uuid4(),
            user_id=other_user_id,
            event_type="agent_create",
            resource_id=str(uuid.uuid4()),
        )
        db_session.add(other_event)
        await db_session.commit()

        response = await client.get(f"/v1/usage/events/{other_event.id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_usage_event_requires_auth(self, client_no_auth: AsyncClient):
        """Test that getting a usage event requires authentication."""
        response = await client_no_auth.get(f"/v1/usage/events/{uuid.uuid4()}")
        assert response.status_code == 401
