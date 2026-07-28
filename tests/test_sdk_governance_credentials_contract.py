"""
SDK contract tests for governance credentials module.
Tests verify that the SDK correctly maps to the backend API contract.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from mutx.governance_credentials import (
    Credential,
    CredentialBackend,
    GovernanceCredentials,
)


# ---------------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------------


def _backend_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "name": "test-vault",
        "backend": "vault",
        "path": "vault:/secret/test",
        "ttl": 900,
        "is_active": True,
        "is_healthy": False,
    }
    payload.update(overrides)
    return payload


def _credential_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "name": "api-key",
        "backend": "vault",
        "path": "vault:/secret/test/api-key",
        "has_value": True,
        "expires_at": "2026-04-14T10:00:00",
        "metadata": {"owner": "test-team"},
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Sync route tests
# ---------------------------------------------------------------------------


def test_list_backends_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=[_backend_payload()])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    gc = GovernanceCredentials(client)

    result = gc.list_backends()

    assert captured["path"] == "/v1/governance/credentials/backends"
    assert captured["method"] == "GET"
    assert len(result) == 1
    assert isinstance(result[0], CredentialBackend)
    assert result[0].name == "test-vault"
    assert result[0].backend == "vault"


def test_register_backend_hits_contract_route_and_maps_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "registered"})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    gc = GovernanceCredentials(client)

    result = gc.register_backend(
        name="my-vault",
        backend="vault",
        path="vault:/secret/myapp",
        ttl=3600,
        config={"access_token": "abc123"},
    )

    assert captured["path"] == "/v1/governance/credentials/backends"
    assert captured["method"] == "POST"
    assert captured["json"]["name"] == "my-vault"
    assert captured["json"]["backend"] == "vault"
    assert captured["json"]["path"] == "vault:/secret/myapp"
    assert captured["json"]["ttl"] == 3600
    assert captured["json"]["config"]["access_token"] == "abc123"
    assert isinstance(result, dict)


def test_register_backend_omits_optional_config() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "registered"})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    gc = GovernanceCredentials(client)

    gc.register_backend(name="simple", backend="vault", path="vault:/secret/simple")

    assert "config" not in captured["json"]


def test_unregister_backend_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    backend_name = "to-delete"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"status": "unregistered"})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    gc = GovernanceCredentials(client)

    result = gc.unregister_backend(backend_name)

    assert captured["path"] == f"/v1/governance/credentials/backends/{backend_name}"
    assert captured["method"] == "DELETE"
    assert isinstance(result, dict)


def test_check_backend_health_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    backend_name = "my-vault"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"status": "healthy", "latency_ms": 5})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    gc = GovernanceCredentials(client)

    result = gc.check_backend_health(backend_name)

    assert captured["path"] == f"/v1/governance/credentials/backends/{backend_name}/health"
    assert captured["method"] == "GET"
    assert isinstance(result, dict)


def test_health_check_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"total": 2, "healthy": 1})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    gc = GovernanceCredentials(client)

    result = gc.health_check()

    assert captured["path"] == "/v1/governance/credentials/health"
    assert captured["method"] == "GET"
    assert isinstance(result, dict)


def test_get_credential_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    full_path = "vault:/secret/test/api-key"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=_credential_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    gc = GovernanceCredentials(client)

    result = gc.get_credential(full_path)

    assert captured["path"] == f"/v1/governance/credentials/get/{full_path}"
    assert captured["method"] == "GET"
    assert isinstance(result, Credential)
    assert result.name == "api-key"
    assert result.has_value is True


# ---------------------------------------------------------------------------
# Async route tests
# ---------------------------------------------------------------------------


def test_alist_backends_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=[_backend_payload()])

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    gc = GovernanceCredentials(client)

    import asyncio

    result = asyncio.run(gc.alist_backends())

    assert captured["path"] == "/v1/governance/credentials/backends"
    assert captured["method"] == "GET"
    assert len(result) == 1
    assert isinstance(result[0], CredentialBackend)


def test_aregister_backend_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"status": "registered"})

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    gc = GovernanceCredentials(client)

    import asyncio

    result = asyncio.run(
        gc.aregister_backend(
            name="async-vault",
            backend="vault",
            path="vault:/secret/async",
        )
    )

    assert captured["path"] == "/v1/governance/credentials/backends"
    assert captured["method"] == "POST"
    assert isinstance(result, dict)


def test_aunregister_backend_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    backend_name = "async-to-delete"

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"status": "unregistered"})

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    gc = GovernanceCredentials(client)

    import asyncio

    result = asyncio.run(gc.aunregister_backend(backend_name))

    assert captured["path"] == f"/v1/governance/credentials/backends/{backend_name}"
    assert captured["method"] == "DELETE"
    assert isinstance(result, dict)


def test_acheck_backend_health_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    backend_name = "async-vault"

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"status": "healthy"})

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    gc = GovernanceCredentials(client)

    import asyncio

    result = asyncio.run(gc.acheck_backend_health(backend_name))

    assert captured["path"] == f"/v1/governance/credentials/backends/{backend_name}/health"
    assert captured["method"] == "GET"
    assert isinstance(result, dict)


def test_ahealth_check_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"total": 1, "healthy": 1})

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    gc = GovernanceCredentials(client)

    import asyncio

    result = asyncio.run(gc.ahealth_check())

    assert captured["path"] == "/v1/governance/credentials/health"
    assert captured["method"] == "GET"
    assert isinstance(result, dict)


def test_aget_credential_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    full_path = "vault:/secret/async/api-key"

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=_credential_payload())

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    gc = GovernanceCredentials(client)

    import asyncio

    result = asyncio.run(gc.aget_credential(full_path))

    assert captured["path"] == f"/v1/governance/credentials/get/{full_path}"
    assert captured["method"] == "GET"
    assert isinstance(result, Credential)


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


def test_credential_backend_parses_required_fields() -> None:
    backend = CredentialBackend(_backend_payload())

    assert backend.name == "test-vault"
    assert backend.backend == "vault"
    assert backend.path == "vault:/secret/test"
    assert backend.ttl == 900
    assert backend.is_active is True
    assert backend.is_healthy is False


def test_credential_backend_parses_optional_fields() -> None:
    backend = CredentialBackend(_backend_payload(is_active=False, is_healthy=True, ttl=3600))

    assert backend.is_active is False
    assert backend.is_healthy is True
    assert backend.ttl == 3600


def test_credential_parses_required_fields() -> None:
    cred = Credential(_credential_payload())

    assert cred.name == "api-key"
    assert cred.backend == "vault"
    assert cred.path == "vault:/secret/test/api-key"
    assert cred.has_value is True
    assert cred.expires_at is not None
    assert cred.metadata["owner"] == "test-team"


def test_credential_parses_null_expires_at() -> None:
    cred = Credential(_credential_payload(expires_at=None))

    assert cred.expires_at is None


def test_credential_parses_empty_metadata() -> None:
    cred = Credential(_credential_payload(metadata={}))

    assert cred.metadata == {}


# ---------------------------------------------------------------------------
# Client-type enforcement tests
# ---------------------------------------------------------------------------


def test_list_backends_rejects_async_client() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    gc = GovernanceCredentials(client)

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        gc.list_backends()


def test_register_backend_rejects_async_client() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    gc = GovernanceCredentials(client)

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        gc.register_backend(name="x", backend="vault", path="vault:/x")


def test_unregister_backend_rejects_async_client() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    gc = GovernanceCredentials(client)

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        gc.unregister_backend("x")


def test_check_backend_health_rejects_async_client() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    gc = GovernanceCredentials(client)

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        gc.check_backend_health("x")


def test_health_check_rejects_async_client() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    gc = GovernanceCredentials(client)

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        gc.health_check()


def test_get_credential_rejects_async_client() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    gc = GovernanceCredentials(client)

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        gc.get_credential("vault:/x")


# ---------------------------------------------------------------------------
# Integration sanity: sync client works end-to-end with mock
# ---------------------------------------------------------------------------


def test_list_backends_works_with_sync_client_and_empty_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    gc = GovernanceCredentials(client)

    result = gc.list_backends()
    assert result == []


def test_register_backend_works_with_sync_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "registered"})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    gc = GovernanceCredentials(client)

    result = gc.register_backend(name="x", backend="vault", path="vault:/x")
    assert result["status"] == "registered"


def test_get_credential_works_with_sync_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_credential_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    gc = GovernanceCredentials(client)

    result = gc.get_credential("vault:/secret/test/api-key")
    assert isinstance(result, Credential)
    assert result.has_value is True
