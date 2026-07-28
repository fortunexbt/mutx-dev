"""Durable tenant-owned scheduler API and background execution loop."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import croniter
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api import database
from src.api.auth.dependencies import get_current_internal_user
from src.api.database import get_db
from src.api.models import Agent, ScheduledTask, User
from src.api.models.scheduler_schemas import (
    SchedulerTaskCreate,
    SchedulerListResponse,
    SchedulerTaskResponse,
    SchedulerTaskUpdate,
    SchedulerWebhookPayload,
    TriggerTaskResponse,
)
from src.api.services.auth import Role, check_role
from src.api.services.scheduler_service import (
    SchedulerService,
    SchedulerTaskNotFound,
    TaskClaim,
    as_utc,
)
from src.api.services.scheduler_webhook import (
    SchedulerWebhookDeliveryError,
    UnsafeSchedulerWebhookTarget,
    deliver_scheduler_webhook,
    validate_scheduler_webhook_target,
)

logger = logging.getLogger(__name__)
SUPPORTED_TASK_TYPES = frozenset({"log", "webhook", "agent_heartbeat"})

_scheduler_running = False
_scheduler_task: asyncio.Task[None] | None = None
_execution_tasks: dict[str, asyncio.Task[None]] = {}
_execution_ids: dict[str, str] = {}


@asynccontextmanager
async def _scheduler_lifespan(app):
    """Start one polling loop per API worker; database claims coordinate execution."""
    ready_event = getattr(app.state, "database_ready_event", None)
    _ensure_scheduler_running(ready_event=ready_event)
    try:
        yield
    finally:
        await _stop_scheduler()


router = APIRouter(
    prefix="/scheduler",
    tags=["scheduler"],
    lifespan=_scheduler_lifespan,
)


class ScheduledActionError(RuntimeError):
    """An expected scheduled-action failure with an API-safe status code."""

    def __init__(self, message: str, *, status_code: int = 500, code: str = "runtime_error"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


async def require_scheduler_reader(
    current_user: User = Depends(get_current_internal_user),
) -> User:
    """Require the persisted read role after applying the internal-user gate."""
    if not check_role(current_user.roles or [], [Role.VIEWER, Role.DEVELOPER]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Required roles: ['VIEWER', 'DEVELOPER']",
        )
    return current_user


async def require_scheduler_developer(
    current_user: User = Depends(get_current_internal_user),
) -> User:
    """Require the persisted mutation role after applying the internal-user gate."""
    if not check_role(current_user.roles or [], [Role.DEVELOPER]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Required roles: ['DEVELOPER']",
        )
    return current_user


def _task_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Task not found")


def _timestamp(value: datetime | None) -> int | None:
    normalized = as_utc(value)
    return int(normalized.timestamp()) if normalized is not None else None


def _serialize_task(task: ScheduledTask) -> SchedulerTaskResponse:
    return SchedulerTaskResponse(
        id=str(task.id),
        name=task.name,
        description=task.description,
        enabled=task.enabled,
        schedule=task.schedule,
        interval_seconds=task.interval_seconds,
        task_type=task.task_type,
        payload=dict(task.payload or {}),
        last_run=_timestamp(task.last_run),
        next_run=_timestamp(task.next_run) if task.enabled else None,
        run_count=task.run_count,
        success_count=task.success_count,
        failure_count=task.failure_count,
        status=task.status,
        last_started_at=_timestamp(task.last_started_at),
        last_finished_at=_timestamp(task.last_finished_at),
        last_succeeded_at=_timestamp(task.last_succeeded_at),
        last_failed_at=_timestamp(task.last_failed_at),
        last_error=task.last_error,
        active_execution_id=(
            str(task.active_execution_id) if task.active_execution_id is not None else None
        ),
        created_at=_timestamp(task.created_at) or 0,
        updated_at=_timestamp(task.updated_at) or 0,
    )


async def _get_owned_heartbeat_agent(
    agent_id: uuid.UUID,
    db: AsyncSession,
    owner: User | SimpleNamespace,
) -> Agent:
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.user_id == owner.id,
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def _send_agent_heartbeat(task: dict[str, Any], db: AsyncSession) -> None:
    payload = task.get("payload", {})
    raw_agent_id = payload.get("agent_id")
    if not raw_agent_id:
        raise ScheduledActionError(
            "agent_heartbeat requires payload.agent_id",
            status_code=400,
            code="invalid_payload",
        )
    try:
        agent_id = uuid.UUID(str(raw_agent_id))
        owner_id = uuid.UUID(str(task["owner_user_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ScheduledActionError(
            "agent_heartbeat requires valid agent and owner identifiers",
            status_code=400,
            code="invalid_payload",
        ) from exc

    try:
        agent = await _get_owned_heartbeat_agent(agent_id, db, SimpleNamespace(id=owner_id))
    except HTTPException as exc:
        raise ScheduledActionError(
            str(exc.detail),
            status_code=exc.status_code,
            code="agent_not_found",
        ) from exc

    from src.api.routes.agent_runtime import HeartbeatRequest, heartbeat

    request = HeartbeatRequest(
        agent_id=str(agent.id),
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )
    await heartbeat(request=request, db=db, agent=agent)


async def _execute_task_action(task: dict[str, Any], *, db: AsyncSession) -> None:
    """Execute the immutable action snapshot associated with one durable claim."""
    task_type = task.get("task_type", "log")
    payload = task.get("payload", {})
    task_id = task["id"]
    if task_type not in SUPPORTED_TASK_TYPES:
        raise ScheduledActionError(
            f"Unsupported scheduled task type: {task_type}",
            status_code=400,
            code="unsupported_task_type",
        )

    logger.info("[scheduler] Executing task %s (%s)", task_id, task_type)
    if task_type == "webhook":
        try:
            webhook_payload = SchedulerWebhookPayload.model_validate(payload)
        except ValidationError as exc:
            error = exc.errors(include_input=False)[0]
            location = ".".join(str(part) for part in error["loc"])
            raise ScheduledActionError(
                f"Invalid webhook payload at {location}: {error['msg']}",
                status_code=400,
                code="invalid_payload",
            ) from exc
        try:
            status_code = await deliver_scheduler_webhook(webhook_payload)
        except UnsafeSchedulerWebhookTarget as exc:
            raise ScheduledActionError(
                str(exc),
                status_code=400,
                code="unsafe_webhook_target",
            ) from exc
        except SchedulerWebhookDeliveryError as exc:
            raise ScheduledActionError(
                str(exc),
                status_code=502,
                code="webhook_delivery_failed",
            ) from exc
        logger.info("[scheduler] Webhook task %s → %s", task_id, status_code)
        return

    if task_type == "agent_heartbeat":
        await _send_agent_heartbeat(task, db)
        logger.info("[scheduler] Heartbeat recorded for agent %s", payload.get("agent_id"))
        return

    logger.info("[scheduler] Log task %s: %s", task_id, payload.get("message", ""))


def _session_factory_for(db: AsyncSession) -> async_sessionmaker[AsyncSession]:
    if db.bind is None:
        return database.async_session_maker
    return async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)


async def _run_task_execution(
    claim: TaskClaim,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    error: Exception | None = None
    try:
        if claim.snapshot is None:
            return
        async with session_factory() as db:
            try:
                await _execute_task_action(claim.snapshot, db=db)
            except asyncio.CancelledError:
                error = ScheduledActionError(
                    "Scheduled task execution cancelled",
                    code="cancelled",
                )
            except Exception as exc:
                error = exc
                logger.exception(
                    "[scheduler] Task %s execution %s failed",
                    claim.task_id,
                    claim.execution_id,
                )
            await SchedulerService(db).finalize_execution(
                claim.task_id,
                claim.execution_id,
                error=error,
            )
    finally:
        task_key = str(claim.task_id)
        if _execution_tasks.get(task_key) is asyncio.current_task():
            _execution_tasks.pop(task_key, None)
            _execution_ids.pop(task_key, None)


def _launch_claimed_execution(
    claim: TaskClaim,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> asyncio.Task[None]:
    execution_task = asyncio.create_task(
        _run_task_execution(claim, session_factory=session_factory)
    )
    task_key = str(claim.task_id)
    _execution_tasks[task_key] = execution_task
    _execution_ids[task_key] = str(claim.execution_id)
    return execution_task


async def _schedule_due_tasks(
    now: datetime | None = None,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> list[asyncio.Task[None]]:
    """Load and conditionally claim due rows before launching their actions."""
    factory = session_factory or database.async_session_maker
    async with factory() as db:
        claims = await SchedulerService(db).claim_due_tasks(now=now)
    return [
        _launch_claimed_execution(claim, session_factory=factory)
        for claim in claims
        if claim.snapshot is not None
    ]


async def _scheduler_loop(*, ready_event: asyncio.Event | None = None) -> None:
    global _scheduler_running
    try:
        if ready_event is not None:
            await ready_event.wait()
        while _scheduler_running:
            try:
                await _schedule_due_tasks()
            except Exception:
                logger.exception("[scheduler] Durable polling loop failed")
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        logger.info("[scheduler] Background scheduler loop cancelled")
    finally:
        _scheduler_running = False


def _ensure_scheduler_running(*, ready_event: asyncio.Event | None = None) -> None:
    global _scheduler_running, _scheduler_task
    if not _scheduler_running or _scheduler_task is None or _scheduler_task.done():
        _scheduler_running = True
        _scheduler_task = asyncio.create_task(_scheduler_loop(ready_event=ready_event))
        logger.info("[scheduler] Background scheduler loop started")


async def _stop_scheduler() -> None:
    global _scheduler_running, _scheduler_task
    _scheduler_running = False
    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
        await asyncio.gather(_scheduler_task, return_exceptions=True)
    _scheduler_task = None

    executions = list(_execution_tasks.values())
    for execution in executions:
        if not execution.done():
            execution.cancel()
    if executions:
        await asyncio.gather(*executions, return_exceptions=True)
    _execution_tasks.clear()
    _execution_ids.clear()


async def _validate_task_action(
    task_type: str,
    payload: dict[str, Any],
    *,
    current_user: User,
    db: AsyncSession,
) -> None:
    if task_type not in SUPPORTED_TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported task type: {task_type}")

    if task_type == "webhook":
        try:
            webhook_payload = SchedulerWebhookPayload.model_validate(payload)
        except ValidationError as exc:
            error = exc.errors(include_input=False)[0]
            location = ".".join(str(part) for part in error["loc"])
            raise HTTPException(
                status_code=400,
                detail=f"Invalid webhook payload at {location}: {error['msg']}",
            ) from exc
        try:
            await validate_scheduler_webhook_target(webhook_payload.url)
        except UnsafeSchedulerWebhookTarget as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if task_type != "agent_heartbeat":
        return
    raw_agent_id = payload.get("agent_id")
    if not raw_agent_id:
        raise HTTPException(
            status_code=400,
            detail="agent_heartbeat requires payload.agent_id",
        )
    try:
        agent_id = uuid.UUID(str(raw_agent_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid agent_id") from exc
    await _get_owned_heartbeat_agent(agent_id, db, current_user)


@router.get("", response_model=SchedulerListResponse)
async def get_scheduler(
    current_user: User = Depends(require_scheduler_reader),
    db: AsyncSession = Depends(get_db),
) -> SchedulerListResponse:
    """List durable scheduled tasks owned by the authenticated user."""
    tasks = await SchedulerService(db).list_tasks(current_user.id)
    return SchedulerListResponse(tasks=[_serialize_task(task) for task in tasks], total=len(tasks))


@router.post("", response_model=SchedulerTaskResponse, status_code=201)
async def create_scheduled_task(
    task_data: SchedulerTaskCreate,
    current_user: User = Depends(require_scheduler_developer),
    db: AsyncSession = Depends(get_db),
) -> SchedulerTaskResponse:
    """Create a durable tenant-owned scheduled task."""
    if task_data.schedule:
        try:
            croniter.croniter(task_data.schedule, datetime.now(tz=timezone.utc))
        except (croniter.CroniterBadCronError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid cron expression: {exc}") from exc
    if not task_data.schedule and not task_data.interval_seconds:
        raise HTTPException(
            status_code=400,
            detail="Either 'schedule' (cron expression) or 'interval_seconds' is required",
        )
    await _validate_task_action(
        task_data.task_type,
        task_data.payload,
        current_user=current_user,
        db=db,
    )
    task = await SchedulerService(db).create_task(current_user.id, task_data)
    logger.info("[scheduler] Created task %s: %s", task.id, task.name)
    return _serialize_task(task)


@router.get("/{task_id}", response_model=SchedulerTaskResponse)
async def get_task(
    task_id: str,
    current_user: User = Depends(require_scheduler_reader),
    db: AsyncSession = Depends(get_db),
) -> SchedulerTaskResponse:
    """Get one owned scheduled task without exposing foreign identifiers."""
    try:
        task = await SchedulerService(db).get_owned_task(task_id, current_user.id)
    except SchedulerTaskNotFound as exc:
        raise _task_not_found() from exc
    return _serialize_task(task)


@router.patch("/{task_id}", response_model=SchedulerTaskResponse)
async def update_scheduled_task(
    task_id: str,
    update_data: SchedulerTaskUpdate,
    current_user: User = Depends(require_scheduler_developer),
    db: AsyncSession = Depends(get_db),
) -> SchedulerTaskResponse:
    """Update one owned task under a database row lock."""
    service = SchedulerService(db)
    try:
        task = await service.get_owned_task(task_id, current_user.id, for_update=True)
    except SchedulerTaskNotFound as exc:
        raise _task_not_found() from exc

    changes = update_data.model_dump(exclude_none=True)
    effective_task_type = changes.get("task_type", task.task_type)
    effective_payload = changes.get("payload", task.payload or {})
    await _validate_task_action(
        effective_task_type,
        effective_payload,
        current_user=current_user,
        db=db,
    )
    new_schedule = changes.get("schedule", task.schedule)
    if changes.get("schedule") is not None and new_schedule:
        try:
            croniter.croniter(new_schedule, datetime.now(tz=timezone.utc))
        except (croniter.CroniterBadCronError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid cron expression: {exc}") from exc

    cancel_running = changes.get("enabled") is False and task.active_execution_id is not None
    task = await service.update_task(task, changes)
    execution_task = _execution_tasks.get(str(task.id)) if cancel_running else None
    if execution_task is not None and not execution_task.done():
        execution_task.cancel()
        await asyncio.gather(execution_task, return_exceptions=True)
        task = await service.get_owned_task(task.id, current_user.id)

    logger.info("[scheduler] Updated task %s", task.id)
    return _serialize_task(task)


@router.delete("/{task_id}", status_code=204)
async def delete_scheduled_task(
    task_id: str,
    current_user: User = Depends(require_scheduler_developer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete one owned task without revealing whether a foreign ID exists."""
    service = SchedulerService(db)
    if not await service.delete_task(task_id, current_user.id):
        raise _task_not_found()
    execution_task = _execution_tasks.get(task_id)
    if execution_task is not None and not execution_task.done():
        execution_task.cancel()
        await asyncio.gather(execution_task, return_exceptions=True)
    _execution_tasks.pop(task_id, None)
    _execution_ids.pop(task_id, None)
    logger.info("[scheduler] Deleted task %s", task_id)


