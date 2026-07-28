from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import click
import pytest
from click.testing import CliRunner

from cli.main import cli
from cli.services.base import APIService
from cli.services.models import AgentRecord, DeploymentRecord


class DummyResponse:
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> Any:
        return self._payload


class LoginConfig:
    def __init__(self) -> None:
        self.api_url = "http://localhost:8000"
        self.api_key = None
        self.refresh_token = None
        self.config_path = Path("/tmp/mutx-config.json")

    def is_authenticated(self) -> bool:
        return bool(self.api_key and self.refresh_token)

    def clear_auth(self) -> None:
        self.api_key = None
        self.refresh_token = None


def test_login_hits_v1_auth_route_and_saves_tokens(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        captured["path"] = path
        captured["json"] = json
        return DummyResponse(
            200,
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
            },
        )

    config = LoginConfig()
    monkeypatch.setattr("cli.main.CLIConfig", lambda: config)
    monkeypatch.setattr("cli.main.get_client", lambda _: SimpleNamespace(post=fake_post))

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "login",
            "--email",
            "operator@example.com",
            "--password",
            "StrongPass1!",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/auth/login",
        "json": {
            "email": "operator@example.com",
            "password": "StrongPass1!",
        },
    }
    assert config.api_url == "https://api.mutx.dev"
    assert config.api_key == "access-token"
    assert config.refresh_token == "refresh-token"
    assert "Logged in successfully!" in result.output


def test_login_reports_unreachable_api_without_traceback(monkeypatch) -> None:
    def fake_post(path: str, json: dict[str, Any] | None = None) -> DummyResponse:
        raise httpx.ConnectError("Connection refused")

    config = LoginConfig()
    monkeypatch.setattr("cli.main.CLIConfig", lambda: config)
    monkeypatch.setattr(
        "cli.main.get_client",
        lambda _: SimpleNamespace(post=fake_post, close=lambda: None),
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "login",
            "--email",
            "operator@example.com",
            "--password",
            "StrongPass1!",
        ],
    )

    assert result.exit_code == 1
    assert config.api_url == "https://api.mutx.dev"
    assert "Could not reach API" in result.output
    assert "Logged in successfully" not in result.output
    assert "Traceback" not in result.output


def test_auth_login_service_failure_exits_nonzero_without_success(monkeypatch) -> None:
    config = LoginConfig()
    monkeypatch.setattr("cli.main.CLIConfig", lambda: config)
    monkeypatch.setattr("cli.commands.auth.current_config", lambda: config)
    monkeypatch.setattr(
        "cli.commands.auth.get_client",
        lambda _: SimpleNamespace(
            post=lambda path, json: DummyResponse(503, {"detail": "Authentication unavailable"})
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "auth",
            "login",
            "--email",
            "operator@example.com",
            "--password",
            "StrongPass1!",
        ],
    )

    assert result.exit_code == 1
    assert "Authentication unavailable" in result.output
    assert "Logged in successfully" not in result.output


