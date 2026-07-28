import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import Agent, AgentRun, Deployment, UsageEvent, Metrics, AgentMetric, User
from src.api.models.schemas import (
    AnalyticsSummaryResponse,
    AgentMetricsSummary,
    AnalyticsTimeSeriesResponse,
    AnalyticsTimeSeries,
    CostSummaryResponse,
    BudgetResponse,
)
from src.api.models.numeric import require_finite_float
from src.api.services.billing import get_current_billing_period, get_plan_credits, get_usage_credits

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)

BILLING_INTEGRITY_ERROR = "Billing data is unavailable because numeric integrity checks failed"


def _nullable_metric(value: object) -> tuple[float | None, bool]:
    if value is None:
        return None, False
    try:
        return require_finite_float(value, path="$.analytics.metric"), False
    except (TypeError, ValueError, OverflowError):
        return None, True


def _average_metric(
    values: list[object],
    *,
    empty_value: float | None,
) -> tuple[float | None, bool]:
    finite_values: list[float] = []
    for value in values:
        if value is None:
            continue
        finite_value, incomplete = _nullable_metric(value)
        if incomplete or finite_value is None:
            return None, True
        finite_values.append(finite_value)

    if not finite_values:
        return empty_value, False
    return _nullable_metric(sum(finite_values) / len(finite_values))


def _billing_value(value: object, *, path: str) -> float:
    try:
        return require_finite_float(value, path=path)
    except (TypeError, ValueError, OverflowError) as exc:
        logger.error("Rejected non-finite billing aggregate at %s", path)
        raise HTTPException(status_code=503, detail=BILLING_INTEGRITY_ERROR) from exc


