"""
MUTX Observability API Routes.

REST API for MUTX Observability Schema - agent run observability.

Routes:
- POST   /v1/observability/runs         - Create/report a MutxRun
- GET    /v1/observability/runs         - List runs with filters
- GET    /v1/observability/runs/{id}    - Get run detail with steps
- POST   /v1/observability/runs/{id}/steps     - Add steps to a run
- GET    /v1/observability/runs/{id}/eval      - Get eval for a run
- POST   /v1/observability/runs/{id}/eval      - Submit eval result
- GET    /v1/observability/runs/{id}/provenance - Get provenance for a run

Based on the agent-run open standard for agent observability.
https://github.com/builderz-labs/agent-run

MIT License - Copyright (c) 2026 Builderz Labs
https://github.com/builderz-labs/agent-run/blob/9c7c3fa68413de878fae2d605c90fb334a0201f6/LICENSE

Schema adaptation only. The current upstream package is quarantined pending
maintainer security review and is not required by this module.
"""

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import User, MutxRun, MutxStep, MutxCost, MutxProvenance, MutxEvalResult
from src.api.models.observability import (
    MutxRunCreate,
    MutxRunResponse,
    MutxRunDetailResponse,
    MutxRunHistoryResponse,
    MutxStepCreate,
    MutxStep as MutxStepSchema,
    MutxCostResponse,
    MutxProvenance as MutxProvenanceSchema,
    MutxEvalResponse,
    MutxEvalCreate,
    MutxRunStatus,
    MutxStepType,
    MutxStepBatchResponse,
    generate_run_id,
    compute_run_hash,
)
from src.api.models.numeric import NonNegativeFiniteFloat, nullable_non_finite_numbers

router = APIRouter(prefix="/observability", tags=["observability"])


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


def _encode_list(value: list) -> str:
    return json.dumps(value, allow_nan=False)


def _decode_list(value: Optional[str]) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _serialize_cost(cost: Optional[MutxCost]) -> Optional[MutxCostResponse]:
    if cost is None:
        return None
    cost_usd, degraded = nullable_non_finite_numbers(cost.cost_usd)
    return MutxCostResponse(
        input_tokens=cost.input_tokens,
        output_tokens=cost.output_tokens,
        cache_read_tokens=cost.cache_read_tokens,
        cache_write_tokens=cost.cache_write_tokens,
        total_tokens=cost.total_tokens,
        cost_usd=cost_usd,
        model=cost.model,
        degraded=degraded,
    )


def _serialize_provenance(pv: Optional[MutxProvenance]) -> Optional[MutxProvenanceSchema]:
    if pv is None:
        return None
    return MutxProvenanceSchema(
        run_hash=pv.run_hash,
        parent_run_hash=pv.parent_run_hash,
        lineage=_decode_list(pv.lineage),
        model_version=pv.model_version,
        config_hash=pv.config_hash,
        runtime=pv.runtime,
        signed_by=pv.signed_by,
        signature=pv.signature,
        created_at=pv.created_at,
    )


def _serialize_step(step: MutxStep) -> MutxStepSchema:
    return MutxStepSchema(
        id=step.id,
        type=MutxStepType(step.type),
        tool_name=step.tool_name,
        mcp_server=step.mcp_server,
        input_preview=step.input_preview,
        output_preview=step.output_preview,
        success=step.success,
        error=step.error,
        started_at=step.started_at,
        ended_at=step.ended_at,
        duration_ms=step.duration_ms,
        tokens_used=step.tokens_used,
        step_metadata=_decode_json(step.step_metadata),
    )


def _serialize_eval(eval_result: Optional[MutxEvalResult]) -> Optional[MutxEvalResponse]:
    if eval_result is None:
        return None
    metrics, metrics_degraded = nullable_non_finite_numbers(
        _decode_json(eval_result.metrics) if eval_result.metrics else None
    )
    score, score_degraded = nullable_non_finite_numbers(eval_result.score)
    return MutxEvalResponse.model_validate(
        {
            "task_type": eval_result.task_type,
            "eval_layer": eval_result.eval_layer,
            "pass": eval_result.eval_pass,
            "score": score,
            "expected_outcome": eval_result.expected_outcome,
            "actual_outcome": eval_result.actual_outcome,
            "metrics": metrics,
            "regression_from": eval_result.regression_from,
            "detail": eval_result.detail,
            "benchmark_id": eval_result.benchmark_id,
            "degraded": metrics_degraded or score_degraded,
        }
    )


