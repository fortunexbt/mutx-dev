"""Analytics API SDK - /analytics endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import httpx

from mutx._http import api_path


class AnalyticsSummary:
    """Analytics summary for a time period."""

    def __init__(self, data: dict[str, Any]):
        self.total_agents: int = data["total_agents"]
        self.active_agents: int = data["active_agents"]
        self.total_deployments: int = data["total_deployments"]
        self.active_deployments: int = data["active_deployments"]
        self.total_runs: int = data["total_runs"]
        self.successful_runs: int = data["successful_runs"]
        self.failed_runs: int = data["failed_runs"]
        self.total_api_calls: int = data["total_api_calls"]
        self.avg_latency_ms: float = data.get("avg_latency_ms", 0.0)
        self.period_start: datetime = datetime.fromisoformat(data["period_start"])
        self.period_end: datetime = datetime.fromisoformat(data["period_end"])
        self._data = data

    def __repr__(self) -> str:
        return (
            f"AnalyticsSummary(agents={self.total_agents}, "
            f"deployments={self.total_deployments}, runs={self.total_runs})"
        )


class AgentMetricsSummary:
    """Metrics summary for a specific agent."""

    def __init__(self, data: dict[str, Any]):
        self.agent_id: str = data["agent_id"]
        self.agent_name: str = data["agent_name"]
        self.total_runs: int = data["total_runs"]
        self.successful_runs: int = data["successful_runs"]
        self.failed_runs: int = data["failed_runs"]
        self.avg_cpu: Optional[float] = data.get("avg_cpu")
        self.avg_memory: Optional[float] = data.get("avg_memory")
        self.total_requests: int = data.get("total_requests", 0)
        self.avg_latency_ms: Optional[float] = data.get("avg_latency_ms")
        self.period_start: datetime = datetime.fromisoformat(data["period_start"])
        self.period_end: datetime = datetime.fromisoformat(data["period_end"])
        self._data = data


class TimeSeriesPoint:
    """Single point in a time series."""

    def __init__(self, data: dict[str, Any]):
        self.timestamp: datetime = datetime.fromisoformat(
            data["timestamp"].replace("Z", "+00:00")
            if isinstance(data["timestamp"], str)
            else data["timestamp"]
        )
        self.value: float = data["value"]
        self._data = data


class AnalyticsTimeSeries:
    """Time series data for a metric."""

    def __init__(self, data: dict[str, Any]):
        self.metric: str = data["metric"]
        self.interval: str = data["interval"]
        self.data: list[TimeSeriesPoint] = [TimeSeriesPoint(p) for p in data.get("data", [])]
        self.period_start: datetime = datetime.fromisoformat(data["period_start"])
        self.period_end: datetime = datetime.fromisoformat(data["period_end"])
        self._data = data


class Analytics:
    """SDK resource for /analytics endpoints."""

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

    def get_summary(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> AnalyticsSummary:
        """Get analytics summary for the current user.

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
        response = self._client.get("analytics/summary", params=params)
        response.raise_for_status()
        return AnalyticsSummary(response.json())

    async def aget_summary(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> AnalyticsSummary:
        """Get analytics summary (async)."""
        self._require_async_client()
        params: dict[str, Any] = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        response = await self._client.get("analytics/summary", params=params)
        response.raise_for_status()
        return AnalyticsSummary(response.json())

    def get_agent_summary(
        self,
        agent_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> AgentMetricsSummary:
        """Get metrics summary for a specific agent."""
        self._require_sync_client()
        params: dict[str, Any] = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        response = self._client.get(
            api_path("analytics/agents/{agent_id}/summary", agent_id=agent_id), params=params
        )
        response.raise_for_status()
        return AgentMetricsSummary(response.json())

    async def aget_agent_summary(
        self,
        agent_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> AgentMetricsSummary:
        """Get metrics summary for a specific agent (async)."""
        self._require_async_client()
        params: dict[str, Any] = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        response = await self._client.get(
            api_path("analytics/agents/{agent_id}/summary", agent_id=agent_id), params=params
        )
        response.raise_for_status()
        return AgentMetricsSummary(response.json())

    def get_timeseries(
        self,
        metric: str,
        interval: str = "hour",
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> AnalyticsTimeSeries:
        """Get time series data for a metric.

        Args:
            metric: Metric type (runs, api_calls, latency)
            interval: Time bucket interval (hour, day, minute)
            period_start: ISO datetime or "24h", "7d", "30d"
            period_end: ISO datetime or "24h", "7d", "30d"
            agent_id: Optional agent ID to filter by
        """
        self._require_sync_client()
        params: dict[str, Any] = {
            "metric": metric,
            "interval": interval,
        }
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        if agent_id:
            params["agent_id"] = str(agent_id)

        response = self._client.get("analytics/timeseries", params=params)
        response.raise_for_status()
        return AnalyticsTimeSeries(response.json())

    async def aget_timeseries(
        self,
        metric: str,
        interval: str = "hour",
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> AnalyticsTimeSeries:
        """Get time series data (async)."""
        self._require_async_client()
        params: dict[str, Any] = {
            "metric": metric,
            "interval": interval,
        }
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        if agent_id:
            params["agent_id"] = str(agent_id)

        response = await self._client.get("analytics/timeseries", params=params)
        response.raise_for_status()
        return AnalyticsTimeSeries(response.json())

    def get_costs(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get cost summary for the current user."""
        self._require_sync_client()
        params: dict[str, Any] = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        response = self._client.get("analytics/costs", params=params)
        response.raise_for_status()
        return response.json()

    async def aget_costs(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get cost summary (async)."""
        self._require_async_client()
        params: dict[str, Any] = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        response = await self._client.get("analytics/costs", params=params)
        response.raise_for_status()
        return response.json()

    def get_budget(self) -> dict[str, Any]:
        """Get current budget information."""
        self._require_sync_client()
        response = self._client.get("analytics/budget")
        response.raise_for_status()
        return response.json()

    async def aget_budget(self) -> dict[str, Any]:
        """Get current budget information (async)."""
        self._require_async_client()
        response = await self._client.get("analytics/budget")
        response.raise_for_status()
        return response.json()
