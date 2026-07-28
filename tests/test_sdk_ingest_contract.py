"""SDK contract tests for ingest module."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import httpx
import pytest

from mutx.ingest import Ingest
from tests.sdk_contract_utils import assert_v1_request


def _agent_status_response(**overrides):
    payload = {
        "status": "ok",
        "agent_id": str(uuid.uuid4()),
        "reported_status": "running",
    }
    payload.update(overrides)
    return payload


def _deployment_response(**overrides):
    payload = {
        "status": "ok",
        "deployment_id": str(uuid.uuid4()),
        "event": "healthy",
    }
    payload.update(overrides)
    return payload


def _metrics_response(**overrides):
    payload = {
        "status": "ok",
        "agent_id": str(uuid.uuid4()),
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Sync client — report_agent_status
# ---------------------------------------------------------------------------


def test_report_agent_status_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        captured["json"] = kwargs.get("json", {})
        response = httpx.Response(200, json=_agent_status_response(agent_id=agent_id))
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.ingest.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        client = Ingest(mock_instance)
        result = client.report_agent_status(agent_id=agent_id, status="running")

    assert_v1_request(mock_instance.post, "POST", "/v1/ingest/agent-status")
    assert captured["json"]["agent_id"] == agent_id
    assert captured["json"]["status"] == "running"
    assert isinstance(result, dict)


def test_report_agent_status_with_optional_fields():
    captured = {}
    agent_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())

    def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        captured["json"] = kwargs.get("json", {})
        response = httpx.Response(200, json=_agent_status_response(agent_id=agent_id))
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.ingest.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        client = Ingest(mock_instance)
        result = client.report_agent_status(
            agent_id=agent_id,
            status="error",
            node_id=node_id,
            error_message="oom",
        )

    assert captured["json"]["node_id"] == node_id
    assert captured["json"]["error_message"] == "oom"
    assert result["status"] == "ok"


def test_report_agent_status_rejects_async_client():
    async_client = httpx.AsyncClient()

    client = Ingest(async_client)
    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        client.report_agent_status(agent_id=str(uuid.uuid4()), status="running")


# ---------------------------------------------------------------------------
# Sync client — report_deployment_event
# ---------------------------------------------------------------------------


def test_report_deployment_event_hits_contract_route():
    captured = {}
    deployment_id = str(uuid.uuid4())

    def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        captured["json"] = kwargs.get("json", {})
        response = httpx.Response(200, json=_deployment_response(deployment_id=deployment_id))
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.ingest.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        client = Ingest(mock_instance)
        result = client.report_deployment_event(deployment_id=deployment_id, event="healthy")

    assert_v1_request(mock_instance.post, "POST", "/v1/ingest/deployment")
    assert captured["json"]["deployment_id"] == deployment_id
    assert captured["json"]["event"] == "healthy"
    assert isinstance(result, dict)


def test_report_deployment_event_with_optional_fields():
    captured = {}
    deployment_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())

    def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        captured["json"] = kwargs.get("json", {})
        response = httpx.Response(200, json=_deployment_response(deployment_id=deployment_id))
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.ingest.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        client = Ingest(mock_instance)
        result = client.report_deployment_event(
            deployment_id=deployment_id,
            event="failed",
            status="unhealthy",
            node_id=node_id,
            error_message="crashed",
        )

    assert captured["json"]["status"] == "unhealthy"
    assert captured["json"]["node_id"] == node_id
    assert captured["json"]["error_message"] == "crashed"
    assert result["status"] == "ok"


def test_report_deployment_event_rejects_async_client():
    async_client = httpx.AsyncClient()

    client = Ingest(async_client)
    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        client.report_deployment_event(deployment_id=str(uuid.uuid4()), event="healthy")


# ---------------------------------------------------------------------------
# Sync client — report_metrics
# ---------------------------------------------------------------------------


def test_report_metrics_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        captured["json"] = kwargs.get("json", {})
        response = httpx.Response(200, json=_metrics_response(agent_id=agent_id))
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.ingest.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        client = Ingest(mock_instance)
        result = client.report_metrics(agent_id=agent_id, cpu_usage=50.0, memory_usage=1024.0)

    assert_v1_request(mock_instance.post, "POST", "/v1/ingest/metrics")
    assert captured["json"]["agent_id"] == agent_id
    assert captured["json"]["cpu_usage"] == 50.0
    assert captured["json"]["memory_usage"] == 1024.0
    assert isinstance(result, dict)


def test_report_metrics_optional_fields():
    captured = {}

    def mock_post(*args, **kwargs):
        captured["json"] = kwargs.get("json", {})
        response = httpx.Response(200, json=_metrics_response())
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.ingest.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        client = Ingest(mock_instance)
        # Only agent_id, no metrics
        result = client.report_metrics(agent_id=str(uuid.uuid4()))

    assert "cpu_usage" not in captured["json"]
    assert "memory_usage" not in captured["json"]
    assert result["status"] == "ok"


def test_report_metrics_rejects_async_client():
    async_client = httpx.AsyncClient()

    client = Ingest(async_client)
    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        client.report_metrics(agent_id=str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Async client — areport_agent_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_areport_agent_status_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_agent_status_response(agent_id=agent_id))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        ingest = Ingest(client)
        result = await ingest.areport_agent_status(agent_id=agent_id, status="running")

    assert captured["path"] == "/v1/ingest/agent-status"
    assert captured["json"]["agent_id"] == agent_id
    assert captured["json"]["status"] == "running"
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_areport_agent_status_with_optional_fields():
    captured = {}
    agent_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_agent_status_response(agent_id=agent_id))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        ingest = Ingest(client)
        result = await ingest.areport_agent_status(
            agent_id=agent_id,
            status="error",
            node_id=node_id,
            error_message="segfault",
        )

    assert captured["json"]["node_id"] == node_id
    assert captured["json"]["error_message"] == "segfault"
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_areport_agent_status_requires_async_client():
    sync_client = httpx.Client()

    client = Ingest(sync_client)
    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await client.areport_agent_status(agent_id=str(uuid.uuid4()), status="running")


# ---------------------------------------------------------------------------
# Async client — areport_deployment_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_areport_deployment_event_hits_contract_route():
    captured = {}
    deployment_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_deployment_response(deployment_id=deployment_id))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        ingest = Ingest(client)
        result = await ingest.areport_deployment_event(deployment_id=deployment_id, event="healthy")

    assert captured["path"] == "/v1/ingest/deployment"
    assert captured["json"]["deployment_id"] == deployment_id
    assert captured["json"]["event"] == "healthy"
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_areport_deployment_event_requires_async_client():
    sync_client = httpx.Client()

    client = Ingest(sync_client)
    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await client.areport_deployment_event(deployment_id=str(uuid.uuid4()), event="healthy")


# ---------------------------------------------------------------------------
# Async client — areport_metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_areport_metrics_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_metrics_response(agent_id=agent_id))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        ingest = Ingest(client)
        result = await ingest.areport_metrics(agent_id=agent_id, cpu_usage=25.0, memory_usage=512.0)

    assert captured["path"] == "/v1/ingest/metrics"
    assert captured["json"]["agent_id"] == agent_id
    assert captured["json"]["cpu_usage"] == 25.0
    assert captured["json"]["memory_usage"] == 512.0
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_areport_metrics_requires_async_client():
    sync_client = httpx.Client()

    client = Ingest(sync_client)
    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await client.areport_metrics(agent_id=str(uuid.uuid4()))
