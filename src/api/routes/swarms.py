"""
Swarm routes for multi-agent swarm management.
A swarm is a collection of agent deployments that work together.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import Agent, Deployment, Swarm, User
from src.api.models.schemas import SwarmBlueprintResponse
from src.api.services.assistant_control_plane import list_swarm_blueprints

router = APIRouter(prefix="/swarms", tags=["swarms"])
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class SwarmCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    agent_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=20)
    min_replicas: int = Field(default=1, ge=1, le=10)
    max_replicas: int = Field(default=10, ge=1, le=50)


class SwarmUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    min_replicas: Optional[int] = Field(None, ge=1, le=10)
    max_replicas: Optional[int] = Field(None, ge=1, le=50)


class SwarmScale(BaseModel):
    replicas: int = Field(..., ge=1, le=50, description="Target replicas per agent")


class SwarmAgentResponse(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    status: str
    replicas: int


class SwarmResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    agent_ids: list[uuid.UUID]
    min_replicas: int
    max_replicas: int
    created_at: datetime
    updated_at: datetime
    agents: list[SwarmAgentResponse] = []


class SwarmListResponse(BaseModel):
    items: list[SwarmResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


@router.get("/blueprints", response_model=list[SwarmBlueprintResponse])
async def list_swarm_blueprint_catalog(
    _current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """List curated multi-agent orchestration blueprints sourced from Orchestra Research."""
    return list_swarm_blueprints()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _serialize_swarm(swarm: Swarm, db: AsyncSession) -> SwarmResponse:
    """Serialize swarm with agent details."""
    agents = []
    for agent_id_str in swarm.agent_ids:
        try:
            agent_id = uuid.UUID(agent_id_str)
        except ValueError:
            continue
        agent_result = await db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.user_id == swarm.user_id)
        )
        agent = agent_result.scalar_one_or_none()
        if agent:
            deploy_result = await db.execute(
                select(Deployment).where(
                    Deployment.agent_id == agent_id,
                    Deployment.status.in_(["running", "ready", "deploying"]),
                )
            )
            deployment = deploy_result.scalar_one_or_none()
            agents.append(
                SwarmAgentResponse(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    status=agent.status,
                    replicas=deployment.replicas if deployment else 0,
                )
            )

    return SwarmResponse(
        id=swarm.id,
        name=swarm.name,
        description=swarm.description,
        agent_ids=[uuid.UUID(aid) for aid in swarm.agent_ids],
        min_replicas=swarm.min_replicas,
        max_replicas=swarm.max_replicas,
        created_at=swarm.created_at,
        updated_at=swarm.updated_at,
        agents=agents,
    )


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------


@router.get("", response_model=SwarmListResponse)
async def list_swarms(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """List all swarms for the current user."""
    # Count total
    count_result = await db.execute(
        select(func.count()).select_from(Swarm).where(Swarm.user_id == current_user.id)
    )
    total = count_result.scalar_one() or 0

    # Paginated query
    result = await db.execute(
        select(Swarm)
        .where(Swarm.user_id == current_user.id)
        .order_by(Swarm.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    swarms = result.scalars().all()

    return SwarmListResponse(
        items=[await _serialize_swarm(s, db) for s in swarms],
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(swarms),
    )


@router.post("", response_model=SwarmResponse, status_code=201)
async def create_swarm(
    swarm_data: SwarmCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Create a new swarm."""
    # Validate all agents exist and are owned by the user
    for agent_id in swarm_data.agent_ids:
        agent_result = await db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.user_id == current_user.id)
        )
        agent = agent_result.scalar_one_or_none()
        if not agent:
            raise HTTPException(
                status_code=400, detail=f"Agent {agent_id} not found or not owned by user"
            )

    swarm = Swarm(
        name=swarm_data.name,
        description=swarm_data.description,
        agent_ids=[str(aid) for aid in swarm_data.agent_ids],
        user_id=current_user.id,
        min_replicas=swarm_data.min_replicas,
        max_replicas=swarm_data.max_replicas,
    )
    db.add(swarm)
    await db.commit()
    await db.refresh(swarm)
    logger.info(f"Created swarm: {swarm.id}")
    return await _serialize_swarm(swarm, db)


@router.get("/{swarm_id}", response_model=SwarmResponse)
async def get_swarm(
    swarm_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    """Get swarm details."""
    result = await db.execute(
        select(Swarm).where(Swarm.id == swarm_id, Swarm.user_id == current_user.id)
    )
    swarm = result.scalar_one_or_none()
    if not swarm:
        raise HTTPException(status_code=404, detail="Swarm not found")
    return await _serialize_swarm(swarm, db)


@router.patch("/{swarm_id}", response_model=SwarmResponse)
async def update_swarm(
    swarm_id: uuid.UUID,
    update_data: SwarmUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Update swarm metadata."""
    result = await db.execute(
        select(Swarm).where(Swarm.id == swarm_id, Swarm.user_id == current_user.id)
    )
    swarm = result.scalar_one_or_none()
    if not swarm:
        raise HTTPException(status_code=404, detail="Swarm not found")

    updates = update_data.model_dump(exclude_unset=True)
    if "name" in updates:
        swarm.name = updates["name"]
    if "description" in updates:
        swarm.description = updates["description"]
    if "min_replicas" in updates:
        swarm.min_replicas = updates["min_replicas"]
    if "max_replicas" in updates:
        swarm.max_replicas = updates["max_replicas"]

    await db.commit()
    await db.refresh(swarm)
    logger.info(f"Updated swarm: {swarm.id}")
    return await _serialize_swarm(swarm, db)


@router.delete("/{swarm_id}", status_code=204)
async def delete_swarm(
    swarm_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Delete a swarm."""
    result = await db.execute(
        select(Swarm).where(Swarm.id == swarm_id, Swarm.user_id == current_user.id)
    )
    swarm = result.scalar_one_or_none()
    if not swarm:
        raise HTTPException(status_code=404, detail="Swarm not found")

    await db.delete(swarm)
    await db.commit()
    logger.info(f"Deleted swarm: {swarm_id}")


@router.post("/{swarm_id}/scale", response_model=SwarmResponse)
async def scale_swarm(
    swarm_id: uuid.UUID,
    scale_data: SwarmScale,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Scale all agents in a swarm to the specified replicas."""
    result = await db.execute(
        select(Swarm).where(Swarm.id == swarm_id, Swarm.user_id == current_user.id)
    )
    swarm = result.scalar_one_or_none()
    if not swarm:
        raise HTTPException(status_code=404, detail="Swarm not found")

    if scale_data.replicas < swarm.min_replicas or scale_data.replicas > swarm.max_replicas:
        raise HTTPException(
            status_code=400,
            detail=f"Replicas must be between {swarm.min_replicas} and {swarm.max_replicas}",
        )

    for agent_id_str in swarm.agent_ids:
        try:
            agent_id = uuid.UUID(agent_id_str)
        except ValueError:
            continue
        deploy_result = await db.execute(
            select(Deployment).where(
                Deployment.agent_id == agent_id, Deployment.status.in_(["running", "ready"])
            )
        )
        deployment = deploy_result.scalar_one_or_none()
        if deployment:
            deployment.replicas = scale_data.replicas

    await db.commit()
    await db.refresh(swarm)
    logger.info(f"Scaled swarm {swarm_id} to {scale_data.replicas} replicas")
    return await _serialize_swarm(swarm, db)
