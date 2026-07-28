from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.models import User, UserSetting
from src.api.models.pico_tutor import (
    PicoTutorEntitlement,
    PicoTutorOpenAIConnectionStatus,
    PicoTutorProviderProof,
)
from src.api.security import decrypt_secret_value, encrypt_secret_value

logger = logging.getLogger(__name__)
settings = get_settings()

PICO_TUTOR_OPENAI_KEY = "pico.tutor.openai"
_PLAN_HIERARCHY = {
    "FREE": 0,
    "STARTER": 1,
    "PRO": 2,
    "ENTERPRISE": 3,
}


class _MissingAsyncOpenAI:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(
            "openai package is not installed; install project dependencies to use Pico tutor"
        )


try:
    from openai import AsyncOpenAI
except ModuleNotFoundError:
    AsyncOpenAI = _MissingAsyncOpenAI


class PicoTutorOpenAIConnectionError(ValueError):
    pass


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mask_api_key(api_key: str) -> str:
    trimmed = api_key.strip()
    if len(trimmed) < 4:
        return "stored key"
    return f"••••{trimmed[-4:]}"


def _configured_openai_model() -> str:
    return settings.pico_tutor_model.removeprefix("openai/")


def _normalize_api_key(api_key: str) -> str:
    normalized = api_key.strip()
    if len(normalized) < 10 or any(character.isspace() for character in normalized):
        raise PicoTutorOpenAIConnectionError("OpenAI key must not be empty or contain whitespace.")
    return normalized


def _platform_api_key() -> str | None:
    raw_key = os.getenv("OPENAI_API_KEY")
    if raw_key is None:
        return None
    try:
        return _normalize_api_key(raw_key)
    except PicoTutorOpenAIConnectionError:
        logger.warning("Ignoring invalid whitespace-only or malformed platform OpenAI key")
        return None


def get_pico_tutor_entitlement(user: User) -> PicoTutorEntitlement:
    normalized_plan = str(user.plan or "FREE").strip().upper()
    if normalized_plan not in _PLAN_HIERARCHY:
        normalized_plan = "FREE"
    plan_level = _PLAN_HIERARCHY[normalized_plan]
    return PicoTutorEntitlement(
        plan=normalized_plan.lower(),
        tutorAccess=plan_level >= _PLAN_HIERARCHY["STARTER"],
        byokAccess=plan_level >= _PLAN_HIERARCHY["PRO"],
    )


def require_pico_tutor_access(user: User) -> PicoTutorEntitlement:
    entitlement = get_pico_tutor_entitlement(user)
    if not entitlement.tutorAccess:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TUTOR_PLAN_REQUIRED",
                "message": "Live Pico Tutor requires the Starter plan or higher.",
                "minimumPlan": entitlement.minimumPlan,
                "upgradeUrl": "/pico/pricing",
            },
        )
    return entitlement


def require_pico_tutor_byok_access(user: User) -> PicoTutorEntitlement:
    entitlement = require_pico_tutor_access(user)
    if not entitlement.byokAccess:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TUTOR_BYOK_PLAN_REQUIRED",
                "message": "Connecting a personal OpenAI key requires the Pro plan or higher.",
                "minimumPlan": entitlement.byokMinimumPlan,
                "upgradeUrl": "/pico/pricing",
            },
        )
    return entitlement


async def _get_setting(db: AsyncSession, *, user_id, key: str) -> UserSetting | None:
    result = await db.execute(
        select(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == key)
    )
    return result.scalar_one_or_none()


def _status_message(
    *,
    status: str,
    masked_key: str | None = None,
    byok_access: bool,
) -> str:
    if status == "connected":
        return f"Your validated OpenAI key {masked_key or 'stored in MUTX'} is active."
    if status == "platform":
        if byok_access:
            return (
                "Platform OpenAI credentials are configured but not validated by this status "
                "check. You can connect a validated personal key instead."
            )
        return "Platform OpenAI credentials are configured but not validated by this status check."
    if status == "error":
        return "A saved OpenAI key has no usable validation proof. Reconnect it before using live Tutor."
    if byok_access:
        return "No model provider is available. Connect a validated OpenAI key to use live Tutor."
    return "No platform model provider is available. Academy guidance remains available."


