"""
MUTX Security CLI Commands.

CLI commands for MUTX runtime-security capabilities.

Commands:
- mutx security evaluate <tool> <args>   - Dry-run policy evaluation
- mutx security approve <request-id>     - Approve deferred action
- mutx security deny <request-id>        - Deny deferred action
- mutx security audit                   - Run local AARM-alignment gap check
- mutx security receipts                 - View recent receipts
- mutx security metrics                 - View governance metrics

Informed by the AARM specification. The local audit is not an AARM conformance
report and does not establish Core, Extended, or organizational conformance.
https://github.com/aarm-dev/docs/tree/8eff208b98786b2c9a578b26cb7eaca440ec4020

AARM documentation reference: MIT License, Copyright (c) 2023 Mintlify.
"""

import json

import click

from cli.config import CLIConfig, get_client
from cli.errors import CLIServiceError
from cli.services.observability import SecurityService


def _get_config() -> CLIConfig:
    ctx = click.get_current_context()
    return ctx.obj["config"]


def _service() -> SecurityService:
    return SecurityService(config=_get_config(), client_factory=get_client)


@click.group(name="security")
def security_group():
    """MUTX runtime-security capabilities and local alignment checks."""
    pass


@security_group.command(name="evaluate")
@click.argument("tool_name")
@click.option("--agent-id", required=True, help="Agent ID")
@click.option("--session-id", required=True, help="Session ID")
@click.option("--args", "-a", default="{}", help="Tool arguments as JSON")
@click.option("--trigger", default="manual", help="What triggered this (manual, cron, etc.)")
@click.option("--runtime", default="mutx", help="Runtime identifier")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def evaluate_action(
    tool_name: str,
    agent_id: str,
    session_id: str,
    args: str,
    trigger: str,
    runtime: str,
    output_json: bool,
):
    """
    Evaluate an action against policy (dry-run).

    Check what the policy decision would be for a given action
    without actually executing it.
    """
    try:
        tool_args = json.loads(args) if args != "{}" else {}
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing --args: {e}", err=True)
        return

    try:
        result = _service().evaluate_action(
            tool_name=tool_name,
            tool_args=tool_args,
            agent_id=agent_id,
            session_id=session_id,
            trigger=trigger,
            runtime=runtime,
        )
    except CLIServiceError as exc:
        click.echo(f"Error evaluating action: {exc}", err=True)
        return

    if output_json:
        click.echo(json.dumps(result, indent=2))
        return

    decision = result.get("decision", "UNKNOWN")
    reason = result.get("reason", "")

    color = ""
    reset = ""
    if decision == "allow":
        color = "\033[92m"
    elif decision == "deny":
        color = "\033[91m"
    elif decision == "defer":
        color = "\033[93m"

    click.echo(f"Decision: {color}{decision}{reset}")
    click.echo(f"Reason:   {reason}")
    if result.get("rule_name"):
        click.echo(f"Rule:     {result.get('rule_name')}")
    if result.get("action_hash"):
        click.echo(f"Action:   {result.get('action_hash')[:16]}...")


@security_group.group(name="approvals")
def approvals_group():
    """Manage human approval workflows."""
    pass


@approvals_group.command(name="list")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def list_approvals(output_json: bool):
    """List pending approval requests."""
    try:
        pending = _service().list_approvals()
    except CLIServiceError as exc:
        click.echo(f"Error fetching approvals: {exc}", err=True)
        return

    if output_json:
        click.echo(json.dumps(pending, indent=2))
        return

    if not pending:
        click.echo("No pending approvals.")
        return

    click.echo(f"Pending Approvals ({len(pending)}):")
    click.echo("-" * 80)
    for req in pending:
        remaining = req.get("remaining_seconds", 0)
        minutes = remaining // 60
        seconds = remaining % 60
        click.echo(
            f"  {req.get('request_id')[:8]}... | {req.get('tool_name'):<25} | {minutes}m {seconds}s remaining"
        )
        click.echo(f"                    Reason: {req.get('reason', '-')}")


@approvals_group.command(name="approve")
@click.argument("request_id")
@click.option("--comment", "-c", default="", help="Optional comment")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def approve_action(request_id: str, comment: str, output_json: bool):
    """Approve a pending request."""
    try:
        result = _service().approve_request(request_id, comment)
    except CLIServiceError as exc:
        click.echo(f"Error approving request: {exc}", err=True)
        return

    if output_json:
        click.echo(json.dumps(result, indent=2))
        return

    click.echo(f"Approved: {result.get('status')}")
    click.echo(f"Request ID: {result.get('request_id')}")


