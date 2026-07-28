"""Tests for the authenticated, owner-scoped ``/v1/security`` surface."""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

TEST_AGENT_ID = "33333333-3333-4333-a333-333333333333"
OTHER_AGENT_ID = "55555555-5555-4555-a555-555555555555"


@pytest_asyncio.fixture(autouse=True)
async def developer_principal(db_session, test_user, test_agent, other_user):
    """Legacy success cases run as the least-privileged mutation role."""
    test_user.roles = ["DEVELOPER"]
    test_user.plan = "STARTER"
    other_user.plan = "STARTER"
    db_session.add_all([test_user, other_user])
    await db_session.commit()


@pytest_asyncio.fixture
async def other_test_agent(db_session, other_user):
    from src.api.models.models import Agent, AgentStatus

    agent = Agent(
        id=uuid.UUID(OTHER_AGENT_ID),
        name="other-security-agent",
        config="{}",
        user_id=other_user.id,
        status=AgentStatus.CREATING,
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


async def _set_roles(db_session, user, *roles: str) -> None:
    user.roles = list(roles)
    db_session.add(user)
    await db_session.commit()


async def _approval_request_id(db_session, owner, request_id: str) -> str:
    """Keep request-ID setup readable in tests that switch principals."""
    del db_session, owner
    return request_id


# ---------------------------------------------------------------------------
# POST /v1/security/actions/evaluate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_action_returns_decision(client: AsyncClient):
    """Evaluate action returns a policy decision."""
    response = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "file_read",
            "tool_args": {"path": "/etc/passwd"},
            "agent_id": TEST_AGENT_ID,
            "session_id": "session-001",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "decision" in data
    assert "action_id" in data
    assert "action_hash" in data
    assert data["decision"] in ("permit", "deny", "defer")


@pytest.mark.asyncio
async def test_evaluate_action_missing_required_fields(client: AsyncClient):
    """Missing required fields returns 422."""
    response = await client.post(
        "/v1/security/actions/evaluate",
        json={"tool_name": "file_read"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/security/approvals/request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_approval_success(client: AsyncClient):
    """Request approval creates a pending approval."""
    response = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "tool_args": {"path": "/tmp/test"},
            "agent_id": TEST_AGENT_ID,
            "session_id": "session-001",
            "reason": "Needs human review",
            "timeout_minutes": 5,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "request_id" in data
    assert "token" not in data
    assert data["owner_id"]
    assert data["reviewer_id"] is None
    assert data["can_resolve"] is False
    assert data["status"] == "pending"
    assert data["tool_name"] == "file_write"


@pytest.mark.asyncio
async def test_request_approval_missing_fields(client: AsyncClient):
    """Missing required fields returns 422."""
    response = await client.post(
        "/v1/security/approvals/request",
        json={"tool_name": "file_write"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/security/approvals/{request_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_approval_not_found(client: AsyncClient):
    """Non-existent approval returns 404."""
    response = await client.get("/v1/security/approvals/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_approval_after_request(client: AsyncClient):
    """GET approval after request returns the approval details."""
    # Create an approval first
    create_resp = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "bash_exec",
            "tool_args": {"cmd": "rm -rf /tmp/test"},
            "agent_id": TEST_AGENT_ID,
            "session_id": "session-002",
            "reason": "Destructive command",
        },
    )
    assert create_resp.status_code == 201
    request_id = create_resp.json()["request_id"]

    response = await client.get(f"/v1/security/approvals/{request_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == request_id
    assert data["status"] == "pending"
    assert "token" not in data


# ---------------------------------------------------------------------------
# POST /v1/security/approvals/{request_id}/approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assigned_developer_can_approve_with_request_id(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_user,
    other_user,
):
    """An assigned non-owner developer can resolve a pending request."""
    await _set_roles(db_session, other_user, "DEVELOPER")
    other_user.plan = "FREE"
    db_session.add(other_user)
    await db_session.commit()
    create_resp = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_delete",
            "agent_id": TEST_AGENT_ID,
            "session_id": "session-003",
            "reviewer_id": str(other_user.id),
        },
    )
    assert create_resp.json()["reviewer_id"] == str(other_user.id)
    request_id = await _approval_request_id(
        db_session,
        test_user,
        create_resp.json()["request_id"],
    )
    reviewer_read = await other_user_client.get(
        f"/v1/security/approvals/{create_resp.json()['request_id']}"
    )
    reviewer_list = await other_user_client.get("/v1/security/approvals")

    response = await other_user_client.post(
        f"/v1/security/approvals/{request_id}/approve",
        json={"comment": "Looks safe"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert reviewer_read.status_code == 200
    assert reviewer_read.json()["owner_id"] == str(test_user.id)
    assert reviewer_read.json()["reviewer_id"] == str(other_user.id)
    assert reviewer_read.json()["can_resolve"] is True
    assert "token" not in reviewer_read.json()
    assert create_resp.json()["request_id"] in {item["request_id"] for item in reviewer_list.json()}
    assert all("token" not in item for item in reviewer_list.json())


@pytest.mark.asyncio
async def test_legacy_create_and_canonical_resolution_share_one_public_workflow(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_user,
    other_user,
):
    """Compatibility creation is immediately actionable through canonical routes."""
    await _set_roles(db_session, other_user, "DEVELOPER")
    other_user.plan = "FREE"
    db_session.add(other_user)
    await db_session.commit()

    created = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "outbound_message_send",
            "tool_args": {"recipient": "customer@example.com"},
            "agent_id": TEST_AGENT_ID,
            "session_id": "public-convergence-session",
            "reviewer_id": str(other_user.id),
            "reason": "Human review required",
        },
    )
    request_id = created.json()["request_id"]

    canonical = await other_user_client.get(f"/v1/approvals/{request_id}")
    resolved = await other_user_client.post(
        f"/v1/approvals/{request_id}/approve",
        json={"comment": "Approved through the canonical workflow"},
    )
    compatibility_read = await client.get(f"/v1/security/approvals/{request_id}")

    assert created.status_code == 201
    assert canonical.status_code == 200
    assert canonical.json()["owner_id"] == str(test_user.id)
    assert canonical.json()["reviewer_id"] == str(other_user.id)
    assert canonical.json()["can_resolve"] is True
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "APPROVED"
    assert resolved.json()["can_resolve"] is False
    assert compatibility_read.status_code == 200
    assert compatibility_read.json()["status"] == "approved"
    assert "token" not in compatibility_read.json()


@pytest.mark.asyncio
async def test_legacy_timeout_persists_expired_state_and_blocks_resolution(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    other_user,
):
    """Legacy timeout never leaves an actionable canonical PENDING record."""
    from sqlalchemy import update

    from src.api.models.approval import ApprovalRecord

    await _set_roles(db_session, other_user, "DEVELOPER")
    created = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "expired_action",
            "agent_id": TEST_AGENT_ID,
            "session_id": "expired-public-session",
            "reviewer_id": str(other_user.id),
            "timeout_minutes": 1,
        },
    )
    request_id = uuid.UUID(created.json()["request_id"])
    await db_session.execute(
        update(ApprovalRecord)
        .where(ApprovalRecord.id == request_id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(minutes=2))
    )
    await db_session.commit()

    compatibility_read = await other_user_client.get(f"/v1/security/approvals/{request_id}")
    canonical_read = await other_user_client.get(f"/v1/approvals/{request_id}")
    resolution = await other_user_client.post(
        f"/v1/security/approvals/{request_id}/approve",
        json={},
    )

    assert compatibility_read.status_code == 200
    assert compatibility_read.json()["status"] == "expired"
    assert compatibility_read.json()["can_resolve"] is False
    assert canonical_read.status_code == 200
    assert canonical_read.json()["status"] == "EXPIRED"
    assert canonical_read.json()["can_resolve"] is False
    assert resolution.status_code == 409


@pytest.mark.asyncio
async def test_approval_request_replay_is_rejected(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_user,
    other_user,
):
    """A terminal approval cannot be replayed with the same request ID."""
    await _set_roles(db_session, other_user, "DEVELOPER")
    create_resp = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_copy",
            "agent_id": TEST_AGENT_ID,
            "session_id": "session-004",
            "reviewer_id": str(other_user.id),
        },
    )
    request_id = await _approval_request_id(
        db_session,
        test_user,
        create_resp.json()["request_id"],
    )

    first = await other_user_client.post(
        f"/v1/security/approvals/{request_id}/approve",
        json={},
    )
    response = await other_user_client.post(
        f"/v1/security/approvals/{request_id}/approve",
        json={},
    )
    assert first.status_code == 200
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# POST /v1/security/approvals/{request_id}/deny
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assigned_developer_can_deny_request(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_user,
    other_user,
):
    """Deny a pending request returns 200."""
    await _set_roles(db_session, other_user, "DEVELOPER")
    create_resp = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "network_access",
            "agent_id": TEST_AGENT_ID,
            "session_id": "session-005",
            "reviewer_id": str(other_user.id),
        },
    )
    request_id = await _approval_request_id(
        db_session,
        test_user,
        create_resp.json()["request_id"],
    )

    response = await other_user_client.post(
        f"/v1/security/approvals/{request_id}/deny",
        json={"comment": "Too risky"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "denied"


# ---------------------------------------------------------------------------
# GET /v1/security/approvals  — list pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pending_approvals_exposes_no_resolution_secret(client: AsyncClient):
    """List pending approvals uses public request IDs and no resolution secret."""
    created = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "redacted-list-session",
        },
    )
    assert created.status_code == 201
    response = await client.get("/v1/security/approvals")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert response.json()
    assert all("token" not in item for item in response.json())


