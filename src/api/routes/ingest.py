import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import get_current_user_or_api_key
from src.api.database import get_db
from src.api.models import (
    Agent,
    Deployment,
    AgentLog,
    AgentMetric,
    AgentStatus,
    User,
    DeploymentEvent as DeploymentEventModel,
)
from src.api.models.schemas import (
    AgentStatusUpdate,
    DeploymentEvent,
    IngestEvent,
    MetricsReportRequest,
)
from src.api.services.auth import Role, check_role
from src.api.services.event_ingestion import process_ingest_event
from src.api.services.webhook_service import (
    trigger_agent_status_event,
    trigger_deployment_event,
    trigger_webhook_event,
)
from src.api.time_utils import utc_now, utc_now_naive

router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)


async def get_ingest_auth(
    authorization: Optional[str] = Header(None, description="Bearer token for JWT auth"),
    x_api_key: Optional[str] = Header(
        None, alias="X-API-Key", description="API key for ingestion authentication"
    ),
    session: AsyncSession = Depends(get_db),
    *,
    request: Request,
) -> User:
    """Authenticate ingestion requests via JWT or API key."""
    user = await get_current_user_or_api_key(
        request=request,
        authorization=authorization,
        x_api_key=x_api_key,
        session=session,
    )
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication. Provide valid JWT Bearer token or X-API-Key header.",
        )
    return user


async def require_ingest_developer(
    current_user: User = Depends(get_ingest_auth),
) -> User:
    """Enforce the persisted developer role for ingestion principals."""
    if not check_role(current_user.roles or [], [Role.DEVELOPER]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Required roles: ['DEVELOPER']",
        )
    return current_user


@router.post("/agent-status")
async def agent_status_update(
    status_data: AgentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ingest_developer),
):
    """Update an agent status and append logs (Ingestion)."""
    # Resolve through the owner scope so missing and foreign agents are indistinguishable.
    result = await db.execute(
        select(Agent).where(
            Agent.id == status_data.agent_id,
            Agent.user_id == current_user.id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    old_status = agent.status

    # Determine final status: error_message overrides to FAILED
    if status_data.error_message:
        final_status = AgentStatus.FAILED.value
    else:
        final_status = status_data.status.value

    agent.status = final_status
    agent.last_heartbeat = utc_now()
    agent.updated_at = datetime.now(timezone.utc)

    log = AgentLog(
        agent_id=agent.id,
        level="info",
        message=f"Status changed from {old_status} to {final_status}",
        extra_data=f"node_id: {status_data.node_id}",
    )
    db.add(log)

    if status_data.error_message:
        error_log = AgentLog(
            agent_id=agent.id,
            level="error",
            message=status_data.error_message,
            extra_data=f"node_id: {status_data.node_id}",
        )
        db.add(error_log)

    await db.commit()

    # Trigger webhook
    await trigger_agent_status_event(
        db, current_user.id, agent.id, old_status, agent.status, agent.name
    )

    logger.info(f"Agent {agent.id} status updated to {final_status}")
    return {"status": "updated"}


@router.post("/deployment")
async def deployment_event(
    event_data: DeploymentEvent,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ingest_developer),
):
    """Update deployment state and related agent state (Ingestion)."""
    # Resolve the deployment and its agent in one owner-scoped query before mutation.
    result = await db.execute(
        select(Deployment, Agent)
        .join(Agent, Agent.id == Deployment.agent_id)
        .where(
            Deployment.id == event_data.deployment_id,
            Agent.user_id == current_user.id,
        )
    )
    deployment_row = result.one_or_none()
    if deployment_row is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    deployment, agent = deployment_row

    if event_data.status:
        deployment.status = event_data.status

    if event_data.node_id:
        deployment.node_id = event_data.node_id

    # Record the event in the lifecycle history
    new_event = DeploymentEventModel(
        deployment_id=deployment.id,
        event_type=event_data.event,
        status=event_data.status or deployment.status,
        node_id=event_data.node_id,
        error_message=event_data.error_message,
    )
    db.add(new_event)

    if event_data.error_message:
        deployment.error_message = event_data.error_message
        deployment.status = "failed"
        error_log = AgentLog(
            agent_id=deployment.agent_id,
            level="error",
            message=event_data.error_message,
            extra_data=f"deployment_id: {deployment.id}, event: {event_data.event}",
        )
        db.add(error_log)

    if event_data.event == "stopped" or event_data.status == "stopped":
        deployment.ended_at = utc_now_naive()
        agent.status = AgentStatus.STOPPED.value

    if event_data.event == "healthy" or event_data.status == "running":
        deployment.status = "running"
        if deployment.started_at is None:
            deployment.started_at = utc_now_naive()

    await db.commit()

    # Trigger webhook
    await trigger_deployment_event(
        db, current_user.id, deployment.id, agent.id, event_data.event, deployment.status
    )

    logger.info(f"Deployment {deployment.id} event: {event_data.event}")
    return {"status": "processed"}


@router.post("/metrics")
async def receive_metrics(
    metrics_data: MetricsReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ingest_developer),
):
    """Record agent metrics (Ingestion)."""
    # Resolve through the owner scope so missing and foreign agents are indistinguishable.
    result = await db.execute(
        select(Agent).where(
            Agent.id == metrics_data.agent_id,
            Agent.user_id == current_user.id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.last_heartbeat = utc_now()
    metric = AgentMetric(
        agent_id=metrics_data.agent_id,
        cpu_usage=metrics_data.cpu_usage,
        memory_usage=metrics_data.memory_usage,
    )
    db.add(metric)
    await db.commit()

    # Trigger metrics webhook
    await trigger_webhook_event(
        db,
        current_user.id,
        "metrics.report",
        {
            "agent_id": str(metrics_data.agent_id),
            "cpu_usage": metrics_data.cpu_usage,
            "memory_usage": metrics_data.memory_usage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    logger.debug(f"Received metrics for agent {metrics_data.agent_id}")
    return {"status": "recorded"}


@router.post("/events")
async def ingest_event(
    event_data: IngestEvent,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ingest_developer),
):
    """Accept structured events from SDK adapters through the legacy alias."""
    return await process_ingest_event(event_data, current_user, db)
