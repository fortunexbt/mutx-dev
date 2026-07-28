from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.openclaw_runtime import (
    _build_openclaw_install_command,
    _is_supported_openclaw_node_version,
    OpenClawAgentBinding,
    OpenClawGatewayHealth,
    build_openclaw_surface_command,
    ensure_personal_assistant_binding,
    get_gateway_health,
    inspect_importable_openclaw_runtime,
    install_openclaw,
    list_local_sessions,
    merge_runtime_binding,
    persist_openclaw_runtime_snapshot,
    resolve_gateway_auth_argument,
    update_binding_governance,
)
from cli.errors import ValidationError
from cli.runtime_registry import (
    load_binding,
    load_manifest,
    load_wizard_state,
    provider_pointers_dir,
    reset_wizard_state,
    write_pointer,
)


def test_openclaw_npm_install_is_release_pinned() -> None:
    command = _build_openclaw_install_command(
        install_method="npm",
        non_interactive=True,
    )

    assert "--install-method npm" in command
    assert "--version 2026.7.1" in command
    assert "/2d2ddc43d0dcf71f31283d780f9fe9ff4cc04fe4/scripts/install.sh" in command
    assert command.endswith("--no-prompt")
    assert "latest" not in command


def test_openclaw_git_install_fetches_an_immutable_script() -> None:
    command = _build_openclaw_install_command(
        install_method="git",
        non_interactive=True,
    )

    commit = "2d2ddc43d0dcf71f31283d780f9fe9ff4cc04fe4"
    assert f"/{commit}/scripts/install.sh" in command
    assert f"--version {commit}" in command
    assert command.endswith("--no-prompt")


def test_openclaw_node_runtime_contract_matches_upstream() -> None:
    assert _is_supported_openclaw_node_version("v22.22.3") is True
    assert _is_supported_openclaw_node_version("24.15.0") is True
    assert _is_supported_openclaw_node_version("v25.9.0") is True
    assert _is_supported_openclaw_node_version("v22.22.2") is False
    assert _is_supported_openclaw_node_version("v23.11.1") is False
    assert _is_supported_openclaw_node_version("v24.14.9") is False


def test_autonomy_runbook_keeps_node_and_npm_on_the_shared_node24_lane() -> None:
    runbook = (Path(__file__).resolve().parents[1] / "docs" / "autonomy-runbook.md").read_text(
        encoding="utf-8"
    )

    assert "/node24/bin/node" in runbook
    assert "/node24/bin/npm" in runbook
    assert "/node22/bin/npm" not in runbook
    assert "Node 24.15+ is the shared supported intersection" in runbook


@pytest.mark.parametrize("install_method", ["npm", "git"])
def test_official_installer_can_bootstrap_node(monkeypatch, install_method: str) -> None:
    commands: list[str] = []
    monkeypatch.setattr(
        "cli.openclaw_runtime._require_supported_openclaw_node",
        lambda: pytest.fail("the official installer must own its Node bootstrap"),
    )
    monkeypatch.setattr("cli.openclaw_runtime._run_bash", commands.append)
    monkeypatch.setattr("cli.openclaw_runtime.find_openclaw_bin", lambda: "/usr/bin/openclaw")

    resolved = install_openclaw(install_method=install_method, non_interactive=True)

    assert resolved == "/usr/bin/openclaw"
    assert commands and f"--install-method {install_method}" in commands[0]


def test_get_gateway_health_reports_needs_onboard_when_cli_exists_without_config(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "cli.openclaw_runtime.find_openclaw_bin", lambda: "/opt/homebrew/bin/openclaw"
    )
    monkeypatch.setattr("cli.openclaw_runtime.detect_openclaw_config_path", lambda: None)
    monkeypatch.setattr("cli.openclaw_runtime.detect_openclaw_state_dir", lambda: None)
    monkeypatch.setattr("cli.openclaw_runtime.detect_gateway_port", lambda: None)

    health = get_gateway_health()

    assert health.status == "needs_onboard"
    assert health.installed is True
    assert health.onboarded is False


