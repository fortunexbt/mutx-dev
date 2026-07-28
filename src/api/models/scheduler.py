"""Durable scheduler persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.api.database import Base


class ScheduledTask(Base):
    """A tenant-owned task and its latest durable execution state."""

    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        CheckConstraint(
            "schedule IS NOT NULL OR interval_seconds IS NOT NULL",
            name="ck_scheduled_tasks_has_schedule",
        ),
        CheckConstraint(
            "task_type IN ('log', 'webhook', 'agent_heartbeat')",
            name="ck_scheduled_tasks_task_type",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'running', 'succeeded', 'failed')",
            name="ck_scheduled_tasks_status",
        ),
        Index("ix_scheduled_tasks_owner_created_at", "owner_id", "created_at"),
        Index("ix_scheduled_tasks_due", "enabled", "next_run"),
        Index("ix_scheduled_tasks_claim_expires_at", "claim_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False, default="log")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled")
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_succeeded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
