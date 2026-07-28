import click
from typing import Optional

from cli.config import current_config, get_client
from cli.errors import CLIServiceError
from cli.operator_readiness import (
    api_key_last_used,
    describe_api_key_lifecycle,
    describe_api_key_readiness,
)
from cli.services.base import APIService


@click.group(name="api-keys")
def api_keys_group():
    """Manage API keys"""
    pass


def _service() -> APIService:
    return APIService(config=current_config(), client_factory=get_client)


@api_keys_group.command(name="list")
def list_api_keys():
    """List all API keys"""
    try:
        payload = _service().request_json(
            "get", "/v1/api-keys", ok_statuses={200}, expected_type=(dict, list)
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    keys = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not keys:
        click.echo("No API keys found.")
        return

    for key in keys:
        lifecycle = describe_api_key_lifecycle(key)
        readiness = describe_api_key_readiness(key) or lifecycle
        expires = key.get("expires_at") or "never"
        last_used = api_key_last_used(key) or "never"
        click.echo(
            f"{key['id']} | {key['name']} | state={lifecycle} | health={readiness} | "
            f"last used: {last_used} | expires: {expires}"
        )


@api_keys_group.command(name="create")
@click.option("--name", "-n", required=True, help="Name for the API key")
@click.option("--expires-in-days", "-e", default=None, type=int, help="Expiration in days (1-365)")
def create_api_key(name: str, expires_in_days: Optional[int]):
    """Create a new API key"""
    payload = {"name": name}
    if expires_in_days is not None:
        payload["expires_in_days"] = expires_in_days

    try:
        data = _service().request_json(
            "post",
            "/v1/api-keys",
            ok_statuses={201},
            expected_type=dict,
            invalid_message="Unable to create API key",
            json=payload,
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Created API key: {data['name']}")
    click.echo(f"Key ID:  {data['id']}")
    click.echo(f"Secret:  {data['key']}")
    click.echo("")
    click.echo("⚠  Save this secret now — it will not be shown again.")


@api_keys_group.command(name="revoke")
@click.argument("key_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def revoke_api_key(key_id: str, force: bool):
    """Revoke (delete) an API key"""
    if not force:
        if not click.confirm(f"Are you sure you want to revoke API key {key_id}?"):
            return

    try:
        _service().request_empty(
            "delete",
            f"/v1/api-keys/{key_id}",
            ok_statuses={204},
            not_found_message="API key not found",
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Revoked API key: {key_id}")


@api_keys_group.command(name="rotate")
@click.argument("key_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def rotate_api_key(key_id: str, force: bool):
    """Rotate an API key (revoke old, create new)"""
    if not force:
        if not click.confirm(
            f"Rotating will revoke the old key immediately. Continue for {key_id}?"
        ):
            return

    try:
        data = _service().request_json(
            "post",
            f"/v1/api-keys/{key_id}/rotate",
            ok_statuses={200},
            expected_type=dict,
            not_found_message="API key not found",
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Rotated API key: {data['name']}")
    click.echo(f"New Key ID:  {data['id']}")
    click.echo(f"New Secret:  {data['key']}")
    click.echo("")
    click.echo("⚠  Save this secret now — it will not be shown again.")
