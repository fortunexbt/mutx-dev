from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import click
import httpx

from cli.errors import CLIServiceError
from cli.services.base import APIService

from cli.faramesh_runtime import (
    FAREMESH_SOCKET_PATH,
    approve_defer,
    collect_faramesh_snapshot,
    deny_defer,
    ensure_faramesh_installed,
    find_faramesh_bin,
    generate_prometheus_metrics,
    get_default_policy_path,
    get_faramesh_health,
    get_pending_defers,
    get_recent_decisions,
    is_faramesh_available,
    kill_agent,
    list_policy_packs,
    reload_policy,
    start_faramesh_daemon,
    validate_policy,
)


def _ensure_faramesh() -> bool:
    """Ensure Faramesh is installed and the daemon is running."""
    if is_faramesh_available():
        return True

    installed, bin_path = ensure_faramesh_installed(install_if_missing=True, non_interactive=True)
    if not installed:
        click.echo("Failed to install Faramesh.", err=True)
        return False

    policy_path = get_default_policy_path()
    proc = start_faramesh_daemon(policy_path=policy_path, socket_path=FAREMESH_SOCKET_PATH)
    if proc is None:
        click.echo("Failed to start Faramesh daemon.", err=True)
        return False

    for _ in range(10):
        time.sleep(0.5)
        if is_faramesh_available():
            return True

    click.echo("Faramesh daemon started but is not responding.", err=True)
    return False


class _GovernanceGroup(click.Group):
    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except httpx.HTTPStatusError as exc:
            response = exc.response
            try:
                payload = response.json()
            except Exception:
                payload = None
            detail = payload.get("detail") if isinstance(payload, dict) else None
            message = detail if isinstance(detail, str) else "Governance request failed."
            raise click.ClickException(message) from exc
        except httpx.HTTPError as exc:
            raise click.ClickException("Could not reach the MUTX API.") from exc
        except CLIServiceError as exc:
            raise click.ClickException(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise click.ClickException("API returned malformed JSON.") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise click.ClickException("API returned an unexpected response shape.") from exc


@click.group(name="governance", cls=_GovernanceGroup)
def governance_group():
    """Inspect Faramesh governance engine state (read-only)."""
    pass


def _governance_client():
    from cli.config import current_config, get_client

    config = current_config()
    if not config.is_authenticated():
        click.echo("Error: Not authenticated. Run 'mutx login' first.", err=True)
        sys.exit(1)

    service = APIService(config=config, client_factory=get_client)

    class GovernanceClient:
        @staticmethod
        def _request(method: str, path: str, ok_statuses: set[int], **kwargs):
            response = service.request_response(method, path, **kwargs)
            service._expect_status(response, ok_statuses)
            return response

        def get(self, path: str, *, ok_statuses: set[int] | None = None, **kwargs):
            return self._request("get", path, ok_statuses or {200}, **kwargs)

        def post(self, path: str, *, ok_statuses: set[int] | None = None, **kwargs):
            return self._request("post", path, ok_statuses or {200}, **kwargs)

        def delete(self, path: str, *, ok_statuses: set[int] | None = None, **kwargs):
            return self._request("delete", path, ok_statuses or {200}, **kwargs)

    return GovernanceClient()


@governance_group.command(name="doctor")
def doctor_command() -> None:
    """Summarize governance attestation posture."""
    client = _governance_client()
    response = client.get("/v1/governance/attestations")
    response.raise_for_status()
    payload = response.json()
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}

    click.echo("Governance Doctor")
    click.echo("=" * 50)
    click.echo(f"  Identities:          {summary.get('identities', 0)}")
    click.echo(f"  Discovery items:     {summary.get('discovery_items', 0)}")
    click.echo(f"  Credential backends: {summary.get('credential_backends', 0)}")
    click.echo(f"  Supervised agents:   {summary.get('supervised_agents', 0)}")
    click.echo(f"  Pending approvals:   {summary.get('pending_approvals', 0)}")


@governance_group.command(name="verify")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def verify_command(output_json: bool) -> None:
    """Verify governance attestations."""
    client = _governance_client()
    response = client.post("/v1/governance/attestations/verify")
    response.raise_for_status()
    payload = response.json()

    if output_json:
        click.echo(json.dumps(payload, indent=2))
        return

    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    click.echo("Governance attestation verification")
    click.echo(f"  Identities:          {summary.get('identities', 0)}")
    click.echo(f"  Discovery items:     {summary.get('discovery_items', 0)}")
    click.echo(f"  Credential backends: {summary.get('credential_backends', 0)}")


@governance_group.group(name="trust")
def trust_group() -> None:
    """Inspect and adjust governance trust records."""
    pass


