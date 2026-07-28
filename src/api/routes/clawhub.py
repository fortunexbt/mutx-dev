import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from src.api.auth.ownership import get_owned_agent as _get_owned_agent
from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import AgentLog, User
from src.api.models.schemas import AssistantSkillResponse, ClawHubSkillBundleResponse
from src.api.services.assistant_control_plane import (
    install_skill_bundle,
    find_skill_catalog_item,
    list_assistant_skills,
    list_configured_skill_ids,
    list_skill_bundles,
    list_skill_catalog,
    skill_catalog_payload,
    update_assistant_skills,
)

router = APIRouter(prefix="/clawhub", tags=["clawhub"])
logger = logging.getLogger(__name__)


async def get_owned_agent(
    agent_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
    **kwargs: Any,
) -> Any:
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


class InstallSkillRequest(BaseModel):
    agent_id: uuid.UUID
    skill_id: str


class InstallSkillBundleRequest(BaseModel):
    agent_id: uuid.UUID
    bundle_id: str


def _failed_response(
    *, operation: str, detail: str, status_code: int, **context: Any
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "failed",
            "operation": operation,
            "detail": detail,
            **context,
        },
    )


def _skill_from_payload(skills: list[dict[str, Any]], skill_id: str) -> dict[str, Any] | None:
    return next((skill for skill in skills if skill["id"] == skill_id), None)


@router.get("/skills", response_model=list[AssistantSkillResponse])
async def list_available_skills():
    """Returns the current MUTX skill catalog, including bundled Orchestra Research imports."""
    return [AssistantSkillResponse(**skill_catalog_payload(item)) for item in list_skill_catalog()]


@router.get("/bundles", response_model=list[ClawHubSkillBundleResponse])
async def list_available_skill_bundles():
    """Returns curated skill bundles for shipping common Orchestra Research stacks."""
    return [ClawHubSkillBundleResponse(**item) for item in list_skill_bundles()]


