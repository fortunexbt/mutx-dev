from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from mutx import Deployments, Webhooks
from mutx.agents import Agent, AgentDetail, Agents


def _agent_payload(config: Any = None, **overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "name": "test-agent",
        "description": "sdk contract test",
        "status": "creating",
        "config": json.dumps(config if config is not None else {"model": "gpt-4o"}),
        "created_at": "2026-03-12T09:00:00",
        "updated_at": "2026-03-12T09:00:00",
        "user_id": str(uuid.uuid4()),
    }
    payload.update(overrides)
    return payload


def test_agent_parses_stringified_config_into_config_json_and_dict_alias() -> None:
    raw_config = {"model": "gpt-4o-mini", "temperature": 0.2}

    agent = Agent(_agent_payload(config=raw_config))

    assert agent.config == raw_config
    assert agent.config_json == json.dumps(raw_config)
    assert agent._data["config"] == agent.config_json


def test_agents_create_accepts_dict_config_and_sends_backend_json_string_contract() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_agent_payload(config={"model": "gpt-4o"}))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    agents = Agents(client)

    agents.create(
        name="demo",
        description="test",
        config={"model": "gpt-4o", "temperature": 0.1},
    )

    assert captured["path"] == "/v1/agents"
    assert isinstance(captured["json"]["config"], dict)
    assert captured["json"]["config"]["model"] == "gpt-4o"


def test_agents_create_accepts_json_string_config_and_preserves_it() -> None:
    captured: dict[str, Any] = {}
    raw_json = json.dumps({"model": "gpt-4o-mini", "temperature": 0.3})

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_agent_payload(config=json.loads(raw_json)))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    agents = Agents(client)

    agents.create(name="demo", config=raw_json)

    assert captured["json"]["config"] == raw_json


def test_top_level_sdk_exports_include_deployments_and_webhooks() -> None:
    assert Deployments is not None
    assert Webhooks is not None


def test_agent_detail_parses_nested_deployments_and_events() -> None:
    deployment_id = uuid.uuid4()
    detail = AgentDetail(
        _agent_payload(
            deployments=[
                {
                    "id": str(deployment_id),
                    "agent_id": str(uuid.uuid4()),
                    "status": "running",
                    "replicas": 2,
                    "node_id": "node-1",
                    "started_at": "2026-03-12T10:00:00",
                    "ended_at": None,
                    "error_message": None,
                    "events": [
                        {
                            "id": str(uuid.uuid4()),
                            "deployment_id": str(deployment_id),
                            "event_type": "deploy",
                            "status": "running",
                            "node_id": "node-1",
                            "error_message": None,
                            "created_at": "2026-03-12T10:00:01",
                        }
                    ],
                }
            ]
        )
    )

    assert len(detail.deployments) == 1
    assert detail.deployments[0].status == "running"
    assert detail.deployments[0].replicas == 2
    assert len(detail.deployments[0].events) == 1
    assert detail.deployments[0].events[0].event_type == "deploy"


def test_agent_logs_maps_backend_extra_data_field_to_sdk_aliases() -> None:
    agent_id = uuid.uuid4()
    log_payload = [
        {
            "id": str(uuid.uuid4()),
            "agent_id": str(agent_id),
            "level": "INFO",
            "message": "ready",
            "extra_data": '{"deployment_id":"abc"}',
            "timestamp": "2026-03-12T10:15:00",
        }
    ]

    client = httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"items": log_payload})
        ),
    )
    logs = Agents(client).logs(agent_id)

    assert logs[0].extra_data == '{"deployment_id":"abc"}'
    assert logs[0].metadata == '{"deployment_id":"abc"}'
