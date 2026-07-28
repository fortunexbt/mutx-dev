import pytest
import pytest_asyncio
from httpx import AsyncClient
import uuid
from datetime import datetime, timedelta
from sqlalchemy import select

from src.api.auth.jwt import create_access_token
from src.api.models.models import Webhook, WebhookDeliveryLog


@pytest.fixture(autouse=True)
def _mock_public_webhook_dns(monkeypatch):
    import src.api.services.webhook_service as webhook_service

    async def fake_resolve_webhook_destination_ips(hostname: str, port: int) -> set[str]:
        return {"93.184.216.34"}

    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        fake_resolve_webhook_destination_ips,
    )


@pytest_asyncio.fixture(autouse=True)
async def _persisted_webhook_developers(db_session, test_user, other_user):
    """Keep legacy lifecycle tests on their intended write-capable principals."""

    test_user.roles = ["DEVELOPER"]
    other_user.roles = ["DEVELOPER"]
    await db_session.commit()


@pytest.mark.asyncio
async def test_webhook_lifecycle(client: AsyncClient, test_user):
    # 1. Create Webhook
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["agent.*"], "secret": "test-secret"},
    )
    assert response.status_code == 201
    webhook = response.json()
    webhook_id = webhook["id"]
    assert webhook["url"] == "https://example.com/webhook"
    assert "agent.*" in webhook["events"]
    assert webhook["secret"] is None
    assert webhook["has_secret"] is True

    # 2. List Webhooks
    response = await client.get("/v1/webhooks/")
    assert response.status_code == 200
    webhooks = response.json()
    assert any(w["id"] == webhook_id for w in webhooks["items"])

    # 3. Get Webhook
    response = await client.get(f"/v1/webhooks/{webhook_id}")
    assert response.status_code == 200
    assert response.json()["id"] == webhook_id

    # 4. Update Webhook
    response = await client.patch(
        f"/v1/webhooks/{webhook_id}",
        json={"url": "https://example.com/updated", "is_active": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com/updated"
    assert data["is_active"] is False

    # 5. Delete Webhook
    response = await client.delete(f"/v1/webhooks/{webhook_id}")
    assert response.status_code == 204

    # 6. Verify Deletion
    response = await client.get(f"/v1/webhooks/{webhook_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_name",
    ["agent.heartbeat", "agent.status", "agent.status_update"],
)
async def test_webhook_create_accepts_runtime_status_event_names(
    client: AsyncClient, event_name: str
):
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": [event_name]},
    )

    assert response.status_code == 201
    assert response.json()["events"] == [event_name]


@pytest.mark.asyncio
async def test_webhook_secret_is_encrypted_at_rest(client: AsyncClient, db_session):
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"], "secret": "test-secret"},
    )
    assert response.status_code == 201

    webhook_id = uuid.UUID(response.json()["id"])
    result = await db_session.execute(select(Webhook).where(Webhook.id == webhook_id))
    webhook = result.scalar_one()

    assert webhook.secret != "test-secret"
    assert response.json()["secret"] is None
    assert response.json()["has_secret"] is True


@pytest.mark.asyncio
async def test_webhook_list_honors_skip_and_limit(client: AsyncClient):
    for idx in range(3):
        response = await client.post(
            "/v1/webhooks/",
            json={"url": f"https://example.com/webhook-{idx}", "events": ["agent.*"]},
        )
        assert response.status_code == 201

    full_response = await client.get("/v1/webhooks/")
    assert full_response.status_code == 200
    assert len(full_response.json()["items"]) == 3

    limited_response = await client.get("/v1/webhooks/?limit=1")
    assert limited_response.status_code == 200
    assert len(limited_response.json()["items"]) == 1

    skipped_response = await client.get("/v1/webhooks/?skip=1&limit=10")
    assert skipped_response.status_code == 200
    assert len(skipped_response.json()["items"]) == 2


