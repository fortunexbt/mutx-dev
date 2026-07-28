"""
Credential broker API routes for MUTX governance.
"""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.auth.dependencies import get_current_internal_user, require_roles
from src.api.models import User
from src.api.services.credential_broker import (
    CredentialBackend,
    get_credential_broker,
)

router = APIRouter(prefix="/governance/credentials", tags=["governance"])


async def require_credential_reader(
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
    _internal_user: User = Depends(get_current_internal_user),
) -> User:
    """Require an internal persisted principal with read access."""
    return current_user


async def require_credential_developer(
    current_user: User = Depends(require_roles("DEVELOPER")),
    _internal_user: User = Depends(get_current_internal_user),
) -> User:
    """Require an internal persisted principal with credential mutation access."""
    return current_user


def _broker_for_user(current_user: User):
    return get_credential_broker(namespace=str(current_user.id))


class CredentialBackendRegister(BaseModel):
    name: str
    backend: str
    path: str
    ttl: Optional[int] = 900
    config: dict = Field(default_factory=dict)


class CredentialResponse(BaseModel):
    name: str
    backend: str
    path: str
    value: Optional[str] = None
    has_value: bool = False
    expires_at: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class BackendHealthResponse(BaseModel):
    name: str
    backend: str
    path: str
    ttl: int
    is_active: bool
    is_healthy: bool


@router.get("/backends", response_model=list[BackendHealthResponse])
async def list_credential_backends(
    current_user: User = Depends(require_credential_reader),
):
    """List all registered credential backends."""
    broker = _broker_for_user(current_user)
    backends = await broker.list_backends()
    return [
        BackendHealthResponse(
            name=b["name"],
            backend=b["backend"],
            path=b["path"],
            ttl=b["ttl"],
            is_active=b["is_active"],
            is_healthy=b["is_healthy"],
        )
        for b in backends
    ]


@router.post("/backends", status_code=201)
async def register_credential_backend(
    request: CredentialBackendRegister,
    current_user: User = Depends(require_credential_developer),
):
    """Register a new credential backend."""
    try:
        backend_enum = CredentialBackend(request.backend)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid backend type: {request.backend}. "
            f"Supported: vault, awssecrets, gcpsm, azurekv, onepassword, infisical",
        )

    broker = _broker_for_user(current_user)
    success = await broker.register_backend(
        name=request.name,
        backend=backend_enum,
        path=request.path,
        ttl=timedelta(seconds=request.ttl),
        config=request.config,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to register backend")

    return {"status": "registered", "name": request.name}


@router.delete("/backends/{backend_name}")
async def unregister_credential_backend(
    backend_name: str,
    current_user: User = Depends(require_credential_developer),
):
    """Unregister a credential backend."""
    broker = _broker_for_user(current_user)
    success = await broker.unregister_backend(backend_name)

    if not success:
        raise HTTPException(status_code=404, detail=f"Backend '{backend_name}' not found")

    return {"status": "unregistered", "name": backend_name}


@router.get("/backends/{backend_name}/health")
async def check_backend_health(
    backend_name: str,
    current_user: User = Depends(require_credential_reader),
):
    """Check health of a specific credential backend."""
    broker = _broker_for_user(current_user)
    backends = await broker.list_backends()

    for backend in backends:
        if backend["name"] == backend_name:
            return {
                "name": backend_name,
                "healthy": backend["is_healthy"],
                "backend": backend["backend"],
            }

    raise HTTPException(status_code=404, detail=f"Backend '{backend_name}' not found")


@router.get("/health")
async def check_all_backends_health(
    current_user: User = Depends(require_credential_reader),
):
    """Check health of all credential backends."""
    broker = _broker_for_user(current_user)
    return await broker.health_check()


@router.get("/get/{full_path:path}", response_model=CredentialResponse)
async def get_credential(
    full_path: str,
    current_user: User = Depends(require_credential_reader),
):
    """
    Retrieve a credential by its full path.

    Path format: backend:/path/to/secret
    Examples:
        vault:/secret/myapp/api-key
        awssecrets:/prod/myapp/api-key
        gcpsm:/my-project/my-secret
    """
    broker = _broker_for_user(current_user)
    credential = await broker.get_credential_by_path(full_path, requester_id=str(current_user.id))

    if not credential:
        raise HTTPException(status_code=404, detail=f"Credential not found: {full_path}")

    return CredentialResponse(
        name=credential.name,
        backend=credential.backend,
        path=credential.path,
        value=None,
        has_value=bool(credential.value),
        expires_at=credential.expires_at.isoformat() if credential.expires_at else None,
        metadata=credential.metadata,
    )
