import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import Agent, AgentRun, AgentRunTrace, User
from src.api.services.analytics import log_analytics_event, AnalyticsEventType
from src.api.services.usage import track_usage_best_effort
from src.api.models.schemas import (
    RunCreate,
    RunDetailResponse,
    RunHistoryResponse,
    RunResponse,
    RunTraceCreate,
    RunTraceHistoryResponse,
    RunTraceResponse,
)

router = APIRouter(prefix="/runs", tags=["runs"])


def _encode_json(value: dict[str, Any]) -> str:
    return json.dumps(value, allow_nan=False)


def _decode_json(value: Optional[str]) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _serialize_trace(trace: AgentRunTrace) -> RunTraceResponse:
    return RunTraceResponse(
        id=trace.id,
        run_id=trace.run_id,
        event_type=trace.event_type,
        message=trace.message,
        payload=_decode_json(trace.payload),
        sequence=trace.sequence,
        timestamp=trace.timestamp,
    )


def _serialize_run(run: AgentRun) -> RunResponse:
    metadata = _decode_json(run.run_metadata)
    return RunResponse(
        id=run.id,
        agent_id=run.agent_id,
        status=run.status,
        input_text=run.input_text,
        output_text=run.output_text,
        error_message=run.error_message,
        metadata=metadata,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        trace_count=len(getattr(run, "traces", [])),
        subject_type=metadata.get("subject_type"),
        subject_id=metadata.get("subject_id"),
        subject_label=metadata.get("subject_label"),
        template_id=metadata.get("template_id"),
        execution_mode=metadata.get("execution_mode"),
    )