async def _wait_for_execution(
    service: SchedulerService,
    *,
    task_id: uuid.UUID,
    owner_id: uuid.UUID,
    execution_id: uuid.UUID,
    timeout_seconds: float = 30,
) -> ScheduledTask:
    deadline = time.monotonic() + timeout_seconds
    while True:
        task = await service.get_owned_task(task_id, owner_id)
        if task.active_execution_id != execution_id or task.status != "running":
            return task
        if time.monotonic() >= deadline:
            raise HTTPException(status_code=409, detail="Task execution is still running")
        await asyncio.sleep(0.05)


@router.post("/{task_id}/trigger", response_model=TriggerTaskResponse)
async def trigger_scheduled_task(
    task_id: str,
    current_user: User = Depends(require_scheduler_developer),
    db: AsyncSession = Depends(get_db),
) -> TriggerTaskResponse:
    """Atomically claim an owned task and return once its durable outcome is known."""
    service = SchedulerService(db)
    try:
        claim = await service.claim_owned_task(task_id, current_user.id)
    except SchedulerTaskNotFound as exc:
        raise _task_not_found() from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    execution_task = None
    if claim.claimed:
        execution_task = _launch_claimed_execution(
            claim,
            session_factory=_session_factory_for(db),
        )
    elif _execution_ids.get(str(claim.task_id)) == str(claim.execution_id):
        execution_task = _execution_tasks.get(str(claim.task_id))

    if execution_task is not None:
        await asyncio.shield(execution_task)
    try:
        completed_task = await _wait_for_execution(
            service,
            task_id=claim.task_id,
            owner_id=current_user.id,
            execution_id=claim.execution_id,
        )
    except SchedulerTaskNotFound as exc:
        raise _task_not_found() from exc

    logger.info(
        "[scheduler] Manually triggered task %s (execution=%s)",
        task_id,
        claim.execution_id,
    )
    if completed_task.status == "failed":
        raise HTTPException(
            status_code=completed_task.last_error_status_code or 500,
            detail=f"Scheduled task execution failed: {completed_task.last_error}",
        )
    return TriggerTaskResponse(
        task_id=str(claim.task_id),
        triggered_at=_timestamp(claim.triggered_at) or 0,
        execution_id=str(claim.execution_id),
        status=completed_task.status,
        completed_at=_timestamp(completed_task.last_finished_at),
    )
