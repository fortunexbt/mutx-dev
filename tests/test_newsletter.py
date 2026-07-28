"""Truthful compatibility tests for the intentionally unmounted newsletter SDK resource."""

from __future__ import annotations

from unittest.mock import Mock

import httpx
import pytest

from mutx.newsletter import Newsletter


UNAVAILABLE_MESSAGE = "not available in the mounted public /v1 API"


def _unexpected_request(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"Newsletter compatibility resource made a request to {request.url}")


def test_sync_methods_fail_closed_without_sending_a_request() -> None:
    with httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(_unexpected_request),
    ) as client:
        newsletter = Newsletter(client)

        with pytest.raises(RuntimeError, match=UNAVAILABLE_MESSAGE):
            newsletter.get_count()
        with pytest.raises(RuntimeError, match=UNAVAILABLE_MESSAGE):
            newsletter.signup(email="operator@example.com")


@pytest.mark.asyncio
async def test_async_methods_fail_closed_without_sending_a_request() -> None:
    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(_unexpected_request),
    ) as client:
        newsletter = Newsletter(client)

        with pytest.raises(RuntimeError, match=UNAVAILABLE_MESSAGE):
            await newsletter.acount()
        with pytest.raises(RuntimeError, match=UNAVAILABLE_MESSAGE):
            await newsletter.asignup(email="operator@example.com")


def test_sync_methods_reject_an_async_client_before_availability_check() -> None:
    newsletter = Newsletter(Mock(spec=httpx.AsyncClient))

    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        newsletter.get_count()
    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        newsletter.signup(email="operator@example.com")


@pytest.mark.asyncio
async def test_async_methods_reject_a_sync_client_before_availability_check() -> None:
    newsletter = Newsletter(Mock(spec=httpx.Client))

    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await newsletter.acount()
    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await newsletter.asignup(email="operator@example.com")
