from __future__ import annotations

import json

from click.testing import CliRunner

from cli.main import cli


class _DummyConfig:
    def is_authenticated(self) -> bool:
        return True


class _DummyResponse:
    def __init__(self, payload: dict):
        self.status_code = 200
        self._payload = payload
        self.text = json.dumps(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _DummyClient:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []

    def get(self, path: str):
        self.calls.append(("GET", path, None))
        if path == "/v1/governance/attestations":
            return _DummyResponse(
                {
                    "summary": {
                        "identities": 2,
                        "discovery_items": 3,
                        "credential_backends": 1,
                        "supervised_agents": 1,
                        "pending_approvals": 0,
                    },
                    "coverage": {
                        "runtime_guardrail_presence": True,
                        "receipt_integrity": True,
                    },
                    "compliance": {"overall_satisfied": True},
                }
            )
        if path == "/v1/governance/trust":
            return _DummyResponse(
                {
                    "items": [
                        {
                            "agent_id": "agent-1",
                            "trust_score": 700,
                            "trust_tier": "elevated",
                            "lifecycle_status": "active",
                        }
                    ]
                }
            )
        if path == "/v1/governance/lifecycle":
            return _DummyResponse(
                {
                    "items": [
                        {
                            "agent_id": "agent-1",
                            "lifecycle_status": "active",
                            "credential_status": "brokered",
                        }
                    ]
                }
            )
        if path == "/v1/governance/discovery":
            return _DummyResponse(
                {
                    "items": [
                        {
                            "entity_id": "codex:session-1",
                            "entity_type": "local_session",
                            "risk_level": "high",
                            "registration_status": "unregistered",
                        }
                    ]
                }
            )
        raise AssertionError(f"Unexpected GET path {path}")

    def post(self, path: str, json: dict | None = None):
        self.calls.append(("POST", path, json))
        if path == "/v1/governance/attestations/verify":
            return _DummyResponse(
                {"summary": {"identities": 2, "discovery_items": 3, "credential_backends": 1}}
            )
        if path.startswith("/v1/governance/trust/"):
            return _DummyResponse(
                {
                    "agent_id": "agent-1",
                    "trust_score": json.get("score", 0) if json else 0,
                    "trust_tier": "trusted",
                }
            )
        if path.startswith("/v1/governance/lifecycle/"):
            return _DummyResponse({"agent_id": "agent-1", "lifecycle_status": json.get("state")})
        if path == "/v1/governance/discovery/scan":
            return _DummyResponse({"count": 4, "scanned_at": "2026-04-17T12:00:00Z"})
        raise AssertionError(f"Unexpected POST path {path}")


def test_governance_doctor_command(monkeypatch) -> None:
    client = _DummyClient()
    monkeypatch.setattr("cli.config.current_config", _DummyConfig)
    monkeypatch.setattr("cli.config.get_client", lambda _config: client)

    result = CliRunner().invoke(cli, ["governance", "doctor"])

    assert result.exit_code == 0
    assert "Governance Doctor" in result.output
    assert ("GET", "/v1/governance/attestations", None) in client.calls


def test_governance_verify_json_command(monkeypatch) -> None:
    client = _DummyClient()
    monkeypatch.setattr("cli.config.current_config", _DummyConfig)
    monkeypatch.setattr("cli.config.get_client", lambda _config: client)

    result = CliRunner().invoke(cli, ["governance", "verify", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["summary"]["identities"] == 2
    assert ("POST", "/v1/governance/attestations/verify", None) in client.calls


def test_governance_trust_list_command(monkeypatch) -> None:
    client = _DummyClient()
    monkeypatch.setattr("cli.config.current_config", _DummyConfig)
    monkeypatch.setattr("cli.config.get_client", lambda _config: client)

    result = CliRunner().invoke(cli, ["governance", "trust", "list"])

    assert result.exit_code == 0
    assert "agent-1" in result.output
    assert ("GET", "/v1/governance/trust", None) in client.calls


def test_governance_lifecycle_set_command(monkeypatch) -> None:
    client = _DummyClient()
    monkeypatch.setattr("cli.config.current_config", _DummyConfig)
    monkeypatch.setattr("cli.config.get_client", lambda _config: client)

    result = CliRunner().invoke(
        cli,
        ["governance", "lifecycle", "set", "agent-1", "suspended", "--reason", "pause"],
    )

    assert result.exit_code == 0
    assert "suspended" in result.output
    assert (
        "POST",
        "/v1/governance/lifecycle/agent-1",
        {"state": "suspended", "reason": "pause", "apply_runtime_action": True},
    ) in client.calls


def test_governance_lifecycle_set_omits_empty_reason(monkeypatch) -> None:
    client = _DummyClient()
    monkeypatch.setattr("cli.config.current_config", _DummyConfig)
    monkeypatch.setattr("cli.config.get_client", lambda _config: client)

    result = CliRunner().invoke(cli, ["governance", "lifecycle", "set", "agent-1", "active"])

    assert result.exit_code == 0
    assert (
        "POST",
        "/v1/governance/lifecycle/agent-1",
        {"state": "active", "apply_runtime_action": True},
    ) in client.calls


def test_governance_discovery_scan_command(monkeypatch) -> None:
    client = _DummyClient()
    monkeypatch.setattr("cli.config.current_config", _DummyConfig)
    monkeypatch.setattr("cli.config.get_client", lambda _config: client)

    result = CliRunner().invoke(cli, ["governance", "discovery", "scan"])

    assert result.exit_code == 0
    assert "Scanned 4 entities" in result.output
    assert ("POST", "/v1/governance/discovery/scan", None) in client.calls
