import json
import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.ownership import get_owned_agent as _get_owned_agent
from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import (
    Agent,
    AgentLog,
    AgentMetric,
    AgentResourceUsage,
    AgentStatus,
    AgentType,
    Deployment,
    DeploymentEvent as DeploymentEventModel,
    User,
)
from src.api.services.usage import track_usage_best_effort
from src.api.models.schemas import (
    AgentConfigBase,
    AgentConfigResponse,
    AgentConfigUpdateRequest,
    AgentLogHistoryResponse,
    AgentMetricHistoryResponse,
    AgentResourceUsageCreate,
    PaginatedAgentResourceUsageResponse,
    AgentResourceUsageResponse,
    AgentCreate,
    AgentDetailResponse,
    AgentResponse,
    AgentListResponse,
    AnthropicAgentConfig,
    CustomAgentConfig,
    LangChainAgentConfig,
    OpenClawAgentConfig,
    OpenAIAgentConfig,
)
from src.api.models.numeric import reject_non_finite_floats
from src.api.time_utils import utc_now_naive

router = APIRouter(prefix="/agents", tags=["agents"])
logger = logging.getLogger(__name__)


async def get_owned_agent(
    agent_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
    **kwargs: Any,
) -> Agent:
    """Resolve ownership without revealing whether another tenant owns the id."""
    try:
        return await _get_owned_agent(agent_id, db, current_user, **kwargs)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        raise HTTPException(
            status_code=404,
            detail=kwargs.get("not_found_detail", "Agent not found"),
        ) from None


AGENT_CONFIG_MODEL_MAP: dict[AgentType, type[AgentConfigBase]] = {
    AgentType.OPENAI: OpenAIAgentConfig,
    AgentType.ANTHROPIC: AnthropicAgentConfig,
    AgentType.LANGCHAIN: LangChainAgentConfig,
    AgentType.CUSTOM: CustomAgentConfig,
    AgentType.OPENCLAW: OpenClawAgentConfig,
}


def _parse_agent_config_payload(config: Any) -> dict[str, Any]:
    if config is None:
        return {}

    if isinstance(config, BaseModel):
        config_dict = config.model_dump(exclude_none=True)
    elif isinstance(config, str):
        try:
            config_dict = json.loads(config)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid JSON in agent configuration"
            ) from exc
    else:
        config_dict = config

    if not isinstance(config_dict, dict):
        raise HTTPException(status_code=400, detail="Agent configuration must be a JSON object")

    return dict(config_dict)


def _deserialize_agent_config(config: Any) -> dict[str, Any] | None:
    if not config:
        return None

    if isinstance(config, str):
        try:
            config_dict = json.loads(config)
        except json.JSONDecodeError:
            return {"raw_config": config}
    elif isinstance(config, dict):
        config_dict = config
    else:
        return {"raw_config": config}

    if not isinstance(config_dict, dict):
        return {"raw_config": config_dict}

    return config_dict


def _deserialize_extra_metadata(extra_metadata: Any) -> dict[str, Any] | None:
    if not extra_metadata:
        return None

    if isinstance(extra_metadata, str):
        try:
            parsed = json.loads(extra_metadata)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    return extra_metadata if isinstance(extra_metadata, dict) else None


def _to_agent_resource_usage_response(usage: AgentResourceUsage) -> AgentResourceUsageResponse:
    return AgentResourceUsageResponse(
        id=usage.id,
        agent_id=usage.agent_id,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        api_calls=usage.api_calls,
        cost_usd=usage.cost_usd,
        model=usage.model,
        extra_metadata=_deserialize_extra_metadata(usage.extra_metadata),
        period_start=usage.period_start,
        period_end=usage.period_end,
        created_at=usage.created_at,
    )


def _extract_config_version(config: dict[str, Any] | None) -> int:
    if not isinstance(config, dict):
        return 1

    version = config.get("version")
    if isinstance(version, int) and version >= 1:
        return version

    return 1


