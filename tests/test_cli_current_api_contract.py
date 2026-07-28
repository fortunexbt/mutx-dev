from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from click.testing import CliRunner

from cli.errors import (
    APIRequestError,
    AuthenticationExpiredError,
    InvalidCredentialsError,
    ResourceNotFoundError,
    ValidationError,
)
from cli.main import cli
from cli.services.base import APIService
from cli.services.auth import AuthService
from cli.services.documents import DocumentsService
from cli.services.reasoning import ReasoningService
from src.api.main import create_app


REPO_ROOT = Path(__file__).resolve().parents[1]
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
SERVICE_REQUEST_METHODS = {
    "_perform_request",
    "_request",
    "request_empty",
    "request_json",
    "request_response",
    "request_text",
}


class DummyConfig:
    api_url = "https://api.example.test"
    refresh_token = None

    def is_authenticated(self) -> bool:
        return True


class MutableAuthConfig:
    api_url = "https://api.example.test"
    api_url_source = "config"
    config_path = Path("/tmp/mutx-cli-auth.json")

    def __init__(self) -> None:
        self.access_token: str | None = "access-token"
        self.refresh_token: str | None = "refresh-token"

    def is_authenticated(self) -> bool:
        return bool(self.access_token and self.refresh_token)

    def clear_auth(self) -> None:
        self.access_token = None
        self.refresh_token = None


class DummyResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any = None,
        *,
        text: str | None = None,
        malformed: bool = False,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else str(payload)
        self.headers: dict[str, str] = {}
        self.content = b""
        self._malformed = malformed

    def json(self) -> Any:
        if self._malformed:
            raise ValueError("invalid JSON")
        return self._payload


class StaticClient:
    def __init__(self, response: DummyResponse | None = None, error: Exception | None = None):
        self.response = response
        self.error = error

    def get(self, path: str, **kwargs: Any) -> DummyResponse:
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response

    def post(self, path: str, **kwargs: Any) -> DummyResponse:
        return self.get(path, **kwargs)

    def close(self) -> None:
        return None


def _render_path(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if not isinstance(node, ast.JoinedStr):
        return None

    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue):
            parts.append("{}")
        else:
            return None
    return "".join(parts)


def _cli_request_contracts() -> set[tuple[str, str]]:
    contracts: set[tuple[str, str]] = set()
    for source_path in (REPO_ROOT / "cli").rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue

            call_name = node.func.attr.lower()
            method: str | None = None
            path: str | None = None
            if call_name in HTTP_METHODS and node.args:
                method = call_name
                path = _render_path(node.args[0])
            elif call_name in SERVICE_REQUEST_METHODS and len(node.args) >= 2:
                method = _render_path(node.args[0])
                path = _render_path(node.args[1])

            if method and path and path.startswith("/v1/"):
                contracts.add((method.lower(), path))
    return contracts


def _mounted_contracts() -> set[tuple[str, str]]:
    mounted: set[tuple[str, str]] = set()
    app = create_app(enable_lifespan=False)
    for route in app.routes:
        if not route.path.startswith("/v1/"):
            continue
        normalized_path = re.sub(r"\{[^}]+\}", "{}", route.path)
        for method in route.methods or set():
            if method.lower() in HTTP_METHODS:
                mounted.add((method.lower(), normalized_path))
    return mounted


def test_every_cli_v1_request_matches_a_mounted_method_and_exact_path() -> None:
    requested = _cli_request_contracts()
    mounted = _mounted_contracts()

    assert requested
    assert requested - mounted == set()


@pytest.mark.parametrize("status_code", [403, 404, 409, 500])
def test_api_service_preserves_error_status_and_detail(status_code: int) -> None:
    response = DummyResponse(status_code, {"detail": f"failure-{status_code}"})
    service = APIService(
        config=DummyConfig(),
        client_factory=lambda _config: StaticClient(response=response),
    )

    with pytest.raises(APIRequestError, match=f"failure-{status_code}") as exc_info:
        service.request_json("get", "/v1/agents", ok_statuses={200}, expected_type=dict)

    assert exc_info.value.status_code == status_code


