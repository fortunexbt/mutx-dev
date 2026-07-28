"""Approval workflow REST endpoints."""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import require_plan, require_roles
from src.api.config import get_settings
from src.api.database import get_db
from src.api.models import User
from src.api.services.approval import ApprovalRequest, ApprovalStatus
from src.api.services.approval_persistence import (
    ApprovalForbiddenError,
    ApprovalIdempotencyConflictError,
    ApprovalNotFoundError,
    ApprovalReviewerError,
    ApprovalTransitionConflictError,
    approval_request_from_record,
    create_approval_record,
    deliver_approval_notification,
    get_persisted_roles,
    get_visible_approval,
    list_eligible_reviewers,
    list_visible_approvals,
    resolve_approval,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])
logger = logging.getLogger(__name__)

# Approval mutations are a paid Autopilot capability. ``require_plan`` resolves
# the authenticated user from the database and checks persisted ``User.plan``;
# request payloads and token claims cannot grant this entitlement. Unknown or
# missing plans fail closed as Free. Reads intentionally remain available as a
# read-only preview.
require_paid_approval_plan = require_plan("starter")


async def require_paid_approval_developer(
    current_user: User = Depends(require_roles("DEVELOPER")),
    _paid_user: User = Depends(require_paid_approval_plan),
) -> User:
    """Require both a persisted developer role and the paid approval entitlement."""
    return current_user


class ApprovalCreate(BaseModel):
    """Payload for creating a new approval request."""

    agent_id: str
    session_id: str
    action_type: str
    payload: dict = Field(default_factory=dict)
    reviewer_id: uuid.UUID | None = None


class ApprovalResolve(BaseModel):
    """Optional comment when approving or rejecting."""

    comment: Optional[str] = None


class ApprovalListResponse(BaseModel):
    """Paginated response for listing approval requests."""

    items: list[ApprovalRequest] = Field(default_factory=list)
    total: int
    skip: int
    limit: int
    status: Optional[str] = None
    agent_id: Optional[str] = None


class EligibleReviewer(BaseModel):
    """Discoverable reviewer identity eligible for explicit assignment."""

    id: uuid.UUID
    email: str
    name: str
    roles: list[str] = Field(default_factory=list)


def _request_uuid(request_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(request_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found",
        ) from exc


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Approval request not found",
    )


@router.post("", response_model=ApprovalRequest, status_code=status.HTTP_201_CREATED)
async def create_approval(
    body: ApprovalCreate,
    idempotency_key: str | None = Header(
        None,
        alias="Idempotency-Key",
        max_length=255,
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_paid_approval_developer),
):
    """Submit and durably notify a new approval request."""
    webhook_url = getattr(get_settings(), "approval_webhook_url", None)
    try:
        created = await create_approval_record(
            db,
            owner=user,
            agent_id=body.agent_id,
            session_id=body.session_id,
            action_type=body.action_type,
            payload=body.payload,
            reviewer_id=body.reviewer_id,
            idempotency_key=idempotency_key,
            webhook_url=webhook_url,
        )
    except ApprovalIdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ApprovalReviewerError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # The approval and its outbox row are committed before any external I/O.
    # Replays can safely call this helper: DELIVERED and backoff-delayed events
    # cannot be claimed again.
    await deliver_approval_notification(db, approval_id=created.record.id)

    logger.info(
        "Approval request %s: id=%s agent_id=%s action=%s requester=%s",
        "replayed" if created.replayed else "created",
        created.record.id,
        created.record.agent_id,
        created.record.action_type,
        created.record.requester,
    )
    return approval_request_from_record(
        created.record,
        user_id=user.id,
        roles=await get_persisted_roles(db, user),
    )


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    status_filter: Optional[ApprovalStatus] = Query(None, alias="status"),
    agent_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """List owner-, reviewer-, or ADMIN-visible approval requests."""
    records, total = await list_visible_approvals(
        db,
        user=user,
        status_filter=status_filter,
        agent_id=agent_id,
        offset=skip,
        limit=limit,
    )
    roles = await get_persisted_roles(db, user)
    return ApprovalListResponse(
        items=[
            approval_request_from_record(record, user_id=user.id, roles=roles) for record in records
        ],
        total=total,
        skip=skip,
        limit=limit,
        status=status_filter,
        agent_id=agent_id,
    )


@router.get("/reviewers", response_model=list[EligibleReviewer])
async def get_eligible_reviewers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_paid_approval_developer),
):
    """List active non-owner users eligible for reviewer assignment."""
    reviewers = await list_eligible_reviewers(db, owner_id=user.id)
    return [
        EligibleReviewer(
            id=reviewer.id,
            email=reviewer.email,
            name=reviewer.name,
            roles=[
                role
                for role in (reviewer.roles if isinstance(reviewer.roles, list) else [])
                if isinstance(role, str)
            ],
        )
        for reviewer in reviewers
    ]


@router.get("/{request_id}", response_model=ApprovalRequest)
async def get_approval(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Fetch a single visible approval request by ID."""
    try:
        record = await get_visible_approval(db, request_id=_request_uuid(request_id), user=user)
    except ApprovalNotFoundError as exc:
        raise _not_found() from exc
    return approval_request_from_record(
        record,
        user_id=user.id,
        roles=await get_persisted_roles(db, user),
    )


async def _resolve_request(
    *,
    request_id: str,
    body: ApprovalResolve,
    db: AsyncSession,
    user: User,
    target_status: ApprovalStatus,
) -> ApprovalRequest:
    try:
        record = await resolve_approval(
            db,
            request_id=_request_uuid(request_id),
            user=user,
            target_status=target_status,
            comment=body.comment,
        )
    except ApprovalNotFoundError as exc:
        raise _not_found() from exc
    except ApprovalForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ApprovalTransitionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    logger.info(
        "Approval request resolved: id=%s status=%s approver=%s",
        request_id,
        target_status.value,
        user.email,
    )
    return approval_request_from_record(
        record,
        user_id=user.id,
        roles=await get_persisted_roles(db, user),
    )


@router.post("/{request_id}/approve", response_model=ApprovalRequest)
async def approve_request(
    request_id: str,
    body: ApprovalResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("DEVELOPER")),
):
    """Approve a pending request as a non-owner ADMIN or assigned DEVELOPER."""
    return await _resolve_request(
        request_id=request_id,
        body=body,
        db=db,
        user=user,
        target_status=ApprovalStatus.APPROVED,
    )


@router.post("/{request_id}/reject", response_model=ApprovalRequest)
async def reject_request(
    request_id: str,
    body: ApprovalResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("DEVELOPER")),
):
    """Reject a pending request as a non-owner ADMIN or assigned DEVELOPER."""
    return await _resolve_request(
        request_id=request_id,
        body=body,
        db=db,
        user=user,
        target_status=ApprovalStatus.REJECTED,
    )
