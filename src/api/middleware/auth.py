import uuid
from functools import wraps
from typing import Callable, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.auth.jwt import verify_access_token
from src.api.config import get_settings
from src.api.database import async_session_maker, get_db
from src.api.models.models import Agent, User
from src.api.services.user_service import (
    UserService,
    extract_agent_api_key_prefix,
    verify_api_key,
)


async def _resolve_user_from_bearer_token(
    token: str,
    session: AsyncSession,
    *,
    user_service: UserService | None = None,
) -> Optional[User]:
    """Resolve an active user from a bearer token (JWT first, then API key fallback)."""
    service = user_service or UserService(session)

    user_id = verify_access_token(token)
    if user_id:
        user = await service.get_user_by_id(user_id)
        if user and user.is_active:
            return user

    user = await service.get_user_for_api_key(token)
    if user and user.is_active:
        return user

    return None


def _enforce_email_verification_if_required(user: User) -> None:
    settings = get_settings()
    if settings.require_email_verification and not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification is required",
        )


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


async def _resolve_state_user(request: Request, session: AsyncSession) -> Optional[User]:
    user_id = getattr(request.state, "auth_user_id", None)
    if not user_id:
        return None

    user_service = UserService(session)
    user = await user_service.get_user_by_id(user_id)
    if user and user.is_active:
        _enforce_email_verification_if_required(user)
        return user

    return None


async def _populate_api_key_context(request: Request, token: str) -> None:
    try:
        async with async_session_maker() as session:
            user_service = UserService(session)
            auth_context = await user_service.authenticate_api_key(token)
    except Exception:
        request.state.auth_credential_error = "lookup_failed"
        return

    if not auth_context:
        request.state.auth_credential_error = "invalid"
        return

    user, managed_api_key_id = auth_context
    request.state.auth_user_id = user.id
    request.state.auth_method = "api_key"
    request.state.auth_api_key_id = managed_api_key_id
    request.state.auth_api_key_identifier = f"managed:{managed_api_key_id}"
    request.state.auth_credential_error = None


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Resolve auth context early for downstream middleware and handlers."""

    async def dispatch(self, request: Request, call_next: Callable):
        request.state.auth_user_id = None
        request.state.auth_method = None
        request.state.auth_api_key_id = None
        request.state.auth_api_key_identifier = None
        request.state.auth_credential_error = None

        bearer_token = _extract_bearer_token(request.headers.get("Authorization"))
        x_api_key = request.headers.get("X-API-Key")

        if bearer_token:
            user_id = verify_access_token(bearer_token)
            if user_id:
                request.state.auth_user_id = user_id
                request.state.auth_method = "jwt"
            elif bearer_token.startswith("mutx_live_"):
                await _populate_api_key_context(request, bearer_token)
            else:
                # Arbitrary legacy bearer keys are still resolved by the request-scoped
                # dependency. Avoid turning a malformed or expired JWT into a global
                # database lookup whose outage can mask the correct 401 response.
                request.state.auth_credential_error = "invalid"
        elif x_api_key:
            await _populate_api_key_context(request, x_api_key)

        return await call_next(request)


def add_authentication_middleware(app: FastAPI) -> None:
    app.add_middleware(AuthenticationMiddleware)


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db),
) -> User:
    state_user = await _resolve_state_user(request, session)
    if state_user:
        return state_user

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_service = UserService(session)
    user = await _resolve_user_from_bearer_token(token, session, user_service=user_service)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _enforce_email_verification_if_required(user)

    return user


def assert_internal_user(user: User) -> None:
    """Restrict access to verified users on configured internal email domains."""
    if not user.is_email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    settings = get_settings()
    allowed_domains = {
        domain.strip().lower()
        for domain in settings.internal_user_email_domains
        if domain and domain.strip()
    }

    user_domain = user.email.rsplit("@", 1)[-1].lower() if "@" in user.email else ""
    if user_domain not in allowed_domains:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


async def get_current_internal_user(
    user: User = Depends(get_current_user),
) -> User:
    assert_internal_user(user)
    return user


async def get_current_user_optional(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_db),
) -> Optional[User]:
    state_user = await _resolve_state_user(request, session)
    if state_user:
        return state_user

    credential_error = getattr(request.state, "auth_credential_error", None)
    if credential_error == "lookup_failed":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
            headers={"Retry-After": "1"},
        )

    if not authorization and x_api_key:
        if credential_error == "invalid":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
                headers={"WWW-Authenticate": "API-Key"},
            )
        try:
            user = await UserService(session).get_user_for_api_key(x_api_key)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service is temporarily unavailable",
                headers={"Retry-After": "1"},
            ) from exc
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
                headers={"WWW-Authenticate": "API-Key"},
            )
        _enforce_email_verification_if_required(user)
        return user

    if not authorization:
        return None

    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_service = UserService(session)
    user = await _resolve_user_from_bearer_token(token, session, user_service=user_service)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _enforce_email_verification_if_required(user)
    return user


async def get_api_key_user(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Authenticate using any active user-owned API key."""
    if getattr(request.state, "auth_method", None) == "api_key":
        state_user = await _resolve_state_user(request, session)
        if state_user:
            return state_user

    if not x_api_key:
        return None

    user_service = UserService(session)
    user = await user_service.get_user_for_api_key(x_api_key)
    if user:
        _enforce_email_verification_if_required(user)
    return user


