"""Simple analytics event tracking service (quick win for issue #264)"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import AnalyticsEvent
from src.api.models.numeric import reject_non_finite_floats

logger = logging.getLogger(__name__)


# Event type constants
class AnalyticsEventType:
    # Agent lifecycle events
    AGENT_RUN_STARTED = "agent_run.started"
    AGENT_RUN_COMPLETED = "agent_run.completed"
    AGENT_RUN_FAILED = "agent_run.failed"

    # API key events
    API_KEY_CREATED = "api_key.created"
    API_KEY_USED = "api_key.used"
    API_KEY_EXPIRED = "api_key.expired"

    # User events
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"


async def log_analytics_event(
    db: AsyncSession,
    event_name: str,
    event_type: str,
    user_id: Optional[uuid.UUID] = None,
    properties: Optional[dict] = None,
) -> AnalyticsEvent:
    """Log an analytics event to the database.

    Args:
        db: Database session
        event_name: Human-readable event name
        event_type: Event type (use AnalyticsEventType constants)
        user_id: Optional user UUID
        properties: Optional dict of event properties (will be JSON serialized)

    Returns:
        The created AnalyticsEvent
    """
    if properties:
        reject_non_finite_floats(properties, path="$.properties")

    event = AnalyticsEvent(
        event_name=event_name,
        event_type=event_type,
        user_id=user_id,
        properties=json.dumps(properties, allow_nan=False) if properties else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    logger.info(f"Analytics event logged: {event_type} - {event_name}")
    return event


async def get_user_events(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 100,
) -> list[AnalyticsEvent]:
    """Get analytics events for a specific user."""
    result = await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.user_id == user_id)
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_events_by_type(
    db: AsyncSession,
    event_type: str,
    limit: int = 100,
) -> list[AnalyticsEvent]:
    """Get analytics events of a specific type."""
    result = await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.event_type == event_type)
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
