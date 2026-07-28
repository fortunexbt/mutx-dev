from __future__ import annotations

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


def test_deploy_events_hits_contract_route_and_renders_items(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["params"] = params
        return DummyResponse(
            200,
            {
                "deployment_id": "dep-123",
                "deployment_status": "running",
                "items": [
                    {
                        "created_at": "2026-03-12T15:00:00",
                        "event_type": "scale",
                        "status": "running",
                        "node_id": "node-1",
                    }
                ],
            },
        )

    monkeypatch.setattr("cli.commands.deploy.current_config", DummyConfig)
    monkeypatch.setattr(
        "cli.commands.deploy.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "events",
            "dep-123",
            "--limit",
            "25",
            "--skip",
            "10",
            "--event-type",
            "scale",
            "--status",
            "running",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/deployments/dep-123/events",
        "params": {
            "limit": 25,
            "skip": 10,
            "event_type": "scale",
            "status": "running",
        },
    }
    assert "Deployment: dep-123 | status: running" in result.output
    assert "scale | running | node: node-1" in result.output


def test_deploy_list_passes_agent_and_status_filters(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["params"] = params
        return DummyResponse(
            200,
            {
                "items": [
                    {
                        "id": "dep-123",
                        "agent_id": "agent-123",
                        "status": "running",
                        "replicas": 2,
                    }
                ],
                "total": 1,
                "skip": 2,
                "limit": 5,
                "has_more": False,
            },
        )

    monkeypatch.setattr("cli.commands.deploy.current_config", DummyConfig)
    monkeypatch.setattr(
        "cli.commands.deploy.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "list",
            "--limit",
            "5",
            "--skip",
            "2",
            "--agent-id",
            "agent-123",
            "--status",
            "running",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/deployments",
        "params": {
            "limit": 5,
            "skip": 2,
            "agent_id": "agent-123",
            "status": "running",
        },
    }
    assert "dep-123 | agent-123 | running | replicas: 2" in result.output


def test_deploy_create_hits_canonical_route_with_replicas(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["json"] = json
        return DummyResponse(201, {"id": "dep-456", "status": "pending"})

    monkeypatch.setattr("cli.commands.deploy.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.deploy.get_client", lambda config: SimpleNamespace(post=fake_post)
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deploy", "create", "--agent-id", "agent-123", "--replicas", "3"],
    )

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/deployments",
        "json": {"agent_id": "agent-123", "replicas": 3},
    }
    assert "Created deployment: dep-456" in result.output
    assert "Status: pending" in result.output


def test_deploy_restart_hits_contract_route_and_renders_status(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["json"] = json
        return DummyResponse(200, {"id": "dep-789", "status": "pending"})

    monkeypatch.setattr("cli.commands.deploy.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.deploy.get_client", lambda config: SimpleNamespace(post=fake_post)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["deploy", "restart", "dep-789"])

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/deployments/dep-789/restart",
        "json": None,
    }
    assert "Restarted deployment: dep-789" in result.output
    assert "Status: pending" in result.output


def test_deploy_versions_hits_contract_route_and_renders_snapshot(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["params"] = params
        return DummyResponse(
            200,
            {
                "deployment_id": "dep-123",
                "items": [
                    {
                        "id": "ver-2",
                        "deployment_id": "dep-123",
                        "version": 2,
                        "config_snapshot": '{"replicas": 2, "version": "v1.2.0"}',
                        "status": "current",
                        "created_at": "2026-03-12T16:00:00",
                        "rolled_back_at": None,
                    },
                    {
                        "id": "ver-1",
                        "deployment_id": "dep-123",
                        "version": 1,
                        "config_snapshot": '{"replicas": 1, "version": "v1.1.0"}',
                        "status": "superseded",
                        "created_at": "2026-03-11T16:00:00",
                        "rolled_back_at": "2026-03-12T16:00:00",
                    },
                ],
                "total": 2,
            },
        )

    monkeypatch.setattr("cli.commands.deploy.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.deploy.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["deploy", "versions", "dep-123"])

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/deployments/dep-123/versions",
        "params": None,
    }
    assert "Deployment: dep-123 | versions: 2" in result.output
    assert (
        "v2 | current | created: 2026-03-12T16:00:00 | runtime version: v1.2.0 | replicas: 2"
        in result.output
    )
    assert "rolled back: 2026-03-12T16:00:00" in result.output


def test_deploy_rollback_hits_contract_route_and_renders_new_state(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["json"] = json
        return DummyResponse(
            200,
            {
                "id": "dep-789",
                "status": "running",
                "version": "v1.1.0",
                "replicas": 1,
            },
        )

    monkeypatch.setattr("cli.commands.deploy.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.deploy.get_client", lambda config: SimpleNamespace(post=fake_post)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["deploy", "rollback", "dep-789", "--version", "1"])

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/deployments/dep-789/rollback",
        "json": {"version": 1},
    }
    assert "Rolled back deployment: dep-789" in result.output
    assert "Status: running" in result.output
    assert "Version: v1.1.0" in result.output
    assert "Replicas: 1" in result.output


def test_deploy_logs_hits_contract_route_and_supports_level_filter(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["params"] = params
        return DummyResponse(
            200,
            {
                "deployment_id": "dep-123",
                "items": [
                    {
                        "timestamp": "2026-03-12T15:05:00",
                        "level": "ERROR",
                        "message": "probe failed",
                    }
                ],
                "total": 1,
                "skip": 3,
                "limit": 20,
                "has_more": False,
            },
        )

    monkeypatch.setattr("cli.commands.deploy.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.deploy.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deploy", "logs", "dep-123", "--limit", "20", "--skip", "3", "--level", "ERROR"],
    )

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/deployments/dep-123/logs",
        "params": {
            "limit": 20,
            "skip": 3,
            "level": "ERROR",
        },
    }
    assert "2026-03-12T15:05:00 | ERROR | probe failed" in result.output


def test_deploy_metrics_hits_contract_route_and_renders_points(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["params"] = params
        return DummyResponse(
            200,
            {
                "deployment_id": "dep-123",
                "items": [
                    {
                        "timestamp": "2026-03-12T15:10:00",
                        "cpu_usage": 0.5,
                        "memory_usage": 0.75,
                    }
                ],
                "total": 1,
                "skip": 1,
                "limit": 10,
                "has_more": False,
            },
        )

    monkeypatch.setattr("cli.commands.deploy.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.deploy.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deploy", "metrics", "dep-123", "--limit", "10", "--skip", "1"],
    )

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/deployments/dep-123/metrics",
        "params": {
            "limit": 10,
            "skip": 1,
        },
    }
    assert "2026-03-12T15:10:00 | cpu: 0.5 | memory: 0.75" in result.output
