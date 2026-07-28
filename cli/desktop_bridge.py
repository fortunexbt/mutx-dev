#!/usr/bin/env python3
"""MUTX desktop bridge.

Exposes a small JSON-RPC surface over stdio so the Electron shell can talk to
the existing Python operator stack without reimplementing setup/runtime logic in
JavaScript.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.config import CLIConfig, HOSTED_API_URL, LOCAL_API_URL, current_config
from cli.faramesh_runtime import (
    FAREMESH_SOCKET_PATH,
    collect_faramesh_snapshot,
    get_default_policy_path,
    get_faramesh_health,
    is_faramesh_available,
    start_faramesh_daemon,
)
from cli.local_control_plane import (
    ensure_local_container_runtime,
    ensure_local_control_plane,
    local_control_plane_ready,
    managed_local_control_checkout,
    managed_local_control_root,
)
from cli.openclaw_runtime import (
    build_openclaw_surface_command,
    collect_openclaw_runtime_snapshot,
    find_openclaw_bin,
    get_gateway_health,
    list_local_sessions,
)
from cli.runtime_registry import list_bindings, load_manifest, load_wizard_state, mutx_home_dir
from cli.services import (
    AgentsService,
    AssistantService,
    AuthService,
    CLIServiceError,
    DocumentsService,
    RuntimeStateService,
    TemplatesService,
)
from cli.setup_wizard import prepare_runtime_state_sync, run_openclaw_setup_wizard

try:
    from src.api.services.document_engine import get_document_engine_readiness
except Exception:  # noqa: BLE001
    get_document_engine_readiness = None

EXIT_COMMANDS = {"exit", "quit", "q"}
ROOT_DIR = Path(__file__).resolve().parent.parent


def get_mutx_version() -> str:
    with (ROOT_DIR / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    return str(pyproject["project"]["version"])


def get_config() -> CLIConfig:
    return current_config()


def get_auth_service() -> AuthService:
    return AuthService(config=get_config())


def get_runtime_service() -> RuntimeStateService:
    return RuntimeStateService(config=get_config())


def get_assistant_service() -> AssistantService:
    return AssistantService(config=get_config())


def get_templates_service() -> TemplatesService:
    return TemplatesService(config=get_config())


def get_agents_service() -> AgentsService:
    return AgentsService(config=get_config())


def get_documents_service() -> DocumentsService:
    return DocumentsService(config=get_config())


def _success(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"success": True, **(payload or {})}


def _failure(message: str) -> dict[str, Any]:
    return {"success": False, "error": message}


def _expand_path_argument(value: Any, label: str) -> tuple[Path | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, f"{label} must be a non-empty string"
    if "\0" in value:
        return None, f"{label} contains an unsupported null character"
    return Path(value).expanduser(), None


def _run_applescript(script: str) -> None:
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)


def _open_command_in_terminal(command: list[str], cwd: str | None = None) -> None:
    shell_command = shlex.join(command)
    if cwd:
        shell_command = f"cd {shlex.quote(str(Path(cwd).expanduser()))} && {shell_command}"
    escaped = shell_command.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "Terminal" to do script "{escaped}"'
    _run_applescript(script)


def system_info() -> dict[str, Any]:
    config = get_config()
    auth = get_auth_service()
    auth_state = auth.status()
    openclaw_health = get_gateway_health()
    faramesh_health = get_faramesh_health()
    runtime_snapshot = collect_openclaw_runtime_snapshot().to_payload()

    return {
        "mutx_version": get_mutx_version(),
        "api_url": config.api_url,
        "api_url_source": config.api_url_source,
        "authenticated": auth_state.authenticated,
        "user": None,
        "config_path": str(config.config_path),
        "mutx_home": str(mutx_home_dir()),
        "local_control_plane": {
            "path": str(managed_local_control_root()),
            "ready": local_control_plane_ready(),
        },
        "openclaw": {
            "binary_path": find_openclaw_bin(),
            "health": openclaw_health.to_payload(),
            "manifest": load_manifest("openclaw") or runtime_snapshot,
            "bindings": list_bindings("openclaw"),
        },
        "faramesh": {
            "available": is_faramesh_available(),
            "socket_path": FAREMESH_SOCKET_PATH,
            "health": asdict(faramesh_health),
            "policy_path": get_default_policy_path(),
        },
        "documents": (
            get_document_engine_readiness().to_payload()
            if callable(get_document_engine_readiness)
            else {
                "enabled": False,
                "python_ok": False,
                "predict_rlm_available": False,
                "deno_available": False,
                "credentials_ok": False,
                "ready": False,
                "driver": "unavailable",
                "artifacts_dir": None,
                "missing_requirements": [
                    "documents_enabled",
                    "python>=3.11",
                    "deno",
                    "predict_rlm",
                    "OPENAI_API_KEY",
                ],
                "configured_model_providers": [],
            }
        ),
        "cli_available": True,
    }


def auth_status() -> dict[str, Any]:
    auth = get_auth_service()
    status = auth.status()
    user = None
    if status.authenticated:
        try:
            profile = auth.whoami()
            user = {
                "email": profile.email,
                "name": profile.name,
                "plan": profile.plan,
            }
        except CLIServiceError:
            user = None

    return {
        "authenticated": status.authenticated,
        "api_url": status.api_url,
        "user": user,
    }


def auth_login(email: str, password: str, api_url: str | None = None) -> dict[str, Any]:
    try:
        get_auth_service().login(email=email, password=password, api_url=api_url)
        return _success(auth_status())
    except CLIServiceError as exc:
        return _failure(str(exc))


def auth_register(
    name: str, email: str, password: str, api_url: str | None = None
) -> dict[str, Any]:
    try:
        get_auth_service().register(name=name, email=email, password=password, api_url=api_url)
        return _success(auth_status())
    except CLIServiceError as exc:
        return _failure(str(exc))


def auth_local_bootstrap(name: str, api_url: str | None = None) -> dict[str, Any]:
    try:
        get_auth_service().local_bootstrap(name=name, api_url=api_url or LOCAL_API_URL)
        return _success(auth_status())
    except CLIServiceError as exc:
        return _failure(str(exc))


def auth_store_tokens(
    access_token: str, refresh_token: str | None = None, api_url: str | None = None
) -> dict[str, Any]:
    config = get_config()
    if api_url:
        config.api_url = api_url
    config.access_token = access_token
    config.refresh_token = refresh_token
    return _success(auth_status())


def auth_logout() -> dict[str, Any]:
    get_auth_service().logout()
    return _success()


def doctor_run() -> dict[str, Any]:
    config = get_config()
    auth = get_auth_service()
    assistant_service = get_assistant_service()
    payload: dict[str, Any] = {
        "api_url": config.api_url,
        "api_url_source": config.api_url_source,
        "config_path": str(config.config_path),
        "authenticated": auth.status().authenticated,
        "api_health": "unreachable",
        "openclaw": get_gateway_health().to_payload(),
        "runtime_snapshot": collect_openclaw_runtime_snapshot().to_payload(),
        "faramesh": asdict(collect_faramesh_snapshot()),
        "documents": (
            get_document_engine_readiness().to_payload()
            if callable(get_document_engine_readiness)
            else {
                "enabled": False,
                "python_ok": False,
                "predict_rlm_available": False,
                "deno_available": False,
                "credentials_ok": False,
                "ready": False,
                "driver": "unavailable",
                "artifacts_dir": None,
                "missing_requirements": [
                    "documents_enabled",
                    "python>=3.11",
                    "deno",
                    "predict_rlm",
                    "OPENAI_API_KEY",
                ],
                "configured_model_providers": [],
            }
        ),
        "user": None,
        "assistant": None,
    }

    try:
        import httpx

        response = httpx.get(f"{config.api_url}/health", timeout=2.0)
        payload["api_health"] = (
            response.json().get("status", "unknown") if response.status_code == 200 else "error"
        )
    except Exception:
        payload["api_health"] = "unreachable"

    try:
        prepare_runtime_state_sync(
            get_runtime_service() if auth.status().authenticated else None,
            install_method="npm",
        )
        if auth.status().authenticated:
            user = auth.whoami()
            payload["user"] = {"email": user.email, "name": user.name, "plan": user.plan}
            overview = assistant_service.overview()
            if overview is not None:
                payload["assistant"] = {
                    "name": overview.name,
                    "status": overview.status,
                    "onboarding_status": overview.onboarding_status,
                    "assistant_id": overview.assistant_id,
                    "workspace": overview.workspace,
                    "session_count": overview.session_count,
                    "gateway_status": overview.gateway.status,
                }
    except CLIServiceError:
        pass

    return payload


def setup_inspect_environment() -> dict[str, Any]:
    return system_info()


def setup_start(
    mode: str,
    assistant_name: str,
    action_type: str | None = None,
    openclaw_install_method: str = "npm",
) -> dict[str, Any]:
    config = get_config()
    if not get_auth_service().status().authenticated:
        return _failure(
            "Not authenticated. Authenticate through the desktop flow before running setup."
        )

    if mode == "local":
        try:
            ensure_local_control_plane(
                api_url=LOCAL_API_URL,
                progress=None,
                container_runtime_ensurer=lambda progress: ensure_local_container_runtime(
                    progress=progress,
                    prompt_install=None,
                ),
            )
            config.api_url = LOCAL_API_URL
        except Exception as exc:  # noqa: BLE001
            return _failure(f"Local control plane failed: {exc}")
    else:
        config.api_url = HOSTED_API_URL

    effective_action = action_type or ("import" if find_openclaw_bin() else "install")
    install_openclaw = effective_action == "install"

    try:
        result = run_openclaw_setup_wizard(
            mode=mode,
            assistant_name=assistant_name,
            description=None,
            replicas=1,
            model=None,
            workspace=None,
            install_openclaw=install_openclaw,
            openclaw_install_method=openclaw_install_method,
            no_input=True,
            templates_service=get_templates_service(),
            assistant_service=get_assistant_service(),
            runtime_service=get_runtime_service(),
            requested_action=effective_action,
            progress=None,
        )
        return _success(
            {
                "mode": mode,
                "assistant_id": result.binding.agent_id,
                "workspace": result.binding.workspace,
                "deployment": result.deployment,
                "action_type": result.action_type,
            }
        )
    except CLIServiceError as exc:
        return _failure(str(exc))


def setup_get_state() -> dict[str, Any]:
    return load_wizard_state("openclaw")


def runtime_inspect() -> dict[str, Any]:
    return {
        "openclaw": load_manifest("openclaw") or collect_openclaw_runtime_snapshot().to_payload(),
        "faramesh": asdict(collect_faramesh_snapshot()),
        "local_control_plane": {
            "ready": local_control_plane_ready(),
            "path": str(managed_local_control_root()),
        },
    }


def runtime_resync() -> dict[str, Any]:
    try:
        result = prepare_runtime_state_sync(get_runtime_service(), install_method="npm")
        return _success({"result": result})
    except CLIServiceError as exc:
        return _failure(str(exc))


def runtime_open_surface(surface: str = "tui") -> dict[str, Any]:
    manifest = load_manifest("openclaw") or collect_openclaw_runtime_snapshot().to_payload()
    gateway_url = manifest.get("gateway_url")

    try:
        command = build_openclaw_surface_command(surface=surface, gateway_url=gateway_url)
        _open_command_in_terminal(command)
        return _success()
    except CLIServiceError as exc:
        return _failure(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _failure(str(exc))


def control_plane_status() -> dict[str, Any]:
    checkout_root = managed_local_control_checkout()
    return {
        "ready": local_control_plane_ready(),
        "path": str(checkout_root),
        "exists": checkout_root.exists(),
    }


def control_plane_start() -> dict[str, Any]:
    try:
        ensure_local_control_plane(
            api_url=LOCAL_API_URL,
            progress=None,
            container_runtime_ensurer=lambda progress: ensure_local_container_runtime(
                progress=progress,
                prompt_install=None,
            ),
        )
        return _success({"ready": local_control_plane_ready()})
    except Exception as exc:  # noqa: BLE001
        return _failure(str(exc))


def control_plane_stop() -> dict[str, Any]:
    checkout_root = managed_local_control_checkout()
    dev_script = checkout_root / "scripts" / "dev.sh"
    if not dev_script.exists():
        return _success({"message": "No managed local control plane checkout found"})

    result = subprocess.run(
        ["/bin/bash", str(dev_script), "down"],
        cwd=checkout_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip() or "Could not stop local control plane"
        return _failure(message)
    return _success({"message": "Local control plane stopped"})


def _local_assistant_binding() -> tuple[dict[str, Any] | None, dict[str, Any]]:
    runtime_snapshot = collect_openclaw_runtime_snapshot().to_payload()
    bindings = runtime_snapshot.get("bindings")
    current_binding = runtime_snapshot.get("current_binding")

    binding = current_binding if isinstance(current_binding, dict) else None
    if binding is None and isinstance(bindings, list):
        for item in bindings:
            if isinstance(item, dict):
                binding = item
                break

    return binding, runtime_snapshot


def assistant_overview() -> dict[str, Any]:
    binding, runtime_snapshot = _local_assistant_binding()

    if binding is None:
        return {"found": False}

    assistant_id = str(
        binding.get("assistant_id") or binding.get("agent_id") or binding.get("id") or ""
    ).strip()
    assistant_name = str(
        binding.get("assistant_name") or binding.get("name") or assistant_id or "Assistant"
    ).strip()
    workspace = str(binding.get("workspace") or "").strip() or None
    sessions = list_local_sessions(assistant_id=assistant_id or None)
    gateway = (
        runtime_snapshot.get("gateway") if isinstance(runtime_snapshot.get("gateway"), dict) else {}
    )

    return {
        "found": True,
        "agent_id": assistant_id or None,
        "name": assistant_name,
        "status": "running" if sessions else "ready",
        "onboarding_status": "local-bound",
        "assistant_id": assistant_id or None,
        "workspace": workspace,
        "session_count": len(sessions),
        "gateway": gateway,
        "deployments": [],
        "installed_skills": [],
    }


def assistant_sessions() -> list[dict[str, Any]]:
    binding, _runtime_snapshot = _local_assistant_binding()
    if binding is None:
        return []

    assistant_id = str(
        binding.get("assistant_id") or binding.get("agent_id") or binding.get("id") or ""
    ).strip()
    return list_local_sessions(assistant_id=assistant_id or None)


def agents_list() -> list[dict[str, Any]]:
    try:
        agents = get_agents_service().list_agents(limit=50)
        return [
            {
                "id": agent.id,
                "name": agent.name,
                "type": agent.type,
                "status": agent.status,
                "description": agent.description,
                "created_at": str(agent.created_at) if agent.created_at else None,
                "updated_at": str(agent.updated_at) if agent.updated_at else None,
            }
            for agent in agents
        ]
    except CLIServiceError:
        return []


def agents_create(name: str, description: str = "", agent_type: str = "openai") -> dict[str, Any]:
    try:
        agent = get_agents_service().create_agent(
            name=name,
            description=description,
            agent_type=agent_type,
        )
        return _success(
            {
                "id": agent.id,
                "name": agent.name,
                "type": agent.type,
                "status": agent.status,
            }
        )
    except CLIServiceError as exc:
        return _failure(str(exc))


def agents_stop(agent_id: str) -> dict[str, Any]:
    try:
        get_agents_service().stop_agent(agent_id)
        return _success()
    except CLIServiceError as exc:
        return _failure(str(exc))


def governance_status() -> dict[str, Any]:
    snapshot = collect_faramesh_snapshot()
    return {
        "provider": snapshot.provider,
        "status": snapshot.status,
        "version": snapshot.version,
        "decisions_total": snapshot.decisions_total,
        "permits_today": snapshot.permits_today,
        "denies_today": snapshot.denies_today,
        "defers_today": snapshot.defers_today,
        "pending_approvals": snapshot.pending_approvals,
        "last_decision_at": snapshot.last_decision_at,
    }


def governance_restart() -> dict[str, Any]:
    if is_faramesh_available():
        return _success({"already_running": True, "socket_path": FAREMESH_SOCKET_PATH})
    policy_path = get_default_policy_path()
    if not policy_path:
        return _failure("No policy file found")
    proc = start_faramesh_daemon(policy_path=policy_path)
    if proc is None:
        return _failure("Failed to start Faramesh daemon")
    return _success({"socket_path": FAREMESH_SOCKET_PATH})


def finder_reveal(path: Any = None) -> dict[str, Any]:
    expanded, error = _expand_path_argument(path, "Finder path")
    if error or expanded is None:
        return _failure(error or "Finder path is invalid")

    try:
        if not expanded.exists():
            return _failure(f"Path does not exist: {path}")
        result = subprocess.run(
            ["open", "-R", str(expanded)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return _failure(f"Could not reveal path in Finder: {exc}")

    if result.returncode != 0:
        return _failure("Finder could not reveal the requested path")
    return _success()


def shell_open_terminal(cwd: Any = None) -> dict[str, Any]:
    expanded: Path | None = None
    if cwd is not None:
        expanded, error = _expand_path_argument(cwd, "Terminal working directory")
        if error or expanded is None:
            return _failure(error or "Terminal working directory is invalid")

    try:
        if expanded is not None and (not expanded.exists() or not expanded.is_dir()):
            return _failure(f"Terminal working directory does not exist: {cwd}")

        command = ["open", "-a", "Terminal"]
        if expanded is not None:
            command.append(str(expanded))
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        return _failure(f"Could not open Terminal: {exc}")

    if result.returncode != 0:
        return _failure("Terminal could not open the requested working directory")
    return _success({"cwd": str(expanded) if expanded is not None else None})


def dialog_choose_workspace() -> dict[str, Any]:
    script = """