def _serialize_run(run: MutxRun, include_steps: bool = False) -> MutxRunResponse:
    loaded_steps = run.__dict__.get("steps")
    loaded_cost = run.__dict__.get("cost")
    loaded_provenance = run.__dict__.get("provenance")
    loaded_eval = run.__dict__.get("eval_result")
    response_cost = _serialize_cost(loaded_cost)
    response_eval = _serialize_eval(loaded_eval)
    response = MutxRunResponse(
        id=run.id,
        agent_id=run.agent_id,
        agent_name=run.agent_name,
        model=run.model,
        provider=run.provider,
        runtime=run.runtime,
        runtime_version=run.runtime_version,
        trigger=run.trigger,
        parent_run_id=run.parent_run_id,
        task_id=run.task_id,
        status=MutxRunStatus(run.status),
        outcome=run.outcome,
        started_at=run.started_at,
        ended_at=run.ended_at,
        duration_ms=run.duration_ms,
        step_count=len(loaded_steps) if loaded_steps is not None else 0,
        tools_available=_decode_list(run.tools_available),
        cost=response_cost,
        provenance=_serialize_provenance(loaded_provenance),
        eval=response_eval,
        error=run.error,
        git_branch=run.git_branch,
        git_commit=run.git_commit,
        workspace_id=run.workspace_id,
        tags=_decode_list(run.tags),
        run_metadata=_decode_json(run.run_metadata),
        degraded=bool(
            (response_cost is not None and response_cost.degraded)
            or (response_eval is not None and response_eval.degraded)
        ),
        created_at=run.created_at,
    )
    return response


