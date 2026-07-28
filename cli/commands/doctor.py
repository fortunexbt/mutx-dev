import json

import click
import httpx

from cli.config import current_config
from cli.openclaw_runtime import collect_openclaw_runtime_snapshot, get_gateway_health
from cli.services import AssistantService, AuthService, CLIServiceError, RuntimeStateService
from cli.setup_wizard import prepare_runtime_state_sync

try:
    from src.api.services.document_engine import get_document_engine_readiness
except Exception:  # noqa: BLE001
    get_document_engine_readiness = None


@click.command(name="doctor")
@click.option("--output", type=click.Choice(["table", "json"]), default="table")
def doctor_command(output: str):
    config = current_config()
    auth = AuthService(config=config)
    assistant_service = AssistantService(config=config)
    runtime_service = RuntimeStateService(config=config)

    payload: dict[str, object] = {
        "api_url": config.api_url,
        "api_url_source": config.api_url_source,
        "config_path": str(config.config_path),
        "authenticated": auth.status().authenticated,
        "api_health": "unreachable",
        "openclaw": get_gateway_health().to_payload(),
        "runtime_snapshot": collect_openclaw_runtime_snapshot().to_payload(),
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
        response = httpx.get(f"{config.api_url}/health", timeout=2.0)
        if response.status_code == 200:
            health_payload = response.json()
            payload["api_health"] = (
                health_payload.get("status", "unknown")
                if isinstance(health_payload, dict)
                else "invalid-response"
            )
        else:
            payload["api_health"] = "error"
    except ValueError:
        payload["api_health"] = "invalid-response"
    except httpx.HTTPError:
        payload["api_health"] = "unreachable"

    try:
        prepare_runtime_state_sync(
            runtime_service if auth.status().authenticated else None,
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

    if output == "json":
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(f"API URL: {payload['api_url']} ({payload['api_url_source']})")
    click.echo(f"Config Path: {payload['config_path']}")
    click.echo(f"Authenticated: {'yes' if payload['authenticated'] else 'no'}")
    click.echo(f"API Health: {payload['api_health']}")
    click.echo(
        "OpenClaw: "
        f"{payload['openclaw']['status']} | "
        f"gateway={payload['openclaw']['gateway_url'] or 'n/a'} | "
        f"onboarded={'yes' if payload['openclaw']['onboarded'] else 'no'}"
    )
    click.echo(
        "Registry: "
        f"bindings={payload['runtime_snapshot']['binding_count']} | "
        f"binary={payload['runtime_snapshot']['binary_path'] or 'n/a'} | "
        f"home={payload['runtime_snapshot']['home_path'] or 'n/a'} | "
        f"last_seen={payload['runtime_snapshot']['last_seen_at'] or 'n/a'}"
    )
    if payload["runtime_snapshot"].get("adopted_existing_runtime"):
        click.echo("Registry Adoption: existing OpenClaw runtime imported into MUTX tracking")
    click.echo(
        "Privacy: "
        f"{payload['runtime_snapshot']['privacy_summary'] or 'Local-only runtime tracking.'}"
    )
    click.echo(
        "Documents: "
        f"enabled={'yes' if payload['documents']['enabled'] else 'no'} | "
        f"ready={'yes' if payload['documents']['ready'] else 'no'} | "
        f"driver={payload['documents']['driver']} | "
        f"deno={'yes' if payload['documents']['deno_available'] else 'no'} | "
        f"predict_rlm={'yes' if payload['documents']['predict_rlm_available'] else 'no'} | "
        f"credentials={'yes' if payload['documents']['credentials_ok'] else 'no'}"
    )
    if payload["documents"].get("missing_requirements"):
        click.echo(
            "Documents Missing: "
            + ", ".join(str(item) for item in payload["documents"]["missing_requirements"])
        )
    if payload["user"]:
        click.echo(
            f"User: {payload['user']['email']} | {payload['user']['name']} | {payload['user']['plan']}"
        )
    if payload["assistant"]:
        click.echo(
            "Assistant: "
            f"{payload['assistant']['name']} | {payload['assistant']['status']} | "
            f"{payload['assistant']['onboarding_status']} | sessions={payload['assistant']['session_count']} | "
            f"gateway={payload['assistant']['gateway_status']} | "
            f"assistant_id={payload['assistant']['assistant_id']}"
        )
