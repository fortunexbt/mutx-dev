"""Schemas for the legacy runtime-security API and its durable state."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.api.models.numeric import DegradedNumericResponseModel


class SecurityWriteModel(BaseModel):
    """Fail closed when callers supply fields outside the public contract."""

    model_config = ConfigDict(extra="forbid")


class ActionEvaluateRequest(SecurityWriteModel):
    """Request to evaluate an action without executing it."""

    tool_name: str = Field(..., min_length=1, max_length=255, description="Name of the tool")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    agent_id: uuid.UUID = Field(..., description="Persisted agent ID")
    session_id: str = Field(..., min_length=1, max_length=180, description="Session ID")
    trigger: str = Field(default="manual", max_length=120, description="What triggered this")
    runtime: str = Field(default="mutx", max_length=120, description="Runtime identifier")


class ActionEvaluateResponse(BaseModel):
    """Response from action evaluation."""

    decision: str
    rule_id: str | None = None
    rule_name: str | None = None
    reason: str
    would_modify: bool = False
    evaluation_id: str
    receipt_id: str
    action_id: str
    action_hash: str


class ApprovalRequestCreate(SecurityWriteModel):
    """Request human approval for an action."""

    tool_name: str = Field(..., min_length=1, max_length=255, description="Name of the tool")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    agent_id: uuid.UUID = Field(..., description="Persisted agent ID")
    session_id: str = Field(..., min_length=1, max_length=180, description="Session ID")
    reviewer_id: uuid.UUID | None = Field(
        default=None,
        description="Persisted non-requester reviewer assignment",
    )
    reason: str = Field(default="", max_length=4000, description="Why approval is needed")
    timeout_minutes: int = Field(default=5, ge=1, le=60, description="Timeout in minutes")


class ApprovalRequestResponse(BaseModel):
    """Public representation of a legacy security approval."""

    request_id: str
    owner_id: str
    reviewer_id: str | None
    can_resolve: bool
    status: str
    tool_name: str
    reason: str
    created_at: str
    expires_at: str
    remaining_seconds: int


class ApprovalActionRequest(SecurityWriteModel):
    """Approve or deny a request as the authenticated principal."""

    comment: str = Field(default="", max_length=4000, description="Optional comment")


class ApprovalActionResponse(BaseModel):
    """Response for approve/deny actions."""

    status: str
    request_id: str


class ComplianceResponse(BaseModel):
    """Backward-compatible local AARM-alignment check response."""

    overall_satisfied: bool
    version: str
    checked_at: str
    summary: dict[str, Any]
    results: list[dict[str, Any]]


class ReceiptResponse(BaseModel):
    """Response for a single action receipt."""

    receipt_id: str = ""
    action_id: str = ""
    action_hash: str = ""
    session_id: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = Field(default_factory=dict)
    agent_id: str = ""
    user_id: str = ""
    policy_decision: str = ""
    policy_rule_id: str | None = None
    policy_rule_name: str | None = None
    decision_reason: str = ""
    outcome: str = ""
    outcome_detail: str = ""
    timestamp: str = ""
    duration_ms: int | None = None
    signature: str | None = None
    signed_by: str | None = None
    signer_key_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionReceiptListResponse(BaseModel):
    """Response for listing receipts in a session."""

    session_id: str
    count: int
    total: int
    limit: int
    offset: int
    receipts: list[dict[str, Any]] = Field(default_factory=list)


class SessionCreateResponse(BaseModel):
    """Response for creating a security session."""

    session_id: str
    agent_id: str
    created_at: str


class SessionCreateRequest(SecurityWriteModel):
    """Create or refresh an authenticated principal's security session."""

    session_id: str = Field(..., min_length=1, max_length=180, description="Session ID")
    agent_id: uuid.UUID = Field(..., description="Persisted agent ID")
    original_request: str = Field(default="", max_length=4000)
    stated_intent: str = Field(default="", max_length=4000)


class SessionSummaryResponse(DegradedNumericResponseModel):
    """Response for getting a session summary."""

    session_id: str
    agent_id: str
    duration_seconds: float | None = 0.0
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


class MetricsResponse(DegradedNumericResponseModel):
    """Governance metrics response."""

    total_evaluations: int
    permits: int
    denials: int
    defers: int
    pending_approvals: int
    intent_drifts: int
    active_sessions: int
    avg_latency_ms: float | None
    decisions_per_minute: int
    decisions_per_hour: int


class SecuritySessionState(BaseModel):
    """Validated storage representation for an owner-bound security session."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    owner_id: uuid.UUID
    session_id: str
    agent_id: str
    user_id: str
    original_request: str = ""
    stated_intent: str = ""
    created_at: datetime
    updated_at: datetime
    total_actions: int = 0
    permits: int = 0
    denials: int = 0
    defers: int = 0
    errors: int = 0
    intent_alignment: str = "unknown"
