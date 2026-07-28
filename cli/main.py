import click

from cli.config import CLIConfig, get_client, resolve_hosted_api_url
from cli.commands.agent import agent_group
from cli.commands.assistant import assistant_group
from cli.commands.auth import auth_group
from cli.commands.agents import agents_group
from cli.commands.api_keys import api_keys_group
from cli.commands.clawhub import clawhub_group
from cli.commands.config import config_group
from cli.commands.deployment import deployment_group
from cli.commands.deploy import deploy_group
from cli.commands.doctor import doctor_command
from cli.commands.documents import documents_group
from cli.commands.reasoning import reasoning_group
from cli.commands.governance import governance_group
from cli.commands.observability import observability_group
from cli.commands.runtime import runtime_group
from cli.commands.security import security_group
from cli.commands.onboard import onboard_command
from cli.commands.setup import setup_group
from cli.commands.tui import tui_command
from cli.commands.update import update_command
from cli.commands.webhooks import webhooks_group
from cli.commands.scheduler import scheduler_group
from cli.commands.budgets import budgets_group
from cli.commands.usage import usage_group
from cli.services import AuthService, CLIServiceError


@click.group()
@click.option("--api-url", default=None, help="API URL (overrides config)")
@click.pass_context
def cli(ctx, api_url):
    """mutx.dev CLI - Deploy and manage agents"""
    ctx.ensure_object(dict)
    config = CLIConfig()
    if api_url:
        config.set_runtime_api_url(api_url)
    ctx.obj["config"] = config


def _auth_service() -> AuthService:
    return AuthService(config=click.get_current_context().obj["config"], client_factory=get_client)


@cli.command(name="login")
@click.option("--email", "-e", prompt=True, help="Email address")
@click.option("--password", "-p", prompt=True, hide_input=True, help="Password")
@click.option("--api-url", "-u", default=None, help="API URL")
@click.pass_context
def login(ctx, email: str, password: str, api_url: str | None):
    """Login to mutx.dev"""
    try:
        config = ctx.obj["config"]
        _auth_service().login(
            email=email,
            password=password,
            api_url=resolve_hosted_api_url(config, api_url),
        )
        click.echo("Logged in successfully!")
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command(name="logout")
def logout():
    """Logout from mutx.dev"""
    try:
        if not _auth_service().logout():
            click.echo("No local access token is stored.")
            click.echo("Run 'mutx status' to inspect current CLI state.")
            return
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("Logged out successfully.")
    click.echo("Local access and refresh tokens cleared.")
    click.echo("Run 'mutx status' to confirm local auth state.")


@cli.command(name="whoami")
def whoami():
    """Show current user info"""
    try:
        user = _auth_service().whoami()
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Email: {user.email}")
    click.echo(f"Name: {user.name}")
    click.echo(f"Plan: {user.plan}")


@cli.command(name="status")
def status():
    """Show CLI status"""
    cli_status = _auth_service().status()
    click.echo(f"API URL: {cli_status.api_url}")
    if cli_status.authenticated:
        click.echo("Status: Logged in")
    else:
        click.echo("Status: Not logged in")


cli.add_command(agents_group)
cli.add_command(agent_group)
cli.add_command(assistant_group)
cli.add_command(auth_group)
cli.add_command(api_keys_group)
cli.add_command(clawhub_group)
cli.add_command(deploy_group)
cli.add_command(deployment_group)
cli.add_command(doctor_command)
cli.add_command(documents_group)
cli.add_command(reasoning_group)
cli.add_command(config_group)
cli.add_command(governance_group)
cli.add_command(observability_group)
cli.add_command(runtime_group)
cli.add_command(security_group)
cli.add_command(onboard_command)
cli.add_command(setup_group)
cli.add_command(update_command)
cli.add_command(webhooks_group)
cli.add_command(tui_command)
cli.add_command(scheduler_group)
cli.add_command(budgets_group)
cli.add_command(usage_group)


if __name__ == "__main__":
    cli()