def _parse_datetime(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _resolve_period(
    period_start: Optional[str],
    period_end: Optional[str],
    *,
    default_days: int = 30,
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if period_start == "24h":
        period_start_dt = now - timedelta(hours=24)
    elif period_start == "7d":
        period_start_dt = now - timedelta(days=7)
    elif period_start == "30d":
        period_start_dt = now - timedelta(days=30)
    else:
        period_start_dt = _parse_datetime(period_start) or (now - timedelta(days=default_days))

    period_end_dt = _parse_datetime(period_end) or now
    return period_start_dt, period_end_dt


def _decode_event_metadata(raw: Optional[str]) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _resolve_usage_agent_key(
    *,
    event_type: str,
    resource_type: Optional[str],
    resource_id: Optional[str],
    event_metadata: Optional[str],
    owned_agent_ids: set[str],
) -> str | None:
    metadata = _decode_event_metadata(event_metadata)
    metadata_agent_id = metadata.get("agent_id")
    if isinstance(metadata_agent_id, str) and metadata_agent_id in owned_agent_ids:
        return metadata_agent_id

    if resource_type == "agent" and resource_id in owned_agent_ids:
        return resource_id

    if event_type.startswith("agent_") and resource_id in owned_agent_ids:
        return resource_id

    return None


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    period_start: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    period_start_dt, period_end_dt = _resolve_period(period_start, period_end)

    agent_query = select(Agent.id, Agent.status).where(Agent.user_id == current_user.id)
    agent_result = await db.execute(agent_query)
    agent_rows = agent_result.all()
    agent_ids = [row.id for row in agent_rows]

    total_agents = len(agent_rows)
    active_agents = sum(1 for row in agent_rows if row.status == "running")

    if agent_ids:
        total_deployments = (
            await db.execute(
                select(func.count())
                .select_from(Deployment)
                .where(Deployment.agent_id.in_(agent_ids))
            )
        ).scalar_one() or 0

        active_deployments = (
            await db.execute(
                select(func.count())
                .select_from(Deployment)
                .where(
                    Deployment.agent_id.in_(agent_ids),
                    Deployment.status.in_(["running", "ready", "deploying"]),
                )
            )
        ).scalar_one() or 0
    else:
        total_deployments = active_deployments = 0

    if agent_ids:
        status_rows = (
            await db.execute(
                select(AgentRun.status, func.count().label("count"))
                .where(
                    and_(
                        AgentRun.agent_id.in_(agent_ids),
                        AgentRun.started_at >= period_start_dt,
                        AgentRun.started_at <= period_end_dt,
                    )
                )
                .group_by(AgentRun.status)
            )
        ).all()
        status_counts = {row.status: row.count for row in status_rows}
        total_runs = sum(status_counts.values())
        successful_runs = status_counts.get("completed", 0)
        failed_runs = status_counts.get("failed", 0)
    else:
        total_runs = successful_runs = failed_runs = 0

    api_call_query = (
        select(func.count())
        .select_from(UsageEvent)
        .where(
            and_(
                UsageEvent.user_id == current_user.id,
                UsageEvent.event_type == "api_call",
                UsageEvent.created_at >= period_start_dt,
                UsageEvent.created_at <= period_end_dt,
            )
        )
    )
    total_api_calls = (await db.execute(api_call_query)).scalar_one() or 0

    avg_latency_ms: float | None = 0.0
    incomplete = False
    if agent_ids:
        latency_query = select(Metrics.latency).where(
            and_(
                Metrics.agent_id.in_(agent_ids),
                Metrics.timestamp >= period_start_dt,
                Metrics.timestamp <= period_end_dt,
            )
        )
        result = await db.execute(latency_query)
        avg_latency_ms, incomplete = _average_metric(
            list(result.scalars()),
            empty_value=0.0,
        )

    return AnalyticsSummaryResponse(
        total_agents=total_agents,
        active_agents=active_agents,
        total_deployments=total_deployments,
        active_deployments=active_deployments,
        total_runs=total_runs,
        successful_runs=successful_runs,
        failed_runs=failed_runs,
        total_api_calls=total_api_calls,
        avg_latency_ms=round(avg_latency_ms, 2) if avg_latency_ms is not None else None,
        period_start=period_start_dt,
        period_end=period_end_dt,
        incomplete=incomplete,
    )


@router.get("/agents/{agent_id}/summary", response_model=AgentMetricsSummary)
async def get_agent_metrics_summary(
    agent_id: uuid.UUID,
    period_start: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    from fastapi import HTTPException

    agent_result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == current_user.id)
    )
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

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

    run_status_rows = (
        await db.execute(
            select(AgentRun.status, func.count().label("count"))
            .where(
                and_(
                    AgentRun.agent_id == agent_id,
                    AgentRun.started_at >= period_start_dt,
                    AgentRun.started_at <= period_end_dt,
                )
            )
            .group_by(AgentRun.status)
        )
    ).all()
    status_counts = {row.status: row.count for row in run_status_rows}
    total_runs = sum(status_counts.values())
    successful_runs = status_counts.get("completed", 0)
    failed_runs = status_counts.get("failed", 0)

    avg_cpu_result = (
        (
            await db.execute(
                select(AgentMetric.cpu_usage).where(
                    and_(
                        AgentMetric.agent_id == agent_id,
                        AgentMetric.timestamp >= period_start_dt,
                        AgentMetric.timestamp <= period_end_dt,
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    avg_cpu, cpu_incomplete = _average_metric(list(avg_cpu_result), empty_value=None)
    if avg_cpu is not None:
        avg_cpu = round(avg_cpu, 2)

    avg_memory_result = (
        (
            await db.execute(
                select(AgentMetric.memory_usage).where(
                    and_(
                        AgentMetric.agent_id == agent_id,
                        AgentMetric.timestamp >= period_start_dt,
                        AgentMetric.timestamp <= period_end_dt,
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    avg_memory, memory_incomplete = _average_metric(list(avg_memory_result), empty_value=None)
    if avg_memory is not None:
        avg_memory = round(avg_memory, 2)

    total_requests = (
        await db.execute(
            select(func.coalesce(func.sum(Metrics.requests), 0)).where(
                and_(
                    Metrics.agent_id == agent_id,
                    Metrics.timestamp >= period_start_dt,
                    Metrics.timestamp <= period_end_dt,
                )
            )
        )
    ).scalar_one()

    avg_latency_result = (
        (
            await db.execute(
                select(Metrics.latency).where(
                    and_(
                        Metrics.agent_id == agent_id,
                        Metrics.timestamp >= period_start_dt,
                        Metrics.timestamp <= period_end_dt,
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    avg_latency, latency_incomplete = _average_metric(list(avg_latency_result), empty_value=None)
    if avg_latency is not None:
        avg_latency = round(avg_latency, 2)

    return AgentMetricsSummary(
        agent_id=agent_id,
        agent_name=agent.name,
        total_runs=total_runs,
        successful_runs=successful_runs,
        failed_runs=failed_runs,
        avg_cpu=avg_cpu,
        avg_memory=avg_memory,
        total_requests=total_requests,
        avg_latency_ms=avg_latency,
        period_start=period_start_dt,
        period_end=period_end_dt,
        incomplete=cpu_incomplete or memory_incomplete or latency_incomplete,
    )


@router.get("/timeseries", response_model=AnalyticsTimeSeriesResponse)
async def get_analytics_timeseries(
    metric: str = Query(...),
    interval: str = Query("hour"),
    period_start: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None),
    agent_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
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

    data = []
    incomplete = False
    if metric == "runs":
        q = select(
            func.date_trunc(interval, AgentRun.started_at).label("ts"), func.count().label("count")
        ).where(
            and_(
                AgentRun.user_id == current_user.id,
                AgentRun.started_at >= period_start_dt,
                AgentRun.started_at <= period_end_dt,
            )
        )
        if agent_id:
            q = q.where(AgentRun.agent_id == agent_id)
        q = q.group_by("ts").order_by("ts")
        for row in await db.execute(q):
            data.append(
                AnalyticsTimeSeries(
                    timestamp=row.ts.replace(tzinfo=timezone.utc) if row.ts else now,
                    value=row.count,
                )
            )
    elif metric == "api_calls":
        q = select(
            func.date_trunc(interval, UsageEvent.created_at).label("ts"),
            func.count().label("count"),
        ).where(
            and_(
                UsageEvent.user_id == current_user.id,
                UsageEvent.event_type == "api_call",
                UsageEvent.created_at >= period_start_dt,
                UsageEvent.created_at <= period_end_dt,
            )
        )
        q = q.group_by("ts").order_by("ts")
        for row in await db.execute(q):
            data.append(
                AnalyticsTimeSeries(
                    timestamp=row.ts.replace(tzinfo=timezone.utc) if row.ts else now,
                    value=row.count,
                )
            )
    elif metric == "latency":
        latency_filter = and_(
            Agent.user_id == current_user.id,
            Metrics.timestamp >= period_start_dt,
            Metrics.timestamp <= period_end_dt,
        )
        source_values_query = (
            select(Metrics.latency).join(Agent, Agent.id == Metrics.agent_id).where(latency_filter)
        )
        if agent_id:
            source_values_query = source_values_query.where(Metrics.agent_id == agent_id)
        source_result = await db.execute(source_values_query)
        if hasattr(source_result, "scalars"):
            source_values = source_result.scalars().all()
        else:
            # Lightweight route-test doubles may only implement row iteration.
            source_values = [
                getattr(row, "latency", getattr(row, "avg", None)) for row in source_result
            ]
        _, source_incomplete = _average_metric(list(source_values), empty_value=None)
        incomplete = incomplete or source_incomplete

        q = (
            select(
                func.date_trunc(interval, Metrics.timestamp).label("ts"),
                func.avg(Metrics.latency).label("avg"),
            )
            .join(Agent, Agent.id == Metrics.agent_id)
            .where(latency_filter)
        )
        if agent_id:
            q = q.where(Metrics.agent_id == agent_id)
        q = q.group_by("ts").order_by("ts")
        for row in await db.execute(q):
            value, value_incomplete = _nullable_metric(row.avg)
            incomplete = incomplete or value_incomplete
            data.append(
                AnalyticsTimeSeries(
                    timestamp=row.ts.replace(tzinfo=timezone.utc) if row.ts else now,
                    value=round(value, 2) if value is not None else None,
                )
            )

    return AnalyticsTimeSeriesResponse(
        metric=metric,
        interval=interval,
        data=data,
        period_start=period_start_dt,
        period_end=period_end_dt,
        incomplete=incomplete,
    )


@router.get("/costs", response_model=CostSummaryResponse)
async def get_cost_summary(
    period_start: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    period_start_dt, period_end_dt = _resolve_period(period_start, period_end)

    period_filter = and_(
        UsageEvent.user_id == current_user.id,
        UsageEvent.created_at >= period_start_dt,
        UsageEvent.created_at < period_end_dt,
    )

    # Billing totals validate each source row before any SQL aggregate can hide
    # a legacy NaN as NULL or propagate Infinity.
    try:
        total_credits = await get_usage_credits(
            db,
            current_user.id,
            period_start=period_start_dt,
            period_end=period_end_dt,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        logger.error("Rejected non-finite cost source data for user %s", current_user.id)
        raise HTTPException(status_code=503, detail=BILLING_INTEGRITY_ERROR) from exc

    # Credits grouped by event_type via SQL aggregate
    event_type_rows = (
        await db.execute(
            select(
                UsageEvent.event_type,
                func.coalesce(func.sum(UsageEvent.credits_used), 0.0).label("total"),
            )
            .where(period_filter)
            .group_by(UsageEvent.event_type)
        )
    ).all()
    usage_by_event_type = {
        (row.event_type or "unknown"): round(
            _billing_value(row.total, path=f"$.usage_by_event_type.{row.event_type or 'unknown'}"),
            2,
        )
        for row in event_type_rows
    }

    # Agent breakdown: select only the columns needed for _resolve_usage_agent_key
    # instead of loading full ORM objects
    agent_result = await db.execute(select(Agent.id).where(Agent.user_id == current_user.id))
    owned_agent_ids = {str(agent_id) for agent_id in agent_result.scalars().all()}

    usage_by_agent: dict[str, float] = {}
    agent_key_rows = (
        await db.execute(
            select(
                UsageEvent.event_type,
                UsageEvent.resource_type,
                UsageEvent.resource_id,
                UsageEvent.event_metadata,
                UsageEvent.credits_used,
            ).where(period_filter)
        )
    ).all()

    for row in agent_key_rows:
        agent_key = _resolve_usage_agent_key(
            event_type=row.event_type or "",
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            event_metadata=row.event_metadata,
            owned_agent_ids=owned_agent_ids,
        )
        if agent_key:
            usage_by_agent[agent_key] = usage_by_agent.get(agent_key, 0.0) + _billing_value(
                row.credits_used,
                path=f"$.usage_by_agent.{agent_key}",
            )

    credits_total = get_plan_credits(current_user.plan)
    finite_total_credits = _billing_value(total_credits, path="$.total_credits_used")

    return CostSummaryResponse(
        total_credits_used=round(finite_total_credits, 2),
        credits_remaining=round(max(0.0, credits_total - finite_total_credits), 2),
        credits_total=credits_total,
        usage_by_event_type=usage_by_event_type,
        usage_by_agent={key: round(value, 2) for key, value in usage_by_agent.items()},
        period_start=period_start_dt,
        period_end=period_end_dt,
    )


@router.get("/budget", response_model=BudgetResponse)
async def get_budget(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
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


# ── Revenue & Subscription Analytics (internal) ─────────────────────


@router.get("/revenue")
async def get_revenue_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Revenue overview — MRR, active subs, payments. Internal users only."""
    from src.api.auth.dependencies import assert_internal_user

    assert_internal_user(current_user)

    from src.api.models.subscription import Subscription, Payment

    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    # Active subscriptions count by plan
    active_subs = await db.execute(
        select(Subscription.plan, func.count(Subscription.id))
        .where(Subscription.status.in_(["active", "trialing"]))
        .group_by(Subscription.plan)
    )
    subs_by_plan = {plan: count for plan, count in active_subs.all()}

    # MRR: sum payments this month
    mrr_result = await db.execute(
        select(func.sum(Payment.amount_cents)).where(
            Payment.status == "paid", Payment.created_at >= month_start
        )
    )
    mrr_cents = mrr_result.scalar_one() or 0

    # Total payments this month
    payment_count = await db.execute(
        select(func.count(Payment.id)).where(
            Payment.status == "paid", Payment.created_at >= month_start
        )
    )
    total_payments = payment_count.scalar_one() or 0

    # Total users
    total_users = await db.execute(select(func.count(User.id)))

    # New users this month
    new_users = await db.execute(select(func.count(User.id)).where(User.created_at >= month_start))

    return {
        "mrr_cents": mrr_cents,
        "mrr_usd": round(mrr_cents / 100, 2),
        "active_subscriptions": subs_by_plan,
        "total_active_subs": sum(subs_by_plan.values()),
        "payments_this_month": total_payments,
        "total_users": total_users.scalar_one() or 0,
        "new_users_this_month": new_users.scalar_one() or 0,
    }


@router.get("/subscriptions")
async def get_subscriptions_list(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """List subscriptions with user info. Internal users only."""
    from src.api.auth.dependencies import assert_internal_user

    assert_internal_user(current_user)

    from src.api.models.subscription import Subscription

    query = (
        select(Subscription, User.email, User.name)
        .join(User, Subscription.user_id == User.id)
        .order_by(Subscription.created_at.desc())
    )
    if status_filter:
        query = query.where(Subscription.status == status_filter)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)

    rows = result.all()
    return {
        "subscriptions": [
            {
                "id": str(sub.id),
                "user_email": email,
                "user_name": name,
                "plan": sub.plan,
                "status": sub.status,
                "stripe_customer_id": sub.stripe_customer_id,
                "current_period_end": sub.current_period_end.isoformat()
                if sub.current_period_end
                else None,
                "cancel_at_period_end": sub.cancel_at_period_end,
                "created_at": sub.created_at.isoformat() if sub.created_at else None,
            }
            for sub, email, name in rows
        ],
        "count": len(rows),
    }


@router.get("/payments")
async def get_payments_list(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """List recent payments. Internal users only."""
    from src.api.auth.dependencies import assert_internal_user

    assert_internal_user(current_user)

    from src.api.models.subscription import Payment

    result = await db.execute(
        select(Payment, User.email)
        .join(User, Payment.user_id == User.id)
        .order_by(Payment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    rows = result.all()
    return {
        "payments": [
            {
                "id": str(pay.id),
                "user_email": email,
                "stripe_invoice_id": pay.stripe_invoice_id,
                "amount_cents": pay.amount_cents,
                "currency": pay.currency,
                "status": pay.status,
                "created_at": pay.created_at.isoformat() if pay.created_at else None,
            }
            for pay, email in rows
        ],
        "count": len(rows),
    }