@trust_group.command(name="list")
def trust_list_command() -> None:
    """List governance trust records."""
    client = _governance_client()
    response = client.get("/v1/governance/trust")
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items", []) if isinstance(payload, dict) else []

    if not items:
        click.echo("No governance trust records found.")
        return

    click.echo(f"{'AGENT':<24} {'SCORE':<8} {'TIER':<14} {'LIFECYCLE'}")
    click.echo("-" * 70)
    for item in items:
        click.echo(
            f"{item.get('agent_id', '-'):<24} {item.get('trust_score', '-')!s:<8} "
            f"{item.get('trust_tier', '-'):<14} {item.get('lifecycle_status', '-')}"
        )


@governance_group.group(name="lifecycle")
def lifecycle_group() -> None:
    """Manage governance lifecycle state."""
    pass


@lifecycle_group.command(name="set")
@click.argument("agent_id")
@click.argument("state")
@click.option("--reason", default=None, help="Reason for the lifecycle change")
@click.option("--apply-runtime-action/--no-apply-runtime-action", default=True)
def lifecycle_set_command(
    agent_id: str, state: str, reason: str | None, apply_runtime_action: bool
) -> None:
    """Set lifecycle state for an agent."""
    client = _governance_client()
    payload = {
        "state": state,
        "apply_runtime_action": apply_runtime_action,
    }
    if reason is not None:
        payload["reason"] = reason
    response = client.post(f"/v1/governance/lifecycle/{agent_id}", json=payload)
    response.raise_for_status()
    result = response.json()
    click.echo(
        f"{result.get('agent_id', agent_id)} lifecycle state: "
        f"{result.get('lifecycle_status', state)}"
    )


@governance_group.group(name="discovery")
def discovery_group() -> None:
    """Inspect governance discovery inventory."""
    pass


@discovery_group.command(name="scan")
def discovery_scan_command() -> None:
    """Run a governance discovery scan."""
    client = _governance_client()
    response = client.post("/v1/governance/discovery/scan")
    response.raise_for_status()
    payload = response.json()
    click.echo(f"Scanned {payload.get('count', 0)} entities")


@governance_group.command(name="status")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def status_command(output_json: bool) -> None:
    """Show Faramesh daemon health and policy status."""
    health = get_faramesh_health()
    snapshot = collect_faramesh_snapshot()

    if output_json:
        click.echo(json.dumps(snapshot.to_payload(), indent=2))
        return

    if health.doctor_summary:
        for line in health.doctor_summary.split("\n"):
            click.echo(f"  {line}")
    else:
        click.echo(f"  Status:       {snapshot.status}")
        click.echo(f"  Socket:       {'reachable' if health.socket_reachable else 'not found'}")
        click.echo(f"  Daemon:       {'running' if health.daemon_reachable else 'not reachable'}")
        click.echo(f"  Version:      {health.version or 'unknown'}")
        click.echo(f"  Policy:       {health.policy_name or 'none loaded'}")
        click.echo(f"  Decisions:    {health.decisions_total} total")
        click.echo(f"  Denied:       {health.denied_today} today")
        click.echo(f"  Deferred:     {health.deferred_today} today")
        click.echo(f"  Pending:      {health.pending_approvals} awaiting approval")


@governance_group.command(name="decisions")
@click.option("--limit", "-n", default=20, help="Number of recent decisions to show")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def decisions_command(limit: int, output_json: bool) -> None:
    """Show recent governance decisions (PERMIT/DENY/DEFER)."""
    if not is_faramesh_available():
        click.echo("Faramesh daemon is not running.", err=True)
        click.echo("Start it with: faramesh serve --policy policy.yaml", err=True)
        sys.exit(1)

    try:
        decisions = get_recent_decisions(limit=limit)
    except Exception as exc:
        click.echo(f"Error fetching decisions: {exc}", err=True)
        sys.exit(1)

    if output_json:
        click.echo(json.dumps([d.__dict__ for d in decisions], indent=2, default=str))
        return

    if not decisions:
        click.echo("No recent decisions found.")
        return

    click.echo(f"{'EFFECT':<8} {'TOOL_ID':<25} {'AGENT':<20} {'RULE':<15} {'LATENCY'}")
    click.echo("-" * 85)
    for d in decisions:
        if not d.effect:
            continue
        rule = d.rule_id or "-"
        agent = d.agent_id or "-"
        if len(agent) > 18:
            agent = agent[:15] + "..."
        latency = f"{d.latency_ms}ms" if d.latency_ms else "-"
        effect_color = ""
        if d.effect == "PERMIT":
            effect_color = "\033[92m"
        elif d.effect == "DENY":
            effect_color = "\033[91m"
        elif d.effect == "DEFER":
            effect_color = "\033[93m"
        reset = "\033[0m"
        click.echo(
            f"{effect_color}{d.effect:<8}{reset} {d.tool_id or '-':<25} {agent:<20} {rule:<15} {latency}"
        )


