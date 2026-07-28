"""Persistent, single-use OAuth state issuance and validation."""

from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy import delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.models import OAuthAuthorizationState
from src.api.security import hash_token_value


async def issue_oauth_state(
    session: AsyncSession,
    *,
    flow: str,
    provider: str,
    redirect_uri: str,
    ttl_seconds: int,
) -> str:
    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await session.execute(
        delete(OAuthAuthorizationState).where(
            or_(
                OAuthAuthorizationState.expires_at <= now,
                OAuthAuthorizationState.consumed_at.is_not(None),
            )
        )
    )
    session.add(
        OAuthAuthorizationState(
            state_hash=hash_token_value(state),
            flow=flow,
            provider=provider,
            redirect_uri=redirect_uri,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
    )
    await session.commit()
    return state


async def consume_oauth_state(
    session: AsyncSession,
    *,
    state: str,
    flow: str,
    provider: str,
    redirect_uri: str,
) -> bool:
    """Atomically consume a matching unexpired state token."""
    if not state:
        return False

    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(OAuthAuthorizationState)
        .where(
            OAuthAuthorizationState.state_hash == hash_token_value(state),
            OAuthAuthorizationState.flow == flow,
            OAuthAuthorizationState.provider == provider,
            OAuthAuthorizationState.redirect_uri == redirect_uri,
            OAuthAuthorizationState.expires_at > now,
            OAuthAuthorizationState.consumed_at.is_(None),
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.rollback()
        return False

    await session.commit()
    return True
