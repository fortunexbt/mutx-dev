"""Focused route tests for durable, tenant-scoped telemetry configuration."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import src.api.routes.telemetry as telemetry_route
import src.api.services.telemetry_backend as telemetry_backend
from src.api.models.telemetry_backend import TelemetryBackendConfig


@pytest.fixture(autouse=True)
def administrator_principal(test_user):
    test_user.roles = ["ADMIN"]


@pytest.fixture
def reachable_collector(monkeypatch: pytest.MonkeyPatch) -> None:
    async def reachable(_target):
        return True, None

    monkeypatch.setattr(telemetry_backend, "_probe_endpoint", reachable)
    monkeypatch.setattr(
        telemetry_route,
        "get_runtime_telemetry_status",
        lambda: (True, "console"),
    )


@pytest.mark.asyncio
async def test_get_telemetry_config_requires_authentication(client_no_auth: AsyncClient):
    response = await client_no_auth.get("/v1/telemetry/config")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_telemetry_config_is_truthful_when_tenant_has_no_saved_target(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        telemetry_route,
        "get_runtime_telemetry_status",
        lambda: (True, "console"),
    )

    response = await client.get("/v1/telemetry/config")

    assert response.status_code == 200
    assert response.json() == {
        "otel_enabled": True,
        "exporter_type": "console",
        "endpoint": None,
        "protocol": None,
        "configured": False,
        "runtime_applied": False,
    }


@pytest.mark.asyncio
async def test_configure_telemetry_requires_authentication(client_no_auth: AsyncClient):
    response = await client_no_auth.post(
        "/v1/telemetry/config",
        json={"otlp_endpoint": "http://8.8.8.8:4317", "protocol": "grpc"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_configure_telemetry_persists_owned_config_and_bounded_health_result(
    client: AsyncClient,
    db_session,
    test_user,
    reachable_collector,
):
    response = await client.post(
        "/v1/telemetry/config",
        json={"otlp_endpoint": "HTTP://8.8.8.8:4317/", "protocol": "grpc"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "configured"
    assert payload["runtime_applied"] is False
    assert payload["config"]["endpoint"] == "http://8.8.8.8:4317/"
    assert payload["config"]["protocol"] == "grpc"
    assert payload["health"] | {"checked_at": None} == {
        "configured": True,
        "endpoint_reachable": True,
        "using_grpc": True,
        "endpoint": "http://8.8.8.8:4317/",
        "status": "reachable",
        "checked_at": None,
        "failure_reason": None,
    }

    record = (
        await db_session.execute(
            select(TelemetryBackendConfig).where(TelemetryBackendConfig.owner_id == test_user.id)
        )
    ).scalar_one()
    assert record.endpoint == "http://8.8.8.8:4317/"
    assert record.owner_id == test_user.id


@pytest.mark.asyncio
async def test_telemetry_role_and_internal_user_gates_run_before_state_change(
    client: AsyncClient,
    db_session,
    test_user,
):
    for role in ("VIEWER", "DEVELOPER", "AUDIT_ADMIN"):
        test_user.roles = [role]
        response = await client.post(
            "/v1/telemetry/config",
            json={"otlp_endpoint": "http://8.8.8.8:4317", "protocol": "grpc"},
        )
        assert response.status_code == 403

    test_user.roles = ["ADMIN"]
    test_user.email = "external@example.com"
    response = await client.post(
        "/v1/telemetry/config",
        json={"otlp_endpoint": "http://8.8.8.8:4317", "protocol": "grpc"},
    )
    assert response.status_code == 403
    assert (await db_session.execute(select(TelemetryBackendConfig))).scalars().all() == []


@pytest.mark.asyncio
async def test_configure_rejects_private_target_without_persisting_it(
    client: AsyncClient,
    db_session,
):
    response = await client.post(
        "/v1/telemetry/config",
        json={"otlp_endpoint": "http://169.254.169.254:4317", "protocol": "grpc"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "OTLP endpoint resolves to a non-public address"}
    assert (await db_session.execute(select(TelemetryBackendConfig))).scalars().all() == []


@pytest.mark.asyncio
async def test_unknown_request_fields_are_rejected(client: AsyncClient):
    response = await client.post(
        "/v1/telemetry/config",
        json={
            "otlp_endpoint": "http://8.8.8.8:4317",
            "protocol": "grpc",
            "owner_id": "22222222-2222-4222-a222-222222222222",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_tenants_cannot_read_or_overwrite_each_others_configuration(
    client: AsyncClient,
    other_user_client: AsyncClient,
    test_user,
    other_user,
    reachable_collector,
):
    other_user.roles = ["ADMIN"]
    other_user.email = "other@mutx.dev"
    other_user.is_email_verified = True

    first = await client.post(
        "/v1/telemetry/config",
        json={"otlp_endpoint": "http://8.8.8.8:4317", "protocol": "grpc"},
    )
    second = await other_user_client.post(
        "/v1/telemetry/config",
        json={"otlp_endpoint": "http://1.1.1.1:4318", "protocol": "http"},
    )
    assert first.status_code == 200
    assert second.status_code == 200

    first_read = await client.get("/v1/telemetry/config")
    second_read = await other_user_client.get("/v1/telemetry/config")

    assert first_read.json()["endpoint"] == "http://8.8.8.8:4317"
    assert first_read.json()["protocol"] == "grpc"
    assert second_read.json()["endpoint"] == "http://1.1.1.1:4318"
    assert second_read.json()["protocol"] == "http"
    assert test_user.id != other_user.id
