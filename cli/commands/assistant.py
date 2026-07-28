import json

import click

from cli.config import current_config, get_client
from cli.services import AssistantService, CLIServiceError


@click.group(name="assistant")
def assistant_group():
    """Operate the Personal Assistant control plane surfaces."""
    pass


def _service() -> AssistantService:
    return AssistantService(config=current_config(), client_factory=get_client)


def _echo_service_error(error: CLIServiceError) -> None:
    click.echo(f"Error: {error}", err=True)


@assistant_group.command(name="overview")
@click.option("--agent-id", default=None, help="Assistant agent id")
@click.option("--output", type=click.Choice(["table", "json"]), default="table")
def overview_command(agent_id: str | None, output: str):
    try:
        overview = _service().overview(agent_id=agent_id)
    except CLIServiceError as exc:
        _echo_service_error(exc)
        return

    if overview is None:
        click.echo("No Personal Assistant found.")
        return

    if output == "json":
        click.echo(
            json.dumps(
                {
                    "agent_id": overview.agent_id,
                    "name": overview.name,
                    "status": overview.status,
                    "onboarding_status": overview.onboarding_status,
                    "assistant_id": overview.assistant_id,
                    "workspace": overview.workspace,
                    "session_count": overview.session_count,
                    "gateway_status": overview.gateway.status,
                },
                indent=2,
            )
        )
        return

    click.echo(f"Assistant: {overview.name} ({overview.agent_id})")
    click.echo(f"Status: {overview.status} | Onboarding: {overview.onboarding_status}")
    click.echo(f"Workspace: {overview.workspace} | Sessions: {overview.session_count}")
    click.echo(f"Gateway: {overview.gateway.status} | {overview.gateway.doctor_summary}")


@assistant_group.group(name="skills")
def assistant_skills_group():
    """List and configure assistant skills."""
    pass


@assistant_skills_group.command(name="list")
@click.option("--agent-id", required=True, help="Assistant agent id")
def list_skills_command(agent_id: str):
    try:
        skills = _service().list_skills(agent_id)
    except CLIServiceError as exc:
        _echo_service_error(exc)
        return

    if not skills:
        click.echo("No skills found.")
        return

    for skill in skills:
        click.echo(f"{skill.id} | {skill.name} | {skill.status} | {skill.category}")


@assistant_skills_group.command(name="install")
@click.option("--agent-id", required=True, help="Assistant agent id")
@click.option("--skill-id", required=True, help="Skill id")
def install_skill_command(agent_id: str, skill_id: str):
    try:
        skills = _service().install_skill(agent_id, skill_id)
    except CLIServiceError as exc:
        _echo_service_error(exc)
        return

    skill = next((item for item in skills if item.id == skill_id), None)
    status = skill.status if skill is not None else "configured"
    click.echo(f"Configured skill {skill_id} on assistant {agent_id} (status: {status}).")
    if skill is not None and skill.reconciliation_required:
        click.echo("Runtime reconciliation is still required.")


@assistant_skills_group.command(name="remove")
@click.option("--agent-id", required=True, help="Assistant agent id")
@click.option("--skill-id", required=True, help="Skill id")
def remove_skill_command(agent_id: str, skill_id: str):
    try:
        _service().uninstall_skill(agent_id, skill_id)
        click.echo(f"Removed skill configuration {skill_id} from assistant {agent_id}.")
    except CLIServiceError as exc:
        _echo_service_error(exc)


@assistant_group.command(name="channels")
@click.option("--agent-id", required=True, help="Assistant agent id")
def channels_command(agent_id: str):
    try:
        channels = _service().list_channels(agent_id)
    except CLIServiceError as exc:
        _echo_service_error(exc)
        return

    for channel in channels:
        state = "enabled" if channel.enabled else "disabled"
        click.echo(f"{channel.id} | {channel.label} | {state} | {channel.mode}")


@assistant_group.command(name="sessions")
@click.option("--agent-id", default=None, help="Assistant agent id")
def sessions_command(agent_id: str | None):
    try:
        sessions = _service().list_sessions(agent_id=agent_id)
    except CLIServiceError as exc:
        _echo_service_error(exc)
        return

    if not sessions:
        click.echo("No sessions found.")
        return

    for session in sessions:
        click.echo(
            f"{session.get('agent')} | {session.get('channel')} | {session.get('age')} | {session.get('tokens')}"
        )


@assistant_group.command(name="health")
@click.option("--agent-id", required=True, help="Assistant agent id")
def health_command(agent_id: str):
    try:
        health = _service().health(agent_id)
    except CLIServiceError as exc:
        _echo_service_error(exc)
        return

    click.echo(f"Gateway status: {health.status}")
    click.echo(health.doctor_summary)
