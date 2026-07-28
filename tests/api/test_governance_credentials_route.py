"""
CRUD tests for /governance/credentials routes — register, list, health, get, unregister.
"""

import pytest
from httpx import AsyncClient

import src.api.routes.governance_credentials as gov_cred


@pytest.fixture(autouse=True)
def developer_principal(test_user):
    test_user.roles = ["DEVELOPER"]


class FakeBroker:
    """In-memory credential broker for testing."""

    def __init__(self):
        self._backends: list[dict] = []

    async def list_backends(self):
        return list(self._backends)

    async def register_backend(self, *, name, backend, path, ttl, config):
        self._backends.append(
            {
                "name": name,
                "backend": backend.value if hasattr(backend, "value") else str(backend),
                "path": path,
                "ttl": int(ttl.total_seconds()),
                "is_active": True,
                "is_healthy": True,
            }
        )
        return True

    async def unregister_backend(self, name: str):
        before = len(self._backends)
        self._backends = [b for b in self._backends if b["name"] != name]
        return len(self._backends) < before

    async def health_check(self):
        return {"healthy": all(b["is_healthy"] for b in self._backends)}

    async def get_credential_by_path(self, full_path: str, requester_id: str | None = None):
        from src.api.services.credential_broker import Credential
        from datetime import datetime, timezone

        return Credential(
            name="test-secret",
            backend="vault",
            path=full_path,
            value="secret-value-redacted",
            expires_at=datetime.now(timezone.utc),
            metadata={"scope": "test"},
        )


@pytest.fixture
def fake_broker():
    return FakeBroker()


@pytest.fixture
def patch_broker(fake_broker, monkeypatch):
    """Patch get_credential_broker to return a FakeBroker instance."""
    monkeypatch.setattr(
        gov_cred,
        "get_credential_broker",
        lambda namespace=None: fake_broker,
    )


# ---------------------------------------------------------------------------
# GET /governance/credentials/backends — list backends
# ---------------------------------------------------------------------------


class TestListCredentialBackends:
    @pytest.mark.asyncio
    async def test_list_backends_empty(self, client: AsyncClient, patch_broker):
        response = await client.get("/v1/governance/credentials/backends")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_backends_returns_registered(
        self, client: AsyncClient, patch_broker, fake_broker
    ):
        fake_broker._backends.append(
            {
                "name": "vault-prod",
                "backend": "vault",
                "path": "secret/prod",
                "ttl": 900,
                "is_active": True,
                "is_healthy": True,
            }
        )
        response = await client.get("/v1/governance/credentials/backends")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "vault-prod"
        assert data[0]["backend"] == "vault"
        assert data[0]["is_active"] is True


# ---------------------------------------------------------------------------
# POST /governance/credentials/backends — register backend
# ---------------------------------------------------------------------------


class TestRegisterCredentialBackend:
    @pytest.mark.asyncio
    async def test_register_valid_backend(self, client: AsyncClient, patch_broker):
        response = await client.post(
            "/v1/governance/credentials/backends",
            json={
                "name": "my-vault",
                "backend": "vault",
                "path": "secret/myapp",
                "ttl": 600,
                "config": {"address": "http://vault:8200"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "registered"
        assert data["name"] == "my-vault"

    @pytest.mark.asyncio
    async def test_register_invalid_backend_type(self, client: AsyncClient, patch_broker):
        response = await client.post(
            "/v1/governance/credentials/backends",
            json={
                "name": "bad-backend",
                "backend": "nonexistent",
                "path": "secret/test",
            },
        )
        assert response.status_code == 400
        assert "Invalid backend type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_each_valid_backend_type(self, client: AsyncClient, patch_broker):
        """Verify all supported backend enum values are accepted."""
        for backend_type in ["vault", "awssecrets", "gcpsm", "azurekv", "onepassword", "infisical"]:
            response = await client.post(
                "/v1/governance/credentials/backends",
                json={
                    "name": f"test-{backend_type}",
                    "backend": backend_type,
                    "path": f"secret/{backend_type}",
                },
            )
            assert response.status_code == 201, f"Failed for backend type: {backend_type}"


# ---------------------------------------------------------------------------
# DELETE /governance/credentials/backends/{backend_name} — unregister
# ---------------------------------------------------------------------------


class TestUnregisterCredentialBackend:
    @pytest.mark.asyncio
    async def test_unregister_existing_backend(
        self, client: AsyncClient, patch_broker, fake_broker
    ):
        fake_broker._backends.append(
            {
                "name": "vault-staging",
                "backend": "vault",
                "path": "secret/staging",
                "ttl": 900,
                "is_active": True,
                "is_healthy": True,
            }
        )
        response = await client.delete("/v1/governance/credentials/backends/vault-staging")
        assert response.status_code == 200
        assert response.json()["status"] == "unregistered"
        assert response.json()["name"] == "vault-staging"

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_backend(self, client: AsyncClient, patch_broker):
        response = await client.delete("/v1/governance/credentials/backends/ghost")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /governance/credentials/backends/{backend_name}/health
# ---------------------------------------------------------------------------


class TestBackendHealthCheck:
    @pytest.mark.asyncio
    async def test_health_existing_backend(self, client: AsyncClient, patch_broker, fake_broker):
        fake_broker._backends.append(
            {
                "name": "vault-health",
                "backend": "vault",
                "path": "secret/health",
                "ttl": 900,
                "is_active": True,
                "is_healthy": True,
            }
        )
        response = await client.get("/v1/governance/credentials/backends/vault-health/health")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "vault-health"
        assert data["healthy"] is True

    @pytest.mark.asyncio
    async def test_health_nonexistent_backend(self, client: AsyncClient, patch_broker):
        response = await client.get("/v1/governance/credentials/backends/nope/health")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_health_unhealthy_backend(self, client: AsyncClient, patch_broker, fake_broker):
        fake_broker._backends.append(
            {
                "name": "vault-down",
                "backend": "vault",
                "path": "secret/down",
                "ttl": 900,
                "is_active": True,
                "is_healthy": False,
            }
        )
        response = await client.get("/v1/governance/credentials/backends/vault-down/health")
        assert response.status_code == 200
        assert response.json()["healthy"] is False


# ---------------------------------------------------------------------------
# GET /governance/credentials/health — check all backends
# ---------------------------------------------------------------------------


class TestAllBackendsHealth:
    @pytest.mark.asyncio
    async def test_all_healthy(self, client: AsyncClient, patch_broker, fake_broker):
        response = await client.get("/v1/governance/credentials/health")
        assert response.status_code == 200
        assert response.json()["healthy"] is True

    @pytest.mark.asyncio
    async def test_all_empty(self, client: AsyncClient, patch_broker):
        response = await client.get("/v1/governance/credentials/health")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /governance/credentials/get/{full_path} — get credential
# ---------------------------------------------------------------------------


class TestGetCredential:
    @pytest.mark.asyncio
    async def test_get_credential_returns_redacted_value(self, client: AsyncClient, patch_broker):
        response = await client.get("/v1/governance/credentials/get/vault:/secret/prod/api-key")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-secret"
        assert data["backend"] == "vault"
        assert data["value"] is None  # Always redacted
        assert data["has_value"] is True
        assert "expires_at" in data
        assert data["metadata"]["scope"] == "test"
