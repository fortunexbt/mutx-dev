import click

from cli.config import current_config, get_client
from cli.errors import CLIServiceError
from cli.services.base import APIService


@click.group(name="clawhub")
def clawhub_group():
    """Manage ClawHub skills"""
    pass


def _service() -> APIService:
    return APIService(config=current_config(), client_factory=get_client)


@clawhub_group.command(name="list")
def list_skills():
    """List skills from the MUTX catalog."""
    try:
        skills = _service().request_json(
            "get",
            "/v1/clawhub/skills",
            ok_statuses={200},
            expected_type=list,
            require_auth=False,
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    if not skills:
        click.echo("No skills found.")
        return

    click.echo(f"{'ID':<24} | {'NAME':<28} | {'SRC':<18} | {'AVAIL':<5} | {'AUTHOR':<20}")
    click.echo("-" * 108)
    for skill in skills:
        click.echo(
            f"{skill['id']:<24} | {skill['name'][:28]:<28} | {skill.get('source', 'catalog')[:18]:<18} | "
            f"{('yes' if skill.get('available', True) else 'no'):<5} | {skill['author'][:20]:<20}"
        )


@clawhub_group.command(name="bundles")
def list_bundles():
    """List curated skill bundles."""
    try:
        bundles = _service().request_json(
            "get",
            "/v1/clawhub/bundles",
            ok_statuses={200},
            expected_type=list,
            require_auth=False,
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    if not bundles:
        click.echo("No bundles found.")
        return

    click.echo(f"{'ID':<32} | {'NAME':<28} | {'SKILLS':<13} | {'TEMPLATE':<28}")
    click.echo("-" * 113)
    for bundle in bundles:
        skill_ratio = f"{bundle.get('available_skill_count', 0)}/{bundle.get('skill_count', 0)}"
        click.echo(
            f"{bundle['id']:<32} | {bundle['name'][:28]:<28} | "
            f"{skill_ratio:<13} | {str(bundle.get('recommended_template_id') or '')[:28]:<28}"
        )


@clawhub_group.command(name="install")
@click.option("--agent-id", "-a", required=True, help="Agent ID to install the skill to")
@click.option("--skill-id", "-s", required=True, help="Skill ID to install")
def install_skill(agent_id: str, skill_id: str):
    """Configure a skill request for an agent."""
    try:
        payload = _service().request_json(
            "post",
            "/v1/clawhub/install",
            ok_statuses={200},
            expected_type=dict,
            not_found_message=f"Unknown skill or agent not found for '{skill_id}'",
            json={"agent_id": agent_id, "skill_id": skill_id},
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f"Configured '{skill_id}' for agent {agent_id} "
        f"(status: {payload.get('status', 'configured')})."
    )
    if payload.get("reconciliation_required"):
        click.echo("Runtime reconciliation is still required.")


@clawhub_group.command(name="install-bundle")
@click.option("--agent-id", "-a", required=True, help="Agent ID to install the bundle to")
@click.option("--bundle-id", "-b", required=True, help="Bundle ID to install")
def install_bundle(agent_id: str, bundle_id: str):
    """Configure a curated bundle for an agent."""
    try:
        payload = _service().request_json(
            "post",
            "/v1/clawhub/install-bundle",
            ok_statuses={200},
            expected_type=dict,
            not_found_message=f"Unknown bundle or agent not found for '{bundle_id}'",
            json={"agent_id": agent_id, "bundle_id": bundle_id},
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    configured = payload.get("configured_skill_ids", [])
    runtime_ready = payload.get("runtime_ready_skill_ids", [])
    click.echo(
        f"Configured bundle '{bundle_id}' for agent {agent_id}: "
        f"{len(configured)} configured, {len(runtime_ready)} runtime-ready, "
        f"{len(payload.get('unavailable_skill_ids', []))} unavailable"
    )


@clawhub_group.command(name="uninstall")
@click.option("--agent-id", "-a", required=True, help="Agent ID to uninstall the skill from")
@click.option("--skill-id", "-s", required=True, help="Skill ID to uninstall")
def uninstall_skill(agent_id: str, skill_id: str):
    """Remove a skill configuration from an agent."""
    try:
        _service().request_json(
            "post",
            "/v1/clawhub/uninstall",
            ok_statuses={200},
            expected_type=dict,
            not_found_message=f"Agent {agent_id} not found",
            json={"agent_id": agent_id, "skill_id": skill_id},
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Removed configuration for '{skill_id}' from agent {agent_id}.")
