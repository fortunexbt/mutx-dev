import json

import click

from cli.config import current_config, get_client
from cli.errors import CLIServiceError
from cli.services.base import APIService


@click.group(name="scheduler")
def scheduler_group():
    """Manage scheduled tasks"""
    pass


def _service() -> APIService:
    return APIService(config=current_config(), client_factory=get_client)


@scheduler_group.command(name="list")
@click.option("--limit", "-l", default=50, help="Number of schedules to fetch")
@click.option("--skip", "-s", default=0, help="Number of schedules to skip")
def list_schedules(limit: int, skip: int):
    """List all scheduled tasks"""
    if limit != 50 or skip != 0:
        raise click.ClickException("Scheduler pagination is unavailable.")
    try:
        payload = _service().request_json(
            "get", "/v1/scheduler", ok_statuses={200}, expected_type=dict
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    schedules = payload.get("tasks", [])
    if not schedules:
        click.echo("No schedules found.")
        return

    for schedule in schedules:
        active = "active" if schedule.get("enabled", False) else "paused"
        cron = schedule.get("schedule", "n/a")
        click.echo(
            f"{schedule['id']} | {schedule.get('name', 'unnamed')} | {active} | cron: {cron}"
        )


@scheduler_group.command(name="get")
@click.argument("schedule_id")
def get_schedule(schedule_id: str):
    """Get a scheduled task by ID"""
    try:
        schedule = _service().request_json(
            "get",
            f"/v1/scheduler/{schedule_id}",
            ok_statuses={200},
            expected_type=dict,
            not_found_message="Schedule not found",
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"ID:       {schedule['id']}")
    click.echo(f"Name:     {schedule.get('name', 'n/a')}")
    click.echo(f"Agent:    {schedule.get('payload', {}).get('agent_id', 'n/a')}")
    click.echo(f"Cron:     {schedule.get('schedule', 'n/a')}")
    click.echo(f"Status:   {'active' if schedule.get('enabled') else 'paused'}")
    click.echo(f"Next run: {schedule.get('next_run', 'n/a')}")
    click.echo(f"Created:  {schedule.get('created_at', 'n/a')}")


@scheduler_group.command(name="create")
@click.option("--name", "-n", required=True, help="Schedule name")
@click.option("--agent-id", required=True, help="Agent ID to trigger")
@click.option("--cron", "-c", required=True, help="Cron expression (e.g. '0 * * * *')")
@click.option("--input", "input_json", default="{}", help="JSON input payload for the run")
def create_schedule(name: str, agent_id: str, cron: str, input_json: str):
    """Create a scheduled agent heartbeat."""
    try:
        parsed_input = json.loads(input_json)
    except json.JSONDecodeError:
        raise click.ClickException("Invalid JSON in --input") from None
    if parsed_input != {}:
        raise click.ClickException(
            "Scheduled agent input is unavailable; the API currently supports heartbeats only."
        )
    try:
        schedule = _service().request_json(
            "post",
            "/v1/scheduler",
            ok_statuses={201},
            expected_type=dict,
            invalid_message="Unable to create schedule",
            json={
                "name": name,
                "schedule": cron,
                "task_type": "agent_heartbeat",
                "payload": {"agent_id": agent_id},
            },
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Created schedule: {schedule['id']}")
    click.echo(f"Name: {schedule.get('name')}")
    click.echo(f"Next run: {schedule.get('next_run', 'n/a')}")


@scheduler_group.command(name="pause")
@click.argument("schedule_id")
def pause_schedule(schedule_id: str):
    """Pause a scheduled task"""
    try:
        _service().request_json(
            "patch",
            f"/v1/scheduler/{schedule_id}",
            ok_statuses={200},
            expected_type=dict,
            not_found_message="Schedule not found",
            json={"enabled": False},
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Paused schedule: {schedule_id}")


@scheduler_group.command(name="resume")
@click.argument("schedule_id")
def resume_schedule(schedule_id: str):
    """Resume a paused scheduled task"""
    try:
        _service().request_json(
            "patch",
            f"/v1/scheduler/{schedule_id}",
            ok_statuses={200},
            expected_type=dict,
            not_found_message="Schedule not found",
            json={"enabled": True},
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Resumed schedule: {schedule_id}")


@scheduler_group.command(name="delete")
@click.argument("schedule_id")
@click.option("--force", "-f", is_flag=True, help="Delete without confirmation")
def delete_schedule(schedule_id: str, force: bool):
    """Delete a scheduled task"""
    if not force and not click.confirm(f"Are you sure you want to delete schedule {schedule_id}?"):
        return
    try:
        _service().request_empty(
            "delete",
            f"/v1/scheduler/{schedule_id}",
            ok_statuses={204},
            not_found_message="Schedule not found",
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Deleted schedule: {schedule_id}")
