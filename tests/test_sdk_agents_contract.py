"""Contract tests for sdk/mutx/agents.py."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from sdk.mutx.agents import (
    Agent,
    AgentDetail,
    AgentLog,
    AgentMetric,
    Agents,
    Deployment,
    DeploymentEvent,
)
from tests.sdk_contract_utils import assert_v1_request


# ---------------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------------


def _agent_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "test-agent",
        "description": "A test agent",
        "status": "active",
        "config": '{"model": "gpt-4"}',
        "created_at": "2026-04-03T01:00:00+00:00",
        "updated_at": "2026-04-03T02:00:00+00:00",
        "user_id": "user-001",
    }
    payload.update(overrides)
    return payload


def _deployment_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "660e8400-e29b-41d4-a716-446655440001",
        "agent_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "running",
        "replicas": 2,
        "node_id": "node-abc",
        "started_at": "2026-04-03T01:30:00+00:00",
        "ended_at": None,
        "error_message": None,
        "events": [],
    }
    payload.update(overrides)
    return payload


def _deployment_event_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "770e8400-e29b-41d4-a716-446655440002",
        "deployment_id": "660e8400-e29b-41d4-a716-446655440001",
        "event_type": "scaling",
        "status": "completed",
        "node_id": "node-abc",
        "error_message": None,
        "created_at": "2026-04-03T01:35:00+00:00",
    }
    payload.update(overrides)
    return payload


def _agent_log_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "880e8400-e29b-41d4-a716-446655440003",
        "agent_id": "550e8400-e29b-41d4-a716-446655440000",
        "level": "INFO",
        "message": "Agent started successfully",
        "timestamp": "2026-04-03T01:05:00+00:00",
        "extra_data": {"key": "value"},
        "metadata": {"key": "value"},
    }
    payload.update(overrides)
    return payload


def _agent_metric_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "990e8400-e29b-41d4-a716-446655440004",
        "agent_id": "550e8400-e29b-41d4-a716-446655440000",
        "cpu_usage": 45.5,
        "memory_usage": 1024,
        "timestamp": "2026-04-03T01:10:00+00:00",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Data class tests: Agent
# ---------------------------------------------------------------------------


class TestAgent:
    def test_agent_parsed_fields(self):
        payload = _agent_payload()
        agent = Agent(payload)

        assert agent.id == UUID("550e8400-e29b-41d4-a716-446655440000")
        assert agent.name == "test-agent"
        assert agent.description == "A test agent"
        assert agent.status == "active"
        assert agent.config == {"model": "gpt-4"}
        assert agent.created_at == datetime.fromisoformat("2026-04-03T01:00:00+00:00")
        assert agent.updated_at == datetime.fromisoformat("2026-04-03T02:00:00+00:00")
        assert agent.user_id == "user-001"

    def test_agent_config_parsed_from_json_string(self):
        payload = _agent_payload(config='{"temperature": 0.7, "max_tokens": 1000}')
        agent = Agent(payload)

        assert agent.config == {"temperature": 0.7, "max_tokens": 1000}

    def test_agent_config_returns_raw_if_not_string(self):
        raw_config = {"model": "claude-3"}
        payload = _agent_payload(config=raw_config)
        agent = Agent(payload)

        assert agent.config == raw_config

    def test_agent_config_returns_raw_if_invalid_json(self):
        payload = _agent_payload(config="not valid json {")
        agent = Agent(payload)

        assert agent.config == "not valid json {"

    def test_agent_optional_fields_missing(self):
        payload = _agent_payload()
        del payload["description"]
        del payload["config"]
        del payload["user_id"]
        agent = Agent(payload)

        assert agent.description is None
        assert agent.config is None
        assert agent.user_id is None

    def test_agent_repr(self):
        payload = _agent_payload()
        agent = Agent(payload)

        repr_str = repr(agent)
        assert "Agent" in repr_str
        assert "test-agent" in repr_str
        assert "active" in repr_str


# ---------------------------------------------------------------------------
# Data class tests: DeploymentEvent
# ---------------------------------------------------------------------------


class TestDeploymentEvent:
    def test_deployment_event_fields(self):
        payload = _deployment_event_payload()
        event = DeploymentEvent(payload)

        assert event.id == UUID("770e8400-e29b-41d4-a716-446655440002")
        assert event.deployment_id == UUID("660e8400-e29b-41d4-a716-446655440001")
        assert event.event_type == "scaling"
        assert event.status == "completed"
        assert event.node_id == "node-abc"
        assert event.error_message is None
        assert event.created_at == datetime.fromisoformat("2026-04-03T01:35:00+00:00")

    def test_deployment_event_optional_fields_missing(self):
        payload = _deployment_event_payload()
        del payload["node_id"]
        del payload["error_message"]
        event = DeploymentEvent(payload)

        assert event.node_id is None
        assert event.error_message is None


# ---------------------------------------------------------------------------
# Data class tests: Deployment
# ---------------------------------------------------------------------------


class TestDeployment:
    def test_deployment_parsed_fields(self):
        event_payload = _deployment_event_payload()
        payload = _deployment_payload(events=[event_payload])
        deployment = Deployment(payload)

        assert deployment.id == UUID("660e8400-e29b-41d4-a716-446655440001")
        assert deployment.agent_id == UUID("550e8400-e29b-41d4-a716-446655440000")
        assert deployment.status == "running"
        assert deployment.replicas == 2
        assert deployment.node_id == "node-abc"
        assert deployment.started_at == datetime.fromisoformat("2026-04-03T01:30:00+00:00")
        assert deployment.ended_at is None
        assert deployment.error_message is None
        assert len(deployment.events) == 1
        assert isinstance(deployment.events[0], DeploymentEvent)

    def test_deployment_optional_fields_missing(self):
        payload = _deployment_payload()
        del payload["node_id"]
        del payload["started_at"]
        del payload["ended_at"]
        del payload["error_message"]
        del payload["events"]
        deployment = Deployment(payload)

        assert deployment.node_id is None
        assert deployment.started_at is None
        assert deployment.ended_at is None
        assert deployment.error_message is None
        assert deployment.events == []


# ---------------------------------------------------------------------------
# Data class tests: AgentDetail
# ---------------------------------------------------------------------------


class TestAgentDetail:
    def test_agent_detail_inherits_agent(self):
        payload = _agent_payload()
        detail = AgentDetail(payload)

        assert isinstance(detail, Agent)
        assert detail.id == UUID("550e8400-e29b-41d4-a716-446655440000")
        assert detail.name == "test-agent"

    def test_agent_detail_deployments(self):
        dep_payload = _deployment_payload()
        payload = _agent_payload(deployments=[dep_payload])
        detail = AgentDetail(payload)

        assert len(detail.deployments) == 1
        assert isinstance(detail.deployments[0], Deployment)
        assert detail.deployments[0].id == UUID("660e8400-e29b-41d4-a716-446655440001")


# ---------------------------------------------------------------------------
# Data class tests: AgentLog
# ---------------------------------------------------------------------------


class TestAgentLog:
    def test_agent_log_fields(self):
        payload = _agent_log_payload()
        log = AgentLog(payload)

        assert log.id == UUID("880e8400-e29b-41d4-a716-446655440003")
        assert log.agent_id == UUID("550e8400-e29b-41d4-a716-446655440000")
        assert log.level == "INFO"
        assert log.message == "Agent started successfully"
        assert log.timestamp == datetime.fromisoformat("2026-04-03T01:05:00+00:00")
        assert log.extra_data == {"key": "value"}
        assert log.metadata == {"key": "value"}

    def test_agent_log_metadata_falls_back_to_extra_data(self):
        payload = _agent_log_payload()
        del payload["metadata"]
        log = AgentLog(payload)

        assert log.metadata == log.extra_data

    def test_agent_log_optional_fields_missing(self):
        payload = _agent_log_payload()
        del payload["extra_data"]
        del payload["metadata"]
        log = AgentLog(payload)

        assert log.extra_data is None
        assert log.metadata is None


# ---------------------------------------------------------------------------
# Data class tests: AgentMetric
# ---------------------------------------------------------------------------


class TestAgentMetric:
    def test_agent_metric_fields(self):
        payload = _agent_metric_payload()
        metric = AgentMetric(payload)

        assert metric.id == UUID("990e8400-e29b-41d4-a716-446655440004")
        assert metric.agent_id == UUID("550e8400-e29b-41d4-a716-446655440000")
        assert metric.cpu_usage == 45.5
        assert metric.memory_usage == 1024
        assert metric.timestamp == datetime.fromisoformat("2026-04-03T01:10:00+00:00")

    def test_agent_metric_optional_fields_missing(self):
        payload = _agent_metric_payload()
        del payload["cpu_usage"]
        del payload["memory_usage"]
        metric = AgentMetric(payload)

        assert metric.cpu_usage is None
        assert metric.memory_usage is None


# ---------------------------------------------------------------------------
# Client guard: sync methods require httpx.Client
# ---------------------------------------------------------------------------


class TestAgentsSyncClientGuard:
    """Sync methods must raise when given an AsyncClient."""

    # Methods that call _require_sync_client (have positional args that exercise guard)
    _methods_with_id = ["get", "delete", "deploy", "stop", "logs", "metrics"]

    @pytest.mark.parametrize("method", _methods_with_id)
    def test_raises_on_async_client(self, method: str):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        agents = Agents(mock_client)
        func = getattr(agents, method)

        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            func("any-id")

    def test_create_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        agents = Agents(mock_client)

        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            agents.create("any-name")

    def test_list_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        agents = Agents(mock_client)

        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            agents.list()


# ---------------------------------------------------------------------------
# Client guard: async methods require httpx.AsyncClient
# ---------------------------------------------------------------------------


class TestAgentsAsyncClientGuard:
    """Async methods must raise when given a sync httpx.Client.

    Note: We use MagicMock(spec=httpx.Client) for the sync client, not
    AsyncMock, because AsyncMock(spec=httpx.AsyncClient) is recognized as
    an AsyncClient instance by isinstance() and would not trigger the guard.
    """

    _methods = ["aget", "adelete", "adeploy", "astop", "alogs", "ametrics"]

    @pytest.mark.parametrize("method", _methods)
    @pytest.mark.asyncio
    async def test_raises_on_sync_client(self, method: str):
        mock_client = MagicMock(spec=httpx.Client)
        agents = Agents(mock_client)
        func = getattr(agents, method)

        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await func("any-id")

    @pytest.mark.asyncio
    async def test_acreate_raises_on_sync_client(self):
        mock_client = MagicMock(spec=httpx.Client)
        agents = Agents(mock_client)

        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await agents.acreate("any-name")

    @pytest.mark.asyncio
    async def test_alist_raises_on_sync_client(self):
        mock_client = MagicMock(spec=httpx.Client)
        agents = Agents(mock_client)

        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await agents.alist()

    @pytest.mark.asyncio
    async def test_aupdate_config_raises_on_sync_client(self):
        mock_client = MagicMock(spec=httpx.Client)
        agents = Agents(mock_client)

        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await agents.aupdate_config("any-id", {})


# ---------------------------------------------------------------------------
# Sync methods: create
# ---------------------------------------------------------------------------


class TestAgentsCreate:
    def test_create_success(self):
        returned = _agent_payload(name="my-agent")
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        agents = Agents(mock_client)

        result = agents.create(
            name="my-agent", description="desc", type="anthropic", config={"model": "claude-3"}
        )

        assert isinstance(result, Agent)
        assert result.name == "my-agent"
        request = assert_v1_request(mock_client.post, "POST", "/v1/agents")
        assert json.loads(request.content) == {
            "name": "my-agent",
            "description": "desc",
            "type": "anthropic",
            "config": {"model": "claude-3"},
        }
        mock_response.raise_for_status.assert_called_once()

    def test_create_minimal(self):
        returned = _agent_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        agents = Agents(mock_client)

        result = agents.create(name="minimal-agent")

        assert isinstance(result, Agent)
        request = assert_v1_request(mock_client.post, "POST", "/v1/agents")
        assert json.loads(request.content) == {
            "name": "minimal-agent",
            "description": None,
            "type": "openai",
            "config": None,
        }

    def test_create_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "422", request=MagicMock(), response=MagicMock(status_code=422)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        agents = Agents(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            agents.create(name="bad-agent")


# ---------------------------------------------------------------------------
# Sync methods: list
# ---------------------------------------------------------------------------


class TestAgentsList:
    def test_list_success(self):
        returned = [
            _agent_payload(name="agent-1"),
            _agent_payload(name="agent-2", id="660e8400-e29b-41d4-a716-446655440099"),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        result = agents.list(skip=10, limit=25)

        assert len(result) == 2
        assert all(isinstance(a, Agent) for a in result)
        request = assert_v1_request(mock_client.get, "GET", "/v1/agents")
        assert dict(request.url.params) == {"skip": "10", "limit": "25"}
        mock_response.raise_for_status.assert_called_once()

    def test_list_defaults(self):
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        agents.list()

        request = assert_v1_request(mock_client.get, "GET", "/v1/agents")
        assert dict(request.url.params) == {"skip": "0", "limit": "50"}

    def test_list_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            agents.list()


# ---------------------------------------------------------------------------
# Sync methods: get
# ---------------------------------------------------------------------------


class TestAgentsGet:
    def test_get_success(self):
        payload = _agent_payload(deployments=[_deployment_payload()])
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        result = agents.get("550e8400-e29b-41d4-a716-446655440000")

        assert isinstance(result, AgentDetail)
        assert result.name == "test-agent"
        assert_v1_request(
            mock_client.get,
            "GET",
            "/v1/agents/550e8400-e29b-41d4-a716-446655440000",
        )
        mock_response.raise_for_status.assert_called_once()

    def test_get_uuid(self):
        agent_uuid = UUID("550e8400-e29b-41d4-a716-446655440000")
        payload = _agent_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        agents.get(agent_uuid)

        assert_v1_request(mock_client.get, "GET", f"/v1/agents/{agent_uuid}")

    def test_get_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            agents.get("nonexistent-id")


# ---------------------------------------------------------------------------
# Sync methods: delete
# ---------------------------------------------------------------------------


class TestAgentsDelete:
    def test_delete_success(self):
        mock_response = MagicMock()
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.delete.return_value = mock_response
        agents = Agents(mock_client)

        agents.delete("550e8400-e29b-41d4-a716-446655440000")

        assert_v1_request(
            mock_client.delete,
            "DELETE",
            "/v1/agents/550e8400-e29b-41d4-a716-446655440000",
        )
        mock_response.raise_for_status.assert_called_once()

    def test_delete_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=MagicMock(status_code=403)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.delete.return_value = mock_response
        agents = Agents(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            agents.delete("protected-id")


# ---------------------------------------------------------------------------
# Sync methods: deploy
# ---------------------------------------------------------------------------


class TestAgentsDeploy:
    def test_deploy_success(self):
        returned = {"deployment_id": "660e8400-e29b-41d4-a716-446655440001", "status": "deploying"}
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        agents = Agents(mock_client)

        result = agents.deploy("550e8400-e29b-41d4-a716-446655440000")

        assert result == returned
        assert_v1_request(
            mock_client.post,
            "POST",
            "/v1/agents/550e8400-e29b-41d4-a716-446655440000/deploy",
        )
        mock_response.raise_for_status.assert_called_once()

    def test_deploy_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "409", request=MagicMock(), response=MagicMock(status_code=409)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        agents = Agents(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            agents.deploy("conflict-id")


# ---------------------------------------------------------------------------
# Sync methods: stop
# ---------------------------------------------------------------------------


class TestAgentsStop:
    def test_stop_success(self):
        returned = {"status": "stopped"}
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        agents = Agents(mock_client)

        result = agents.stop("550e8400-e29b-41d4-a716-446655440000")

        assert result == returned
        assert_v1_request(
            mock_client.post,
            "POST",
            "/v1/agents/550e8400-e29b-41d4-a716-446655440000/stop",
        )
        mock_response.raise_for_status.assert_called_once()

    def test_stop_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400", request=MagicMock(), response=MagicMock(status_code=400)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        agents = Agents(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            agents.stop("bad-id")


# ---------------------------------------------------------------------------
# Sync methods: logs
# ---------------------------------------------------------------------------


class TestAgentsLogs:
    def test_logs_success(self):
        returned = [
            _agent_log_payload(),
            _agent_log_payload(id="990e8400-e29b-41d4-a716-446655440099", level="ERROR"),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agent_id": "550e8400-e29b-41d4-a716-446655440000",
            "items": returned,
            "total": 2,
            "has_more": False,
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        result = agents.logs("550e8400-e29b-41d4-a716-446655440000", skip=5, limit=20, level="INFO")

        assert len(result) == 2
        assert all(isinstance(log, AgentLog) for log in result)
        request = assert_v1_request(
            mock_client.get,
            "GET",
            "/v1/agents/550e8400-e29b-41d4-a716-446655440000/logs",
        )
        assert dict(request.url.params) == {"skip": "5", "limit": "20", "level": "INFO"}
        mock_response.raise_for_status.assert_called_once()

    def test_logs_defaults(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agent_id": "550e8400-e29b-41d4-a716-446655440000",
            "items": [],
            "total": 0,
            "has_more": False,
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        agents.logs("550e8400-e29b-41d4-a716-446655440000")

        request = assert_v1_request(
            mock_client.get,
            "GET",
            "/v1/agents/550e8400-e29b-41d4-a716-446655440000/logs",
        )
        assert dict(request.url.params) == {"skip": "0", "limit": "100"}

    def test_logs_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            agents.logs("err-id")


# ---------------------------------------------------------------------------
# Sync methods: metrics
# ---------------------------------------------------------------------------


class TestAgentsMetrics:
    def test_metrics_success(self):
        returned = [
            _agent_metric_payload(),
            _agent_metric_payload(id="aa0e8400-e29b-41d4-a716-4466554400aa"),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agent_id": "550e8400-e29b-41d4-a716-446655440000",
            "items": returned,
            "total": 2,
            "has_more": False,
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        result = agents.metrics("550e8400-e29b-41d4-a716-446655440000", skip=0, limit=50)

        assert len(result) == 2
        assert all(isinstance(m, AgentMetric) for m in result)
        request = assert_v1_request(
            mock_client.get,
            "GET",
            "/v1/agents/550e8400-e29b-41d4-a716-446655440000/metrics",
        )
        assert dict(request.url.params) == {"skip": "0", "limit": "50"}
        mock_response.raise_for_status.assert_called_once()

    def test_metrics_defaults(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agent_id": "550e8400-e29b-41d4-a716-446655440000",
            "items": [],
            "total": 0,
            "has_more": False,
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        agents.metrics("550e8400-e29b-41d4-a716-446655440000")

        request = assert_v1_request(
            mock_client.get,
            "GET",
            "/v1/agents/550e8400-e29b-41d4-a716-446655440000/metrics",
        )
        assert dict(request.url.params) == {"skip": "0", "limit": "100"}

    def test_metrics_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503", request=MagicMock(), response=MagicMock(status_code=503)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            agents.metrics("err-id")


# ---------------------------------------------------------------------------
# Sync methods: update_config
# ---------------------------------------------------------------------------


class TestAgentsUpdateConfig:
    def test_update_config_dict(self):
        returned = _agent_payload(config={"model": "gpt-4o"})
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.patch.return_value = mock_response
        agents = Agents(mock_client)

        result = agents.update_config("550e8400-e29b-41d4-a716-446655440000", {"model": "gpt-4o"})

        assert isinstance(result, AgentDetail)
        request = assert_v1_request(
            mock_client.patch,
            "PATCH",
            "/v1/agents/550e8400-e29b-41d4-a716-446655440000/config",
        )
        assert "config" in json.loads(request.content)
        mock_response.raise_for_status.assert_called_once()

    def test_update_config_string(self):
        returned = _agent_payload(config="{}")
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.patch.return_value = mock_response
        agents = Agents(mock_client)

        agents.update_config("550e8400-e29b-41d4-a716-446655440000", '{"model": "claude-3"}')

        call_args = mock_client.patch.call_args
        assert call_args.kwargs["json"]["config"] == '{"model": "claude-3"}'

    def test_update_config_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400", request=MagicMock(), response=MagicMock(status_code=400)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.patch.return_value = mock_response
        agents = Agents(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            agents.update_config("bad-id", {})


# ---------------------------------------------------------------------------
# Sync methods: stream_logs
# ---------------------------------------------------------------------------


class TestAgentsStreamLogs:
    def test_stream_logs_yields_logs(self):
        returned = [
            _agent_log_payload(),
            _agent_log_payload(id="bb0e8400-e29b-41d4-a716-4466554400bb"),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agent_id": "550e8400-e29b-41d4-a716-446655440000",
            "items": returned,
            "total": 2,
            "has_more": False,
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)
        collected: list[AgentLog] = []

        for log in agents.stream_logs(
            "550e8400-e29b-41d4-a716-446655440000",
            callback=lambda agent_log: collected.append(agent_log),
        ):
            pass

        assert len(collected) == 2
        assert all(isinstance(agent_log, AgentLog) for agent_log in collected)

    def test_stream_logs_calls_callback(self):
        returned = [
            _agent_log_payload(),
            _agent_log_payload(id="cc0e8400-e29b-41d4-a716-4466554400cc"),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agent_id": "550e8400-e29b-41d4-a716-446655440000",
            "items": returned,
            "total": 2,
            "has_more": False,
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)
        callback_count = 0

        def callback(log: AgentLog) -> None:
            nonlocal callback_count
            callback_count += 1

        list(agents.stream_logs("550e8400-e29b-41d4-a716-446655440000", callback=callback))

        assert callback_count == 2

    def test_stream_logs_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        agents = Agents(mock_client)

        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            # Must iterate the generator for _require_sync_client to fire
            list(agents.stream_logs("any-id", callback=lambda log: None))


# ---------------------------------------------------------------------------
# Async methods
# ---------------------------------------------------------------------------


class TestAgentsAsyncMethods:
    @pytest.mark.asyncio
    async def test_acreate_success(self):
        returned = _agent_payload(name="async-agent")
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        agents = Agents(mock_client)

        result = await agents.acreate(name="async-agent")

        assert isinstance(result, Agent)
        assert result.name == "async-agent"
        mock_client.post.assert_called_once()
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_alist_success(self):
        returned = [_agent_payload()]
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        result = await agents.alist(skip=5, limit=10)

        assert len(result) == 1
        assert isinstance(result[0], Agent)
        request = assert_v1_request(mock_client.get, "GET", "/v1/agents")
        assert dict(request.url.params) == {"skip": "5", "limit": "10"}

    @pytest.mark.asyncio
    async def test_aget_success(self):
        payload = _agent_payload(deployments=[_deployment_payload()])
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        result = await agents.aget("550e8400-e29b-41d4-a716-446655440000")

        assert isinstance(result, AgentDetail)
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_adelete_success(self):
        mock_response = MagicMock()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.delete.return_value = mock_response
        agents = Agents(mock_client)

        await agents.adelete("550e8400-e29b-41d4-a716-446655440000")

        mock_client.delete.assert_called_once()
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_adeploy_success(self):
        returned = {"deployment_id": "new-dep", "status": "deploying"}
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        agents = Agents(mock_client)

        result = await agents.adeploy("550e8400-e29b-41d4-a716-446655440000")

        assert result == returned
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_astop_success(self):
        returned = {"status": "stopped"}
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        agents = Agents(mock_client)

        result = await agents.astop("550e8400-e29b-41d4-a716-446655440000")

        assert result == returned
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_alogs_success(self):
        returned = [_agent_log_payload()]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agent_id": "550e8400-e29b-41d4-a716-446655440000",
            "items": returned,
            "total": 1,
            "has_more": False,
        }
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        result = await agents.alogs("550e8400-e29b-41d4-a716-446655440000", level="WARN")

        assert len(result) == 1
        assert isinstance(result[0], AgentLog)
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_ametrics_success(self):
        returned = [_agent_metric_payload()]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agent_id": "550e8400-e29b-41d4-a716-446655440000",
            "items": returned,
            "total": 1,
            "has_more": False,
        }
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)

        result = await agents.ametrics("550e8400-e29b-41d4-a716-446655440000")

        assert len(result) == 1
        assert isinstance(result[0], AgentMetric)
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_aupdate_config_success(self):
        returned = _agent_payload(config={"model": "gpt-4o"})
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.patch.return_value = mock_response
        agents = Agents(mock_client)

        result = await agents.aupdate_config(
            "550e8400-e29b-41d4-a716-446655440000", {"model": "gpt-4o"}
        )

        assert isinstance(result, AgentDetail)
        mock_client.patch.assert_called_once()
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_astream_logs(self):
        returned = [
            _agent_log_payload(),
            _agent_log_payload(id="dd0e8400-e29b-41d4-a716-4466554400dd"),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agent_id": "550e8400-e29b-41d4-a716-446655440000",
            "items": returned,
            "total": 2,
            "has_more": False,
        }
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        agents = Agents(mock_client)
        collected: list[AgentLog] = []
        callback_count = 0

        def callback(log: AgentLog) -> None:
            nonlocal callback_count
            callback_count += 1

        async for log in agents.astream_logs(
            "550e8400-e29b-41d4-a716-446655440000", callback=callback
        ):
            collected.append(log)

        assert len(collected) == 2
        assert all(isinstance(agent_log, AgentLog) for agent_log in collected)
        assert callback_count == 2