set theChoice to choose folder with prompt "Choose MUTX Workspace"
POSIX path of theChoice
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return _success({"path": result.stdout.strip()})
        return _failure("No folder selected")
    except Exception as exc:  # noqa: BLE001
        return _failure(str(exc))


def dialog_choose_files(allow_multiple: bool = True) -> dict[str, Any]:
    multiple_clause = "with multiple selections allowed" if allow_multiple else ""
    script = f"""
set theChoice to choose file with prompt "Choose Document Files" {multiple_clause}
if class of theChoice is list then
  set outPaths to {{}}
  repeat with itemRef in theChoice
    set end of outPaths to POSIX path of itemRef
  end repeat
  return outPaths as string
else
  return POSIX path of theChoice
end if
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return _failure("No files selected")
        raw = result.stdout.strip()
        paths = [item.strip() for item in raw.split(",") if item.strip()]
        return _success({"paths": paths})
    except Exception as exc:  # noqa: BLE001
        return _failure(str(exc))


def documents_list_templates() -> dict[str, Any]:
    try:
        templates = get_documents_service().list_templates()
        return _success({"items": [asdict(item) for item in templates]})
    except CLIServiceError as exc:
        return _failure(str(exc))


def documents_list_jobs(limit: int = 20, status_filter: str | None = None) -> dict[str, Any]:
    try:
        history = get_documents_service().list_jobs(limit=limit, status_filter=status_filter)
        return _success({"items": [asdict(item) for item in history.items], "total": history.total})
    except CLIServiceError as exc:
        return _failure(str(exc))


def documents_get_job(job_id: str) -> dict[str, Any]:
    try:
        return _success({"job": asdict(get_documents_service().get_job(job_id))})
    except CLIServiceError as exc:
        return _failure(str(exc))


def documents_create_job(
    template_id: str,
    execution_mode: str = "local",
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        job = get_documents_service().create_job(
            template_id=template_id,
            execution_mode=execution_mode,
            parameters=parameters,
        )
        return _success({"job": asdict(job)})
    except CLIServiceError as exc:
        return _failure(str(exc))


def documents_register_local_artifact(
    job_id: str,
    role: str,
    kind: str,
    file_path: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        artifact = get_documents_service().register_artifact_reference(
            job_id=job_id,
            role=role,
            kind=kind,
            file_path=file_path,
            metadata=metadata,
        )
        return _success({"artifact": asdict(artifact)})
    except CLIServiceError as exc:
        return _failure(str(exc))


def documents_launch_local(job_id: str, output_dir: str | None = None) -> dict[str, Any]:
    try:
        launch = get_documents_service().launch_local(job_id=job_id, output_dir=output_dir)
        return _success({"launch": asdict(launch)})
    except CLIServiceError as exc:
        return _failure(str(exc))


def documents_run_local(job_id: str, output_dir: str | None = None) -> dict[str, Any]:
    try:
        service = get_documents_service()
        job = service.get_job(job_id)
        result = service.run_local_job(job=job, output_dir=output_dir)
        return _success({"job": asdict(result)})
    except CLIServiceError as exc:
        return _failure(str(exc))


def documents_submit_event(
    job_id: str,
    event_type: str,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    status_value: str | None = None,
    output_text: str | None = None,
    error_message: str | None = None,
    result_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        job = get_documents_service().submit_event(
            job_id=job_id,
            event_type=event_type,
            message=message,
            payload=payload,
            status_value=status_value,
            output_text=output_text,
            error_message=error_message,
            result_summary=result_summary,
        )
        return _success({"job": asdict(job)})
    except CLIServiceError as exc:
        return _failure(str(exc))


def documents_upload_artifact(
    job_id: str,
    role: str,
    kind: str,
    file_path: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        artifact = get_documents_service().upload_artifact(
            job_id=job_id,
            role=role,
            kind=kind,
            file_path=file_path,
            metadata=metadata,
        )
        return _success({"artifact": asdict(artifact)})
    except CLIServiceError as exc:
        return _failure(str(exc))


def documents_download_artifact(
    job_id: str,
    artifact_id: str,
    destination: str | None = None,
) -> dict[str, Any]:
    try:
        path = get_documents_service().download_artifact(
            job_id=job_id,
            artifact_id=artifact_id,
            destination=destination,
        )
        return _success({"path": str(path)})
    except CLIServiceError as exc:
        return _failure(str(exc))


METHODS = {
    "system.info": system_info,
    "auth.status": auth_status,
    "auth.login": auth_login,
    "auth.register": auth_register,
    "auth.localBootstrap": auth_local_bootstrap,
    "auth.storeTokens": auth_store_tokens,
    "auth.logout": auth_logout,
    "doctor.run": doctor_run,
    "setup.inspectEnvironment": setup_inspect_environment,
    "setup.start": setup_start,
    "setup.getState": setup_get_state,
    "runtime.inspect": runtime_inspect,
    "runtime.resync": runtime_resync,
    "runtime.openSurface": runtime_open_surface,
    "controlPlane.status": control_plane_status,
    "controlPlane.start": control_plane_start,
    "controlPlane.stop": control_plane_stop,
    "assistant.overview": assistant_overview,
    "assistant.sessions": assistant_sessions,
    "agents.list": agents_list,
    "agents.create": agents_create,
    "agents.stop": agents_stop,
    "governance.status": governance_status,
    "governance.restart": governance_restart,
    "finder.reveal": finder_reveal,
    "shell.openTerminal": shell_open_terminal,
    "dialog.chooseWorkspace": dialog_choose_workspace,
    "dialog.chooseFiles": dialog_choose_files,
    "documents.listTemplates": documents_list_templates,
    "documents.listJobs": documents_list_jobs,
    "documents.getJob": documents_get_job,
    "documents.createJob": documents_create_job,
    "documents.registerLocalArtifact": documents_register_local_artifact,
    "documents.launchLocal": documents_launch_local,
    "documents.runLocal": documents_run_local,
    "documents.submitEvent": documents_submit_event,
    "documents.uploadArtifact": documents_upload_artifact,
    "documents.downloadArtifact": documents_download_artifact,
}


def handle_request(data: dict[str, Any]) -> dict[str, Any]:
    method_name = data.get("method")
    params = data.get("params", {})
    msg_id = data.get("id")
    if method_name in EXIT_COMMANDS:
        return {"id": msg_id, "result": "goodbye"}

    handler = METHODS.get(str(method_name))
    if handler is None:
        return {"id": msg_id, "error": f"Unknown method: {method_name}"}

    try:
        if isinstance(params, dict):
            result = handler(**params)
        elif isinstance(params, list):
            result = handler(*params)
        elif params is None:
            result = handler()
        else:
            result = handler(params)
        return {"id": msg_id, "result": result}
    except TypeError as exc:
        return {"id": msg_id, "error": f"Invalid parameters: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"id": msg_id, "error": str(exc)}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line in EXIT_COMMANDS:
            break
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        print(json.dumps(handle_request(data)), flush=True)


if __name__ == "__main__":
    main()
