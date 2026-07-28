from __future__ import annotations

from datetime import datetime, timezone
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


def test_webhooks_list_hits_contract_route_and_forwards_filters(monkeypatch) -> None:
    captured: list[tuple[str, dict[str, Any] | None]] = []

    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        captured.append((path, params))
        if path == "/v1/webhooks/":
            return DummyResponse(
                200,
                {
                    "items": [
                        {
                            "id": "wh-123",
                            "url": "https://example.com/hook",
                            "is_active": True,
                            "events": ["agent.status"],
                        }
                    ]
                },
            )

        return DummyResponse(
            200,
            {
                "items": [
                    {
                        "id": "delivery-1",
                        "event": "agent.status",
                        "success": True,
                        "attempts": 1,
                        "status_code": 204,
                        "created_at": "2026-03-14T16:00:00",
                        "delivered_at": "2026-03-14T16:00:01",
                    }
                ]
            },
        )

    monkeypatch.setattr("cli.commands.webhooks.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.operator_readiness.utc_now", lambda: datetime(2026, 3, 15, 16, 0, tzinfo=timezone.utc)
    )
    monkeypatch.setattr(
        "cli.commands.webhooks.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["webhooks", "list", "--limit", "25", "--skip", "5"])

    assert result.exit_code == 0
    assert captured == [
        ("/v1/webhooks/", {"limit": 25, "skip": 5}),
        ("/v1/webhooks/wh-123/deliveries", {"limit": 5, "skip": 0}),
    ]
    assert "wh-123 | https://example.com/hook | state=active | delivery=healthy" in result.output
    assert "events: agent.status" in result.output


def test_webhooks_deliveries_hits_live_delivery_route_and_query_contract(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    webhook_id = "wh-delivery-1"

    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["params"] = params
        return DummyResponse(
            200,
            {
                "items": [
                    {
                        "id": "delivery-1",
                        "event": "agent.status",
                        "success": False,
                        "attempts": 2,
                        "status_code": 502,
                        "delivered_at": None,
                        "created_at": "2026-03-12T15:00:00",
                    }
                ]
            },
        )

    monkeypatch.setattr("cli.commands.webhooks.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.webhooks.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "webhooks",
            "deliveries",
            webhook_id,
            "--skip",
            "3",
            "--limit",
            "10",
            "--event",
            "agent.status",
            "--success",
            "true",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "path": f"/v1/webhooks/{webhook_id}/deliveries",
        "params": {
            "skip": 3,
            "limit": 10,
            "event": "agent.status",
            "success": True,
        },
    }
    assert (
        "delivery-1 | event=agent.status | success=False | attempts=2 | status=502" in result.output
    )


def test_webhooks_get_hits_contract_route_and_prints_created_timestamp(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_get(path: str, params: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["params"] = params
        return DummyResponse(
            200,
            {
                "id": "wh-456",
                "url": "https://example.com/hook",
                "is_active": False,
                "events": ["deployment.failed"],
                "created_at": "2026-03-12T15:00:00",
            },
        )

    monkeypatch.setattr("cli.commands.webhooks.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.webhooks.get_client", lambda config: SimpleNamespace(get=fake_get)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["webhooks", "get", "wh-456"])

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/webhooks/wh-456",
        "params": None,
    }
    assert "wh-456 | https://example.com/hook | state=inactive" in result.output
    assert "Created: 2026-03-12T15:00:00" in result.output


def test_webhooks_test_hits_live_contract_route(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["json"] = json
        return DummyResponse(
            200,
            {
                "status": "test_delivered",
                "message": "Test event delivered successfully",
            },
        )

    monkeypatch.setattr("cli.commands.webhooks.current_config", lambda: DummyConfig())
    monkeypatch.setattr(
        "cli.commands.webhooks.get_client", lambda config: SimpleNamespace(post=fake_post)
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["webhooks", "test", "wh-789"])

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/webhooks/wh-789/test",
        "json": None,
    }
    assert "Triggered webhook test: wh-789" in result.output
    assert "Test event delivered successfully" in result.output
