"""Helpers for asserting resolved SDK requests without coupling tests to route arguments."""

from __future__ import annotations

from unittest.mock import Mock

import httpx

SDK_TEST_BASE_URL = "https://api.test/v1/"


def assert_v1_request(
    mocked_method: Mock,
    method: str,
    expected_path: str,
) -> httpx.Request:
    """Replay a recorded resource call and assert its final canonical HTTP request."""

    assert mocked_method.call_count == 1
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    with httpx.Client(
        base_url=SDK_TEST_BASE_URL,
        transport=httpx.MockTransport(handler),
    ) as client:
        request_method = getattr(client, method.lower())
        request_method(*mocked_method.call_args.args, **mocked_method.call_args.kwargs)

    request = requests[0]
    assert request.method == method.upper()
    assert request.url.path == expected_path
    return request