@governance_group.command(name="pending")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def pending_command(output_json: bool) -> None:
    """Show pending approval requests (DEFER queue)."""
    if not is_faramesh_available():
        click.echo("Faramesh daemon is not running.", err=True)
        click.echo("Start it with: faramesh serve --policy policy.yaml", err=True)
        sys.exit(1)

    try:
        defers = get_pending_defers()
    except Exception as exc:
        click.echo(f"Error fetching pending: {exc}", err=True)
        sys.exit(1)

    if output_json:
        click.echo(json.dumps([d.__dict__ for d in defers], indent=2, default=str))
        return

    if not defers:
        click.echo("No pending approvals.")
        return

    click.echo(f"{'TOKEN':<12} {'AGENT':<20} {'TOOL':<20} {'STATUS'}")
    click.echo("-" * 70)
    for d in defers:
        agent = d.agent_id or "-"
        if len(agent) > 18:
            agent = agent[:15] + "..."
        status_color = "\033[93m"
        reset = "\033[0m"
        click.echo(
            f"{d.defer_token[:12]:<12} {agent:<20} {d.tool_id:<20} {status_color}{d.status}{reset}"
        )

    click.echo(f"\n{len(defers)} pending approval(s).")
    click.echo("To approve/deny, use: faramesh agent approve|deny <token>")


@governance_group.command(name="metrics")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def metrics_command(output_json: bool) -> None:
    """Show governance metrics and statistics."""
    if not is_faramesh_available():
        click.echo("Faramesh daemon is not running.", err=True)
        click.echo("Start it with: faramesh serve --policy policy.yaml", err=True)
        sys.exit(1)

    try:
        decisions = get_recent_decisions(limit=200)
        defers = get_pending_defers()
    except Exception as exc:
        click.echo(f"Error fetching metrics: {exc}", err=True)
        sys.exit(1)

    total = len(decisions)
    permits = sum(1 for d in decisions if d.effect == "PERMIT")
    denies = sum(1 for d in decisions if d.effect == "DENY")
    defer_count = sum(1 for d in decisions if d.effect == "DEFER")
    avg_latency = 0
    if decisions:
        latencies = [d.latency_ms for d in decisions if d.latency_ms]
        if latencies:
            avg_latency = sum(latencies) // len(latencies)

    if output_json:
        click.echo(
            json.dumps(
                {
                    "decisions_total": total,
                    "permits": permits,
                    "denies": denies,
                    "deferred": defer_count,
                    "pending_approvals": len(defers),
                    "avg_latency_ms": avg_latency,
                },
                indent=2,
            )
        )
        return

    permit_pct = (permits / total * 100) if total > 0 else 0
    deny_pct = (denies / total * 100) if total > 0 else 0
    defer_pct = (defer_count / total * 100) if total > 0 else 0

    click.echo("Governance Metrics")
    click.echo("=" * 40)
    click.echo(f"  Total Decisions:   {total}")
    click.echo(f"  Permits:            {permits} ({permit_pct:.1f}%)")
    click.echo(f"  Denies:             {denies} ({deny_pct:.1f}%)")
    click.echo(f"  Defers:             {defer_count} ({defer_pct:.1f}%)")
    click.echo(f"  Pending Approvals:  {len(defers)}")
    click.echo(f"  Avg Latency:        {avg_latency}ms")


@governance_group.command(name="tail")
@click.option("--limit", "-n", default=0, help="Stop after N decisions (0=unlimited)")
def tail_command(limit: int) -> None:
    """Stream live governance decisions (Ctrl+C to stop)."""
    if not is_faramesh_available():
        click.echo("Faramesh daemon is not running.", err=True)
        click.echo("Start it with: faramesh serve --policy policy.yaml", err=True)
        sys.exit(1)

    from cli.faramesh_runtime import _send_socket_request

    interrupted = False

    def handler(signum, frame):
        nonlocal interrupted
        interrupted = True
        click.echo("\nStopped.")

    signal.signal(signal.SIGINT, handler)

    click.echo("Streaming decisions... (Ctrl+C to stop)")
    click.echo(f"{'TIME':<10} {'EFFECT':<8} {'TOOL_ID':<25} {'AGENT':<15}")
    click.echo("-" * 65)

    count = 0
    try:
        while not interrupted:
            if limit > 0 and count >= limit:
                break

            request = {"type": "audit_subscribe"}
            responses = _send_socket_request(FAREMESH_SOCKET_PATH, request, timeout=1.0)

            for resp in responses:
                if not isinstance(resp, dict):
                    continue
                effect = resp.get("effect", "")
                if not effect:
                    continue

                ts = time.strftime("%H:%M:%S")
                tool_id = str(resp.get("tool_id") or "-")
                agent = str(resp.get("agent_id") or "-")
                if len(tool_id) > 23:
                    tool_id = tool_id[:20] + "..."
                if len(agent) > 13:
                    agent = agent[:10] + "..."

                effect_color = ""
                if effect == "PERMIT":
                    effect_color = "\033[92m"
                elif effect == "DENY":
                    effect_color = "\033[91m"
                elif effect == "DEFER":
                    effect_color = "\033[93m"
                reset = "\033[0m"

                click.echo(f"{ts:<10} {effect_color}{effect:<8}{reset} {tool_id:<25} {agent:<15}")
                count += 1
                if limit > 0 and count >= limit:
                    break

            if not responses:
                time.sleep(0.5)

    except Exception as exc:
        click.echo(f"\nError: {exc}", err=True)
        sys.exit(1)