@router.post("/install")
async def install_skill(
    request: InstallSkillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Persists a skill request without claiming unproven runtime activation."""
    agent = await get_owned_agent(request.agent_id, db, current_user)
    previous_config = agent.config
    try:
        update_assistant_skills(agent, skill_id=request.skill_id, install=True)
    except KeyError:
        return _failed_response(
            operation="configure",
            detail=f"Unknown skill: {request.skill_id}",
            status_code=404,
            skill_id=request.skill_id,
        )
    except RuntimeError as exc:
        return _failed_response(
            operation="configure",
            detail=str(exc),
            status_code=409,
            skill_id=request.skill_id,
        )

    log = AgentLog(
        agent_id=agent.id,
        level="info",
        message=f"[ClawHub] Skill configuration request persisted: {request.skill_id}",
        timestamp=datetime.now(timezone.utc),
    )
    db.add(log)
    try:
        await db.commit()
    except SQLAlchemyError:
        logger.exception("Failed to persist ClawHub skill configuration")
        await db.rollback()
        agent.config = previous_config
        return _failed_response(
            operation="configure",
            detail="Failed to persist the skill configuration.",
            status_code=500,
            skill_id=request.skill_id,
        )

    skills = list_assistant_skills(agent)
    skill = _skill_from_payload(skills, request.skill_id)
    if skill is None:
        return _failed_response(
            operation="configure",
            detail=f"Configured skill is missing from the catalog: {request.skill_id}",
            status_code=500,
            skill_id=request.skill_id,
        )
    return {
        "status": skill["status"],
        "operation": "configure",
        "skill_id": request.skill_id,
        "configured": skill["configured"],
        "runtime_ready": skill["runtime_ready"],
        "reconciliation_required": skill["reconciliation_required"],
        "detail": skill["status_detail"],
        "skill": skill,
        "skills": skills,
    }


@router.post("/install-bundle")
async def install_bundle(
    request: InstallSkillBundleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Configures available bundle skills and reports runtime reconciliation separately."""
    agent = await get_owned_agent(request.agent_id, db, current_user)
    previous_config = agent.config
    try:
        result = install_skill_bundle(agent, bundle_id=request.bundle_id)
    except KeyError:
        return _failed_response(
            operation="configure_bundle",
            detail=f"Unknown bundle: {request.bundle_id}",
            status_code=404,
            bundle_id=request.bundle_id,
        )

    skills = list_assistant_skills(agent)
    bundle_skill_ids = set(result["configured_skill_ids"] + result["unavailable_skill_ids"])
    bundle_skills = [skill for skill in skills if skill["id"] in bundle_skill_ids]
    runtime_ready_skill_ids = [skill["id"] for skill in bundle_skills if skill["runtime_ready"]]
    failed_skill_ids = [skill["id"] for skill in bundle_skills if skill["status"] == "failed"]
    reconciliation_required_skill_ids = [
        skill["id"] for skill in bundle_skills if skill["reconciliation_required"]
    ]

    log = AgentLog(
        agent_id=agent.id,
        level="info",
        message=(
            f"[ClawHub] Bundle configured for {request.bundle_id} "
            f"({len(result['configured_skill_ids'])} skills configured, "
            f"{len(result['unavailable_skill_ids'])} unavailable)"
        ),
        timestamp=datetime.now(timezone.utc),
    )
    db.add(log)
    try:
        await db.commit()
    except SQLAlchemyError:
        logger.exception("Failed to persist ClawHub bundle configuration")
        await db.rollback()
        agent.config = previous_config
        return _failed_response(
            operation="configure_bundle",
            detail="Failed to persist the bundle configuration.",
            status_code=500,
            bundle_id=request.bundle_id,
        )

    if failed_skill_ids:
        status = "failed"
    elif (
        runtime_ready_skill_ids
        and len(runtime_ready_skill_ids) == len(bundle_skill_ids)
        and not result["unavailable_skill_ids"]
    ):
        status = "runtime_ready"
    elif result["configured_skill_ids"]:
        status = "configured"
    else:
        status = "unavailable"

    if failed_skill_ids:
        detail = "Bundle configuration was saved, but runtime reconciliation has failed."
    elif reconciliation_required_skill_ids:
        detail = "Bundle configuration was saved. Runtime reconciliation is still required."
    elif status == "runtime_ready":
        detail = "Every configured bundle skill has runtime reconciliation evidence."
    else:
        detail = "No bundle skills could be configured because their files are unavailable."

    return {
        "status": status,
        "operation": "configure_bundle",
        "bundle_id": request.bundle_id,
        "configured_skill_ids": result["configured_skill_ids"],
        "newly_configured_skill_ids": result["newly_configured_skill_ids"],
        # Compatibility alias: installed now means runtime-ready, never merely configured.
        "installed_skill_ids": runtime_ready_skill_ids,
        "runtime_ready_skill_ids": runtime_ready_skill_ids,
        "reconciliation_required_skill_ids": reconciliation_required_skill_ids,
        "unavailable_skill_ids": result["unavailable_skill_ids"],
        "failed_skill_ids": failed_skill_ids,
        "reconciliation_required": bool(reconciliation_required_skill_ids),
        "detail": detail,
        "skills": skills,
    }


@router.post("/uninstall")
async def uninstall_skill(
    request: InstallSkillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    """Removes a skill request and its persisted reconciliation evidence."""
    agent = await get_owned_agent(request.agent_id, db, current_user)
    previous_config = agent.config
    was_configured = request.skill_id in set(list_configured_skill_ids(agent))
    if find_skill_catalog_item(request.skill_id) is None and not was_configured:
        return _failed_response(
            operation="remove",
            detail=f"Unknown skill: {request.skill_id}",
            status_code=404,
            skill_id=request.skill_id,
        )
    update_assistant_skills(agent, skill_id=request.skill_id, install=False)
    log = AgentLog(
        agent_id=agent.id,
        level="info",
        message=(
            f"[ClawHub] Removed skill configuration: {request.skill_id}"
            if was_configured
            else f"[ClawHub] Skill was already not configured: {request.skill_id}"
        ),
        timestamp=datetime.now(timezone.utc),
    )
    db.add(log)
    try:
        await db.commit()
    except SQLAlchemyError:
        logger.exception("Failed to persist ClawHub skill removal")
        await db.rollback()
        agent.config = previous_config
        return _failed_response(
            operation="remove",
            detail="Failed to persist removal of the skill configuration.",
            status_code=500,
            skill_id=request.skill_id,
        )

    skills = list_assistant_skills(agent)
    skill = _skill_from_payload(skills, request.skill_id)
    return {
        "status": "removed" if was_configured else "not_configured",
        "operation": "remove",
        "skill_id": request.skill_id,
        "configured": False,
        "runtime_ready": False,
        "reconciliation_required": False,
        "detail": (
            "Skill configuration and reconciliation evidence were removed."
            if was_configured
            else "The skill was not configured for this assistant."
        ),
        "skill": skill,
        "skills": skills,
    }
