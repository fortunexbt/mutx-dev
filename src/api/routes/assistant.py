from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.auth.ownership import get_owned_agent as _get_owned_agent
from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import Agent, AgentType, Deployment, User
from src.api.models.schemas import (
    AssistantChannelResponse,
    AssistantHealthResponse,
    AssistantOverviewEnvelope,
    AssistantSessionResponse,
    AssistantSkillResponse,
    AssistantWakeupResponse,
)
from src.api.routes.deployments import _serialize_deployment
from src.api.services.assistant_control_plane import (
    collect_assistant_overview,
    collect_gateway_health,
    is_assistant_agent,
    list_assistant_channels,
    list_assistant_skills,
    list_assistant_wakeups,
    list_gateway_sessions,
    update_assistant_skills,
)
from src.api.services.session_ownership import filter_and_claim_owned_sessions

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _can_view_host_diagnostics(current_user: User) -> bool:
    return any(
        isinstance(role, str) and role.strip().upper() == "ADMIN"
        for role in (current_user.roles or [])
    )


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


async def _resolve_assistant_agent(
    *,
    db: AsyncSession,
    current_user: User,
    agent_id: uuid.UUID | None,
) -> Agent | None:
    if agent_id is not None:
        agent = await get_owned_agent(
            agent_id,
            db,
            current_user,
            include_deployments=True,
            include_deployment_events=True,
        )
        if not is_assistant_agent(agent):
            raise HTTPException(status_code=400, detail="Agent is not an assistant runtime")
        return agent

    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.deployments).selectinload(Deployment.events))
        .where(Agent.user_id == current_user.id, Agent.type == AgentType.OPENCLAW)
        .order_by(Agent.created_at.desc())
    )
    return result.scalars().first()


@router.get("/overview", response_model=AssistantOverviewEnvelope)
async def assistant_overview(
    agent_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    agent = await _resolve_assistant_agent(db=db, current_user=current_user, agent_id=agent_id)
    if agent is None:
        return {
            "has_assistant": False,
            "recommended_template_id": "personal_assistant",
            "assistant": None,
        }

    deployment_payloads = [_serialize_deployment(deployment) for deployment in agent.deployments]
    return {
        "has_assistant": True,
        "recommended_template_id": "personal_assistant",
        "assistant": collect_assistant_overview(
            agent,
            deployment_payloads,
            include_host_diagnostics=_can_view_host_diagnostics(current_user),
        ),
    }


@router.get("/{agent_id}/skills", response_model=list[AssistantSkillResponse])
async def assistant_skills(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    agent = await get_owned_agent(agent_id, db, current_user)
    if not is_assistant_agent(agent):
        raise HTTPException(status_code=400, detail="Agent is not an assistant runtime")
    return list_assistant_skills(agent)


@router.post("/{agent_id}/skills/{skill_id}", response_model=list[AssistantSkillResponse])
async def install_assistant_skill(
    agent_id: uuid.UUID,
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    agent = await get_owned_agent(agent_id, db, current_user)
    if not is_assistant_agent(agent):
        raise HTTPException(status_code=400, detail="Agent is not an assistant runtime")
    try:
        update_assistant_skills(agent, skill_id=skill_id, install=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown skill: {skill_id}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return list_assistant_skills(agent)


@router.delete("/{agent_id}/skills/{skill_id}", response_model=list[AssistantSkillResponse])
async def uninstall_assistant_skill(
    agent_id: uuid.UUID,
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    agent = await get_owned_agent(agent_id, db, current_user)
    if not is_assistant_agent(agent):
        raise HTTPException(status_code=400, detail="Agent is not an assistant runtime")
    update_assistant_skills(agent, skill_id=skill_id, install=False)
    await db.commit()
    return list_assistant_skills(agent)


@router.get("/{agent_id}/channels", response_model=list[AssistantChannelResponse])
async def assistant_channels(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    agent = await get_owned_agent(agent_id, db, current_user)
    if not is_assistant_agent(agent):
        raise HTTPException(status_code=400, detail="Agent is not an assistant runtime")
    return list_assistant_channels(agent)


@router.get("/{agent_id}/wakeups", response_model=list[AssistantWakeupResponse])
async def assistant_wakeups(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    agent = await get_owned_agent(agent_id, db, current_user)
    if not is_assistant_agent(agent):
        raise HTTPException(status_code=400, detail="Agent is not an assistant runtime")
    return list_assistant_wakeups(agent)


@router.get("/{agent_id}/health", response_model=AssistantHealthResponse)
async def assistant_health(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    agent = await get_owned_agent(agent_id, db, current_user)
    if not is_assistant_agent(agent):
        raise HTTPException(status_code=400, detail="Agent is not an assistant runtime")
    return collect_gateway_health(
        include_host_diagnostics=_can_view_host_diagnostics(current_user),
    )


@router.get("/{agent_id}/sessions", response_model=list[AssistantSessionResponse])
async def assistant_sessions(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    agent = await get_owned_agent(agent_id, db, current_user)
    if not is_assistant_agent(agent):
        raise HTTPException(status_code=400, detail="Agent is not an assistant runtime")
    return await filter_and_claim_owned_sessions(
        db,
        user=current_user,
        sessions=list_gateway_sessions(),
        required_agent_id=agent.id,
    )
