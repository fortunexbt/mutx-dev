"""Authenticated, tenant-scoped telemetry backend configuration routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import get_current_internal_user, require_roles
from src.api.database import get_db
from src.api.models import User
from src.api.models.telemetry_schemas import (
    TelemetryConfigRequest,
    TelemetryConfigStatusResponse,
    TelemetryConfigureResponse,
    TelemetryHealthResponse,
)
from src.api.services.telemetry_backend import (
    TelemetryEndpointError,
    configure_telemetry_backend,
    get_current_config,
    get_runtime_telemetry_status,
    get_telemetry_health,
)


async def require_internal_telemetry_admin(
    current_user: User = Depends(require_roles("ADMIN")),
    _internal_user: User = Depends(get_current_internal_user),
) -> User:
    """Require a persisted internal administrator for telemetry operations."""
    return current_user


router = APIRouter(
    prefix="/telemetry",
    tags=["telemetry"],
    dependencies=[Depends(require_internal_telemetry_admin)],
)


@router.get("/config", response_model=TelemetryConfigStatusResponse)
async def get_telemetry_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_internal_telemetry_admin),
) -> TelemetryConfigStatusResponse:
    """Return runtime exporter status and this tenant's saved collector target."""
    config = await get_current_config(db, owner_id=current_user.id)
    otel_enabled, exporter_type = get_runtime_telemetry_status()
    return TelemetryConfigStatusResponse(
        otel_enabled=otel_enabled,
        exporter_type=exporter_type,
        endpoint=config["endpoint"],
        protocol=config["protocol"],
        configured=config["configured"],
        runtime_applied=False,
    )


@router.post("/config", response_model=TelemetryConfigureResponse)
async def configure_telemetry(
    payload: TelemetryConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_internal_telemetry_admin),
) -> TelemetryConfigureResponse:
    """Validate and durably save this tenant's OTLP connectivity target."""
    try:
        config = await configure_telemetry_backend(
            db,
            owner_id=current_user.id,
            otlp_endpoint=payload.otlp_endpoint,
            protocol=payload.protocol,
        )
    except TelemetryEndpointError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    health = await get_telemetry_health(db, owner_id=current_user.id)
    return TelemetryConfigureResponse(
        status="configured",
        runtime_applied=False,
        config=config,
        health=health,
    )


@router.get("/health", response_model=TelemetryHealthResponse)
async def get_telemetry_backend_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_internal_telemetry_admin),
) -> TelemetryHealthResponse:
    """Probe only this tenant's configured collector through a pinned public IP."""
    health = await get_telemetry_health(db, owner_id=current_user.id)
    return TelemetryHealthResponse.model_validate(health)
