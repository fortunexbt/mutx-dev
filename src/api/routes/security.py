"""
MUTX Security API Routes.

REST API for MUTX runtime-security capabilities.

Routes:
- POST   /v1/security/actions/evaluate        - Evaluate action without executing
- POST   /v1/security/approvals/request    - Request human approval
- POST   /v1/security/approvals/{id}/approve - Approve deferred action
- POST   /v1/security/approvals/{id}/deny   - Deny deferred action
- GET    /v1/security/approvals/{id}        - Get approval status
- GET    /v1/security/receipts/{id}         - Get action receipt
- GET    /v1/security/compliance             - Run local AARM-alignment checks
- GET    /v1/security/metrics               - Get governance metrics

Informed by the AARM specification. The local check is not an AARM conformance
report and does not establish Core, Extended, or organizational conformance.
https://github.com/aarm-dev/docs/tree/8eff208b98786b2c9a578b26cb7eaca440ec4020

AARM documentation reference: MIT License, Copyright (c) 2023 Mintlify.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from src.api.auth.dependencies import get_current_user
from src.api.models import User
from src.api.services.governance_runtime import get_governance_runtime
from src.security import (
    AARMComplianceChecker,
    NormalizedAction,
)
from src.security.telemetry import TelemetryEventType

router = APIRouter(prefix="/security", tags=["security"])


_governance = get_governance_runtime()
_mediator = _governance.mediator
_context_accumulator = _governance.context_accumulator
_policy_engine = _governance.policy_engine
_approval_service = _governance.approval_service
_receipt_generator = _governance.receipt_generator
_telemetry_exporter = _governance.telemetry_exporter


class ActionEvaluateRequest(BaseModel):
    """Request to evaluate an action without executing."""

    tool_name: str = Field(..., description="Name of the tool")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    agent_id: str = Field(..., description="Agent ID")
    session_id: str = Field(..., description="Session ID")
    user_id: Optional[str] = Field(default=None, description="User ID")
    trigger: str = Field(default="manual", description="What triggered this")
    runtime: str = Field(default="mutx", description="Runtime identifier")


class ActionEvaluateResponse(BaseModel):
    """Response from action evaluation."""

    decision: str
    rule_id: Optional[str] = None
    rule_name: Optional[str] = None
    reason: str
    would_modify: bool = False
    action_id: str
    action_hash: str


class ApprovalRequestCreate(BaseModel):
    """Request human approval for an action."""

    tool_name: str = Field(..., description="Name of the tool")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    agent_id: str = Field(..., description="Agent ID")
    session_id: str = Field(..., description="Session ID")
    user_id: Optional[str] = Field(default=None, description="User ID")
    reason: str = Field(default="", description="Why approval is needed")
    timeout_minutes: int = Field(default=5, ge=1, le=60, description="Timeout in minutes")


class ApprovalRequestResponse(BaseModel):
    """Response for approval request."""

    request_id: str
    token: str
    status: str
    tool_name: str
    reason: str
    created_at: str
    expires_at: str
    remaining_seconds: int


class ApprovalActionRequest(BaseModel):
    """Approve or deny a request."""

    reviewer: str = Field(..., description="Who is approving/denying")
    comment: str = Field(default="", description="Optional comment")


class ComplianceResponse(BaseModel):
    """Backward-compatible local AARM-alignment check response."""

    overall_satisfied: bool
    version: str
    checked_at: str
    summary: dict[str, Any]
    results: list[dict[str, Any]]


class ApprovalActionResponse(BaseModel):
    """Response for approve/deny action on an approval request."""

    status: str
    request_id: str


class ReceiptActionModel(BaseModel):
    """Action summary within a receipt."""

    id: str = ""
    tool_name: str = ""
    action_hash: str = ""
    timestamp: str = ""
    effect: str = ""


class ReceiptResponse(BaseModel):
    """Response for a single action receipt."""

    receipt_version: str = "1.0"
    receipt_id: str = ""
    action_id: str = ""
    action_hash: str = ""
    session_id: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = Field(default_factory=dict)
    agent_id: str = ""
    user_id: str = ""
    policy_decision: str = ""
    policy_rule_id: Optional[str] = None
    policy_rule_name: Optional[str] = None
    decision_reason: str = ""
    outcome: str = ""
    outcome_detail: str = ""
    timestamp: str = ""
    duration_ms: Optional[int] = None
    session_snapshot: Optional[dict[str, Any]] = None
    prior_action_hashes: list[str] = Field(default_factory=list)
    signature: Optional[str] = None
    signed_by: Optional[str] = None
    signature_algorithm: Optional[str] = None
    signing_key_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionReceiptListResponse(BaseModel):
    """Response for listing receipts in a session."""

    session_id: str
    count: int
    receipts: list[dict[str, Any]] = Field(default_factory=list)


class SessionCreateResponse(BaseModel):
    """Response for creating a security session."""

    session_id: str
    agent_id: str
    created_at: str


class SessionSummaryResponse(BaseModel):
    """Response for getting a session summary."""

    session_id: str
    agent_id: str
    duration_seconds: float = 0.0
    total_actions: int = 0
    permits: int = 0
    denials: int = 0
    defers: int = 0
    errors: int = 0
    intent_alignment: str = "unknown"


class SessionCloseResponse(BaseModel):
    """Response for closing a session."""

    session_id: str
    status: str


class MetricsResponse(BaseModel):
    """Governance metrics response."""

    total_evaluations: int
    permits: int
    denials: int
    defers: int
    pending_approvals: int
    intent_drifts: int
    active_sessions: int
    avg_latency_ms: float
    decisions_per_minute: int
    decisions_per_hour: int


@router.post("/actions/evaluate", response_model=ActionEvaluateResponse)
async def evaluate_action(
    request: ActionEvaluateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Evaluate an action against policy without executing.

    This endpoint allows you to check what the policy decision would be
    for a given action without actually executing it.
    """
    action = NormalizedAction(
        tool_name=request.tool_name,
        tool_args=request.tool_args,
        agent_id=request.agent_id,
        session_id=request.session_id,
        user_id=request.user_id or str(current_user.id),
        trigger=request.trigger,
        runtime=request.runtime,
    )

    context = _context_accumulator.get_context(request.session_id)
    result = _policy_engine.evaluate(action, context)

    return ActionEvaluateResponse(
        decision=result.decision.value,
        rule_id=result.rule_id,
        rule_name=result.rule_name,
        reason=result.reason,
        would_modify=result.is_modified,
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
    current_user: User = Depends(get_current_user),
):
    """
    Request human approval for a deferred action.

    Creates an approval request that can be approved or denied via
    the approve/deny endpoints.
    """
    action = NormalizedAction(
        tool_name=request.tool_name,
        tool_args=request.tool_args,
        agent_id=request.agent_id,
        session_id=request.session_id,
        user_id=request.user_id or str(current_user.id),
    )

    approval_request = _approval_service.request_approval(
        action=action,
        reason=request.reason,
        timeout_minutes=request.timeout_minutes,
    )

    _telemetry_exporter.export_approval_event(
        event_type=TelemetryEventType.APPROVAL_REQUESTED,
        request_id=approval_request.id,
        token=approval_request.token,
        reviewer="",
        tool_name=request.tool_name,
        agent_id=request.agent_id,
        session_id=request.session_id,
    )

    return ApprovalRequestResponse(
        request_id=approval_request.id,
        token=approval_request.token,
        status=approval_request.status.value,
        tool_name=approval_request.tool_name,
        reason=approval_request.reason,
        created_at=approval_request.created_at.isoformat(),
        expires_at=approval_request.expires_at.isoformat(),
        remaining_seconds=approval_request.remaining_seconds,
    )


