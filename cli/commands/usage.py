from typing import Any

import click

from cli.config import current_config, get_client
from cli.errors import CLIServiceError
from cli.services.base import APIService


@click.group(name="usage")
def usage_group():
    """View usage statistics"""
    pass


def _service() -> APIService:
    return APIService(config=current_config(), client_factory=get_client)


def _period_params(period: str) -> dict[str, Any]:
    window = {
        "daily": "24h",
        "weekly": "7d",
        "monthly": "30d",
    }.get(period)
    if window is None:
        raise click.ClickException("Yearly usage aggregation is unavailable.")
    return {"period_start": window}


def _usage_breakdown(period: str) -> dict[str, Any]:
    try:
        return _service().request_json(
            "get",
            "/v1/budgets/usage",
            ok_statuses={200},
            expected_type=dict,
            params=_period_params(period),
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc


@usage_group.command(name="summary")
@click.option(
    "--period",
    "-p",
    default="monthly",
    type=click.Choice(["daily", "weekly", "monthly", "yearly"]),
    help="Time period",
)
def usage_summary(period: str):
    """Get overall usage summary"""
    data = _usage_breakdown(period)
    click.echo(f"Period: {period}")
    click.echo(f"Credits used: {data.get('total_credits_used', 0)}")
    click.echo(f"Credits remaining: {data.get('credits_remaining', 0)}")
    click.echo(f"Credits total: {data.get('credits_total', 0)}")
    click.echo(f"Window: {data.get('period_start', 'n/a')} to {data.get('period_end', 'n/a')}")


@usage_group.command(name="by-agent")
@click.option("--limit", "-l", default=50, help="Number of records to fetch")
@click.option(
    "--period",
    "-p",
    default="monthly",
    type=click.Choice(["daily", "weekly", "monthly", "yearly"]),
    help="Time period",
)
def usage_by_agent(limit: int, period: str):
    """Get usage breakdown by agent"""
    data = _usage_breakdown(period).get("usage_by_agent", [])[:limit]
    if not data:
        click.echo("No usage data found.")
        return

    header = f"{'AGENT ID':<40} {'AGENT':<24} {'EVENTS':<12} {'CREDITS':<12}"
    click.echo(header)
    click.echo("-" * len(header))

    for row in data:
        click.echo(
            f"{row.get('agent_id', 'n/a')[:38]:<40} "
            f"{row.get('agent_name', 'n/a')[:22]:<24} "
            f"{row.get('event_count', 0):<12,} "
            f"{row.get('credits_used', 0):.2f}"
        )


@usage_group.command(name="by-day")
@click.option(
    "--period",
    "-p",
    default="monthly",
    type=click.Choice(["daily", "weekly", "monthly", "yearly"]),
    help="Time period",
)
def usage_by_day(period: str):
    """Report that daily buckets are not mounted."""
    raise click.ClickException(
        "Daily usage buckets are unavailable; use 'mutx usage summary' for the mounted breakdown."
    )


@usage_group.command(name="current")
def usage_current():
    """Get current billing period usage"""
    try:
        data = _service().request_json("get", "/v1/budgets", ok_statuses={200}, expected_type=dict)
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Plan: {data.get('plan', 'unknown')}")
    click.echo(f"Credits used: {data.get('credits_used', 0)}")
    click.echo(f"Credits remaining: {data.get('credits_remaining', 0)}")
    click.echo(f"Credits total: {data.get('credits_total', 0)}")
    click.echo(f"Resets: {data.get('reset_date', 'n/a')}")