# ---------------------------------------------------------------------------
# GET /v1/security/receipts/{receipt_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_receipt_not_found(client: AsyncClient):
    """Non-existent receipt returns 404."""
    response = await client.get("/v1/security/receipts/nonexistent")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/security/receipts/session/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_receipts(client: AsyncClient):
    """Session receipts endpoint returns structured response."""
    response = await client.get("/v1/security/receipts/session/test-session")
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "count" in data
    assert "receipts" in data


# ---------------------------------------------------------------------------
# GET /v1/security/compliance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compliance_check(client: AsyncClient, db_session, test_user):
    """Compatibility route returns a local AARM-alignment gap report."""
    await _set_roles(db_session, test_user, "ADMIN")
    response = await client.get("/v1/security/compliance")
    assert response.status_code == 200
    data = response.json()
    assert "overall_satisfied" in data
    assert "version" in data
    assert "results" in data
    assert data["overall_satisfied"] is False
    assert data["summary"]["conformance_claim"] == "none"


# ---------------------------------------------------------------------------
# GET /v1/security/metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_metrics(client: AsyncClient, db_session, test_user):
    """Metrics endpoint returns governance counters."""
    await _set_roles(db_session, test_user, "ADMIN")
    response = await client.get("/v1/security/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "total_evaluations" in data
    assert "permits" in data
    assert "denials" in data
    assert "defers" in data


# ---------------------------------------------------------------------------
# GET /v1/security/metrics/prometheus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prometheus_metrics(client: AsyncClient, db_session, test_user):
    """Prometheus metrics returns plain text."""
    await _set_roles(db_session, test_user, "ADMIN")
    response = await client.get("/v1/security/metrics/prometheus")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /v1/security/sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_security_session(client: AsyncClient):
    """Create a security session returns session context."""
    response = await client.post(
        "/v1/security/sessions",
        params={"session_id": "sec-001", "agent_id": TEST_AGENT_ID},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "sec-001"
    assert "created_at" in data


# ---------------------------------------------------------------------------
# GET /v1/security/sessions/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_security_session_not_found(client: AsyncClient):
    """Non-existent security session returns 404."""
    response = await client.get("/v1/security/sessions/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_security_session_after_create(client: AsyncClient):
    """GET session after creating returns session summary."""
    await client.post(
        "/v1/security/sessions",
        params={"session_id": "sec-002", "agent_id": TEST_AGENT_ID},
    )
    response = await client.get("/v1/security/sessions/sec-002")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /v1/security/sessions/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_security_session(client: AsyncClient):
    """Close session returns 200 with closed status."""
    await client.post(
        "/v1/security/sessions",
        params={"session_id": "sec-003", "agent_id": TEST_AGENT_ID},
    )
    response = await client.delete("/v1/security/sessions/sec-003")
    assert response.status_code == 200
    assert response.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_close_security_session_not_found(client: AsyncClient):
    """Closing non-existent session returns 404."""
    response = await client.delete("/v1/security/sessions/nonexistent")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Authentication, roles, ownership, and durable state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_routes_require_authentication(client_no_auth: AsyncClient):
    """Both safe reads and mutations reject unauthenticated callers."""
    listed = await client_no_auth.get("/v1/security/approvals")
    created = await client_no_auth.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "unauthenticated-session",
        },
    )
    metrics = await client_no_auth.get("/v1/security/metrics")

    assert listed.status_code == 401
    assert created.status_code == 401
    assert metrics.status_code == 401


@pytest.mark.asyncio
async def test_viewer_can_read_owned_state_but_cannot_mutate(
    client: AsyncClient,
    db_session,
    test_user,
):
    approval = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "viewer-session",
        },
    )
    session = await client.post(
        "/v1/security/sessions",
        params={"session_id": "viewer-session", "agent_id": TEST_AGENT_ID},
    )
    assert approval.status_code == 201
    assert session.status_code == 200

    await _set_roles(db_session, test_user, "VIEWER")
    request_id = approval.json()["request_id"]
    request_id = await _approval_request_id(db_session, test_user, request_id)

    assert (await client.get(f"/v1/security/approvals/{request_id}")).status_code == 200
    assert (await client.get("/v1/security/approvals")).status_code == 200
    assert (await client.get("/v1/security/sessions/viewer-session")).status_code == 200

    evaluate = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "file_read",
            "agent_id": TEST_AGENT_ID,
            "session_id": "viewer-session",
        },
    )
    request = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "viewer-session",
        },
    )
    approve = await client.post(
        f"/v1/security/approvals/{request_id}/approve",
        json={},
    )
    close = await client.delete("/v1/security/sessions/viewer-session")

    assert evaluate.status_code == 403
    assert request.status_code == 403
    assert approve.status_code == 403
    assert close.status_code == 403