async def get_user_from_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Authenticate using any active user-owned API key."""
    if getattr(request.state, "auth_method", None) == "api_key":
        state_user = await _resolve_state_user(request, session)
        if state_user:
            return state_user

    if not x_api_key:
        return None

    user_service = UserService(session)
    user = await user_service.get_user_for_api_key(x_api_key)
    if user:
        _enforce_email_verification_if_required(user)
    return user


async def get_current_user_or_api_key(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate using either JWT Bearer token or API key."""
    state_user = await _resolve_state_user(request, session)
    if state_user:
        return state_user

    user_service = UserService(session)

    # Try Authorization header first (JWT or API key in Bearer token)
    token = _extract_bearer_token(authorization)
    if token:
        user = await _resolve_user_from_bearer_token(token, session, user_service=user_service)
        if user:
            _enforce_email_verification_if_required(user)
            return user

    # Try explicit API key header
    if x_api_key:
        user = await user_service.get_user_for_api_key(x_api_key)
        if user:
            _enforce_email_verification_if_required(user)
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_agent(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db),
):
    """Authenticate an agent using its API key in the Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    agent = None
    candidate_agents: list[Agent] = []

    if token.startswith("mutx_agent_"):
        candidate_agent_id = None
        token_parts = token.split("_", 3)
        if len(token_parts) >= 4:
            try:
                candidate_agent_id = uuid.UUID(hex=token_parts[2])
            except ValueError:
                candidate_agent_id = None

        if candidate_agent_id is not None:
            result = await session.execute(select(Agent).where(Agent.id == candidate_agent_id))
            candidate_agent = result.scalar_one_or_none()
            if (
                candidate_agent
                and candidate_agent.api_key
                and verify_api_key(token, candidate_agent.api_key)
            ):
                agent = candidate_agent

        if agent is None:
            candidate_prefix = extract_agent_api_key_prefix(token)
            if candidate_prefix is not None:
                result = await session.execute(
                    select(Agent).where(Agent.api_key_prefix == candidate_prefix)
                )
                candidate_agents = list(result.scalars().all())

    if agent is None:
        if not candidate_agents:
            result = await session.execute(
                select(Agent).where(Agent.api_key.is_not(None), Agent.api_key_prefix.is_(None))
            )
            candidate_agents = list(result.scalars().all())

        for candidate_agent in candidate_agents:
            if candidate_agent.api_key and verify_api_key(token, candidate_agent.api_key):
                agent = candidate_agent
                break

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return agent


async def get_authenticated_user(
    user: User = Depends(get_current_user),
) -> User:
    return user


def require_auth(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    return wrapper


# Plan hierarchy: each plan includes access to all lower tiers
_PLAN_HIERARCHY: dict[str, int] = {
    "FREE": 0,
    "STARTER": 1,
    "PRO": 2,
    "ENTERPRISE": 3,
}


def require_plan(min_plan: str):
    """FastAPI dependency factory that enforces minimum plan tier.

    Usage:
        @router.post("/feature", dependencies=[Depends(require_plan("pro"))])
        async def feature(...): ...

    Returns 402 with upgrade_url if user's plan is insufficient.
    """
    min_level = _PLAN_HIERARCHY.get(min_plan.upper(), 0)

    async def _check_plan(
        user: User = Depends(get_current_user),
    ) -> User:
        user_level = _PLAN_HIERARCHY.get((user.plan or "FREE").upper(), 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"This feature requires the {min_plan} plan or higher",
                headers={"Upgrade-URL": "/pricing"},
            )
        return user

    return _check_plan
