"""Neutral approval DTOs and webhook transport helpers.

Approval state is stored in the canonical ``approval_requests`` table.  This
module intentionally contains no process-local approval store.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    """Possible states for an approval request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ApprovalRequest(BaseModel):
    """Public representation of a canonical approval request."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    owner_id: uuid.UUID
    reviewer_id: uuid.UUID | None
    can_resolve: bool
    agent_id: str
    session_id: str
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    requester: str
    approver: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    comment: str | None = None

    model_config = {"use_enum_values": True}


async def post_approval_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    delivery_id: str | None = None,
) -> None:
    """POST one outbox event and raise when the destination rejects it."""
    headers = {"Idempotency-Key": delivery_id} if delivery_id else None
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()


__all__ = [
    "ApprovalRequest",
    "ApprovalStatus",
    "post_approval_webhook",
]
