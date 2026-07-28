from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from urllib.parse import urlparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from cli.errors import CLIServiceError, ValidationError
from cli.personal_assistant import DEFAULT_ASSISTANT_MODEL, slugify_assistant_id
from cli.runtime_registry import (
    load_manifest,
    list_bindings,
    provider_root,
    provider_wizard_state_path,
    save_binding,
    save_manifest,
    write_pointer,
)


OPENCLAW_VERSION = "2026.7.1"
OPENCLAW_SOURCE_COMMIT = "2d2ddc43d0dcf71f31283d780f9fe9ff4cc04fe4"
OPENCLAW_INSTALL_URL = (
    "https://raw.githubusercontent.com/openclaw/openclaw/"
    f"{OPENCLAW_SOURCE_COMMIT}/scripts/install.sh"
)
DEFAULT_OPENCLAW_INSTALL_METHOD = "npm"
DEFAULT_GATEWAY_PORT = 18789
SUPPORTED_OPENCLAW_INSTALL_METHODS = ("npm", "git")
OPENCLAW_PROVIDER_ID = "openclaw"


def _is_supported_openclaw_node_version(version: str) -> bool:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
    if match is None:
        return False
    parsed = tuple(int(part) for part in match.groups())
    return (
        (22, 22, 3) <= parsed < (23, 0, 0)
        or (24, 15, 0) <= parsed < (25, 0, 0)
        or parsed >= (25, 9, 0)
    )


def _require_supported_openclaw_node() -> None:
    node = shutil.which("node")
    if node is None:
        raise ValidationError("OpenClaw requires Node 24.15+ (recommended).")
    result = subprocess.run(
        [node, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or not _is_supported_openclaw_node_version(result.stdout):
        raise ValidationError(
            "OpenClaw requires Node 22.22.3+, 24.15+, or 25.9+; Node 24 is recommended."
        )


@dataclass(slots=True)
class OpenClawGatewayHealth:
    status: str
    cli_available: bool
    installed: bool
    onboarded: bool
    gateway_configured: bool
    gateway_reachable: bool
    gateway_port: int | None
    gateway_url: str | None
    credential_detected: bool
    config_path: str | None
    state_dir: str | None
    doctor_summary: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cli_available": self.cli_available,
            "installed": self.installed,
            "onboarded": self.onboarded,
            "gateway_configured": self.gateway_configured,
            "gateway_reachable": self.gateway_reachable,
            "gateway_port": self.gateway_port,
            "gateway_url": self.gateway_url,
            "credential_detected": self.credential_detected,
            "config_path": self.config_path,
            "state_dir": self.state_dir,
            "doctor_summary": self.doctor_summary,
        }


@dataclass(slots=True)
class OpenClawAgentBinding:
    agent_id: str
    workspace: str
    agent_dir: str | None
    model: str | None
    install_method: str
    gateway_port: int | None
    created: bool
    governance_enabled: bool = False
    governance_policy: str | None = None

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "managed_by_mutx": True,
            "install_method": self.install_method,
            "gateway_port": self.gateway_port,
            "agent_dir": self.agent_dir,
            "governance_enabled": self.governance_enabled,
            "governance_policy": self.governance_policy,
            "provisioned_at": datetime.now(timezone.utc).isoformat(),
        }


@dataclass(slots=True)
class OpenClawRuntimeSnapshot:
    provider: str
    payload: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass(slots=True)
class OpenClawInstallResolution:
    binary_path: str
    install_method: str
    disposition: str

    @property
    def imported_existing(self) -> bool:
        return self.disposition == "detected_existing"


def normalize_install_method(value: str | None) -> str:
    method = (value or DEFAULT_OPENCLAW_INSTALL_METHOD).strip().lower()
    if method not in SUPPORTED_OPENCLAW_INSTALL_METHODS:
        raise ValidationError(
            f"Unsupported OpenClaw install method '{value}'. "
            f"Use one of: {', '.join(SUPPORTED_OPENCLAW_INSTALL_METHODS)}."
        )
    return method


def detect_openclaw_state_dir() -> Path | None:
    for env_name in ("OPENCLAW_HOME", "OPENCLAW_STATE_DIR"):
        env_value = os.environ.get(env_name)
        if env_value:
            return Path(env_value).expanduser()

    default = Path.home() / ".openclaw"
    if default.exists():
        return default
    return None


def resolve_openclaw_home() -> Path:
    for env_name in ("OPENCLAW_HOME", "OPENCLAW_STATE_DIR"):
        env_value = os.environ.get(env_name)
        if env_value:
            return Path(env_value).expanduser()
    return Path.home() / ".openclaw"


