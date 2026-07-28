import click

from cli.config import current_config, get_client, resolve_hosted_api_url
from cli.services import AuthService, CLIServiceError


@click.group(name="auth")
def auth_group():
    """Manage authentication."""
    pass


def _service() -> AuthService:
    return AuthService(config=current_config(), client_factory=get_client)


@auth_group.command(name="login")
@click.option("--email", "-e", prompt=True, help="Email address")
@click.option("--password", "-p", prompt=True, hide_input=True, help="Password")
@click.option("--api-url", "-u", default=None, help="API URL")
def login_command(email: str, password: str, api_url: str | None):
    try:
        config = current_config()
        _service().login(
            email=email,
            password=password,
            api_url=resolve_hosted_api_url(config, api_url),
        )
        click.echo("Logged in successfully.")
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc


@auth_group.command(name="register")
@click.option("--name", "-n", required=True, help="Display name")
@click.option("--email", "-e", required=True, help="Email address")
@click.option("--password", "-p", prompt=True, hide_input=True, help="Password")
def register_command(name: str, email: str, password: str):
    try:
        status = _service().register(name=name, email=email, password=password)
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    if status.authenticated:
        click.echo("Registered and logged in successfully.")
    else:
        click.echo("Registered. Verify your email, then run 'mutx auth login'.")


@auth_group.command(name="logout")
def logout_command():
    try:
        if not _service().logout():
            click.echo("No local access token is stored.")
            return
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("Logged out successfully.")


@auth_group.command(name="whoami")
def whoami_command():
    try:
        user = _service().whoami()
        click.echo(f"{user.email} | {user.name} | {user.plan}")
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc


@auth_group.command(name="status")
def status_command():
    status = _service().status()
    click.echo(f"API URL: {status.api_url}")
    click.echo(f"Source: {status.api_url_source}")
    click.echo(f"Authenticated: {'yes' if status.authenticated else 'no'}")
