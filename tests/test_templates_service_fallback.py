from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.config import CLIConfig
from cli.errors import APIRequestError
from cli.services.assistant import TemplatesService


class DummyResponse:
    def __init__(self, status_code: int, payload: dict[str, object]):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict[str, object]:
        return self._payload


class DummyClient:
    def __init__(self, calls: list[tuple[str, dict[str, object]]]):
        self.calls = calls

    def post(self, path: str, **kwargs):
        payload = kwargs.get("json") or {}
        self.calls.append((path, payload))
        if path == "/v1/templates/personal_assistant/deploy":
            return DummyResponse(500, {"detail": "internal error"})
        if path == "/v1/agents":
            return DummyResponse(
                201,
                {
                    "id": "agent-pa-01",
                    "name": payload.get("name", "Personal Assistant"),
                    "type": "openclaw",
                    "config": payload.get("config", {}),
                },
            )
        if path == "/v1/deployments":
            return DummyResponse(
                201,
                {
                    "id": "dep-pa-01",
                    "agent_id": payload.get("agent_id", "agent-pa-01"),
                    "status": "pending",
                    "replicas": payload.get("replicas", 1),
                },
            )
        raise AssertionError(f"Unexpected path: {path}")

    def close(self) -> None:
        return None


def test_templates_service_surfaces_authoritative_deploy_failure(tmp_path: Path) -> None:
    config = CLIConfig(config_path=tmp_path / "config.json")
    config.access_token = "access-token"
    config.refresh_token = "refresh-token"
    calls: list[tuple[str, dict[str, object]]] = []
    service = TemplatesService(
        config=config,
        client_factory=lambda _config: DummyClient(calls),
    )

    with pytest.raises(APIRequestError, match="internal error") as exc_info:
        service.deploy_template(
            "personal_assistant",
            name="Personal Assistant",
            assistant_id="personal-assistant",
            workspace="/tmp/openclaw/workspace-personal-assistant",
            runtime_metadata={"install_method": "npm"},
        )

    assert exc_info.value.status_code == 500
    assert [path for path, _payload in calls] == [
        "/v1/templates/personal_assistant/deploy",
    ]
