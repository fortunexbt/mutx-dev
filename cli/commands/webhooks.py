import click
from typing import Any, Optional

from cli.config import current_config, get_client
from cli.errors import CLIServiceError
from cli.operator_readiness import describe_webhook_delivery_health, describe_webhook_lifecycle
from cli.services.base import APIService


@click.group(name="webhooks")
def webhooks_group():
    """Manage webhooks and delivery history"""
    pass


def _service() -> APIService:
    return APIService(config=current_config(), client_factory=get_client)


@webhooks_group.command(name="list")
@click.option("--limit", "-l", default=50, help="Number of webhooks to fetch")
@click.option("--skip", "-s", default=0, help="Number of webhooks to skip")
def list_webhooks(limit: int, skip: int):
    """List all configured webhooks"""
    service = _service()
    try:
        payload = service.request_json(
            "get",
            "/v1/webhooks/",
            ok_statuses={200},
            expected_type=(dict, list),
            params={"limit": limit, "skip": skip},
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    webhooks = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not webhooks:
        click.echo("No webhooks found.")
        return

    for webhook in webhooks:
        lifecycle = describe_webhook_lifecycle(webhook)
        delivery = lifecycle
        last_delivery = "never"

        if lifecycle == "active":
            try:
                delivery_payload = service.request_json(
                    "get",
                    f"/v1/webhooks/{webhook['id']}/deliveries",
                    ok_statuses={200},
                    expected_type=(dict, list),
                    params={"limit": 5, "skip": 0},
                )
            except CLIServiceError:
                delivery = "delivery-data-unavailable"
            else:
                deliveries = (
                    delivery_payload.get("items", delivery_payload)
                    if isinstance(delivery_payload, dict)
                    else delivery_payload
                )
                delivery = describe_webhook_delivery_health(webhook, deliveries)
                if deliveries:
                    latest_delivery = deliveries[0]
                    last_delivery = (
                        latest_delivery.get("created_at")
                        or latest_delivery.get("delivered_at")
                        or "unknown"
                    )
        events = ",".join(webhook.get("events", [])) or "*"
        click.echo(
            f"{webhook['id']} | {webhook['url']} | state={lifecycle} | delivery={delivery} | "
            f"last delivery: {last_delivery} | events: {events}"
        )


@webhooks_group.command(name="deliveries")
@click.argument("webhook_id")
@click.option("--skip", "-s", default=0, help="Number of deliveries to skip")
@click.option("--limit", "-l", default=50, help="Number of deliveries to fetch")
@click.option("--event", help="Filter by event")
@click.option(
    "--success",
    type=click.Choice(["true", "false"], case_sensitive=False),
    help="Filter by success status (true/false)",
)
def webhook_deliveries(
    webhook_id: str, skip: int, limit: int, event: Optional[str], success: Optional[str]
):
    """Fetch delivery history for a webhook"""
    params: dict[str, Any] = {"skip": skip, "limit": limit}
    if event:
        params["event"] = event
    if success is not None:
        params["success"] = success.lower() == "true"

    try:
        payload = _service().request_json(
            "get",
            f"/v1/webhooks/{webhook_id}/deliveries",
            ok_statuses={200},
            expected_type=(dict, list),
            not_found_message="Webhook not found",
            params=params,
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    deliveries = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not deliveries:
        click.echo("No webhook deliveries found.")
        return

    for item in deliveries:
        click.echo(
            f"{item['id']} | event={item['event']} | success={item['success']} | attempts={item['attempts']} | status={item.get('status_code') or 'n/a'}"
        )


@webhooks_group.command(name="get")
@click.argument("webhook_id")
def get_webhook(webhook_id: str):
    """Fetch one webhook by id"""
    try:
        webhook = _service().request_json(
            "get",
            f"/v1/webhooks/{webhook_id}",
            ok_statuses={200},
            expected_type=dict,
            not_found_message="Webhook not found",
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    lifecycle = describe_webhook_lifecycle(webhook)
    click.echo(f"{webhook['id']} | {webhook['url']} | state={lifecycle}")
    click.echo(f"Events: {','.join(webhook.get('events', [])) or '*'}")
    click.echo(f"Created: {webhook.get('created_at')}")


@webhooks_group.command(name="test")
@click.argument("webhook_id")
def test_webhook(webhook_id: str):
    """Trigger a test delivery for a webhook"""
    try:
        payload = _service().request_json(
            "post",
            f"/v1/webhooks/{webhook_id}/test",
            ok_statuses={200},
            expected_type=dict,
            not_found_message="Webhook not found",
        )
    except CLIServiceError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Triggered webhook test: {webhook_id}")
    if isinstance(payload, dict) and payload.get("message"):
        click.echo(str(payload["message"]))