async def _get_user_agent(agent_id: uuid.UUID, current_user: User, db: AsyncSession) -> Agent:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == current_user.id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def _get_user_run(run_id: uuid.UUID, current_user: User, db: AsyncSession) -> AgentRun:
    result = await db.execute(
        select(AgentRun)
        .options(selectinload(AgentRun.traces))
        .where(AgentRun.id == run_id, AgentRun.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("", response_model=RunDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    request: RunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    agent = await _get_user_agent(request.agent_id, current_user, db)
    started_at = request.started_at or datetime.now(timezone.utc)

    run = AgentRun(
        agent_id=agent.id,
        user_id=current_user.id,
        status=request.status,
        input_text=request.input_text,
        output_text=request.output_text,
        error_message=request.error_message,
        run_metadata=_encode_json(request.metadata),
        started_at=started_at,
        completed_at=request.completed_at,
    )
    db.add(run)
    await db.flush()

    for idx, trace in enumerate(request.traces):
        db.add(
            AgentRunTrace(
                run_id=run.id,
                event_type=trace.event_type,
                message=trace.message,
                payload=_encode_json(trace.payload),
                sequence=idx,
                timestamp=trace.timestamp or datetime.now(timezone.utc),
            )
        )

    await db.commit()

    # Track analytics event
    await log_analytics_event(
        db,
        event_name="Agent run created",
        event_type=AnalyticsEventType.AGENT_RUN_STARTED,
        user_id=current_user.id,
        properties={"agent_id": str(agent.id), "run_id": str(run.id)},
    )

    await track_usage_best_effort(
        db=db,
        user_id=current_user.id,
        event_type="agent_run_created",
        resource_id=str(run.id),
        metadata={"agent_id": str(agent.id)},
    )

    persisted_run = await _get_user_run(run.id, current_user, db)
    traces = sorted(persisted_run.traces, key=lambda item: (item.sequence, item.timestamp))

    return RunDetailResponse(
        **_serialize_run(persisted_run).model_dump(),
        traces=[_serialize_trace(trace) for trace in traces],
    )


@router.get("", response_model=RunHistoryResponse)
async def list_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    agent_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    if agent_id is not None:
        await _get_user_agent(agent_id, current_user, db)

    run_filters = [AgentRun.user_id == current_user.id]
    if agent_id is not None:
        run_filters.append(AgentRun.agent_id == agent_id)
    if status:
        run_filters.append(AgentRun.status == status)

    total_stmt = select(func.count()).select_from(AgentRun).where(*run_filters)
    total = (await db.execute(total_stmt)).scalar_one()

    query = (
        select(AgentRun)
        .options(selectinload(AgentRun.traces))
        .where(*run_filters)
        .order_by(AgentRun.started_at.desc())
        .offset(skip)
        .limit(limit)
    )
    runs = (await db.execute(query)).scalars().all()

    return RunHistoryResponse(
        items=[_serialize_run(run) for run in runs],
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(runs),
        agent_id=agent_id,
        status=status,
    )


@router.get("/{run_id}", response_model=RunDetailResponse)
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    run = await _get_user_run(run_id, current_user, db)
    traces = sorted(run.traces, key=lambda item: (item.sequence, item.timestamp))

    return RunDetailResponse(
        **_serialize_run(run).model_dump(),
        traces=[_serialize_trace(trace) for trace in traces],
    )


@router.get("/{run_id}/traces", response_model=RunTraceHistoryResponse)
async def list_run_traces(
    run_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    event_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    run = await _get_user_run(run_id, current_user, db)

    trace_filters = [AgentRunTrace.run_id == run.id]
    if event_type:
        trace_filters.append(AgentRunTrace.event_type == event_type)

    total_stmt = select(func.count()).select_from(AgentRunTrace).where(*trace_filters)
    total = (await db.execute(total_stmt)).scalar_one()

    traces_query = (
        select(AgentRunTrace)
        .where(*trace_filters)
        .order_by(AgentRunTrace.sequence.asc(), AgentRunTrace.timestamp.asc())
        .offset(skip)
        .limit(limit)
    )
    traces = (await db.execute(traces_query)).scalars().all()

    return RunTraceHistoryResponse(
        run_id=run.id,
        items=[_serialize_trace(trace) for trace in traces],
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(traces),
        event_type=event_type,
    )


@router.post(
    "/{run_id}/traces", response_model=RunTraceHistoryResponse, status_code=status.HTTP_201_CREATED
)
async def add_run_traces(
    run_id: uuid.UUID,
    traces: list[RunTraceCreate],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """
    Add traces to an existing run.

    This endpoint allows adding execution traces to a run after it has been created.
    Traces are used to track the step-by-step execution of an agent.
    """
    run = await _get_user_run(run_id, current_user, db)

    # Get the current max sequence to continue from
    max_seq_result = await db.execute(
        select(func.max(AgentRunTrace.sequence)).where(AgentRunTrace.run_id == run.id)
    )
    max_seq = max_seq_result.scalar()
    current_max_seq = max_seq if max_seq is not None else -1

    # Add new traces
    new_traces = []
    for idx, trace in enumerate(traces):
        new_trace = AgentRunTrace(
            run_id=run.id,
            event_type=trace.event_type,
            message=trace.message,
            payload=_encode_json(trace.payload),
            sequence=current_max_seq + 1 + idx,
            timestamp=trace.timestamp or datetime.now(timezone.utc),
        )
        db.add(new_trace)
        new_traces.append(new_trace)

    await db.commit()

    # Refresh the new traces
    for trace in new_traces:
        await db.refresh(trace)

    # Fetch all traces for the run (respecting limit)
    trace_filters = [AgentRunTrace.run_id == run.id]

    total_stmt = select(func.count()).select_from(AgentRunTrace).where(*trace_filters)
    total = (await db.execute(total_stmt)).scalar_one()

    traces_query = (
        select(AgentRunTrace)
        .where(*trace_filters)
        .order_by(AgentRunTrace.sequence.asc(), AgentRunTrace.timestamp.asc())
        .offset(skip)
        .limit(limit)
    )
    all_traces = (await db.execute(traces_query)).scalars().all()

    return RunTraceHistoryResponse(
        run_id=run.id,
        items=[_serialize_trace(trace) for trace in all_traces],
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(all_traces),
    )