@approvals_group.command(name="deny")
@click.argument("request_id")
@click.option("--reason", "-c", default="", help="Reason for denial")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def deny_action(request_id: str, reason: str, output_json: bool):
    """Deny a pending request."""
    try:
        result = _service().deny_request(request_id, reason)
    except CLIServiceError as exc:
        click.echo(f"Error denying request: {exc}", err=True)
        return

    if output_json:
        click.echo(json.dumps(result, indent=2))
        return

    click.echo(f"Denied: {result.get('status')}")
    click.echo(f"Request ID: {result.get('request_id')}")


@security_group.command(name="audit")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def run_audit(output_json: bool):
    """
    Run the local AARM-alignment gap check.

    Reports current capability gaps. This is not an AARM conformance assessment.
    """
    try:
        report = _service().get_compliance_report()
    except CLIServiceError as exc:
        click.echo(f"Error running alignment check: {exc}", err=True)
        return

    if output_json:
        click.echo(json.dumps(report, indent=2))
        return

    overall = report.get("overall_satisfied", False)
    summary = report.get("summary", {})

    if overall:
        click.echo("\033[92m✓ Local AARM alignment checks: COMPLETE\033[0m")
        click.echo("This is not an AARM conformance designation.")
    else:
        click.echo("\033[93m! Local AARM alignment checks: GAPS REMAIN\033[0m")

    click.echo("")
    click.echo("Summary:")
    click.echo(
        f"  MUST requirements: {summary.get('must_satisfied', 0)}/{summary.get('must_requirements', 0)}"
    )
    click.echo(
        f"  SHOULD requirements: {summary.get('should_satisfied', 0)}/{summary.get('should_requirements', 0)}"
    )

    click.echo("")
    click.echo("Requirements:")
    for result in report.get("results", []):
        req_id = result.get("requirement_id", "")
        level = result.get("level", "")
        satisfied = result.get("satisfied", False)
        description = result.get("description", "")

        status_str = "\033[92m✓\033[0m" if satisfied else "\033[91m✗\033[0m"
        click.echo(f"  {status_str} [{level}] {req_id}: {description}")

        if not satisfied and result.get("details"):
            click.echo(f"       {result.get('details')[:100]}")


@security_group.command(name="metrics")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--prometheus", is_flag=True, help="Output in Prometheus format")
def show_metrics(output_json: bool, prometheus: bool):
    """Show governance metrics."""
    try:
        if prometheus:
            metrics_text = _service().get_prometheus_metrics()
        else:
            metrics = _service().get_metrics()
    except CLIServiceError as exc:
        click.echo(f"Error fetching metrics: {exc}", err=True)
        return

    if prometheus:
        click.echo(metrics_text)
        return

    if output_json:
        click.echo(json.dumps(metrics, indent=2))
        return

    click.echo("Governance Metrics")
    click.echo("=" * 50)
    click.echo(f"  Total Evaluations:   {metrics.get('total_evaluations', 0)}")
    click.echo(f"  Permits:             {metrics.get('permits', 0)}")
    click.echo(f"  Denials:             {metrics.get('denials', 0)}")
    click.echo(f"  Defers:              {metrics.get('defers', 0)}")
    click.echo(f"  Pending Approvals:   {metrics.get('pending_approvals', 0)}")
    click.echo(f"  Intent Drifts:       {metrics.get('intent_drifts', 0)}")
    click.echo(f"  Active Sessions:     {metrics.get('active_sessions', 0)}")
    click.echo("")
    click.echo(f"  Avg Latency:         {metrics.get('avg_latency_ms', 0):.2f}ms")
    click.echo(f"  Decisions/min:       {metrics.get('decisions_per_minute', 0)}")
    click.echo(f"  Decisions/hour:      {metrics.get('decisions_per_hour', 0)}")


@security_group.group(name="receipts")
def receipts_group():
    """View action receipts (audit trail)."""
    pass