async def validate_openai_api_key(api_key: str) -> None:
    normalized_key = _normalize_api_key(api_key)
    try:
        client = AsyncOpenAI(api_key=normalized_key, timeout=5.0, max_retries=0)
        await client.chat.completions.create(
            model=_configured_openai_model(),
            messages=[{"role": "user", "content": "Reply with OK."}],
            max_completion_tokens=1,
        )
    except Exception as exc:
        if isinstance(exc, PicoTutorOpenAIConnectionError):
            raise
        raise PicoTutorOpenAIConnectionError(
            "Failed to validate the OpenAI key and configured Tutor model. "
            "Check the key and try again."
        ) from exc


def _build_user_setting_upsert(
    dialect_name: str,
    *,
    user_id: Any,
    key: str,
    value: dict[str, str],
):
    insert = postgresql_insert if dialect_name == "postgresql" else sqlite_insert
    statement = insert(UserSetting).values(user_id=user_id, key=key, value=value)
    return statement.on_conflict_do_update(
        index_elements=[UserSetting.user_id, UserSetting.key],
        set_={"value": value, "updated_at": datetime.now(timezone.utc)},
    )


async def _upsert_user_setting(
    db: AsyncSession,
    *,
    user_id: Any,
    key: str,
    value: dict[str, str],
) -> None:
    """Atomically create or replace a user setting on supported databases."""
    dialect_name = db.get_bind().dialect.name
    if dialect_name in {"postgresql", "sqlite"}:
        statement = _build_user_setting_upsert(
            dialect_name,
            user_id=user_id,
            key=key,
            value=value,
        )
        await db.execute(statement)
        await db.commit()
        return

    result = await db.execute(
        update(UserSetting)
        .where(UserSetting.user_id == user_id, UserSetting.key == key)
        .values(value=value, updated_at=datetime.now(timezone.utc))
    )
    if result.rowcount:
        await db.commit()
        return

    db.add(UserSetting(user_id=user_id, key=key, value=value))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        await db.execute(
            update(UserSetting)
            .where(UserSetting.user_id == user_id, UserSetting.key == key)
            .values(value=value, updated_at=datetime.now(timezone.utc))
        )
        await db.commit()


async def get_pico_tutor_openai_connection_status(
    db: AsyncSession,
    *,
    user: User,
) -> PicoTutorOpenAIConnectionStatus:
    entitlement = require_pico_tutor_access(user)
    setting = await _get_setting(db, user_id=user.id, key=PICO_TUTOR_OPENAI_KEY)
    payload = setting.value if setting and isinstance(setting.value, dict) else {}
    encrypted_key = payload.get("api_key_encrypted") if isinstance(payload, dict) else None
    decrypted_key = (
        decrypt_secret_value(encrypted_key)
        if isinstance(encrypted_key, str) and encrypted_key
        else None
    )
    masked_key = payload.get("masked_key") if isinstance(payload, dict) else None
    connected_at = payload.get("connected_at") if isinstance(payload, dict) else None
    validated_at = payload.get("validated_at") if isinstance(payload, dict) else None
    validated_model = payload.get("validated_model") if isinstance(payload, dict) else None
    platform_key_present = _platform_api_key() is not None
    model_name = _configured_openai_model()
    checked_at = _utcnow_iso()

    if (
        entitlement.byokAccess
        and encrypted_key
        and (not decrypted_key or not validated_at or validated_model != model_name)
    ):
        return PicoTutorOpenAIConnectionStatus(
            status="error",
            source="none",
            connected=False,
            model=model_name,
            maskedKey=masked_key if isinstance(masked_key, str) else None,
            connectedAt=connected_at if isinstance(connected_at, str) else None,
            validatedAt=validated_at if isinstance(validated_at, str) else None,
            message=_status_message(
                status="error",
                masked_key=masked_key if isinstance(masked_key, str) else None,
                byok_access=entitlement.byokAccess,
            ),
            providerAvailable=False,
            canConnect=entitlement.byokAccess,
            entitlement=entitlement,
        )

    if (
        entitlement.byokAccess
        and decrypted_key
        and isinstance(validated_at, str)
        and validated_model == model_name
    ):
        return PicoTutorOpenAIConnectionStatus(
            status="connected",
            source="user",
            connected=True,
            model=model_name,
            maskedKey=masked_key if isinstance(masked_key, str) else _mask_api_key(decrypted_key),
            connectedAt=connected_at if isinstance(connected_at, str) else None,
            validatedAt=validated_at if isinstance(validated_at, str) else None,
            message=_status_message(
                status="connected",
                masked_key=(
                    masked_key if isinstance(masked_key, str) else _mask_api_key(decrypted_key)
                ),
                byok_access=entitlement.byokAccess,
            ),
            providerAvailable=True,
            canConnect=entitlement.byokAccess,
            entitlement=entitlement,
            proof=PicoTutorProviderProof(
                kind="validated_user_key",
                checkedAt=checked_at,
                validatedAt=validated_at,
            ),
        )

    if platform_key_present:
        return PicoTutorOpenAIConnectionStatus(
            status="platform",
            source="platform",
            connected=False,
            model=model_name,
            message=_status_message(status="platform", byok_access=entitlement.byokAccess),
            providerAvailable=False,
            canConnect=entitlement.byokAccess,
            entitlement=entitlement,
            proof=PicoTutorProviderProof(
                kind="configured_platform_key",
                checkedAt=checked_at,
            ),
        )

    return PicoTutorOpenAIConnectionStatus(
        status="disconnected",
        source="none",
        connected=False,
        model=model_name,
        message=_status_message(status="disconnected", byok_access=entitlement.byokAccess),
        providerAvailable=False,
        canConnect=entitlement.byokAccess,
        entitlement=entitlement,
    )


