"""Usage tracking service for quota and billing."""

import json
import logging
import uuid

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api import database as database_module
from src.api.models.models import UsageEvent
from src.api.models.numeric import reject_non_finite_floats, require_finite_float

logger = logging.getLogger(__name__)


def _encode_metadata(metadata: Optional[dict[str, Any]]) -> Optional[str]:
    if not metadata:
        return None
    reject_non_finite_floats(metadata, path="$.metadata")
    return json.dumps(metadata, allow_nan=False)


async def track_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
    event_type: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    credits_used: float = 1.0,
) -> UsageEvent:
    """Add a usage event to the current session."""
    finite_credits = require_finite_float(credits_used, path="$.credits_used")
    if finite_credits < 0:
        raise ValueError("credits_used must be non-negative")

    # Convert UUID to string for SQLite compatibility
    resource_id_str = str(resource_id) if resource_id else None
    event = UsageEvent(
        user_id=user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id_str,
        event_metadata=_encode_metadata(metadata),
        credits_used=finite_credits,
    )
    db.add(event)
    return event


async def track_usage_best_effort(
    *,
    db: AsyncSession | None = None,
    user_id: uuid.UUID,
    event_type: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    credits_used: float = 1.0,
) -> bool:
    """Persist a usage event without failing the primary request path."""
    try:
        session_factory = database_module.async_session_maker
        if db is not None and db.bind is not None:
            session_factory = async_sessionmaker(
                db.bind,
                class_=AsyncSession,
                expire_on_commit=False,
            )

        async with session_factory() as session:
            await track_usage(
                session,
                user_id=user_id,
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                metadata=metadata,
                credits_used=credits_used,
            )
            await session.commit()
        return True
    except Exception:
        logger.warning(
            "Usage tracking failed",
            exc_info=True,
            extra={
                "user_id": str(user_id),
                "event_type": event_type,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id else None,
            },
        )
        return False