def test_logout_service_failure_exits_nonzero_and_preserves_local_tokens(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(path: str, json: dict[str, str]) -> DummyResponse:
        captured.update(path=path, json=json)
        return DummyResponse(503, {"detail": "Logout unavailable"})

    config = LoginConfig()
    config.api_key = "access-token"
    config.refresh_token = "refresh-token"
    monkeypatch.setattr("cli.main.CLIConfig", lambda: config)
    monkeypatch.setattr("cli.main.get_client", lambda _: SimpleNamespace(post=fake_post))

    result = CliRunner().invoke(cli, ["logout"])

    assert result.exit_code == 1
    assert captured == {
        "path": "/v1/auth/logout",
        "json": {"refresh_token": "refresh-token"},
    }
    assert "Logout unavailable" in result.output
    assert "Logged out successfully" not in result.output
    assert config.api_key == "access-token"
    assert config.refresh_token == "refresh-token"


def test_api_service_refreshes_tokens_after_401() -> None:
    calls: list[tuple[str, str]] = []

    class DummyClient:
        def __init__(self) -> None:
            self.resource_calls = 0

        def get(self, path: str, **kwargs):
            calls.append(("get", path))
            self.resource_calls += 1
            if self.resource_calls == 1:
                return DummyResponse(401, {"detail": "expired"})
            return DummyResponse(200, {"ok": True})

        def post(self, path: str, **kwargs):
            calls.append(("post", path))
            if path == "/v1/auth/refresh":
                return DummyResponse(
                    200,
                    {"access_token": "new-access", "refresh_token": "new-refresh"},
                )
            raise AssertionError(f"unexpected post path: {path}")

        def close(self) -> None:
            return None

    class DummyService(APIService):
        pass

    config = LoginConfig()
    config.api_key = "expired-access"
    config.refresh_token = "refresh-token"
    client = DummyClient()
    service = DummyService(config=config, client_factory=lambda _: client)

    response = service._request("get", "/v1/agents")

    assert response.status_code == 200
    assert config.api_key == "new-access"
    assert config.refresh_token == "new-refresh"
    assert calls == [
        ("get", "/v1/agents"),
        ("post", "/v1/auth/refresh"),
        ("get", "/v1/agents"),
    ]


def test_tui_command_dispatches_to_launcher(monkeypatch) -> None:
    launched = {"value": False}

    def fake_launch() -> None:
        launched["value"] = True

    monkeypatch.setattr("cli.commands.tui.launch_tui", fake_launch)

    runner = CliRunner()
    result = runner.invoke(cli, ["tui"])

    assert result.exit_code == 0
    assert launched["value"] is True


def test_tui_renders_logged_out_state(monkeypatch) -> None:
    textual = pytest.importorskip("textual")
    assert textual is not None

    import cli.tui.app as tui_app

    class DummyAuthService:
        def status(self):
            return SimpleNamespace(
                authenticated=False,
                api_url="http://localhost:8000",
                config_path=Path("/tmp/mutx-config.json"),
            )

    monkeypatch.setattr(tui_app, "AuthService", DummyAuthService)

    from cli.tui.app import MUTX_ASCII_LOGO, MutxTUI

    async def run() -> tuple[str, str, str, str]:
        app = MutxTUI()
        async with app.run_test() as pilot:
            await pilot.pause()
            banner_widget = app.query_one("#status-banner")
            detail_widget = app.query_one("#setup-body")
            logo_widget = app.query_one("#brand-art")
            signal_widget = app.query_one("#brand-signal")
            banner = getattr(banner_widget, "renderable", banner_widget.render())
            detail = getattr(detail_widget, "renderable", detail_widget.render())
            logo = getattr(logo_widget, "renderable", logo_widget.render())
            signal = getattr(signal_widget, "renderable", signal_widget.render())
            return str(banner), str(detail), str(logo), str(signal)

    import asyncio

    banner, detail, logo, signal = asyncio.run(run())
    assert "Auth: local only" in banner
    assert "login required" in detail
    assert "mutx setup hosted" in detail
    assert logo == MUTX_ASCII_LOGO
    assert "__  __" in logo
    assert "/_/\\_\\" in logo
    assert len(logo.splitlines()) == 5
    assert "/v1" in signal
    assert "login required" in signal


def test_tui_logged_out_disables_mutating_actions(monkeypatch) -> None:
    textual = pytest.importorskip("textual")
    assert textual is not None

    import cli.tui.app as tui_app

    class DummyAuthService:
        def status(self):
            return SimpleNamespace(
                authenticated=False,
                api_url="http://localhost:8000",
                config_path=Path("/tmp/mutx-config.json"),
            )

    monkeypatch.setattr(tui_app, "AuthService", DummyAuthService)

    from cli.tui.app import MutxTUI

    async def run() -> tuple[bool, bool, bool]:
        app = MutxTUI()
        async with app.run_test() as pilot:
            await pilot.pause()
            result = (
                app.query_one("#fleet-deploy").disabled,
                app.query_one("#deployments-restart").disabled,
                app.query_one("#deployments-delete").disabled,
            )
            app.exit()
            return result

    import asyncio

    deploy_disabled, restart_disabled, delete_disabled = asyncio.run(run())
    assert deploy_disabled is True
    assert restart_disabled is True
    assert delete_disabled is True


def test_setup_configure_button_opens_configure_surface(monkeypatch) -> None:
    textual = pytest.importorskip("textual")
    assert textual is not None

    from cli.tui.app import MutxTUI

    called: list[str] = []
    app = MutxTUI()
    monkeypatch.setattr(app, "_open_openclaw_surface", lambda surface: called.append(surface))
    app.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="setup-configure-openclaw")))
    assert called == ["configure"]


