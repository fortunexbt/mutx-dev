"""
Tests for /budgets endpoints.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


class TestGetBudget:
    """Tests for GET /budgets endpoint."""

    @pytest.mark.asyncio
    async def test_get_budget_authenticated(self, client: AsyncClient):
        """Test getting budget as authenticated user."""
        response = await client.get("/v1/budgets")
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "plan" in data
        assert "credits_total" in data
        assert "credits_used" in data
        assert "credits_remaining" in data
        assert "reset_date" in data
        assert "usage_percentage" in data

    @pytest.mark.asyncio
    async def test_get_budget_uses_current_billing_cycle_only(
        self,
        client: AsyncClient,
        db_session,
        test_user,
    ):
        """Historical usage outside the current month should not burn current credits."""
        from src.api.models.models import UsageEvent

        now = datetime.now(timezone.utc)
        current_month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        previous_month_event_time = current_month_start - timedelta(days=1)
        current_month_event_time = current_month_start + timedelta(days=1)

        db_session.add_all(
            [
                UsageEvent(
                    user_id=test_user.id,
                    event_type="api_call",
                    credits_used=80.0,
                    created_at=previous_month_event_time,
                ),
                UsageEvent(
                    user_id=test_user.id,
                    event_type="api_call",
                    credits_used=20.0,
                    created_at=current_month_event_time,
                ),
            ]
        )
        await db_session.commit()

        response = await client.get("/v1/budgets")
        assert response.status_code == 200
        data = response.json()
        assert data["credits_used"] == 20.0
        assert data["credits_remaining"] == 80.0
        assert data["usage_percentage"] == 20.0


class TestGetUsageBreakdown:
    """Tests for GET /budgets/usage endpoint."""

    @pytest.mark.asyncio
    async def test_get_usage_breakdown_authenticated(self, client: AsyncClient):
        """Test getting usage breakdown as authenticated user."""
        response = await client.get("/v1/budgets/usage")
        assert response.status_code == 200
        data = response.json()
        assert "total_credits_used" in data
        assert "credits_remaining" in data
        assert "credits_total" in data
        assert "period_start" in data
        assert "period_end" in data
        assert "usage_by_agent" in data
        assert "usage_by_type" in data

    @pytest.mark.asyncio
    async def test_get_usage_breakdown_with_period(self, client: AsyncClient):
        """Test getting usage breakdown with period parameter."""
        response = await client.get("/v1/budgets/usage?period_start=7d")
        assert response.status_code == 200
        data = response.json()
        assert "period_start" in data
        assert "period_end" in data

    @pytest.mark.asyncio
    async def test_usage_breakdown_prefers_agent_id_from_metadata(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        test_agent,
    ):
        """Run-scoped usage should still roll up to the owning agent instead of a run UUID."""
        from src.api.models.models import UsageEvent

        db_session.add(
            UsageEvent(
                user_id=test_user.id,
                event_type="agent_run_created",
                resource_id="77777777-7777-4777-a777-777777777777",
                event_metadata=json.dumps({"agent_id": str(test_agent.id)}),
                credits_used=12.5,
            )
        )
        await db_session.commit()

        response = await client.get("/v1/budgets/usage?period_start=30d")
        assert response.status_code == 200
        data = response.json()
        usage_by_agent = data["usage_by_agent"]
        assert usage_by_agent[0]["agent_id"] == str(test_agent.id)
        assert usage_by_agent[0]["agent_name"] == test_agent.name
        assert usage_by_agent[0]["credits_used"] == 12.5

    @pytest.mark.asyncio
    async def test_usage_breakdown_never_resolves_a_foreign_agent_name(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        other_user,
    ):
        from src.api.models.models import Agent, AgentStatus, UsageEvent

        foreign_agent = Agent(
            name="confidential-foreign-agent",
            description="Another tenant's agent",
            config='{"model": "gpt-4"}',
            user_id=other_user.id,
            status=AgentStatus.CREATING,
        )
        db_session.add(foreign_agent)
        await db_session.flush()
        db_session.add(
            UsageEvent(
                user_id=test_user.id,
                event_type="agent_run_created",
                resource_id=str(foreign_agent.id),
                event_metadata=json.dumps({"agent_id": str(foreign_agent.id)}),
                credits_used=3.0,
            )
        )
        await db_session.commit()

        response = await client.get("/v1/budgets/usage?period_start=30d")

        assert response.status_code == 200
        entry = response.json()["usage_by_agent"][0]
        assert entry["agent_id"] == str(foreign_agent.id)
        assert entry["agent_name"].startswith("Unknown agent")
        assert "confidential" not in entry["agent_name"]