def detect_openclaw_config_path() -> Path | None:
    env_path = os.environ.get("OPENCLAW_CONFIG_PATH")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())

    state_dir = detect_openclaw_state_dir()
    if state_dir is not None:
        candidates.append(state_dir / "openclaw.json")

    candidates.extend(
        [
            Path("/etc/openclaw/openclaw.json"),
            Path("./openclaw.json"),
            Path("/app/openclaw.json"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def detect_openclaw_home_source() -> str:
    for env_name in ("OPENCLAW_HOME", "OPENCLAW_STATE_DIR"):
        if os.environ.get(env_name):
            return env_name
    return "default"


def _tracking_mode_for_disposition(disposition: str | None) -> str:
    if disposition == "detected_existing":
        return "import_existing_runtime"
    if disposition in {"installed_by_mutx", "reinstalled_by_mutx"}:
        return "track_mutx_bootstrapped_runtime"
    return "track_external_runtime"


def _privacy_summary() -> str:
    return (
        "MUTX tracks your local OpenClaw runtime under ~/.mutx/providers/openclaw without moving "
        "the upstream home directory, and it does not upload local gateway keys or secrets."
    )


def _read_json_file(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if isinstance(payload, dict):
        return payload
    return {}


def _npm_global_bin_dir() -> Path | None:
    if shutil.which("npm") is None:
        return None

    candidates = (
        ("npm", "prefix", "-g"),
        ("npm", "config", "get", "prefix"),
    )
    for command in candidates:
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, OSError):
            continue

        prefix = result.stdout.strip()
        if prefix and prefix.startswith("/"):
            return Path(prefix) / "bin"
    return None


def find_openclaw_bin() -> str | None:
    resolved = shutil.which("openclaw")
    if resolved:
        return resolved

    candidates: list[Path] = [
        Path("/opt/homebrew/bin/openclaw"),
        Path("/usr/local/bin/openclaw"),
        Path.home() / ".local" / "bin" / "openclaw",
    ]

    npm_bin = _npm_global_bin_dir()
    if npm_bin is not None:
        candidates.append(npm_bin / "openclaw")

    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _extract_json_payload(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return None

    object_start = text.find("{")
    array_start = text.find("[")
    has_object = object_start >= 0
    has_array = array_start >= 0

    start = -1
    end = -1

    if has_object and has_array:
        if object_start < array_start:
            start = object_start
            end = text.rfind("}")
        else:
            start = array_start
            end = text.rfind("]")
    elif has_object:
        start = object_start
        end = text.rfind("}")
    elif has_array:
        start = array_start
        end = text.rfind("]")

    if start < 0 or end < start:
        return None

    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _run_command(
    command: list[str],
    *,
    capture_output: bool = True,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=check,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise CLIServiceError(f"Command not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        timeout_label = f"{timeout:g}s" if timeout is not None else "the allotted time"
        raise CLIServiceError(
            f"Command timed out after {timeout_label}: {' '.join(command)}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or "").strip()
        raise CLIServiceError(stderr or f"Command failed: {' '.join(command)}") from exc


def _run_bash(command: str) -> None:
    _run_command(["/bin/bash", "-lc", command], capture_output=False)


def _last_nonempty_line(raw: str) -> str | None:
    for line in reversed(raw.splitlines()):
        value = line.strip()
        if value:
            return value
    return None


def run_openclaw_text(args: list[str], *, timeout: float | None = None) -> str:
    claw_bin = find_openclaw_bin()
    if claw_bin is None:
        raise ValidationError("OpenClaw is not installed.")

    result = _run_command([claw_bin, *args], timeout=timeout)
    output = (result.stdout or "").strip()
    if output:
        return output
    return (result.stderr or "").strip()


def resolve_openclaw_config_file() -> str | None:
    detected = detect_openclaw_config_path()
    if detected is not None:
        return str(detected)

    try:
        raw = run_openclaw_text(["config", "file"])
    except CLIServiceError:
        return None

    candidate = _last_nonempty_line(raw)
    if not candidate:
        return None
    return str(Path(candidate).expanduser())


def validate_openclaw_config() -> str:
    return run_openclaw_text(["config", "validate"])


def detect_openclaw_version() -> str | None:
    claw_bin = find_openclaw_bin()
    if claw_bin is None:
        return None

    try:
        result = subprocess.run(
            [claw_bin, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    output = (result.stdout or result.stderr or "").strip()
    if not output:
        return None

    first_line = output.splitlines()[0].strip()
    if first_line.lower().startswith("openclaw"):
        return first_line
    return f"openclaw {first_line}"


def detect_gateway_port() -> int | None:
    for env_name in ("OPENCLAW_GATEWAY_PORT", "GATEWAY_PORT"):
        env_value = os.environ.get(env_name)
        if env_value:
            try:
                port = int(env_value)
            except ValueError:
                continue
            if port > 0:
                return port

    config = _read_json_file(detect_openclaw_config_path())
    raw_port = ((config.get("gateway") or {}).get("port")) if config else None
    if isinstance(raw_port, int) and raw_port > 0:
        return raw_port
    if isinstance(raw_port, str) and raw_port.isdigit():
        port = int(raw_port)
        if port > 0:
            return port
    return None


def detect_gateway_token() -> str:
    auth_arg = resolve_gateway_auth_argument()
    if auth_arg is None:
        return ""
    return auth_arg[1]


def resolve_gateway_auth_argument() -> tuple[str, str] | None:
    for env_name in (
        "OPENCLAW_GATEWAY_PASSWORD",
        "GATEWAY_PASSWORD",
    ):
        env_value = os.environ.get(env_name)
        if env_value:
            value = env_value.strip()
            if value:
                return ("--password", value)

    for env_name in (
        "OPENCLAW_GATEWAY_TOKEN",
        "GATEWAY_TOKEN",
    ):
        env_value = os.environ.get(env_name)
        if env_value:
            value = env_value.strip()
            if value:
                return ("--token", value)

    config = _read_json_file(detect_openclaw_config_path())
    gateway = config.get("gateway") or {}
    auth = gateway.get("auth") or {}
    mode = str(auth.get("mode") or "token").strip().lower()
    if mode == "password":
        password = str(auth.get("password") or "").strip()
        if password:
            return ("--password", password)
        token = str(auth.get("token") or "").strip()
        if token:
            return ("--token", token)
        return None

    token = str(auth.get("token") or "").strip()
    if token:
        return ("--token", token)
    password = str(auth.get("password") or "").strip()
    if password:
        return ("--password", password)
    return None


def _is_default_gateway_url(gateway_url: str | None) -> bool:
    if not gateway_url:
        return True

    port = detect_gateway_port()
    if not port:
        return False

    normalized = gateway_url.rstrip("/")
    defaults = {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"ws://127.0.0.1:{port}",
        f"ws://localhost:{port}",
    }
    if normalized in defaults:
        return True

    parsed = urlparse(normalized)
    if parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port == port:
        return True
    return False


def get_gateway_health() -> OpenClawGatewayHealth:
    claw_bin = find_openclaw_bin()
    cli_available = claw_bin is not None
    config_path = detect_openclaw_config_path()
    state_dir = detect_openclaw_state_dir()
    gateway_port = detect_gateway_port()
    gateway_url = f"http://127.0.0.1:{gateway_port}" if gateway_port else None
    onboarded = config_path is not None
    gateway_configured = onboarded or (state_dir is not None and state_dir.exists())
    credential_detected = bool(detect_gateway_token())

    gateway_reachable = False
    if gateway_url:
        try:
            response = httpx.get(f"{gateway_url}/health", timeout=0.75)
            gateway_reachable = response.status_code < 500
        except httpx.HTTPError:
            gateway_reachable = False

    if gateway_reachable:
        status = "healthy"
        doctor_summary = "Gateway is reachable and ready for assistant operations."
    elif onboarded and cli_available:
        status = "degraded"
        doctor_summary = (
            "OpenClaw is configured locally, but the gateway is not reachable. "
            "Run `openclaw onboard --install-daemon` or `openclaw doctor`."
        )
    elif onboarded:
        status = "degraded"
        doctor_summary = "OpenClaw config is present, but the CLI is not discoverable on PATH."
    elif cli_available:
        status = "needs_onboard"
        doctor_summary = (
            "OpenClaw is installed, but onboarding is not complete. "
            "Run `openclaw onboard --install-daemon`."
        )
    else:
        status = "missing"
        doctor_summary = (
            "OpenClaw is not installed. Install it with `mutx setup --install-openclaw` "
            "or use the official upstream installer."
        )

    return OpenClawGatewayHealth(
        status=status,
        cli_available=cli_available,
        installed=cli_available,
        onboarded=onboarded,
        gateway_configured=gateway_configured,
        gateway_reachable=gateway_reachable,
        gateway_port=gateway_port,
        gateway_url=gateway_url,
        credential_detected=credential_detected,
        config_path=str(config_path) if config_path else None,
        state_dir=str(state_dir) if state_dir else None,
        doctor_summary=doctor_summary,
    )


def _build_openclaw_install_command(*, install_method: str, non_interactive: bool) -> str:
    method = normalize_install_method(install_method)
    version = OPENCLAW_VERSION if method == "npm" else OPENCLAW_SOURCE_COMMIT
    command = (
        f"curl -fsSL --proto '=https' --tlsv1.2 {shlex.quote(OPENCLAW_INSTALL_URL)} "
        f"| bash -s -- --install-method {shlex.quote(method)} "
        f"--version {shlex.quote(version)} --no-onboard"
    )
    return f"{command} --no-prompt" if non_interactive else command


def install_openclaw(*, install_method: str, non_interactive: bool) -> str:
    method = normalize_install_method(install_method)
    command = _build_openclaw_install_command(
        install_method=method,
        non_interactive=non_interactive,
    )

    _run_bash(command)
    resolved = find_openclaw_bin()
    if resolved:
        return resolved

    raise CLIServiceError(
        "OpenClaw installed successfully, but `openclaw` is not discoverable on PATH in this shell. "
        "Open a new terminal or add your npm global bin directory to PATH, then rerun `mutx setup`."
    )


def ensure_openclaw_installed(
    *,
    install_if_missing: bool,
    install_method: str,
    no_input: bool,
    prompt_install: Callable[[], bool] | None = None,
    command_runner: Callable[[str], None] | None = None,
    force_install: bool = False,
) -> OpenClawInstallResolution:
    resolved = find_openclaw_bin()
    if resolved and not force_install:
        return OpenClawInstallResolution(
            binary_path=resolved,
            install_method=normalize_install_method(install_method),
            disposition="detected_existing",
        )

    if not install_if_missing:
        if no_input:
            raise ValidationError(
                "OpenClaw is required for the Personal Assistant. "
                "Re-run with `--install-openclaw`, or install it first via "
                f"`npm install -g openclaw@{OPENCLAW_VERSION}`."
            )
        if prompt_install is None or not prompt_install():
            raise ValidationError(
                "OpenClaw installation was declined. "
                f"Install it first with `npm install -g openclaw@{OPENCLAW_VERSION}`, "
                "then rerun `mutx setup`."
            )

    method = normalize_install_method(install_method)
    command = _build_openclaw_install_command(
        install_method=method,
        non_interactive=no_input,
    )

    if command_runner is not None:
        command_runner(command)
        resolved = find_openclaw_bin()
        if resolved:
            return OpenClawInstallResolution(
                binary_path=resolved,
                install_method=method,
                disposition="reinstalled_by_mutx" if force_install else "installed_by_mutx",
            )
        raise CLIServiceError(
            "OpenClaw installer finished, but `openclaw` is still not available on PATH. "
            "Open a new terminal or fix PATH, then rerun `mutx setup`."
        )

    return OpenClawInstallResolution(
        binary_path=install_openclaw(install_method=method, non_interactive=no_input),
        install_method=method,
        disposition="reinstalled_by_mutx" if force_install else "installed_by_mutx",
    )


def ensure_openclaw_onboarded(
    *,
    no_input: bool,
    command_runner: Callable[[list[str]], None] | None = None,
) -> OpenClawGatewayHealth:
    health = get_gateway_health()
    if health.gateway_reachable:
        return health

    if no_input:
        raise ValidationError(
            "OpenClaw onboarding is required before MUTX can bind the Personal Assistant. "
            "Run `openclaw onboard --install-daemon` in an interactive terminal, then rerun the command."
        )

    claw_bin = find_openclaw_bin()
    if claw_bin is None:
        raise ValidationError("OpenClaw is not installed.")

    command = [claw_bin, "onboard", "--install-daemon"]
    if command_runner is not None:
        command_runner(command)
    else:
        _run_command(command, capture_output=False)
    return get_gateway_health()


def inspect_importable_openclaw_runtime(
    *,
    install_method: str,
) -> tuple[OpenClawInstallResolution, OpenClawGatewayHealth]:
    install_resolution = ensure_openclaw_installed(
        install_if_missing=False,
        install_method=install_method,
        no_input=True,
    )
    config_path = resolve_openclaw_config_file()
    if not config_path:
        raise ValidationError(
            "OpenClaw is installed, but no config file was detected. "
            "Open `openclaw tui` to finish the upstream setup, then rerun the import."
        )

    try:
        validate_openclaw_config()
    except CLIServiceError as exc:
        raise ValidationError(
            "OpenClaw was detected, but the config is invalid. "
            "Open `openclaw tui` to repair the upstream config, then rerun the import.\n"
            f"{exc}"
        ) from exc

    health = get_gateway_health()
    if not health.onboarded:
        raise ValidationError(
            "OpenClaw config validated, but onboarding is incomplete. "
            "Open `openclaw tui` or run `openclaw onboard --install-daemon`, then rerun the import."
        )
    if not health.gateway_reachable:
        raise ValidationError(
            "OpenClaw config validated, but the local gateway is not reachable yet. "
            "Open `openclaw tui` or run `openclaw onboard --install-daemon`, then rerun the import."
        )
    return install_resolution, health


def run_openclaw_json(args: list[str], *, timeout: float | None = None) -> Any:
    claw_bin = find_openclaw_bin()
    if claw_bin is None:
        raise ValidationError("OpenClaw is not installed.")

    result = _run_command([claw_bin, *args], timeout=timeout)
    payload = _extract_json_payload(result.stdout)
    if payload is None:
        raise CLIServiceError(f"OpenClaw returned invalid JSON for: {' '.join(args)}")
    return payload


def build_openclaw_surface_command(
    *,
    surface: str,
    gateway_url: str | None = None,
    session_key: str | None = None,
) -> list[str]:
    claw_bin = find_openclaw_bin()
    if claw_bin is None:
        raise ValidationError("OpenClaw is not installed.")

    normalized = surface.strip().lower()
    if normalized not in {"tui", "configure"}:
        raise ValidationError("Unsupported OpenClaw surface. Use `tui` or `configure`.")

    command = [claw_bin, normalized]
    if normalized == "tui":
        if gateway_url and not _is_default_gateway_url(gateway_url):
            command.extend(["--url", gateway_url])
        if session_key:
            command.extend(["--session", session_key])
    return command


def open_openclaw_surface(
    *,
    surface: str,
    gateway_url: str | None = None,
    session_key: str | None = None,
    command_runner: Callable[[list[str]], None] | None = None,
) -> None:
    command = build_openclaw_surface_command(
        surface=surface,
        gateway_url=gateway_url,
        session_key=session_key,
    )
    if command_runner is not None:
        command_runner(command)
        return
    _run_command(command, capture_output=False)


def list_openclaw_agents() -> list[dict[str, Any]]:
    payload = run_openclaw_json(["agents", "list", "--json"], timeout=2.0)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _default_workspace(assistant_id: str) -> str:
    state_dir = detect_openclaw_state_dir() or (Path.home() / ".openclaw")
    return str((state_dir / f"workspace-{assistant_id}").expanduser())


def ensure_personal_assistant_binding(
    *,
    assistant_name: str,
    model: str | None = None,
    workspace: str | None = None,
    assistant_id: str | None = None,
    install_method: str = DEFAULT_OPENCLAW_INSTALL_METHOD,
) -> OpenClawAgentBinding:
    normalized_assistant_id = assistant_id or slugify_assistant_id(assistant_name)
    requested_workspace = workspace or _default_workspace(normalized_assistant_id)
    requested_model = model or DEFAULT_ASSISTANT_MODEL

    for existing in list_openclaw_agents():
        if str(existing.get("id") or existing.get("agentId") or "") != normalized_assistant_id:
            continue
        return OpenClawAgentBinding(
            agent_id=normalized_assistant_id,
            workspace=str(existing.get("workspace") or requested_workspace),
            agent_dir=str(existing.get("agentDir") or "") or None,
            model=str(existing.get("model") or requested_model),
            install_method=normalize_install_method(install_method),
            gateway_port=detect_gateway_port(),
            created=False,
        )

    payload = run_openclaw_json(
        [
            "agents",
            "add",
            normalized_assistant_id,
            "--workspace",
            requested_workspace,
            "--model",
            requested_model,
            "--non-interactive",
            "--json",
        ]
    )
    if not isinstance(payload, dict):
        raise CLIServiceError("OpenClaw returned an invalid agent binding payload.")

    return OpenClawAgentBinding(
        agent_id=str(payload.get("agentId") or normalized_assistant_id),
        workspace=str(payload.get("workspace") or requested_workspace),
        agent_dir=str(payload.get("agentDir") or "") or None,
        model=str(payload.get("model") or requested_model),
        install_method=normalize_install_method(install_method),
        gateway_port=detect_gateway_port(),
        created=True,
    )


def _binding_payload(
    binding: OpenClawAgentBinding,
    *,
    assistant_name: str | None = None,
) -> dict[str, Any]:
    return {
        "provider": OPENCLAW_PROVIDER_ID,
        "assistant_id": binding.agent_id,
        "assistant_name": assistant_name,
        "workspace": binding.workspace,
        "agent_dir": binding.agent_dir,
        "model": binding.model,
        "install_method": binding.install_method,
        "gateway_port": binding.gateway_port,
        "governance_enabled": binding.governance_enabled,
        "governance_policy": binding.governance_policy,
        "managed_by_mutx": True,
        "created_by_last_run": binding.created,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _normalize_binding_record(
    payload: dict[str, Any],
    *,
    install_method: str,
    gateway_port: int | None,
    observed_at: str,
) -> dict[str, Any] | None:
    assistant_id = str(payload.get("assistant_id") or payload.get("agent_id") or "").strip()
    if not assistant_id:
        return None

    workspace = str(payload.get("workspace") or _default_workspace(assistant_id)).strip()
    agent_dir = str(payload.get("agent_dir") or payload.get("agentDir") or "").strip() or None
    model = str(payload.get("model") or "").strip() or None
    assistant_name = str(payload.get("assistant_name") or "").strip() or None

    normalized = dict(payload)
    normalized.update(
        {
            "provider": OPENCLAW_PROVIDER_ID,
            "assistant_id": assistant_id,
            "assistant_name": assistant_name,
            "workspace": workspace,
            "agent_dir": agent_dir,
            "model": model,
            "install_method": str(payload.get("install_method") or install_method),
            "gateway_port": payload.get("gateway_port", gateway_port),
            "managed_by_mutx": bool(payload.get("managed_by_mutx", True)),
            "created_by_last_run": bool(payload.get("created_by_last_run", False)),
            "tracked_by_mutx": bool(payload.get("tracked_by_mutx", True)),
            "live_detected": bool(payload.get("live_detected", False)),
            "source": str(payload.get("source") or "mutx-registry"),
            "updated_at": str(payload.get("updated_at") or observed_at),
        }
    )
    return normalized


def _binding_payload_from_live_agent(
    agent: dict[str, Any],
    *,
    install_method: str,
    gateway_port: int | None,
    observed_at: str,
) -> dict[str, Any] | None:
    assistant_id = str(agent.get("id") or agent.get("agentId") or "").strip()
    if not assistant_id:
        return None

    workspace = str(agent.get("workspace") or _default_workspace(assistant_id)).strip()
    agent_dir = str(agent.get("agentDir") or agent.get("agent_dir") or "").strip() or None
    model = str(agent.get("model") or "").strip() or None
    assistant_name = str(agent.get("name") or agent.get("label") or "").strip() or None

    return {
        "provider": OPENCLAW_PROVIDER_ID,
        "assistant_id": assistant_id,
        "assistant_name": assistant_name,
        "workspace": workspace,
        "agent_dir": agent_dir,
        "model": model,
        "install_method": install_method,
        "gateway_port": gateway_port,
        "managed_by_mutx": False,
        "created_by_last_run": False,
        "tracked_by_mutx": False,
        "live_detected": True,
        "source": "openclaw-live",
        "updated_at": observed_at,
    }


def _merge_runtime_bindings(
    *,
    tracked_bindings: list[dict[str, Any]],
    live_agents: list[dict[str, Any]],
    current_binding: dict[str, Any] | None,
    assistant_name: str | None,
    install_method: str,
    gateway_port: int | None,
    observed_at: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    merged: dict[str, dict[str, Any]] = {}

    for payload in tracked_bindings:
        normalized = _normalize_binding_record(
            payload,
            install_method=install_method,
            gateway_port=gateway_port,
            observed_at=observed_at,
        )
        if normalized is not None:
            merged[normalized["assistant_id"]] = normalized

    for agent in live_agents:
        live_payload = _binding_payload_from_live_agent(
            agent,
            install_method=install_method,
            gateway_port=gateway_port,
            observed_at=observed_at,
        )
        if live_payload is None:
            continue

        assistant_id = str(live_payload["assistant_id"])
        existing = merged.get(assistant_id)
        if existing is None:
            merged[assistant_id] = live_payload
            continue

        merged[assistant_id] = {
            **existing,
            "workspace": live_payload["workspace"],
            "agent_dir": live_payload["agent_dir"],
            "model": live_payload["model"],
            "gateway_port": live_payload["gateway_port"],
            "live_detected": True,
            "tracked_by_mutx": True,
            "source": "mutx-registry+openclaw-live",
            "updated_at": observed_at,
        }

    if current_binding is not None:
        normalized_current = _normalize_binding_record(
            current_binding,
            install_method=install_method,
            gateway_port=gateway_port,
            observed_at=observed_at,
        )
        if normalized_current is not None:
            existing = merged.get(normalized_current["assistant_id"])
            if existing is not None:
                normalized_current["live_detected"] = bool(existing.get("live_detected"))
                normalized_current["source"] = (
                    "mutx-registry+openclaw-live"
                    if existing.get("live_detected")
                    else "mutx-registry"
                )
            merged[normalized_current["assistant_id"]] = normalized_current

    resolved_current_binding = None
    if current_binding is not None:
        current_assistant_id = str(current_binding.get("assistant_id") or "").strip()
        if current_assistant_id:
            resolved_current_binding = merged.get(current_assistant_id)
    elif assistant_name:
        requested_assistant_id = slugify_assistant_id(assistant_name)
        resolved_current_binding = merged.get(requested_assistant_id)

    bindings = sorted(merged.values(), key=lambda item: str(item.get("assistant_id") or ""))
    return bindings, resolved_current_binding


def update_binding_governance(
    binding: OpenClawAgentBinding,
    *,
    enabled: bool | None = None,
    policy: str | None = None,
    assistant_name: str | None = None,
) -> OpenClawAgentBinding:
    """Update governance settings on an existing binding."""
    updated = OpenClawAgentBinding(
        agent_id=binding.agent_id,
        workspace=binding.workspace,
        agent_dir=binding.agent_dir,
        model=binding.model,
        install_method=binding.install_method,
        gateway_port=binding.gateway_port,
        created=binding.created,
        governance_enabled=enabled if enabled is not None else binding.governance_enabled,
        governance_policy=policy if policy is not None else binding.governance_policy,
    )
    save_binding(
        OPENCLAW_PROVIDER_ID,
        updated.agent_id,
        _binding_payload(updated, assistant_name=assistant_name),
    )
    return updated


def collect_openclaw_runtime_snapshot(
    *,
    binding: OpenClawAgentBinding | None = None,
    assistant_name: str | None = None,
    install_method: str | None = None,
    installation_disposition: str | None = None,
    action_type: str | None = None,
) -> OpenClawRuntimeSnapshot:
    observed_at = datetime.now(timezone.utc).isoformat()
    health = get_gateway_health()
    manifest = load_manifest(OPENCLAW_PROVIDER_ID)
    resolved_install_method = (
        normalize_install_method(install_method)
        if install_method
        else str(manifest.get("install_method") or DEFAULT_OPENCLAW_INSTALL_METHOD)
    )
    binary_path = find_openclaw_bin()
    config_path = detect_openclaw_config_path()
    state_dir = detect_openclaw_state_dir() or resolve_openclaw_home()
    home_source = detect_openclaw_home_source()
    version = detect_openclaw_version()
    resolved_disposition = str(
        installation_disposition
        or manifest.get("installation_disposition")
        or ("detected_existing" if binary_path else "unknown")
    )
    tracking_mode = str(
        manifest.get("tracking_mode") or _tracking_mode_for_disposition(resolved_disposition)
    )
    privacy_summary = str(manifest.get("privacy_summary") or _privacy_summary())
    adopted_existing_runtime = bool(
        manifest.get("adopted_existing_runtime")
        if "adopted_existing_runtime" in manifest
        else resolved_disposition == "detected_existing"
    )
    resolved_action_type = str(
        action_type
        or manifest.get("last_action_type")
        or ("import" if adopted_existing_runtime else "install")
    )
    import_source = manifest.get("import_source")
    if not isinstance(import_source, dict):
        import_source = {}
    import_source = {
        **import_source,
        "binary_path": binary_path,
        "config_path": str(config_path) if config_path else resolve_openclaw_config_file(),
        "home_path": str(state_dir),
        "home_source": home_source,
    }

    tracked_bindings = list_bindings(OPENCLAW_PROVIDER_ID)
    try:
        live_agents = list_openclaw_agents() if binary_path else []
    except CLIServiceError:
        live_agents = []
    explicit_current_binding = (
        _binding_payload(binding, assistant_name=assistant_name) if binding is not None else None
    )
    bindings, current_binding = _merge_runtime_bindings(
        tracked_bindings=tracked_bindings,
        live_agents=live_agents,
        current_binding=explicit_current_binding,
        assistant_name=assistant_name,
        install_method=resolved_install_method,
        gateway_port=health.gateway_port,
        observed_at=observed_at,
    )

    tracked_binding_ids = {
        str(item.get("assistant_id") or item.get("agent_id") or "").strip()
        for item in tracked_bindings
        if str(item.get("assistant_id") or item.get("agent_id") or "").strip()
    }
    if explicit_current_binding is not None:
        current_tracked_id = str(explicit_current_binding.get("assistant_id") or "").strip()
        if current_tracked_id:
            tracked_binding_ids.add(current_tracked_id)

    payload = {
        "provider": OPENCLAW_PROVIDER_ID,
        "runtime_key": OPENCLAW_PROVIDER_ID,
        "label": "OpenClaw",
        "cue": "🦞",
        "provider_root": str(provider_root(OPENCLAW_PROVIDER_ID)),
        "wizard_state_path": str(provider_wizard_state_path(OPENCLAW_PROVIDER_ID)),
        "binary_path": binary_path,
        "binary_confirmed": bool(binary_path),
        "home_path": str(state_dir),
        "home_source": home_source,
        "config_path": str(config_path) if config_path else None,
        "state_dir": str(state_dir),
        "install_method": resolved_install_method,
        "installation_disposition": resolved_disposition,
        "tracking_mode": tracking_mode,
        "imported_into_mutx": True,
        "adopted_existing_runtime": adopted_existing_runtime,
        "keys_remain_local": True,
        "credential_sync_policy": "local_only",
        "privacy_summary": privacy_summary,
        "last_action_type": resolved_action_type,
        "import_source": import_source,
        "version": version,
        "status": health.status,
        "gateway": health.to_payload(),
        "gateway_url": health.gateway_url,
        "gateway_port": health.gateway_port,
        "last_seen_at": observed_at,
        "last_synced_at": manifest.get("last_synced_at"),
        "bindings": bindings,
        "binding_count": len(bindings),
        "tracked_binding_count": len(tracked_binding_ids),
        "live_binding_count": len(live_agents),
        "current_binding": current_binding,
        "observed_source": "local",
    }
    if assistant_name and current_binding is None:
        payload["assistant_name"] = assistant_name
    return OpenClawRuntimeSnapshot(provider=OPENCLAW_PROVIDER_ID, payload=payload)


def persist_openclaw_runtime_snapshot(
    *,
    binding: OpenClawAgentBinding | None = None,
    assistant_name: str | None = None,
    install_method: str | None = None,
    installation_disposition: str | None = None,
    synced_at: str | None = None,
    action_type: str | None = None,
) -> OpenClawRuntimeSnapshot:
    snapshot = collect_openclaw_runtime_snapshot(
        binding=binding,
        assistant_name=assistant_name,
        install_method=install_method,
        installation_disposition=installation_disposition,
        action_type=action_type,
    )
    payload = snapshot.to_payload()
    manifest = {
        "provider": payload["provider"],
        "runtime_key": payload["runtime_key"],
        "label": payload["label"],
        "cue": payload["cue"],
        "provider_root": payload["provider_root"],
        "wizard_state_path": payload["wizard_state_path"],
        "binary_path": payload["binary_path"],
        "binary_confirmed": payload["binary_confirmed"],
        "home_path": payload["home_path"],
        "home_source": payload["home_source"],
        "config_path": payload["config_path"],
        "state_dir": payload["state_dir"],
        "install_method": payload["install_method"],
        "installation_disposition": payload["installation_disposition"],
        "tracking_mode": payload["tracking_mode"],
        "imported_into_mutx": payload["imported_into_mutx"],
        "adopted_existing_runtime": payload["adopted_existing_runtime"],
        "keys_remain_local": payload["keys_remain_local"],
        "credential_sync_policy": payload["credential_sync_policy"],
        "privacy_summary": payload["privacy_summary"],
        "last_action_type": payload["last_action_type"],
        "import_source": payload["import_source"],
        "version": payload["version"],
        "status": payload["status"],
        "gateway": payload["gateway"],
        "gateway_url": payload["gateway_url"],
        "gateway_port": payload["gateway_port"],
        "last_seen_at": payload["last_seen_at"],
        "last_synced_at": synced_at or payload.get("last_synced_at"),
        "binding_count": payload["binding_count"],
        "tracked_binding_count": payload.get("tracked_binding_count", payload["binding_count"]),
        "live_binding_count": payload.get("live_binding_count", payload["binding_count"]),
        "current_binding": payload["current_binding"],
    }
    save_manifest(OPENCLAW_PROVIDER_ID, manifest)

    write_pointer(OPENCLAW_PROVIDER_ID, "home", payload["home_path"])
    write_pointer(OPENCLAW_PROVIDER_ID, "state", payload["state_dir"])
    write_pointer(OPENCLAW_PROVIDER_ID, "config.json", payload.get("config_path"))
    write_pointer(OPENCLAW_PROVIDER_ID, "bin/openclaw", payload.get("binary_path"))
    if binding is not None:
        save_binding(
            OPENCLAW_PROVIDER_ID,
            binding.agent_id,
            _binding_payload(binding, assistant_name=assistant_name),
        )
    return OpenClawRuntimeSnapshot(
        provider=OPENCLAW_PROVIDER_ID,
        payload={**payload, "last_synced_at": synced_at or payload.get("last_synced_at")},
    )


def prepare_personal_assistant_runtime(
    *,
    assistant_name: str,
    model: str | None = None,
    workspace: str | None = None,
    assistant_id: str | None = None,
    install_if_missing: bool,
    install_method: str,
    no_input: bool,
    prompt_install: Callable[[], bool] | None = None,
    install_command_runner: Callable[[str], None] | None = None,
    onboard_command_runner: Callable[[list[str]], None] | None = None,
) -> tuple[OpenClawAgentBinding, OpenClawGatewayHealth]:
    install_resolution = ensure_openclaw_installed(
        install_if_missing=install_if_missing,
        install_method=install_method,
        no_input=no_input,
        prompt_install=prompt_install,
        command_runner=install_command_runner,
    )
    persist_openclaw_runtime_snapshot(
        install_method=install_resolution.install_method,
        installation_disposition=install_resolution.disposition,
    )
    health = ensure_openclaw_onboarded(
        no_input=no_input,
        command_runner=onboard_command_runner,
    )
    binding = ensure_personal_assistant_binding(
        assistant_name=assistant_name,
        model=model,
        workspace=workspace,
        assistant_id=assistant_id,
        install_method=install_method,
    )
    persist_openclaw_runtime_snapshot(
        binding=binding,
        assistant_name=assistant_name,
        install_method=install_resolution.install_method,
        installation_disposition=install_resolution.disposition,
    )
    return binding, health


def merge_runtime_binding(
    config: dict[str, Any] | None,
    *,
    binding: OpenClawAgentBinding,
    health: OpenClawGatewayHealth | None = None,
) -> dict[str, Any]:
    updated = dict(config or {})
    metadata = dict(updated.get("metadata") or {})
    existing_runtime_metadata = dict(metadata.get("runtime") or {})
    runtime_metadata = dict(existing_runtime_metadata)
    binding_runtime_metadata = binding.runtime_metadata()
    if existing_runtime_metadata.get("provisioned_at"):
        binding_runtime_metadata["provisioned_at"] = existing_runtime_metadata["provisioned_at"]
    runtime_metadata.update(binding_runtime_metadata)
    if health is not None:
        runtime_metadata["gateway_status"] = health.status
        runtime_metadata["gateway_url"] = health.gateway_url
    metadata["runtime"] = runtime_metadata
    updated["metadata"] = metadata
    updated["assistant_id"] = binding.agent_id
    updated["workspace"] = binding.workspace
    if binding.model:
        updated["model"] = binding.model
    return updated


def _deserialize_config(config: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(config, dict):
        return dict(config)
    if isinstance(config, str):
        try:
            payload = json.loads(config)
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return dict(payload)
    return {}


def reconcile_openclaw_agent_config(
    *,
    agent_name: str,
    config: dict[str, Any] | str | None,
    install_if_missing: bool,
    install_method: str,
    no_input: bool,
    prompt_install: Callable[[], bool] | None = None,
    install_command_runner: Callable[[str], None] | None = None,
    onboard_command_runner: Callable[[list[str]], None] | None = None,
) -> tuple[dict[str, Any], OpenClawAgentBinding, OpenClawGatewayHealth]:
    current = _deserialize_config(config)
    requested_assistant_id = str(current.get("assistant_id") or slugify_assistant_id(agent_name))
    requested_workspace = current.get("workspace")
    workspace = (
        str(requested_workspace)
        if isinstance(requested_workspace, str) and requested_workspace.strip()
        else None
    )
    requested_model = current.get("model")
    model = (
        str(requested_model)
        if isinstance(requested_model, str) and requested_model.strip()
        else None
    )

    binding, health = prepare_personal_assistant_runtime(
        assistant_name=agent_name,
        model=model,
        workspace=workspace,
        assistant_id=requested_assistant_id,
        install_if_missing=install_if_missing,
        install_method=install_method,
        no_input=no_input,
        prompt_install=prompt_install,
        install_command_runner=install_command_runner,
        onboard_command_runner=onboard_command_runner,
    )
    return merge_runtime_binding(current, binding=binding, health=health), binding, health


def _session_store_files() -> list[Path]:
    state_dir = detect_openclaw_state_dir()
    if state_dir is None:
        return []

    agents_dir = state_dir / "agents"
    if not agents_dir.exists():
        return []

    files: list[Path] = []
    for agent_dir in agents_dir.iterdir():
        sessions_file = agent_dir / "sessions" / "sessions.json"
        if sessions_file.exists() and sessions_file.is_file():
            files.append(sessions_file)
    return files


def _format_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    if value >= 1000:
        return f"{round(value / 1000)}k"
    return str(value)


def _format_age(timestamp_ms: int) -> str:
    if not timestamp_ms:
        return "-"
    diff = datetime.now(timezone.utc).timestamp() * 1000 - timestamp_ms
    if diff <= 0:
        return "now"
    mins = int(diff / 60000)
    hours = int(mins / 60)
    days = int(hours / 24)
    if days > 0:
        return f"{days}d"
    if hours > 0:
        return f"{hours}h"
    return f"{mins}m"


def list_local_sessions(*, assistant_id: str | None = None) -> list[dict[str, Any]]:
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    sessions: list[dict[str, Any]] = []
    for sessions_file in _session_store_files():
        agent_name = sessions_file.parent.parent.name
        if assistant_id and agent_name != assistant_id:
            continue

        payload = _read_json_file(sessions_file)
        if not payload:
            continue

        for key, entry in payload.items():
            if not isinstance(entry, dict):
                continue
            updated_at = int(entry.get("updatedAt") or 0)
            total = int(entry.get("totalTokens") or 0)
            context = int(entry.get("contextTokens") or 0)
            pct = round((total / context) * 100) if context > 0 else 0
            sessions.append(
                {
                    "id": entry.get("sessionId") or f"{agent_name}:{key}",
                    "key": str(key),
                    "agent": agent_name,
                    "kind": str(entry.get("chatType") or "unknown"),
                    "age": _format_age(updated_at),
                    "model": str(entry.get("model") or ""),
                    "tokens": f"{_format_tokens(total)}/{_format_tokens(context)} ({pct}%)",
                    "channel": str(
                        (entry.get("deliveryContext") or {}).get("channel")
                        or entry.get("lastChannel")
                        or entry.get("channel")
                        or ""
                    ),
                    "flags": [],
                    "active": (now - updated_at) < (90 * 60 * 1000) if updated_at else False,
                    "start_time": updated_at,
                    "last_activity": updated_at,
                    "source": "openclaw-local",
                }
            )

    return sorted(sessions, key=lambda item: item["last_activity"], reverse=True)
