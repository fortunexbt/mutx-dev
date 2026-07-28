from __future__ import annotations

import asyncio
import warnings

import pytest

pytestmark = pytest.mark.skip("MutxAsyncClient not yet implemented")

try:
    from mutx import MutxAsyncClient  # noqa: F401
except ImportError:
    MutxAsyncClient = object  # type: ignore[assignment, misc]


SAMPLE_UUID = "123e4567-e89b-12d3-a456-426614174000"


def _close_async_client(client: MutxAsyncClient) -> None:
    asyncio.run(client.aclose())


def test_mutx_async_client_emits_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = MutxAsyncClient(api_key="test-key", base_url="https://api.test/v1/")
        try:
            assert any("MutxAsyncClient is deprecated" in str(item.message) for item in caught)
        finally:
            _close_async_client(client)


@pytest.mark.parametrize(
    "resource_name, method_name, arg",
    [
        ("agents", "list", None),
        ("deployments", "list", None),
        ("api_keys", "list", None),
        ("webhooks", "list", None),
        ("agents", "deploy", SAMPLE_UUID),
        ("agents", "stop", SAMPLE_UUID),
        ("deployments", "logs", SAMPLE_UUID),
        ("webhooks", "get_deliveries", SAMPLE_UUID),
    ],
)
def test_mutx_async_client_sync_resource_methods_reject_async_transport(
    resource_name: str,
    method_name: str,
    arg: str | None,
) -> None:
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        client = MutxAsyncClient(api_key="test-key", base_url="https://api.test/v1/")

    try:
        resource = getattr(client, resource_name)
        method = getattr(resource, method_name)
        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            if arg is None:
                method()
            else:
                method(arg)
    finally:
        _close_async_client(client)
