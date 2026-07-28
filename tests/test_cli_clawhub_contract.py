from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from click.testing import CliRunner

from cli.main import cli


class DummyConfig:
    def is_authenticated(self) -> bool:
        return True


class DummyResponse:
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> Any:
        return self._payload


def test_clawhub_list_hits_canonical_route_and_renders_skills(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    skill_id = str(uuid.uuid4())

    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        return DummyResponse(
            200,
            [
                {
                    "id": skill_id,
                    "name": "weather-skill",
                    "author": "fortunexbt",
                    "source": "orchestra-research",
                    "available": True,
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "calculator-skill",
                    "author": "openclaw",
                    "source": "workspace",
                    "available": False,
                },
            ],
        )

    monkeypatch.setattr("cli.commands.clawhub.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.clawhub.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["clawhub", "list"])

    assert result.exit_code == 0
    assert captured["path"] == "/v1/clawhub/skills"
    assert skill_id in result.output
    assert "weather-skill" in result.output
    assert "fortunexbt" in result.output
    assert "calculator-skill" in result.output
    assert "orchestra-research" in result.output


def test_clawhub_list_empty(monkeypatch) -> None:
    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        return DummyResponse(200, [])

    monkeypatch.setattr("cli.commands.clawhub.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.clawhub.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["clawhub", "list"])

    assert result.exit_code == 0
    assert "No skills found" in result.output


def test_clawhub_bundles_hits_canonical_route(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        return DummyResponse(
            200,
            [
                {
                    "id": "orchestra-research-foundation",
                    "name": "Research Foundation",
                    "skill_count": 8,
                    "available_skill_count": 6,
                    "recommended_template_id": "orchestra_research_foundation",
                }
            ],
        )

    monkeypatch.setattr("cli.commands.clawhub.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.clawhub.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["clawhub", "bundles"])

    assert result.exit_code == 0
    assert captured["path"] == "/v1/clawhub/bundles"
    assert "orchestra-research-foundation" in result.output
    assert "Research Foundation" in result.output
    assert "6/8" in result.output


def test_clawhub_install_hits_canonical_route(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())
    skill_id = str(uuid.uuid4())

    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["json"] = json
        return DummyResponse(200, {"status": "installing"})

    monkeypatch.setattr("cli.commands.clawhub.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.clawhub.get_client", lambda config: SimpleNamespace(post=fake_post)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["clawhub", "install", "-a", agent_id, "-s", skill_id])

    assert result.exit_code == 0
    assert captured["path"] == "/v1/clawhub/install"
    assert captured["json"] == {
        "agent_id": agent_id,
        "skill_id": skill_id,
    }
    assert f"Configured '{skill_id}' for agent {agent_id}" in result.output


def test_clawhub_install_agent_not_found(monkeypatch) -> None:
    agent_id = "nonexistent-agent"
    skill_id = str(uuid.uuid4())

    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        return DummyResponse(404, {"detail": "Agent not found"})

    monkeypatch.setattr("cli.commands.clawhub.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.clawhub.get_client", lambda config: SimpleNamespace(post=fake_post)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["clawhub", "install", "-a", agent_id, "-s", skill_id])

    assert result.exit_code == 1
    assert "Unknown skill or agent not found" in result.output
    assert "Configured" not in result.output


def test_clawhub_install_bundle_hits_canonical_route(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())

    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["json"] = json
        return DummyResponse(
            200,
            {
                "bundle_id": "orchestra-research-foundation",
                "configured_skill_ids": ["langchain", "llamaindex"],
                "runtime_ready_skill_ids": ["langchain"],
                "unavailable_skill_ids": ["0-autoresearch-skill"],
            },
        )

    monkeypatch.setattr("cli.commands.clawhub.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.clawhub.get_client", lambda config: SimpleNamespace(post=fake_post)
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "clawhub",
            "install-bundle",
            "-a",
            agent_id,
            "-b",
            "orchestra-research-foundation",
        ],
    )

    assert result.exit_code == 0
    assert captured["path"] == "/v1/clawhub/install-bundle"
    assert captured["json"] == {
        "agent_id": agent_id,
        "bundle_id": "orchestra-research-foundation",
    }
    assert "2 configured, 1 runtime-ready, 1 unavailable" in result.output


def test_clawhub_uninstall_hits_canonical_route(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    agent_id = str(uuid.uuid4())
    skill_id = str(uuid.uuid4())

    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["json"] = json
        return DummyResponse(200, {"status": "uninstalled"})

    monkeypatch.setattr("cli.commands.clawhub.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.clawhub.get_client", lambda config: SimpleNamespace(post=fake_post)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["clawhub", "uninstall", "-a", agent_id, "-s", skill_id])

    assert result.exit_code == 0
    assert captured["path"] == "/v1/clawhub/uninstall"
    assert captured["json"] == {
        "agent_id": agent_id,
        "skill_id": skill_id,
    }
    assert f"Removed configuration for '{skill_id}' from agent {agent_id}" in result.output


def test_clawhub_uninstall_agent_not_found(monkeypatch) -> None:
    agent_id = "nonexistent-agent"
    skill_id = str(uuid.uuid4())

    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        return DummyResponse(404, {"detail": "Agent not found"})

    monkeypatch.setattr("cli.commands.clawhub.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.clawhub.get_client", lambda config: SimpleNamespace(post=fake_post)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["clawhub", "uninstall", "-a", agent_id, "-s", skill_id])

    assert result.exit_code == 1
    assert f"Error: Agent {agent_id} not found" in result.output
    assert "Removed configuration" not in result.output
