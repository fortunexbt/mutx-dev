from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from mutx.deployments import Deployment, Deployments


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


def _event_history_payload(deployment_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    payload = {
        "deployment_id": str(deployment_id),
        "deployment_status": "running",
        "items": [
            {
                "id": str(uuid.uuid4()),
                "deployment_id": str(deployment_id),
                "event_type": "scale",
                "status": "running",
                "node_id": "node-1",
                "error_message": None,
                "created_at": "2026-03-12T10:00:00",
            }
        ],
        "total": 1,
        "skip": 0,
        "limit": 100,
        "event_type": None,
        "status": None,
    }
    payload.update(overrides)
    return payload


def _metrics_payload() -> list[dict[str, Any]]:
    return [
        {
            "id": str(uuid.uuid4()),
            "agent_id": str(uuid.uuid4()),
            "cpu_usage": 0.61,
            "memory_usage": 0.44,
            "timestamp": "2026-03-12T10:15:00",
        }
    ]


def test_deployments_create_hits_canonical_route_and_maps_payload() -> None:
    agent_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(
            201,
            json=_deployment_payload(agent_id=str(agent_id), status="pending", replicas=3),
        )

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        deployment = Deployments(client).create(agent_id, replicas=3)

    assert captured["path"] == "/v1/deployments"
    assert json.loads(captured["body"]) == {"agent_id": str(agent_id), "replicas": 3}
    assert deployment.agent_id == agent_id
    assert deployment.status == "pending"
    assert deployment.replicas == 3


@pytest.mark.asyncio
async def test_deployments_acreate_hits_canonical_route_and_maps_payload() -> None:
    agent_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(
            201,
            json=_deployment_payload(agent_id=str(agent_id), status="pending", replicas=2),
        )

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        deployment = await Deployments(client).acreate(agent_id, replicas=2)

    assert captured["path"] == "/v1/deployments"
    assert json.loads(captured["body"]) == {"agent_id": str(agent_id), "replicas": 2}
    assert deployment.agent_id == agent_id
    assert deployment.status == "pending"
    assert deployment.replicas == 2


def test_deployments_restart_hits_contract_route_and_maps_payload() -> None:
    deployment_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(
            200, json=_deployment_payload(id=str(deployment_id), status="pending")
        )

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        deployment = Deployments(client).restart(deployment_id)

    assert captured["path"] == f"/v1/deployments/{deployment_id}/restart"
    assert captured["body"] == ""
    assert deployment.id == deployment_id
    assert deployment.status == "pending"


@pytest.mark.asyncio
async def test_deployments_arestart_hits_contract_route_and_maps_payload() -> None:
    deployment_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(
            200, json=_deployment_payload(id=str(deployment_id), status="pending")
        )

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        deployment = await Deployments(client).arestart(deployment_id)

    assert captured["path"] == f"/v1/deployments/{deployment_id}/restart"
    assert captured["body"] == ""
    assert deployment.id == deployment_id
    assert deployment.status == "pending"


def test_deployments_events_hits_contract_route_and_maps_payload() -> None:
    deployment_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(
            200,
            json=_event_history_payload(
                deployment_id,
                deployment_status="failed",
                event_type="restart",
                status="failed",
            ),
        )

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        history = Deployments(client).events(
            deployment_id,
            skip=3,
            limit=25,
            event_type="restart",
            status="failed",
        )

    assert captured["path"] == f"/v1/deployments/{deployment_id}/events"
    assert captured["query"] == {
        "skip": "3",
        "limit": "25",
        "event_type": "restart",
        "status": "failed",
    }
    assert history.deployment_id == deployment_id
    assert history.deployment_status == "failed"
    assert history.total == 1
    assert history.items[0].event_type == "scale"


@pytest.mark.asyncio
async def test_deployments_aevents_hits_contract_route_and_maps_payload() -> None:
    deployment_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=_event_history_payload(deployment_id))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        history = await Deployments(client).aevents(deployment_id, skip=1, limit=10)

    assert captured["path"] == f"/v1/deployments/{deployment_id}/events"
    assert captured["query"] == {"skip": "1", "limit": "10"}
    assert history.deployment_id == deployment_id
    assert history.items[0].status == "running"


def test_deployment_parser_accepts_nullable_started_at_and_nested_events() -> None:
    deployment_id = uuid.uuid4()
    payload = _deployment_payload(
        id=str(deployment_id),
        started_at=None,
        events=[
            {
                "id": str(uuid.uuid4()),
                "deployment_id": str(deployment_id),
                "event_type": "create",
                "status": "pending",
                "node_id": None,
                "error_message": None,
                "created_at": "2026-03-12T09:00:00",
            }
        ],
    )

    deployment = Deployment(payload)

    assert deployment.started_at is None
    assert len(deployment.events) == 1
    assert deployment.events[0].event_type == "create"


def test_deployment_parser_accepts_z_suffix_timestamps() -> None:
    deployment_id = uuid.uuid4()
    payload = _deployment_payload(
        id=str(deployment_id),
        started_at="2026-03-12T09:00:00Z",
        ended_at="2026-03-12T09:30:00Z",
        events=[
            {
                "id": str(uuid.uuid4()),
                "deployment_id": str(deployment_id),
                "event_type": "restart",
                "status": "pending",
                "node_id": None,
                "error_message": None,
                "created_at": "2026-03-12T09:45:00Z",
            }
        ],
    )

    deployment = Deployment(payload)

    assert deployment.started_at is not None
    assert deployment.started_at.tzinfo is not None
    assert deployment.ended_at is not None
    assert deployment.ended_at.tzinfo is not None
    assert deployment.events[0].created_at.tzinfo is not None


def test_deployments_logs_support_level_filter_param() -> None:
    deployment_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        payload = Deployments(client).logs(deployment_id, skip=2, limit=50, level="ERROR")

    assert payload == []
    assert captured["path"] == f"/v1/deployments/{deployment_id}/logs"
    assert captured["query"] == {"skip": "2", "limit": "50", "level": "ERROR"}


@pytest.mark.asyncio
async def test_deployments_alogs_support_level_filter_param() -> None:
    deployment_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        payload = await Deployments(client).alogs(deployment_id, skip=4, limit=75, level="INFO")

    assert payload == []
    assert captured["path"] == f"/v1/deployments/{deployment_id}/logs"
    assert captured["query"] == {"skip": "4", "limit": "75", "level": "INFO"}


def test_deployments_metrics_hits_contract_route_and_query_params() -> None:
    deployment_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=_metrics_payload())

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        payload = Deployments(client).metrics(deployment_id, skip=5, limit=15)

    assert captured["path"] == f"/v1/deployments/{deployment_id}/metrics"
    assert captured["query"] == {"skip": "5", "limit": "15"}
    assert payload[0]["cpu_usage"] == 0.61
    assert payload[0]["memory_usage"] == 0.44


@pytest.mark.asyncio
async def test_deployments_ametrics_hits_contract_route_and_query_params() -> None:
    deployment_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=_metrics_payload())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        payload = await Deployments(client).ametrics(deployment_id, skip=6, limit=12)

    assert captured["path"] == f"/v1/deployments/{deployment_id}/metrics"
    assert captured["query"] == {"skip": "6", "limit": "12"}
    assert payload[0]["cpu_usage"] == 0.61
