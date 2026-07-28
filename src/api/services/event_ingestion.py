"""Shared event ingestion logic for SDK adapter events.

Used by both ``/v1/events`` and ``/v1/ingest/events`` route handlers so
that the ingestion contract, ownership checks, and audit-log persistence
stay in one place.
"""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import Agent, AgentLog, User
from src.api.models.schemas import IngestEvent
from src.api.models.numeric import reject_non_finite_floats

logger = logging.getLogger(__name__)


async def process_ingest_event(
    event_data: IngestEvent,
    current_user: User,
    db: AsyncSession,
) -> dict[str, str]:
    """Validate, authorize, and persist an SDK adapter event.

    Returns a JSON-serializable dict suitable as the route response.
    """
    resolved_agent_id = event_data.agent_id
    reject_non_finite_floats(event_data.payload, path="$.payload")

    # If an agent_id is provided, verify ownership and persist as AgentLog
    if resolved_agent_id is not None:
        result = await db.execute(
            select(Agent).where(
                Agent.id == resolved_agent_id,
                Agent.user_id == current_user.id,
            )
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        log = AgentLog(
            agent_id=resolved_agent_id,
            level="info",
            message=f"Adapter event: {event_data.event_type}",
            extra_data=json.dumps(event_data.payload, default=str, allow_nan=False),
            meta_data={
                "event_type": event_data.event_type,
                "adapter_timestamp": event_data.timestamp,
                "agent_id": str(resolved_agent_id),
            },
        )
        db.add(log)
        await db.commit()

    logger.info(
        "Ingested event type=%s user=%s agent=%s",
        event_data.event_type,
        current_user.id,
        resolved_agent_id,
    )
    return {"status": "accepted", "event_type": event_data.event_type}