@pytest.mark.asyncio
async def test_caller_supplied_identity_fields_are_rejected(
    client: AsyncClient,
    db_session,
    test_user,
):
    supplied_user = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "identity-session",
            "user_id": "22222222-2222-4222-a222-222222222222",
            "owner_id": "22222222-2222-4222-a222-222222222222",
            "requester": "spoofed-requester@example.com",
        },
    )
    assert supplied_user.status_code == 422

    supplied_session_user = await client.post(
        "/v1/security/sessions",
        params={
            "session_id": "identity-session",
            "agent_id": TEST_AGENT_ID,
            "user_id": "22222222-2222-4222-a222-222222222222",
        },
    )
    assert supplied_session_user.status_code == 422

    created = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "identity-session",
        },
    )
    assert created.status_code == 201
    request_id = await _approval_request_id(
        db_session,
        test_user,
        created.json()["request_id"],
    )

    supplied_reviewer = await client.post(
        f"/v1/security/approvals/{request_id}/approve",
        json={"reviewer": "spoofed-reviewer@example.com"},
    )
    assert supplied_reviewer.status_code == 422
    status_response = await client.get(f"/v1/security/approvals/{created.json()['request_id']}")
    assert status_response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_requester_cannot_assign_themselves_as_reviewer(
    client: AsyncClient,
    test_user,
):
    response = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "self-assignment-session",
            "reviewer_id": str(test_user.id),
        },
    )

    assert response.status_code == 400
    assert "cannot be assigned" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reviewer_assignment_requires_persisted_reviewer_role(
    client: AsyncClient,
    other_user,
):
    response = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "viewer-assignment-session",
            "reviewer_id": str(other_user.id),
        },
    )

    assert response.status_code == 400
    assert "persisted reviewer role" in response.json()["detail"]