@router.get("/approvals/{request_id}", response_model=ApprovalRequestResponse)
async def get_approval(
    request_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get the status of an approval request."""
    approval_request = _approval_service.get_request(request_id)

    if not approval_request:
        raise HTTPException(status_code=404, detail="Approval request not found")

    return ApprovalRequestResponse(
        request_id=approval_request.id,
        token=approval_request.token,
        status=approval_request.status.value,
        tool_name=approval_request.tool_name,
        reason=approval_request.reason,
        created_at=approval_request.created_at.isoformat(),
        expires_at=approval_request.expires_at.isoformat(),
        remaining_seconds=approval_request.remaining_seconds,
    )


@router.post(
    "/approvals/{token}/approve",
    response_model=ApprovalActionResponse,
    status_code=status.HTTP_200_OK,
)
async def approve_request(
    token: str,
    request: ApprovalActionRequest,
    current_user: User = Depends(get_current_user),
):
    """Approve a pending request."""
    success = _approval_service.approve(token, reviewer=request.reviewer, comment=request.comment)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Request not found or not pending",
        )

    approval_request = _approval_service.get_by_token(token)

    _telemetry_exporter.export_approval_event(
        event_type=TelemetryEventType.APPROVAL_APPROVED,
        request_id=approval_request.id,
        token=token,
        reviewer=request.reviewer,
        tool_name=approval_request.tool_name,
        agent_id=approval_request.agent_id,
        session_id=approval_request.session_id,
        comment=request.comment,
    )

    return ApprovalActionResponse(
        status="approved",
        request_id=approval_request.id,
    )


@router.post(
    "/approvals/{token}/deny",
    response_model=ApprovalActionResponse,
    status_code=status.HTTP_200_OK,
)
async def deny_request(
    token: str,
    request: ApprovalActionRequest,
    current_user: User = Depends(get_current_user),
):
    """Deny a pending request."""
    success = _approval_service.deny(token, reviewer=request.reviewer, reason=request.comment)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Request not found or not pending",
        )

    approval_request = _approval_service.get_by_token(token)

    _telemetry_exporter.export_approval_event(
        event_type=TelemetryEventType.APPROVAL_DENIED,
        request_id=approval_request.id,
        token=token,
        reviewer=request.reviewer,
        tool_name=approval_request.tool_name,
        agent_id=approval_request.agent_id,
        session_id=approval_request.session_id,
        comment=request.comment,
    )

    return ApprovalActionResponse(
        status="denied",
        request_id=approval_request.id,
    )


@router.get("/approvals", response_model=list[ApprovalRequestResponse])
async def list_pending_approvals(
    current_user: User = Depends(get_current_user),
):
    """List all pending approval requests."""
    pending = _approval_service.list_pending()

    return [
        ApprovalRequestResponse(
            request_id=r.id,
            token=r.token,
            status=r.status.value,
            tool_name=r.tool_name,
            reason=r.reason,
            created_at=r.created_at.isoformat(),
            expires_at=r.expires_at.isoformat(),
            remaining_seconds=r.remaining_seconds,
        )
        for r in pending
    ]


@router.get("/receipts/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a receipt by ID."""
    receipt = _receipt_generator.get_receipt(receipt_id)

    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return ReceiptResponse(**receipt.to_dict())


@router.get("/receipts/session/{session_id}", response_model=SessionReceiptListResponse)
async def get_session_receipts(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    """Get receipts for a session."""
    receipts = _receipt_generator.get_receipts_for_session(session_id, limit)

    return SessionReceiptListResponse(
        session_id=session_id,
        count=len(receipts),
        receipts=[r.to_dict() for r in receipts],
    )


@router.get("/compliance", response_model=ComplianceResponse)
async def run_compliance_check(
    current_user: User = Depends(get_current_user),
):
    """Run local capability checks mapped to AARM; not a conformance report."""
    checker = AARMComplianceChecker(
        mediator=_mediator,
        context_accumulator=_context_accumulator,
        policy_engine=_policy_engine,
        approval_service=_approval_service,
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
                "requirement_id": r.requirement_id,
                "level": r.level.value,
                "description": r.description,
                "satisfied": r.satisfied,
                "details": r.details,
            }
            for r in report.results
        ],
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    current_user: User = Depends(get_current_user),
):
    """Get governance metrics."""
    return MetricsResponse(**_telemetry_exporter.get_metrics_summary())