@pytest.mark.asyncio
async def test_webhook_unauthorized(client_no_auth: AsyncClient):
    response = await client_no_auth.get("/v1/webhooks/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_verify_docs_static_route_is_not_shadowed(client: AsyncClient):
    response = await client.get("/v1/webhooks/verify-docs")

    assert response.status_code == 200
    assert response.json()["algorithm"] == "HMAC-SHA256"
    assert response.json()["header"] == "X-Webhook-Signature"


@pytest.mark.asyncio
async def test_viewer_can_read_owned_webhooks_and_delivery_history(
    client: AsyncClient,
    db_session,
    test_user,
):
    webhook = Webhook(
        user_id=test_user.id,
        url="https://example.com/webhook",
        events=["*"],
        secret=None,
        is_active=True,
    )
    db_session.add(webhook)
    await db_session.commit()
    await db_session.refresh(webhook)
    db_session.add(
        WebhookDeliveryLog(
            webhook_id=webhook.id,
            event="agent.status",
            payload='{"status":"running"}',
            success=True,
            attempts=1,
        )
    )
    test_user.roles = ["VIEWER"]
    await db_session.commit()

    responses = [
        await client.get("/v1/webhooks/"),
        await client.get(f"/v1/webhooks/{webhook.id}"),
        await client.get(f"/v1/webhooks/{webhook.id}/deliveries"),
        await client.get("/v1/webhooks/verify-docs"),
    ]

    assert [response.status_code for response in responses] == [200, 200, 200, 200]


@pytest.mark.asyncio
async def test_viewer_mutations_are_denied_before_dns_db_or_http_side_effects(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch,
):
    webhook = Webhook(
        user_id=test_user.id,
        url="https://example.com/webhook",
        events=["*"],
        secret=None,
        is_active=True,
    )
    db_session.add(webhook)
    await db_session.commit()
    await db_session.refresh(webhook)
    delivery = WebhookDeliveryLog(
        webhook_id=webhook.id,
        event="agent.status",
        payload='{"status":"running"}',
        success=False,
        attempts=1,
    )
    db_session.add(delivery)
    test_user.roles = ["VIEWER"]
    await db_session.commit()
    await db_session.refresh(delivery)

    async def forbidden_side_effect(*args, **kwargs):
        raise AssertionError("webhook side effect ran before persisted-role denial")

    import src.api.services.webhook_service as webhook_service

    monkeypatch.setattr(db_session, "execute", forbidden_side_effect)
    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        forbidden_side_effect,
    )
    monkeypatch.setattr(
        webhook_service,
        "_send_pinned_webhook_request",
        forbidden_side_effect,
    )

    responses = [
        await client.post(
            "/v1/webhooks/",
            json={"url": "https://example.com/new", "events": ["*"]},
        ),
        await client.patch(
            f"/v1/webhooks/{webhook.id}",
            json={"url": "https://example.com/changed"},
        ),
        await client.delete(f"/v1/webhooks/{webhook.id}"),
        await client.post(f"/v1/webhooks/{webhook.id}/test"),
        await client.post(
            "/v1/webhooks/retry",
            json={"delivery_id": str(delivery.id)},
        ),
    ]

    assert {response.status_code for response in responses} == {403}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["DEVELOPER", "ADMIN"])
