"""
Policy management routes — CRUD + SSE hot-reload endpoint.
"""

import asyncio
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import require_roles
from src.api.database import get_db
from src.api.models import User
from src.api.services.policy_store import (
    Policy,
    PolicyConflictError,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
    PolicyIdentityMismatchError,
    PolicyNotFoundError,
    PolicyStore,
    PolicyUpdate,
    PolicyVersionConflictError,
)

router = APIRouter(prefix="/policies", tags=["policies"])
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _read_store(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("VIEWER", "DEVELOPER"))],
) -> PolicyStore:
    return PolicyStore(db, user.id)


async def _developer_store(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("DEVELOPER"))],
) -> PolicyStore:
    return PolicyStore(db, user.id)


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------


@router.get("", response_model=list[Policy])
async def list_policies(
    store: Annotated[PolicyStore, Depends(_read_store)],
):
    """List policies owned by the authenticated user."""
    return await store.list_policies()


@router.post("", response_model=Policy, status_code=status.HTTP_201_CREATED)
async def create_policy(
    policy: Policy,
    store: Annotated[PolicyStore, Depends(_developer_store)],
):
    """Create a new policy."""
    try:
        return await store.create_policy(policy)
    except PolicyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Policy '{policy.name}' already exists",
        ) from exc


@router.post("/evaluate", response_model=PolicyEvaluationResult)
async def evaluate_policies(
    context: PolicyEvaluationContext,
    store: Annotated[PolicyStore, Depends(_developer_store)],
):
    """Evaluate this tenant's enabled policies against a pending action context."""
    return await store.evaluate(context)


@router.get("/{name}", response_model=Policy)
async def get_policy(
    name: str,
    store: Annotated[PolicyStore, Depends(_read_store)],
):
    """Fetch a single policy by name."""
    policy = await store.get_policy(name)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


@router.put("/{name}", response_model=Policy)
async def update_policy(
    name: str,
    policy: PolicyUpdate,
    store: Annotated[PolicyStore, Depends(_developer_store)],
):
    """Completely replace a policy when its owner, identity, and version match."""
    try:
        return await store.update_policy(name, policy)
    except PolicyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Policy not found",
        ) from exc
    except PolicyIdentityMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PolicyVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PolicyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    name: str,
    store: Annotated[PolicyStore, Depends(_developer_store)],
):
    """Delete a policy by name."""
    deleted = await store.delete_policy(name)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")


# ------------------------------------------------------------------
# SSE hot-reload
# ------------------------------------------------------------------


async def _sse_reload_generator(
    store: PolicyStore,
    policy_name: str,
    initial_version: int,
):
    """
    Yield SSE events as long as the policy version has not changed.
    Exits when the policy is updated or deleted.
    """
    try:
        # Send initial connected comment
        yield 'data: {"event":"connected","policy":"' + policy_name + '"}\n\n'
        while True:
            await asyncio.sleep(5)
            current = await store.get_policy(policy_name)
            if current is None:
                # Policy was deleted — send end signal and exit
                yield 'data: {"event":"deleted","policy":"' + policy_name + '"}\n\n'
                break
            if current.version != initial_version:
                # Version changed — send reload event and exit
                yield f"data: {json.dumps({'event': 'reload', 'policy': policy_name, 'version': current.version})}\n\n"
                break
    except asyncio.CancelledError:
        # Client disconnected gracefully
        pass


@router.post("/{name}/reload")
async def reload_policy(
    name: str,
    store: Annotated[PolicyStore, Depends(_read_store)],
):
    """
    SSE endpoint that pushes a 'reload' event when the named policy is
    updated (version increments) or deleted.

    The stream stays open and monitors the policy version, exiting when
    a change is detected so clients can re-fetch the policy.
    """
    policy = await store.get_policy(name)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")

    initial_version = policy.version

    async def event_generator():
        async for chunk in _sse_reload_generator(store, name, initial_version):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