@governance_group.command(name="start")
@click.option(
    "--policy", "-p", type=click.Path(exists=False), default=None, help="Policy file path"
)
@click.option(
    "--install/--no-install", "auto_install", default=True, help="Install Faramesh if missing"
)
def start_command(policy: str | None, auto_install: bool) -> None:
    """Install Faramesh if needed and start the governance daemon."""
    if is_faramesh_available():
        click.echo("Faramesh daemon is already running.")
        return

    if auto_install:
        installed, bin_path = ensure_faramesh_installed(
            install_if_missing=True, non_interactive=True
        )
        if not installed:
            click.echo("Failed to install Faramesh.", err=True)
            sys.exit(1)
        click.echo(f"Faramesh installed: {bin_path}")

    if not find_faramesh_bin():
        click.echo(
            "Faramesh is not installed. Use --install or run with --no-install to skip.", err=True
        )
        sys.exit(1)

    policy_path = policy or get_default_policy_path()

    if policy_path:
        click.echo(f"Starting daemon with policy: {policy_path}")
    else:
        click.echo("Starting daemon without a policy file.")

    proc = start_faramesh_daemon(policy_path=policy_path, socket_path=FAREMESH_SOCKET_PATH)
    if proc is None:
        click.echo("Failed to start Faramesh daemon.", err=True)
        sys.exit(1)

    for i in range(10):
        time.sleep(0.5)
        if is_faramesh_available():
            click.echo("Faramesh daemon is now running.")
            return

    click.echo("Faramesh daemon started but is not responding.", err=True)
    sys.exit(1)


@governance_group.command(name="approve")
@click.argument("token")
def approve_command(token: str) -> None:
    """Approve a deferred governance decision."""
    if not _ensure_faramesh():
        sys.exit(1)

    click.echo(f"Approving deferred action: {token}")
    success = approve_defer(FAREMESH_SOCKET_PATH, token)
    if success:
        click.echo("Approved.")
    else:
        click.echo("Approval failed.", err=True)
        sys.exit(1)


@governance_group.command(name="deny")
@click.argument("token")
def deny_command(token: str) -> None:
    """Deny a deferred governance decision."""
    if not _ensure_faramesh():
        sys.exit(1)

    click.echo(f"Denying deferred action: {token}")
    success = deny_defer(FAREMESH_SOCKET_PATH, token)
    if success:
        click.echo("Denied.")
    else:
        click.echo("Denial failed.", err=True)
        sys.exit(1)


@governance_group.command(name="kill")
@click.argument("agent_id")
def kill_command(agent_id: str) -> None:
    """Emergency kill an agent (stops all pending actions)."""
    if not _ensure_faramesh():
        sys.exit(1)

    click.echo(f"Emergency kill for agent: {agent_id}")
    success = kill_agent(FAREMESH_SOCKET_PATH, agent_id)
    if success:
        click.echo("Agent killed.")
    else:
        click.echo("Kill failed.", err=True)
        sys.exit(1)


@governance_group.group(name="policy")
def policy_group():
    """Policy management commands."""
    pass


@policy_group.command(name="validate")
@click.argument("policy_path", type=click.Path(exists=True))
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def policy_validate_command(policy_path: str, output_json: bool) -> None:
    """Validate an FPL policy file."""
    result = validate_policy(FAREMESH_SOCKET_PATH, policy_path)

    if output_json:
        click.echo(json.dumps(result, indent=2))
        return

    if result.get("valid"):
        click.echo(f"Policy is valid: {policy_path}")
        if result.get("output"):
            click.echo(result["output"])
    else:
        click.echo(f"Policy is invalid: {policy_path}", err=True)
        click.echo(f"Error: {result.get('error', 'unknown')}", err=True)
        sys.exit(1)


