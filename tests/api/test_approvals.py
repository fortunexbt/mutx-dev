"""Tests for the durable ``/v1/approvals`` workflow."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.database import Base
from src.api.models import ApprovalNotificationOutbox, ApprovalRecord, User, UserSetting
from src.api.services.approval import ApprovalStatus
from src.api.services.approval_persistence import (
    ApprovalTransitionConflictError,
    create_approval_record,
    resolve_approval,
)


# ------------------------------------------------------------------
# Route integration tests
# ------------------------------------------------------------------


class TestApprovalRoutes:
    """Integration tests for /v1/approvals routes."""

    @pytest_asyncio.fixture(autouse=True)
    async def paid_approval_users(self, db_session, test_user, other_user):
        """Route fixtures use the persisted Starter entitlement unless a test downgrades it."""
        test_user.plan = "STARTER"
        test_user.roles = ["DEVELOPER"]
        other_user.plan = "STARTER"
        db_session.add_all([test_user, other_user])
        await db_session.commit()

    @pytest_asyncio.fixture
    async def approval_service(self):
        """Compatibility fixture; canonical approval state is database scoped."""
        yield

    @pytest.mark.asyncio
    async def test_free_plan_is_read_only_even_with_paid_client_claims(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        approval_service,
    ):
        created = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-preview",
                "session_id": "session-preview",
                "action_type": "deploy",
                "payload": {},
            },
        )
        assert created.status_code == 201
        request_id = created.json()["id"]

        test_user.plan = "FREE"
        db_session.add(test_user)
        await db_session.commit()

        listed = await client.get("/v1/approvals")
        fetched = await client.get(f"/v1/approvals/{request_id}")
        create_denied = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-claimed-paid",
                "session_id": "session-claimed-paid",
                "action_type": "deploy",
                "plan": "STARTER",
                "payload": {"entitlement": {"plan": "starter"}},
            },
        )
        approve_denied = await client.post(
            f"/v1/approvals/{request_id}/approve",
            json={},
        )
        reject_denied = await client.post(
            f"/v1/approvals/{request_id}/reject",
            json={},
        )

        assert listed.status_code == 200
        assert listed.json()["items"][0]["id"] == request_id
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "PENDING"
        assert create_denied.status_code == 402
        assert approve_denied.status_code == 403
        assert reject_denied.status_code == 403
        assert create_denied.headers["upgrade-url"] == "/pricing"

    @pytest.mark.asyncio
    async def test_starter_plan_can_create_and_resolve_approval(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        other_user.roles = ["ADMIN"]
        db_session.add(other_user)
        await db_session.commit()
        created = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-starter",
                "session_id": "session-starter",
                "action_type": "deploy",
                "payload": {},
            },
        )
        resolved = await other_user_client.post(
            f"/v1/approvals/{created.json()['id']}/approve",
            json={"comment": "Starter entitlement is persisted"},
        )

        assert created.status_code == 201
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "APPROVED"

    @pytest.mark.asyncio
    async def test_assigned_free_reviewer_can_resolve_paid_owner_request(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        other_user.roles = ["DEVELOPER"]
        other_user.plan = "FREE"
        db_session.add(other_user)
        await db_session.commit()

        created = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-assigned-free-reviewer",
                "session_id": "session-assigned-free-reviewer",
                "action_type": "deploy",
                "reviewer_id": str(other_user.id),
                "payload": {},
            },
        )
        reviewer_view = await other_user_client.get(f"/v1/approvals/{created.json()['id']}")
        reviewer_creation_support = await other_user_client.get("/v1/approvals/reviewers")
        resolved = await other_user_client.post(
            f"/v1/approvals/{created.json()['id']}/approve",
            json={"comment": "Reviewer entitlement is assignment-based"},
        )

        assert created.status_code == 201
        assert reviewer_view.status_code == 200
        assert reviewer_view.json()["owner_id"] != str(other_user.id)
        assert reviewer_view.json()["reviewer_id"] == str(other_user.id)
        assert reviewer_view.json()["can_resolve"] is True
        assert reviewer_creation_support.status_code == 402
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "APPROVED"
        assert resolved.json()["can_resolve"] is False

    @pytest.mark.asyncio
    async def test_reviewer_discovery_returns_only_eligible_non_owner_users(
        self,
        client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        other_user.roles = ["DEVELOPER"]
        db_session.add(other_user)
        await db_session.commit()

        response = await client.get("/v1/approvals/reviewers")

        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(other_user.id),
                "email": other_user.email,
                "name": other_user.name,
                "roles": ["DEVELOPER"],
            }
        ]

    @pytest.mark.asyncio
    async def test_unknown_persisted_plan_fails_closed(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        approval_service,
    ):
        test_user.plan = "UNRECOGNIZED"
        db_session.add(test_user)
        await db_session.commit()

        response = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-no-entitlement",
                "session_id": "session-no-entitlement",
                "action_type": "deploy",
                "payload": {},
            },
        )

        assert response.status_code == 402

    @pytest.mark.asyncio
    async def test_approval_routes_require_authentication(
        self,
        client_no_auth: AsyncClient,
        approval_service,
    ):
        listed = await client_no_auth.get("/v1/approvals")
        created = await client_no_auth.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-unauthorized",
                "session_id": "session-unauthorized",
                "action_type": "deploy",
                "payload": {},
            },
        )
        approved = await client_no_auth.post(f"/v1/approvals/{uuid.uuid4()}/approve", json={})
        rejected = await client_no_auth.post(f"/v1/approvals/{uuid.uuid4()}/reject", json={})

        assert listed.status_code == 401
        assert created.status_code == 401
        assert approved.status_code == 401
        assert rejected.status_code == 401

    @pytest.mark.asyncio
    async def test_recording_approval_does_not_enable_enforcement_gate(
        self,
        client: AsyncClient,
        approval_service,
    ):
        before = await client.get("/v1/pico/progress")
        created = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-policy-independent",
                "session_id": "session-policy-independent",
                "action_type": "deploy",
                "payload": {},
            },
        )
        after = await client.get("/v1/pico/progress")

        assert before.status_code == 200
        assert created.status_code == 201
        assert after.status_code == 200
        assert before.json()["autopilot"]["approvalGateEnabled"] is False
        assert after.json()["autopilot"]["approvalGateEnabled"] is False
        assert after.json()["autopilot"]["approvalRequestIds"] == []

    @pytest.mark.asyncio
    async def test_create_approval(
        self,
        client: AsyncClient,
        test_user,
        approval_service,
    ):
        response = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-abc",
                "session_id": "session-xyz",
                "action_type": "deploy",
                "payload": {"target": "production"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["agent_id"] == "agent-abc"
        assert data["status"] == "PENDING"
        assert data["requester"] == test_user.email
        assert data["owner_id"] == str(test_user.id)
        assert data["reviewer_id"] is None
        assert data["can_resolve"] is False

    @pytest.mark.asyncio
    async def test_create_approval_persists_beyond_service_reset(
        self,
        client: AsyncClient,
        approval_service,
    ):
        create_resp = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-persist",
                "session_id": "session-persist",
                "action_type": "deploy",
                "payload": {"target": "production"},
            },
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["id"]

        fetch_resp = await client.get(f"/v1/approvals/{request_id}")
        assert fetch_resp.status_code == 200
        assert fetch_resp.json()["id"] == request_id
        assert fetch_resp.json()["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_get_approval(
        self,
        client: AsyncClient,
        approval_service,
    ):
        # Create first
        create_resp = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-get",
                "session_id": "session-get",
                "action_type": "query",
                "payload": {},
            },
        )
        request_id = create_resp.json()["id"]

        # Fetch
        response = await client.get(f"/v1/approvals/{request_id}")
        assert response.status_code == 200
        assert response.json()["id"] == request_id

    @pytest.mark.asyncio
    async def test_get_approval_not_found(
        self,
        client: AsyncClient,
        approval_service,
    ):
        response = await client.get(f"/v1/approvals/{uuid.uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_approvals_returns_pending(
        self,
        client: AsyncClient,
        approval_service,
    ):
        for i in range(3):
            await client.post(
                "/v1/approvals",
                json={
                    "agent_id": f"agent-list-{i}",
                    "session_id": f"session-list-{i}",
                    "action_type": "deploy",
                    "payload": {},
                },
            )

        response = await client.get("/v1/approvals")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 3
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_list_approvals_filter_by_status(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        other_user.roles = ["ADMIN"]
        db_session.add(other_user)
        await db_session.commit()
        create_resp = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-filter",
                "session_id": "session-filter",
                "action_type": "deploy",
                "payload": {},
            },
        )
        request_id = create_resp.json()["id"]

        # Approve it
        approved = await other_user_client.post(
            f"/v1/approvals/{request_id}/approve",
            json={"comment": "ok"},
        )
        assert approved.status_code == 200

        # Filter by APPROVED status
        response = await client.get("/v1/approvals?status=APPROVED")
        assert response.status_code == 200
        items = response.json()["items"]
        assert all(r["status"] == "APPROVED" for r in items)

        # Filter by PENDING status
        response = await client.get("/v1/approvals?status=PENDING")
        assert response.status_code == 200
        items = response.json()["items"]
        assert all(r["status"] == "PENDING" for r in items)

    @pytest.mark.asyncio
    async def test_list_approvals_filter_by_agent(
        self,
        client: AsyncClient,
        approval_service,
    ):
        await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-target",
                "session_id": "session-1",
                "action_type": "deploy",
                "payload": {},
            },
        )
        await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-other",
                "session_id": "session-2",
                "action_type": "deploy",
                "payload": {},
            },
        )

        response = await client.get("/v1/approvals?agent_id=agent-target")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["agent_id"] == "agent-target"

    @pytest.mark.asyncio
    async def test_list_filters_owner_and_query_before_counting_and_pagination(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        other_user,
        approval_service,
    ):
        owned_ids = []
        for index, agent_id in enumerate(["agent-target", "agent-other", "agent-target"]):
            response = await client.post(
                "/v1/approvals",
                json={
                    "agent_id": agent_id,
                    "session_id": f"owned-session-{index}",
                    "action_type": "deploy",
                    "payload": {},
                },
            )
            owned_ids.append(response.json()["id"])

        other_user.roles = ["DEVELOPER"]
        for index in range(4):
            response = await other_user_client.post(
                "/v1/approvals",
                json={
                    "agent_id": "agent-target",
                    "session_id": f"other-session-{index}",
                    "action_type": "deploy",
                    "payload": {},
                },
            )
            assert response.status_code == 201

        first_page = await client.get(
            "/v1/approvals?status=PENDING&agent_id=agent-target&skip=0&limit=1"
        )
        second_page = await client.get(
            "/v1/approvals?status=PENDING&agent_id=agent-target&skip=1&limit=1"
        )

        assert first_page.status_code == 200
        assert second_page.status_code == 200
        assert first_page.json()["total"] == 2
        assert second_page.json()["total"] == 2
        returned_ids = {
            first_page.json()["items"][0]["id"],
            second_page.json()["items"][0]["id"],
        }
        assert returned_ids == {owned_ids[0], owned_ids[2]}

    @pytest.mark.asyncio
    async def test_other_user_cannot_infer_or_resolve_owned_approval(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        approval_service,
    ):
        create_response = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-private",
                "session_id": "session-private",
                "action_type": "deploy",
                "payload": {},
            },
        )
        request_id = create_response.json()["id"]

        list_response = await other_user_client.get("/v1/approvals")
        get_response = await other_user_client.get(f"/v1/approvals/{request_id}")
        approve_response = await other_user_client.post(
            f"/v1/approvals/{request_id}/approve",
            json={},
        )
        reject_response = await other_user_client.post(
            f"/v1/approvals/{request_id}/reject",
            json={},
        )

        assert list_response.status_code == 200
        assert list_response.json()["items"] == []
        assert list_response.json()["total"] == 0
        assert get_response.status_code == 404
        assert approve_response.status_code == 403
        assert reject_response.status_code == 403

    @pytest.mark.asyncio
    async def test_approver_role_retains_cross_owner_access(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        create_response = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-reviewed",
                "session_id": "session-reviewed",
                "action_type": "deploy",
                "payload": {},
            },
        )
        request_id = create_response.json()["id"]
        other_user.roles = ["ADMIN"]
        db_session.add(other_user)
        await db_session.commit()

        list_response = await other_user_client.get("/v1/approvals?status=PENDING&limit=1")
        approve_response = await other_user_client.post(
            f"/v1/approvals/{request_id}/approve",
            json={"comment": "reviewed by admin"},
        )

        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert list_response.json()["items"][0]["id"] == request_id
        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "APPROVED"
        assert approve_response.json()["approver"] == other_user.email

    @pytest.mark.asyncio
    async def test_approve_request(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        create_resp = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-approve",
                "session_id": "session-approve",
                "action_type": "deploy",
                "payload": {},
            },
        )
        request_id = create_resp.json()["id"]

        other_user.roles = ["ADMIN"]
        db_session.add(other_user)
        await db_session.commit()

        response = await other_user_client.post(
            f"/v1/approvals/{request_id}/approve",
            json={"comment": "looks good"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "APPROVED"
        assert data["approver"] == other_user.email
        assert data["comment"] == "looks good"

    @pytest.mark.asyncio
    async def test_reject_request(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        other_user.roles = ["DEVELOPER"]
        db_session.add(other_user)
        await db_session.commit()
        create_resp = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-reject",
                "session_id": "session-reject",
                "action_type": "deploy",
                "payload": {},
                "reviewer_id": str(other_user.id),
            },
        )
        request_id = create_resp.json()["id"]

        response = await other_user_client.post(
            f"/v1/approvals/{request_id}/reject",
            json={"comment": "not ready"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "REJECTED"
        assert data["comment"] == "not ready"

    @pytest.mark.asyncio
    async def test_cannot_approve_already_approved(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        create_resp = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-double",
                "session_id": "session-double",
                "action_type": "deploy",
                "payload": {},
            },
        )
        request_id = create_resp.json()["id"]

        other_user.roles = ["ADMIN"]
        db_session.add(other_user)
        await db_session.commit()

        first_response = await other_user_client.post(
            f"/v1/approvals/{request_id}/approve", json={}
        )
        second_resp = await other_user_client.post(
            f"/v1/approvals/{request_id}/approve",
            json={"comment": "again"},
        )
        assert first_response.status_code == 200
        assert second_resp.status_code == 409
        assert "already in 'APPROVED' state" in second_resp.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("roles", [["VIEWER"], ["ADMIN"]])
    async def test_owner_cannot_resolve_own_request_with_any_persisted_role(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        roles,
        approval_service,
    ):
        created = await client.post(
            "/v1/approvals",
            json={
                "agent_id": f"agent-owner-{roles[0].lower()}",
                "session_id": "session-owner",
                "action_type": "deploy",
                "payload": {},
            },
        )
        request_id = created.json()["id"]

        test_user.roles = roles
        db_session.add(test_user)
        await db_session.commit()

        approved = await client.post(f"/v1/approvals/{request_id}/approve", json={})
        rejected = await client.post(f"/v1/approvals/{request_id}/reject", json={})

        assert approved.status_code == 403
        assert rejected.status_code == 403
        expected_detail = (
            "owners cannot resolve" if roles == ["ADMIN"] else "Insufficient permissions"
        )
        assert expected_detail in approved.json()["detail"]

    @pytest.mark.asyncio
    async def test_transient_admin_attribute_does_not_grant_global_scope(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        created = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-transient-role",
                "session_id": "session-transient-role",
                "action_type": "deploy",
                "payload": {},
            },
        )
        other_user.role = "ADMIN"
        other_user.roles = ["ADMIN"]

        listed = await other_user_client.get("/v1/approvals")
        fetched = await other_user_client.get(f"/v1/approvals/{created.json()['id']}")
        resolved = await other_user_client.post(
            f"/v1/approvals/{created.json()['id']}/approve", json={}
        )

        assert other_user.roles == ["VIEWER"]
        assert listed.json()["total"] == 0
        assert fetched.status_code == 404
        assert resolved.status_code == 403
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_persisted_developer_has_no_unassigned_cross_user_scope(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        other_user.roles = ["DEVELOPER"]
        db_session.add(other_user)
        await db_session.commit()
        created = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-developer-private",
                "session_id": "session-developer-private",
                "action_type": "deploy",
                "payload": {},
            },
        )
        request_id = created.json()["id"]

        listed = await other_user_client.get("/v1/approvals")
        fetched = await other_user_client.get(f"/v1/approvals/{request_id}")
        resolved = await other_user_client.post(f"/v1/approvals/{request_id}/approve", json={})

        assert listed.json()["total"] == 0
        assert fetched.status_code == 404
        assert resolved.status_code == 404

    @pytest.mark.asyncio
    async def test_explicit_persisted_developer_assignment_grants_scoped_review(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        db_session,
        other_user,
        approval_service,
    ):
        other_user.roles = ["DEVELOPER"]
        db_session.add(other_user)
        await db_session.commit()
        created = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-assigned-reviewer",
                "session_id": "session-assigned-reviewer",
                "action_type": "deploy",
                "payload": {},
                "reviewer_id": str(other_user.id),
            },
        )
        request_id = created.json()["id"]

        listed = await other_user_client.get("/v1/approvals")
        approved = await other_user_client.post(
            f"/v1/approvals/{request_id}/approve",
            json={"comment": "assigned review"},
        )

        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["id"] == request_id
        assert approved.status_code == 200
        assert approved.json()["status"] == "APPROVED"

    @pytest.mark.asyncio
    async def test_viewer_cannot_be_assigned_as_reviewer(
        self,
        client: AsyncClient,
        other_user,
        approval_service,
    ):
        response = await client.post(
            "/v1/approvals",
            json={
                "agent_id": "agent-viewer-reviewer",
                "session_id": "session-viewer-reviewer",
                "action_type": "deploy",
                "payload": {},
                "reviewer_id": str(other_user.id),
            },
        )

        assert response.status_code == 400
        assert "persisted reviewer role" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_ignores_malformed_legacy_user_setting(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        approval_service,
    ):
        db_session.add(
            UserSetting(
                user_id=test_user.id,
                key=f"approval.request.{uuid.uuid4()}",
                value="{malformed-json",
            )
        )
        await db_session.commit()

        response = await client.get("/v1/approvals")

        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_idempotency_key_replays_same_request_and_rejects_mismatch(
        self,
        client: AsyncClient,
        db_session,
        approval_service,
    ):
        body = {
            "agent_id": "agent-idempotent",
            "session_id": "session-idempotent",
            "action_type": "deploy",
            "payload": {"target": "production"},
        }
        headers = {"Idempotency-Key": "approval-create-1"}

        first = await client.post("/v1/approvals", json=body, headers=headers)
        replay = await client.post("/v1/approvals", json=body, headers=headers)
        mismatch = await client.post(
            "/v1/approvals",
            json={**body, "payload": {"target": "staging"}},
            headers=headers,
        )
        count = (
            await db_session.execute(select(func.count()).select_from(ApprovalRecord))
        ).scalar_one()

        assert first.status_code == replay.status_code == 201
        assert first.json()["id"] == replay.json()["id"]
        assert mismatch.status_code == 409
        assert "different approval request" in mismatch.json()["detail"]
        assert count == 1

    @pytest.mark.asyncio
    async def test_idempotency_key_is_scoped_per_owner(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        other_user,
        approval_service,
    ):
        body = {
            "agent_id": "agent-owner-key",
            "session_id": "session-owner-key",
            "action_type": "deploy",
            "payload": {},
        }
        headers = {"Idempotency-Key": "shared-owner-key"}

        other_user.roles = ["DEVELOPER"]
        first = await client.post("/v1/approvals", json=body, headers=headers)
        second = await other_user_client.post("/v1/approvals", json=body, headers=headers)

        assert first.status_code == second.status_code == 201
        assert first.json()["id"] != second.json()["id"]

    @pytest.mark.asyncio
    async def test_webhook_success_is_not_emitted_again_on_idempotent_retry(
        self,
        client: AsyncClient,
        db_session,
        monkeypatch,
        approval_service,
    ):
        from src.api.routes import approvals as approval_routes

        calls = []
        persisted_before_delivery = []

        async def fake_post(url, payload, *, delivery_id=None):
            calls.append((url, payload, delivery_id))
            approval_count = (
                await db_session.execute(select(func.count()).select_from(ApprovalRecord))
            ).scalar_one()
            outbox_count = (
                await db_session.execute(
                    select(func.count()).select_from(ApprovalNotificationOutbox)
                )
            ).scalar_one()
            persisted_before_delivery.append((approval_count, outbox_count))

        monkeypatch.setattr(
            approval_routes,
            "get_settings",
            lambda: SimpleNamespace(approval_webhook_url="https://webhook.invalid/approval"),
        )
        monkeypatch.setattr(
            "src.api.services.approval_persistence.post_approval_webhook",
            fake_post,
        )
        body = {
            "agent_id": "agent-webhook-once",
            "session_id": "session-webhook-once",
            "action_type": "deploy",
            "payload": {},
        }
        headers = {"Idempotency-Key": "webhook-once"}

        first = await client.post("/v1/approvals", json=body, headers=headers)
        replay = await client.post("/v1/approvals", json=body, headers=headers)
        delivery = (
            await db_session.execute(
                select(
                    ApprovalNotificationOutbox.status,
                    ApprovalNotificationOutbox.attempt_count,
                )
            )
        ).one()

        assert first.json()["id"] == replay.json()["id"]
        assert len(calls) == 1
        assert persisted_before_delivery == [(1, 1)]
        assert delivery == ("DELIVERED", 1)
        assert calls[0][2] is not None

    @pytest.mark.asyncio
    async def test_failed_webhook_retry_reuses_outbox_without_duplicate_record(
        self,
        client: AsyncClient,
        db_session,
        monkeypatch,
        approval_service,
    ):
        from src.api.routes import approvals as approval_routes

        calls = []

        async def flaky_post(url, payload, *, delivery_id=None):
            calls.append(delivery_id)
            if len(calls) == 1:
                raise RuntimeError("temporary webhook failure")

        monkeypatch.setattr(
            approval_routes,
            "get_settings",
            lambda: SimpleNamespace(approval_webhook_url="https://webhook.invalid/approval"),
        )
        monkeypatch.setattr(
            "src.api.services.approval_persistence.post_approval_webhook",
            flaky_post,
        )
        body = {
            "agent_id": "agent-webhook-retry",
            "session_id": "session-webhook-retry",
            "action_type": "deploy",
            "payload": {},
        }
        headers = {"Idempotency-Key": "webhook-retry"}

        first = await client.post("/v1/approvals", json=body, headers=headers)
        failed = (
            await db_session.execute(
                select(
                    ApprovalNotificationOutbox.status,
                    ApprovalNotificationOutbox.attempt_count,
                )
            )
        ).one()
        await db_session.execute(
            update(ApprovalNotificationOutbox).values(
                next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1)
            )
        )
        await db_session.commit()

        replay = await client.post("/v1/approvals", json=body, headers=headers)
        delivered = (
            await db_session.execute(
                select(
                    ApprovalNotificationOutbox.status,
                    ApprovalNotificationOutbox.attempt_count,
                )
            )
        ).one()
        record_count = (
            await db_session.execute(select(func.count()).select_from(ApprovalRecord))
        ).scalar_one()

        assert first.status_code == replay.status_code == 201
        assert first.json()["id"] == replay.json()["id"]
        assert failed == ("FAILED", 1)
        assert delivered == ("DELIVERED", 2)
        assert len(calls) == 2
        assert len(set(calls)) == 1
        assert record_count == 1


@pytest.mark.asyncio
async def test_concurrent_terminal_transitions_have_one_winner(tmp_path):
    database_path = tmp_path / "approval-race.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 10},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner_id = uuid.uuid4()
    first_admin_id = uuid.uuid4()
    second_admin_id = uuid.uuid4()

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with sessions() as session:
            owner = User(
                id=owner_id,
                email="race-owner@example.com",
                name="Race Owner",
                plan="STARTER",
                roles=["VIEWER"],
            )
            session.add_all(
                [
                    owner,
                    User(
                        id=first_admin_id,
                        email="race-admin-1@example.com",
                        name="Race Admin One",
                        plan="STARTER",
                        roles=["ADMIN"],
                    ),
                    User(
                        id=second_admin_id,
                        email="race-admin-2@example.com",
                        name="Race Admin Two",
                        plan="STARTER",
                        roles=["ADMIN"],
                    ),
                ]
            )
            await session.commit()
            created = await create_approval_record(
                session,
                owner=owner,
                agent_id="agent-race",
                session_id="session-race",
                action_type="deploy",
                payload={},
                reviewer_id=None,
                idempotency_key=None,
                webhook_url=None,
            )
            request_id = created.record.id

        async def transition(admin_id, target_status):
            async with sessions() as session:
                admin = (
                    await session.execute(select(User).where(User.id == admin_id))
                ).scalar_one()
                return await resolve_approval(
                    session,
                    request_id=request_id,
                    user=admin,
                    target_status=target_status,
                    comment=target_status.value.lower(),
                )

        results = await asyncio.gather(
            transition(first_admin_id, ApprovalStatus.APPROVED),
            transition(second_admin_id, ApprovalStatus.REJECTED),
            return_exceptions=True,
        )
        successes = [result for result in results if isinstance(result, ApprovalRecord)]
        conflicts = [
            result for result in results if isinstance(result, ApprovalTransitionConflictError)
        ]

        async with sessions() as session:
            stored_status = (
                await session.execute(
                    select(ApprovalRecord.status).where(ApprovalRecord.id == request_id)
                )
            ).scalar_one()

        assert len(successes) == 1
        assert len(conflicts) == 1
        assert stored_status == successes[0].status
        assert conflicts[0].current_status == stored_status
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_idempotent_creates_persist_one_request(tmp_path):
    database_path = tmp_path / "approval-idempotency-race.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 10},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner_id = uuid.uuid4()

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add(
                User(
                    id=owner_id,
                    email="idempotency-race-owner@example.com",
                    name="Idempotency Race Owner",
                    plan="STARTER",
                    roles=["VIEWER"],
                )
            )
            await session.commit()

        async def create_once():
            async with sessions() as session:
                owner = (
                    await session.execute(select(User).where(User.id == owner_id))
                ).scalar_one()
                return await create_approval_record(
                    session,
                    owner=owner,
                    agent_id="agent-idempotency-race",
                    session_id="session-idempotency-race",
                    action_type="deploy",
                    payload={"target": "production"},
                    reviewer_id=None,
                    idempotency_key="concurrent-create",
                    webhook_url=None,
                )

        first, second = await asyncio.gather(create_once(), create_once())

        async with sessions() as session:
            count = (
                await session.execute(select(func.count()).select_from(ApprovalRecord))
            ).scalar_one()

        assert first.record.id == second.record.id
        assert {first.replayed, second.replayed} == {False, True}
        assert count == 1
    finally:
        await engine.dispose()