def test_ensure_personal_assistant_binding_reuses_existing_agent(monkeypatch) -> None:
    monkeypatch.setattr(
        "cli.openclaw_runtime.list_openclaw_agents",
        lambda: [
            {
                "id": "personal-assistant",
                "workspace": "/tmp/openclaw/workspace-personal-assistant",
                "agentDir": "/tmp/openclaw/agents/personal-assistant/agent",
                "model": "openai-codex/gpt-5.4",
            }
        ],
    )
    monkeypatch.setattr("cli.openclaw_runtime.detect_gateway_port", lambda: 18789)

    binding = ensure_personal_assistant_binding(
        assistant_name="Personal Assistant",
        install_method="npm",
    )

    assert binding.created is False
    assert binding.agent_id == "personal-assistant"
    assert binding.workspace == "/tmp/openclaw/workspace-personal-assistant"


def test_merge_runtime_binding_updates_assistant_identity() -> None:
    binding = OpenClawAgentBinding(
        agent_id="personal-assistant",
        workspace="/tmp/openclaw/workspace-personal-assistant",
        agent_dir="/tmp/openclaw/agents/personal-assistant/agent",
        model="openai-codex/gpt-5.4",
        install_method="npm",
        gateway_port=18789,
        created=True,
    )
    health = OpenClawGatewayHealth(
        status="healthy",
        cli_available=True,
        installed=True,
        onboarded=True,
        gateway_configured=True,
        gateway_reachable=True,
        gateway_port=18789,
        gateway_url="http://127.0.0.1:18789",
        credential_detected=True,
        config_path="/tmp/openclaw.json",
        state_dir="/tmp/.openclaw",
        doctor_summary="Gateway is reachable and ready for assistant operations.",
    )

    payload = merge_runtime_binding({"metadata": {"starter": True}}, binding=binding, health=health)

    assert payload["assistant_id"] == "personal-assistant"
    assert payload["workspace"] == "/tmp/openclaw/workspace-personal-assistant"
    assert payload["metadata"]["runtime"]["managed_by_mutx"] is True
    assert payload["metadata"]["runtime"]["gateway_status"] == "healthy"


