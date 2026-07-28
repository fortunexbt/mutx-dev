"""
Approval workflow REST endpoints.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.database import get_db
from src.api.auth.dependencies import get_current_user
from src.api.models import User, UserSetting
from src.api.services.approval import ApprovalRequest, ApprovalService, ApprovalStatus

router = APIRouter(prefix="/approvals", tags=["approvals"])
logger = logging.getLogger(__name__)

APPROVER_ROLES = {"DEVELOPER", "ADMIN"}
APPROVAL_KEY_PREFIX = "approval.request."


def _has_approver_role(user: User) -> bool:
    role: Optional[str] = getattr(user, "role", None)
    return role in APPROVER_ROLES if role is not None else False


def _ensure_approval_visible(user: User, req: ApprovalRequest) -> None:
    if _has_approver_role(user):
        return
    if req.requester == user.email or req.approver == user.email:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Approval request is not visible to this user",
    )


def _approval_key(request_id: str) -> str:
    return f"{APPROVAL_KEY_PREFIX}{request_id}"


def _coerce_approval_request(value: object) -> ApprovalRequest | None:
    if not isinstance(value, dict):
        return None

    try:
        return ApprovalRequest.model_validate(value)
    except Exception:
        logger.warning("Skipping malformed approval record", extra={"value": value})
        return None


async def _load_approval_setting(
    db: AsyncSession,
    request_id: str,
) -> tuple[UserSetting, ApprovalRequest]:
    result = await db.execute(
        select(UserSetting).where(UserSetting.key == _approval_key(request_id))
    )
    setting = result.scalar_one_or_none()
    if setting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found",
        )

    approval = _coerce_approval_request(setting.value)
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored approval request is invalid",
        )

    return setting, approval


async def _count_approval_settings(db: AsyncSession) -> int:
    """Count total approval records in the user_settings table."""
    stmt = (
        select(func.count())
        .select_from(UserSetting)
        .where(UserSetting.key.like(f"{APPROVAL_KEY_PREFIX}%"))
    )
    return (await db.execute(stmt)).scalar_one()


async def _list_approval_settings(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[ApprovalRequest], int]:
    """Return a page of approval records plus the total count."""
    base_filter = UserSetting.key.like(f"{APPROVAL_KEY_PREFIX}%")

    total = (
        await db.execute(select(func.count()).select_from(UserSetting).where(base_filter))
    ).scalar_one()

    result = await db.execute(
        select(UserSetting)
        .where(base_filter)
        .order_by(UserSetting.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    approvals: list[ApprovalRequest] = []
    for setting in result.scalars().all():
        approval = _coerce_approval_request(setting.value)
        if approval is not None:
            approvals.append(approval)
    return approvals, total


class ApprovalCreate(BaseModel):
    """Payload for creating a new approval request."""

    agent_id: str
    session_id: str
    action_type: str
    payload: dict = {}


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


async def create_approval_record(
    body: ApprovalCreate,
    db: AsyncSession,
    user: User,
) -> ApprovalRequest:
    """Persist an approval request using the same path as the public route."""
    req = ApprovalRequest(
        agent_id=body.agent_id,
        session_id=body.session_id,
        action_type=body.action_type,
        payload=body.payload,
        requester=user.email,
    )

    db.add(
        UserSetting(
            user_id=user.id,
            key=_approval_key(str(req.id)),
            value=req.model_dump(mode="json"),
        )
    )
    await db.commit()

    webhook_url = getattr(get_settings(), "approval_webhook_url", None)
    if webhook_url:
        await ApprovalService._send_webhook(webhook_url, req)

    logger.info(
        "Approval request created: id=%s agent_id=%s action=%s requester=%s",
        req.id,
        req.agent_id,
        req.action_type,
        req.requester,
    )
    return req


@router.post("", response_model=ApprovalRequest, status_code=status.HTTP_201_CREATED)
async def create_approval(
    body: ApprovalCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Submit a new approval request.

    Stored in the existing user_settings table so approvals survive process restarts.
    """
    return await create_approval_record(body, db, user)


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    status_filter: Optional[ApprovalStatus] = Query(None, alias="status"),
    agent_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List approval requests visible to the authenticated user.

    - ``status``: filter by status (PENDING, APPROVED, REJECTED, EXPIRED).
      Omit to return all statuses.
    - ``agent_id``: filter by agent
    - ``skip`` / ``limit``: pagination controls
    """
    approvals, total = await _list_approval_settings(db, offset=skip, limit=limit)
    visible_results = []
    for req in approvals:
        if status_filter is not None and req.status != status_filter:
            continue
        if agent_id is not None and req.agent_id != agent_id:
            continue
        try:
            _ensure_approval_visible(user, req)
        except HTTPException:
            continue
        visible_results.append(req)

    return ApprovalListResponse(
        items=visible_results,
        total=total,
        skip=skip,
        limit=limit,
        status=status_filter,
        agent_id=agent_id,
    )


@router.get("/{request_id}", response_model=ApprovalRequest)
async def get_approval(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch a single approval request by ID."""
    _, req = await _load_approval_setting(db, request_id)
    _ensure_approval_visible(user, req)
    return req


@router.post("/{request_id}/approve", response_model=ApprovalRequest)
async def approve_request(
    request_id: str,
    body: ApprovalResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Approve a pending request.

    Requires DEVELOPER or ADMIN role unless the requester is approving their own request.
    """
    setting, approval = await _load_approval_setting(db, request_id)
    _ensure_approval_visible(user, approval)

    if not _has_approver_role(user) and approval.requester != user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requester or an approver role can approve this request",
        )

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve request in '{approval.status}' state",
        )

    approval.status = ApprovalStatus.APPROVED
    approval.approver = user.email
    approval.comment = body.comment
    approval.resolved_at = datetime.now(timezone.utc)
    setting.value = approval.model_dump(mode="json")
    await db.commit()

    logger.info("Approval request approved: id=%s approver=%s", request_id, user.email)
    return approval


@router.post("/{request_id}/reject", response_model=ApprovalRequest)
async def reject_request(
    request_id: str,
    body: ApprovalResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Reject a pending request.

    Requires DEVELOPER or ADMIN role unless the requester is rejecting their own request.
    """
    setting, approval = await _load_approval_setting(db, request_id)
    _ensure_approval_visible(user, approval)

    if not _has_approver_role(user) and approval.requester != user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requester or an approver role can reject this request",
        )

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject request in '{approval.status}' state",
        )

    approval.status = ApprovalStatus.REJECTED
    approval.approver = user.email
    approval.comment = body.comment
    approval.resolved_at = datetime.now(timezone.utc)
    setting.value = approval.model_dump(mode="json")
    await db.commit()

    logger.info("Approval request rejected: id=%s approver=%s", request_id, user.email)
    return approval
