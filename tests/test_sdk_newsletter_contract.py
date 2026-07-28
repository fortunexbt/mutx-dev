"""Contract tests for the compatibility-only newsletter SDK resource."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import Mock

import httpx
import pytest

from mutx.newsletter import Newsletter


def _unexpected_request(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"newsletter compatibility resource attempted network I/O: {request.url}")


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda newsletter: newsletter.get_count(), id="count"),
        pytest.param(
            lambda newsletter: newsletter.signup("test@example.com"),
            id="signup",
        ),
    ],
)
def test_sync_newsletter_endpoints_fail_before_network_io(
    operation: Callable[[Newsletter], object],
) -> None:
    with httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(_unexpected_request),
    ) as client:
        with pytest.raises(RuntimeError, match="not available in the mounted public /v1 API"):
            operation(Newsletter(client))


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda newsletter: newsletter.acount(), id="count"),
        pytest.param(
            lambda newsletter: newsletter.asignup("test@example.com"),
            id="signup",
        ),
    ],
)
@pytest.mark.asyncio
async def test_async_newsletter_endpoints_fail_before_network_io(
    operation: Callable[[Newsletter], Coroutine[Any, Any, object]],
) -> None:
    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(_unexpected_request),
    ) as client:
        with pytest.raises(RuntimeError, match="not available in the mounted public /v1 API"):
            await operation(Newsletter(client))


def test_sync_methods_reject_async_transport() -> None:
    newsletter = Newsletter(Mock(spec=httpx.AsyncClient))

    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        newsletter.get_count()
    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        newsletter.signup("test@example.com")


@pytest.mark.asyncio
async def test_async_methods_reject_sync_transport() -> None:
    newsletter = Newsletter(Mock(spec=httpx.Client))

    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await newsletter.acount()
    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await newsletter.asignup("test@example.com")
