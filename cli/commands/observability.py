"""
MUTX Observability CLI Commands.

CLI commands for MUTX Observability Schema - agent run observability.

Commands:
- mutx observability runs list    - List runs with filters
- mutx observability runs show    - Show run details
- mutx observability eval submit  - Submit an evaluation

Based on the agent-run open standard for agent observability.
https://github.com/builderz-labs/agent-run

MIT License - Copyright (c) 2026 Builderz Labs
https://github.com/builderz-labs/agent-run/blob/9c7c3fa68413de878fae2d605c90fb334a0201f6/LICENSE

Schema adaptation only. Do not import or execute the current upstream package;
it is quarantined pending maintainer security review.
"""

import json
from datetime import datetime

import click

from cli.config import CLIConfig, get_client
from cli.errors import CLIServiceError
from cli.services.observability import ObservabilityService


def _get_config() -> CLIConfig:
    ctx = click.get_current_context()
    return ctx.obj["config"]


def _service() -> ObservabilityService:
    return ObservabilityService(config=_get_config(), client_factory=get_client)


@click.group(name="observability")
def observability_group():
    """MUTX Observability - track and evaluate agent runs."""
    pass


@observability_group.group(name="runs")
def runs_group():
    """Manage agent runs (MutxRun)."""
    pass


@runs_group.command(name="list")
@click.option("--skip", "-s", default=0, help="Skip N records")
@click.option("--limit", "-n", default=20, help="Limit to N records")
@click.option("--agent-id", help="Filter by agent ID")
@click.option("--status", help="Filter by status (pending, running, completed, failed)")
@click.option("--runtime", help="Filter by runtime")
@click.option("--trigger", help="Filter by trigger (manual, cron, webhook, agent)")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def list_runs(
    skip: int,
    limit: int,
    agent_id: str | None,
    status: str | None,
    runtime: str | None,
    trigger: str | None,
    output_json: bool,
):
    """List agent runs with optional filters."""
    try:
        data = _service().list_runs_page(
            skip=skip,
            limit=limit,
            agent_id=agent_id,
            status=status,
            runtime=runtime,
            trigger=trigger,
        )
    except CLIServiceError as exc:
        click.echo(f"Error fetching runs: {exc}", err=True)
        return

    if output_json:
        click.echo(json.dumps(data, indent=2, default=str))
        return

    items = data.get("items", [])
    total = data.get("total", 0)

    if not items:
        click.echo("No runs found.")
        return

    click.echo(f"Runs (total: {total}, showing {len(items)}):")
    click.echo("-" * 100)
    click.echo(
        f"{'RUN ID':<38} {'AGENT':<20} {'STATUS':<12} {'TRIGGER':<10} {'DURATION':<10} {'SCORE'}"
    )
    click.echo("-" * 100)

    for run in items:
        run_id = run.get("id", "")[:36]
        agent = run.get("agent_id", "")[:18]
        status_val = run.get("status", "")
        trigger_val = run.get("trigger", "") or "-"
        duration = run.get("duration_ms")
        duration_str = f"{duration}ms" if duration else "-"
        eval_data = run.get("eval")
        score = f"{eval_data.get('score', 0):.0f}" if eval_data else "-"

        click.echo(
            f"{run_id:<38} {agent:<20} {status_val:<12} {trigger_val:<10} {duration_str:<10} {score}"
        )


