"""Billing helpers for plan credits and usage windows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import UsageEvent
from src.api.models.numeric import require_finite_float
from src.api.models.plan_tiers import PlanTier

PLAN_CREDITS: dict[PlanTier, float] = {
    PlanTier.FREE: 100.0,
    PlanTier.STARTER: 1000.0,
    PlanTier.PRO: 10000.0,
    PlanTier.ENTERPRISE: 100000.0,
}


def get_plan_credits(plan: PlanTier | str | None) -> float:
    """Return the monthly credit allocation for a plan tier."""
    if plan is None:
        return PLAN_CREDITS[PlanTier.FREE]

    try:
        tier = plan if isinstance(plan, PlanTier) else PlanTier(str(plan))
    except ValueError:
        return PLAN_CREDITS[PlanTier.FREE]

    return PLAN_CREDITS.get(tier, PLAN_CREDITS[PlanTier.FREE])


def get_current_billing_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the current monthly billing window as a half-open interval."""
    reference = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    period_start = datetime(reference.year, reference.month, 1, tzinfo=timezone.utc)

    if reference.month == 12:
        period_end = datetime(reference.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        period_end = datetime(reference.year, reference.month + 1, 1, tzinfo=timezone.utc)

    return period_start, period_end


async def get_usage_credits(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> float:
    """Sum usage credits for a user, optionally within a time window."""
    filters = [UsageEvent.user_id == user_id]

    if period_start is not None:
        filters.append(UsageEvent.created_at >= period_start)
    if period_end is not None:
        filters.append(UsageEvent.created_at < period_end)

    result = await db.execute(select(UsageEvent.credits_used).where(and_(*filters)))
    total = 0.0
    for index, raw_credits in enumerate(result.scalars()):
        total += require_finite_float(
            raw_credits,
            path=f"$.billing.events[{index}].credits_used",
        )
    return require_finite_float(total, path="$.billing.credits_used")
