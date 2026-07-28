import json
import logging
from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.auth.ownership import (
    get_owned_agent as _get_owned_agent,
    get_owned_deployment as _get_owned_deployment,
)
from src.api.database import get_db
from src.api.models import (
    Deployment,
    Agent,
    AgentStatus,
    User,
    AgentLog,
    AgentMetric,
    DeploymentEvent as DeploymentEventModel,
    DeploymentVersion,
)
from src.api.models.schemas import (
    DeploymentListResponse,
    DeploymentResponse,
    DeploymentScale,
    DeploymentCreate,
    DeploymentEventHistoryResponse,
    DeploymentLogsHistoryResponse,
    DeploymentMetricsHistoryResponse,
    DeploymentVersionHistoryResponse,
    DeploymentRollbackRequest,
    deployment_allowed_actions,
)
from src.api.auth.dependencies import require_roles
from src.api.services.deployment_lifecycle import create_deployment_record
from src.api.services.usage import track_usage_best_effort
from src.api.time_utils import utc_now_naive

router = APIRouter(prefix="/deployments", tags=["deployments"])
logger = logging.getLogger(__name__)


async def get_owned_agent(
    agent_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
    **kwargs: Any,
) -> Agent:
    """Resolve agent ownership without disclosing cross-tenant existence."""
    try:
        return await _get_owned_agent(agent_id, db, current_user, **kwargs)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        raise HTTPException(
            status_code=404,
            detail=kwargs.get("not_found_detail", "Agent not found"),
        ) from None


async def get_owned_deployment(
    deployment_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
    **kwargs: Any,
) -> Deployment:
    """Resolve deployment ownership without disclosing cross-tenant existence."""
    try:
        return await _get_owned_deployment(deployment_id, db, current_user, **kwargs)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        raise HTTPException(
            status_code=404,
            detail=kwargs.get("not_found_detail", "Deployment not found"),
        ) from None


ACTIVE_DEPLOYMENT_STATUSES = frozenset({"pending", "deploying", "running", "ready"})
RUNNING_DEPLOYMENT_STATUSES = frozenset({"running", "ready"})
RESTARTABLE_DEPLOYMENT_STATUSES = frozenset({"running", "ready", "failed"})


def _serialize_deployment(deployment: Deployment) -> dict[str, object]:
    return {
        "id": deployment.id,
        "agent_id": deployment.agent_id,
        "status": deployment.status,
        "version": deployment.version,
        "replicas": deployment.replicas,
        "node_id": deployment.node_id,
        "started_at": deployment.started_at,
        "ended_at": deployment.ended_at,
        "error_message": deployment.error_message,
        "allowed_actions": deployment_allowed_actions(deployment.status),
        "events": [
            {
                "id": event.id,
                "deployment_id": event.deployment_id,
                "event_type": event.event_type,
                "status": event.status,
                "node_id": event.node_id,
                "error_message": event.error_message,
                "created_at": event.created_at,
            }
            for event in getattr(deployment, "events", [])
        ],
    }


async def _set_agent_running(deployment: Deployment, db: AsyncSession) -> None:
    result = await db.execute(select(Agent).where(Agent.id == deployment.agent_id))
    agent = result.scalar_one_or_none()
    if agent and agent.status != AgentStatus.DELETING.value:
        agent.status = AgentStatus.RUNNING.value


async def _stop_agent_without_active_deployments(
    deployment: Deployment,
    db: AsyncSession,
) -> None:
    active_result = await db.execute(
        select(Deployment.id)
        .where(
            Deployment.agent_id == deployment.agent_id,
            Deployment.id != deployment.id,
            Deployment.status.in_(ACTIVE_DEPLOYMENT_STATUSES),
        )
        .limit(1)
    )
    if active_result.scalar_one_or_none() is not None:
        return

    result = await db.execute(select(Agent).where(Agent.id == deployment.agent_id))
    agent = result.scalar_one_or_none()
    if agent and agent.status != AgentStatus.DELETING.value:
        agent.status = AgentStatus.STOPPED.value


