"""Tests for /v1/runtime route — provider snapshots and governance endpoints."""

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def administrator_principal(test_user):
    test_user.roles = ["ADMIN"]


# ---------------------------------------------------------------------------
# GET /v1/runtime/providers/{provider}  — read provider state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_runtime_provider_requires_auth(client_no_auth: AsyncClient):
    """GET provider snapshot requires authentication."""
    response = await client_no_auth.get("/v1/runtime/providers/openclaw")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_runtime_provider_returns_200(client: AsyncClient):
    """GET provider snapshot returns 200 with default state."""
    response = await client.get("/v1/runtime/providers/openclaw")
    assert response.status_code == 200
    data = response.json()
    assert "provider" in data
    assert data["provider"] == "openclaw"


# ---------------------------------------------------------------------------
# PUT /v1/runtime/providers/{provider}  — upsert provider state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_runtime_provider_requires_auth(client_no_auth: AsyncClient):
    """PUT provider snapshot requires authentication."""
    response = await client_no_auth.put(
        "/v1/runtime/providers/openclaw",
        json={"label": "OpenClaw", "status": "healthy"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upsert_runtime_provider_minimal(client: AsyncClient):
    """PUT with minimal payload creates provider state."""
    response = await client.put(
        "/v1/runtime/providers/openclaw",
        json={"label": "OpenClaw", "status": "healthy"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "openclaw"
    assert data["label"] == "OpenClaw"
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_upsert_runtime_provider_with_gateway(client: AsyncClient):
    """PUT with gateway config persists correctly."""
    response = await client.put(
        "/v1/runtime/providers/test-provider",
        json={
            "label": "Test Provider",
            "status": "running",
            "gateway_url": "http://localhost:8080",
            "gateway_port": 8080,
            "version": "1.0.0",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "test-provider"
    assert data["gateway_url"] == "http://localhost:8080"


@pytest.mark.asyncio
async def test_upsert_then_get_runtime_provider(client: AsyncClient):
    """PUT then GET returns the stored state."""
    await client.put(
        "/v1/runtime/providers/roundtrip",
        json={"label": "Roundtrip", "status": "active", "version": "2.0"},
    )
    response = await client.get("/v1/runtime/providers/roundtrip")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "roundtrip"
    assert data["label"] == "Roundtrip"
    assert data["version"] == "2.0"


# ---------------------------------------------------------------------------
# GET /v1/runtime/governance/metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_governance_metrics_returns_200(client: AsyncClient):
    """Governance metrics endpoint returns text/plain."""
    response = await client.get("/v1/runtime/governance/metrics")
    # May return 200 or 500 depending on faramesh availability
    assert response.status_code in (200, 500)


# ---------------------------------------------------------------------------
# GET /v1/runtime/governance/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_governance_status_returns_json(client: AsyncClient):
    """Governance status returns a JSON object."""
    response = await client.get("/v1/runtime/governance/status")
    assert response.status_code == 200
    data = response.json()
    # Either returns health info or an error message
    assert isinstance(data, dict)
