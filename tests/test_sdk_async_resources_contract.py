from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from mutx.agents import Agents
from mutx.deployments import Deployments
from mutx.api_keys import APIKeys
from mutx.webhooks import Webhooks


def _agent_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "name": "test-agent",
        "description": "agent for async contract",
        "status": "running",
        "config": {"model": "gpt-4o"},
        "created_at": "2026-03-12T09:00:00",
        "updated_at": "2026-03-12T09:00:00",
        "user_id": str(uuid.uuid4()),
    }
    payload.update(overrides)
    return payload


def _deployment_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "agent_id": str(uuid.uuid4()),
        "status": "running",
        "replicas": 1,
        "node_id": "node-1",
        "started_at": "2026-03-12T09:05:00",
        "ended_at": None,
        "error_message": None,
    }
    payload.update(overrides)
    return payload


def _api_key_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "name": "ci-key",
        "is_active": True,
        "last_used": None,
        "created_at": "2026-03-12T09:00:00",
        "expires_at": None,
        "key": "mutx_" + uuid.uuid4().hex,
    }
    payload.update(overrides)
    return payload


def _webhook_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "url": "https://example.com/webhook",
        "events": ["agent.started", "agent.stopped"],
        "secret": "whsec-abc",
        "is_active": True,
        "created_at": "2026-03-12T09:00:00",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_agents_async_methods_are_awaited_with_async_client() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_agent_payload(name="async-agent"))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        agents = Agents(client)
        agent = await agents.acreate(name="async-agent", config={"model": "gpt-4o"})

    assert captured["path"] == "/v1/agents"
    assert captured["json"]["name"] == "async-agent"
    assert captured["json"]["config"]["model"] == "gpt-4o"
    assert agent.name == "async-agent"


@pytest.mark.asyncio
async def test_agents_sync_methods_reject_async_transport() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        agents = Agents(client)
        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            agents.list()


@pytest.mark.asyncio
async def test_deployments_async_methods_are_awaited_with_async_client() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = request.url.query.params if request.url.query else {}
        return httpx.Response(201, json=_deployment_payload())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        deployments = Deployments(client)
        deployment = await deployments.acreate(str(uuid.uuid4()), replicas=2)

    assert captured["path"] == "/v1/deployments"
    assert deployment.status in {"running", "pending", "creating"}


@pytest.mark.asyncio
async def test_api_keys_async_methods_are_awaited_with_async_client() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_api_key_payload(key="mutx_test_key"))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        api_keys = APIKeys(client)
        key = await api_keys.acreate("test-key")

    assert captured["path"] == "/v1/api-keys"
    assert key.name == "ci-key"
    assert key.key == "mutx_test_key"


@pytest.mark.asyncio
async def test_webhooks_async_methods_are_awaited_with_async_client() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode()) if request.content else {}
        return httpx.Response(201, json=_webhook_payload())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        webhooks = Webhooks(client)
        webhook = await webhooks.acreate(url="https://example.com/hook", events=["agent.started"])

    assert captured["path"] == "/v1/webhooks/"
    assert webhook.url == "https://example.com/webhook"
    assert webhook.events == ["agent.started", "agent.stopped"]
