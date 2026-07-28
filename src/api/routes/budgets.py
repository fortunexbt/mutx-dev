"""
Budget routes for user credits and usage management.
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import UsageEvent, Agent, User
from src.api.models.numeric import require_finite_float
from src.api.services.billing import get_current_billing_period, get_plan_credits, get_usage_credits

router = APIRouter(prefix="/budgets", tags=["budgets"])
logger = logging.getLogger(__name__)

BILLING_INTEGRITY_ERROR = "Billing data is unavailable because numeric integrity checks failed"


def _billing_value(value: object, *, path: str) -> float:
    try:
        return require_finite_float(value, path=path)
    except (TypeError, ValueError, OverflowError) as exc:
        logger.error("Rejected non-finite billing aggregate at %s", path)
        raise HTTPException(status_code=503, detail=BILLING_INTEGRITY_ERROR) from exc


class BudgetResponse(BaseModel):
    user_id: uuid.UUID
    plan: str
    credits_total: float
    credits_used: float
    credits_remaining: float
    reset_date: datetime
    usage_percentage: float


class UsageByAgent(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    credits_used: float
    event_count: int


class UsageByType(BaseModel):
    event_type: str
    credits_used: float
    event_count: int


class UsageBreakdownResponse(BaseModel):
    total_credits_used: float
    credits_remaining: float
    credits_total: float
    period_start: datetime
    period_end: datetime
    usage_by_agent: list[UsageByAgent]
    usage_by_type: list[UsageByType]


def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _decode_event_metadata(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_uuid(value: Optional[str]) -> uuid.UUID:
    if value:
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            pass
    return uuid.UUID(int=0)


@router.get("", response_model=BudgetResponse)
async def get_budget(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Get the current user's monthly budget and credits."""
    billing_period_start, reset_date = get_current_billing_period()
    try:
        credits_used = await get_usage_credits(
            db,
            current_user.id,
            period_start=billing_period_start,
            period_end=reset_date,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        logger.error("Rejected non-finite billing aggregate for user %s", current_user.id)
        raise HTTPException(status_code=503, detail=BILLING_INTEGRITY_ERROR) from exc

    credits_total = get_plan_credits(current_user.plan)
    credits_remaining = max(0.0, credits_total - credits_used)

    return BudgetResponse(
        user_id=current_user.id,
        plan=current_user.plan,
        credits_total=credits_total,
        credits_used=round(credits_used, 2),
        credits_remaining=round(credits_remaining, 2),
        reset_date=reset_date,
        usage_percentage=round((credits_used / credits_total) * 100, 2) if credits_total > 0 else 0,
    )


@router.get("/usage", response_model=UsageBreakdownResponse)
async def get_usage_breakdown(
    period_start: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Get detailed usage breakdown by agent and event type."""
    now = datetime.now(timezone.utc)

    if period_start == "24h":
        period_start_dt = now - timedelta(hours=24)
    elif period_start == "7d":
        period_start_dt = now - timedelta(days=7)
    elif period_start == "30d":
        period_start_dt = now - timedelta(days=30)
    else:
        period_start_dt = _parse_datetime(period_start) or (now - timedelta(days=30))

    period_end_dt = _parse_datetime(period_end) or now

    date_filter = and_(
        UsageEvent.user_id == current_user.id,
        UsageEvent.created_at >= period_start_dt,
        UsageEvent.created_at < period_end_dt,
    )

    # Validate every source row before grouped SQL aggregates can hide or
    # propagate a legacy non-finite value.
    try:
        total_credits = await get_usage_credits(
            db,
            current_user.id,
            period_start=period_start_dt,
            period_end=period_end_dt,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        logger.error("Rejected non-finite usage source data for user %s", current_user.id)
        raise HTTPException(status_code=503, detail=BILLING_INTEGRITY_ERROR) from exc

    # --- Breakdown by event_type via SQL GROUP BY ---
    type_result = await db.execute(
        select(
            UsageEvent.event_type,
            func.coalesce(func.sum(UsageEvent.credits_used), 0.0),
            func.count(),
        )
        .where(date_filter)
        .group_by(UsageEvent.event_type)
    )
    type_rows = type_result.all()
    usage_by_type = [
        UsageByType(
            event_type=row[0] or "unknown",
            credits_used=round(
                _billing_value(row[1], path=f"$.usage_by_type.{row[0] or 'unknown'}"),
                2,
            ),
            event_count=int(row[2]),
        )
        for row in type_rows
    ]

    # --- Breakdown by agent via SQL GROUP BY on resource_id ---
    # The original code extracted agent_id from event_metadata JSON first,
    # then fell back to resource_id when resource_type == "agent" or
    # event_type starts with "agent_".  Doing JSON parsing inside SQL
    # across heterogeneous databases is fragile, so we use a simpler
    # SQL-level aggregation keyed on (resource_type, resource_id) and
    # post-process in Python only for the metadata-based cases.
    agent_result = await db.execute(
        select(
            UsageEvent.resource_type,
            UsageEvent.resource_id,
            UsageEvent.event_metadata,
            UsageEvent.event_type,
            func.coalesce(func.sum(UsageEvent.credits_used), 0.0),
            func.count(),
        )
        .where(
            and_(
                date_filter,
                UsageEvent.resource_id.isnot(None),
            )
        )
        .group_by(
            UsageEvent.resource_type,
            UsageEvent.resource_id,
            UsageEvent.event_metadata,
            UsageEvent.event_type,
        )
    )
    agent_rows = agent_result.all()

    # Collapse rows into a dict keyed by resolved agent_id string
    agent_usage: dict[str, dict[str, float | int]] = {}
    for resource_type, resource_id, raw_metadata, event_type_val, credits, count in agent_rows:
        metadata = _decode_event_metadata(raw_metadata)
        agent_key = metadata.get("agent_id") if isinstance(metadata.get("agent_id"), str) else None

        if not agent_key and resource_type == "agent" and resource_id:
            agent_key = resource_id

        if not agent_key and event_type_val and event_type_val.startswith("agent_") and resource_id:
            agent_key = resource_id

        if not agent_key:
            continue

        if agent_key not in agent_usage:
            agent_usage[agent_key] = {"credits": 0.0, "count": 0}
        agent_usage[agent_key]["credits"] += _billing_value(
            credits,
            path=f"$.usage_by_agent.{agent_key}",
        )
        agent_usage[agent_key]["count"] += int(count)

    # Batch-resolve agent names (single query instead of N+1)
    agent_uuids = [
        _safe_uuid(agent_id_str)
        for agent_id_str in agent_usage
        if _safe_uuid(agent_id_str).int != 0
    ]

    agent_name_map: dict[uuid.UUID, str] = {}
    if agent_uuids:
        agent_rows_db = await db.execute(
            select(Agent.id, Agent.name).where(
                Agent.id.in_(agent_uuids),
                Agent.user_id == current_user.id,
            )
        )
        for row in agent_rows_db.all():
            agent_name_map[row[0]] = row[1]

    usage_by_agent = []
    for agent_id_str, data in agent_usage.items():
        agent_uuid = _safe_uuid(agent_id_str)
        if agent_uuid in agent_name_map:
            agent_name = agent_name_map[agent_uuid]
        elif agent_uuid.int != 0:
            agent_name = f"Unknown agent ({str(agent_uuid)[:8]})"
        else:
            agent_name = f"Unscoped usage ({str(agent_uuid)[:8]})"

        usage_by_agent.append(
            UsageByAgent(
                agent_id=agent_uuid,
                agent_name=agent_name,
                credits_used=round(float(data["credits"]), 2),
                event_count=int(data["count"]),
            )
        )

    credits_total = get_plan_credits(current_user.plan)

    return UsageBreakdownResponse(
        total_credits_used=round(total_credits, 2),
        credits_remaining=max(0, credits_total - total_credits),
        credits_total=credits_total,
        period_start=period_start_dt,
        period_end=period_end_dt,
        usage_by_agent=sorted(usage_by_agent, key=lambda x: x.credits_used, reverse=True),
        usage_by_type=sorted(usage_by_type, key=lambda x: x.credits_used, reverse=True),
    )