@router.get("/metrics/prometheus", response_class=Response)
async def get_prometheus_metrics(
    current_user: User = Depends(get_current_user),
):
    """Get metrics in Prometheus format."""
    return PlainTextResponse(content=_telemetry_exporter.get_prometheus_metrics())


@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_200_OK)
async def create_session(
    session_id: str = Query(..., description="Session ID"),
    agent_id: str = Query(..., description="Agent ID"),
    user_id: Optional[str] = Query(default=None, description="User ID"),
    original_request: str = Query(default="", description="Original user request"),
    stated_intent: str = Query(default="", description="Stated user intent"),
    current_user: User = Depends(get_current_user),
):
    """Create a new session context."""
    context = _context_accumulator.create_session(
        session_id=session_id,
        agent_id=agent_id,
        user_id=user_id or str(current_user.id),
        original_request=original_request,
        stated_intent=stated_intent,
    )

    return SessionCreateResponse(
        session_id=context.session_id,
        agent_id=context.agent_id,
        created_at=context.created_at.isoformat(),
    )


@router.get("/sessions/{session_id}", response_model=SessionSummaryResponse)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get session context."""
    context = _context_accumulator.get_context(session_id)

    if not context:
        raise HTTPException(status_code=404, detail="Session not found")

    summary = _context_accumulator.get_session_summary(session_id)
    return SessionSummaryResponse(**summary)


@router.delete("/sessions/{session_id}", response_model=SessionCloseResponse)
async def close_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Close a session."""
    context = _context_accumulator.close_session(session_id)

    if not context:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionCloseResponse(session_id=session_id, status="closed")
