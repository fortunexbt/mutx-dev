"""
Monitoring routes for system health and alerts.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_db
from src.api.auth.dependencies import get_current_internal_user, require_roles
from src.api.models import Alert, AlertType, Agent, User
from src.api.models.numeric import DegradedNumericResponseModel

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
logger = logging.getLogger(__name__)


# Response schemas
class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    type: AlertType
    message: str
    resolved: bool
    created_at: datetime
    resolved_at: Optional[datetime] = None


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    total: int
    unresolved_count: int
    skip: int
    limit: int
    has_more: bool


class AlertResolveRequest(BaseModel):
    resolved: bool = True


class HealthStatusResponse(DegradedNumericResponseModel):
    status: str
    timestamp: datetime
    database: str
    uptime_seconds: float | None
    version: str = "1.0.0"


def _serialize_alert(alert: Alert) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        agent_id=alert.agent_id,
        type=alert.type,
        message=alert.message,
        resolved=alert.resolved,
        created_at=alert.created_at,
        resolved_at=alert.resolved_at,
    )


async def require_internal_monitoring_admin(
    current_user: User = Depends(require_roles("ADMIN")),
    _internal_user: User = Depends(get_current_internal_user),
) -> User:
    """Restrict global platform health details to internal administrators."""
    return current_user


@router.get("/health", response_model=HealthStatusResponse)
async def get_health(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_internal_monitoring_admin),
):
    """Get authenticated platform health details."""
    # Check database connectivity
    db_status = "healthy"
    try:
        await db.execute(select(1))
    except Exception:
        db_status = "unhealthy"

    start_time = getattr(request.app.state, "start_time", None)
    uptime = datetime.now(timezone.utc).timestamp() - start_time if start_time is not None else 0.0

    return HealthStatusResponse(
        status=db_status,
        timestamp=datetime.now(timezone.utc),
        database=db_status,
        uptime_seconds=uptime,
    )


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    agent_id: Optional[uuid.UUID] = Query(None),
    resolved: Optional[bool] = Query(None),
    alert_type: Optional[AlertType] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """List alerts for the user's agents."""
    # Filter by user's agents
    agent_subquery = select(Agent.id).where(Agent.user_id == current_user.id)

    query = select(Alert).where(Alert.agent_id.in_(agent_subquery))

    if agent_id:
        # Verify ownership
        agent_result = await db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.user_id == current_user.id)
        )
        if not agent_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Agent not found")
        query = query.where(Alert.agent_id == agent_id)

    if resolved is not None:
        query = query.where(Alert.resolved == resolved)

    if alert_type:
        query = query.where(Alert.type == alert_type)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one() or 0

    # Get unresolved count
    unresolved_query = (
        select(func.count())
        .select_from(Alert)
        .where(and_(Alert.agent_id.in_(agent_subquery), Alert.resolved.is_(False)))
    )
    unresolved_count = (await db.execute(unresolved_query)).scalar_one() or 0

    # Apply pagination
    query = query.order_by(Alert.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    alerts = result.scalars().all()

    return AlertListResponse(
        items=[_serialize_alert(a) for a in alerts],
        total=total,
        unresolved_count=unresolved_count,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(alerts),
    )


@router.patch("/alerts/{alert_id}", response_model=AlertResponse)
async def resolve_alert(
    alert_id: uuid.UUID,
    resolve_data: AlertResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Resolve or unresolve an alert."""
    # Verify alert belongs to user's agent
    alert_result = await db.execute(
        select(Alert)
        .join(Agent, Alert.agent_id == Agent.id)
        .where(Alert.id == alert_id, Agent.user_id == current_user.id)
    )
    alert = alert_result.scalar_one_or_none()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.resolved = resolve_data.resolved
    if resolve_data.resolved:
        alert.resolved_at = datetime.now(timezone.utc)
    else:
        alert.resolved_at = None

    await db.commit()
    await db.refresh(alert)

    logger.info(f"Alert {alert_id} resolved: {resolve_data.resolved}")
    return _serialize_alert(alert)