async def connect_pico_tutor_openai(
    db: AsyncSession,
    *,
    user: User,
    api_key: str,
) -> PicoTutorOpenAIConnectionStatus:
    require_pico_tutor_byok_access(user)
    normalized_key = _normalize_api_key(api_key)
    await validate_openai_api_key(normalized_key)

    now = _utcnow_iso()
    payload = {
        "api_key_encrypted": encrypt_secret_value(normalized_key),
        "masked_key": _mask_api_key(normalized_key),
        "connected_at": now,
        "validated_at": now,
        "validated_model": _configured_openai_model(),
    }
    await _upsert_user_setting(
        db,
        user_id=user.id,
        key=PICO_TUTOR_OPENAI_KEY,
        value=payload,
    )
    return await get_pico_tutor_openai_connection_status(db, user=user)


async def disconnect_pico_tutor_openai(
    db: AsyncSession,
    *,
    user: User,
) -> PicoTutorOpenAIConnectionStatus:
    require_pico_tutor_byok_access(user)
    await db.execute(
        delete(UserSetting).where(
            UserSetting.user_id == user.id,
            UserSetting.key == PICO_TUTOR_OPENAI_KEY,
        )
    )
    await db.commit()
    return await get_pico_tutor_openai_connection_status(db, user=user)


async def resolve_pico_tutor_api_key(
    db: AsyncSession | None,
    *,
    user: User | None,
) -> tuple[str | None, str]:
    entitlement = get_pico_tutor_entitlement(user) if user is not None else None
    if db is not None and user is not None and entitlement and entitlement.byokAccess:
        setting = await _get_setting(db, user_id=user.id, key=PICO_TUTOR_OPENAI_KEY)
        payload = setting.value if setting and isinstance(setting.value, dict) else {}
        encrypted_key = payload.get("api_key_encrypted") if isinstance(payload, dict) else None
        validated_at = payload.get("validated_at") if isinstance(payload, dict) else None
        validated_model = payload.get("validated_model") if isinstance(payload, dict) else None
        if (
            isinstance(encrypted_key, str)
            and encrypted_key
            and isinstance(validated_at, str)
            and validated_model == _configured_openai_model()
        ):
            decrypted = decrypt_secret_value(encrypted_key)
            if decrypted:
                return decrypted, "user"
            logger.warning("Failed to decrypt Pico tutor OpenAI key for user %s", user.id)

    platform_key = _platform_api_key()
    if platform_key:
        return platform_key, "platform"

    return None, "none"