@runs_group.command(name="show")
@click.argument("run_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--steps", is_flag=True, help="Show step details")
def show_run(run_id: str, output_json: bool, steps: bool):
    """Show detailed information about a run."""
    try:
        run = _service().get_run(run_id)
    except CLIServiceError as exc:
        click.echo(f"Error fetching run: {exc}", err=True)
        return

    if output_json:
        click.echo(json.dumps(run, indent=2, default=str))
        return

    click.echo(f"Run: {run_id}")
    click.echo("=" * 80)
    click.echo(f"  Agent ID:      {run.get('agent_id')}")
    click.echo(f"  Agent Name:    {run.get('agent_name') or '-'}")
    click.echo(f"  Status:        {run.get('status')}")
    click.echo(f"  Outcome:       {run.get('outcome') or '-'}")
    click.echo(f"  Trigger:       {run.get('trigger') or '-'}")
    click.echo(f"  Runtime:       {run.get('runtime') or '-'}")
    click.echo(f"  Model:         {run.get('model') or '-'}")
    click.echo(f"  Provider:       {run.get('provider') or '-'}")

    started = run.get("started_at", "")
    if started:
        try:
            dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            started = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            pass
    click.echo(f"  Started:       {started}")

    ended = run.get("ended_at")
    if ended:
        try:
            dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
            ended = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            pass
    click.echo(f"  Ended:         {ended or '-'}")

    duration = run.get("duration_ms")
    click.echo(f"  Duration:      {duration}ms" if duration else "  Duration:       -")

    click.echo("")
    click.echo("  Cost:")
    cost = run.get("cost") or {}
    click.echo(f"    Input Tokens:   {cost.get('input_tokens', 0):,}")
    click.echo(f"    Output Tokens:  {cost.get('output_tokens', 0):,}")
    total_tokens = cost.get("total_tokens")
    if total_tokens:
        click.echo(f"    Total Tokens:   {total_tokens:,}")
    cost_usd = cost.get("cost_usd")
    if cost_usd is not None:
        click.echo(f"    Cost (USD):     ${cost_usd:.6f}")

    click.echo("")
    click.echo("  Provenance:")
    prov = run.get("provenance") or {}
    click.echo(f"    Run Hash:       {prov.get('run_hash', '-')}")
    click.echo(f"    Parent Hash:     {prov.get('parent_run_hash') or '-'}")
    click.echo(f"    Runtime:        {prov.get('runtime') or '-'}")

    if steps:
        click.echo("")
        click.echo("  Steps:")
        run_steps = run.get("steps", [])
        if not run_steps:
            click.echo("    No steps recorded.")
        for i, step in enumerate(run_steps):
            step_type = step.get("type", "")
            tool_name = step.get("tool_name")
            success = step.get("success")
            duration_ms = step.get("duration_ms")

            success_str = ""
            if success is True:
                success_str = " [OK]"
            elif success is False:
                success_str = " [FAIL]"

            duration_str = f" ({duration_ms}ms)" if duration_ms else ""

            if tool_name:
                click.echo(f"    {i + 1}. {step_type}{success_str} - {tool_name}{duration_str}")
            else:
                click.echo(f"    {i + 1}. {step_type}{success_str}{duration_str}")

            error = step.get("error")
            if error:
                click.echo(f"       Error: {error[:100]}")

    eval_data = run.get("eval")
    if eval_data:
        click.echo("")
        click.echo("  Evaluation:")
        click.echo(f"    Pass:         {eval_data.get('pass')}")
        click.echo(f"    Score:        {eval_data.get('score')}/100")
        click.echo(f"    Task Type:    {eval_data.get('task_type') or '-'}")
        click.echo(f"    Eval Layer:   {eval_data.get('eval_layer') or '-'}")
        detail = eval_data.get("detail")
        if detail:
            click.echo(f"    Detail:       {detail[:100]}")

    tags = run.get("tags", [])
    if tags:
        click.echo("")
        click.echo(f"  Tags: {', '.join(tags)}")

    metadata = run.get("metadata", {})
    if metadata:
        click.echo("")
        click.echo("  Metadata:")
        for key, value in list(metadata.items())[:5]:
            click.echo(f"    {key}: {str(value)[:50]}")


@observability_group.group(name="eval")
def eval_group():
    """Manage run evaluations (MutxEval)."""
    pass


