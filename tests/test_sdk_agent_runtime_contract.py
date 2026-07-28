# SDK contract tests for agent runtime module

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mutx.agent_runtime import (
    AgentInfo,
    AgentMetrics,
    Command,
    MutxAgentClient,
    MutxAgentSyncClient,
    create_agent_client,
)


def _agent_info_response(**overrides):
    payload = {
        "agent_id": str(uuid.uuid4()),
        "name": "test-agent",
        "api_key": "mutx_agent_" + uuid.uuid4().hex,
        "status": "registered",
    }
    payload.update(overrides)
    return payload


def _command_response(**overrides):
    payload = {
        "command_id": str(uuid.uuid4()),
        "action": "run_task",
        "parameters": {"task_id": "123"},
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(overrides)
    return payload


def _capture_transport(
    response_payload: dict,
    *,
    status_code: int = 200,
) -> tuple[list[httpx.Request], httpx.MockTransport]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, json=response_payload)

    return requests, httpx.MockTransport(handler)


def test_agent_info_parses_response():
    response = _agent_info_response()
    info = AgentInfo(
        agent_id=response["agent_id"],
        name=response["name"],
        api_key=response["api_key"],
        status=response["status"],
        registered_at=datetime.now(timezone.utc),
    )

    assert info.agent_id == response["agent_id"]
    assert info.name == response["name"]
    assert info.api_key == response["api_key"]
    assert info.status == "registered"


def test_command_parses_response():
    received_at = datetime.now(timezone.utc)
    cmd = Command(
        command_id=str(uuid.uuid4()),
        action="stop",
        parameters={"reason": "maintenance"},
        received_at=received_at,
    )

    assert cmd.action == "stop"
    assert cmd.parameters["reason"] == "maintenance"


def test_agent_metrics_defaults():
    metrics = AgentMetrics()

    assert metrics.cpu_usage == 0.0
    assert metrics.memory_usage == 0.0
    assert metrics.uptime_seconds == 0.0
    assert metrics.requests_processed == 0
    assert metrics.errors_count == 0
    assert metrics.custom == {}


def test_agent_metrics_with_values():
    metrics = AgentMetrics(
        cpu_usage=50.5,
        memory_usage=1024.0,
        uptime_seconds=3600.0,
        requests_processed=100,
        errors_count=2,
        custom={"version": "1.0"},
    )

    assert metrics.cpu_usage == 50.5
    assert metrics.memory_usage == 1024.0
    assert metrics.uptime_seconds == 3600.0
    assert metrics.requests_processed == 100
    assert metrics.errors_count == 2
    assert metrics.custom["version"] == "1.0"


@pytest.mark.asyncio
async def test_mutx_agent_client_register_hits_contract_route():
    agent_id = str(uuid.uuid4())
    api_key = "mutx_agent_" + uuid.uuid4().hex
    requests, transport = _capture_transport(
        _agent_info_response(agent_id=agent_id, api_key=api_key)
    )
    client = MutxAgentClient(mutx_url="https://api.test")
    client._client = httpx.AsyncClient(base_url=client.api_base_url, transport=transport)
    try:
        info = await client.register(name="test-agent", description="Test agent")
    finally:
        await client.close()

    request = requests[0]
    body = json.loads(request.content)
    assert request.url.path == "/v1/agents/register"
    assert body["name"] == "test-agent"
    assert body["description"] == "Test agent"
    assert info.agent_id == agent_id


@pytest.mark.asyncio
async def test_mutx_agent_client_connect_hits_canonical_status_route():
    agent_id = str(uuid.uuid4())
    requests, transport = _capture_transport(
        {
            "agent_id": agent_id,
            "status": "running",
            "last_heartbeat": None,
            "uptime_seconds": 1.0,
        }
    )
    client = MutxAgentClient(mutx_url="https://api.test")
    client._client = httpx.AsyncClient(base_url=client.api_base_url, transport=transport)
    try:
        connected = await client.connect(agent_id, "agent-secret")
    finally:
        await client.close()

    assert connected is True
    assert requests[0].url.path == f"/v1/agents/{agent_id}/status"
    assert requests[0].headers["authorization"] == "Bearer agent-secret"