def test_build_cockpit_snapshot_includes_local_and_managed_workspaces() -> None:
    from cli.tui.cockpit import build_cockpit_snapshot

    managed_agent = AgentRecord(
        id="agent-pa",
        name="Personal Assistant",
        description=None,
        type="openclaw",
        status="running",
        config={"assistant_id": "personal-assistant"},
        config_version=1,
        created_at=None,
        updated_at=None,
        user_id=None,
        deployments=[],
    )
    deployment = DeploymentRecord(
        id="dep-pa",
        agent_id="agent-pa",
        status="running",
        version="v1",
        replicas=1,
        node_id="node-1",
        started_at="2026-03-25T10:00:00Z",
        ended_at=None,
        error_message=None,
        events=[],
    )

    snapshot = build_cockpit_snapshot(
        runtime_snapshot={
            "gateway": {"status": "healthy"},
            "bindings": [
                {
                    "assistant_id": "personal-assistant",
                    "assistant_name": "Personal Assistant",
                    "workspace": "/tmp/workspace-personal-assistant",
                    "tracked_by_mutx": True,
                    "live_detected": True,
                },
                {
                    "assistant_id": "x",
                    "assistant_name": "Workspace X",
                    "workspace": "/tmp/workspace-x",
                    "tracked_by_mutx": False,
                    "live_detected": True,
                },
            ],
        },
        onboarding={"status": "completed"},
        assistant_name="Personal Assistant",
        agents=[managed_agent],
        deployments=[deployment],
        raw_sessions=[
            {
                "id": "session-pa",
                "key": "sess-pa",
                "agent": "personal-assistant",
                "channel": "discord",
                "age": "2m",
                "model": "openai/gpt-5",
                "tokens": "2k",
                "source": "openclaw",
                "active": True,
                "last_activity": 1_710_000_020_000,
            },
            {
                "id": "session-x",
                "key": "sess-x",
                "agent": "x",
                "channel": "cli",
                "age": "5m",
                "model": "openai/gpt-5-mini",
                "tokens": "1k",
                "source": "openclaw",
                "active": True,
                "last_activity": 1_710_000_010_000,
            },
        ],
        governance_defers=[],
        governance_decisions=[],
    )

    workspaces = {item.assistant_id: item for item in snapshot.workspaces}

    assert set(workspaces) == {"personal-assistant", "x"}
    assert workspaces["personal-assistant"].managed_by_mutx is True
    assert workspaces["personal-assistant"].managed_label == "managed"
    assert workspaces["x"].managed_by_mutx is False
    assert workspaces["x"].managed_label == "local"
    assert workspaces["x"].session_count == 1
    assert workspaces["x"].status == "healthy"


