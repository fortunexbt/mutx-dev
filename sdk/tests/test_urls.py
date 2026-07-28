from __future__ import annotations

import json

import httpx
import pytest

from mutx import MutxClient
from mutx._http import DEFAULT_BASE_URL, api_path, normalize_api_base_url
from mutx.agent_runtime import MutxAgentClient, MutxAgentSyncClient
from mutx.agents import Agents
from mutx.approvals import Approvals
from mutx.deployments import Deployments
from mutx.newsletter import Newsletter


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        (DEFAULT_BASE_URL, "https://api.mutx.dev/v1"),
        ("https://api.mutx.dev/", "https://api.mutx.dev/v1"),
        ("https://api.mutx.dev/v1", "https://api.mutx.dev/v1"),
        ("https://api.mutx.dev/v1/", "https://api.mutx.dev/v1"),
        ("http://localhost:8000", "http://localhost:8000/v1"),
        ("http://localhost:8000/api", "http://localhost:8000/api/v1"),
    ],
)
def test_normalize_api_base_url(base_url: str, expected: str) -> None:
    assert normalize_api_base_url(base_url) == expected


@pytest.mark.parametrize(
    "base_url",
    ["", "   ", "localhost:8000", "ftp://api.mutx.dev", "https://api.mutx.dev?x=1"],
)
def test_normalize_api_base_url_rejects_invalid_values(base_url: str) -> None:
    with pytest.raises(ValueError):
        normalize_api_base_url(base_url)


def test_mutx_client_uses_canonical_base_and_context_manager() -> None:
    with MutxClient(api_key="test", base_url="http://localhost:8000/v1/") as client:
        request = client.http.build_request("GET", "agents")
        assert str(request.url) == "http://localhost:8000/v1/agents"
        assert client.base_url == "http://localhost:8000/v1"
        assert client.api_base_url == "http://localhost:8000/v1"
        assert not client.http.is_closed

    assert client.http.is_closed


def test_mutx_client_exposes_approvals_on_its_canonical_transport() -> None:
    with MutxClient(api_key="test", base_url="https://api.test") as client:
        approvals = client.approvals

        assert isinstance(approvals, Approvals)
        assert approvals._client is client.http
        request = client.http.build_request("GET", "approvals")
        assert str(request.url) == "https://api.test/v1/approvals"


def test_agent_runtime_clients_share_base_url_normalization() -> None:
    async_client = MutxAgentClient(mutx_url="https://api.mutx.dev/v1/")
    sync_client = MutxAgentSyncClient(mutx_url="http://localhost:8000")

    assert async_client.api_base_url == "https://api.mutx.dev/v1"
    assert sync_client.mutx_url == "http://localhost:8000"
    assert sync_client.api_base_url == "http://localhost:8000/v1"


def test_api_path_encodes_each_identifier_as_one_segment() -> None:
    assert (
        api_path("agents/{agent_id}/logs", agent_id="team/agent ?#")
        == "agents/team%2Fagent%20%3F%23/logs"
    )


def test_sync_resource_preserves_query_and_encoded_id_contracts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/agents":
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json={
                "id": "00000000-0000-0000-0000-000000000001",
                "name": "encoded-agent",
                "status": "stopped",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "deployments": [],
            },
        )

    with httpx.Client(
        base_url=normalize_api_base_url(DEFAULT_BASE_URL),
        transport=httpx.MockTransport(handler),
    ) as http:
        resource = Agents(http)
        assert resource.list(skip=7, limit=9) == []
        resource.get("team/agent ?#")

    assert str(requests[0].url) == "https://api.mutx.dev/v1/agents?skip=7&limit=9"
    assert requests[1].url.raw_path == b"/v1/agents/team%2Fagent%20%3F%23"


@pytest.mark.asyncio
async def test_async_resource_preserves_body_and_encoded_id_contracts() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "00000000-0000-0000-0000-000000000002",
                "agent_id": "00000000-0000-0000-0000-000000000001",
                "status": "running",
                "replicas": 3,
                "events": [],
            },
        )

    async with httpx.AsyncClient(
        base_url=normalize_api_base_url("http://localhost:8000/v1"),
        transport=httpx.MockTransport(handler),
    ) as http:
        deployment = await Deployments(http).ascale("deployment/blue ?#", replicas=3)

    assert deployment.replicas == 3
    assert requests[0].url.raw_path == b"/v1/deployments/deployment%2Fblue%20%3F%23/scale"
    assert json.loads(requests[0].content) == {"replicas": 3}


def test_unmounted_newsletter_fails_before_network_io() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    with httpx.Client(
        base_url=normalize_api_base_url(DEFAULT_BASE_URL),
        transport=httpx.MockTransport(handler),
    ) as http:
        with pytest.raises(RuntimeError, match="not available in the mounted public /v1 API"):
            Newsletter(http).get_count()