@policy_group.command(name="reload")
@click.option("--policy", "-p", type=click.Path(exists=True), default=None, help="New policy file")
def policy_reload_command(policy: str | None) -> None:
    """Hot-reload the running policy (no daemon restart required)."""
    if not _ensure_faramesh():
        sys.exit(1)

    click.echo("Reloading policy...")
    success = reload_policy(FAREMESH_SOCKET_PATH, policy)
    if success:
        click.echo("Policy reloaded.")
    else:
        click.echo("Reload failed.", err=True)
        sys.exit(1)


@policy_group.command(name="list")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def policy_list_command(output_json: bool) -> None:
    """List all bundled policy packs."""
    packs = list_policy_packs()

    if output_json:
        click.echo(json.dumps(packs, indent=2))
        return

    if not packs:
        click.echo("No policy packs found.")
        return

    click.echo("Bundled Policy Packs")
    click.echo("=" * 50)
    for pack in packs:
        click.echo(f"  {pack['name']:<20} {pack['description']}")
        click.echo(f"    {pack['path']}")
        click.echo()


@policy_group.command(name="edit")
@click.option("--policy", "-p", type=click.Path(), default=None, help="Policy file to edit")
def policy_edit_command(policy: str | None) -> None:
    """Edit a policy file in $EDITOR."""
    policy_path = policy or get_default_policy_path()

    if not policy_path:
        click.echo("No policy file found. Use --policy to specify one.", err=True)
        sys.exit(1)

    editor = os.environ.get("EDITOR", "vi")
    try:
        subprocess.call([editor, policy_path])
    except Exception as exc:
        click.echo(f"Failed to open editor: {exc}", err=True)
        sys.exit(1)


@governance_group.group(name="credential")
def credential_group():
    """Credential broker management for governance."""
    pass


def _parse_ttl(ttl_str: str) -> int:
    """Parse TTL string like '15m', '1h', '30s' to seconds."""
    ttl_str = ttl_str.strip().lower()
    if ttl_str.endswith("m"):
        return int(ttl_str[:-1]) * 60
    elif ttl_str.endswith("h"):
        return int(ttl_str[:-1]) * 3600
    elif ttl_str.endswith("s"):
        return int(ttl_str[:-1])
    else:
        return int(ttl_str)


@credential_group.command(name="list")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def credential_list_command(output_json: bool) -> None:
    """List registered credential backends."""
    try:
        client = _governance_client()
        response = client.get("/v1/governance/credentials/backends")
        backends = response.json()

        if output_json:
            click.echo(json.dumps(backends, indent=2))
            return

        if not backends:
            click.echo("Credential Broker Configuration")
            click.echo("=" * 50)
            click.echo("  No credential backends registered.")
            click.echo()
            click.echo(
                "Supported backends: vault, awssecrets, gcpsm, azurekv, onepassword, infisical"
            )
            click.echo(
                "Register with: mutx governance credential register <backend> <name> [options]"
            )
            return

        click.echo("Credential Broker Configuration")
        click.echo("=" * 70)
        click.echo(f"{'Name':<20} {'Backend':<12} {'Path':<20} {'Healthy':<8}")
        click.echo("-" * 70)
        for backend in backends:
            healthy = "yes" if backend.get("is_healthy") else "NO"
            click.echo(
                f"{backend['name']:<20} {backend['backend']:<12} {backend['path']:<20} {healthy:<8}"
            )

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)


@credential_group.command(name="register")
@click.argument(
    "backend",
    type=click.Choice(["vault", "awssecrets", "gcpsm", "azurekv", "onepassword", "infisical"]),
)
@click.argument("name")
@click.option("--path", "-p", required=True, help="Secret path/backend URL")
@click.option("--ttl", "-t", default="15m", help="Credential TTL (e.g., 15m, 1h, 30s)")
@click.option("--url", help="Backend URL (for Vault, Azure, Infisical)")
@click.option("--token", help="API token or secret key")
def credential_register_command(
    backend: str, name: str, path: str, ttl: str, url: str | None, token: str | None
) -> None:
    """Register a credential backend for credential brokering."""
    try:
        config_data = {}
        if url:
            config_data["url"] = url
        if token:
            config_data["token"] = token

        client = _governance_client()
        payload = {
            "name": name,
            "backend": backend,
            "path": path,
            "ttl": _parse_ttl(ttl),
            "config": config_data,
        }

        client.post(
            "/v1/governance/credentials/backends",
            ok_statuses={201},
            json=payload,
        )

        click.echo(f"Credential backend registered: {name} ({backend})")

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)


@credential_group.command(name="unregister")
@click.argument("name")
def credential_unregister_command(name: str) -> None:
    """Unregister a credential backend."""
    try:
        client = _governance_client()
        client.delete(f"/v1/governance/credentials/backends/{name}")

        click.echo(f"Credential backend unregistered: {name}")

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)