def test_build_cockpit_snapshot_deduplicates_session_row_ids() -> None:
    from cli.tui.cockpit import build_cockpit_snapshot

    snapshot = build_cockpit_snapshot(
        runtime_snapshot={
            "gateway": {"status": "healthy"},
            "bindings": [
                {
                    "assistant_id": "x",
                    "assistant_name": "Workspace X",
                    "workspace": "/tmp/workspace-x",
                    "tracked_by_mutx": False,
                    "live_detected": True,
                }
            ],
        },
        onboarding={"status": "completed"},
        assistant_name=None,
        agents=[],
        deployments=[],
        raw_sessions=[
            {
                "id": "session-x",
                "key": "agent:x:base",
                "agent": "x",
                "channel": "cli",
                "age": "2m",
                "model": "openai/gpt-5-mini",
                "tokens": "1k",
                "source": "openclaw",
                "active": True,
                "last_activity": 100,
            },
            {
                "id": "session-x",
                "key": "agent:x:base:run:123",
                "agent": "x",
                "channel": "cli",
                "age": "2m",
                "model": "openai/gpt-5-mini",
                "tokens": "1k",
                "source": "openclaw",
                "active": True,
                "last_activity": 100,
            },
        ],
        governance_defers=[],
        governance_decisions=[],
    )

    assert [item.id for item in snapshot.sessions] == [
        "session-x",
        "session-x:agent:x:base:run:123",
    ]


def test_build_cockpit_snapshot_ranks_incidents_by_urgency() -> None:
    from cli.tui.cockpit import build_cockpit_snapshot

    agents = [
        AgentRecord(
            id="agent-alpha",
            name="Alpha",
            description=None,
            type="openclaw",
            status="failed",
            config={"assistant_id": "alpha"},
            config_version=1,
            created_at=None,
            updated_at=None,
            user_id=None,
            deployments=[],
        ),
        AgentRecord(
            id="agent-beta",
            name="Beta",
            description=None,
            type="openclaw",
            status="failed",
            config={"assistant_id": "beta"},
            config_version=1,
            created_at=None,
            updated_at=None,
            user_id=None,
            deployments=[],
        ),
    ]
    deployments = [
        DeploymentRecord(
            id="dep-alpha",
            agent_id="agent-alpha",
            status="failed",
            version="v1",
            replicas=1,
            node_id=None,
            started_at=None,
            ended_at=None,
            error_message="image pull failed",
            events=[],
        ),
        DeploymentRecord(
            id="dep-beta",
            agent_id="agent-beta",
            status="failed",
            version="v1",
            replicas=1,
            node_id=None,
            started_at=None,
            ended_at=None,
            error_message="heartbeat timeout while waiting for runtime",
            events=[],
        ),
    ]

    snapshot = build_cockpit_snapshot(
        runtime_snapshot={
            "gateway": {"status": "healthy"},
            "bindings": [
                {
                    "assistant_id": "alpha",
                    "workspace": "/tmp/workspace-alpha",
                    "tracked_by_mutx": True,
                },
                {
                    "assistant_id": "beta",
                    "workspace": "/tmp/workspace-beta",
                    "tracked_by_mutx": True,
                },
                {"assistant_id": "x", "workspace": "/tmp/workspace-x", "tracked_by_mutx": False},
            ],
        },
        onboarding={"status": "completed"},
        assistant_name="Personal Assistant",
        agents=agents,
        deployments=deployments,
        raw_sessions=[],
        governance_defers=[SimpleNamespace(agent_id="x")],
        governance_decisions=[],
    )

    assert [(item.assistant_id, item.status, item.severity) for item in snapshot.incidents] == [
        ("alpha", "failed", "critical"),
        ("beta", "stale", "critical"),
        ("x", "healthy", "medium"),
    ]


