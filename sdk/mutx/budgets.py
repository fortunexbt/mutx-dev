"""Budgets API SDK - /budgets endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import httpx


class Budget:
    """Represents a user's budget/credits."""

    def __init__(self, data: dict[str, Any]):
        self.user_id: str = data["user_id"]
        self.plan: str = data["plan"]
        self.credits_total: float = data["credits_total"]
        self.credits_used: float = data["credits_used"]
        self.credits_remaining: float = data["credits_remaining"]
        self.reset_date: datetime = datetime.fromisoformat(data["reset_date"])
        self.usage_percentage: float = data["usage_percentage"]
        self._data = data

    def __repr__(self) -> str:
        return f"Budget(plan={self.plan}, remaining={self.credits_remaining}/{self.credits_total})"


class UsageByAgent:
    """Usage breakdown by agent."""

    def __init__(self, data: dict[str, Any]):
        self.agent_id: str = data["agent_id"]
        self.agent_name: str = data["agent_name"]
        self.credits_used: float = data["credits_used"]
        self.event_count: int = data["event_count"]
        self._data = data


class UsageByType:
    """Usage breakdown by event type."""

    def __init__(self, data: dict[str, Any]):
        self.event_type: str = data["event_type"]
        self.credits_used: float = data["credits_used"]
        self.event_count: int = data["event_count"]
        self._data = data


class UsageBreakdown:
    """Detailed usage breakdown response."""

    def __init__(self, data: dict[str, Any]):
        self.total_credits_used: float = data["total_credits_used"]
        self.credits_remaining: float = data["credits_remaining"]
        self.credits_total: float = data["credits_total"]
        self.period_start: datetime = datetime.fromisoformat(data["period_start"])
        self.period_end: datetime = datetime.fromisoformat(data["period_end"])
        self.usage_by_agent: list[UsageByAgent] = [
            UsageByAgent(a) for a in data.get("usage_by_agent", [])
        ]
        self.usage_by_type: list[UsageByType] = [
            UsageByType(t) for t in data.get("usage_by_type", [])
        ]
        self._data = data


class Budgets:
    """SDK resource for /budgets endpoints."""

    def __init__(self, client: httpx.Client | httpx.AsyncClient):
        self._client = client

    def _require_sync_client(self) -> None:
        if isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError(
                "This resource requires a sync httpx.Client. For async clients, use the `a*` methods."
            )

    def _require_async_client(self) -> None:
        if not isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError(
                "This async resource helper requires an async httpx.AsyncClient and an `a*` method call."
            )

    def get(self) -> Budget:
        """Get current user's budget and credits."""
        self._require_sync_client()
        response = self._client.get("budgets")
        response.raise_for_status()
        return Budget(response.json())

    async def aget(self) -> Budget:
        """Get current user's budget and credits (async)."""
        self._require_async_client()
        response = await self._client.get("budgets")
        response.raise_for_status()
        return Budget(response.json())

    def get_usage(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> UsageBreakdown:
        """Get detailed usage breakdown by agent and event type.

        Args:
            period_start: ISO datetime or "24h", "7d", "30d"
            period_end: ISO datetime or "24h", "7d", "30d"
        """
        self._require_sync_client()
        params: dict[str, Any] = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        response = self._client.get("budgets/usage", params=params)
        response.raise_for_status()
        return UsageBreakdown(response.json())

    async def aget_usage(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> UsageBreakdown:
        """Get detailed usage breakdown (async)."""
        self._require_async_client()
        params: dict[str, Any] = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        response = await self._client.get("budgets/usage", params=params)
        response.raise_for_status()
        return UsageBreakdown(response.json())
