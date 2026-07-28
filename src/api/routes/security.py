"""
MUTX Security API Routes.

REST API for MUTX runtime-security capabilities. Legacy tenant state exposed
here is durably scoped to the authenticated principal. Global compliance and
metrics operations are restricted to ADMIN principals.

Informed by the AARM specification. The local check is not an AARM conformance
report and does not establish Core, Extended, or organizational conformance.
https://github.com/aarm-dev/docs/tree/8eff208b98786b2c9a578b26cb7eaca440ec4020

AARM documentation reference: MIT License, Copyright (c) 2023 Mintlify.
"""

from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import require_plan, require_roles
from src.api.config import get_settings
from src.api.database import get_db
from src.api.models import ApprovalRecord, User
from src.api.models.security_schemas import (
    ActionEvaluateRequest,
    ActionEvaluateResponse,
    ApprovalActionRequest,
    ApprovalActionResponse,
    ApprovalRequestCreate,
    ApprovalRequestResponse,
    ComplianceResponse,
    MetricsResponse,
    ReceiptResponse,
    SessionCloseResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionReceiptListResponse,
    SessionSummaryResponse,
)
from src.api.services.approval import ApprovalStatus
from src.api.services.approval_persistence import (
    ApprovalForbiddenError,
    ApprovalNotFoundError,
    ApprovalReviewerError,
    ApprovalTransitionConflictError,
    approval_request_from_record,
    create_approval_record,
    deliver_approval_notification,
    get_persisted_roles,
    get_visible_approval as get_visible_canonical_approval,
    list_visible_approvals,
    resolve_approval,
)
from src.api.services.governance_runtime import get_governance_runtime
from src.api.services.security_state import (
    SecurityStateConflictError,
    SecurityStateForbiddenError,
    SecurityStateNotFoundError,
    close_visible_session,
    create_or_replace_session,
    get_global_metrics,
    get_owned_action_context,
    get_visible_receipt,
    get_visible_session,
    list_visible_session_receipts,
    metrics_to_prometheus,
    record_evaluation,
    validate_approval_context,
)
from src.security import AARMComplianceChecker, NormalizedAction
from src.security.receipts import ReceiptSigningError

router = APIRouter(prefix="/security", tags=["security"])
SAFE_READ_ROLES = ("VIEWER", "DEVELOPER")
require_paid_approval_plan = require_plan("starter")


async def require_paid_security_approval_developer(
    current_user: User = Depends(require_roles("DEVELOPER")),
    _paid_user: User = Depends(require_paid_approval_plan),
) -> User:
    """Require paid ownership to create an approval, not to review one."""
    return current_user


# These components hold global policy/runtime instrumentation. Tenant-owned
# approval and session data is intentionally never read from their process-local
# stores by this router.
_governance = get_governance_runtime()
_mediator = _governance.mediator
_context_accumulator = _governance.context_accumulator
_policy_engine = _governance.policy_engine
_receipt_generator = _governance.receipt_generator
_telemetry_exporter = _governance.telemetry_exporter


def _not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found",
    )