def test_tui_keeps_workspace_selection_across_snapshot_refresh(monkeypatch) -> None:
    textual = pytest.importorskip("textual")
    assert textual is not None

    import cli.tui.app as tui_app
    from cli.tui.models import CockpitSnapshot, WorkspaceRecord

    class DummyAuthService:
        def status(self):
            return SimpleNamespace(
                authenticated=False,
                api_url="http://localhost:8000",
                config_path=Path("/tmp/mutx-config.json"),
            )

    monkeypatch.setattr(tui_app, "AuthService", DummyAuthService)

    from cli.tui.app import MutxTUI

    workspaces = [
        WorkspaceRecord(
            id="alpha",
            name="Alpha",
            assistant_id="alpha",
            workspace="/tmp/workspace-alpha",
            status="healthy",
            managed_by_mutx=True,
            managed_label="managed",
            gateway_status="healthy",
            session_count=1,
            last_activity=100,
            last_activity_label="1m",
            incident_severity="healthy",
            incident_summary="No active incidents.",
            agent_id="agent-alpha",
        ),
        WorkspaceRecord(
            id="beta",
            name="Beta",
            assistant_id="beta",
            workspace="/tmp/workspace-beta",
            status="failed",
            managed_by_mutx=True,
            managed_label="managed",
            gateway_status="healthy",
            session_count=0,
            last_activity=50,
            last_activity_label="failed",
            incident_severity="critical",
            incident_summary="Latest deployment failed.",
            agent_id="agent-beta",
        ),
    ]
    cockpit = CockpitSnapshot(
        runtime_snapshot={"gateway": {"status": "healthy"}, "bindings": []},
        onboarding={"status": "completed"},
        assistant_name="Personal Assistant",
        workspaces=workspaces,
        incidents=[],
        sessions=[],
        deployments=[],
        gateway_status="healthy",
    )

    async def run() -> str | None:
        app = MutxTUI()
        app.load_workspace_detail = lambda *args, **kwargs: None
        app.load_deployment_detail = lambda *args, **kwargs: None
        app._render_selected_session_detail = lambda: None
        async with app.run_test() as pilot:
            await pilot.pause()
            app._selection.workspace_id = "beta"
            app._apply_cockpit_snapshot(cockpit)
            app._apply_cockpit_snapshot(cockpit)
            selected = app._selection.workspace_id
            app.exit()
            return selected

    import asyncio

    assert asyncio.run(run()) == "beta"


def test_authenticated_tui_defaults_to_fleet_and_enter_opens_selected_session(monkeypatch) -> None:
    textual = pytest.importorskip("textual")
    assert textual is not None

    import cli.tui.app as tui_app

    class DummyAuthService:
        def status(self):
            return SimpleNamespace(
                authenticated=True,
                api_url="https://api.mutx.dev",
                config_path=Path("/tmp/mutx-config.json"),
            )

        def whoami(self):
            return SimpleNamespace(email="operator@example.com", plan="pro")

    monkeypatch.setattr(tui_app, "AuthService", DummyAuthService)
    monkeypatch.setattr(tui_app.MutxTUI, "load_operator_profile", lambda self: None)
    monkeypatch.setattr(tui_app.MutxTUI, "load_cockpit", lambda self: None)

    from cli.tui.app import MutxTUI
    from cli.tui.models import SessionRecord

    async def run() -> tuple[str, list[str]]:
        app = MutxTUI()
        called: list[str] = []
        async with app.run_test() as pilot:
            await pilot.pause()
            active = app.query_one("#workspace").active
            app.query_one("#workspace").active = "sessions-pane"
            app._session_cache["session-1"] = SessionRecord(
                id="session-1",
                key="sess-1",
                assistant_id="personal-assistant",
                workspace="/tmp/workspace-personal-assistant",
                channel="discord",
                age="1m",
                model="openai/gpt-5",
                tokens="2k",
                source="openclaw",
                active=True,
                last_activity=100,
                managed_by_mutx=True,
                agent_id="agent-pa",
            )
            app._selection.session_id = "session-1"
            monkeypatch.setattr(app, "_open_selected_session", lambda: called.append("session"))
            app.action_default_current_row()
            app.exit()
            return active, called

    import asyncio

    active, called = asyncio.run(run())
    assert active == "fleet-pane"
    assert called == ["session"]


