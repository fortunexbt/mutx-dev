"""
SDK contract tests for API keys module.
Tests verify that the SDK correctly maps to the backend API contract.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from mutx.api_keys import APIKey, APIKeyWithSecret, APIKeys


def _api_key_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "name": "test-key",
        "is_active": True,
        "last_used": None,
        "created_at": "2026-03-12T09:00:00",
        "expires_at": None,
    }
    payload.update(overrides)
    return payload


def _api_key_with_secret_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "name": "test-key",
        "is_active": True,
        "last_used": None,
        "created_at": "2026-03-12T09:00:00",
        "expires_at": None,
        "key": "mutx_sk_test_" + str(uuid.uuid4()).replace("-", "")[:32],
    }
    payload.update(overrides)
    return payload


def test_api_keys_list_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=[_api_key_payload()])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    api_keys = APIKeys(client)

    api_keys.list()

    assert captured["path"] == "/v1/api-keys"
    assert captured["method"] == "GET"


def test_api_keys_alist_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=[_api_key_payload()])

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    api_keys = APIKeys(client)

    import asyncio

    asyncio.run(api_keys.alist())

    assert captured["path"] == "/v1/api-keys"
    assert captured["method"] == "GET"


def test_api_keys_create_hits_contract_route_and_maps_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_api_key_with_secret_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    api_keys = APIKeys(client)

    api_keys.create(name="my-key", expires_in_days=30)

    assert captured["path"] == "/v1/api-keys"
    assert captured["method"] == "POST"
    assert captured["json"]["name"] == "my-key"
    assert captured["json"]["expires_in_days"] == 30


def test_api_keys_create_without_expiry() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_api_key_with_secret_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    api_keys = APIKeys(client)

    api_keys.create(name="permanent-key")

    assert "expires_in_days" not in captured["json"]


def test_api_keys_acreate_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_api_key_with_secret_payload())

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    api_keys = APIKeys(client)

    import asyncio

    asyncio.run(api_keys.acreate(name="async-key"))

    assert captured["path"] == "/v1/api-keys"
    assert captured["method"] == "POST"


def test_api_keys_revoke_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    key_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(204)

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    api_keys = APIKeys(client)

    api_keys.revoke(key_id)

    assert captured["path"] == f"/v1/api-keys/{key_id}"
    assert captured["method"] == "DELETE"


def test_api_keys_arevoke_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    key_id = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(204)

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    api_keys = APIKeys(client)

    import asyncio

    asyncio.run(api_keys.arevoke(key_id))

    assert captured["path"] == f"/v1/api-keys/{key_id}"
    assert captured["method"] == "DELETE"


def test_api_keys_rotate_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    key_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=_api_key_with_secret_payload(name="rotated-key"))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    api_keys = APIKeys(client)

    result = api_keys.rotate(key_id)

    assert captured["path"] == f"/v1/api-keys/{key_id}/rotate"
    assert captured["method"] == "POST"
    assert isinstance(result, APIKeyWithSecret)


def test_api_keys_arotate_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    key_id = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=_api_key_with_secret_payload())

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    api_keys = APIKeys(client)

    import asyncio

    result = asyncio.run(api_keys.arotate(key_id))

    assert captured["path"] == f"/v1/api-keys/{key_id}/rotate"
    assert captured["method"] == "POST"
    assert isinstance(result, APIKeyWithSecret)


def test_api_key_parses_required_fields() -> None:
    key = APIKey(_api_key_payload())

    assert key.id is not None
    assert key.name == "test-key"
    assert key.is_active is True


def test_api_key_parses_optional_fields() -> None:
    key = APIKey(
        _api_key_payload(
            last_used="2026-03-14T10:00:00",
            expires_at="2026-04-14T10:00:00",
        )
    )

    assert key.last_used is not None
    assert key.expires_at is not None


def test_api_key_with_secret_includes_key_field() -> None:
    key = APIKeyWithSecret(_api_key_with_secret_payload())

    assert hasattr(key, "key")
    assert key.key.startswith("mutx_sk_test_")


def test_api_keys_list_rejects_async_client() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    api_keys = APIKeys(client)

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        api_keys.list()


def test_api_keys_create_rejects_async_client() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    api_keys = APIKeys(client)

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        api_keys.create(name="test")


def test_api_keys_list_works_with_sync_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    api_keys = APIKeys(client)

    result = api_keys.list()
    assert result == []
