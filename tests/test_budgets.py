"""Contract tests for sdk/mutx/budgets.py."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from sdk.mutx.budgets import Budget, Budgets, UsageByAgent, UsageByType, UsageBreakdown
from tests.sdk_contract_utils import assert_v1_request


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_budget_data() -> dict:
    return {
        "user_id": "user-123",
        "plan": "pro",
        "credits_total": 1000.0,
        "credits_used": 250.0,
        "credits_remaining": 750.0,
        "reset_date": "2026-05-01T00:00:00",
        "usage_percentage": 25.0,
    }


@pytest.fixture
def usage_by_agent_data() -> dict:
    return {
        "agent_id": "agent-abc",
        "agent_name": "claude-opus",
        "credits_used": 150.0,
        "event_count": 42,
    }


@pytest.fixture
def usage_by_type_data() -> dict:
    return {
        "event_type": "chat",
        "credits_used": 100.0,
        "event_count": 30,
    }


@pytest.fixture
def usage_breakdown_data(usage_by_agent_data, usage_by_type_data) -> dict:
    return {
        "total_credits_used": 250.0,
        "credits_remaining": 750.0,
        "credits_total": 1000.0,
        "period_start": "2026-04-01T00:00:00",
        "period_end": "2026-04-30T23:59:59",
        "usage_by_agent": [usage_by_agent_data],
        "usage_by_type": [usage_by_type_data],
    }


# ---------------------------------------------------------------------------
# Data class parsing
# ---------------------------------------------------------------------------


class TestBudgetParsing:
    def test_required_fields(self, minimal_budget_data):
        budget = Budget(minimal_budget_data)
        assert budget.user_id == "user-123"
        assert budget.plan == "pro"
        assert budget.credits_total == 1000.0
        assert budget.credits_used == 250.0
        assert budget.credits_remaining == 750.0
        assert isinstance(budget.reset_date, datetime)
        assert budget.reset_date.year == 2026
        assert budget.reset_date.month == 5
        assert budget.reset_date.day == 1
        assert budget.usage_percentage == 25.0

    def test_repr(self, minimal_budget_data):
        budget = Budget(minimal_budget_data)
        r = repr(budget)
        assert "pro" in r
        assert "750.0" in r
        assert "1000.0" in r

    def test_raw_data_preserved(self, minimal_budget_data):
        budget = Budget(minimal_budget_data)
        assert budget._data is minimal_budget_data


class TestUsageByAgentParsing:
    def test_fields(self, usage_by_agent_data):
        uba = UsageByAgent(usage_by_agent_data)
        assert uba.agent_id == "agent-abc"
        assert uba.agent_name == "claude-opus"
        assert uba.credits_used == 150.0
        assert uba.event_count == 42

    def test_raw_data_preserved(self, usage_by_agent_data):
        uba = UsageByAgent(usage_by_agent_data)
        assert uba._data is usage_by_agent_data


class TestUsageByTypeParsing:
    def test_fields(self, usage_by_type_data):
        ubt = UsageByType(usage_by_type_data)
        assert ubt.event_type == "chat"
        assert ubt.credits_used == 100.0
        assert ubt.event_count == 30

    def test_raw_data_preserved(self, usage_by_type_data):
        ubt = UsageByType(usage_by_type_data)
        assert ubt._data is usage_by_type_data


class TestUsageBreakdownParsing:
    def test_required_fields(self, usage_breakdown_data):
        ub = UsageBreakdown(usage_breakdown_data)
        assert ub.total_credits_used == 250.0
        assert ub.credits_remaining == 750.0
        assert ub.credits_total == 1000.0
        assert isinstance(ub.period_start, datetime)
        assert isinstance(ub.period_end, datetime)

    def test_nested_lists(self, usage_breakdown_data):
        ub = UsageBreakdown(usage_breakdown_data)
        assert len(ub.usage_by_agent) == 1
        assert isinstance(ub.usage_by_agent[0], UsageByAgent)
        assert ub.usage_by_agent[0].agent_id == "agent-abc"
        assert len(ub.usage_by_type) == 1
        assert isinstance(ub.usage_by_type[0], UsageByType)
        assert ub.usage_by_type[0].event_type == "chat"

    def test_empty_nested_lists(self):
        data = {
            "total_credits_used": 0.0,
            "credits_remaining": 1000.0,
            "credits_total": 1000.0,
            "period_start": "2026-04-01T00:00:00",
            "period_end": "2026-04-30T23:59:59",
            "usage_by_agent": [],
            "usage_by_type": [],
        }
        ub = UsageBreakdown(data)
        assert ub.usage_by_agent == []
        assert ub.usage_by_type == []

    def test_raw_data_preserved(self, usage_breakdown_data):
        ub = UsageBreakdown(usage_breakdown_data)
        assert ub._data is usage_breakdown_data


# ---------------------------------------------------------------------------
# Type guards
# ---------------------------------------------------------------------------


class TestSyncClientTypeGuard:
    def test_sync_method_raises_on_async_client(self, minimal_budget_data):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        budgets = Budgets(mock_client)
        with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
            budgets.get()


class TestAsyncClientTypeGuard:
    @pytest.mark.asyncio
    async def test_async_method_raises_on_sync_client(self, minimal_budget_data):
        mock_client = MagicMock(spec=httpx.Client)
        budgets = Budgets(mock_client)
        with pytest.raises(RuntimeError, match="requires an async httpx.AsyncClient"):
            await budgets.aget()


# ---------------------------------------------------------------------------
# Sync methods
# ---------------------------------------------------------------------------


class TestBudgetsSyncGet:
    def test_get_success(self, minimal_budget_data):
        mock_response = MagicMock()
        mock_response.json.return_value = minimal_budget_data
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        budgets = Budgets(mock_client)

        result = budgets.get()

        assert isinstance(result, Budget)
        assert result.user_id == "user-123"
        assert_v1_request(mock_client.get, "GET", "/v1/budgets")
        mock_response.raise_for_status.assert_called_once()

    def test_get_raises_for_status(self, minimal_budget_data):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        budgets = Budgets(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            budgets.get()


class TestBudgetsSyncGetUsage:
    def test_get_usage_no_params(self, usage_breakdown_data):
        mock_response = MagicMock()
        mock_response.json.return_value = usage_breakdown_data
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        budgets = Budgets(mock_client)

        result = budgets.get_usage()

        assert isinstance(result, UsageBreakdown)
        request = assert_v1_request(mock_client.get, "GET", "/v1/budgets/usage")
        assert dict(request.url.params) == {}

    def test_get_usage_with_period_params(self, usage_breakdown_data):
        mock_response = MagicMock()
        mock_response.json.return_value = usage_breakdown_data
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        budgets = Budgets(mock_client)

        result = budgets.get_usage(period_start="24h", period_end="7d")

        assert isinstance(result, UsageBreakdown)
        request = assert_v1_request(mock_client.get, "GET", "/v1/budgets/usage")
        assert dict(request.url.params) == {"period_start": "24h", "period_end": "7d"}

    def test_get_usage_raises_for_status(self, usage_breakdown_data):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        budgets = Budgets(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            budgets.get_usage()


# ---------------------------------------------------------------------------
# Async methods
# ---------------------------------------------------------------------------


class TestBudgetsAsyncGet:
    @pytest.mark.asyncio
    async def test_aget_success(self, minimal_budget_data):
        mock_response = MagicMock()
        mock_response.json.return_value = minimal_budget_data
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        budgets = Budgets(mock_client)

        result = await budgets.aget()

        assert isinstance(result, Budget)
        assert result.user_id == "user-123"
        assert_v1_request(mock_client.get, "GET", "/v1/budgets")
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_raises_for_status(self, minimal_budget_data):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        budgets = Budgets(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            await budgets.aget()


class TestBudgetsAsyncGetUsage:
    @pytest.mark.asyncio
    async def test_aget_usage_no_params(self, usage_breakdown_data):
        mock_response = MagicMock()
        mock_response.json.return_value = usage_breakdown_data
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        budgets = Budgets(mock_client)

        result = await budgets.aget_usage()

        assert isinstance(result, UsageBreakdown)
        request = assert_v1_request(mock_client.get, "GET", "/v1/budgets/usage")
        assert dict(request.url.params) == {}

    @pytest.mark.asyncio
    async def test_aget_usage_with_period_params(self, usage_breakdown_data):
        mock_response = MagicMock()
        mock_response.json.return_value = usage_breakdown_data
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        budgets = Budgets(mock_client)

        result = await budgets.aget_usage(period_start="30d", period_end="now")

        assert isinstance(result, UsageBreakdown)
        request = assert_v1_request(mock_client.get, "GET", "/v1/budgets/usage")
        assert dict(request.url.params) == {"period_start": "30d", "period_end": "now"}

    @pytest.mark.asyncio
    async def test_aget_usage_raises_for_status(self, usage_breakdown_data):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        budgets = Budgets(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            await budgets.aget_usage()