def test_command_palette_and_button_share_deploy_action() -> None:
    textual = pytest.importorskip("textual")
    assert textual is not None

    from cli.tui.app import MutxTUI

    called: list[str] = []
    app = MutxTUI()
    app.action_deploy_selected_agent = lambda: called.append("deploy")

    app._dispatch_palette_command("deploy")
    app.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="fleet-deploy")))

    assert called == ["deploy", "deploy"]


def test_open_selected_session_forwards_session_key() -> None:
    textual = pytest.importorskip("textual")
    assert textual is not None

    from cli.tui.app import MutxTUI
    from cli.tui.models import SessionRecord

    called: list[tuple[str, str | None]] = []
    app = MutxTUI()
    app._session_cache["session-1"] = SessionRecord(
        id="session-1",
        key="sess-1",
        assistant_id="personal-assistant",
        workspace="/tmp/workspace-personal-assistant",
        channel="discord",
        age="1m",
        model="openai/gpt-5",
        tokens="2k",
        source="openclaw",
        active=True,
        last_activity=100,
        managed_by_mutx=True,
        agent_id="agent-pa",
    )
    app._selection.session_id = "session-1"
    app._open_openclaw_surface = lambda surface, session_key=None: called.append(
        (surface, session_key)
    )

    app._open_selected_session()

    assert called == [("tui", "sess-1")]


def test_tui_dashboard_button_opens_hosted_dashboard(monkeypatch) -> None:
    textual = pytest.importorskip("textual")
    assert textual is not None

    import cli.tui.app as tui_app

    class DummyAuthService:
        def status(self):
            return SimpleNamespace(
                authenticated=False,
                api_url="http://localhost:8000",
                config_path=Path("/tmp/mutx-config.json"),
            )

    monkeypatch.setattr(tui_app, "AuthService", DummyAuthService)

    from cli.tui.app import HOSTED_LOGIN_URL, MutxTUI

    opened: list[str] = []
    monkeypatch.setattr("cli.tui.app.webbrowser.open", lambda url: opened.append(url) or True)

    app = MutxTUI()
    monkeypatch.setattr(app, "_set_notice", lambda *args, **kwargs: None)
    app.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="brand-open-dashboard")))

    assert opened == [HOSTED_LOGIN_URL]


@pytest.mark.skipif(
    not importlib.util.find_spec("textual"),
    reason="textual not installed",
)
def test_render_openclaw_runtime_detail_shows_gateway_binding_and_sessions() -> None:
    from cli.tui.app import _render_openclaw_runtime_detail

    agent = AgentRecord(
        id="agent-1",
        name="Personal Assistant",
        description=None,
        type="openclaw",
        status="failed",
        config={
            "assistant_id": "personal-assistant",
            "workspace": "/tmp/ws",
            "model": "openai/gpt-5",
            "metadata": {
                "runtime": {
                    "gateway_status": "healthy",
                    "gateway_url": "http://127.0.0.1:18789",
                    "gateway_port": 18789,
                    "agent_dir": "/tmp/agent",
                }
            },
        },
        config_version=1,
        created_at=None,
        updated_at=None,
        user_id=None,
        deployments=[],
    )

    overview = SimpleNamespace(
        status="failed",
        session_count=2,
        installed_skills=[SimpleNamespace(id="web_search")],
        channels=[SimpleNamespace(id="discord", enabled=False)],
        deployments=[
            SimpleNamespace(
                id="dep-1", status="failed", node_id=None, error_message="heartbeat timeout"
            )
        ],
    )

    rendered = _render_openclaw_runtime_detail(
        agent=agent,
        runtime_snapshot={
            "binary_path": "/opt/homebrew/bin/openclaw",
            "config_path": "/Users/test/.openclaw/openclaw.json",
            "state_dir": "/Users/test/.openclaw",
            "adopted_existing_runtime": True,
            "gateway": {
                "status": "healthy",
                "gateway_url": "http://127.0.0.1:18789",
                "gateway_port": 18789,
                "config_path": "/Users/test/.openclaw/openclaw.json",
                "state_dir": "/Users/test/.openclaw",
                "doctor_summary": "Gateway is reachable.",
            },
            "current_binding": {
                "assistant_id": "personal-assistant",
                "workspace": "/tmp/ws",
                "model": "openai/gpt-5",
                "agent_dir": "/tmp/agent",
            },
            "bindings": [
                {
                    "assistant_id": "personal-assistant",
                    "workspace": "/tmp/ws",
                    "tracked_by_mutx": True,
                    "live_detected": True,
                },
                {
                    "assistant_id": "x",
                    "workspace": "/tmp/workspace-x",
                    "tracked_by_mutx": False,
                    "live_detected": True,
                },
            ],
            "tracked_binding_count": 1,
            "live_binding_count": 2,
        },
        assistant_overview=overview,
        local_sessions=[
            {
                "age": "5m",
                "channel": "discord",
                "tokens": "2k/128k (1%)",
                "model": "openai/gpt-5",
            }
        ],
    )

    assert "Gateway:" in rendered
    assert "Binding:" in rendered
    assert "Detected workspaces (2):" in rendered
    assert "Local sessions:" in rendered
    assert "/tmp/workspace-x" in rendered
    assert "discord" in rendered
    assert "heartbeat timeout" in rendered


