from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_db
from src.api.auth.dependencies import get_current_internal_user, require_roles
from src.api.models import User
from src.api.models.schemas import RuntimeProviderSnapshotResponse, RuntimeProviderSnapshotUpsert
from src.api.services.operator_state import (
    get_runtime_provider_snapshot,
    upsert_runtime_provider_snapshot,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runtime", tags=["runtime"])


async def require_internal_admin(
    current_user: User = Depends(require_roles("ADMIN")),
    _internal_user: User = Depends(get_current_internal_user),
) -> User:
    """Require both a persisted administrator role and internal-user eligibility."""
    return current_user


@router.get("/providers/{provider}", response_model=RuntimeProviderSnapshotResponse)
async def runtime_provider_state(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
):
    return await get_runtime_provider_snapshot(db, user=current_user, provider=provider)


@router.put("/providers/{provider}", response_model=RuntimeProviderSnapshotResponse)
async def upsert_runtime_provider_state(
    provider: str,
    request: RuntimeProviderSnapshotUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("DEVELOPER")),
):
    payload = request.model_dump(mode="json", exclude_none=True)
    payload["provider"] = provider
    return await upsert_runtime_provider_snapshot(
        db,
        user=current_user,
        provider=provider,
        payload=payload,
    )


@router.get("/governance/metrics")
async def governance_metrics(
    current_user: User = Depends(require_internal_admin),
):
    try:
        from cli.faramesh_runtime import (
            collect_faramesh_snapshot,
            generate_prometheus_metrics,
        )

        snapshot = collect_faramesh_snapshot()
        metrics_text = generate_prometheus_metrics(snapshot)
        return Response(content=metrics_text, media_type="text/plain")
    except Exception:
        logger.exception("Failed to generate governance metrics")
        return Response(
            content="# Error: failed to generate governance metrics\n",
            status_code=500,
            media_type="text/plain",
        )


@router.get("/governance/status")
async def governance_status(
    current_user: User = Depends(require_internal_admin),
):
    try:
        from cli.faramesh_runtime import collect_faramesh_snapshot, get_faramesh_health

        health = get_faramesh_health()
        snapshot = collect_faramesh_snapshot()
        return {
            "daemon_reachable": health.daemon_reachable,
            "socket_reachable": health.socket_reachable,
            "policy_loaded": health.policy_loaded,
            "version": health.version,
            "policy_name": health.policy_name,
            "decisions_total": snapshot.decisions_total,
            "permits_today": snapshot.permits_today,
            "denies_today": snapshot.denies_today,
            "defers_today": snapshot.defers_today,
            "pending_approvals": snapshot.pending_approvals,
            "status": snapshot.status,
        }
    except Exception:
        logger.exception("Failed to collect governance status")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to collect governance status"},
        )
