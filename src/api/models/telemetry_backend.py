"""Durable, tenant-owned telemetry backend configuration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.api.database import Base


class TelemetryBackendConfig(Base):
    """One persisted collector target per MUTX tenant principal."""

    __tablename__ = "telemetry_backend_configs"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            name="uq_telemetry_backend_configs_owner_id",
        ),
        CheckConstraint(
            "protocol IN ('grpc', 'http')",
            name="ck_telemetry_backend_configs_protocol",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(String(2048), nullable=False)
    protocol: Mapped[str] = mapped_column(String(8), nullable=False)
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