@pytest.mark.asyncio
async def test_owner_isolation_and_guessed_ids_fail_closed(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_user,
    other_user,
):
    created = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_delete",
            "agent_id": TEST_AGENT_ID,
            "session_id": "owner-session",
        },
    )
    await client.post(
        "/v1/security/sessions",
        params={"session_id": "owner-session", "agent_id": TEST_AGENT_ID},
    )
    await _set_roles(db_session, other_user, "DEVELOPER")

    request_id = created.json()["request_id"]
    request_id = await _approval_request_id(db_session, test_user, request_id)
    hidden_approval = await other_user_client.get(f"/v1/security/approvals/{request_id}")
    hidden_session = await other_user_client.get("/v1/security/sessions/owner-session")
    guessed_approval = await other_user_client.get(
        "/v1/security/approvals/aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
    )
    guessed_resolution = await other_user_client.post(
        f"/v1/security/approvals/{request_id}/approve",
        json={},
    )
    listed = await other_user_client.get("/v1/security/approvals")

    assert hidden_approval.status_code == 404
    assert hidden_session.status_code == 404
    assert guessed_approval.status_code == 404
    assert guessed_resolution.status_code == 404
    assert listed.status_code == 200
    assert listed.json() == []


@pytest.mark.asyncio
async def test_requester_cannot_resolve_own_approval_by_request_id(
    client: AsyncClient,
    db_session,
    test_user,
):
    created_session = await client.post(
        "/v1/security/sessions",
        params={
            "session_id": "developer-session",
            "agent_id": TEST_AGENT_ID,
        },
    )
    evaluated = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "file_read",
            "agent_id": TEST_AGENT_ID,
            "session_id": "developer-session",
        },
    )
    approval = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "developer-session",
        },
    )
    request_id = await _approval_request_id(
        db_session,
        test_user,
        approval.json()["request_id"],
    )
    resolved = await client.post(
        f"/v1/security/approvals/{request_id}/approve",
        json={"comment": "Authenticated review"},
    )
    closed = await client.delete("/v1/security/sessions/developer-session")

    assert created_session.status_code == 200
    assert evaluated.status_code == 200
    assert approval.status_code == 201
    assert resolved.status_code == 403
    assert "owners cannot resolve" in resolved.json()["detail"]
    approval_status = await client.get(f"/v1/security/approvals/{approval.json()['request_id']}")
    assert approval_status.json()["status"] == "pending"
    assert closed.status_code == 200


