"""Canonical FastAPI authentication and authorization dependency facade.

Routes should import dependencies from this module. Compatibility modules may
re-export these names, but they must not grow independent auth behavior.
"""

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status

from src.api.config import get_settings
from src.api.middleware.auth import (
    assert_internal_user,
    get_api_key_user,
    get_authenticated_user,
    get_current_agent,
    get_current_internal_user,
    get_current_user,
    get_current_user_optional,
    get_current_user_or_api_key,
    get_user_from_api_key,
    require_auth,
    require_plan,
)
from src.api.models.models import User
from src.api.services.auth import Role, TokenPayload, check_role, verify_access_token

settings = get_settings()


class SSOTokenUser:
    """Lightweight principal derived from a role-bearing SSO token."""

    def __init__(self, token_payload: TokenPayload):
        self.id = token_payload.sub
        self.email = token_payload.email
        self.name = token_payload.email.split("@")[0] if token_payload.email else "SSO User"
        self.roles = token_payload.roles
        self.is_active = True
        self.is_email_verified = True

    def __repr__(self) -> str:
        return f"<SSOTokenUser(id={self.id}, email={self.email}, roles={self.roles})>"


async def get_current_sso_user(
    authorization: str | None = Header(None, alias="Authorization"),
) -> SSOTokenUser:
    """Validate a role-bearing MUTX SSO token from the Authorization header."""
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

    try:
        payload = verify_access_token(parts[1], settings.jwt_secret)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return SSOTokenUser(payload)


def require_role(roles: list[str]) -> Callable[..., object]:
    """Require a persisted role on the canonical dashboard principal.

    The user is reloaded by :func:`get_current_user` for every request, so role
    changes and revocations do not depend on claims embedded in an access token.
    """

    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        required_role_enums: list[Role] = []
        for role_name in roles:
            try:
                required_role_enums.append(Role(role_name.upper()))
            except ValueError:
                continue

        if not check_role(current_user.roles or [], required_role_enums):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {roles}",
            )

        return current_user

    return role_checker


def require_roles(*roles: str) -> Callable[..., object]:
    """Convenience wrapper for :func:`require_role`."""
    return require_role(list(roles))


__all__ = [
    "SSOTokenUser",
    "assert_internal_user",
    "get_api_key_user",
    "get_authenticated_user",
    "get_current_agent",
    "get_current_internal_user",
    "get_current_sso_user",
    "get_current_user",
    "get_current_user_optional",
    "get_current_user_or_api_key",
    "get_user_from_api_key",
    "require_auth",
    "require_plan",
    "require_role",
    "require_roles",
]