async def test_developer_and_admin_can_manage_owned_webhooks(
    client: AsyncClient,
    db_session,
    test_user,
    role: str,
):
    test_user.roles = [role]
    await db_session.commit()

    created = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"]},
    )

    assert created.status_code == 201
    deleted = await client.delete(f"/v1/webhooks/{created.json()['id']}")
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_webhook_other_user_forbidden(
    client: AsyncClient, other_user_client: AsyncClient, test_user
):
    response = await client.post(
        "/v1/webhooks/",
        json={
            "url": "https://example.com/webhook",
            "events": ["agent.*"],
            "secret": "test-secret",
        },
    )
    assert response.status_code == 201
    webhook_id = response.json()["id"]

    get_response = await other_user_client.get(f"/v1/webhooks/{webhook_id}")
    assert get_response.status_code == 403

    patch_response = await other_user_client.patch(
        f"/v1/webhooks/{webhook_id}",
        json={"url": "https://example.com/hijacked"},
    )
    assert patch_response.status_code == 403

    delete_response = await other_user_client.delete(f"/v1/webhooks/{webhook_id}")
    assert delete_response.status_code == 403

    test_response = await other_user_client.post(f"/v1/webhooks/{webhook_id}/test")
    assert test_response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_test_trigger(client: AsyncClient, test_user, monkeypatch):
    # Mock deliver_webhook_with_retry
    import src.api.services.webhook_service

    async def mock_deliver(*args, **kwargs):
        return True

    monkeypatch.setattr(
        src.api.services.webhook_service, "deliver_webhook_with_retry", mock_deliver
    )

    # Create
    response = await client.post(
        "/v1/webhooks/", json={"url": "https://example.com/webhook", "events": ["*"]}
    )
    webhook_id = response.json()["id"]

    # Test
    response = await client.post(f"/v1/webhooks/{webhook_id}/test")
    assert response.status_code == 200
    assert response.json()["status"] == "test_delivered"