@pytest.mark.asyncio
async def test_admin_gets_global_visibility_and_operations(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_user,
    other_user,
    other_test_agent,
):
    own_approval = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "admin-owner-session",
        },
    )
    await _set_roles(db_session, other_user, "DEVELOPER")
    other_approval = await other_user_client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_delete",
            "agent_id": OTHER_AGENT_ID,
            "session_id": "other-owner-session",
        },
    )
    await other_user_client.post(
        "/v1/security/sessions",
        params={"session_id": "other-owner-session", "agent_id": OTHER_AGENT_ID},
    )
    other_request_id = await _approval_request_id(
        db_session,
        other_user,
        other_approval.json()["request_id"],
    )

    await _set_roles(db_session, test_user, "ADMIN")
    listed = await client.get("/v1/security/approvals")
    global_session = await client.get("/v1/security/sessions/other-owner-session")
    resolved = await client.post(
        f"/v1/security/approvals/{other_request_id}/deny",
        json={"comment": "Global admin review"},
    )
    metrics = await client.get("/v1/security/metrics")
    compliance = await client.get("/v1/security/compliance")

    listed_ids = {item["request_id"] for item in listed.json()}
    assert listed.status_code == 200
    assert own_approval.json()["request_id"] in listed_ids
    assert other_approval.json()["request_id"] in listed_ids
    assert all("token" not in item for item in listed.json())
    assert global_session.status_code == 200
    assert resolved.status_code == 200
    assert metrics.status_code == 200
    assert metrics.json()["pending_approvals"] == 1
    assert compliance.status_code == 200


@pytest.mark.asyncio
async def test_global_operations_reject_developer(client: AsyncClient):
    assert (await client.get("/v1/security/metrics")).status_code == 403
    assert (await client.get("/v1/security/metrics/prometheus")).status_code == 403
    assert (await client.get("/v1/security/compliance")).status_code == 403


@pytest.mark.asyncio
async def test_admin_metrics_aggregate_persisted_evaluations(
    client: AsyncClient,
    db_session,
    test_user,
):
    await client.post(
        "/v1/security/sessions",
        params={"session_id": "metrics-session", "agent_id": TEST_AGENT_ID},
    )
    evaluated = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "file_read",
            "agent_id": TEST_AGENT_ID,
            "session_id": "metrics-session",
        },
    )
    assert evaluated.status_code == 200

    await _set_roles(db_session, test_user, "ADMIN")
    metrics = await client.get("/v1/security/metrics")
    summary = await client.get("/v1/security/sessions/metrics-session")

    assert metrics.status_code == 200
    assert metrics.json()["total_evaluations"] == 1
    assert metrics.json()["active_sessions"] == 1
    assert metrics.json()["decisions_per_hour"] == 1
    assert summary.status_code == 200
    assert summary.json()["total_actions"] == 1


