from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.api.database import Base


class RagIndex(Base):
    """Durable tenant-owned vector index configuration."""

    __tablename__ = "rag_indexes"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_rag_indexes_id_owner"),
        UniqueConstraint("owner_id", "name", name="uq_rag_indexes_owner_name"),
        Index("ix_rag_indexes_owner_created_at", "owner_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_backend: Mapped[str] = mapped_column(String(40), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class RagDocument(Base):
    """Durable document embedding explicitly owned by one tenant."""

    __tablename__ = "rag_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["index_id", "owner_id"],
            ["rag_indexes.id", "rag_indexes.owner_id"],
            name="fk_rag_documents_index_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "index_id",
            "external_id",
            name="uq_rag_documents_index_external_id",
        ),
        Index("ix_rag_documents_owner_index", "owner_id", "index_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    index_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