@eval_group.command(name="submit")
@click.argument("run_id")
@click.option("--pass/--fail", "passed", required=True, help="Pass or fail the run")
@click.option("--score", "-s", type=int, default=100, help="Score 0-100 (default: 100)")
@click.option("--task-type", help="Task type (e.g., bug-fix, pr-review)")
@click.option("--eval-layer", help="Eval layer (e.g., quality, convergence)")
@click.option("--detail", "-d", help="Human-readable evaluation notes")
@click.option("--benchmark-id", help="Benchmark pack ID")
@click.option("--expected", help="Expected outcome")
@click.option("--actual", help="Actual outcome")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def submit_eval(
    run_id: str,
    passed: bool,
    score: int,
    task_type: str | None,
    eval_layer: str | None,
    detail: str | None,
    benchmark_id: str | None,
    expected: str | None,
    actual: str | None,
    output_json: bool,
):
    """Submit an evaluation for a run."""
    if not (0 <= score <= 100):
        click.echo("Error: score must be between 0 and 100", err=True)
        return

    eval_data = {
        "pass": passed,
        "score": score,
    }
    if task_type:
        eval_data["task_type"] = task_type
    if eval_layer:
        eval_data["eval_layer"] = eval_layer
    if detail:
        eval_data["detail"] = detail
    if benchmark_id:
        eval_data["benchmark_id"] = benchmark_id
    if expected:
        eval_data["expected_outcome"] = expected
    if actual:
        eval_data["actual_outcome"] = actual

    try:
        result = _service().submit_eval(run_id, eval_data)
    except CLIServiceError as exc:
        click.echo(f"Error submitting eval: {exc}", err=True)
        return

    if output_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    click.echo(f"Eval submitted for run {run_id}:")
    click.echo(f"  Pass:    {result.get('pass')}")
    click.echo(f"  Score:   {result.get('score')}/100")
    if result.get("task_type"):
        click.echo(f"  Task:    {result.get('task_type')}")


@eval_group.command(name="show")
@click.argument("run_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def show_eval(run_id: str, output_json: bool):
    """Show the evaluation for a run."""
    try:
        eval_data = _service().get_eval(run_id)
    except CLIServiceError as exc:
        click.echo(f"Error fetching eval: {exc}", err=True)
        return

    if eval_data is None:
        click.echo(f"No evaluation found for run {run_id}.")
        return

    if output_json:
        click.echo(json.dumps(eval_data, indent=2, default=str))
        return

    click.echo(f"Evaluation for run {run_id}:")
    click.echo("=" * 50)
    click.echo(f"  Pass:         {eval_data.get('pass')}")
    click.echo(f"  Score:        {eval_data.get('score')}/100")
    click.echo(f"  Task Type:    {eval_data.get('task_type') or '-'}")
    click.echo(f"  Eval Layer:   {eval_data.get('eval_layer') or '-'}")

    metrics = eval_data.get("metrics") or {}
    if metrics:
        click.echo("")
        click.echo("  Metrics:")
        for key, value in metrics.items():
            if value is not None:
                click.echo(f"    {key}: {value}")

    if eval_data.get("detail"):
        click.echo("")
        click.echo(f"  Detail:       {eval_data.get('detail')}")


@observability_group.group(name="provenance")
def provenance_group():
    """View run provenance records."""
    pass


@provenance_group.command(name="show")
@click.argument("run_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def show_provenance(run_id: str, output_json: bool):
    """Show the provenance record for a run."""
    try:
        prov = _service().get_provenance(run_id)
    except CLIServiceError as exc:
        click.echo(f"Error fetching provenance: {exc}", err=True)
        return

    if prov is None:
        click.echo(f"No provenance record found for run {run_id}.")
        return

    if output_json:
        click.echo(json.dumps(prov, indent=2, default=str))
        return

    click.echo(f"Provenance for run {run_id}:")
    click.echo("=" * 50)
    click.echo(f"  Run Hash:       {prov.get('run_hash')}")
    click.echo(f"  Parent Hash:     {prov.get('parent_run_hash') or '-'}")
    click.echo(f"  Runtime:        {prov.get('runtime') or '-'}")
    click.echo(f"  Model Version:  {prov.get('model_version') or '-'}")
    click.echo(f"  Config Hash:    {prov.get('config_hash') or '-'}")

    lineage = prov.get("lineage") or []
    if lineage:
        click.echo(f"  Lineage ({len(lineage)} ancestors):")
        for h in lineage[:5]:
            click.echo(f"    {h}")
        if len(lineage) > 5:
            click.echo(f"    ... and {len(lineage) - 5} more")

    signed = prov.get("signed_by")
    if signed:
        click.echo("")
        click.echo(f"  Signed by:      {signed}")