@credential_group.command(name="health")
@click.argument("name", required=False)
def credential_health_command(name: str | None) -> None:
    """Check health of credential backends."""
    try:
        client = _governance_client()

        if name:
            response = client.get(f"/v1/governance/credentials/backends/{name}/health")
        else:
            response = client.get("/v1/governance/credentials/health")
        health_data = response.json()

        if name:
            backend_health = health_data
            status = "healthy" if backend_health.get("healthy") else "UNHEALTHY"
            click.echo(f"Backend '{name}': {status}")
        else:
            click.echo("Credential Backend Health")
            click.echo("=" * 50)
            for backend_name, health in health_data.items():
                status = "healthy" if health.get("healthy") else "UNHEALTHY"
                error = health.get("error", "")
                if error:
                    click.echo(f"  {backend_name}: {status} ({error})")
                else:
                    click.echo(f"  {backend_name}: {status}")

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)


@governance_group.command(name="export-metrics")
@click.option("--format", "-f", type=click.Choice(["prometheus", "json"]), default="prometheus")
def export_metrics_command(format: str) -> None:
    """Export governance metrics in Prometheus or JSON format."""
    if not _ensure_faramesh():
        sys.exit(1)

    try:
        snapshot = collect_faramesh_snapshot()
    except Exception as exc:
        click.echo(f"Error fetching metrics: {exc}", err=True)
        sys.exit(1)

    if format == "prometheus":
        click.echo(generate_prometheus_metrics(snapshot))
    else:
        click.echo(json.dumps(snapshot.to_payload(), indent=2))


@governance_group.command(name="bind")
@click.argument("agent_id", required=False)
@click.option("--enable/--disable", default=None, help="Enable or disable governance")
@click.option(
    "--policy", "-p", type=click.Path(exists=True), default=None, help="FPL policy file path"
)
@click.option("--list", "list_policies", is_flag=True, help="List available policy packs")
def bind_command(
    agent_id: str | None, enable: bool | None, policy: str | None, list_policies: bool
) -> None:
    """Bind governance policy to an OpenClaw agent."""
    if list_policies:
        packs = list_policy_packs()
        click.echo("Available Policy Packs")
        click.echo("=" * 50)
        for pack in packs:
            click.echo(f"  {pack['name']}")
            click.echo(f"    {pack['description']}")
            click.echo(f"    Path: {pack['path']}")
            click.echo()
        return

    if agent_id is None:
        click.echo("Specify agent_id or use --list to see available policies", err=True)
        sys.exit(1)

    if enable is None and policy is None:
        click.echo("Specify --enable or --disable, and optionally --policy", err=True)
        sys.exit(1)

    try:
        from cli.openclaw_runtime import (
            ensure_personal_assistant_binding,
            update_binding_governance,
        )
    except ImportError as exc:
        click.echo(f"Failed to import OpenClaw runtime: {exc}", err=True)
        sys.exit(1)

    binding = ensure_personal_assistant_binding(assistant_id=agent_id)

    if enable is not None and not enable:
        update_binding_governance(binding, enabled=False, assistant_name=agent_id)
        click.echo(f"Governance disabled for agent: {agent_id}")
        return

    if not _ensure_faramesh():
        click.echo("Faramesh must be running. Start with: mutx governance start", err=True)
        sys.exit(1)

    if policy is None:
        policy_path = get_default_policy_path()
    else:
        policy_path = policy

    update_binding_governance(
        binding,
        enabled=True,
        policy=policy_path,
        assistant_name=agent_id,
    )
    click.echo(f"Governance enabled for agent: {agent_id}")
    if policy_path:
        click.echo(f"  Policy: {policy_path}")


@governance_group.group(name="webhook")
def webhook_group():
    """Manage webhook subscriptions for governance events."""
    pass


GOVERNANCE_EVENT_TYPES = [
    {"name": "governance.decision.permit", "description": "Tool call was permitted"},
    {"name": "governance.decision.deny", "description": "Tool call was denied"},
    {"name": "governance.decision.defer", "description": "Tool call requires approval"},
    {"name": "governance.pending", "description": "New pending approval request"},
    {"name": "governance.approved", "description": "Deferred action was approved"},
    {"name": "governance.denied", "description": "Deferred action was denied"},
    {"name": "governance.killed", "description": "Agent was killed"},
]


@webhook_group.command(name="list-types")
def webhook_list_types_command():
    """List available governance event types for webhook subscriptions."""
    click.echo("Governance Event Types")
    click.echo("=" * 60)
    click.echo(f"{'Event Type':<35} {'Description'}")
    click.echo("-" * 60)
    for event in GOVERNANCE_EVENT_TYPES:
        click.echo(f"{event['name']:<35} {event['description']}")
    click.echo()
    click.echo("Use 'governance webhook create' to subscribe to these events.")
    click.echo("Use 'governance webhook notify' to route FPL 'notify' directives to webhooks.")