@receipts_group.command(name="list")
@click.argument("session_id")
@click.option("--limit", "-n", default=20, help="Number of receipts to show")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def list_receipts(session_id: str, limit: int, output_json: bool):
    """List receipts for a session."""
    try:
        receipts = _service().get_session_receipts(session_id, limit=limit)
    except CLIServiceError as exc:
        click.echo(f"Error fetching receipts: {exc}", err=True)
        return

    data = {"session_id": session_id, "count": len(receipts), "receipts": receipts}

    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    if not receipts:
        click.echo(f"No receipts found for session {session_id}.")
        return

    click.echo(f"Receipts for session {session_id} ({len(receipts)}):")
    click.echo("-" * 100)
    click.echo(f"{'RECEIPT ID':<38} {'ACTION':<25} {'DECISION':<10} {'TIMESTAMP'}")
    click.echo("-" * 100)

    for receipt in receipts:
        receipt_id = receipt.get("receipt_id", "")[:36]
        tool_name = receipt.get("tool_name", "")[:23]
        decision = receipt.get("policy_decision", "")[:10]
        timestamp = receipt.get("timestamp", "")[:19]

        color = ""
        reset = ""
        if decision == "allow":
            color = "\033[92m"
        elif decision == "deny":
            color = "\033[91m"
        elif decision == "defer":
            color = "\033[93m"

        click.echo(f"{receipt_id:<38} {tool_name:<25} {color}{decision:<10}{reset} {timestamp}")


@receipts_group.command(name="show")
@click.argument("receipt_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def show_receipt(receipt_id: str, output_json: bool):
    """Show detailed receipt."""
    try:
        receipt = _service().get_receipt(receipt_id)
    except CLIServiceError as exc:
        click.echo(f"Error fetching receipt: {exc}", err=True)
        return

    if output_json:
        click.echo(json.dumps(receipt, indent=2))
        return

    click.echo(f"Receipt: {receipt_id}")
    click.echo("=" * 80)
    click.echo(f"  Tool:          {receipt.get('tool_name')}")
    click.echo(f"  Decision:      {receipt.get('policy_decision')}")
    click.echo(f"  Reason:       {receipt.get('decision_reason')}")
    click.echo(f"  Outcome:      {receipt.get('outcome')}")
    click.echo(f"  Agent ID:     {receipt.get('agent_id')}")
    click.echo(f"  Session ID:   {receipt.get('session_id')}")
    click.echo(f"  Timestamp:    {receipt.get('timestamp')}")

    if receipt.get("rule_name"):
        click.echo(f"  Rule:         {receipt.get('rule_name')}")

    if receipt.get("signed_by"):
        click.echo(f"  Signed by:    {receipt.get('signed_by')}")

    if receipt.get("session_snapshot"):
        snap = receipt.get("session_snapshot")
        click.echo("")
        click.echo("  Session Snapshot:")
        click.echo(f"    Tool calls:    {snap.get('tool_call_count', 0)}")
        click.echo(f"    Denials:       {snap.get('denied_count', 0)}")


@security_group.group(name="sessions")
def sessions_group():
    """Manage session contexts."""
    pass


@sessions_group.command(name="create")
@click.option("--session-id", required=True, help="Session ID")
@click.option("--agent-id", required=True, help="Agent ID")
@click.option("--intent", default="", help="Stated user intent")
@click.option("--request", default="", help="Original user request")
def create_session(
    session_id: str,
    agent_id: str,
    intent: str,
    request: str,
):
    """Create a new session context."""
    try:
        result = _service().create_session(
            session_id=session_id,
            agent_id=agent_id,
            original_request=request,
            stated_intent=intent,
        )
    except CLIServiceError as exc:
        click.echo(f"Error creating session: {exc}", err=True)
        return

    click.echo(f"Session created: {result.get('session_id')}")


@sessions_group.command(name="show")
@click.argument("session_id")
def show_session(session_id: str):
    """Show session summary."""
    try:
        session = _service().get_session(session_id)
    except CLIServiceError as exc:
        click.echo(f"Error fetching session: {exc}", err=True)
        return

    click.echo(f"Session: {session_id}")
    click.echo("=" * 50)
    click.echo(f"  Agent ID:      {session.get('agent_id')}")
    click.echo(f"  Duration:      {session.get('duration_seconds', 0):.0f}s")
    click.echo(f"  Total Actions: {session.get('total_actions', 0)}")
    click.echo(f"  Permits:       {session.get('permits', 0)}")
    click.echo(f"  Denials:       {session.get('denials', 0)}")
    click.echo(f"  Defers:        {session.get('defers', 0)}")
    click.echo(f"  Errors:        {session.get('errors', 0)}")
    click.echo(f"  Intent:        {session.get('intent_alignment', 'unknown')}")


@sessions_group.command(name="close")
@click.argument("session_id")
def close_session(session_id: str):
    """Close a session."""
    try:
        _service().close_session(session_id)
    except CLIServiceError as exc:
        click.echo(f"Error closing session: {exc}", err=True)
        return

    click.echo(f"Session closed: {session_id}")
