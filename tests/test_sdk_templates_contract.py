"""Contract tests for sdk.mutx.templates."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from mutx.templates import AssistantTemplate, TemplateDeployResponse, Templates


# ---------------------------------------------------------------------------
# Fixtures / payload builders
# ---------------------------------------------------------------------------


def _template_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "name": "Test Template",
        "description": "A test assistant template.",
        "category": "productivity",
        "icon": "🤖",
        "default_model": "gpt-4o",
        "skills": ["skill-1", "skill-2"],
        "config": {"temperature": 0.7, "max_tokens": 4096},
    }
    payload.update(overrides)
    return payload


def _deploy_payload(template_id: str, **overrides: Any) -> dict[str, Any]:
    payload = {
        "template_id": template_id,
        "agent": {
            "id": str(uuid.uuid4()),
            "name": "Deployed Agent",
            "description": "Agent created from template.",
            "status": "pending",
        },
        "deployment": {
            "id": str(uuid.uuid4()),
            "agent_id": str(uuid.uuid4()),
            "status": "pending",
            "replicas": 1,
            "node_id": "node-1",
            "started_at": "2026-03-12T09:00:00",
            "ended_at": None,
            "error_message": None,
        },
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# AssistantTemplate parser tests
# ---------------------------------------------------------------------------


def test_assistant_template_parser_maps_all_fields() -> None:
    data = _template_payload()
    tpl = AssistantTemplate(data)

    assert tpl.id == data["id"]
    assert tpl.name == data["name"]
    assert tpl.description == data["description"]
    assert tpl.category == data["category"]
    assert tpl.icon == data["icon"]
    assert tpl.default_model == data["default_model"]
    assert tpl.skills == data["skills"]
    assert tpl.config == data["config"]
    assert tpl._data == data


def test_assistant_template_parser_defaults_optional_fields() -> None:
    minimal = {"id": str(uuid.uuid4()), "name": "Minimal"}
    tpl = AssistantTemplate(minimal)

    assert tpl.description == ""
    assert tpl.category == ""
    assert tpl.icon is None
    assert tpl.default_model is None
    assert tpl.skills == []
    assert tpl.config == {}


def test_assistant_template_repr() -> None:
    data = _template_payload(name="Repr Test")
    tpl = AssistantTemplate(data)
    assert "Repr Test" in repr(tpl)


# ---------------------------------------------------------------------------
# TemplateDeployResponse parser tests
# ---------------------------------------------------------------------------


def test_template_deploy_response_parser_maps_fields() -> None:
    template_id = str(uuid.uuid4())
    data = _deploy_payload(template_id)
    resp = TemplateDeployResponse(data)

    assert resp.template_id == template_id
    assert isinstance(resp.agent, dict)
    assert isinstance(resp.deployment, dict)
    assert resp._data == data


# ---------------------------------------------------------------------------
# Templates.list / alist — sync + async
# ---------------------------------------------------------------------------


def test_templates_list_hits_route_and_maps_results() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=[_template_payload(), _template_payload(name="Two")])

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        templates = Templates(client).list()

    assert captured["path"] == "/v1/templates"
    assert len(templates) == 2
    assert templates[0].name == "Test Template"
    assert templates[1].name == "Two"


@pytest.mark.asyncio
async def test_templates_alist_hits_route_and_maps_results() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=[_template_payload(name="Async Template")])

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        templates = await Templates(client).alist()

    assert captured["path"] == "/v1/templates"
    assert len(templates) == 1
    assert templates[0].name == "Async Template"


@pytest.mark.asyncio
async def test_templates_list_rejects_async_client() -> None:
    async with httpx.AsyncClient(base_url="https://api.test/v1/") as client:
        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            Templates(client).list()


@pytest.mark.asyncio
async def test_templates_alist_rejects_sync_client() -> None:
    with httpx.Client(base_url="https://api.test/v1/") as client:
        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await Templates(client).alist()


# ---------------------------------------------------------------------------
# Templates.deploy / adeploy — sync + async
# ---------------------------------------------------------------------------


def test_templates_deploy_hits_route_and_maps_payload() -> None:
    template_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(200, json=_deploy_payload(template_id))

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        resp = Templates(client).deploy(
            template_id=template_id,
            name="My Agent",
            description="A description",
            model="gpt-4o",
            workspace="/workspace/test",
            skills=["skill-a", "skill-b"],
            channels={"discord": {"enabled": True}},
            replicas=3,
            runtime_metadata={"env": "test"},
        )

    assert captured["path"] == f"/v1/templates/{template_id}/deploy"
    body = json.loads(captured["body"])
    assert body["name"] == "My Agent"
    assert body["description"] == "A description"
    assert body["model"] == "gpt-4o"
    assert body["workspace"] == "/workspace/test"
    assert body["skills"] == ["skill-a", "skill-b"]
    assert body["channels"] == {"discord": {"enabled": True}}
    assert body["replicas"] == 3
    assert body["runtime_metadata"] == {"env": "test"}

    assert isinstance(resp, TemplateDeployResponse)
    assert resp.template_id == template_id


def test_templates_deploy_omits_optional_null_fields() -> None:
    template_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, json=_deploy_payload(template_id))

    with httpx.Client(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        Templates(client).deploy(template_id=template_id, name="Minimal Agent")

    body = json.loads(captured["body"])
    # Only name and replicas should be present; optional fields must be omitted
    assert "name" in body
    assert "replicas" in body
    assert "description" not in body
    assert "model" not in body
    assert "workspace" not in body
    assert "skills" not in body
    assert "channels" not in body
    assert "runtime_metadata" not in body


@pytest.mark.asyncio
async def test_templates_deploy_rejects_async_client() -> None:
    async with httpx.AsyncClient(base_url="https://api.test/v1/") as client:
        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            Templates(client).deploy(template_id=str(uuid.uuid4()), name="Agent")


@pytest.mark.asyncio
async def test_templates_adeploy_hits_route_and_maps_payload() -> None:
    template_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(200, json=_deploy_payload(template_id))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        resp = await Templates(client).adeploy(
            template_id=template_id,
            name="Async Agent",
            replicas=2,
        )

    assert captured["path"] == f"/v1/templates/{template_id}/deploy"
    body = json.loads(captured["body"])
    assert body["name"] == "Async Agent"
    assert body["replicas"] == 2
    assert isinstance(resp, TemplateDeployResponse)


@pytest.mark.asyncio
async def test_templates_adeploy_rejects_sync_client() -> None:
    with httpx.Client(base_url="https://api.test/v1/") as client:
        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await Templates(client).adeploy(template_id=str(uuid.uuid4()), name="Agent")