@webhook_group.command(name="create")
@click.option(
    "--url", "-u", required=True, help="Webhook URL (must start with http:// or https://)"
)
@click.option(
    "--events",
    "-e",
    multiple=True,
    help="Governance events to subscribe to (can specify multiple)",
)
@click.option("--all-events", "all_events", is_flag=True, help="Subscribe to all governance events")
@click.option("--secret", "-s", help="Webhook secret for signature verification")
def webhook_create_command(url: str, events: tuple, all_events: bool, secret: str | None):
    """Create a webhook subscription for governance events."""
    if not url.startswith(("http://", "https://")):
        click.echo("Error: URL must start with http:// or https://", err=True)
        sys.exit(1)

    if all_events:
        selected_events = [
            "governance.decision.permit",
            "governance.decision.deny",
            "governance.decision.defer",
            "governance.pending",
            "governance.approved",
            "governance.denied",
            "governance.killed",
        ]
    elif events:
        selected_events = list(events)
    else:
        click.echo("Error: Specify --events or --all-events", err=True)
        sys.exit(1)

    try:
        client = _governance_client()
        payload = {
            "url": url,
            "events": selected_events,
            "is_active": True,
        }
        if secret:
            payload["secret"] = secret

        response = client.post("/v1/webhooks/", ok_statuses={201}, json=payload)

        webhook = response.json()
        click.echo("Webhook created successfully!")
        click.echo(f"  ID:     {webhook['id']}")
        click.echo(f"  URL:    {webhook['url']}")
        click.echo(f"  Events: {','.join(webhook['events'])}")

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)


@webhook_group.command(name="notify")
@click.argument("notify_name")
@click.option("--url", "-u", required=True, help="Webhook URL to route to this notify name")
@click.option("--remove", "-r", is_flag=True, help="Remove routing for this notify name")
def webhook_notify_command(notify_name: str, url: str, remove: bool):
    """
    Route FPL 'notify' directives to webhook URLs.

    When an FPL policy uses 'notify: "finance"', this command configures
    which webhook URL should receive those notifications.
    """
    config_dir = Path.home() / ".mutx"
    notify_config_file = config_dir / "governance_notify.json"

    config_dir.mkdir(parents=True, exist_ok=True)

    if notify_config_file.exists():
        try:
            notify_config = json.loads(notify_config_file.read_text())
        except json.JSONDecodeError:
            notify_config = {}
    else:
        notify_config = {}

    if remove:
        if notify_name in notify_config:
            del notify_config[notify_name]
            notify_config_file.write_text(json.dumps(notify_config, indent=2))
            click.echo(f"Removed webhook routing for notify: {notify_name}")
        else:
            click.echo(f"No webhook routing found for notify: {notify_name}")
        return

    if not url.startswith(("http://", "https://")):
        click.echo("Error: URL must start with http:// or https://", err=True)
        sys.exit(1)

    notify_config[notify_name] = {"url": url}

    notify_config_file.write_text(json.dumps(notify_config, indent=2))
    click.echo(f"Configured webhook routing for notify '{notify_name}': {url}")
    click.echo()
    click.echo("Update your FPL policy to use this notify name:")
    click.echo("  defer stripe/refund when amount > 500")
    click.echo(f'    notify: "{notify_name}"')


@webhook_group.command(name="list-notify")
def webhook_list_notify_command():
    """List configured FPL notify-to-webhook routings."""
    config_dir = Path.home() / ".mutx"
    notify_config_file = config_dir / "governance_notify.json"

    if not notify_config_file.exists():
        click.echo("No notify routings configured.")
        click.echo("Use 'mutx governance webhook notify <name> --url <url>' to configure.")
        return

    try:
        notify_config = json.loads(notify_config_file.read_text())
    except json.JSONDecodeError:
        click.echo("Error: Invalid notify configuration file.", err=True)
        return

    if not notify_config:
        click.echo("No notify routings configured.")
        return

    click.echo("FPL Notify Routings")
    click.echo("=" * 50)
    for name, config in notify_config.items():
        click.echo(f"  {name} -> {config['url']}")


@governance_group.group(name="supervise")
def supervise_group():
    """Faramesh supervision mode for production agent deployment."""
    pass


@supervise_group.command(name="list")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def supervise_list_command(output_json: bool) -> None:
    """List all supervised agents."""
    try:
        client = _governance_client()
        response = client.get("/v1/runtime/governance/supervised/")
        agents = response.json()

        if output_json:
            click.echo(json.dumps(agents, indent=2))
            return

        if not agents:
            click.echo("No supervised agents.")
            return

        click.echo("Supervised Agents")
        click.echo("=" * 80)
        click.echo(f"{'Agent ID':<25} {'State':<12} {'PID':<8} {'Restarts':<10} {'Command'}")
        click.echo("-" * 80)
        for agent in agents:
            pid = agent.get("pid") or "-"
            restarts = agent.get("restart_count", 0)
            state = agent.get("state", "unknown")
            agent_id = agent.get("agent_id", "-")
            cmd = " ".join(agent.get("command", []))[:40]
            click.echo(f"{agent_id:<25} {state:<12} {pid:<8} {restarts:<10} {cmd}")

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)


