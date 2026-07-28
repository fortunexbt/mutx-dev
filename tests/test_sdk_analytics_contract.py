"""Contract tests for sdk/mutx/analytics.py."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from sdk.mutx.analytics import (
    AgentMetricsSummary,
    Analytics,
    AnalyticsSummary,
    AnalyticsTimeSeries,
    TimeSeriesPoint,
)


# ---------------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------------


def _analytics_summary_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "total_agents": 5,
        "active_agents": 3,
        "total_deployments": 12,
        "active_deployments": 4,
        "total_runs": 1000,
        "successful_runs": 950,
        "failed_runs": 50,
        "total_api_calls": 50000,
        "avg_latency_ms": 234.5,
        "period_start": "2026-04-01T00:00:00",
        "period_end": "2026-04-03T00:00:00",
    }
    payload.update(overrides)
    return payload


def _agent_metrics_payload(agent_id: str = "agent-001", **overrides: Any) -> dict[str, Any]:
    payload = {
        "agent_id": agent_id,
        "agent_name": "test-agent",
        "total_runs": 200,
        "successful_runs": 190,
        "failed_runs": 10,
        "avg_cpu": 45.2,
        "avg_memory": 512.0,
        "total_requests": 5000,
        "avg_latency_ms": 120.0,
        "period_start": "2026-04-01T00:00:00",
        "period_end": "2026-04-03T00:00:00",
    }
    payload.update(overrides)
    return payload


def _timeseries_payload(
    metric: str = "runs", interval: str = "hour", **overrides: Any
) -> dict[str, Any]:
    payload = {
        "metric": metric,
        "interval": interval,
        "data": [
            {"timestamp": "2026-04-01T00:00:00", "value": 10.0},
            {"timestamp": "2026-04-01T01:00:00", "value": 15.0},
            {"timestamp": "2026-04-01T02:00:00", "value": 12.0},
        ],
        "period_start": "2026-04-01T00:00:00",
        "period_end": "2026-04-01T03:00:00",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# DTO parsing tests
# ---------------------------------------------------------------------------


class TestAnalyticsDTOs:
    def test_analytics_summary_parses_all_fields(self):
        payload = _analytics_summary_payload()
        summary = AnalyticsSummary(payload)

        assert summary.total_agents == 5
        assert summary.active_agents == 3
        assert summary.total_deployments == 12
        assert summary.active_deployments == 4
        assert summary.total_runs == 1000
        assert summary.successful_runs == 950
        assert summary.failed_runs == 50
        assert summary.total_api_calls == 50000
        assert summary.avg_latency_ms == 234.5
        assert isinstance(summary.period_start, datetime)
        assert isinstance(summary.period_end, datetime)

    def test_analytics_summary_repr(self):
        payload = _analytics_summary_payload()
        summary = AnalyticsSummary(payload)
        assert "AnalyticsSummary" in repr(summary)

    def test_analytics_summary_avg_latency_ms_defaults_to_zero(self):
        payload = _analytics_summary_payload()
        del payload["avg_latency_ms"]
        summary = AnalyticsSummary(payload)
        assert summary.avg_latency_ms == 0.0

    def test_agent_metrics_summary_parses_all_fields(self):
        payload = _agent_metrics_payload(agent_id="my-agent")
        metrics = AgentMetricsSummary(payload)

        assert metrics.agent_id == "my-agent"
        assert metrics.agent_name == "test-agent"
        assert metrics.total_runs == 200
        assert metrics.successful_runs == 190
        assert metrics.failed_runs == 10
        assert metrics.avg_cpu == 45.2
        assert metrics.avg_memory == 512.0
        assert metrics.total_requests == 5000
        assert metrics.avg_latency_ms == 120.0
        assert isinstance(metrics.period_start, datetime)
        assert isinstance(metrics.period_end, datetime)

    def test_agent_metrics_summary_optional_fields_can_be_none(self):
        payload = _agent_metrics_payload(avg_cpu=None, avg_memory=None, avg_latency_ms=None)
        metrics = AgentMetricsSummary(payload)
        assert metrics.avg_cpu is None
        assert metrics.avg_memory is None
        assert metrics.avg_latency_ms is None

    def test_timeseries_point_parses_timestamp_with_z_suffix(self):
        point = TimeSeriesPoint({"timestamp": "2026-04-01T12:00:00Z", "value": 5.0})
        assert isinstance(point.timestamp, datetime)
        assert point.value == 5.0

    def test_timeseries_point_parses_timestamp_iso_format(self):
        point = TimeSeriesPoint({"timestamp": "2026-04-01T12:00:00+00:00", "value": 7.0})
        assert isinstance(point.timestamp, datetime)
        assert point.value == 7.0

    def test_analytics_timeseries_parses_data_points(self):
        payload = _timeseries_payload()
        ts = AnalyticsTimeSeries(payload)

        assert ts.metric == "runs"
        assert ts.interval == "hour"
        assert len(ts.data) == 3
        assert all(isinstance(p, TimeSeriesPoint) for p in ts.data)
        assert all(isinstance(p.value, float) for p in ts.data)
        assert isinstance(ts.period_start, datetime)
        assert isinstance(ts.period_end, datetime)

    def test_analytics_timeseries_empty_data(self):
        payload = _timeseries_payload(data=[])
        ts = AnalyticsTimeSeries(payload)
        assert ts.data == []


# ---------------------------------------------------------------------------
# Sync method contract tests
# ---------------------------------------------------------------------------


class TestAnalyticsSyncMethods:
    """Tests for sync Analytics methods using httpx.MockTransport."""

    def _client(self, handler):
        return httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))

    def test_get_summary_success(self):
        payload = _analytics_summary_payload()

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/analytics/summary"
            return httpx.Response(200, json=payload)

        analytics = Analytics(self._client(handler))
        result = analytics.get_summary()

        assert isinstance(result, AnalyticsSummary)
        assert result.total_agents == 5

    def test_get_summary_with_period_params(self):
        captured_params = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_params.update(dict(request.url.params))
            return httpx.Response(200, json=_analytics_summary_payload())

        analytics = Analytics(self._client(handler))
        analytics.get_summary(period_start="7d", period_end="now")

        assert captured_params["period_start"] == "7d"
        assert captured_params["period_end"] == "now"

    def test_get_agent_summary_success(self):
        payload = _agent_metrics_payload(agent_id="agent-xyz")

        def handler(request: httpx.Request) -> httpx.Response:
            assert "/analytics/agents/agent-xyz/summary" in request.url.path
            return httpx.Response(200, json=payload)

        analytics = Analytics(self._client(handler))
        result = analytics.get_agent_summary("agent-xyz")

        assert isinstance(result, AgentMetricsSummary)
        assert result.agent_id == "agent-xyz"

    def test_get_agent_summary_with_period_params(self):
        captured_params = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_params.update(dict(request.url.params))
            return httpx.Response(200, json=_agent_metrics_payload("test-agent"))

        analytics = Analytics(self._client(handler))
        analytics.get_agent_summary("test-agent", period_start="30d")

        assert captured_params["period_start"] == "30d"

    def test_get_timeseries_success(self):
        payload = _timeseries_payload(metric="api_calls", interval="day")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/analytics/timeseries"
            return httpx.Response(200, json=payload)

        analytics = Analytics(self._client(handler))
        result = analytics.get_timeseries(metric="api_calls", interval="day")

        assert isinstance(result, AnalyticsTimeSeries)
        assert result.metric == "api_calls"
        assert result.interval == "day"

    def test_get_timeseries_with_agent_id_filter(self):
        captured_params = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_params.update(dict(request.url.params))
            return httpx.Response(200, json=_timeseries_payload())

        analytics = Analytics(self._client(handler))
        analytics.get_timeseries(metric="runs", agent_id="my-agent")

        assert captured_params["agent_id"] == "my-agent"

    def test_get_costs_success(self):
        costs_payload = {
            "total_cost": 123.45,
            "breakdown": {"api": 100.0, "compute": 23.45},
            "currency": "USD",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/analytics/costs"
            return httpx.Response(200, json=costs_payload)

        analytics = Analytics(self._client(handler))
        result = analytics.get_costs()

        assert isinstance(result, dict)
        assert result["total_cost"] == 123.45

    def test_get_costs_with_period_params(self):
        captured_params = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_params.update(dict(request.url.params))
            return httpx.Response(200, json={"total_cost": 0.0, "breakdown": {}})

        analytics = Analytics(self._client(handler))
        analytics.get_costs(period_start="24h", period_end="now")

        assert captured_params["period_start"] == "24h"
        assert captured_params["period_end"] == "now"

    def test_get_budget_success(self):
        budget_payload = {
            "budget_limit": 1000.0,
            "spent": 345.67,
            "remaining": 654.33,
            "currency": "USD",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/analytics/budget"
            return httpx.Response(200, json=budget_payload)

        analytics = Analytics(self._client(handler))
        result = analytics.get_budget()

        assert isinstance(result, dict)
        assert result["budget_limit"] == 1000.0
        assert result["remaining"] == 654.33

    def test_sync_methods_raise_on_async_client(self):
        async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
        analytics = Analytics(async_client)

        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            analytics.get_summary()

        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            analytics.get_agent_summary("agent-001")

        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            analytics.get_timeseries("runs")

        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            analytics.get_costs()

        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            analytics.get_budget()


# ---------------------------------------------------------------------------
# Async method contract tests
# ---------------------------------------------------------------------------


class TestAnalyticsAsyncMethods:
    """Tests for async Analytics methods using AsyncMock."""

    def _async_client(self, mock_response: MagicMock) -> httpx.AsyncClient:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_response
        client.post.return_value = mock_response
        return client

    @pytest.mark.asyncio
    async def test_aget_summary_success(self):
        payload = _analytics_summary_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = payload

        client = self._async_client(mock_response)
        analytics = Analytics(client)

        result = await analytics.aget_summary()

        assert isinstance(result, AnalyticsSummary)
        assert result.total_runs == 1000
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_agent_summary_success(self):
        payload = _agent_metrics_payload(agent_id="async-agent")
        mock_response = MagicMock()
        mock_response.json.return_value = payload

        client = self._async_client(mock_response)
        analytics = Analytics(client)

        result = await analytics.aget_agent_summary("async-agent")

        assert isinstance(result, AgentMetricsSummary)
        assert result.agent_id == "async-agent"
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_timeseries_success(self):
        payload = _timeseries_payload(metric="latency", interval="minute")
        mock_response = MagicMock()
        mock_response.json.return_value = payload

        client = self._async_client(mock_response)
        analytics = Analytics(client)

        result = await analytics.aget_timeseries(metric="latency", interval="minute")

        assert isinstance(result, AnalyticsTimeSeries)
        assert result.metric == "latency"
        assert result.interval == "minute"

    @pytest.mark.asyncio
    async def test_aget_costs_success(self):
        costs_payload = {"total_cost": 99.99, "breakdown": {"api": 99.99}}
        mock_response = MagicMock()
        mock_response.json.return_value = costs_payload

        client = self._async_client(mock_response)
        analytics = Analytics(client)

        result = await analytics.aget_costs()

        assert isinstance(result, dict)
        assert result["total_cost"] == 99.99
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_budget_success(self):
        budget_payload = {"budget_limit": 500.0, "spent": 100.0, "remaining": 400.0}
        mock_response = MagicMock()
        mock_response.json.return_value = budget_payload

        client = self._async_client(mock_response)
        analytics = Analytics(client)

        result = await analytics.aget_budget()

        assert isinstance(result, dict)
        assert result["budget_limit"] == 500.0
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_methods_raise_on_sync_client(self):
        sync_client = httpx.Client(base_url="https://api.test/v1/")
        analytics = Analytics(sync_client)

        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await analytics.aget_summary()

        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await analytics.aget_agent_summary("agent-001")

        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await analytics.aget_timeseries("runs")

        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await analytics.aget_costs()

        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await analytics.aget_budget()
