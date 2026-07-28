"""Internal JWT creation and role-based access control helpers.

OIDC validation lives in :mod:`src.api.auth.oidc`. Its public types are
re-exported here to preserve compatibility for existing SDK and route imports.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
import uuid

from jose import JWTError, jwt
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import oidc
from src.api.auth.password import hash_password, verify_password
from src.api.models.models import ExternalAuthIdentity, RefreshTokenSession, User
from src.api.security import hash_token_value
from src.api.services.social_auth import OAuthUserProfile

PROVIDER_JWKS_URLS = oidc.PROVIDER_JWKS_URLS
PROVIDER_OIDC_CONFIG = oidc.PROVIDER_OIDC_CONFIG
PROVIDER_USERINFO_URLS = oidc.PROVIDER_USERINFO_URLS
SSOProvider = oidc.SSOProvider
TokenPayload = oidc.TokenPayload
verify_oauth_token = oidc.verify_oauth_token

ALGORITHM = "HS256"


class OAuthIdentityConflictError(Exception):
    """Raised when an OAuth subject cannot be deterministically linked."""


async def get_auth_user_by_email(session: AsyncSession, email: str) -> User | None:
    normalized_email = email.strip().casefold()
    result = await session.execute(select(User).where(func.lower(User.email) == normalized_email))
    return result.scalar_one_or_none()


async def authenticate_password_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User | None:
    user = await get_auth_user_by_email(session, email)
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        return None
    return user


async def consume_email_verification_token(session: AsyncSession, token: str) -> User | None:
    """Atomically consume an unexpired email verification token."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(User)
        .where(
            User.email_verification_token == hash_token_value(token),
            User.email_verification_expires_at.is_not(None),
            User.email_verification_expires_at > now,
            User.is_email_verified.is_(False),
        )
        .values(
            is_email_verified=True,
            email_verified_at=now,
            email_verification_token=None,
            email_verification_expires_at=None,
            updated_at=now,
        )
        .returning(User)
        .execution_options(synchronize_session=False)
    )
    user = result.scalar_one_or_none()
    if user is None:
        await session.rollback()
        return None

    await session.commit()
    return user