@pytest.mark.asyncio
async def test_evaluation_identity_and_provenance_are_persisted(
    client: AsyncClient,
    db_session,
):
    from sqlalchemy import select

    from src.api.models.security_state import SecurityEvaluation, SecurityReceipt

    evaluated = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "provenance_tool",
            "tool_args": {"resource": "report.txt"},
            "agent_id": TEST_AGENT_ID,
            "session_id": "provenance-session",
            "trigger": "test",
            "runtime": "pytest",
        },
    )
    assert evaluated.status_code == 200
    payload = evaluated.json()

    evaluation = (
        await db_session.execute(
            select(SecurityEvaluation).where(
                SecurityEvaluation.id == uuid.UUID(payload["evaluation_id"])
            )
        )
    ).scalar_one()
    receipt = (
        await db_session.execute(
            select(SecurityReceipt).where(SecurityReceipt.id == uuid.UUID(payload["receipt_id"]))
        )
    ).scalar_one()

    assert str(evaluation.action_id) == payload["action_id"]
    assert evaluation.action_hash == payload["action_hash"]
    assert str(evaluation.agent_id) == TEST_AGENT_ID
    assert evaluation.session_id == "provenance-session"
    assert evaluation.tool_name == "provenance_tool"
    assert evaluation.tool_args == {"resource": "report.txt"}
    assert evaluation.trigger == "test"
    assert evaluation.runtime == "pytest"
    assert receipt.evaluation_id == evaluation.id
    assert receipt.payload["action_id"] == payload["action_id"]
    assert receipt.payload["action_hash"] == payload["action_hash"]


@pytest.mark.asyncio
async def test_evaluation_signs_with_platform_key_before_receipt_persistence(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from sqlalchemy import select

    from src.api.models.security_state import SecurityReceipt
    from src.api.routes import security as security_routes
    from src.security.receipts import ActionReceipt, ReceiptGenerator

    key_id = "mutx-platform-api-test"
    private_key = bytes.fromhex("01" * 32)
    public_key = ReceiptGenerator.public_key_bytes(private_key)
    platform_generator = ReceiptGenerator(
        signing_private_key=private_key,
        signing_key_id=key_id,
        trusted_public_keys={key_id: public_key},
        signing_required=True,
    )
    monkeypatch.setattr(security_routes, "_receipt_generator", platform_generator)

    evaluated = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "signed_provenance_tool",
            "agent_id": TEST_AGENT_ID,
            "session_id": "signed-provenance-session",
        },
    )

    assert evaluated.status_code == 200
    receipt_record = (
        await db_session.execute(
            select(SecurityReceipt).where(
                SecurityReceipt.id == uuid.UUID(evaluated.json()["receipt_id"])
            )
        )
    ).scalar_one()
    receipt_payload = dict(receipt_record.payload)
    assert receipt_payload["signature"]
    assert receipt_payload["signer_key_id"] == key_id
    assert receipt_payload["signed_by"] == key_id
    assert receipt_payload["signed_by"] != public_key.hex()
    loaded_receipt = await client.get(f"/v1/security/receipts/{evaluated.json()['receipt_id']}")
    assert loaded_receipt.status_code == 200
    assert loaded_receipt.json()["signer_key_id"] == key_id

    receipt_payload["timestamp"] = datetime.fromisoformat(receipt_payload["timestamp"])
    independent_verifier = ReceiptGenerator(trusted_public_keys={key_id: public_key})
    assert independent_verifier.verify(ActionReceipt(**receipt_payload)) == (True, "")


