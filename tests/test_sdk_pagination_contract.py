"""Contract tests for canonical paginated SDK list responses."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from mutx.agents import Agent, Agents
from mutx.api_keys import APIKey, APIKeys
from mutx.approvals import ApprovalRequest, Approvals
from mutx.pagination import Page, PageEnvelopeError


def _agent_item(index: int) -> dict[str, Any]:
    return {
        "id": f"00000000-0000-4000-8000-{index:012d}",
        "name": f"agent-{index}",
        "description": f"Agent page item {index}",
        "type": "openai",
        "status": "stopped",
        "config": {"model": "gpt-4o-mini"},
        "config_version": 1,
        "created_at": "2026-07-28T09:00:00+00:00",
        "updated_at": "2026-07-28T09:00:00+00:00",
        "user_id": "10000000-0000-4000-8000-000000000001",
    }


def _api_key_item(index: int) -> dict[str, Any]:
    return {
        "id": f"20000000-0000-4000-8000-{index:012d}",
        "name": f"key-{index}",
        "last_used": None,
        "created_at": "2026-07-28T09:00:00+00:00",
        "expires_at": None,
        "is_active": True,
    }


def _approval_item(index: int) -> dict[str, Any]:
    return {
        "id": f"30000000-0000-4000-8000-{index:012d}",
        "owner_id": "30000000-0000-4000-8000-000000000101",
        "reviewer_id": "30000000-0000-4000-8000-000000000102",
        "can_resolve": True,
        "agent_id": "agent-filter",
        "session_id": f"session-{index}",
        "action_type": "deploy",
        "payload": {"target": "production"},
        "status": "PENDING",
        "requester": "operator@mutx.dev",
        "approver": None,
        "created_at": "2026-07-28T09:00:00+00:00",
        "resolved_at": None,
        "comment": None,
    }


@pytest.fixture(
    params=[
        pytest.param(
            (Agents, Agent, "agents", _agent_item, False),
            id="agents",
        ),
        pytest.param(
            (APIKeys, APIKey, "api-keys", _api_key_item, False),
            id="api-keys",
        ),
        pytest.param(
            (Approvals, ApprovalRequest, "approvals", _approval_item, True),
            id="approvals",
        ),
    ]
)
def list_case(
    request: pytest.FixtureRequest,
) -> tuple[type[Any], type[Any], str, Callable[[int], dict[str, Any]], bool]:
    return request.param


def _list_kwargs(is_approvals: bool, *, skip: int, limit: int) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"skip": skip, "limit": limit}
    if is_approvals:
        kwargs.update(status="PENDING", agent_id="agent-filter")
    return kwargs


def _envelope(
    *,
    path: str,
    items: list[dict[str, Any]],
    total: int,
    skip: int,
    limit: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }
    if path == "approvals":
        payload.update(status="PENDING", agent_id="agent-filter")
    else:
        payload["has_more"] = skip + len(items) < total
    return payload


def test_sync_list_parses_exact_nonempty_envelope_and_query(
    list_case: tuple[type[Any], type[Any], str, Callable[[int], dict[str, Any]], bool],
) -> None:
    resource_type, model_type, path, item_factory, is_approvals = list_case
    captured: list[httpx.Request] = []
    response_payload = _envelope(
        path=path,
        items=[item_factory(1), item_factory(2)],
        total=5,
        skip=1,
        limit=2,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=response_payload)

    with httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        page = resource_type(client).list(**_list_kwargs(is_approvals, skip=1, limit=2))

    assert isinstance(page, Page)
    assert len(page) == 2
    assert isinstance(page[0], model_type)
    if path == "agents":
        labels = [item.name for item in page]
        expected_labels = ["agent-1", "agent-2"]
    elif path == "api-keys":
        labels = [item.name for item in page]
        expected_labels = ["key-1", "key-2"]
    else:
        labels = [item.session_id for item in page]
        expected_labels = ["session-1", "session-2"]
    assert labels == expected_labels
    assert page.total == 5
    assert page.skip == 1
    assert page.limit == 2
    assert page.has_more is True
    assert page.is_legacy is False
    assert captured[0].url.path == f"/v1/{path}"
    assert captured[0].url.params["skip"] == "1"
    assert captured[0].url.params["limit"] == "2"
    if is_approvals:
        assert captured[0].url.params["status"] == "PENDING"
        assert captured[0].url.params["agent_id"] == "agent-filter"
        assert page.metadata == {"status": "PENDING", "agent_id": "agent-filter"}


@pytest.mark.asyncio
async def test_async_list_matches_sync_pagination_surface(
    list_case: tuple[type[Any], type[Any], str, Callable[[int], dict[str, Any]], bool],
) -> None:
    resource_type, model_type, path, item_factory, is_approvals = list_case
    captured: list[httpx.Request] = []
    response_payload = _envelope(
        path=path,
        items=[item_factory(3)],
        total=3,
        skip=2,
        limit=1,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=response_payload)

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        page = await resource_type(client).alist(**_list_kwargs(is_approvals, skip=2, limit=1))

    assert isinstance(page, Page)
    assert isinstance(page[0], model_type)
    assert (page.total, page.skip, page.limit, page.has_more) == (3, 2, 1, False)
    assert captured[0].url.path == f"/v1/{path}"
    assert captured[0].url.params["skip"] == "2"
    assert captured[0].url.params["limit"] == "1"


def test_list_parses_exact_empty_envelope(
    list_case: tuple[type[Any], type[Any], str, Callable[[int], dict[str, Any]], bool],
) -> None:
    resource_type, _, path, _, is_approvals = list_case
    response_payload = _envelope(path=path, items=[], total=0, skip=0, limit=50)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_payload)

    with httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        page = resource_type(client).list(**_list_kwargs(is_approvals, skip=0, limit=50))

    assert page == []
    assert page.items == []
    assert page.total == 0
    assert page.has_more is False


def test_list_can_consume_multiple_canonical_pages(
    list_case: tuple[type[Any], type[Any], str, Callable[[int], dict[str, Any]], bool],
) -> None:
    resource_type, _, path, item_factory, is_approvals = list_case
    payloads = {
        "0": _envelope(path=path, items=[item_factory(1)], total=2, skip=0, limit=1),
        "1": _envelope(path=path, items=[item_factory(2)], total=2, skip=1, limit=1),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payloads[request.url.params["skip"]])

    with httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        resource = resource_type(client)
        first = resource.list(**_list_kwargs(is_approvals, skip=0, limit=1))
        second = resource.list(**_list_kwargs(is_approvals, skip=1, limit=1))

    assert len(first) == len(second) == 1
    assert first.has_more is True
    assert second.has_more is False
    assert first[0].id != second[0].id


def test_legacy_bare_list_remains_sequence_compatible(
    list_case: tuple[type[Any], type[Any], str, Callable[[int], dict[str, Any]], bool],
) -> None:
    resource_type, model_type, _, item_factory, is_approvals = list_case

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[item_factory(1)])

    with httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        page = resource_type(client).list(**_list_kwargs(is_approvals, skip=4, limit=2))

    assert page == list(page)
    assert len(page) == 1
    assert isinstance(page[0], model_type)
    assert page.skip == 4
    assert page.limit == 2
    assert page.total is None
    assert page.has_more is None
    assert page.is_legacy is True


@pytest.fixture(
    params=[
        pytest.param({"items": [], "total": 0, "skip": 0}, id="missing-limit"),
        pytest.param(
            {"items": {}, "total": 0, "skip": 0, "limit": 50},
            id="items-not-list",
        ),
        pytest.param(
            {"items": [], "total": "0", "skip": 0, "limit": 50},
            id="total-not-integer",
        ),
        pytest.param(
            {"items": [], "total": 0, "skip": 0, "limit": 50, "has_more": "false"},
            id="has-more-not-boolean",
        ),
    ]
)
def malformed_envelope(request: pytest.FixtureRequest) -> object:
    return request.param


def test_list_rejects_malformed_canonical_envelope(
    list_case: tuple[type[Any], type[Any], str, Callable[[int], dict[str, Any]], bool],
    malformed_envelope: object,
) -> None:
    resource_type, _, _, _, is_approvals = list_case

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=malformed_envelope)

    with httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(PageEnvelopeError):
            resource_type(client).list(**_list_kwargs(is_approvals, skip=0, limit=50))


@pytest.mark.parametrize("resource_type", [Agents, APIKeys])
def test_list_requires_has_more_when_endpoint_contract_defines_it(
    resource_type: type[Any],
) -> None:
    payload = {"items": [], "total": 0, "skip": 0, "limit": 50}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(PageEnvelopeError, match="has_more"):
            resource_type(client).list()