async def consume_password_reset_token(
    session: AsyncSession,
    *,
    token: str,
    new_password: str,
) -> User | None:
    """Atomically reset a password and revoke all active refresh sessions."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(User)
        .where(
            User.password_reset_token == hash_token_value(token),
            User.password_reset_expires_at.is_not(None),
            User.password_reset_expires_at > now,
            User.password_hash.is_not(None),
        )
        .values(
            password_hash=hash_password(new_password),
            password_reset_token=None,
            password_reset_expires_at=None,
            updated_at=now,
        )
        .returning(User)
        .execution_options(synchronize_session=False)
    )
    user = result.scalar_one_or_none()
    if user is None:
        await session.rollback()
        return None

    await session.execute(
        update(RefreshTokenSession)
        .where(
            RefreshTokenSession.user_id == user.id,
            RefreshTokenSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return user


async def resolve_external_auth_user(
    session: AsyncSession,
    *,
    provider: str,
    provider_user_id: str,
    email: str,
    email_verified: bool,
    display_name: str,
    username: str | None = None,
    avatar_url: str | None = None,
    profile: dict | None = None,
) -> User:
    """Resolve a verified external subject to a least-privilege local user.

    Authorization claims from the provider are intentionally not accepted by
    this boundary. A new external user receives the model's persisted VIEWER
    default; privileged roles require a separate explicit database assignment.
    """
    provider = provider.strip().casefold()
    provider_user_id = provider_user_id.strip()
    normalized_email = email.strip().casefold()
    display_name = display_name.strip() or normalized_email.split("@", 1)[0]
    if not provider or not provider_user_id or not normalized_email or not email_verified:
        raise ValueError("OAuth provider identity is incomplete or unverified")

    result = await session.execute(
        select(ExternalAuthIdentity).where(
            ExternalAuthIdentity.provider == provider,
            ExternalAuthIdentity.provider_user_id == provider_user_id,
        )
    )
    identity = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if identity is not None:
        user_result = await session.execute(select(User).where(User.id == identity.user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise ValueError("OAuth identity is not attached to a local user")

        email_owner = await get_auth_user_by_email(session, normalized_email)
        may_sync_user_email = (
            user.password_hash is None
            and user.email.casefold() != normalized_email
            and (email_owner is None or email_owner.id == user.id)
        )
        identity.provider_email = normalized_email
        identity.provider_username = username
        identity.provider_display_name = display_name
        identity.avatar_url = avatar_url
        identity.profile = profile
        identity.updated_at = now
        if may_sync_user_email:
            user.email = normalized_email
        if not user.is_email_verified:
            user.is_email_verified = True
            user.email_verified_at = now
            user.email_verification_token = None
            user.email_verification_expires_at = None
            user.updated_at = now
        if user.password_hash is None:
            # Passwordless identities are never eligible for unauthenticated
            # password recovery, including tokens issued before a provider
            # changed its verified email.
            user.password_reset_token = None
            user.password_reset_expires_at = None

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            if not may_sync_user_email:
                raise

            # Another transaction may have claimed the provider's new email
            # after our conflict check. Preserve the stable provider subject,
            # but never take an email already owned by another local account.
            identity_result = await session.execute(
                select(ExternalAuthIdentity).where(
                    ExternalAuthIdentity.provider == provider,
                    ExternalAuthIdentity.provider_user_id == provider_user_id,
                )
            )
            identity = identity_result.scalar_one_or_none()
            if identity is None:
                raise OAuthIdentityConflictError(
                    "OAuth identity changed during verified email synchronization."
                ) from exc
            user_result = await session.execute(select(User).where(User.id == identity.user_id))
            user = user_result.scalar_one_or_none()
            if user is None:
                raise ValueError("OAuth identity is not attached to a local user") from exc
            email_owner = await get_auth_user_by_email(session, normalized_email)
            if email_owner is None or email_owner.id == user.id:
                raise OAuthIdentityConflictError(
                    "OAuth identity email synchronization conflicted with another transaction."
                ) from exc

            identity.provider_email = normalized_email
            identity.provider_username = username
            identity.provider_display_name = display_name
            identity.avatar_url = avatar_url
            identity.profile = profile
            identity.updated_at = now
            user.password_reset_token = None
            user.password_reset_expires_at = None
            await session.commit()
        await session.refresh(user)
        return user

    if await get_auth_user_by_email(session, normalized_email) is not None:
        raise OAuthIdentityConflictError(
            "A local account already uses this email; sign in to that account first."
        )

    user = User(
        id=uuid.uuid4(),
        email=normalized_email,
        name=display_name,
        password_hash=None,
        plan="FREE",
        is_active=True,
        is_email_verified=True,
        email_verified_at=now,
    )
    identity = ExternalAuthIdentity(
        id=uuid.uuid4(),
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        provider_email=normalized_email,
        provider_username=username,
        provider_display_name=display_name,
        avatar_url=avatar_url,
        profile=profile,
    )
    session.add_all([user, identity])
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        result = await session.execute(
            select(ExternalAuthIdentity).where(
                ExternalAuthIdentity.provider == provider,
                ExternalAuthIdentity.provider_user_id == provider_user_id,
            )
        )
        concurrent_identity = result.scalar_one_or_none()
        if concurrent_identity is None:
            raise OAuthIdentityConflictError(
                "A local account already uses this email; sign in to that account first."
            ) from exc
        user_result = await session.execute(
            select(User).where(User.id == concurrent_identity.user_id)
        )
        concurrent_user = user_result.scalar_one_or_none()
        if concurrent_user is None:
            raise ValueError("OAuth identity is not attached to a local user") from exc
        return concurrent_user

    await session.refresh(user)
    return user


async def resolve_oauth_user(session: AsyncSession, profile: OAuthUserProfile) -> User:
    """Resolve a social OAuth profile through the canonical external identity boundary."""
    return await resolve_external_auth_user(
        session,
        provider=profile.provider.value,
        provider_user_id=profile.provider_user_id,
        email=profile.email,
        email_verified=profile.email_verified,
        display_name=profile.display_name,
        username=profile.username,
        avatar_url=profile.avatar_url,
        profile=profile.profile,
    )


def create_access_token(
    payload: TokenPayload,
    secret: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a JWT access token (HS256) with the given payload.

    Args:
        payload: TokenPayload containing sub, email, roles, exp
        secret: JWT secret key for signing
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT string
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=24)

    expire = datetime.now(timezone.utc) + expires_delta

    to_encode = {
        "sub": payload.sub,
        "email": payload.email,
        "roles": payload.roles,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    encoded_jwt = jwt.encode(to_encode, secret, algorithm=ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str, secret: str) -> TokenPayload:
    """
    Verify and decode an access token.

    Args:
        token: JWT string to verify
        secret: JWT secret key for verification

    Returns:
        TokenPayload with decoded data

    Raises:
        HTTPException: If token is invalid or expired
    """
    from fastapi import HTTPException, status

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"require_exp": True, "require_sub": True},
        )

        subject = payload.get("sub")
        email = payload.get("email")
        roles = payload.get("roles")
        if not isinstance(subject, str) or not subject:
            raise JWTError("Missing token subject")
        if not isinstance(email, str) or not isinstance(roles, list):
            raise JWTError("Malformed token identity claims")

        return TokenPayload(
            sub=subject,
            email=email,
            roles=roles,
            exp=datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


class Role(str, Enum):
    """User roles for RBAC."""

    ADMIN = "ADMIN"  # Full access
    DEVELOPER = "DEVELOPER"  # Read/write agents, no billing
    VIEWER = "VIEWER"  # Read-only access
    AUDIT_ADMIN = "AUDIT_ADMIN"  # Audit logs only


def check_role(user_roles: list[str], required_roles: list[Role]) -> bool:
    """
    Check if user has any of the required roles.

    Args:
        user_roles: List of user's roles
        required_roles: List of roles that grant access

    Returns:
        True if user has at least one required role
    """
    user_roles_upper = {
        role.strip().upper() for role in user_roles if isinstance(role, str) and role.strip()
    }
    required_roles_upper = {role.value.upper() for role in required_roles}

    # ADMIN has access to everything
    if Role.ADMIN.value in user_roles_upper:
        return True

    return bool(user_roles_upper & required_roles_upper)