@pytest.mark.asyncio
async def test_webhook_delivery_history_filters(client: AsyncClient, db_session, test_user):
    create_response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"]},
    )
    assert create_response.status_code == 201
    webhook_id = uuid.UUID(create_response.json()["id"])

    db_session.add_all(
        [
            WebhookDeliveryLog(
                webhook_id=webhook_id,
                event="deployment.event",
                payload='{"status":"running"}',
                success=True,
                attempts=1,
            ),
            WebhookDeliveryLog(
                webhook_id=webhook_id,
                event="agent.status",
                payload='{"new_status":"failed"}',
                success=False,
                error_message="boom",
                attempts=2,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        f"/v1/webhooks/{webhook_id}/deliveries?event=agent.status&success=false"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["event"] == "agent.status"
    assert data["items"][0]["success"] is False


@pytest.mark.asyncio
async def test_webhook_delivery_history_honors_skip_limit_and_desc_order(
    client: AsyncClient, db_session
):
    create_response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"]},
    )
    assert create_response.status_code == 201
    webhook_id = uuid.UUID(create_response.json()["id"])

    now = datetime.now()
    db_session.add_all(
        [
            WebhookDeliveryLog(
                webhook_id=webhook_id,
                event="agent.status",
                payload='{"seq":1}',
                success=True,
                attempts=1,
                created_at=now - timedelta(minutes=3),
            ),
            WebhookDeliveryLog(
                webhook_id=webhook_id,
                event="agent.status",
                payload='{"seq":2}',
                success=False,
                attempts=1,
                created_at=now - timedelta(minutes=2),
            ),
            WebhookDeliveryLog(
                webhook_id=webhook_id,
                event="agent.status",
                payload='{"seq":3}',
                success=True,
                attempts=1,
                created_at=now - timedelta(minutes=1),
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(f"/v1/webhooks/{webhook_id}/deliveries?skip=1&limit=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["payload"] == '{"seq":2}'
    assert data["items"][0]["success"] is False


@pytest.mark.asyncio
async def test_webhook_delivery_history_rejects_invalid_pagination_bounds(client: AsyncClient):
    create_response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"]},
    )
    assert create_response.status_code == 201
    webhook_id = create_response.json()["id"]

    negative_skip = await client.get(f"/v1/webhooks/{webhook_id}/deliveries?skip=-1")
    assert negative_skip.status_code == 422

    zero_limit = await client.get(f"/v1/webhooks/{webhook_id}/deliveries?limit=0")
    assert zero_limit.status_code == 422

    oversized_limit = await client.get(f"/v1/webhooks/{webhook_id}/deliveries?limit=501")
    assert oversized_limit.status_code == 422


@pytest.mark.asyncio
async def test_webhook_delivery_history_rejects_legacy_user_api_key_auth(
    client: AsyncClient, client_no_auth: AsyncClient, db_session, test_user
):
    create_response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"]},
    )
    assert create_response.status_code == 201
    webhook_id = uuid.UUID(create_response.json()["id"])

    test_user.api_key = "legacy-webhook-key"
    db_session.add(test_user)
    db_session.add(
        WebhookDeliveryLog(
            webhook_id=webhook_id,
            event="agent.heartbeat",
            payload='{"status":"running"}',
            success=True,
            attempts=1,
        )
    )
    await db_session.commit()

    response = await client_no_auth.get(
        f"/v1/webhooks/{webhook_id}/deliveries",
        headers={"X-API-Key": "legacy-webhook-key"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_delivery_history_supports_managed_api_key_auth(
    client_no_auth: AsyncClient, db_session, test_user
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    access_token, _ = create_access_token(test_user.id)

    create_response = await client_no_auth.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"]},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert create_response.status_code == 201
    webhook_id = uuid.UUID(create_response.json()["id"])

    key_response = await client_no_auth.post(
        "/v1/api-keys",
        json={"name": "managed-webhook-key"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert key_response.status_code == 201
    managed_api_key = key_response.json()["key"]

    db_session.add(
        WebhookDeliveryLog(
            webhook_id=webhook_id,
            event="agent.heartbeat",
            payload='{"status":"running"}',
            success=True,
            attempts=1,
        )
    )
    await db_session.commit()

    response = await client_no_auth.get(
        f"/v1/webhooks/{webhook_id}/deliveries",
        headers={"X-API-Key": managed_api_key},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["event"] == "agent.heartbeat"


@pytest.mark.asyncio
async def test_webhook_create_supports_managed_api_key_in_bearer_header(
    client_no_auth: AsyncClient, db_session, test_user
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    access_token, _ = create_access_token(test_user.id)
    key_response = await client_no_auth.post(
        "/v1/api-keys",
        json={"name": "webhook-bearer-key"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert key_response.status_code == 201
    managed_api_key = key_response.json()["key"]

    response = await client_no_auth.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["agent.*"]},
        headers={"Authorization": f"Bearer {managed_api_key}"},
    )

    assert response.status_code == 201
    assert response.json()["url"] == "https://example.com/webhook"


@pytest.mark.asyncio
async def test_jwt_uses_current_persisted_viewer_role_before_dns(
    client_no_auth: AsyncClient,
    db_session,
    test_user,
    monkeypatch,
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    access_token, _ = create_access_token(test_user.id)
    test_user.roles = ["VIEWER"]
    await db_session.commit()

    async def forbidden_resolution(*args, **kwargs):
        raise AssertionError("DNS ran before persisted-role denial")

    import src.api.services.webhook_service as webhook_service

    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        forbidden_resolution,
    )
    denied = await client_no_auth.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/denied", "events": ["*"]},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_managed_api_key_uses_current_viewer_role_for_read_and_mutation_denial(
    client_no_auth: AsyncClient,
    db_session,
    test_user,
    monkeypatch,
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    access_token, _ = create_access_token(test_user.id)
    jwt_headers = {"Authorization": f"Bearer {access_token}"}
    created = await client_no_auth.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"]},
        headers=jwt_headers,
    )
    assert created.status_code == 201
    key_response = await client_no_auth.post(
        "/v1/api-keys",
        json={"name": "viewer-webhook-key"},
        headers=jwt_headers,
    )
    assert key_response.status_code == 201
    key_headers = {"X-API-Key": key_response.json()["key"]}

    test_user.roles = ["VIEWER"]
    await db_session.commit()

    async def forbidden_resolution(*args, **kwargs):
        raise AssertionError("DNS ran before persisted-role denial")

    import src.api.services.webhook_service as webhook_service

    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        forbidden_resolution,
    )
    allowed_read = await client_no_auth.get(
        f"/v1/webhooks/{created.json()['id']}",
        headers=key_headers,
    )
    denied_create = await client_no_auth.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/denied", "events": ["*"]},
        headers=key_headers,
    )
    denied_delete = await client_no_auth.delete(
        f"/v1/webhooks/{created.json()['id']}",
        headers=key_headers,
    )

    assert allowed_read.status_code == 200
    assert denied_create.status_code == 403
    assert denied_delete.status_code == 403


@pytest.mark.asyncio
async def test_revoked_managed_api_key_cannot_read_owned_webhooks(
    client_no_auth: AsyncClient,
    db_session,
    test_user,
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    access_token, _ = create_access_token(test_user.id)
    jwt_headers = {"Authorization": f"Bearer {access_token}"}
    created = await client_no_auth.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"]},
        headers=jwt_headers,
    )
    assert created.status_code == 201
    key_response = await client_no_auth.post(
        "/v1/api-keys",
        json={"name": "revoked-webhook-key"},
        headers=jwt_headers,
    )
    assert key_response.status_code == 201
    revoked = await client_no_auth.delete(
        f"/v1/api-keys/{key_response.json()['id']}",
        headers=jwt_headers,
    )
    assert revoked.status_code == 204

    denied = await client_no_auth.get(
        f"/v1/webhooks/{created.json()['id']}",
        headers={"X-API-Key": key_response.json()["key"]},
    )

    assert denied.status_code == 401


@pytest.mark.asyncio
async def test_webhook_delivery_history_other_user_forbidden(
    client: AsyncClient, other_user_client: AsyncClient, db_session, test_user
):
    create_response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"]},
    )
    assert create_response.status_code == 201
    webhook_id = uuid.UUID(create_response.json()["id"])

    db_session.add(
        WebhookDeliveryLog(
            webhook_id=webhook_id,
            event="agent.status",
            payload='{"new_status":"running"}',
            success=True,
            attempts=1,
        )
    )
    await db_session.commit()

    response = await other_user_client.get(f"/v1/webhooks/{webhook_id}/deliveries")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_create_rejects_invalid_url(client: AsyncClient):
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "not-a-valid-url", "events": ["agent.*"]},
    )
    assert response.status_code == 400
    assert "must use HTTPS" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_create_rejects_invalid_event(client: AsyncClient):
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["invalid.event"]},
    )
    assert response.status_code == 400
    assert "Invalid event" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_create_rejects_loopback_destination(client: AsyncClient):
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://127.0.0.1/webhook", "events": ["agent.*"]},
    )

    assert response.status_code == 400
    assert "non-public address" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_update_rejects_invalid_url(client: AsyncClient):
    # Create first
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["agent.*"]},
    )
    assert response.status_code == 201
    webhook_id = response.json()["id"]

    # Try invalid update
    response = await client.patch(
        f"/v1/webhooks/{webhook_id}",
        json={"url": "ftp://example.com"},
    )
    assert response.status_code == 400
    assert "must use HTTPS" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_update_rejects_private_dns_destination(client: AsyncClient, monkeypatch):
    import src.api.services.webhook_service as webhook_service

    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["agent.*"]},
    )
    assert response.status_code == 201
    webhook_id = response.json()["id"]

    async def resolve_to_private_ip(hostname: str, port: int) -> set[str]:
        return {"10.0.0.12"}

    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        resolve_to_private_ip,
    )

    response = await client.patch(
        f"/v1/webhooks/{webhook_id}",
        json={"url": "https://internal.example.com/webhook"},
    )

    assert response.status_code == 400
    assert "non-public address" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_update_rejects_invalid_event(client: AsyncClient):
    # Create first
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["agent.*"]},
    )
    assert response.status_code == 201
    webhook_id = response.json()["id"]

    # Try invalid event
    response = await client.patch(
        f"/v1/webhooks/{webhook_id}",
        json={"events": ["nonexistent.event"]},
    )
    assert response.status_code == 400
    assert "Invalid event" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_get_nonexistent_returns_404(client: AsyncClient):
    response = await client.get("/v1/webhooks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_webhook_update_nonexistent_returns_404(client: AsyncClient):
    response = await client.patch(
        "/v1/webhooks/00000000-0000-0000-0000-000000000000",
        json={"url": "https://example.com"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_webhook_delete_nonexistent_returns_404(client: AsyncClient):
    response = await client.delete("/v1/webhooks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_webhook_test_nonexistent_returns_404(client: AsyncClient):
    response = await client.post("/v1/webhooks/00000000-0000-0000-0000-000000000000/test")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_webhook_deliveries_nonexistent_returns_404(client: AsyncClient):
    response = await client.get("/v1/webhooks/00000000-0000-0000-0000-000000000000/deliveries")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_webhook_delivery_history_empty(client: AsyncClient):
    # Create webhook
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["*"]},
    )
    assert response.status_code == 201
    webhook_id = response.json()["id"]

    # Get deliveries (should be empty list)
    response = await client.get(f"/v1/webhooks/{webhook_id}/deliveries")
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_webhook_test_delivery_failure_returns_502(
    client: AsyncClient, test_user, monkeypatch
):
    import src.api.services.webhook_service

    async def mock_deliver_failure(*args, **kwargs):
        return False

    monkeypatch.setattr(
        src.api.services.webhook_service, "deliver_webhook_with_retry", mock_deliver_failure
    )

    # Create
    response = await client.post(
        "/v1/webhooks/", json={"url": "https://example.com/webhook", "events": ["*"]}
    )
    webhook_id = response.json()["id"]

    # Test - should fail
    response = await client.post(f"/v1/webhooks/{webhook_id}/test")
    assert response.status_code == 502
    assert "delivery failed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_webhook_test_rejects_unsafe_stored_destination(
    client: AsyncClient, db_session, test_user
):
    webhook = Webhook(
        user_id=test_user.id,
        url="https://127.0.0.1/webhook",
        events=["*"],
        secret=None,
        is_active=True,
    )
    db_session.add(webhook)
    await db_session.commit()
    await db_session.refresh(webhook)

    response = await client.post(f"/v1/webhooks/{webhook.id}/test")

    assert response.status_code == 400
    assert "non-public address" in response.json()["detail"]


@pytest.mark.asyncio
async def test_deliver_webhook_blocks_unsafe_destination_before_network(monkeypatch):
    import src.api.services.webhook_service as webhook_service
    from src.api.services.webhook_service import deliver_webhook

    async def exploding_transport(*args, **kwargs):
        raise AssertionError("network request should not be attempted")

    monkeypatch.setattr(webhook_service, "_send_pinned_webhook_request", exploding_transport)

    webhook = Webhook(
        user_id=uuid.uuid4(),
        url="https://127.0.0.1/webhook",
        events=["*"],
        secret=None,
        is_active=True,
    )

    success, status_code, error_message, duration_ms, response_body = await deliver_webhook(
        webhook,
        "test",
        {"message": "blocked"},
        uuid.uuid4(),
    )

    assert success is False
    assert status_code is None
    assert error_message is not None
    assert "non-public address" in error_message


@pytest.mark.asyncio
async def test_webhook_create_defaults_is_active_to_true(client: AsyncClient):
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["agent.*"]},
    )
    assert response.status_code == 201
    assert response.json()["is_active"] is True


@pytest.mark.asyncio
async def test_webhook_create_with_is_active_false(client: AsyncClient):
    response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://example.com/webhook", "events": ["agent.*"], "is_active": False},
    )
    assert response.status_code == 201
    assert response.json()["is_active"] is False
