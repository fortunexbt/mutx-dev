from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import require_roles
from src.api.auth.ownership import (
    get_owned_agent as _get_owned_agent,
    get_owned_deployment as _get_owned_deployment,
)
from src.api.database import get_db
from src.api.models import Agent, AgentStatus, AgentType, User
from src.api.models.schemas import (
    AssistantTemplateResponse,
    StarterDeploymentCreate,
    StarterDeploymentResponse,
)
from src.api.routes.agents import _serialize_agent
from src.api.routes.deployments import _serialize_deployment
from src.api.services import template_catalog as template_catalog_service
from src.api.services.assistant_control_plane import build_template_config, serialize_config
from src.api.services.deployment_lifecycle import create_deployment_record
from src.api.services.usage import track_usage_best_effort

router = APIRouter(prefix="/templates", tags=["templates"])
logger = logging.getLogger(__name__)

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


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
) -> Any:
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


@router.get("", response_model=list[AssistantTemplateResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    return await template_catalog_service.get_user_template_catalog(db, user=current_user)


@router.get(
    "/state",
    response_model=template_catalog_service.TemplateCatalogStateResponse,
)
async def get_template_catalog_state(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    return await template_catalog_service.get_catalog_state(db, user=current_user)


@router.put(
    "/state",
    response_model=template_catalog_service.TemplateCatalogStateResponse,
)
async def put_template_catalog_state(
    request: template_catalog_service.TemplateCatalogStateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    return await template_catalog_service.update_catalog_state(
        db,
        user=current_user,
        state=request,
    )


@router.post(
    "/custom",
    response_model=AssistantTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_custom_template(
    request: template_catalog_service.CustomTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    if template_catalog_service.is_builtin_template_id(request.id):
        raise HTTPException(status_code=409, detail="Built-in template ids are immutable")
    if await template_catalog_service.get_user_template(
        db,
        user=current_user,
        template_id=request.id,
    ):
        raise HTTPException(status_code=409, detail="A template with this id already exists")
    try:
        return await template_catalog_service.create_custom_template(
            db,
            user=current_user,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/custom/{template_id}",
    response_model=AssistantTemplateResponse,
)
async def put_custom_template(
    template_id: str,
    request: template_catalog_service.CustomTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    if template_catalog_service.is_builtin_template_id(template_id):
        raise HTTPException(status_code=403, detail="Built-in templates are immutable")
    try:
        updated = await template_catalog_service.update_custom_template(
            db,
            user=current_user,
            template_id=template_id,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Custom template not found")
    return updated


@router.delete(
    "/custom/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_custom_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
) -> Response:
    if template_catalog_service.is_builtin_template_id(template_id):
        raise HTTPException(status_code=403, detail="Built-in templates are immutable")
    deleted = await template_catalog_service.delete_custom_template(
        db,
        user=current_user,
        template_id=template_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Custom template not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{template_id}/clone",
    response_model=AssistantTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def clone_template(
    template_id: str,
    request: template_catalog_service.TemplateCloneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    source = await template_catalog_service.get_user_template(
        db,
        user=current_user,
        template_id=template_id,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Starter template not found")
    if template_catalog_service.is_builtin_template_id(request.id):
        raise HTTPException(status_code=409, detail="Built-in template ids are immutable")
    if await template_catalog_service.get_user_template(
        db,
        user=current_user,
        template_id=request.id,
    ):
        raise HTTPException(status_code=409, detail="A template with this id already exists")
    try:
        return await template_catalog_service.clone_user_template(
            db,
            user=current_user,
            source=source,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _replay_deployment(
    result: dict[str, object],
    *,
    db: AsyncSession,
    current_user: User,
) -> dict[str, object]:
    try:
        agent_id = uuid.UUID(str(result["agent_id"]))
        deployment_id = uuid.UUID(str(result["deployment_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Stored idempotent deployment result is unavailable",
        ) from exc

    agent = await get_owned_agent(agent_id, db, current_user)
    deployment = await get_owned_deployment(
        deployment_id,
        db,
        current_user,
        include_events=True,
    )
    return {
        "template_id": str(result["template_id"]),
        "agent": _serialize_agent(agent),
        "deployment": _serialize_deployment(deployment),
    }


@router.post(
    "/{template_id}/deploy",
    response_model=StarterDeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def deploy_template(
    template_id: str,
    request: StarterDeploymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    template = await template_catalog_service.get_user_template(
        db,
        user=current_user,
        template_id=template_id,
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Starter template not found")
    current_user_id = current_user.id

    if idempotency_key is not None and not IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key must contain 1-128 letters, numbers, or ._:- characters",
        )

    channels = {key: value.model_dump(exclude_none=True) for key, value in request.channels.items()}
    if template.get("category") == "custom" and not template.get("is_official"):
        try:
            config = template_catalog_service.build_custom_deployment_config(
                template,
                name=request.name,
                description=request.description,
                model=request.model,
                workspace=request.workspace,
                assistant_id=request.assistant_id,
                skills=request.skills,
                skills_provided="skills" in request.model_fields_set,
                channels=channels,
                runtime_metadata=request.runtime_metadata,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        try:
            config = build_template_config(
                template_id=template_id,
                name=request.name,
                description=request.description,
                model=request.model,
                workspace=request.workspace,
                assistant_id=request.assistant_id,
                skills=request.skills,
                channels=channels,
                runtime_metadata=request.runtime_metadata,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Starter template not found") from exc
        if "skills" in request.model_fields_set and not request.skills:
            config["skills"] = []

    request_hash = template_catalog_service.deployment_request_hash(
        template_id,
        request.model_dump(mode="json"),
    )
    if idempotency_key is not None:
        try:
            existing_result = await template_catalog_service.claim_deployment_idempotency(
                db,
                user=current_user,
                idempotency_key=idempotency_key,
                template_id=template_id,
                request_hash=request_hash,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if existing_result is not None:
            return await _replay_deployment(existing_result, db=db, current_user=current_user)

    try:
        agent = Agent(
            name=request.name,
            description=request.description,
            type=AgentType.OPENCLAW,
            config=serialize_config(config),
            user_id=current_user.id,
            status=AgentStatus.CREATING.value,
        )
        db.add(agent)
        await db.flush()

        deployment = await create_deployment_record(
            agent=agent,
            db=db,
            replicas=request.replicas,
            event_type="starter.create",
        )

        await db.commit()
        await db.refresh(agent)
    except Exception:
        await db.rollback()
        if idempotency_key is not None:
            try:
                await template_catalog_service.release_deployment_idempotency(
                    db,
                    user_id=current_user_id,
                    idempotency_key=idempotency_key,
                )
            except Exception:
                await db.rollback()
                logger.warning(
                    "Failed to release template deployment idempotency claim", exc_info=True
                )
        raise

    agent_id = agent.id
    deployment_id = deployment.id
    deployment = await get_owned_deployment(
        deployment_id,
        db,
        current_user,
        include_events=True,
    )
    agent_payload = _serialize_agent(agent)
    deployment_payload = _serialize_deployment(deployment)

    if idempotency_key is not None:
        try:
            await template_catalog_service.complete_deployment_idempotency(
                db,
                user=current_user,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                template_id=template_id,
                agent_id=str(agent_id),
                deployment_id=str(deployment_id),
            )
        except Exception:
            await db.rollback()
            logger.warning(
                "Deployment %s succeeded but its idempotency receipt could not be finalized",
                deployment_id,
                exc_info=True,
            )

    await track_usage_best_effort(
        db=db,
        user_id=current_user_id,
        event_type="starter_deployment_create",
        resource_type="deployment",
        resource_id=str(deployment_id),
        metadata={"template_id": template_id, "agent_type": AgentType.OPENCLAW.value},
    )
    logger.info("Created starter deployment %s for user %s", deployment_id, current_user_id)

    return {
        "template_id": template_id,
        "agent": agent_payload,
        "deployment": deployment_payload,
    }