def _normalize_agent_config_for_response(
    agent_type: AgentType, config: dict[str, Any] | None
) -> dict[str, Any] | None:
    if config is None:
        return None

    config_model = AGENT_CONFIG_MODEL_MAP.get(agent_type)
    if config_model is None:
        return config

    try:
        validated = config_model.model_validate(config)
    except ValidationError:
        return config

    return validated.model_dump(exclude_none=True)


def _validate_agent_config(
    agent_type: AgentType,
    config: Any,
    *,
    version: int | None = None,
    name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate and normalize agent configuration based on its type."""
    config_dict = _parse_agent_config_payload(config)
    try:
        reject_non_finite_floats(config_dict, path="$.config")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if name and not config_dict.get("name"):
        config_dict["name"] = name
    if version is not None:
        config_dict["version"] = version

    config_model = AGENT_CONFIG_MODEL_MAP.get(agent_type)
    if config_model is None:
        return json.dumps(config_dict, allow_nan=False), config_dict

    try:
        validated = config_model.model_validate(config_dict)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Configuration validation failed: {exc}",
        ) from exc

    normalized = validated.model_dump(exclude_none=True)
    return json.dumps(normalized, allow_nan=False), normalized


def _serialize_deployment(deployment: Deployment):
    return {
        "id": deployment.id,
        "agent_id": deployment.agent_id,
        "status": deployment.status,
        "replicas": deployment.replicas,
        "node_id": deployment.node_id,
        "started_at": deployment.started_at,
        "ended_at": deployment.ended_at,
        "error_message": deployment.error_message,
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


def _serialize_agent_config(agent: Agent) -> dict[str, Any]:
    raw_config = _deserialize_agent_config(agent.config)
    normalized_config = _normalize_agent_config_for_response(agent.type, raw_config or {}) or {}
    config_version = _extract_config_version(normalized_config)

    return {
        "agent_id": agent.id,
        "type": agent.type,
        "config": normalized_config,
        "config_version": config_version,
        "updated_at": agent.updated_at,
    }


def _serialize_agent(agent: Agent, include_deployments: bool = False):
    raw_config = _deserialize_agent_config(agent.config)
    config_dict = _normalize_agent_config_for_response(agent.type, raw_config)
    config_version = _extract_config_version(config_dict)

    payload = {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "type": agent.type,
        "status": agent.status,
        "config": config_dict,
        "config_version": config_version,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
        "user_id": agent.user_id,
    }

    if include_deployments:
        payload["deployments"] = [
            _serialize_deployment(deployment) for deployment in agent.deployments
        ]

    return payload


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    agent_data: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    config_json, _normalized_config = _validate_agent_config(
        agent_data.type,
        agent_data.config,
        version=1,
        name=agent_data.name,
    )

    agent = Agent(
        name=agent_data.name,
        description=agent_data.description,
        type=agent_data.type,
        config=config_json,
        user_id=current_user.id,
        status=AgentStatus.CREATING.value,
    )
    db.add(agent)
    await db.flush()

    await db.commit()
    await db.refresh(agent)
    logger.info(f"Created agent: {agent.id}")

    await track_usage_best_effort(
        db=db,
        user_id=current_user.id,
        event_type="agent_create",
        resource_type="agent",
        resource_id=str(agent.id),
        metadata={"agent_type": agent.type.value},
    )

    return _serialize_agent(agent)


@router.get("", response_model=AgentListResponse)
async def list_agents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    # Ownership enforcement: always filter by authenticated user's ID.
    # Client-supplied user_id query params are ignored - ownership is derived
    # from the auth token via current_user, not from client input.
    base_filter = Agent.user_id == current_user.id

    # Total count via SQL aggregate — avoids loading full rows just to count.
    count_stmt = select(func.count()).select_from(Agent).where(base_filter)
    total = (await db.execute(count_stmt)).scalar_one()

    query = (
        select(Agent).where(base_filter).order_by(Agent.created_at.desc()).offset(skip).limit(limit)
    )
    result = await db.execute(query)
    agents = result.scalars().all()

    return AgentListResponse(
        items=[_serialize_agent(agent) for agent in agents],
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + limit) < total,
    )


@router.get("/{agent_id}", response_model=AgentDetailResponse)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    agent = await get_owned_agent(
        agent_id,
        db,
        current_user,
        include_deployments=True,
        include_deployment_events=True,
    )
    return _serialize_agent(agent, include_deployments=True)


@router.get("/{agent_id}/config", response_model=AgentConfigResponse)
async def get_agent_config(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    agent = await get_owned_agent(
        agent_id,
        db,
        current_user,
        forbidden_detail="Not authorized to access this agent config",
    )
    return _serialize_agent_config(agent)


@router.patch("/{agent_id}/config", response_model=AgentConfigResponse)
async def update_agent_config(
    agent_id: uuid.UUID,
    request: AgentConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    agent = await get_owned_agent(
        agent_id,
        db,
        current_user,
        forbidden_detail="Not authorized to update this agent config",
    )
    current_config = _deserialize_agent_config(agent.config)
    current_version = _extract_config_version(current_config)
    config_json, _normalized_config = _validate_agent_config(
        agent.type,
        request.config,
        version=current_version + 1,
        name=agent.name,
    )
    agent.config = config_json
    await db.commit()
    await db.refresh(agent)
    logger.info(f"Updated config for agent: {agent_id}")
    return _serialize_agent_config(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    agent = await get_owned_agent(
        agent_id,
        db,
        current_user,
        forbidden_detail="Not authorized to delete this agent",
    )

    agent.status = AgentStatus.DELETING.value
    await db.delete(agent)
    await db.commit()
    logger.info(f"Deleted agent: {agent_id}")


class AgentDeployResponse(BaseModel):
    deployment_id: uuid.UUID
    status: str


class AgentStopResponse(BaseModel):
    status: str


@router.post("/{agent_id}/deploy", response_model=AgentDeployResponse)
async def deploy_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    try:
        agent = await get_owned_agent(
            agent_id,
            db,
            current_user,
            forbidden_detail="Not authorized to deploy this agent",
        )

        deployment = Deployment(
            agent_id=agent_id,
            status="deploying",
            replicas=1,
            started_at=utc_now_naive(),
        )
        db.add(deployment)
        await db.flush()

        deploy_event = DeploymentEventModel(
            deployment_id=deployment.id,
            event_type="deploy",
            status="deploying",
        )
        db.add(deploy_event)

        agent.status = AgentStatus.RUNNING.value
        await db.commit()
        await db.refresh(deployment)
        logger.info(f"Deployed agent: {agent_id}, deployment: {deployment.id}")

        await track_usage_best_effort(
            db=db,
            user_id=current_user.id,
            event_type="agent_deployed",
            resource_type="agent",
            resource_id=str(agent_id),
            metadata={"deployment_id": str(deployment.id)},
        )

        return {"deployment_id": deployment.id, "status": "deploying"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to deploy agent: {agent_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to deploy agent: {str(e)}",
        ) from e


@router.post("/{agent_id}/stop", response_model=AgentStopResponse)
async def stop_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    agent = await get_owned_agent(
        agent_id,
        db,
        current_user,
        forbidden_detail="Not authorized to stop this agent",
    )

    result = await db.execute(
        select(Deployment).where(
            Deployment.agent_id == agent_id, Deployment.status.in_(["running", "deploying"])
        )
    )
    deployments = result.scalars().all()
    for deployment in deployments:
        deployment.status = "stopped"
        deployment.ended_at = utc_now_naive()

        stop_event = DeploymentEventModel(
            deployment_id=deployment.id,
            event_type="stop",
            status="stopped",
        )
        db.add(stop_event)

    agent.status = AgentStatus.STOPPED.value
    await db.commit()

    await track_usage_best_effort(
        db=db,
        user_id=current_user.id,
        event_type="agent_stopped",
        resource_type="agent",
        resource_id=str(agent_id),
    )

    logger.info(f"Stopped agent: {agent_id}")
    return {"status": "stopped"}


@router.get("/{agent_id}/logs", response_model=AgentLogHistoryResponse)
async def get_agent_logs(
    agent_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    level: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    await get_owned_agent(
        agent_id,
        db,
        current_user,
        forbidden_detail="Not authorized to access this agent's logs",
    )

    count_query = select(func.count()).select_from(AgentLog).where(AgentLog.agent_id == agent_id)
    if level:
        count_query = count_query.where(AgentLog.level == level)
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    query = select(AgentLog).where(AgentLog.agent_id == agent_id).offset(skip).limit(limit)
    if level:
        query = query.where(AgentLog.level == level)
    query = query.order_by(AgentLog.timestamp.desc())
    result = await db.execute(query)
    logs = result.scalars().all()
    return AgentLogHistoryResponse(
        agent_id=agent_id,
        items=logs,
        total=total,
        has_more=(skip + limit) < total,
    )


@router.get("/{agent_id}/metrics", response_model=AgentMetricHistoryResponse)
async def get_agent_metrics(
    agent_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    await get_owned_agent(
        agent_id,
        db,
        current_user,
        forbidden_detail="Not authorized to access this agent's metrics",
    )

    count_query = (
        select(func.count()).select_from(AgentMetric).where(AgentMetric.agent_id == agent_id)
    )
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    query = (
        select(AgentMetric)
        .where(AgentMetric.agent_id == agent_id)
        .offset(skip)
        .limit(limit)
        .order_by(AgentMetric.timestamp.desc())
    )
    result = await db.execute(query)
    metrics = result.scalars().all()
    return AgentMetricHistoryResponse(
        agent_id=agent_id,
        items=metrics,
        total=total,
        has_more=(skip + limit) < total,
    )


# --- Resource Usage Routes ---


@router.post(
    "/{agent_id}/resource-usage",
    response_model=AgentResourceUsageResponse,
    status_code=201,
)
async def create_agent_resource_usage(
    agent_id: uuid.UUID,
    request: AgentResourceUsageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Record resource usage for an agent (tokens, API calls, cost)."""
    await get_owned_agent(
        agent_id,
        db,
        current_user,
        forbidden_detail="Not authorized to access this agent's resource usage",
    )

    usage = AgentResourceUsage(
        agent_id=agent_id,
        prompt_tokens=request.prompt_tokens,
        completion_tokens=request.completion_tokens,
        total_tokens=request.total_tokens,
        api_calls=request.api_calls,
        cost_usd=request.cost_usd,
        model=request.model,
        extra_metadata=(
            json.dumps(request.extra_metadata, allow_nan=False) if request.extra_metadata else None
        ),
        period_start=request.period_start,
        period_end=request.period_end,
    )
    db.add(usage)
    await db.commit()
    await db.refresh(usage)
    logger.info(f"Recorded resource usage for agent: {agent_id}")
    return _to_agent_resource_usage_response(usage)


@router.get(
    "/{agent_id}/resource-usage",
    response_model=PaginatedAgentResourceUsageResponse,
)
async def list_agent_resource_usage(
    agent_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """List resource usage records for an agent."""
    await get_owned_agent(
        agent_id,
        db,
        current_user,
        forbidden_detail="Not authorized to access this agent's resource usage",
    )

    # Total count
    count_stmt = (
        select(func.count())
        .select_from(AgentResourceUsage)
        .where(AgentResourceUsage.agent_id == agent_id)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    query = (
        select(AgentResourceUsage)
        .where(AgentResourceUsage.agent_id == agent_id)
        .order_by(AgentResourceUsage.period_start.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    usages = result.scalars().all()

    return PaginatedAgentResourceUsageResponse(
        items=[_to_agent_resource_usage_response(usage) for usage in usages],
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + limit) < total,
    )