@pytest.mark.asyncio
async def test_required_receipt_signing_failure_prevents_evaluation_persistence(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from sqlalchemy import func, select

    from src.api.models.security_state import SecurityEvaluation, SecurityReceipt
    from src.api.routes import security as security_routes
    from src.security.receipts import ReceiptGenerator

    monkeypatch.setattr(
        security_routes,
        "_receipt_generator",
        ReceiptGenerator(signing_required=True),
    )

    evaluated = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "unsigned_provenance_tool",
            "agent_id": TEST_AGENT_ID,
            "session_id": "unsigned-provenance-session",
        },
    )

    assert evaluated.status_code == 503
    assert evaluated.json()["detail"] == "Security receipt signing is unavailable"
    evaluation_count = int(
        (
            await db_session.execute(select(func.count()).select_from(SecurityEvaluation))
        ).scalar_one()
    )
    receipt_count = int(
        (await db_session.execute(select(func.count()).select_from(SecurityReceipt))).scalar_one()
    )
    assert evaluation_count == 0
    assert receipt_count == 0


@pytest.mark.asyncio
async def test_safe_reads_require_viewer_or_developer_and_admin_inherits(
    client: AsyncClient,
    db_session,
    test_user,
):
    created = await client.post(
        "/v1/security/sessions",
        params={"session_id": "role-session", "agent_id": TEST_AGENT_ID},
    )
    assert created.status_code == 200

    for roles in (("AUDIT_ADMIN",), ()):
        await _set_roles(db_session, test_user, *roles)
        assert (await client.get("/v1/security/sessions/role-session")).status_code == 403
        assert (await client.get("/v1/security/approvals")).status_code == 403
        assert (await client.get("/v1/security/receipts/session/role-session")).status_code == 403

    await _set_roles(db_session, test_user, "ADMIN")
    assert (await client.get("/v1/security/sessions/role-session")).status_code == 200


@pytest.mark.asyncio
async def test_agent_ids_must_exist_be_owned_and_match_the_session(
    client: AsyncClient,
    db_session,
    test_user,
    other_test_agent,
):
    from src.api.models.models import Agent, AgentStatus

    nonexistent_id = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
    cross_owner = await client.post(
        "/v1/security/sessions",
        params={"session_id": "cross-owner-agent", "agent_id": OTHER_AGENT_ID},
    )
    nonexistent = await client.post(
        "/v1/security/sessions",
        params={"session_id": "missing-agent", "agent_id": nonexistent_id},
    )
    assert cross_owner.status_code == 404
    assert nonexistent.status_code == 404

    second_agent_id = uuid.UUID("66666666-6666-4666-a666-666666666666")
    db_session.add(
        Agent(
            id=second_agent_id,
            name="second-security-agent",
            config="{}",
            user_id=test_user.id,
            status=AgentStatus.CREATING,
        )
    )
    await db_session.commit()
    assert (
        await client.post(
            "/v1/security/sessions",
            params={"session_id": "bound-session", "agent_id": TEST_AGENT_ID},
        )
    ).status_code == 200

    mismatched_evaluation = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "file_read",
            "agent_id": str(second_agent_id),
            "session_id": "bound-session",
        },
    )
    mismatched_approval = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": str(second_agent_id),
            "session_id": "bound-session",
        },
    )
    assert mismatched_evaluation.status_code == 409
    assert mismatched_approval.status_code == 409