@router.post("/actions/evaluate", response_model=ActionEvaluateResponse)
async def evaluate_action(
    request: ActionEvaluateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Evaluate an action without executing it and durably account for the result."""
    try:
        agent, context = await get_owned_action_context(
            db,
            user=current_user,
            agent_id=request.agent_id,
            session_id=request.session_id,
        )
    except SecurityStateNotFoundError as exc:
        raise _not_found("Agent or security session") from exc
    except SecurityStateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    action = NormalizedAction(
        tool_name=request.tool_name,
        tool_args=request.tool_args,
        agent_id=str(agent.id),
        session_id=request.session_id,
        user_id=str(current_user.id),
        trigger=request.trigger,
        runtime=request.runtime,
    )

    started_at = perf_counter()
    result = _policy_engine.evaluate(action, context)
    latency_ms = (perf_counter() - started_at) * 1000
    receipt = _receipt_generator.generate(
        action=action,
        context=context,
        decision=result,
        outcome="evaluated",
        outcome_detail="Dry-run policy evaluation",
        duration_ms=max(0, round(latency_ms)),
    )
    try:
        _receipt_generator.sign_for_persistence(receipt)
    except ReceiptSigningError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security receipt signing is unavailable",
        ) from exc
    try:
        evaluation_id, receipt_id = await record_evaluation(
            db,
            owner=current_user,
            action=action,
            result=result,
            receipt=receipt,
            latency_ms=latency_ms,
            receipt_verifier=_receipt_generator,
            require_verified_receipt=_receipt_generator.signing_required,
        )
    except SecurityStateNotFoundError as exc:
        raise _not_found("Agent or security session") from exc
    except SecurityStateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return ActionEvaluateResponse(
        decision=result.decision.value,
        rule_id=result.rule_id,
        rule_name=result.rule_name,
        reason=result.reason,
        would_modify=result.is_modified,
        evaluation_id=str(evaluation_id),
        receipt_id=str(receipt_id),
        action_id=action.id,
        action_hash=action.action_hash,
    )


@router.post(
    "/approvals/request",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_approval(
    request: ApprovalRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_paid_security_approval_developer),
):
    """Create a canonical durable approval owned by the authenticated principal."""
    try:
        await validate_approval_context(
            db,
            owner=current_user,
            agent_id=request.agent_id,
            session_id=request.session_id,
        )
        created = await create_approval_record(
            db,
            owner=current_user,
            agent_id=str(request.agent_id),
            session_id=request.session_id,
            action_type=request.tool_name,
            payload={
                "tool_args": request.tool_args,
                "reason": request.reason,
                "timeout_minutes": request.timeout_minutes,
                "source": "legacy_security",
            },
            reviewer_id=request.reviewer_id,
            idempotency_key=None,
            webhook_url=getattr(get_settings(), "approval_webhook_url", None),
        )
    except SecurityStateNotFoundError as exc:
        raise _not_found("Agent or security session") from exc
    except SecurityStateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ApprovalReviewerError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await deliver_approval_notification(db, approval_id=created.record.id)
    return await _legacy_approval_response(db, record=created.record, user=current_user)


async def _legacy_approval_response(
    db: AsyncSession,
    *,
    record: ApprovalRecord,
    user: User,
) -> ApprovalRequestResponse:
    """Render the legacy shape from the canonical record without secret tokens."""
    public = approval_request_from_record(
        record,
        user_id=user.id,
        roles=await get_persisted_roles(db, user),
    )
    payload = record.payload if isinstance(record.payload, dict) else {}
    timeout_minutes = payload.get("timeout_minutes", 5)
    if not isinstance(timeout_minutes, int) or not 1 <= timeout_minutes <= 60:
        timeout_minutes = 5
    expires_at = public.created_at + timedelta(minutes=timeout_minutes)
    status_value = str(public.status)
    legacy_status = {
        ApprovalStatus.PENDING.value: "pending",
        ApprovalStatus.APPROVED.value: "approved",
        ApprovalStatus.REJECTED.value: "denied",
        ApprovalStatus.EXPIRED.value: "expired",
    }.get(status_value, status_value.lower())
    remaining = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    if legacy_status == "pending" and remaining == 0:
        legacy_status = "expired"
    reason = payload.get("reason", "")
    return ApprovalRequestResponse(
        request_id=str(public.id),
        owner_id=str(public.owner_id),
        reviewer_id=str(public.reviewer_id) if public.reviewer_id else None,
        can_resolve=public.can_resolve,
        status=legacy_status,
        tool_name=public.action_type,
        reason=reason if isinstance(reason, str) else "",
        created_at=public.created_at.isoformat(),
        expires_at=expires_at.isoformat(),
        remaining_seconds=remaining,
    )


@router.get("/approvals/{request_id}", response_model=ApprovalRequestResponse)
async def get_approval(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*SAFE_READ_ROLES)),
):
    """Get an owner-visible approval, or any unambiguous approval as ADMIN."""
    try:
        approval = await get_visible_canonical_approval(
            db,
            user=current_user,
            request_id=uuid.UUID(request_id),
        )
        return await _legacy_approval_response(db, record=approval, user=current_user)
    except (ValueError, ApprovalNotFoundError) as exc:
        raise _not_found("Approval request") from exc


async def _resolve_request(
    *,
    request_id: str,
    request: ApprovalActionRequest,
    decision: str,
    db: AsyncSession,
    current_user: User,
) -> ApprovalActionResponse:
    try:
        approval = await resolve_approval(
            db,
            user=current_user,
            request_id=uuid.UUID(request_id),
            target_status=(
                ApprovalStatus.APPROVED if decision == "approved" else ApprovalStatus.REJECTED
            ),
            comment=request.comment,
        )
    except (ValueError, ApprovalNotFoundError) as exc:
        raise _not_found("Approval request") from exc
    except ApprovalTransitionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ApprovalForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ApprovalActionResponse(status=decision, request_id=str(approval.id))


@router.post(
    "/approvals/{request_id}/approve",
    response_model=ApprovalActionResponse,
    status_code=status.HTTP_200_OK,
)
async def approve_request(
    request_id: str,
    request: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Approve by request ID using the authenticated reviewer identity."""
    return await _resolve_request(
        request_id=request_id,
        request=request,
        decision="approved",
        db=db,
        current_user=current_user,
    )


@router.post(
    "/approvals/{request_id}/deny",
    response_model=ApprovalActionResponse,
    status_code=status.HTTP_200_OK,
)
async def deny_request(
    request_id: str,
    request: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Deny by request ID using the authenticated reviewer identity."""
    return await _resolve_request(
        request_id=request_id,
        request=request,
        decision="denied",
        db=db,
        current_user=current_user,
    )


@router.get("/approvals", response_model=list[ApprovalRequestResponse])
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*SAFE_READ_ROLES)),
):
    """List owner-scoped pending approvals; ADMIN receives the global list."""
    approvals, _ = await list_visible_approvals(
        db,
        user=current_user,
        status_filter=ApprovalStatus.PENDING,
        agent_id=None,
        offset=0,
        limit=1000,
    )
    return [
        await _legacy_approval_response(db, record=item, user=current_user) for item in approvals
    ]


@router.get("/receipts/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*SAFE_READ_ROLES)),
):
    """Get a durable receipt visible to the authenticated principal."""
    try:
        return ReceiptResponse(
            **await get_visible_receipt(db, user=current_user, receipt_id=receipt_id)
        )
    except SecurityStateNotFoundError as exc:
        raise _not_found("Receipt") from exc


@router.get("/receipts/session/{session_id}", response_model=SessionReceiptListResponse)
async def get_session_receipts(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*SAFE_READ_ROLES)),
):
    """Get an owner-filtered page of durable session receipts."""
    receipts, total = await list_visible_session_receipts(
        db,
        user=current_user,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return SessionReceiptListResponse(
        session_id=session_id,
        count=len(receipts),
        total=total,
        limit=limit,
        offset=offset,
        receipts=receipts,
    )


@router.get("/compliance", response_model=ComplianceResponse)
async def run_compliance_check(
    _current_user: User = Depends(require_roles("ADMIN")),
):
    """Run the genuinely global local capability check as ADMIN."""
    checker = AARMComplianceChecker(
        mediator=_mediator,
        context_accumulator=_context_accumulator,
        policy_engine=_policy_engine,
        approval_service=None,
        receipt_generator=_receipt_generator,
        telemetry_exporter=_telemetry_exporter,
    )
    report = checker.full_audit()
    return ComplianceResponse(
        overall_satisfied=report.overall_satisfied,
        version=report.version,
        checked_at=report.checked_at.isoformat(),
        summary=report.summary(),
        results=[
            {
                "requirement_id": result.requirement_id,
                "level": result.level.value,
                "description": result.description,
                "satisfied": result.satisfied,
                "details": result.details,
            }
            for result in report.results
        ],
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Get global metrics aggregated from durable state as ADMIN."""
    try:
        return await get_global_metrics(db, user=current_user)
    except SecurityStateForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required") from exc


@router.get("/metrics/prometheus", response_class=Response)
async def get_prometheus_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Get global durable metrics in Prometheus format as ADMIN."""
    try:
        metrics = await get_global_metrics(db, user=current_user)
    except SecurityStateForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required") from exc
    return PlainTextResponse(content=metrics_to_prometheus(metrics))


@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_200_OK)
async def create_session(
    request: Annotated[SessionCreateRequest, Query()],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Create or refresh a durable session owned by the authenticated principal."""
    try:
        session = await create_or_replace_session(
            db,
            owner=current_user,
            session_id=request.session_id,
            agent_id=request.agent_id,
            original_request=request.original_request,
            stated_intent=request.stated_intent,
        )
    except SecurityStateNotFoundError as exc:
        raise _not_found("Agent") from exc
    except SecurityStateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return SessionCreateResponse(
        session_id=session.session_id,
        agent_id=session.agent_id,
        created_at=session.created_at.astimezone(timezone.utc).isoformat(),
    )


@router.get("/sessions/{session_id}", response_model=SessionSummaryResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*SAFE_READ_ROLES)),
):
    """Get an owner-visible session, or any unambiguous session as ADMIN."""
    try:
        session = await get_visible_session(db, user=current_user, session_id=session_id)
    except SecurityStateNotFoundError as exc:
        raise _not_found("Session") from exc
    return SessionSummaryResponse(
        session_id=session.session_id,
        agent_id=session.agent_id,
        duration_seconds=max(
            0.0,
            (session.updated_at - session.created_at).total_seconds(),
        ),
        total_actions=session.total_actions,
        permits=session.permits,
        denials=session.denials,
        defers=session.defers,
        errors=session.errors,
        intent_alignment=session.intent_alignment,
    )


@router.delete("/sessions/{session_id}", response_model=SessionCloseResponse)
async def close_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Close an owner-visible session, or any unambiguous session as ADMIN."""
    try:
        session = await close_visible_session(db, user=current_user, session_id=session_id)
    except SecurityStateNotFoundError as exc:
        raise _not_found("Session") from exc
    return SessionCloseResponse(session_id=session.session_id, status="closed")