def test_list_local_sessions_reads_openclaw_store(monkeypatch, tmp_path: Path) -> None:
    state_dir = tmp_path / ".openclaw"
    sessions_dir = state_dir / "agents" / "personal-assistant" / "sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "sessions.json").write_text(
        json.dumps(
            {
                "abc": {
                    "sessionId": "session-01",
                    "updatedAt": 1_700_000_000_000,
                    "totalTokens": 2500,
                    "contextTokens": 8000,
                    "chatType": "dm",
                    "model": "openai-codex/gpt-5.4",
                    "deliveryContext": {"channel": "discord"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_HOME", str(state_dir))

    sessions = list_local_sessions(assistant_id="personal-assistant")

    assert len(sessions) == 1
    assert sessions[0]["id"] == "session-01"
    assert sessions[0]["agent"] == "personal-assistant"
    assert sessions[0]["channel"] == "discord"


def test_persist_openclaw_runtime_snapshot_tracks_manifest_bindings_and_pointers(
    monkeypatch, tmp_path: Path
) -> None:
    mutx_home = tmp_path / ".mutx"
    openclaw_home = tmp_path / ".openclaw"
    openclaw_home.mkdir()
    config_path = openclaw_home / "openclaw.json"
    config_path.write_text(json.dumps({"gateway": {"port": 18789}}), encoding="utf-8")
    workspace = openclaw_home / "workspace-personal-assistant"
    binding = OpenClawAgentBinding(
        agent_id="personal-assistant",
        workspace=str(workspace),
        agent_dir=str(openclaw_home / "agents" / "personal-assistant" / "agent"),
        model="openai/gpt-5",
        install_method="npm",
        gateway_port=18789,
        created=False,
    )

    monkeypatch.setenv("MUTX_HOME", str(mutx_home))
    monkeypatch.setenv("OPENCLAW_HOME", str(openclaw_home))
    monkeypatch.setattr("cli.openclaw_runtime.find_openclaw_bin", lambda: "/usr/local/bin/openclaw")
    monkeypatch.setattr("cli.openclaw_runtime.detect_openclaw_config_path", lambda: config_path)
    monkeypatch.setattr("cli.openclaw_runtime.detect_openclaw_state_dir", lambda: openclaw_home)
    monkeypatch.setattr("cli.openclaw_runtime.detect_gateway_port", lambda: 18789)
    monkeypatch.setattr("cli.openclaw_runtime.detect_openclaw_version", lambda: "openclaw 1.2.3")
    monkeypatch.setattr(
        "cli.openclaw_runtime.get_gateway_health",
        lambda: OpenClawGatewayHealth(
            status="healthy",
            cli_available=True,
            installed=True,
            onboarded=True,
            gateway_configured=True,
            gateway_reachable=True,
            gateway_port=18789,
            gateway_url="http://127.0.0.1:18789",
            credential_detected=True,
            config_path=str(config_path),
            state_dir=str(openclaw_home),
            doctor_summary="Gateway is reachable and ready for assistant operations.",
        ),
    )

    snapshot = persist_openclaw_runtime_snapshot(
        binding=binding,
        assistant_name="Personal Assistant",
        install_method="npm",
    ).to_payload()

    manifest = load_manifest("openclaw")
    tracked_binding = load_binding("openclaw", "personal-assistant")

    assert snapshot["binding_count"] == 1
    assert manifest["provider"] == "openclaw"
    assert manifest["gateway_url"] == "http://127.0.0.1:18789"
    assert manifest["binary_path"] == "/usr/local/bin/openclaw"
    assert manifest["tracking_mode"] == "import_existing_runtime"
    assert manifest["adopted_existing_runtime"] is True
    assert manifest["last_action_type"] == "import"
    assert manifest["import_source"]["binary_path"] == "/usr/local/bin/openclaw"
    assert manifest["keys_remain_local"] is True
    assert "does not upload local gateway keys" in manifest["privacy_summary"]
    assert tracked_binding["assistant_id"] == "personal-assistant"
    assert tracked_binding["workspace"] == str(workspace)
    assert (mutx_home / "providers" / "openclaw" / "pointers" / "home").exists()


def test_persist_openclaw_runtime_snapshot_merges_live_openclaw_agents(
    monkeypatch, tmp_path: Path
) -> None:
    mutx_home = tmp_path / ".mutx"
    openclaw_home = tmp_path / ".openclaw"
    openclaw_home.mkdir()
    config_path = openclaw_home / "openclaw.json"
    config_path.write_text(json.dumps({"gateway": {"port": 18789}}), encoding="utf-8")
    binding = OpenClawAgentBinding(
        agent_id="personal-assistant",
        workspace=str(openclaw_home / "workspace-personal-assistant"),
        agent_dir=str(openclaw_home / "agents" / "personal-assistant" / "agent"),
        model="openai/gpt-5",
        install_method="npm",
        gateway_port=18789,
        created=False,
    )

    monkeypatch.setenv("MUTX_HOME", str(mutx_home))
    monkeypatch.setenv("OPENCLAW_HOME", str(openclaw_home))
    monkeypatch.setattr("cli.openclaw_runtime.find_openclaw_bin", lambda: "/usr/local/bin/openclaw")
    monkeypatch.setattr("cli.openclaw_runtime.detect_openclaw_config_path", lambda: config_path)
    monkeypatch.setattr("cli.openclaw_runtime.detect_openclaw_state_dir", lambda: openclaw_home)
    monkeypatch.setattr("cli.openclaw_runtime.detect_gateway_port", lambda: 18789)
    monkeypatch.setattr("cli.openclaw_runtime.detect_openclaw_version", lambda: "openclaw 1.2.3")
    monkeypatch.setattr(
        "cli.openclaw_runtime.get_gateway_health",
        lambda: OpenClawGatewayHealth(
            status="healthy",
            cli_available=True,
            installed=True,
            onboarded=True,
            gateway_configured=True,
            gateway_reachable=True,
            gateway_port=18789,
            gateway_url="http://127.0.0.1:18789",
            credential_detected=True,
            config_path=str(config_path),
            state_dir=str(openclaw_home),
            doctor_summary="Gateway is reachable and ready for assistant operations.",
        ),
    )
    monkeypatch.setattr(
        "cli.openclaw_runtime.list_openclaw_agents",
        lambda: [
            {
                "id": "personal-assistant",
                "workspace": str(openclaw_home / "workspace-personal-assistant"),
                "agentDir": str(openclaw_home / "agents" / "personal-assistant" / "agent"),
                "model": "openai/gpt-5",
            },
            {
                "id": "x",
                "workspace": str(openclaw_home / "workspace-x"),
                "agentDir": str(openclaw_home / "agents" / "x" / "agent"),
                "model": "openai/gpt-5-mini",
            },
        ],
    )

    snapshot = persist_openclaw_runtime_snapshot(
        binding=binding,
        assistant_name="Personal Assistant",
        install_method="npm",
    ).to_payload()

    assert snapshot["binding_count"] == 2
    assert snapshot["tracked_binding_count"] == 1
    assert snapshot["live_binding_count"] == 2
    assert snapshot["current_binding"]["assistant_id"] == "personal-assistant"

    bindings_by_id = {item["assistant_id"]: item for item in snapshot["bindings"]}
    assert bindings_by_id["personal-assistant"]["tracked_by_mutx"] is True
    assert bindings_by_id["personal-assistant"]["live_detected"] is True
    assert bindings_by_id["x"]["tracked_by_mutx"] is False
    assert bindings_by_id["x"]["live_detected"] is True
    assert bindings_by_id["x"]["workspace"].endswith("workspace-x")


def test_wizard_state_defaults_and_reset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MUTX_HOME", str(tmp_path / ".mutx"))

    state = reset_wizard_state("openclaw", mode="hosted")

    assert state["provider"] == "openclaw"
    assert state["mode"] == "hosted"
    assert state["current_step"] == "auth"
    assert state["completed_steps"] == []
    assert load_wizard_state("openclaw")["providers"][0]["id"] == "openclaw"


def test_update_binding_governance_persists_binding(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MUTX_HOME", str(tmp_path / ".mutx"))
    binding = OpenClawAgentBinding(
        agent_id="personal-assistant",
        workspace="/tmp/openclaw/workspace-personal-assistant",
        agent_dir=None,
        model="openai/gpt-5",
        install_method="npm",
        gateway_port=18789,
        created=False,
    )

    updated = update_binding_governance(
        binding,
        enabled=True,
        policy="/tmp/.mutx/policies/starter.fpl",
        assistant_name="Personal Assistant",
    )
    saved = load_binding("openclaw", "personal-assistant")

    assert updated.governance_enabled is True
    assert updated.governance_policy == "/tmp/.mutx/policies/starter.fpl"
    assert saved["assistant_id"] == "personal-assistant"
    assert saved["governance_enabled"] is True
    assert saved["governance_policy"] == "/tmp/.mutx/policies/starter.fpl"


def test_inspect_importable_openclaw_runtime_succeeds_for_valid_existing_install(
    monkeypatch,
) -> None:
    health = OpenClawGatewayHealth(
        status="healthy",
        cli_available=True,
        installed=True,
        onboarded=True,
        gateway_configured=True,
        gateway_reachable=True,
        gateway_port=18789,
        gateway_url="http://127.0.0.1:18789",
        credential_detected=True,
        config_path="/tmp/.openclaw/openclaw.json",
        state_dir="/tmp/.openclaw",
        doctor_summary="Gateway is reachable and ready for assistant operations.",
    )
    monkeypatch.setattr(
        "cli.openclaw_runtime.ensure_openclaw_installed",
        lambda **_: __import__(
            "cli.openclaw_runtime", fromlist=["OpenClawInstallResolution"]
        ).OpenClawInstallResolution(
            binary_path="/opt/homebrew/bin/openclaw",
            install_method="npm",
            disposition="detected_existing",
        ),
    )
    monkeypatch.setattr(
        "cli.openclaw_runtime.resolve_openclaw_config_file", lambda: "/tmp/.openclaw/openclaw.json"
    )
    monkeypatch.setattr("cli.openclaw_runtime.validate_openclaw_config", lambda: "Config valid")
    monkeypatch.setattr("cli.openclaw_runtime.get_gateway_health", lambda: health)

    resolution, imported_health = inspect_importable_openclaw_runtime(install_method="npm")

    assert resolution.binary_path == "/opt/homebrew/bin/openclaw"
    assert resolution.imported_existing is True
    assert imported_health.gateway_url == "http://127.0.0.1:18789"


def test_inspect_importable_openclaw_runtime_requires_reachable_gateway(monkeypatch) -> None:
    health = OpenClawGatewayHealth(
        status="degraded",
        cli_available=True,
        installed=True,
        onboarded=True,
        gateway_configured=True,
        gateway_reachable=False,
        gateway_port=18789,
        gateway_url="http://127.0.0.1:18789",
        credential_detected=True,
        config_path="/tmp/.openclaw/openclaw.json",
        state_dir="/tmp/.openclaw",
        doctor_summary="Gateway not reachable.",
    )
    monkeypatch.setattr(
        "cli.openclaw_runtime.ensure_openclaw_installed",
        lambda **_: __import__(
            "cli.openclaw_runtime", fromlist=["OpenClawInstallResolution"]
        ).OpenClawInstallResolution(
            binary_path="/opt/homebrew/bin/openclaw",
            install_method="npm",
            disposition="detected_existing",
        ),
    )
    monkeypatch.setattr(
        "cli.openclaw_runtime.resolve_openclaw_config_file", lambda: "/tmp/.openclaw/openclaw.json"
    )
    monkeypatch.setattr("cli.openclaw_runtime.validate_openclaw_config", lambda: "Config valid")
    monkeypatch.setattr("cli.openclaw_runtime.get_gateway_health", lambda: health)

    try:
        inspect_importable_openclaw_runtime(install_method="npm")
    except ValidationError as exc:
        assert "gateway is not reachable" in str(exc)
    else:
        raise AssertionError("Expected import inspection to reject an unreachable gateway.")


def test_resolve_gateway_auth_argument_reads_token_from_config(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps({"gateway": {"auth": {"mode": "token", "token": "gateway-token"}}}),
        encoding="utf-8",
    )

    monkeypatch.setattr("cli.openclaw_runtime.detect_openclaw_config_path", lambda: config_path)
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("OPENCLAW_GATEWAY_PASSWORD", raising=False)
    monkeypatch.delenv("GATEWAY_PASSWORD", raising=False)

    assert resolve_gateway_auth_argument() == ("--token", "gateway-token")


def test_resolve_gateway_auth_argument_reads_password_from_config(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps({"gateway": {"auth": {"mode": "password", "password": "gateway-password"}}}),
        encoding="utf-8",
    )

    monkeypatch.setattr("cli.openclaw_runtime.detect_openclaw_config_path", lambda: config_path)
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("OPENCLAW_GATEWAY_PASSWORD", raising=False)
    monkeypatch.delenv("GATEWAY_PASSWORD", raising=False)

    assert resolve_gateway_auth_argument() == ("--password", "gateway-password")


def test_build_openclaw_surface_command_includes_gateway_url_without_auth_for_override(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "cli.openclaw_runtime.find_openclaw_bin", lambda: "/opt/homebrew/bin/openclaw"
    )
    monkeypatch.setattr("cli.openclaw_runtime.detect_gateway_port", lambda: 18789)

    command = build_openclaw_surface_command(
        surface="tui",
        gateway_url="ws://remote.example.test:18789",
    )

    assert command == [
        "/opt/homebrew/bin/openclaw",
        "tui",
        "--url",
        "ws://remote.example.test:18789",
    ]


def test_build_openclaw_surface_command_omits_local_url_override(monkeypatch) -> None:
    monkeypatch.setattr(
        "cli.openclaw_runtime.find_openclaw_bin", lambda: "/opt/homebrew/bin/openclaw"
    )
    monkeypatch.setattr("cli.openclaw_runtime.detect_gateway_port", lambda: 18789)

    command = build_openclaw_surface_command(
        surface="tui",
        gateway_url="http://127.0.0.1:18789",
    )

    assert command == [
        "/opt/homebrew/bin/openclaw",
        "tui",
    ]


def test_write_pointer_replaces_stale_directory(monkeypatch, tmp_path: Path) -> None:
    mutx_home = tmp_path / ".mutx"
    target = tmp_path / ".openclaw"
    target.mkdir()
    monkeypatch.setenv("MUTX_HOME", str(mutx_home))

    stale_pointer = provider_pointers_dir("openclaw") / "home"
    stale_pointer.mkdir(parents=True)
    (stale_pointer / "old.txt").write_text("stale", encoding="utf-8")

    write_pointer("openclaw", "home", target)

    assert stale_pointer.exists()
    assert stale_pointer.is_symlink() or stale_pointer.read_text(encoding="utf-8") == str(target)