@pytest.mark.asyncio
async def test_mutx_agent_client_heartbeat_hits_contract_route():
    agent_id = str(uuid.uuid4())
    requests, transport = _capture_transport({"status": "ok"})
    client = MutxAgentClient(mutx_url="https://api.test", agent_id=agent_id, api_key="test-key")
    client._client = httpx.AsyncClient(base_url=client.api_base_url, transport=transport)
    try:
        await client.heartbeat(status="running", message="all good")
    finally:
        await client.close()

    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/agents/heartbeat"
    assert body["agent_id"] == agent_id
    assert body["status"] == "running"
    assert body["message"] == "all good"


@pytest.mark.asyncio
async def test_mutx_agent_client_heartbeat_requires_registration():
    client = MutxAgentClient(mutx_url="https://api.test")

    with pytest.raises(ValueError, match="not registered"):
        await client.heartbeat()


@pytest.mark.asyncio
async def test_mutx_agent_client_report_metrics_hits_contract_route():
    agent_id = str(uuid.uuid4())
    requests, transport = _capture_transport({"status": "ok"})
    client = MutxAgentClient(mutx_url="https://api.test", agent_id=agent_id, api_key="test-key")
    client._client = httpx.AsyncClient(base_url=client.api_base_url, transport=transport)
    try:
        metrics = AgentMetrics(cpu_usage=25.0, memory_usage=512.0, requests_processed=10)
        await client.report_metrics(metrics)
    finally:
        await client.close()

    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/agents/metrics"
    assert body["agent_id"] == agent_id
    assert body["cpu_usage"] == 25.0
    assert body["memory_usage"] == 512.0
    assert body["requests_processed"] == 10


@pytest.mark.asyncio
async def test_mutx_agent_client_poll_commands_hits_contract_route():
    agent_id = str(uuid.uuid4())
    command_id = str(uuid.uuid4())
    requests, transport = _capture_transport(
        {"commands": [_command_response(command_id=command_id)]}
    )
    client = MutxAgentClient(mutx_url="https://api.test", agent_id=agent_id, api_key="test-key")
    client._client = httpx.AsyncClient(base_url=client.api_base_url, transport=transport)
    try:
        commands = await client.poll_commands()
    finally:
        await client.close()

    assert requests[0].url.path == "/v1/agents/commands"
    assert requests[0].url.params["agent_id"] == agent_id
    assert len(commands) == 1
    assert commands[0].command_id == command_id
    assert commands[0].action == "run_task"


@pytest.mark.asyncio
async def test_mutx_agent_client_acknowledge_command_hits_contract_route():
    agent_id = str(uuid.uuid4())
    command_id = str(uuid.uuid4())
    requests, transport = _capture_transport({"status": "acknowledged"})
    client = MutxAgentClient(mutx_url="https://api.test", agent_id=agent_id, api_key="test-key")
    client._client = httpx.AsyncClient(base_url=client.api_base_url, transport=transport)
    try:
        await client.acknowledge_command(
            command_id=command_id,
            success=True,
            result={"output": "done"},
        )
    finally:
        await client.close()

    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/agents/commands/acknowledge"
    assert body["command_id"] == command_id
    assert body["agent_id"] == agent_id
    assert body["success"] is True
    assert body["result"]["output"] == "done"


@pytest.mark.asyncio
async def test_mutx_agent_client_log_hits_contract_route():
    agent_id = str(uuid.uuid4())
    requests, transport = _capture_transport({"status": "logged"})
    client = MutxAgentClient(mutx_url="https://api.test", agent_id=agent_id, api_key="test-key")
    client._client = httpx.AsyncClient(base_url=client.api_base_url, transport=transport)
    try:
        await client.log(level="info", message="Agent started", metadata={"host": "server1"})
    finally:
        await client.close()

    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/agents/logs"
    assert body["agent_id"] == agent_id
    assert body["level"] == "info"
    assert body["message"] == "Agent started"
    assert body["metadata"]["host"] == "server1"


def test_mutx_agent_sync_client_register():
    agent_id = str(uuid.uuid4())
    api_key = "mutx_agent_" + uuid.uuid4().hex
    requests, transport = _capture_transport(
        _agent_info_response(agent_id=agent_id, api_key=api_key),
        status_code=201,
    )
    client = MutxAgentSyncClient(mutx_url="https://api.test")
    http = httpx.Client(base_url=client.api_base_url, transport=transport)
    with patch("mutx.agent_runtime.httpx.Client", return_value=http):
        info = client.register(name="sync-agent", description="Sync test")

    assert requests[0].url.path == "/v1/agents/register"
    assert json.loads(requests[0].content)["name"] == "sync-agent"
    assert info.agent_id == agent_id


