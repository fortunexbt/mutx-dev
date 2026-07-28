"""
Audit Log Routes.

Provides REST API endpoints for querying audit events and traces.
All routes require authentication.
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from src.api.auth.dependencies import require_roles
from src.api.models.models import User
from src.api.services.audit_log import (
    AuditEvent,
    AuditEventType,
    AuditQuery,
    get_audit_log,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventResponse(BaseModel):
    """Response model for an audit event."""

    model_config = ConfigDict(from_attributes=True)

    event_id: str
    agent_id: str
    session_id: str
    run_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    event_type: str
    payload: dict
    timestamp: datetime
    trace_id: str | None = None
    actor_type: str = "agent"
    actor_id: str | None = None
    actor_display: str | None = None
    policy_decision_id: str | None = None
    policy_refs: list[str] = Field(default_factory=list)
    approval_id: str | None = None
    cost_record: dict[str, object] | None = None
    redaction_status: str = "none"
    schema_version: str = "1.0"
    previous_hash: str | None = None
    integrity_hash: str | None = None

    @classmethod
    def from_audit_event(cls, event: AuditEvent) -> "AuditEventResponse":
        """Create response from AuditEvent model."""
        return cls(
            event_id=str(event.event_id),
            agent_id=event.agent_id,
            session_id=event.session_id,
            run_id=event.run_id,
            span_id=event.span_id,
            parent_span_id=event.parent_span_id,
            event_type=event.event_type.value,
            payload=event.payload,
            timestamp=event.timestamp,
            trace_id=event.trace_id,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            actor_display=event.actor_display,
            policy_decision_id=event.policy_decision_id,
            policy_refs=event.policy_refs,
            approval_id=event.approval_id,
            cost_record=event.cost_record,
            redaction_status=event.redaction_status,
            schema_version=event.schema_version,
            previous_hash=event.previous_hash,
            integrity_hash=event.integrity_hash,
        )


class AuditEventsResponse(BaseModel):
    """Response model for a list of audit events."""

    events: list[AuditEventResponse]
    total: int | None = None


class AuditEvidenceExportResponse(BaseModel):
    """Verified governed-operation evidence chain export."""

    schema_version: str
    algorithm: str
    run_id: str | None = None
    session_id: str | None = None
    event_count: int
    chain_root: str | None = None
    verified: bool
    errors: list[str]
    events: list[AuditEventResponse]


@router.get(
    "/events",
    response_model=AuditEventsResponse,
)
async def query_audit_events(
    _current_user: Annotated[User, Depends(require_roles("ADMIN", "AUDIT_ADMIN"))],
    agent_id: Annotated[str | None, Query(description="Filter by agent ID")] = None,
    session_id: Annotated[str | None, Query(description="Filter by session ID")] = None,
    run_id: Annotated[str | None, Query(description="Filter by run ID")] = None,
    time_range_start: Annotated[
        datetime | None,
        Query(
            description="Filter events after this timestamp (ISO 8601 format)",
        ),
    ] = None,
    time_range_end: Annotated[
        datetime | None,
        Query(
            description="Filter events before this timestamp (ISO 8601 format)",
        ),
    ] = None,
    event_type: Annotated[
        AuditEventType | None,
        Query(description="Filter by event type"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum events to return")] = 100,
    skip: Annotated[int, Query(ge=0, description="Number of events to skip")] = 0,
) -> AuditEventsResponse:
    """Query audit events with filters.

    Requires authentication. Results are ordered by timestamp descending.

    Args:
        current_user: The authenticated user.
        agent_id: Optional agent ID filter.
        session_id: Optional session ID filter.
        run_id: Optional run ID filter.
        time_range_start: Optional start time filter.
        time_range_end: Optional end time filter.
        event_type: Optional event type filter.
        limit: Maximum number of events to return (1-1000, default 100).
        skip: Number of events to skip for pagination.

    Returns:
        AuditEventsResponse containing list of matching events.
    """
    filters = AuditQuery(
        agent_id=agent_id,
        session_id=session_id,
        run_id=run_id,
        time_range_start=time_range_start,
        time_range_end=time_range_end,
        event_type=event_type,
        limit=limit,
        skip=skip,
    )

    try:
        audit_log = await get_audit_log()
        events = await audit_log.query(filters)
        event_responses = [AuditEventResponse.from_audit_event(e) for e in events]
        return AuditEventsResponse(events=event_responses)
    except Exception as e:
        logger.exception("Failed to query audit events")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query audit events: {str(e)}",
        )


@router.get(
    "/export",
    response_model=AuditEvidenceExportResponse,
)
async def export_audit_evidence(
    _current_user: Annotated[User, Depends(require_roles("ADMIN", "AUDIT_ADMIN"))],
    run_id: Annotated[str | None, Query(description="Run ID to export")] = None,
    session_id: Annotated[str | None, Query(description="Session ID to export")] = None,
) -> AuditEvidenceExportResponse:
    """Export a verified SHA-256 evidence chain for one run or session."""
    try:
        audit_log = await get_audit_log()
        export = await audit_log.export_evidence(run_id=run_id, session_id=session_id)
        return AuditEvidenceExportResponse(**export)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to export audit evidence: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export audit evidence",
        ) from exc


@router.get(
    "/traces/{trace_id}",
    response_model=AuditEventsResponse,
)
async def get_trace_events(
    trace_id: str,
    _current_user: Annotated[User, Depends(require_roles("ADMIN", "AUDIT_ADMIN"))],
) -> AuditEventsResponse:
    """Get all events for a specific trace.

    Requires authentication. Results are ordered by timestamp ascending.

    Args:
        trace_id: The trace ID to look up.
        current_user: The authenticated user.

    Returns:
        AuditEventsResponse containing all events for the trace.
    """
    try:
        audit_log = await get_audit_log()
        events = await audit_log.get_trace(trace_id)
        event_responses = [AuditEventResponse.from_audit_event(e) for e in events]
        return AuditEventsResponse(events=event_responses)
    except Exception as e:
        logger.exception("Failed to get trace events")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trace events: {str(e)}",
        )