async def _get_user_run(run_id: str, current_user: User, db: AsyncSession) -> MutxRun:
    result = await db.execute(
        select(MutxRun)
        .execution_options(populate_existing=True)
        .options(
            selectinload(MutxRun.steps),
            selectinload(MutxRun.cost),
            selectinload(MutxRun.provenance),
            selectinload(MutxRun.eval_result),
        )
        .where(MutxRun.id == run_id, MutxRun.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    await db.refresh(run, attribute_names=["steps", "cost", "provenance", "eval_result"])
    return run


@router.post("/runs", response_model=MutxRunDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    request: MutxRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """
    Create or report a new MutxRun.

    This is the primary ingestion endpoint for agent run observability.
    """
    run_id = request.id or generate_run_id()
    started_at = request.started_at or datetime.now(timezone.utc)

    cost_record = None
    if request.cost:
        cost_record = MutxCost(
            input_tokens=request.cost.input_tokens,
            output_tokens=request.cost.output_tokens,
            cache_read_tokens=request.cost.cache_read_tokens,
            cache_write_tokens=request.cost.cache_write_tokens,
            total_tokens=request.cost.total_tokens,
            cost_usd=request.cost.cost_usd,
            model=request.cost.model or request.model,
        )

    provenance_record = None
    if request.provenance:
        prov = request.provenance
        provenance_record = MutxProvenance(
            run_hash=prov.run_hash,
            parent_run_hash=prov.parent_run_hash,
            lineage=_encode_list(prov.lineage),
            model_version=prov.model_version,
            config_hash=prov.config_hash,
            runtime=prov.runtime,
            signed_by=prov.signed_by,
            signature=prov.signature,
            created_at=prov.created_at or datetime.now(timezone.utc),
        )
    else:
        run_hash = compute_run_hash(
            agent_id=request.agent_id,
            model=request.model,
            tools_available=request.tools_available,
            config_hash=None,
            trigger=request.trigger.value if request.trigger else None,
        )
        provenance_record = MutxProvenance(
            run_hash=run_hash,
            runtime="mutx@1.0.0" if not request.runtime else request.runtime,
            created_at=datetime.now(timezone.utc),
        )

    run = MutxRun(
        id=run_id,
        user_id=current_user.id,
        agent_id=request.agent_id,
        agent_name=request.agent_name,
        model=request.model,
        provider=request.provider,
        runtime=request.runtime,
        runtime_version=request.runtime_version,
        trigger=request.trigger.value if request.trigger else None,
        parent_run_id=request.parent_run_id,
        task_id=request.task_id,
        status=request.status.value if request.status else MutxRunStatus.PENDING.value,
        outcome=request.outcome.value if request.outcome else None,
        started_at=started_at,
        ended_at=request.ended_at,
        duration_ms=request.duration_ms,
        tools_available=_encode_list(request.tools_available),
        git_branch=request.git_branch,
        git_commit=request.git_commit,
        workspace_id=request.workspace_id,
        tags=_encode_list(request.tags),
        run_metadata=_encode_json(request.run_metadata),
        error=request.error,
    )

    db.add(run)

    if cost_record:
        db.add(cost_record)
        run.cost = cost_record

    if provenance_record:
        db.add(provenance_record)
        run.provenance = provenance_record

    await db.flush()

    for idx, step in enumerate(request.steps):
        db.add(
            MutxStep(
                id=step.id or f"{run_id}-step-{idx}",
                run_id=run_id,
                type=step.type.value if isinstance(step.type, Enum) else step.type,
                tool_name=step.tool_name,
                mcp_server=step.mcp_server,
                input_preview=step.input_preview,
                output_preview=step.output_preview,
                success=step.success,
                error=step.error,
                started_at=step.started_at or datetime.now(timezone.utc),
                ended_at=step.ended_at,
                duration_ms=step.duration_ms,
                tokens_used=step.tokens_used,
                sequence=idx,
                step_metadata=_encode_json(step.step_metadata),
            )
        )

    await db.commit()

    persisted_run = await _get_user_run(run_id, current_user, db)
    steps = sorted(persisted_run.steps, key=lambda s: (s.sequence, s.started_at))

    return MutxRunDetailResponse(
        **_serialize_run(persisted_run, include_steps=True).model_dump(),
        steps=[_serialize_step(s) for s in steps],
    )


@router.get("/runs", response_model=MutxRunHistoryResponse)
async def list_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    runtime: Optional[str] = Query(None, description="Filter by runtime"),
    trigger: Optional[str] = Query(None, description="Filter by trigger"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """List runs with optional filters."""
    run_filters = [MutxRun.user_id == current_user.id]
    if agent_id:
        run_filters.append(MutxRun.agent_id == agent_id)
    if status_filter:
        run_filters.append(MutxRun.status == status_filter)
    if runtime:
        run_filters.append(MutxRun.runtime == runtime)
    if trigger:
        run_filters.append(MutxRun.trigger == trigger)

    total_stmt = select(func.count()).select_from(MutxRun).where(*run_filters)
    total = (await db.execute(total_stmt)).scalar_one()

    query = (
        select(MutxRun)
        .options(
            selectinload(MutxRun.cost),
            selectinload(MutxRun.provenance),
            selectinload(MutxRun.eval_result),
        )
        .where(*run_filters)
        .order_by(MutxRun.started_at.desc())
        .offset(skip)
        .limit(limit)
    )
    runs = (await db.execute(query)).scalars().all()

    return MutxRunHistoryResponse(
        items=[_serialize_run(run) for run in runs],
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(runs),
        agent_id=agent_id,
        status=status_filter,
    )


@router.get("/runs/{run_id}", response_model=MutxRunDetailResponse)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Get a run with full step details."""
    run = await _get_user_run(run_id, current_user, db)
    steps = sorted(run.steps, key=lambda s: (s.sequence, s.started_at))

    return MutxRunDetailResponse(
        **_serialize_run(run, include_steps=True).model_dump(),
        steps=[_serialize_step(s) for s in steps],
    )


@router.post(
    "/runs/{run_id}/steps",
    response_model=MutxStepBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_steps(
    run_id: str,
    steps: list[MutxStepCreate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Add steps to an existing run."""
    await _get_user_run(run_id, current_user, db)

    max_seq_result = await db.execute(
        select(func.max(MutxStep.sequence)).where(MutxStep.run_id == run_id)
    )
    max_seq = max_seq_result.scalar()
    current_max_seq = max_seq if max_seq is not None else -1

    new_steps = []
    for idx, step in enumerate(steps):
        new_step = MutxStep(
            id=step.id or f"{run_id}-step-{current_max_seq + 1 + idx}",
            run_id=run_id,
            type=step.type.value if isinstance(step.type, Enum) else step.type,
            tool_name=step.tool_name,
            mcp_server=step.mcp_server,
            input_preview=step.input_preview,
            output_preview=step.output_preview,
            success=step.success,
            error=step.error,
            started_at=step.started_at or datetime.now(timezone.utc),
            ended_at=step.ended_at,
            duration_ms=step.duration_ms,
            tokens_used=step.tokens_used,
            sequence=current_max_seq + 1 + idx,
            step_metadata=_encode_json(step.step_metadata),
        )
        db.add(new_step)
        new_steps.append(new_step)

    await db.commit()

    for step in new_steps:
        await db.refresh(step)

    total_stmt = select(func.count()).select_from(MutxStep).where(MutxStep.run_id == run_id)
    total = (await db.execute(total_stmt)).scalar_one()

    return MutxStepBatchResponse(
        total=total,
        added=len(new_steps),
    )


@router.get("/runs/{run_id}/eval", response_model=Optional[MutxEvalResponse])
async def get_eval(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Get the evaluation for a run."""
    run = await _get_user_run(run_id, current_user, db)
    if run.eval_result is None:
        raise HTTPException(status_code=404, detail="No evaluation found for this run")
    return _serialize_eval(run.eval_result)


@router.post(
    "/runs/{run_id}/eval", response_model=MutxEvalResponse, status_code=status.HTTP_201_CREATED
)
async def submit_eval(
    run_id: str,
    eval_data: MutxEvalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Submit or update the evaluation for a run."""
    run = await _get_user_run(run_id, current_user, db)

    if run.eval_result:
        eval_record = run.eval_result
        eval_record.task_type = eval_data.task_type
        eval_record.eval_layer = eval_data.eval_layer
        eval_record.eval_pass = eval_data.eval_pass
        eval_record.score = eval_data.score
        eval_record.expected_outcome = eval_data.expected_outcome
        eval_record.actual_outcome = eval_data.actual_outcome
        eval_record.metrics = (
            _encode_json(eval_data.metrics.model_dump()) if eval_data.metrics else None
        )
        eval_record.regression_from = eval_data.regression_from
        eval_record.detail = eval_data.detail
        eval_record.benchmark_id = eval_data.benchmark_id
    else:
        eval_record = MutxEvalResult(
            run_id=run_id,
            task_type=eval_data.task_type,
            eval_layer=eval_data.eval_layer,
            eval_pass=eval_data.eval_pass,
            score=eval_data.score,
            expected_outcome=eval_data.expected_outcome,
            actual_outcome=eval_data.actual_outcome,
            metrics=_encode_json(eval_data.metrics.model_dump()) if eval_data.metrics else None,
            regression_from=eval_data.regression_from,
            detail=eval_data.detail,
            benchmark_id=eval_data.benchmark_id,
        )
        db.add(eval_record)

    await db.commit()
    await db.refresh(eval_record)

    return _serialize_eval(eval_record)


@router.get("/runs/{run_id}/provenance", response_model=Optional[MutxProvenanceSchema])
async def get_provenance(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Get the provenance record for a run."""
    run = await _get_user_run(run_id, current_user, db)
    if run.provenance is None:
        raise HTTPException(status_code=404, detail="No provenance record found for this run")
    return _serialize_provenance(run.provenance)


class MutxRunStatusUpdate(BaseModel):
    """Validated payload for patching run status."""

    status: Optional[MutxRunStatus] = None
    outcome: Optional[str] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)
    error: Optional[str] = None
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    total_tokens: Optional[int] = Field(default=None, ge=0)
    cost_usd: Optional[NonNegativeFiniteFloat] = None


@router.patch("/runs/{run_id}/status", response_model=MutxRunResponse)
async def update_run_status(
    run_id: str,
    status_update: MutxRunStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Update the status of a run (e.g., mark as completed, failed)."""
    run = await _get_user_run(run_id, current_user, db)

    if status_update.status is not None:
        run.status = status_update.status
    if status_update.outcome is not None:
        run.outcome = status_update.outcome
    if status_update.ended_at is not None:
        run.ended_at = status_update.ended_at
    if status_update.duration_ms is not None:
        run.duration_ms = status_update.duration_ms
    if status_update.error is not None:
        run.error = status_update.error

    if any(
        v is not None
        for v in (
            status_update.input_tokens,
            status_update.output_tokens,
            status_update.total_tokens,
            status_update.cost_usd,
        )
    ):
        if run.cost is None:
            run.cost = MutxCost(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cost_usd=0.0,
                model=run.model,
            )
            db.add(run.cost)
        if status_update.input_tokens is not None:
            run.cost.input_tokens = status_update.input_tokens
        if status_update.output_tokens is not None:
            run.cost.output_tokens = status_update.output_tokens
        if status_update.total_tokens is not None:
            run.cost.total_tokens = status_update.total_tokens
        else:
            run.cost.total_tokens = (run.cost.input_tokens or 0) + (run.cost.output_tokens or 0)
        if status_update.cost_usd is not None:
            run.cost.cost_usd = status_update.cost_usd

    await db.commit()
    persisted_run = await _get_user_run(run_id, current_user, db)
    return _serialize_run(persisted_run)