def test_mutx_agent_sync_client_heartbeat():
    agent_id = str(uuid.uuid4())
    requests, transport = _capture_transport({"status": "ok"})
    client = MutxAgentSyncClient(mutx_url="https://api.test", agent_id=agent_id)
    http = httpx.Client(base_url=client.api_base_url, transport=transport)
    with patch("mutx.agent_runtime.httpx.Client", return_value=http):
        client.heartbeat(status="idle", message="waiting")

    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/agents/heartbeat"
    assert body["agent_id"] == agent_id
    assert body["status"] == "idle"


def test_mutx_agent_sync_client_report_metrics():
    agent_id = str(uuid.uuid4())
    requests, transport = _capture_transport({"status": "ok"})
    client = MutxAgentSyncClient(mutx_url="https://api.test", agent_id=agent_id)
    http = httpx.Client(base_url=client.api_base_url, transport=transport)
    with patch("mutx.agent_runtime.httpx.Client", return_value=http):
        client.report_metrics(cpu_usage=75.0, memory_usage=2048.0)

    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/agents/metrics"
    assert body["cpu_usage"] == 75.0
    assert body["memory_usage"] == 2048.0


def test_mutx_agent_sync_client_log():
    agent_id = str(uuid.uuid4())
    requests, transport = _capture_transport({"status": "ok"})
    client = MutxAgentSyncClient(mutx_url="https://api.test", agent_id=agent_id)
    http = httpx.Client(base_url=client.api_base_url, transport=transport)
    with patch("mutx.agent_runtime.httpx.Client", return_value=http):
        client.log(level="error", message="Something failed", metadata={"code": 500})

    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/agents/logs"
    assert body["level"] == "error"
    assert body["message"] == "Something failed"
    assert body["metadata"]["code"] == 500


def test_mutx_agent_sync_client_requires_registration_for_heartbeat():
    client = MutxAgentSyncClient(mutx_url="https://api.test")

    with pytest.raises(ValueError, match="not registered"):
        client.heartbeat()


def test_mutx_agent_sync_client_requires_registration_for_metrics():
    client = MutxAgentSyncClient(mutx_url="https://api.test")

    with pytest.raises(ValueError, match="not registered"):
        client.report_metrics()


def test_mutx_agent_sync_client_requires_registration_for_log():
    client = MutxAgentSyncClient(mutx_url="https://api.test")

    with pytest.raises(ValueError, match="not registered"):
        client.log(level="info", message="test")


@pytest.mark.asyncio
async def test_create_agent_client_registers_new_agent():
    agent_id = str(uuid.uuid4())
    api_key = "mutx_agent_" + uuid.uuid4().hex

    async def mock_post(*args, **kwargs):
        response = AsyncMock()
        response.raise_for_status = lambda: None
        response.json = lambda: _agent_info_response(agent_id=agent_id, api_key=api_key)
        return response

    with patch("mutx.agent_runtime.httpx.AsyncClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_client_class.return_value = mock_instance
        mock_instance.post = mock_post
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.headers = {}

        with patch("mutx.agent_runtime.MutxAgentClient._get_client", return_value=mock_instance):
            client = await create_agent_client(mutx_url="https://api.test", agent_name="new-agent")

    assert client.agent_id == agent_id
    assert client.api_key == api_key


def test_mutx_agent_client_is_registered_property():
    client = MutxAgentClient(mutx_url="https://api.test")
    assert client.is_registered is False

    client._registered = True
    assert client.is_registered is True


def test_mutx_agent_sync_client_is_registered_property():
    client = MutxAgentSyncClient(mutx_url="https://api.test")
    assert client.is_registered is False

    client._registered = True
    assert client.is_registered is True


def test_mutx_agent_client_uptime_property():
    client = MutxAgentClient(mutx_url="https://api.test")
    assert client.uptime >= 0


def test_mutx_agent_client_increment_requests():
    client = MutxAgentClient(mutx_url="https://api.test")
    assert client._requests_processed == 0

    client.increment_requests()
    assert client._requests_processed == 1

    client.increment_requests()
    assert client._requests_processed == 2


def test_mutx_agent_client_increment_errors():
    client = MutxAgentClient(mutx_url="https://api.test")
    assert client._errors_count == 0

    client.increment_errors()
    assert client._errors_count == 1
