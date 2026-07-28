"""Contract tests for mutx.swarm — /swarms SDK endpoints."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from mutx.swarms import Swarm, SwarmAgent, Swarms

# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _swarm_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "name": "test-swarm",
        "description": "A test swarm",
        "agent_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
        "min_replicas": 1,
        "max_replicas": 10,
        "created_at": "2026-03-12T09:00:00",
        "updated_at": "2026-03-12T10:00:00",
        "agents": [
            {
                "agent_id": str(uuid.uuid4()),
                "agent_name": "agent-1",
                "status": "running",
                "replicas": 2,
            },
            {
                "agent_id": str(uuid.uuid4()),
                "agent_name": "agent-2",
                "status": "idle",
                "replicas": 1,
            },
        ],
    }
    payload.update(overrides)
    return payload


def _list_response(items: list[dict[str, Any]], total: int) -> dict[str, Any]:
    return {"items": items, "total": total, "skip": 0, "limit": 50}


# ---------------------------------------------------------------------------
# Swarms — sync
# ---------------------------------------------------------------------------


def test_swarms_list_hits_contract_route_and_maps_payload() -> None:
    swarm_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=_list_response([_swarm_payload(id=swarm_id)], 1))

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        swarms, total = Swarms(client).list(skip=5, limit=25)

    assert captured["path"] == "/v1/swarms"
    assert captured["query"] == {"skip": "5", "limit": "25"}
    assert total == 1
    assert len(swarms) == 1
    assert swarms[0].id == swarm_id
    assert swarms[0].name == "test-swarm"
    assert len(swarms[0].agents) == 2
    assert swarms[0].agents[0].agent_name == "agent-1"
    assert swarms[0].agents[0].replicas == 2


def test_swarms_list_blueprints_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json=[
                {
                    "id": "research-triad",
                    "name": "Research Triad",
                    "summary": "One orchestrator, one scout, one executor",
                    "description": "Curated multi-agent preset",
                    "recommended_min_agents": 3,
                    "recommended_max_agents": 5,
                    "coordination_notes": "Review every loop.",
                    "tags": ["research"],
                    "roles": [
                        {
                            "id": "orchestrator",
                            "title": "Research Orchestrator",
                            "bundle_id": "orchestra-research-foundation",
                            "goal": "Own findings and routing",
                        }
                    ],
                }
            ],
        )

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        blueprints = Swarms(client).list_blueprints()

    assert captured["path"] == "/v1/swarms/blueprints"
    assert len(blueprints) == 1
    assert blueprints[0].id == "research-triad"
    assert blueprints[0].roles[0].bundle_id == "orchestra-research-foundation"


def test_swarms_get_hits_contract_route_and_maps_payload() -> None:
    swarm_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_swarm_payload(id=swarm_id, name="my-swarm"))

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        swarm = Swarms(client).get(swarm_id)

    assert captured["path"] == f"/v1/swarms/{swarm_id}"
    assert swarm.id == swarm_id
    assert swarm.name == "my-swarm"
    assert swarm.description == "A test swarm"
    assert swarm.min_replicas == 1
    assert swarm.max_replicas == 10


def test_swarms_create_hits_contract_route_and_maps_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(201, json=_swarm_payload(name="new-swarm"))

    agent_id_1 = str(uuid.uuid4())
    agent_id_2 = str(uuid.uuid4())

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        swarm = Swarms(client).create(
            name="new-swarm",
            agent_ids=[agent_id_1, agent_id_2],
            description="desc",
            min_replicas=2,
            max_replicas=8,
        )

    assert captured["path"] == "/v1/swarms"
    body = json.loads(captured["body"])
    assert body["name"] == "new-swarm"
    assert body["agent_ids"] == [agent_id_1, agent_id_2]
    assert body["description"] == "desc"
    assert body["min_replicas"] == 2
    assert body["max_replicas"] == 8
    assert swarm.name == "new-swarm"


def test_swarms_create_omits_description_when_none() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(201, json=_swarm_payload())

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        Swarms(client).create(name="no-desc", agent_ids=[str(uuid.uuid4())])

    body = json.loads(captured["body"])
    assert "description" not in body


def test_swarms_scale_hits_contract_route_and_maps_payload() -> None:
    swarm_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(200, json=_swarm_payload(id=swarm_id))

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        swarm = Swarms(client).scale(swarm_id, replicas=5)

    assert captured["path"] == f"/v1/swarms/{swarm_id}/scale"
    assert json.loads(captured["body"]) == {"replicas": 5}
    assert swarm.id == swarm_id


# ---------------------------------------------------------------------------
# Swarms — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_swarms_alist_hits_contract_route_and_maps_payload() -> None:
    swarm_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=_list_response([_swarm_payload(id=swarm_id)], 2))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        swarms, total = await Swarms(client).alist(skip=10, limit=20)

    assert captured["path"] == "/v1/swarms"
    assert captured["query"] == {"skip": "10", "limit": "20"}
    assert total == 2
    assert len(swarms) == 1
    assert swarms[0].id == swarm_id


@pytest.mark.asyncio
async def test_swarms_aget_hits_contract_route_and_maps_payload() -> None:
    swarm_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_swarm_payload(id=swarm_id))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        swarm = await Swarms(client).aget(swarm_id)

    assert captured["path"] == f"/v1/swarms/{swarm_id}"
    assert swarm.id == swarm_id


@pytest.mark.asyncio
async def test_swarms_acreate_hits_contract_route_and_maps_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(201, json=_swarm_payload(name="async-swarm"))

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as sync_client:
        Swarms(sync_client)._require_sync_client()  # exercise client-type guard

    agent_id = str(uuid.uuid4())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        swarm = await Swarms(client).acreate(
            name="async-swarm", agent_ids=[agent_id], min_replicas=3, max_replicas=7
        )

    assert captured["path"] == "/v1/swarms"
    body = json.loads(captured["body"])
    assert body["name"] == "async-swarm"
    assert body["agent_ids"] == [agent_id]
    assert body["min_replicas"] == 3
    assert body["max_replicas"] == 7
    assert swarm.name == "async-swarm"


@pytest.mark.asyncio
async def test_swarms_ascale_hits_contract_route_and_maps_payload() -> None:
    swarm_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(200, json=_swarm_payload(id=swarm_id))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        swarm = await Swarms(client).ascale(swarm_id, replicas=12)

    assert captured["path"] == f"/v1/swarms/{swarm_id}/scale"
    assert json.loads(captured["body"]) == {"replicas": 12}
    assert swarm.id == swarm_id


# ---------------------------------------------------------------------------
# Model parsers
# ---------------------------------------------------------------------------


def test_swarm_parser_maps_all_fields() -> None:
    swarm_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    payload = _swarm_payload(
        id=swarm_id,
        name="full-swarm",
        description="full desc",
        agent_ids=[agent_id],
        min_replicas=2,
        max_replicas=20,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-02T00:00:00",
    )

    swarm = Swarm(payload)

    assert swarm.id == swarm_id
    assert swarm.name == "full-swarm"
    assert swarm.description == "full desc"
    assert swarm.agent_ids == [agent_id]
    assert swarm.min_replicas == 2
    assert swarm.max_replicas == 20
    assert swarm.created_at.year == 2026
    assert swarm.updated_at.year == 2026
    assert len(swarm.agents) == 2


def test_swarm_parser_accepts_optional_description() -> None:
    payload = _swarm_payload()
    del payload["description"]

    swarm = Swarm(payload)

    assert swarm.description is None


def test_swarm_parser_nested_agents() -> None:
    agent_id = str(uuid.uuid4())
    payload = _swarm_payload(
        agents=[{"agent_id": agent_id, "agent_name": "alpha", "status": "running", "replicas": 4}]
    )

    swarm = Swarm(payload)

    assert len(swarm.agents) == 1
    assert swarm.agents[0].agent_id == agent_id
    assert swarm.agents[0].agent_name == "alpha"
    assert swarm.agents[0].status == "running"
    assert swarm.agents[0].replicas == 4


def test_swarm_repr() -> None:
    swarm = Swarm(_swarm_payload(id="swarm-123", name="repr-swarm"))
    assert "swarm-123" in repr(swarm)
    assert "repr-swarm" in repr(swarm)


def test_swarm_agent_repr() -> None:
    agent = SwarmAgent({"agent_id": "a1", "agent_name": "beta", "status": "idle", "replicas": 1})
    # SwarmAgent has the expected attributes but no custom __repr__
    assert agent.agent_id == "a1"
    assert agent.agent_name == "beta"
    assert agent.status == "idle"
    assert agent.replicas == 1


# ---------------------------------------------------------------------------
# Client-type guards
# ---------------------------------------------------------------------------


def test_sync_method_rejects_async_client() -> None:
    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        Swarms(httpx.AsyncClient(base_url="https://api.test/v1/")).list()


@pytest.mark.asyncio
async def test_async_method_rejects_sync_client() -> None:
    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await Swarms(httpx.Client(base_url="https://api.test/v1/")).alist()
