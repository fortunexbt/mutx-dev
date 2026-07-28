"""Approval SDK request contract tests."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from mutx.approvals import Approvals


def _approval_response() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "owner_id": str(uuid.uuid4()),
        "reviewer_id": str(uuid.uuid4()),
        "can_resolve": False,
        "agent_id": "agent-idempotent",
        "session_id": "session-idempotent",
        "action_type": "deploy",
        "payload": {"target": "production"},
        "status": "PENDING",
        "requester": "owner@example.com",
        "approver": None,
        "created_at": "2026-07-28T12:00:00+00:00",
        "resolved_at": None,
        "comment": None,
    }


def test_sync_create_sends_reviewer_and_idempotency_key() -> None:
    captured = []
    reviewer_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(201, json=_approval_response())

    with httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        Approvals(client).create(
            agent_id="agent-idempotent",
            session_id="session-idempotent",
            action_type="deploy",
            payload={"target": "production"},
            reviewer_id=reviewer_id,
            idempotency_key="approval-create-1",
        )

    request = captured[0]
    assert request.url.path == "/v1/approvals"
    assert request.headers["Idempotency-Key"] == "approval-create-1"
    assert json.loads(request.content)["reviewer_id"] == str(reviewer_id)


def test_sync_lists_discoverable_reviewers() -> None:
    reviewer_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/approvals/reviewers"
        return httpx.Response(
            200,
            json=[
                {
                    "id": str(reviewer_id),
                    "email": "reviewer@example.com",
                    "name": "Reviewer",
                    "roles": ["DEVELOPER"],
                }
            ],
        )

    with httpx.Client(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        reviewers = Approvals(client).list_reviewers()

    assert reviewers[0].id == reviewer_id
    assert reviewers[0].roles == ["DEVELOPER"]


@pytest.mark.asyncio
async def test_async_create_sends_reviewer_and_idempotency_key() -> None:
    captured = []
    reviewer_id = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(201, json=_approval_response())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/",
        transport=httpx.MockTransport(handler),
    ) as client:
        await Approvals(client).acreate(
            agent_id="agent-idempotent",
            session_id="session-idempotent",
            action_type="deploy",
            payload={"target": "production"},
            reviewer_id=reviewer_id,
            idempotency_key="approval-create-async",
        )

    request = captured[0]
    assert request.url.path == "/v1/approvals"
    assert request.headers["Idempotency-Key"] == "approval-create-async"
    assert json.loads(request.content)["reviewer_id"] == str(reviewer_id)
