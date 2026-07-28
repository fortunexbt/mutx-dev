import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database import get_db
from src.api.auth.dependencies import require_roles
from src.api.models import get_quota
from src.api.models.models import APIKey, User
from src.api.models.schemas import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyHistoryResponse,
    APIKeyResponse,
)
from src.api.services.user_service import generate_api_key, hash_api_key

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


async def get_owned_api_key(
    db: AsyncSession, user_id: uuid.UUID, key_id: uuid.UUID
) -> APIKey | None:
    result = await db.execute(select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id))
    return result.scalar_one_or_none()


async def count_active_api_keys(db: AsyncSession, user_id: uuid.UUID) -> int:
    count_result = await db.execute(
        select(func.count()).select_from(APIKey).where(APIKey.user_id == user_id, APIKey.is_active),
    )
    return count_result.scalar() or 0


@router.get("", response_model=APIKeyHistoryResponse)
async def list_api_keys(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for the current user, including revoked keys for auditability."""
    # Get total count
    total_stmt = select(func.count()).select_from(APIKey).where(APIKey.user_id == current_user.id)
    total = (await db.execute(total_stmt)).scalar_one()

    # Get paginated results
    query = (
        select(APIKey)
        .where(APIKey.user_id == current_user.id)
        .order_by(APIKey.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    keys = result.scalars().all()

    return APIKeyHistoryResponse(
        items=keys,
        total=total,
        skip=skip,
        limit=limit,
        has_more=total > skip + len(keys),
    )


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: uuid.UUID,
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
    db: AsyncSession = Depends(get_db),
):
    """Get a single API key by ID."""
    api_key = await get_owned_api_key(db, current_user.id, key_id)

    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    return api_key


@router.post("", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(require_roles("DEVELOPER")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key."""
    active_key_count = await count_active_api_keys(db, current_user.id)
    quota = get_quota(current_user.plan)
    max_keys = quota.max_api_keys
    if max_keys != -1 and active_key_count >= max_keys:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active API key limit reached for your plan ({current_user.plan}): {max_keys} keys",
        )

    plain_key, key_prefix = generate_api_key()
    key_hash = hash_api_key(plain_key)

    expires_at = None
    if key_data.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=key_data.expires_in_days)

    api_key = APIKey(
        id=uuid.uuid4(),
        user_id=current_user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=key_data.name,
        expires_at=expires_at,
        is_active=True,
    )

    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return APIKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key=plain_key,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    current_user: User = Depends(require_roles("DEVELOPER")),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key without deleting its record."""
    api_key = await get_owned_api_key(db, current_user.id, key_id)

    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if not api_key.is_active:
        return None

    api_key.is_active = False
    await db.commit()

    return None


@router.post("/{key_id}/rotate", response_model=APIKeyCreateResponse)
async def rotate_api_key(
    key_id: uuid.UUID,
    current_user: User = Depends(require_roles("DEVELOPER")),
    db: AsyncSession = Depends(get_db),
):
    """Rotate an active API key by revoking the old one and issuing a new one."""
    old_key = await get_owned_api_key(db, current_user.id, key_id)

    if not old_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if not old_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="API key is already revoked and cannot be rotated",
        )

    plain_key, key_prefix = generate_api_key()
    key_hash = hash_api_key(plain_key)

    old_key.is_active = False

    new_key = APIKey(
        id=uuid.uuid4(),
        user_id=current_user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=old_key.name,
        expires_at=old_key.expires_at,
        is_active=True,
    )

    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    return APIKeyCreateResponse(
        id=new_key.id,
        name=new_key.name,
        key=plain_key,
        created_at=new_key.created_at,
        expires_at=new_key.expires_at,
    )