@supervise_group.command(name="profiles")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def supervise_profiles_command(output_json: bool) -> None:
    """List configured supervised launch profiles."""
    try:
        client = _governance_client()
        response = client.get("/v1/runtime/governance/supervised/profiles")
        profiles = response.json()
        if output_json:
            click.echo(json.dumps(profiles, indent=2))
            return

        if not profiles:
            click.echo("No supervised launch profiles configured.")
            return

        click.echo("Supervised Launch Profiles")
        click.echo("=" * 80)
        click.echo(f"{'Profile':<24} {'Env Keys':<24} {'Command'}")
        click.echo("-" * 80)
        for profile in profiles:
            env_keys = ", ".join(profile.get("env_keys", [])) or "-"
            cmd = " ".join(profile.get("command", []))
            click.echo(f"{profile['name']:<24} {env_keys[:24]:<24} {cmd}")

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)


@supervise_group.command(name="start")
@click.argument("agent_id")
@click.argument("command", nargs=-1, required=False)
@click.option("--profile", help="Configured supervised launch profile name")
@click.option("--policy", "-p", help="FPL policy file path")
@click.option("--env", "-e", multiple=True, help="Environment variables (KEY=VALUE)")
def supervise_start_command(
    agent_id: str,
    command: tuple,
    profile: str | None,
    policy: str | None,
    env: tuple,
) -> None:
    """Start an agent under Faramesh supervision."""
    try:
        env_dict = {}
        for e in env:
            if "=" in e:
                key, value = e.split("=", 1)
                env_dict[key] = value

        has_command = bool(command)
        has_profile = bool(profile)
        if has_command == has_profile:
            click.echo(
                "Error: Specify exactly one of a raw COMMAND or --profile PROFILE.",
                err=True,
            )
            sys.exit(1)

        client = _governance_client()
        payload = {
            "agent_id": agent_id,
            "command": list(command) if has_command else [],
            "env": env_dict,
        }
        if has_profile:
            payload["profile"] = profile
        if policy:
            payload["faramesh_policy"] = policy

        response = client.post("/v1/runtime/governance/supervised/start", json=payload)
        result = response.json()
        click.echo(f"Agent {agent_id} started with PID {result.get('pid')}")

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)


@supervise_group.command(name="stop")
@click.argument("agent_id")
@click.option("--timeout", "-t", type=float, default=10.0, help="Shutdown timeout in seconds")
def supervise_stop_command(agent_id: str, timeout: float) -> None:
    """Stop a supervised agent."""
    try:
        client = _governance_client()
        client.post(
            f"/v1/runtime/governance/supervised/{agent_id}/stop",
            json={"timeout": timeout},
        )

        click.echo(f"Agent {agent_id} stopped")

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)


@supervise_group.command(name="restart")
@click.argument("agent_id")
def supervise_restart_command(agent_id: str) -> None:
    """Restart a supervised agent."""
    try:
        client = _governance_client()
        response = client.post(f"/v1/runtime/governance/supervised/{agent_id}/restart")
        result = response.json()
        click.echo(f"Agent {agent_id} restarting (attempt {result.get('restart_count')})")

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)


@supervise_group.command(name="status")
@click.argument("agent_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def supervise_status_command(agent_id: str, output_json: bool) -> None:
    """Get status of a supervised agent."""
    try:
        client = _governance_client()
        response = client.get(f"/v1/runtime/governance/supervised/{agent_id}")
        agent = response.json()

        if output_json:
            click.echo(json.dumps(agent, indent=2))
            return

        click.echo(f"Agent: {agent['agent_id']}")
        click.echo(f"  State:        {agent['state']}")
        click.echo(f"  PID:          {agent['pid'] or '-'}")
        click.echo(f"  Restarts:     {agent['restart_count']}")
        click.echo(f"  Last Exit:    {agent['last_exit_code'] or '-'}")
        click.echo(f"  Policy:       {agent.get('faramesh_policy') or 'default'}")
        click.echo(f"  Started:      {agent.get('started_at') or '-'}")
        click.echo(f"  Last Start:   {agent.get('last_start_at') or '-'}")
        click.echo(f"  Last Stop:    {agent.get('last_stop_at') or '-'}")
        click.echo(f"  Command:      {' '.join(agent.get('command', []))}")

    except ImportError:
        click.echo("Error: Cannot import config client.", err=True)
        sys.exit(1)
