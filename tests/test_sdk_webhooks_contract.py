from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from mutx.webhooks import Webhook, WebhookDelivery, Webhooks


def _webhook_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "url": "https://example.com/hook",
        "events": ["*"],
        "secret": None,
        "is_active": True,
        "created_at": "2026-03-12T08:16:00",
    }
    payload.update(overrides)
    return payload


def test_webhook_parses_is_active_and_keeps_active_alias() -> None:
    webhook = Webhook(_webhook_payload(is_active=False))

    assert webhook.is_active is False
    assert webhook.active is False


def test_webhooks_create_uses_trailing_slash_route_and_is_active_contract_field() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_webhook_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    webhooks = Webhooks(client)

    webhooks.create(
        url="https://example.com/hook",
        events=["agent.status"],
        is_active=False,
    )

    assert captured["path"] == "/v1/webhooks/"
    assert captured["json"]["is_active"] is False
    assert "active" not in captured["json"]


def test_webhooks_update_maps_legacy_active_to_is_active_field() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_webhook_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    webhooks = Webhooks(client)

    webhooks.update(webhook_id=uuid.uuid4(), active=False)

    assert captured["json"] == {"is_active": False}


def _delivery_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "webhook_id": str(uuid.uuid4()),
        "event": "agent.status",
        "payload": '{"status":"running"}',
        "status_code": 202,
        "success": True,
        "error_message": None,
        "attempts": 1,
        "created_at": "2026-03-12T08:18:00",
        "delivered_at": "2026-03-12T08:18:01",
    }
    payload.update(overrides)
    return payload


def test_webhook_delivery_parses_optional_contract_fields() -> None:
    delivery = WebhookDelivery(
        _delivery_payload(status_code=None, error_message="boom", delivered_at=None)
    )

    assert delivery.status_code is None
    assert delivery.error_message == "boom"
    assert delivery.delivered_at is None


def test_webhooks_get_deliveries_uses_live_backend_route_and_filters() -> None:
    captured: dict[str, Any] = {}
    webhook_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[_delivery_payload(webhook_id=str(webhook_id))])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    webhooks = Webhooks(client)

    deliveries = webhooks.get_deliveries(
        webhook_id, limit=10, skip=5, event="agent.status", success=False
    )

    assert captured["path"] == f"/v1/webhooks/{webhook_id}/deliveries"
    assert captured["params"] == {
        "skip": "5",
        "limit": "10",
        "event": "agent.status",
        "success": "false",
    }
    assert len(deliveries) == 1
    assert deliveries[0].webhook_id == webhook_id