def test_assistant_service_lists_all_local_sessions_without_agent_id(monkeypatch) -> None:
    from cli.services.assistant import AssistantService

    sessions = [
        {"id": "session-x", "agent": "x", "channel": "cli"},
        {"id": "session-pa", "agent": "personal-assistant", "channel": "discord"},
    ]
    monkeypatch.setattr(
        "cli.services.assistant.list_local_sessions", lambda assistant_id=None: sessions
    )

    service = AssistantService(config=LoginConfig(), client_factory=lambda _: None)

    assert service.list_sessions() == sessions


def test_onboard_hosted_can_register(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class DummyAuth:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def status(self):
            return SimpleNamespace(authenticated=False)

    @click.command()
    @click.option("--register/--login-existing", default=False)
    def fake_setup_hosted(register: bool) -> None:
        captured["register"] = register

    monkeypatch.setattr("cli.commands.onboard.current_config", lambda: SimpleNamespace())
    monkeypatch.setattr("cli.commands.onboard.AuthService", DummyAuth)
    monkeypatch.setattr("cli.commands.onboard.get_client", lambda *_: None)
    monkeypatch.setattr("cli.commands.onboard._get_setup_hosted_command", lambda: fake_setup_hosted)

    runner = CliRunner()
    result = runner.invoke(cli, ["onboard"], input="1\n1\n")

    assert result.exit_code == 0
    assert captured["register"] is True
    assert "Create a new MUTX account" in result.output


def test_onboard_hosted_can_login_existing(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class DummyAuth:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def status(self):
            return SimpleNamespace(authenticated=False)

    @click.command()
    @click.option("--register/--login-existing", default=False)
    def fake_setup_hosted(register: bool) -> None:
        captured["register"] = register

    monkeypatch.setattr("cli.commands.onboard.current_config", lambda: SimpleNamespace())
    monkeypatch.setattr("cli.commands.onboard.AuthService", DummyAuth)
    monkeypatch.setattr("cli.commands.onboard.get_client", lambda *_: None)
    monkeypatch.setattr("cli.commands.onboard._get_setup_hosted_command", lambda: fake_setup_hosted)

    runner = CliRunner()
    result = runner.invoke(cli, ["onboard"], input="1\n2\n")

    assert result.exit_code == 0
    assert captured["register"] is False
    assert "sign in to an existing account" in result.output.lower()