def test_api_service_maps_named_404_contract() -> None:
    service = APIService(
        config=DummyConfig(),
        client_factory=lambda _config: StaticClient(
            response=DummyResponse(404, {"detail": "missing"})
        ),
    )

    with pytest.raises(ResourceNotFoundError, match="Agent not found"):
        service.request_json(
            "get",
            "/v1/agents/missing",
            ok_statuses={200},
            not_found_message="Agent not found",
        )


def test_api_service_maps_422_to_validation_error() -> None:
    service = APIService(
        config=DummyConfig(),
        client_factory=lambda _config: StaticClient(
            response=DummyResponse(422, {"detail": "invalid payload"})
        ),
    )

    with pytest.raises(ValidationError, match="invalid payload"):
        service.request_json(
            "post",
            "/v1/agents",
            ok_statuses={201},
            invalid_message="Unable to create agent",
        )


def test_api_service_reports_401_without_refresh_token() -> None:
    service = APIService(
        config=DummyConfig(),
        client_factory=lambda _config: StaticClient(
            response=DummyResponse(401, {"detail": "expired"})
        ),
    )

    with pytest.raises(AuthenticationExpiredError, match="mutx login"):
        service.request_json("get", "/v1/agents", ok_statuses={200})


def test_api_service_reports_malformed_success_payload() -> None:
    service = APIService(
        config=DummyConfig(),
        client_factory=lambda _config: StaticClient(response=DummyResponse(200, malformed=True)),
    )

    with pytest.raises(APIRequestError, match="malformed JSON") as exc_info:
        service.request_json("get", "/v1/agents", ok_statuses={200}, expected_type=dict)

    assert exc_info.value.status_code == 200


def test_api_service_reports_network_failure_without_traceback_text() -> None:
    request = httpx.Request("GET", "https://api.example.test/v1/agents")
    service = APIService(
        config=DummyConfig(),
        client_factory=lambda _config: StaticClient(
            error=httpx.ConnectError("connection refused", request=request)
        ),
    )

    with pytest.raises(APIRequestError, match="Could not reach API"):
        service.request_json("get", "/v1/agents", ok_statuses={200})


def test_login_401_maps_to_invalid_credentials() -> None:
    config = MutableAuthConfig()
    service = AuthService(
        config=config,
        client_factory=lambda _config: SimpleNamespace(
            post=lambda path, json: DummyResponse(401, {"detail": "invalid"})
        ),
    )

    with pytest.raises(InvalidCredentialsError, match="Invalid email or password"):
        service.login("operator@example.com", "bad-password")


def test_logout_revokes_only_the_stored_server_session_before_clearing_local_tokens() -> None:
    config = MutableAuthConfig()
    sibling_refresh_token = "sibling-refresh-token"
    calls: list[tuple[str, dict[str, str]]] = []

    def post(path: str, json: dict[str, str]) -> DummyResponse:
        calls.append((path, json))
        return DummyResponse(200, {"message": "Successfully logged out"})

    service = AuthService(
        config=config,
        client_factory=lambda _config: SimpleNamespace(post=post),
    )

    assert service.logout() is True
    assert calls == [
        ("/v1/auth/logout", {"refresh_token": "refresh-token"}),
    ]
    assert sibling_refresh_token not in calls[0][1].values()
    assert config.access_token is None
    assert config.refresh_token is None


def test_logout_does_not_rotate_the_token_or_fall_back_to_other_sessions() -> None:
    config = MutableAuthConfig()
    calls: list[tuple[str, dict[str, str]]] = []

    def post(path: str, json: dict[str, str]) -> DummyResponse:
        calls.append((path, json))
        return DummyResponse(401, {"detail": "Invalid or expired refresh token"})

    service = AuthService(
        config=config,
        client_factory=lambda _config: SimpleNamespace(post=post),
    )

    with pytest.raises(AuthenticationExpiredError, match="mutx login"):
        service.logout()

    assert calls == [
        ("/v1/auth/logout", {"refresh_token": "refresh-token"}),
    ]
    assert config.access_token == "access-token"
    assert config.refresh_token == "refresh-token"


