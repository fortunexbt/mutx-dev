"""Tests for POST /v1/events — canonical SDK event ingestion endpoint.

Validates that the /v1/events route delegates correctly to the shared
event ingestion service (src.api.services.event_ingestion).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.models import Agent, AgentLog, AgentStatus, User


@pytest.fixture(autouse=True)
def developer_principal(test_user):
    test_user.roles = ["DEVELOPER"]


class TestEventsRoute:
    """Tests for /v1/events endpoint."""

    @pytest.mark.asyncio
    async def test_events_requires_auth(self, client_no_auth: AsyncClient):
        """POST /v1/events requires authentication."""
        response = await client_no_auth.post(
            "/v1/events",
            json={"event_type": "agent_action"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_events_minimal_payload(self, client: AsyncClient):
        """Accept a minimal event with just event_type."""
        response = await client.post(
            "/v1/events",
            json={"event_type": "agent_action"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["event_type"] == "agent_action"

    @pytest.mark.asyncio
    async def test_events_with_payload(self, client: AsyncClient):
        """Accept an event with adapter-specific payload."""
        response = await client.post(
            "/v1/events",
            json={
                "event_type": "crew_task_start",
                "timestamp": "2026-04-20T09:00:00Z",
                "payload": {
                    "crew_name": "research-crew",
                    "task_description": "Analyze documents",
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["event_type"] == "crew_task_start"

    @pytest.mark.asyncio
    async def test_events_langchain_shape(self, client: AsyncClient):
        """Accept an event matching the LangChain adapter shape."""
        response = await client.post(
            "/v1/events",
            json={
                "event_type": "agent_action",
                "timestamp": "2026-04-20T09:00:00Z",
                "payload": {
                    "agent_name": "researcher",
                    "tool": "search",
                    "tool_input": "MUTX governance",
                    "run_id": str(uuid.uuid4()),
                },
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_events_autogen_shape(self, client: AsyncClient):
        """Accept an event matching the AutoGen adapter shape."""
        response = await client.post(
            "/v1/events",
            json={
                "event_type": "autogen_llm_call",
                "timestamp": "2026-04-20T09:00:00Z",
                "payload": {
                    "agent_name": "assistant",
                    "model": "gpt-4",
                },
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_events_with_owned_agent(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Accept an event with agent_id for an owned agent."""
        agent_id = uuid.uuid4()
        agent = Agent(
            id=agent_id,
            user_id=test_user.id,
            name="Test Agent",
            status=AgentStatus.RUNNING.value,
        )
        db_session.add(agent)
        await db_session.commit()

        response = await client.post(
            "/v1/events",
            json={
                "event_type": "agent_action",
                "agent_id": str(agent_id),
                "payload": {"tool": "search"},
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_events_agent_not_found(self, client: AsyncClient):
        """Return 404 when agent_id references a non-existent agent."""
        response = await client.post(
            "/v1/events",
            json={
                "event_type": "agent_action",
                "agent_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_events_agent_wrong_owner(self, client: AsyncClient, db_session: AsyncSession):
        """Return opaque 404 when agent_id references another user's agent."""
        other_user = User(
            id=uuid.uuid4(),
            email="other-events@example.com",
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
            status=AgentStatus.RUNNING.value,
        )
        db_session.add(agent)
        await db_session.commit()

        response = await client.post(
            "/v1/events",
            json={
                "event_type": "agent_action",
                "agent_id": str(agent_id),
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_events_empty_event_type_rejected(self, client: AsyncClient):
        """Reject events with an empty event_type."""
        response = await client.post(
            "/v1/events",
            json={"event_type": ""},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_events_missing_event_type_rejected(self, client: AsyncClient):
        """Reject events with no event_type field."""
        response = await client.post(
            "/v1/events",
            json={"payload": {"some": "data"}},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_events_persists_agent_log(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Verify the event is stored as an AgentLog when agent_id is provided."""
        agent_id = uuid.uuid4()
        agent = Agent(
            id=agent_id,
            user_id=test_user.id,
            name="Test Agent",
            status=AgentStatus.RUNNING.value,
        )
        db_session.add(agent)
        await db_session.commit()

        response = await client.post(
            "/v1/events",
            json={
                "event_type": "crew_task_end",
                "agent_id": str(agent_id),
                "timestamp": "2026-04-20T09:00:00Z",
                "payload": {"crew_name": "test-crew"},
            },
        )
        assert response.status_code == 200

        logs = (
            (
                await db_session.execute(
                    select(AgentLog)
                    .where(
                        AgentLog.agent_id == agent_id,
                        AgentLog.message == "Adapter event: crew_task_end",
                    )
                    .order_by(AgentLog.timestamp.desc())
                )
            )
            .scalars()
            .all()
        )
        assert len(logs) >= 1
        log = logs[0]
        assert log.level == "info"
        assert log.meta_data is not None
        assert log.meta_data["event_type"] == "crew_task_end"
        assert log.meta_data["adapter_timestamp"] == "2026-04-20T09:00:00Z"

    @pytest.mark.asyncio
    async def test_events_no_agent_id_accepted_no_log(self, client: AsyncClient):
        """Events without agent_id are accepted but no AgentLog is created."""
        response = await client.post(
            "/v1/events",
            json={
                "event_type": "system.heartbeat",
                "timestamp": "2026-04-20T10:00:00Z",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
