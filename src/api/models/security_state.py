"""Durable evidence models for the legacy runtime-security API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.api.database import Base


class SecurityEvaluation(Base):
    """An owner-bound policy evaluation with its public action provenance."""

    __tablename__ = "security_evaluations"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_security_evaluations_id_owner"),
        UniqueConstraint(
            "owner_id",
            "action_id",
            name="uq_security_evaluations_owner_action",
        ),
        Index(
            "ix_security_evaluations_owner_session_created",
            "owner_id",
            "session_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(180), nullable=False)
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_args: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    trigger: Mapped[str] = mapped_column(String(120), nullable=False)
    runtime: Mapped[str] = mapped_column(String(120), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_rule_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    policy_rule_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False)
    would_modify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class SecurityReceipt(Base):
    """A durable, owner-keyed serialized action receipt."""

    __tablename__ = "security_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["evaluation_id", "owner_id"],
            ["security_evaluations.id", "security_evaluations.owner_id"],
            name="fk_security_receipts_evaluation_owner",
            ondelete="CASCADE",
        ),
        Index(
            "ix_security_receipts_owner_session_timestamp",
            "owner_id",
            "session_id",
            "timestamp",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(180), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