@pytest.mark.asyncio
async def test_receipt_pagination_isolated_for_same_session_id_across_owners(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    other_user,
    other_test_agent,
):
    session_id = "shared-session-id"
    await _set_roles(db_session, other_user, "DEVELOPER")
    assert (
        await client.post(
            "/v1/security/sessions",
            params={"session_id": session_id, "agent_id": TEST_AGENT_ID},
        )
    ).status_code == 200
    assert (
        await other_user_client.post(
            "/v1/security/sessions",
            params={"session_id": session_id, "agent_id": OTHER_AGENT_ID},
        )
    ).status_code == 200

    owner_receipt_ids: set[str] = set()
    other_receipt_ids: set[str] = set()
    for index in range(3):
        owner = await client.post(
            "/v1/security/actions/evaluate",
            json={
                "tool_name": f"owner_tool_{index}",
                "agent_id": TEST_AGENT_ID,
                "session_id": session_id,
            },
        )
        other = await other_user_client.post(
            "/v1/security/actions/evaluate",
            json={
                "tool_name": f"other_tool_{index}",
                "agent_id": OTHER_AGENT_ID,
                "session_id": session_id,
            },
        )
        assert owner.status_code == 200
        assert other.status_code == 200
        owner_receipt_ids.add(owner.json()["receipt_id"])
        other_receipt_ids.add(other.json()["receipt_id"])

    page = await client.get(
        f"/v1/security/receipts/session/{session_id}",
        params={"limit": 2, "offset": 1},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert page.json()["count"] == 2
    assert {item["receipt_id"] for item in page.json()["receipts"]} <= owner_receipt_ids
    assert not ({item["receipt_id"] for item in page.json()["receipts"]} & other_receipt_ids)

    hidden = next(iter(other_receipt_ids))
    assert (await client.get(f"/v1/security/receipts/{hidden}")).status_code == 404


@pytest.mark.asyncio
async def test_receipts_are_filtered_by_recorded_owner(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    other_user,
):
    evaluated = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "file_read",
            "agent_id": TEST_AGENT_ID,
            "session_id": "receipt-owner-session",
        },
    )
    assert evaluated.status_code == 200
    receipt_id = evaluated.json()["receipt_id"]
    await _set_roles(db_session, other_user, "VIEWER")

    owner_read = await client.get(f"/v1/security/receipts/{receipt_id}")
    other_read = await other_user_client.get(f"/v1/security/receipts/{receipt_id}")
    other_session = await other_user_client.get(
        "/v1/security/receipts/session/receipt-owner-session"
    )

    assert owner_read.status_code == 200
    assert other_read.status_code == 404
    assert other_session.status_code == 200
    assert other_session.json()["receipts"] == []


@pytest.mark.asyncio
async def test_state_survives_new_app_instance_and_process_store_reset(
    client: AsyncClient,
    db_session,
    test_user,
    other_user,
):
    from httpx import ASGITransport

    from src.api.database import get_db
    from src.api.main import create_app
    from src.api.middleware.auth import get_current_user
    from src.api.routes import security as security_routes

    await _set_roles(db_session, other_user, "DEVELOPER")
    approval = await client.post(
        "/v1/security/approvals/request",
        json={
            "tool_name": "file_write",
            "agent_id": TEST_AGENT_ID,
            "session_id": "durable-session",
            "reviewer_id": str(other_user.id),
        },
    )
    session = await client.post(
        "/v1/security/sessions",
        params={"session_id": "durable-session", "agent_id": TEST_AGENT_ID},
    )
    evaluated = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "file_read",
            "agent_id": TEST_AGENT_ID,
            "session_id": "durable-session",
        },
    )
    assert approval.status_code == 201
    assert session.status_code == 200
    assert evaluated.status_code == 200
    request_id = await _approval_request_id(
        db_session,
        test_user,
        approval.json()["request_id"],
    )

    security_routes._context_accumulator._sessions.clear()
    security_routes._receipt_generator._receipts.clear()
    security_routes._receipt_generator._chains.clear()

    restarted_app = create_app(
        enable_lifespan=False,
        background_monitor_enabled=False,
        database_required_on_startup=False,
    )

    async def override_get_db():
        yield db_session

    current_principal = test_user

    async def override_get_current_user():
        return current_principal

    restarted_app.dependency_overrides[get_db] = override_get_db
    restarted_app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=restarted_app),
        base_url="http://test",
    ) as restarted_client:
        loaded_approval = await restarted_client.get(
            f"/v1/security/approvals/{approval.json()['request_id']}"
        )
        loaded_session = await restarted_client.get("/v1/security/sessions/durable-session")
        loaded_receipt = await restarted_client.get(
            f"/v1/security/receipts/{evaluated.json()['receipt_id']}"
        )
        loaded_receipts = await restarted_client.get(
            "/v1/security/receipts/session/durable-session"
        )
        current_principal = other_user
        resolved = await restarted_client.post(
            f"/v1/security/approvals/{request_id}/approve",
            json={},
        )

    assert loaded_approval.status_code == 200
    assert loaded_approval.json()["status"] == "pending"
    assert loaded_session.status_code == 200
    assert loaded_receipt.status_code == 200
    assert loaded_receipts.json()["receipts"][0]["receipt_id"] == evaluated.json()["receipt_id"]
    assert resolved.status_code == 200