@router.get("", response_model=DeploymentListResponse)
async def list_deployments(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    agent_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    # Ownership enforcement: always filter by authenticated user's agent ownership.
    # Client-supplied user_id query params are ignored - ownership is derived
    # from the auth token via current_user, not from client input.
    # Build base filters for both count and data queries
    base_filters = [Agent.user_id == current_user.id]
    if agent_id:
        await get_owned_agent(
            agent_id,
            db,
            current_user,
            not_found_detail="Agent not found",
            forbidden_detail="Not authorized to view deployments for this agent",
        )
        base_filters.append(Deployment.agent_id == agent_id)
    if status:
        base_filters.append(Deployment.status == status)

    # Count total matching deployments using SQL aggregate
    count_query = (
        select(func.count())
        .select_from(Deployment)
        .join(Agent, Deployment.agent_id == Agent.id)
        .where(*base_filters)
    )
    total = (await db.execute(count_query)).scalar_one()

    # Fetch paginated results
    query = (
        select(Deployment)
        .options(selectinload(Deployment.events))
        .join(Agent, Deployment.agent_id == Agent.id)
        .where(*base_filters)
        .order_by(Deployment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    deployments = result.scalars().all()

    return DeploymentListResponse(
        items=[_serialize_deployment(d) for d in deployments],
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + limit) < total,
    )


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    deployment = await get_owned_deployment(
        deployment_id,
        db,
        current_user,
        include_events=True,
    )
    return _serialize_deployment(deployment)


@router.get("/{deployment_id}/events", response_model=DeploymentEventHistoryResponse)
async def get_deployment_events(
    deployment_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    event_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Get paginated lifecycle events for a specific deployment."""
    deployment = await get_owned_deployment(deployment_id, db, current_user)

    filters = [DeploymentEventModel.deployment_id == deployment.id]
    if event_type:
        filters.append(DeploymentEventModel.event_type == event_type)
    if status:
        filters.append(DeploymentEventModel.status == status)

    total_result = await db.execute(
        select(func.count()).select_from(DeploymentEventModel).where(*filters)
    )
    total = total_result.scalar_one()

    query = (
        select(DeploymentEventModel)
        .where(*filters)
        .order_by(DeploymentEventModel.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    items = result.scalars().all()
    return {
        "deployment_id": deployment.id,
        "deployment_status": deployment.status,
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": total > skip + len(items),
        "event_type": event_type,
        "status": status,
    }


@router.post("/{deployment_id}/scale", response_model=DeploymentResponse)
async def scale_deployment(
    deployment_id: uuid.UUID,
    scale_data: DeploymentScale,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    deployment = await get_owned_deployment(deployment_id, db, current_user)

    if scale_data.replicas == 0:
        if deployment.status not in ACTIVE_DEPLOYMENT_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot stop deployment with status '{deployment.status}'",
            )

        deployment.status = "stopped"
        deployment.ended_at = utc_now_naive()
        event_type = "stop"
        event_status = "stopped"
        usage_event_type = "deployment_stopped"
        await _stop_agent_without_active_deployments(deployment, db)
    elif deployment.status == "stopped":
        deployment.replicas = scale_data.replicas
        deployment.status = "deploying"
        deployment.started_at = utc_now_naive()
        deployment.ended_at = None
        deployment.error_message = None
        event_type = "start"
        event_status = "deploying"
        usage_event_type = "deployment_started"
        await _set_agent_running(deployment, db)
    elif deployment.status in RUNNING_DEPLOYMENT_STATUSES:
        deployment.replicas = scale_data.replicas
        event_type = "scale"
        event_status = deployment.status
        usage_event_type = "deployment_scaled"
    else:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot scale deployment with status '{deployment.status}'",
        )

    scale_event = DeploymentEventModel(
        deployment_id=deployment.id,
        event_type=event_type,
        status=event_status,
        error_message=None,
    )
    db.add(scale_event)

    await db.commit()
    # Re-fetch to ensure events are loaded and attributes are fresh
    deployment = await get_owned_deployment(
        deployment_id,
        db,
        current_user,
        include_events=True,
    )
    logger.info(
        "Applied deployment action %s to %s with requested replicas %s",
        event_type,
        deployment_id,
        scale_data.replicas,
    )

    await track_usage_best_effort(
        db=db,
        user_id=current_user.id,
        event_type=usage_event_type,
        resource_type="deployment",
        resource_id=str(deployment_id),
        metadata={"requested_replicas": scale_data.replicas, "replicas": deployment.replicas},
    )

    return _serialize_deployment(deployment)


@router.delete("/{deployment_id}", status_code=204)
async def kill_deployment(
    deployment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    deployment = await get_owned_deployment(deployment_id, db, current_user)

    if deployment.status == "killed":
        raise HTTPException(status_code=409, detail="Deployment is already terminated")

    deployment.status = "killed"
    deployment.ended_at = utc_now_naive()

    # Record kill event
    kill_event = DeploymentEventModel(
        deployment_id=deployment.id,
        event_type="kill",
        status="killed",
    )
    db.add(kill_event)

    await _stop_agent_without_active_deployments(deployment, db)

    await db.commit()

    await track_usage_best_effort(
        db=db,
        user_id=current_user.id,
        event_type="deployment_killed",
        resource_type="deployment",
        resource_id=str(deployment_id),
    )

    logger.info(f"Killed deployment: {deployment_id}")


@router.post("", response_model=DeploymentResponse, status_code=201)
async def create_deployment(
    deployment_data: DeploymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Create a new deployment for an agent."""
    agent = await get_owned_agent(
        deployment_data.agent_id,
        db,
        current_user,
        not_found_detail="Agent not found",
        forbidden_detail="Not authorized to deploy this agent",
    )

    # Check if agent is in a deployable state
    if agent.status == AgentStatus.DELETING.value:
        raise HTTPException(status_code=400, detail="Cannot deploy an agent that is being deleted")

    deployment = await create_deployment_record(
        agent=agent,
        db=db,
        replicas=deployment_data.replicas,
    )

    await db.commit()
    # Re-fetch to ensure events are loaded and attributes are fresh
    deployment = await get_owned_deployment(
        deployment.id,
        db,
        current_user,
        include_events=True,
    )
    logger.info(f"Created deployment {deployment.id} for agent {deployment_data.agent_id}")
    await track_usage_best_effort(
        db=db,
        user_id=current_user.id,
        event_type="deployment_create",
        resource_type="deployment",
        resource_id=str(deployment.id),
        metadata={"replicas": deployment.replicas},
    )

    return _serialize_deployment(deployment)


@router.post("/{deployment_id}/restart", response_model=DeploymentResponse)
async def restart_deployment(
    deployment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Restart an existing deployment."""
    deployment = await get_owned_deployment(deployment_id, db, current_user)

    if deployment.status not in RESTARTABLE_DEPLOYMENT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot restart deployment with status '{deployment.status}'. "
                "Only running, ready, or failed deployments can be restarted."
            ),
        )

    deployment.status = "deploying"
    deployment.started_at = utc_now_naive()
    deployment.ended_at = None
    deployment.error_message = None

    # Record restart event
    restart_event = DeploymentEventModel(
        deployment_id=deployment.id,
        event_type="restart",
        status="deploying",
    )
    db.add(restart_event)

    await _set_agent_running(deployment, db)

    await db.commit()
    # Re-fetch to ensure events are loaded and attributes are fresh
    deployment = await get_owned_deployment(
        deployment_id,
        db,
        current_user,
        include_events=True,
    )
    logger.info(f"Restarted deployment: {deployment_id}")

    await track_usage_best_effort(
        db=db,
        user_id=current_user.id,
        event_type="deployment_restarted",
        resource_type="deployment",
        resource_id=str(deployment_id),
    )

    return _serialize_deployment(deployment)


@router.get("/{deployment_id}/logs", response_model=DeploymentLogsHistoryResponse)
async def get_deployment_logs(
    deployment_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    level: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Get paginated logs for a specific deployment."""
    deployment = await get_owned_deployment(deployment_id, db, current_user)

    filters = [AgentLog.agent_id == deployment.agent_id]
    if level:
        filters.append(AgentLog.level == level)

    total_stmt = select(func.count()).select_from(AgentLog).where(*filters)
    total = (await db.execute(total_stmt)).scalar_one()

    query = (
        select(AgentLog)
        .where(*filters)
        .order_by(AgentLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    logs = result.scalars().all()
    return DeploymentLogsHistoryResponse(
        deployment_id=deployment.id,
        items=logs,
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(logs),
        level=level,
    )


@router.get("/{deployment_id}/metrics", response_model=DeploymentMetricsHistoryResponse)
async def get_deployment_metrics(
    deployment_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Get paginated metrics for a specific deployment."""
    deployment = await get_owned_deployment(deployment_id, db, current_user)

    filters = [AgentMetric.agent_id == deployment.agent_id]

    total_stmt = select(func.count()).select_from(AgentMetric).where(*filters)
    total = (await db.execute(total_stmt)).scalar_one()

    query = (
        select(AgentMetric)
        .where(*filters)
        .offset(skip)
        .limit(limit)
        .order_by(AgentMetric.timestamp.desc())
    )

    result = await db.execute(query)
    metrics = result.scalars().all()
    return DeploymentMetricsHistoryResponse(
        deployment_id=deployment.id,
        items=metrics,
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(metrics),
    )


@router.get("/{deployment_id}/versions", response_model=DeploymentVersionHistoryResponse)
async def get_deployment_versions(
    deployment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Get version history for a specific deployment."""
    deployment = await get_owned_deployment(deployment_id, db, current_user)

    count_stmt = (
        select(func.count())
        .select_from(DeploymentVersion)
        .where(DeploymentVersion.deployment_id == deployment.id)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    query = (
        select(DeploymentVersion)
        .where(DeploymentVersion.deployment_id == deployment.id)
        .order_by(DeploymentVersion.created_at.desc())
    )

    result = await db.execute(query)
    versions = result.scalars().all()

    return DeploymentVersionHistoryResponse(
        deployment_id=deployment.id,
        items=versions,
        total=total,
        has_more=False,
    )


@router.post("/{deployment_id}/rollback", response_model=DeploymentResponse)
async def rollback_deployment(
    deployment_id: uuid.UUID,
    rollback_data: DeploymentRollbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Rollback a deployment to a specific version."""
    deployment = await get_owned_deployment(deployment_id, db, current_user)

    if deployment.status not in ["running", "ready", "stopped", "failed"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot rollback deployment with status '{deployment.status}'",
        )

    target_version_query = select(DeploymentVersion).where(
        DeploymentVersion.deployment_id == deployment.id,
        DeploymentVersion.version == rollback_data.version,
    )
    result = await db.execute(target_version_query)
    target_version = result.scalar_one_or_none()

    if not target_version:
        raise HTTPException(
            status_code=404,
            detail=f"Version {rollback_data.version} not found for this deployment",
        )

    snapshot = json.loads(target_version.config_snapshot)
    deployment.replicas = int(snapshot.get("replicas", deployment.replicas))
    deployment.version = snapshot.get("version", deployment.version)

    mark_old_query = select(DeploymentVersion).where(
        DeploymentVersion.deployment_id == deployment.id,
        DeploymentVersion.status == "current",
    )
    old_result = await db.execute(mark_old_query)
    old_versions = old_result.scalars().all()
    for old_v in old_versions:
        old_v.status = "superseded"
        old_v.rolled_back_at = utc_now_naive()

    target_version.status = "current"
    target_version.rolled_back_at = None

    rollback_event = DeploymentEventModel(
        deployment_id=deployment.id,
        event_type="rollback",
        status=deployment.status,
    )
    db.add(rollback_event)

    await db.commit()

    deployment = await get_owned_deployment(
        deployment_id,
        db,
        current_user,
        include_events=True,
    )
    logger.info(f"Rolled back deployment {deployment_id} to version {rollback_data.version}")
    return _serialize_deployment(deployment)