def test_scheduler_create_uses_current_payload_and_exact_url(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def post(path: str, json: dict[str, Any]) -> DummyResponse:
        captured.update(path=path, json=json)
        return DummyResponse(201, {"id": "task-1", "name": "heartbeat", "next_run": 42})

    monkeypatch.setattr("cli.commands.scheduler.current_config", DummyConfig)
    monkeypatch.setattr(
        "cli.commands.scheduler.get_client",
        lambda _config: SimpleNamespace(post=post),
    )

    result = CliRunner().invoke(
        cli,
        [
            "scheduler",
            "create",
            "--name",
            "heartbeat",
            "--agent-id",
            "agent-1",
            "--cron",
            "*/5 * * * *",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/scheduler",
        "json": {
            "name": "heartbeat",
            "schedule": "*/5 * * * *",
            "task_type": "agent_heartbeat",
            "payload": {"agent_id": "agent-1"},
        },
    }


def test_scheduler_rejects_unmounted_agent_input_before_network(monkeypatch) -> None:
    monkeypatch.setattr(
        "cli.commands.scheduler.get_client",
        lambda _config: pytest.fail("unsupported scheduler input made a network request"),
    )

    result = CliRunner().invoke(
        cli,
        [
            "scheduler",
            "create",
            "--name",
            "heartbeat",
            "--agent-id",
            "agent-1",
            "--cron",
            "*/5 * * * *",
            "--input",
            '{"prompt":"run"}',
        ],
    )

    assert result.exit_code == 1
    assert "supports heartbeats only" in result.output


def test_usage_summary_uses_mounted_budget_breakdown(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def get(path: str, params: dict[str, Any]) -> DummyResponse:
        captured.update(path=path, params=params)
        return DummyResponse(
            200,
            {
                "total_credits_used": 2,
                "credits_remaining": 8,
                "credits_total": 10,
                "period_start": "start",
                "period_end": "end",
                "usage_by_agent": [],
                "usage_by_type": [],
            },
        )

    monkeypatch.setattr("cli.commands.usage.current_config", DummyConfig)
    monkeypatch.setattr("cli.commands.usage.get_client", lambda _config: SimpleNamespace(get=get))

    result = CliRunner().invoke(cli, ["usage", "summary", "--period", "weekly"])

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/budgets/usage",
        "params": {"period_start": "7d"},
    }


def test_unmounted_budget_mutation_fails_before_network(monkeypatch) -> None:
    monkeypatch.setattr(
        "cli.commands.budgets.get_client",
        lambda _config: pytest.fail("unsupported command made a network request"),
    )

    result = CliRunner().invoke(
        cli,
        ["budgets", "create", "--name", "team", "--limit", "100"],
    )

    assert result.exit_code == 1
    assert "Budget CRUD is unavailable" in result.output


def test_unmounted_daily_usage_buckets_fail_before_network(monkeypatch) -> None:
    monkeypatch.setattr(
        "cli.commands.usage.get_client",
        lambda _config: pytest.fail("unsupported usage command made a network request"),
    )

    result = CliRunner().invoke(cli, ["usage", "by-day"])

    assert result.exit_code == 1
    assert "Daily usage buckets are unavailable" in result.output


def test_public_clawhub_catalog_does_not_require_login(monkeypatch) -> None:
    class LoggedOutConfig(DummyConfig):
        def is_authenticated(self) -> bool:
            return False

    captured: list[str] = []

    def get(path: str) -> DummyResponse:
        captured.append(path)
        return DummyResponse(200, [])

    monkeypatch.setattr("cli.commands.clawhub.current_config", LoggedOutConfig)
    monkeypatch.setattr("cli.commands.clawhub.get_client", lambda _config: SimpleNamespace(get=get))

    result = CliRunner().invoke(cli, ["clawhub", "list"])

    assert result.exit_code == 0
    assert captured == ["/v1/clawhub/skills"]
    assert "No skills found" in result.output


def test_assistant_skill_configuration_reports_reconciliation_state(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def post(path: str) -> DummyResponse:
        captured["path"] = path
        return DummyResponse(
            200,
            [
                {
                    "id": "browser_control",
                    "name": "Browser Control",
                    "category": "automation",
                    "status": "configured",
                    "configured": True,
                    "runtime_ready": False,
                    "reconciliation_required": True,
                }
            ],
        )

    monkeypatch.setattr("cli.commands.assistant.current_config", DummyConfig)
    monkeypatch.setattr(
        "cli.commands.assistant.get_client",
        lambda _config: SimpleNamespace(post=post),
    )

    result = CliRunner().invoke(
        cli,
        [
            "assistant",
            "skills",
            "install",
            "--agent-id",
            "agent-1",
            "--skill-id",
            "browser_control",
        ],
    )

    assert result.exit_code == 0
    assert captured["path"] == "/v1/assistant/agent-1/skills/browser_control"
    assert "status: configured" in result.output
    assert "Runtime reconciliation is still required" in result.output


def test_observability_command_uses_sync_httpx_surface(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def get(path: str, params: dict[str, Any]) -> DummyResponse:
        captured.update(path=path, params=params)
        return DummyResponse(200, {"items": [], "total": 0})

    monkeypatch.setattr("cli.main.CLIConfig", DummyConfig)
    monkeypatch.setattr(
        "cli.commands.observability.get_client",
        lambda _config: SimpleNamespace(get=get),
    )

    result = CliRunner().invoke(cli, ["observability", "runs", "list"])

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/observability/runs",
        "params": {"limit": 20, "skip": 0},
    }


def test_security_command_uses_sync_httpx_surface(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def post(path: str, json: dict[str, Any]) -> DummyResponse:
        captured.update(path=path, json=json)
        return DummyResponse(200, {"decision": "allow", "reason": "ok"})

    monkeypatch.setattr("cli.main.CLIConfig", DummyConfig)
    monkeypatch.setattr(
        "cli.commands.security.get_client",
        lambda _config: SimpleNamespace(post=post),
    )

    result = CliRunner().invoke(
        cli,
        [
            "security",
            "evaluate",
            "shell",
            "--agent-id",
            "agent-1",
            "--session-id",
            "session-1",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "path": "/v1/security/actions/evaluate",
        "json": {
            "tool_name": "shell",
            "tool_args": {},
            "agent_id": "agent-1",
            "session_id": "session-1",
            "trigger": "manual",
            "runtime": "mutx",
        },
    }


def test_document_local_execution_uses_sync_engine(monkeypatch) -> None:
    from src.api.services import document_engine

    service = DocumentsService(config=DummyConfig(), client_factory=lambda _config: None)
    events: list[str] = []
    finished = object()

    monkeypatch.setattr(
        document_engine,
        "execute_document_manifest",
        lambda _manifest: SimpleNamespace(
            events=[], artifacts=[], driver="sync", output_text="done", summary={}
        ),
    )
    monkeypatch.setattr(
        service,
        "launch_local",
        lambda **_kwargs: SimpleNamespace(manifest={"kind": "document"}),
    )

    def submit_event(**kwargs: Any) -> object:
        events.append(kwargs["event_type"])
        return finished

    monkeypatch.setattr(service, "submit_event", submit_event)

    result = service.run_local_job(job=SimpleNamespace(id="doc-1"))

    assert result is finished
    assert events == ["dispatch_started", "job_completed"]


def test_reasoning_local_execution_runs_async_engine(monkeypatch) -> None:
    from src.api.services import reasoning_engine

    service = ReasoningService(config=DummyConfig(), client_factory=lambda _config: None)
    events: list[str] = []
    finished = object()

    async def execute(_manifest: dict[str, Any]) -> SimpleNamespace:
        return SimpleNamespace(
            events=[], artifacts=[], driver="async", output_text="done", summary={}
        )

    monkeypatch.setattr(reasoning_engine, "execute_reasoning_manifest", execute)
    monkeypatch.setattr(
        service,
        "launch_local",
        lambda **_kwargs: SimpleNamespace(manifest={"kind": "reasoning"}),
    )

    def submit_event(**kwargs: Any) -> object:
        events.append(kwargs["event_type"])
        return finished

    monkeypatch.setattr(service, "submit_event", submit_event)

    result = service.run_local_job(job=SimpleNamespace(id="reason-1"))

    assert result is finished
    assert events == ["reasoning.pass_started", "reasoning.completed"]
