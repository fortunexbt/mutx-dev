from typing import Optional

import click

from cli.config import current_config, get_client
from cli.errors import CLIServiceError
from cli.services.base import APIService


@click.group(name="budgets")
def budgets_group():
    """Manage budgets"""
    pass


def _service() -> APIService:
    return APIService(config=current_config(), client_factory=get_client)


def _unsupported() -> None:
    raise click.ClickException(
        "Budget CRUD is unavailable; the API exposes the current account budget only."
    )


@budgets_group.command(name="list")
@click.option("--limit", "-l", default=50, help="Number of budgets to fetch")
@click.option("--skip", "-s", default=0, help="Number of budgets to skip")
def list_budgets(limit: int, skip: int):
    """Show the current account budget."""
    if limit != 50 or skip != 0:
        raise click.ClickException("Budget pagination is unavailable for the current budget.")
    try:
        budget = _service().request_json(
            "get", "/v1/budgets", ok_statuses={200}, expected_type=dict
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Plan: {budget.get('plan', 'unknown')}")
    click.echo(
        f"Credits: {budget.get('credits_used', 0)}/{budget.get('credits_total', 0)} "
        f"({budget.get('usage_percentage', 0)}% used)"
    )
    click.echo(f"Remaining: {budget.get('credits_remaining', 0)}")
    click.echo(f"Resets: {budget.get('reset_date', 'n/a')}")


@budgets_group.command(name="get")
@click.argument("budget_id")
def get_budget(budget_id: str):
    """Report that budget-by-ID is not mounted."""
    _unsupported()


@budgets_group.command(name="create")
@click.option("--name", "-n", required=True, help="Budget name")
@click.option("--limit", "-l", required=True, type=float, help="Spending limit")
@click.option("--currency", "-c", default="USD", help="Currency code (default: USD)")
@click.option(
    "--period",
    "-p",
    default="monthly",
    type=click.Choice(["daily", "weekly", "monthly", "yearly"]),
    help="Budget period",
)
def create_budget(name: str, limit: float, currency: str, period: str):
    """Report that budget creation is not mounted."""
    _unsupported()


@budgets_group.command(name="update")
@click.argument("budget_id")
@click.option("--name", "-n", default=None, help="New budget name")
@click.option("--limit", "-l", type=float, default=None, help="New spending limit")
def update_budget(budget_id: str, name: Optional[str], limit: Optional[float]):
    """Report that budget updates are not mounted."""
    _unsupported()


@budgets_group.command(name="delete")
@click.argument("budget_id")
@click.option("--force", "-f", is_flag=True, help="Delete without confirmation")
def delete_budget(budget_id: str, force: bool):
    """Report that budget deletion is not mounted."""
    _unsupported()
