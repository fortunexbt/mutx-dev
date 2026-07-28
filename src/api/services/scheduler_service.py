"""Durable tenant-scoped scheduler storage and execution claiming."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import croniter
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.scheduler import ScheduledTask
from src.api.models.scheduler_schemas import SchedulerTaskCreate

CLAIM_LEASE_SECONDS = 300
STALE_CLAIM_ERROR = "Scheduled task execution claim expired"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def next_run_at(
    *,
    schedule: str | None,
    interval_seconds: int | None,
    base: datetime,
) -> datetime | None:
    """Return the next UTC execution instant for a persisted schedule."""
    normalized_base = as_utc(base)
    assert normalized_base is not None
    if interval_seconds:
        return (normalized_base + timedelta(seconds=interval_seconds)).replace(microsecond=0)
    if not schedule:
        return None
    try:
        next_run = croniter.croniter(schedule, normalized_base).get_next(datetime)
    except (croniter.CroniterBadCronError, ValueError):
        return None
    return as_utc(next_run)


def task_snapshot(task: ScheduledTask) -> dict[str, Any]:
    """Copy only action data that belongs to the claimed task and tenant."""
    return {
        "id": str(task.id),
        "task_type": task.task_type,
        "payload": dict(task.payload or {}),
        "owner_user_id": str(task.owner_id),
    }


@dataclass(frozen=True)
class TaskClaim:
    task_id: uuid.UUID
    execution_id: uuid.UUID
    triggered_at: datetime
    snapshot: dict[str, Any] | None

    @property
    def claimed(self) -> bool:
        return self.snapshot is not None


class SchedulerTaskNotFound(Exception):
    """Raised for missing and foreign task identifiers alike."""


class SchedulerService:
    """Database-backed scheduler repository and claim coordinator."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def parse_task_id(task_id: str | uuid.UUID) -> uuid.UUID | None:
        try:
            return task_id if isinstance(task_id, uuid.UUID) else uuid.UUID(task_id)
        except (TypeError, ValueError):
            return None

    async def list_tasks(self, owner_id: uuid.UUID) -> list[ScheduledTask]:
        return list(
            (
                await self.db.execute(
                    select(ScheduledTask)
                    .where(ScheduledTask.owner_id == owner_id)
                    .order_by(ScheduledTask.created_at, ScheduledTask.id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )

    async def get_owned_task(
        self,
        task_id: str | uuid.UUID,
        owner_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> ScheduledTask:
        parsed_id = self.parse_task_id(task_id)
        if parsed_id is None:
            raise SchedulerTaskNotFound
        statement = (
            select(ScheduledTask)
            .where(
                ScheduledTask.id == parsed_id,
                ScheduledTask.owner_id == owner_id,
            )
            .execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        task = (await self.db.execute(statement)).scalar_one_or_none()
        if task is None:
            raise SchedulerTaskNotFound
        return task

    async def create_task(
        self,
        owner_id: uuid.UUID,
        task_data: SchedulerTaskCreate,
        *,
        now: datetime | None = None,
    ) -> ScheduledTask:
        created_at = as_utc(now) or utc_now()
        task = ScheduledTask(
            owner_id=owner_id,
            name=task_data.name,
            description=task_data.description,
            enabled=task_data.enabled,
            schedule=task_data.schedule,
            interval_seconds=task_data.interval_seconds,
            task_type=task_data.task_type,
            payload=dict(task_data.payload),
            status="scheduled",
            next_run=(
                next_run_at(
                    schedule=task_data.schedule,
                    interval_seconds=task_data.interval_seconds,
                    base=created_at,
                )
                if task_data.enabled
                else None
            ),
            created_at=created_at,
            updated_at=created_at,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update_task(
        self,
        task: ScheduledTask,
        update_data: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> ScheduledTask:
        updated_at = as_utc(now) or utc_now()
        for key, value in update_data.items():
            setattr(task, key, value)
        task.updated_at = updated_at
        base = as_utc(task.last_run) or as_utc(task.created_at) or updated_at
        task.next_run = (
            next_run_at(
                schedule=task.schedule,
                interval_seconds=task.interval_seconds,
                base=base,
            )
            if task.enabled
            else None
        )
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def delete_task(self, task_id: str | uuid.UUID, owner_id: uuid.UUID) -> bool:
        parsed_id = self.parse_task_id(task_id)
        if parsed_id is None:
            return False
        result = await self.db.execute(
            delete(ScheduledTask).where(
                ScheduledTask.id == parsed_id,
                ScheduledTask.owner_id == owner_id,
            )
        )
        await self.db.commit()
        return bool(result.rowcount)

    async def release_stale_claims(
        self,
        *,
        now: datetime | None = None,
        task_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> int:
        released_at = as_utc(now) or utc_now()
        conditions = [
            ScheduledTask.status == "running",
            ScheduledTask.active_execution_id.is_not(None),
            ScheduledTask.claim_expires_at.is_not(None),
            ScheduledTask.claim_expires_at <= released_at,
        ]
        if task_id is not None:
            conditions.append(ScheduledTask.id == task_id)
        if owner_id is not None:
            conditions.append(ScheduledTask.owner_id == owner_id)
        result = await self.db.execute(
            update(ScheduledTask)
            .where(*conditions)
            .values(
                status="failed",
                active_execution_id=None,
                claim_expires_at=None,
                last_finished_at=released_at,
                last_failed_at=released_at,
                failure_count=ScheduledTask.failure_count + 1,
                last_error=STALE_CLAIM_ERROR,
                last_error_code="claim_expired",
                last_error_status_code=500,
                updated_at=released_at,
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        return int(result.rowcount or 0)

    async def _claim_task(
        self,
        task: ScheduledTask,
        *,
        now: datetime,
        require_due: bool,
    ) -> TaskClaim | None:
        execution_id = uuid.uuid4()
        next_run = (
            next_run_at(
                schedule=task.schedule,
                interval_seconds=task.interval_seconds,
                base=now,
            )
            if task.enabled
            else None
        )
        conditions = [
            ScheduledTask.id == task.id,
            ScheduledTask.owner_id == task.owner_id,
            ScheduledTask.active_execution_id.is_(None),
        ]
        if require_due:
            conditions.extend(
                [
                    ScheduledTask.enabled.is_(True),
                    ScheduledTask.next_run.is_not(None),
                    ScheduledTask.next_run <= now,
                ]
            )
        result = await self.db.execute(
            update(ScheduledTask)
            .where(*conditions)
            .values(
                status="running",
                active_execution_id=execution_id,
                claim_expires_at=now + timedelta(seconds=CLAIM_LEASE_SECONDS),
                last_run=now,
                next_run=next_run,
                last_started_at=now,
                last_finished_at=None,
                last_error=None,
                last_error_code=None,
                last_error_status_code=None,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        if not result.rowcount:
            return None
        claimed = (
            await self.db.execute(
                select(ScheduledTask)
                .where(ScheduledTask.id == task.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        return TaskClaim(
            task_id=claimed.id,
            execution_id=execution_id,
            triggered_at=now,
            snapshot=task_snapshot(claimed),
        )

    async def claim_owned_task(
        self,
        task_id: str | uuid.UUID,
        owner_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> TaskClaim:
        triggered_at = as_utc(now) or utc_now()
        parsed_id = self.parse_task_id(task_id)
        if parsed_id is None:
            raise SchedulerTaskNotFound
        await self.release_stale_claims(
            now=triggered_at,
            task_id=parsed_id,
            owner_id=owner_id,
        )
        task = await self.get_owned_task(parsed_id, owner_id)
        existing_execution_id = task.active_execution_id
        if existing_execution_id is not None:
            return TaskClaim(
                task_id=task.id,
                execution_id=existing_execution_id,
                triggered_at=as_utc(task.last_started_at) or triggered_at,
                snapshot=None,
            )

        claim = await self._claim_task(task, now=triggered_at, require_due=False)
        if claim is not None:
            return claim

        concurrent = await self.get_owned_task(parsed_id, owner_id)
        if concurrent.active_execution_id is None:
            raise RuntimeError("Task execution state is inconsistent")
        return TaskClaim(
            task_id=concurrent.id,
            execution_id=concurrent.active_execution_id,
            triggered_at=as_utc(concurrent.last_started_at) or triggered_at,
            snapshot=None,
        )

    async def claim_due_tasks(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[TaskClaim]:
        claimed_at = as_utc(now) or utc_now()
        await self.release_stale_claims(now=claimed_at)
        candidates = list(
            (
                await self.db.execute(
                    select(ScheduledTask)
                    .where(
                        ScheduledTask.enabled.is_(True),
                        ScheduledTask.next_run.is_not(None),
                        ScheduledTask.next_run <= claimed_at,
                        ScheduledTask.active_execution_id.is_(None),
                    )
                    .order_by(ScheduledTask.next_run, ScheduledTask.id)
                    .limit(limit)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        claims: list[TaskClaim] = []
        for candidate in candidates:
            claim = await self._claim_task(candidate, now=claimed_at, require_due=True)
            if claim is not None:
                claims.append(claim)
        return claims

    async def finalize_execution(
        self,
        task_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        error: Exception | None,
        now: datetime | None = None,
    ) -> bool:
        finished_at = as_utc(now) or utc_now()
        values: dict[str, Any] = {
            "active_execution_id": None,
            "claim_expires_at": None,
            "last_finished_at": finished_at,
            "updated_at": finished_at,
        }
        if error is None:
            values.update(
                status="succeeded",
                last_succeeded_at=finished_at,
                run_count=ScheduledTask.run_count + 1,
                success_count=ScheduledTask.success_count + 1,
                last_error=None,
                last_error_code=None,
                last_error_status_code=None,
            )
        else:
            values.update(
                status="failed",
                last_failed_at=finished_at,
                failure_count=ScheduledTask.failure_count + 1,
                last_error=str(error),
                last_error_code=getattr(error, "code", "runtime_error"),
                last_error_status_code=getattr(error, "status_code", 500),
            )
        result = await self.db.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.id == task_id,
                ScheduledTask.active_execution_id == execution_id,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        return bool(result.rowcount)
