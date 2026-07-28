"""Contract tests for sdk/mutx/budgets.py — no API keys needed."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import httpx
import pytest

from mutx.budgets import Budget, UsageByAgent, UsageByType, UsageBreakdown, Budgets


def _budget_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "user_id": str(uuid.uuid4()),
        "plan": "pro",
        "credits_total": 1000.0,
        "credits_used": 250.0,
        "credits_remaining": 750.0,
        "reset_date": "2026-04-01T00:00:00+00:00",
        "usage_percentage": 25.0,
    }
    payload.update(overrides)
    return payload


def _usage_breakdown_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "total_credits_used": 250.0,
        "credits_remaining": 750.0,
        "credits_total": 1000.0,
        "period_start": "2026-03-01T00:00:00+00:00",
        "period_end": "2026-03-31T23:59:59+00:00",
        "usage_by_agent": [
            {
                "agent_id": str(uuid.uuid4()),
                "agent_name": "cipher-alpha",
                "credits_used": 150.0,
                "event_count": 42,
            },
            {
                "agent_id": str(uuid.uuid4()),
                "agent_name": "swarm-beta",
                "credits_used": 100.0,
                "event_count": 28,
            },
        ],
        "usage_by_type": [
            {
                "event_type": "api_call",
                "credits_used": 180.0,
                "event_count": 55,
            },
            {
                "event_type": "starter_deployment_create",
                "credits_used": 70.0,
                "event_count": 15,
            },
        ],
    }
    payload.update(overrides)
    return payload


# -----------------------------------------------------------------
# Budget dataclass
# -----------------------------------------------------------------


def test_budget_parses_required_fields() -> None:
    raw = _budget_payload()
    budget = Budget(raw)

    assert budget.user_id == raw["user_id"]
    assert budget.plan == "pro"
    assert budget.credits_total == 1000.0
    assert budget.credits_used == 250.0
    assert budget.credits_remaining == 750.0
    assert budget.reset_date == datetime.fromisoformat(raw["reset_date"])
    assert budget.usage_percentage == 25.0


def test_budget_repr() -> None:
    raw = _budget_payload()
    budget = Budget(raw)
    assert "Budget" in repr(budget)
    assert "pro" in repr(budget)


def test_budget_data_attribute() -> None:
    raw = _budget_payload(plan="starter")
    budget = Budget(raw)
    assert budget._data["plan"] == "starter"


# -----------------------------------------------------------------
# UsageByAgent dataclass
# -----------------------------------------------------------------


def test_usage_by_agent_parses_fields() -> None:
    raw = {
        "agent_id": str(uuid.uuid4()),
        "agent_name": "cipher-alpha",
        "credits_used": 150.0,
        "event_count": 42,
    }
    agent = UsageByAgent(raw)

    assert agent.agent_id == raw["agent_id"]
    assert agent.agent_name == "cipher-alpha"
    assert agent.credits_used == 150.0
    assert agent.event_count == 42
    assert agent._data == raw


# -----------------------------------------------------------------
# UsageByType dataclass
# -----------------------------------------------------------------


def test_usage_by_type_parses_fields() -> None:
    raw = {
        "event_type": "api_call",
        "credits_used": 180.0,
        "event_count": 55,
    }
    usage_type = UsageByType(raw)

    assert usage_type.event_type == "api_call"
    assert usage_type.credits_used == 180.0
    assert usage_type.event_count == 55
    assert usage_type._data == raw


# -----------------------------------------------------------------
# UsageBreakdown dataclass
# -----------------------------------------------------------------


def test_usage_breakdown_parses_fields() -> None:
    raw = _usage_breakdown_payload()
    breakdown = UsageBreakdown(raw)

    assert breakdown.total_credits_used == 250.0
    assert breakdown.credits_remaining == 750.0
    assert breakdown.credits_total == 1000.0
    assert breakdown.period_start == datetime.fromisoformat(raw["period_start"])
    assert breakdown.period_end == datetime.fromisoformat(raw["period_end"])


def test_usage_breakdown_nested_agents() -> None:
    raw = _usage_breakdown_payload()
    breakdown = UsageBreakdown(raw)

    assert len(breakdown.usage_by_agent) == 2
    assert all(isinstance(a, UsageByAgent) for a in breakdown.usage_by_agent)
    assert breakdown.usage_by_agent[0].agent_name == "cipher-alpha"
    assert breakdown.usage_by_agent[1].agent_name == "swarm-beta"


def test_usage_breakdown_nested_types() -> None:
    raw = _usage_breakdown_payload()
    breakdown = UsageBreakdown(raw)

    assert len(breakdown.usage_by_type) == 2
    assert all(isinstance(t, UsageByType) for t in breakdown.usage_by_type)
    assert breakdown.usage_by_type[0].event_type == "api_call"
    assert breakdown.usage_by_type[1].event_type == "starter_deployment_create"


def test_usage_breakdown_empty_nested() -> None:
    raw = _usage_breakdown_payload(usage_by_agent=[], usage_by_type=[])
    breakdown = UsageBreakdown(raw)

    assert breakdown.usage_by_agent == []
    assert breakdown.usage_by_type == []


# -----------------------------------------------------------------
# Budgets.get
# -----------------------------------------------------------------


def test_get_returns_budget() -> None:
    raw = _budget_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/budgets"
        return httpx.Response(200, json=raw)

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    budgets = Budgets(client)

    result = budgets.get()

    assert isinstance(result, Budget)
    assert result.plan == "pro"
    assert result.credits_remaining == 750.0


def test_get_parses_all_fields() -> None:
    raw = _budget_payload(
        plan="enterprise",
        credits_total=5000.0,
        credits_used=1234.5,
        credits_remaining=3765.5,
        usage_percentage=24.69,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    budgets = Budgets(client)

    result = budgets.get()

    assert result.plan == "enterprise"
    assert result.credits_total == 5000.0
    assert result.credits_used == 1234.5
    assert result.credits_remaining == 3765.5
    assert result.usage_percentage == 24.69


# -----------------------------------------------------------------
# Budgets.aget
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_aget_returns_budget() -> None:
    raw = _budget_payload(plan="starter")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/budgets"
        return httpx.Response(200, json=raw)

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        budgets = Budgets(client)
        result = await budgets.aget()

    assert isinstance(result, Budget)
    assert result.plan == "starter"


# -----------------------------------------------------------------
# Budgets.get_usage
# -----------------------------------------------------------------


def test_get_usage_returns_usage_breakdown() -> None:
    raw = _usage_breakdown_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/budgets/usage"
        return httpx.Response(200, json=raw)

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    budgets = Budgets(client)

    result = budgets.get_usage()

    assert isinstance(result, UsageBreakdown)
    assert result.total_credits_used == 250.0
    assert len(result.usage_by_agent) == 2
    assert len(result.usage_by_type) == 2


def test_get_usage_passes_period_params() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_usage_breakdown_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    budgets = Budgets(client)

    budgets.get_usage(period_start="7d", period_end="24h")

    assert captured["params"]["period_start"] == "7d"
    assert captured["params"]["period_end"] == "24h"


def test_get_usage_handles_no_params() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_usage_breakdown_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    budgets = Budgets(client)

    budgets.get_usage()

    assert "period_start" not in captured["params"]
    assert "period_end" not in captured["params"]


# -----------------------------------------------------------------
# Budgets.aget_usage
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_aget_usage_returns_usage_breakdown() -> None:
    raw = _usage_breakdown_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        budgets = Budgets(client)
        result = await budgets.aget_usage(period_start="30d")

    assert isinstance(result, UsageBreakdown)
    assert result.total_credits_used == 250.0


@pytest.mark.asyncio
async def test_aget_usage_passes_period_params() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_usage_breakdown_payload())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        budgets = Budgets(client)
        await budgets.aget_usage(period_start="24h", period_end="now")

    assert captured["params"]["period_start"] == "24h"
    assert captured["params"]["period_end"] == "now"


# -----------------------------------------------------------------
# Sync client required enforcement
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_rejects_async_client() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_budget_payload())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        budgets = Budgets(client)
        with pytest.raises(RuntimeError, match="sync"):
            budgets.get()


@pytest.mark.asyncio
async def test_get_usage_rejects_async_client() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_usage_breakdown_payload())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        budgets = Budgets(client)
        with pytest.raises(RuntimeError, match="sync"):
            budgets.get_usage()


# -----------------------------------------------------------------
# Async client required enforcement
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_aget_rejects_sync_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_budget_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    budgets = Budgets(client)
    with pytest.raises(RuntimeError, match="async"):
        await budgets.aget()


@pytest.mark.asyncio
async def test_aget_usage_rejects_sync_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_usage_breakdown_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    budgets = Budgets(client)
    with pytest.raises(RuntimeError, match="async"):
        await budgets.aget_usage()
