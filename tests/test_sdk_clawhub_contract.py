from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from mutx.clawhub import ClawHub, Skill, SkillBundle


def _skill_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": f"skill-{uuid.uuid4().hex[:8]}",
        "name": "test-skill",
        "description": "SDK contract test skill",
        "author": "mutx",
        "stars": 42,
        "category": "productivity",
        "is_official": True,
        "available": True,
        "source": "orchestra-research",
    }
    payload.update(overrides)
    return payload


def _bundle_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "orchestra-research-foundation",
        "name": "Research Foundation",
        "summary": "Core research pack",
        "description": "Curated bundle for research loops",
        "skill_ids": ["langchain", "llamaindex"],
        "skill_count": 2,
        "available_skill_count": 2,
        "unavailable_skill_ids": [],
        "recommended_template_id": "orchestra_research_foundation",
        "recommended_swarm_blueprint_id": "research-triad",
        "tags": ["research"],
        "source": "orchestra-research",
    }
    payload.update(overrides)
    return payload


def test_clawhub_list_skills_parses_sync_skill_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/clawhub/skills"
        return httpx.Response(200, json=[_skill_payload()])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    clawhub = ClawHub(client)

    skills = clawhub.list_skills()

    assert len(skills) == 1
    assert isinstance(skills[0], Skill)
    assert skills[0].name == "test-skill"
    assert skills[0].source == "orchestra-research"
    assert skills[0].available is True


@pytest.mark.asyncio
async def test_clawhub_alist_skills_parses_async_skill_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/clawhub/skills"
        return httpx.Response(200, json=[_skill_payload(name="async-skill")])

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        clawhub = ClawHub(client)

        skills = await clawhub.alist_skills()

    assert len(skills) == 1
    assert isinstance(skills[0], Skill)
    assert skills[0].name == "async-skill"


def test_clawhub_list_bundles_parses_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/clawhub/bundles"
        return httpx.Response(200, json=[_bundle_payload()])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    clawhub = ClawHub(client)

    bundles = clawhub.list_bundles()

    assert len(bundles) == 1
    assert isinstance(bundles[0], SkillBundle)
    assert bundles[0].recommended_template_id == "orchestra_research_foundation"


@pytest.mark.asyncio
async def test_clawhub_alist_bundles_parses_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/clawhub/bundles"
        return httpx.Response(200, json=[_bundle_payload(name="Async Bundle")])

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        clawhub = ClawHub(client)
        bundles = await clawhub.alist_bundles()

    assert len(bundles) == 1
    assert bundles[0].name == "Async Bundle"


@pytest.mark.asyncio
async def test_clawhub_ainstall_skill_returns_json_without_awaiting_plain_dict() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"ok": True, "agent_id": captured["json"]["agent_id"]})

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        clawhub = ClawHub(client)

        result = await clawhub.ainstall_skill(agent_id=uuid.uuid4(), skill_id="skill-demo")

    assert captured["path"] == "/v1/clawhub/install"
    assert captured["json"]["skill_id"] == "skill-demo"
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_clawhub_ainstall_bundle_returns_json_without_awaiting_plain_dict() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"ok": True, "bundle_id": captured["json"]["bundle_id"]})

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        clawhub = ClawHub(client)

        result = await clawhub.ainstall_bundle(
            agent_id=uuid.uuid4(), bundle_id="orchestra-research-foundation"
        )

    assert captured["path"] == "/v1/clawhub/install-bundle"
    assert captured["json"]["bundle_id"] == "orchestra-research-foundation"
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_clawhub_auninstall_skill_returns_json_without_awaiting_plain_dict() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"ok": True, "skill_id": captured["json"]["skill_id"]})

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        clawhub = ClawHub(client)

        result = await clawhub.auninstall_skill(agent_id=uuid.uuid4(), skill_id="skill-demo")

    assert captured["path"] == "/v1/clawhub/uninstall"
    assert captured["json"]["skill_id"] == "skill-demo"
    assert result["ok"] is True
