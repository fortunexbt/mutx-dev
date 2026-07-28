"""Canonical SDK event ingestion endpoint at /v1/events.

SDK adapters (LangChain, CrewAI, AutoGen) POST to ``/v1/events``.
This module registers the route at the path the adapters already use,
delegating to the shared ingestion service.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import get_current_user_or_api_key
from src.api.database import get_db
from src.api.models import User
from src.api.models.schemas import IngestEvent
from src.api.services.auth import Role, check_role
from src.api.services.event_ingestion import process_ingest_event

router = APIRouter(tags=["events"])
logger = logging.getLogger(__name__)


async def require_event_developer(
    current_user: User = Depends(get_current_user_or_api_key),
) -> User:
    """Enforce the persisted developer role for JWT and API-key principals."""
    if not check_role(current_user.roles or [], [Role.DEVELOPER]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Required roles: ['DEVELOPER']",
        )
    return current_user


@router.post("/events")
async def ingest_event(
    event_data: IngestEvent,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_event_developer),
):
    """Accept structured events from SDK adapters (LangChain, CrewAI, AutoGen)."""
    return await process_ingest_event(event_data, current_user, db)
