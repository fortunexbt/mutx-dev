"""CLI contract tests for request-ID based legacy approval decisions."""

from __future__ import annotations

import json
from typing import Any

import httpx

from cli.services.observability import SecurityService


class _AuthenticatedConfig:
    api_url = "https://api.test"
    access_token = "ordinary-access-token"
    refresh_token = "ordinary-refresh-token"

    @staticmethod
    def is_authenticated() -> bool:
        return True


def _exercise(method_name: str, request_id: str) -> httpx.Request:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        status = "approved" if method_name == "approve_request" else "denied"
        return httpx.Response(200, json={"request_id": request_id, "status": status})

    def client_factory(_config: Any) -> httpx.Client:
        return httpx.Client(
            base_url="https://api.test",
            transport=httpx.MockTransport(handler),
        )

    service = SecurityService(
        config=_AuthenticatedConfig(),
        client_factory=client_factory,
    )
    getattr(service, method_name)(request_id, "reviewed")
    return captured[0]


def test_cli_approval_decisions_use_request_id_and_authenticated_transport() -> None:
    request_id = "00000000-0000-4000-8000-000000000123"

    approved = _exercise("approve_request", request_id)
    denied = _exercise("deny_request", request_id)

    assert approved.url.path == f"/v1/security/approvals/{request_id}/approve"
    assert denied.url.path == f"/v1/security/approvals/{request_id}/deny"
    assert json.loads(approved.content) == {"comment": "reviewed"}
    assert json.loads(denied.content) == {"comment": "reviewed"}
    assert "token" not in json.loads(approved.content)
    assert "token" not in json.loads(denied.content)
