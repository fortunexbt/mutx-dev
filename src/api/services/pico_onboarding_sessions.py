"""Durable, user-scoped persistence for Pico onboarding coach sessions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import User, UserSetting
from src.api.models.pico_onboarding import (
    CoachMessage,
    OnboardingState,
    PicoChatResponse,
    PicoOnboardingSessionResponse,
)

PICO_ONBOARDING_SESSION_PREFIX = "pico.onboarding.session."
PICO_ONBOARDING_CONTROL_KEY = "pico.onboarding.control"
PICO_ONBOARDING_REQUEST_PREFIX = "pico.onboarding.request."
PICO_ONBOARDING_SESSION_TTL = timedelta(days=30)

_GENERATION_LEASE_TTL = timedelta(minutes=10)
_GENERATION_HEARTBEAT_SECONDS = 60.0
_GENERATION_WAIT_SECONDS = 30.0
_GENERATION_POLL_SECONDS = 0.025
_MAX_DURABLE_SESSIONS = 10
_MAX_HISTORY_MESSAGES = 24
_MAX_HISTORY_CONTENT_CHARS = 16_000
_MAX_REPLY_CHARS = 16_000
_MAX_PACKAGE_GENERATIONS = 20
_MAX_IDEMPOTENCY_RECORDS = 50
_MAX_SESSION_SETTING_BYTES = 64 * 1024
_MAX_IDEMPOTENCY_SETTING_BYTES = 32 * 1024

_sqlite_user_locks: dict[str, asyncio.Lock] = {}
logger = logging.getLogger(__name__)


class PicoOnboardingSessionNotFoundError(Exception):
    """The requested session does not exist for the authenticated user."""


class PicoOnboardingSessionExpiredError(Exception):
    """The requested session exists but is no longer active."""


class PicoOnboardingSessionAbandonedError(Exception):
    """The requested session predates the user's latest reset."""


class PicoOnboardingIdempotencyConflictError(Exception):
    """A request ID was reused with different canonical request content."""


class PicoOnboardingGenerationBusyError(Exception):
    """Another generation did not finish within the bounded wait window."""


class PicoOnboardingSessionChangedError(Exception):
    """The durable session changed while a package snapshot was being built."""


class _LegacyCachedChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    response: dict[str, Any]


class _ActiveGeneration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_token: str
    request_id: str | None = None
    content_sha256: str
    lease_expires_at: datetime


class _OnboardingControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    generation: int = 0


class _IdempotencyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    request_id: str
    content_sha256: str
    session_id: str
    generation: int
    status: Literal["pending", "completed"]
    claim_token: str
    lease_expires_at: datetime
    response: dict[str, Any] | None = None


class PicoOnboardingSessionRecord(BaseModel):
    """Validated storage representation kept inside ``UserSetting.value``."""

    model_config = ConfigDict(extra="forbid")

    version: int = 2
    session_id: str
    generation: int = 0
    revision: int = 0
    history: list[CoachMessage] = Field(default_factory=list)
    compacted_messages: int = 0
    onboarding_state: OnboardingState = Field(default_factory=OnboardingState)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    abandoned_at: datetime | None = None
    active_generation: _ActiveGeneration | None = None
    cached_responses: list[_LegacyCachedChatResponse] = Field(default_factory=list)
    package_generations: list[dict[str, Any]] = Field(default_factory=list)

    def visible_history(self) -> list[CoachMessage]:
        if self.compacted_messages <= 0:
            return list(self.history)
        return [
            CoachMessage(
                role="assistant",
                content=(
                    f"{self.compacted_messages} earlier onboarding messages were compacted "
                    "to keep this session durable. The structured setup state was preserved "
                    "and remains the source for package generation."
                ),
                onboarding_state=self.onboarding_state,
            ),
            *self.history,
        ]

    def as_response(self) -> PicoOnboardingSessionResponse:
        return PicoOnboardingSessionResponse(
            session_id=self.session_id,
            history=self.visible_history(),
            onboarding_state=self.onboarding_state,
            ready_for_package=self.onboarding_state.ready,
            created_at=self.created_at,
            updated_at=self.updated_at,
            expires_at=self.expires_at,
        )


@dataclass(frozen=True)
class PicoChatTurnClaim:
    session_id: str
    generation: int
    claim_token: str
    request_id: str | None
    content_sha256: str
    history: list[CoachMessage]


@dataclass(frozen=True)
class _WaitForGeneration:
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _setting_key(session_id: str) -> str:
    return f"{PICO_ONBOARDING_SESSION_PREFIX}{session_id}"


def _request_setting_key(request_id: str) -> str:
    digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    return f"{PICO_ONBOARDING_REQUEST_PREFIX}{digest}"


def _canonical_request_sha256(*, message: str, session_id: str) -> str:
    canonical = json.dumps(
        {"message": message, "session_id": session_id},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _serialized_size(value: dict[str, Any]) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _parse_record(setting: UserSetting) -> PicoOnboardingSessionRecord:
    try:
        return PicoOnboardingSessionRecord.model_validate(setting.value)
    except ValidationError as exc:
        raise RuntimeError("Stored Pico onboarding session is invalid") from exc


def _parse_control(setting: UserSetting | None) -> _OnboardingControl:
    if setting is None:
        return _OnboardingControl()
    try:
        return _OnboardingControl.model_validate(setting.value)
    except ValidationError as exc:
        raise RuntimeError("Stored Pico onboarding control record is invalid") from exc


def _parse_idempotency(setting: UserSetting) -> _IdempotencyRecord:
    try:
        return _IdempotencyRecord.model_validate(setting.value)
    except ValidationError as exc:
        raise RuntimeError("Stored Pico onboarding idempotency record is invalid") from exc


def _is_expired(record: PicoOnboardingSessionRecord, *, now: datetime | None = None) -> bool:
    return _as_utc(record.expires_at) <= (now or _utcnow())


def _is_abandoned(record: PicoOnboardingSessionRecord, *, generation: int) -> bool:
    return record.abandoned_at is not None or record.generation != generation


def _lease_is_active(active: _ActiveGeneration, *, now: datetime) -> bool:
    return _as_utc(active.lease_expires_at) > now


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker = "\n\n[Content truncated to keep the durable session within its storage limit.]"
    return f"{value[: limit - len(marker)]}{marker}"


def _normalize_state(
    state: OnboardingState,
    *,
    exclude_unset: bool = False,
) -> OnboardingState:
    allowed = {
        key: value
        for key, value in state.model_dump(exclude_unset=exclude_unset).items()
        if key in OnboardingState.model_fields and key != "ready"
    }
    channels = allowed.get("channels")
    if isinstance(channels, list):
        allowed["channels"] = list(dict.fromkeys(channels))[:16]
    return OnboardingState.model_validate(allowed)


def _onboarding_state_sha256(state: OnboardingState) -> str:
    normalized_state = _normalize_state(state)
    state_json = json.dumps(
        normalized_state.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(state_json.encode("utf-8")).hexdigest()


def _bound_chat_response(response: PicoChatResponse) -> PicoChatResponse:
    state = (
        _normalize_state(response.onboarding_state, exclude_unset=True)
        if response.onboarding_state
        else None
    )
    return response.model_copy(
        update={
            "reply": _truncate_text(response.reply, _MAX_REPLY_CHARS),
            "onboarding_state": state,
        }
    )


def _compact_record(record: PicoOnboardingSessionRecord) -> None:
    record.version = 2
    record.cached_responses = []
    record.onboarding_state = _normalize_state(record.onboarding_state)
    record.package_generations = record.package_generations[-_MAX_PACKAGE_GENERATIONS:]
    record.history = [
        message.model_copy(
            update={
                "content": _truncate_text(message.content, _MAX_HISTORY_CONTENT_CHARS),
                "onboarding_state": (
                    _normalize_state(message.onboarding_state)
                    if message.onboarding_state is not None
                    else None
                ),
            }
        )
        for message in record.history
    ]

    while len(record.history) > _MAX_HISTORY_MESSAGES:
        removed = min(2, len(record.history))
        record.history = record.history[removed:]
        record.compacted_messages += removed

    value = record.model_dump(mode="json")
    while _serialized_size(value) > _MAX_SESSION_SETTING_BYTES and len(record.history) > 2:
        removed = min(2, len(record.history))
        record.history = record.history[removed:]
        record.compacted_messages += removed
        value = record.model_dump(mode="json")

    if _serialized_size(value) > _MAX_SESSION_SETTING_BYTES:
        raise RuntimeError("Pico onboarding session exceeded its durable storage limit")


def _store_record(setting: UserSetting, record: PicoOnboardingSessionRecord) -> None:
    _compact_record(record)
    setting.value = record.model_dump(mode="json")


def _store_idempotency(setting: UserSetting, record: _IdempotencyRecord) -> None:
    value = record.model_dump(mode="json")
    if _serialized_size(value) > _MAX_IDEMPOTENCY_SETTING_BYTES:
        raise RuntimeError("Pico onboarding idempotency result exceeded its storage limit")
    setting.value = value


def _is_sqlite(db: AsyncSession) -> bool:
    bind = db.get_bind()
    return bind.dialect.name == "sqlite"


@asynccontextmanager
async def _lock_user(db: AsyncSession, *, user: User) -> AsyncIterator[None]:
    """Use a PostgreSQL row lock and emulate it with a process lock for SQLite tests."""
    local_lock: asyncio.Lock | None = None
    if _is_sqlite(db):
        local_lock = _sqlite_user_locks.setdefault(str(user.id), asyncio.Lock())
        await local_lock.acquire()

    try:
        result = await db.execute(select(User.id).where(User.id == user.id).with_for_update())
        if result.scalar_one_or_none() is None:
            raise PicoOnboardingSessionNotFoundError
        yield
    finally:
        if local_lock is not None:
            local_lock.release()


async def _get_control_setting(
    db: AsyncSession,
    *,
    user: User,
    for_update: bool = False,
) -> UserSetting | None:
    statement = select(UserSetting).where(
        UserSetting.user_id == user.id,
        UserSetting.key == PICO_ONBOARDING_CONTROL_KEY,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def _ensure_control_setting(
    db: AsyncSession,
    *,
    user: User,
) -> tuple[UserSetting, _OnboardingControl]:
    setting = await _get_control_setting(db, user=user, for_update=True)
    if setting is None:
        control = _OnboardingControl()
        setting = UserSetting(
            user_id=user.id,
            key=PICO_ONBOARDING_CONTROL_KEY,
            value=control.model_dump(mode="json"),
        )
        db.add(setting)
        await db.flush()
        return setting, control
    return setting, _parse_control(setting)


async def _current_generation(db: AsyncSession, *, user: User) -> int:
    setting = await _get_control_setting(db, user=user)
    return _parse_control(setting).generation


async def _get_setting(
    db: AsyncSession,
    *,
    user: User,
    session_id: str,
    for_update: bool = False,
) -> UserSetting | None:
    statement = select(UserSetting).where(
        UserSetting.user_id == user.id,
        UserSetting.key == _setting_key(session_id),
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def _get_request_setting(
    db: AsyncSession,
    *,
    user: User,
    request_id: str,
    for_update: bool = False,
) -> UserSetting | None:
    statement = select(UserSetting).where(
        UserSetting.user_id == user.id,
        UserSetting.key == _request_setting_key(request_id),
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def _session_settings(
    db: AsyncSession,
    *,
    user: User,
    for_update: bool = False,
) -> list[UserSetting]:
    statement = (
        select(UserSetting)
        .where(
            UserSetting.user_id == user.id,
            UserSetting.key.like(f"{PICO_ONBOARDING_SESSION_PREFIX}%"),
        )
        .order_by(UserSetting.updated_at.desc())
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return list(result.scalars())


async def _prune_idempotency_settings(
    db: AsyncSession,
    *,
    user: User,
    generation: int,
    now: datetime,
) -> None:
    result = await db.execute(
        select(UserSetting)
        .where(
            UserSetting.user_id == user.id,
            UserSetting.key.like(f"{PICO_ONBOARDING_REQUEST_PREFIX}%"),
        )
        .order_by(UserSetting.updated_at.desc())
    )
    retained_inactive = 0
    for setting in result.scalars():
        record = _parse_idempotency(setting)
        is_active = (
            record.status == "pending"
            and record.generation == generation
            and _as_utc(record.lease_expires_at) > now
        )
        if is_active:
            continue
        retained_inactive += 1
        if retained_inactive > _MAX_IDEMPOTENCY_RECORDS:
            await db.delete(setting)


async def _prune_session_settings(
    db: AsyncSession,
    *,
    user: User,
    preserve_session_id: str,
    now: datetime,
) -> None:
    settings = await _session_settings(db, user=user, for_update=True)
    kept = 0
    for setting in settings:
        record = _parse_record(setting)
        if record.session_id == preserve_session_id:
            kept += 1
            continue
        active = record.active_generation
        if active is not None and _lease_is_active(active, now=now):
            kept += 1
            continue
        if kept < _MAX_DURABLE_SESSIONS:
            kept += 1
            continue
        await db.delete(setting)


async def get_onboarding_session(
    db: AsyncSession,
    *,
    user: User,
    session_id: str,
    allow_expired: bool = False,
) -> PicoOnboardingSessionRecord:
    """Load one current-generation session without exposing another user's IDs."""
    generation = await _current_generation(db, user=user)
    setting = await _get_setting(db, user=user, session_id=session_id)
    if setting is None:
        raise PicoOnboardingSessionNotFoundError
    record = _parse_record(setting)
    if _is_abandoned(record, generation=generation):
        raise PicoOnboardingSessionAbandonedError
    if not allow_expired and _is_expired(record):
        raise PicoOnboardingSessionExpiredError
    return record


async def get_latest_onboarding_session(
    db: AsyncSession,
    *,
    user: User,
) -> PicoOnboardingSessionRecord | None:
    """Return the latest active session in the user's current reset generation."""
    generation = await _current_generation(db, user=user)
    for setting in await _session_settings(db, user=user):
        record = _parse_record(setting)
        if _is_abandoned(record, generation=generation):
            continue
        if _is_expired(record):
            raise PicoOnboardingSessionExpiredError
        return record
    return None


async def abandon_onboarding_session(
    db: AsyncSession,
    *,
    user: User,
    session_id: str | None = None,
) -> PicoOnboardingSessionRecord | None:
    """Advance the user's durable reset generation and invalidate every older session."""
    try:
        async with _lock_user(db, user=user):
            requested_setting = None
            if session_id is not None:
                requested_setting = await _get_setting(
                    db,
                    user=user,
                    session_id=session_id,
                    for_update=True,
                )
                if requested_setting is None:
                    raise PicoOnboardingSessionNotFoundError

            control_setting, control = await _ensure_control_setting(db, user=user)
            control.generation += 1
            control_setting.value = control.model_dump(mode="json")

            now = _utcnow()
            requested_record = None
            for setting in await _session_settings(db, user=user, for_update=True):
                record = _parse_record(setting)
                if setting is requested_setting:
                    requested_record = record
                record.abandoned_at = now
                record.active_generation = None
                record.updated_at = now
                _store_record(setting, record)

            await _prune_idempotency_settings(
                db,
                user=user,
                generation=control.generation,
                now=now,
            )
            await db.commit()
            return requested_record
    except BaseException:
        await db.rollback()
        raise


def new_onboarding_session(
    *, generation: int = 0, session_id: str | None = None
) -> PicoOnboardingSessionRecord:
    now = _utcnow()
    return PicoOnboardingSessionRecord(
        session_id=session_id or str(uuid.uuid4()),
        generation=generation,
        created_at=now,
        updated_at=now,
        expires_at=now + PICO_ONBOARDING_SESSION_TTL,
    )


def _merge_onboarding_state(
    current: OnboardingState,
    incoming: OnboardingState | None,
) -> OnboardingState:
    current = _normalize_state(current)
    if incoming is None:
        return current

    allowed_fields = set(OnboardingState.model_fields) - {"ready"}
    updates = {
        key: value
        for key, value in incoming.model_dump(exclude_unset=True).items()
        if key in allowed_fields
    }
    return _normalize_state(OnboardingState.model_validate({**current.model_dump(), **updates}))


async def _try_prepare_chat_turn(
    db: AsyncSession,
    *,
    user: User,
    message: str,
    session_id: str | None,
    request_id: str | None,
) -> PicoChatTurnClaim | PicoChatResponse | _WaitForGeneration:
    try:
        async with _lock_user(db, user=user):
            _, control = await _ensure_control_setting(db, user=user)
            now = _utcnow()

            request_setting = None
            idempotency = None
            cached_response = None
            resolved_session_id = session_id
            content_sha256 = None

            if request_id is not None:
                request_setting = await _get_request_setting(
                    db,
                    user=user,
                    request_id=request_id,
                    for_update=True,
                )
                if request_setting is not None:
                    idempotency = _parse_idempotency(request_setting)
                    if idempotency.request_id != request_id:
                        raise PicoOnboardingIdempotencyConflictError
                    resolved_session_id = resolved_session_id or idempotency.session_id
                    content_sha256 = _canonical_request_sha256(
                        message=message,
                        session_id=resolved_session_id,
                    )
                    if (
                        idempotency.session_id != resolved_session_id
                        or idempotency.content_sha256 != content_sha256
                    ):
                        raise PicoOnboardingIdempotencyConflictError
                    if idempotency.generation != control.generation:
                        raise PicoOnboardingSessionAbandonedError
                    if idempotency.status == "completed":
                        if idempotency.response is None:
                            raise RuntimeError("Completed Pico idempotency record has no response")
                        cached_response = PicoChatResponse.model_validate(idempotency.response)

            if resolved_session_id is None:
                resolved_session_id = str(uuid.uuid4())
            if content_sha256 is None:
                content_sha256 = _canonical_request_sha256(
                    message=message,
                    session_id=resolved_session_id,
                )

            session_setting = await _get_setting(
                db,
                user=user,
                session_id=resolved_session_id,
                for_update=True,
            )
            if session_setting is None:
                if session_id is not None or idempotency is not None:
                    raise PicoOnboardingSessionNotFoundError
                record = new_onboarding_session(
                    generation=control.generation,
                    session_id=resolved_session_id,
                )
                session_setting = UserSetting(
                    user_id=user.id,
                    key=_setting_key(resolved_session_id),
                    value={},
                )
                db.add(session_setting)
            else:
                record = _parse_record(session_setting)
                if _is_abandoned(record, generation=control.generation):
                    raise PicoOnboardingSessionAbandonedError
                if _is_expired(record, now=now):
                    raise PicoOnboardingSessionExpiredError

            if cached_response is not None:
                await db.commit()
                return cached_response

            active = record.active_generation
            if active is not None and _lease_is_active(active, now=now):
                await db.commit()
                return _WaitForGeneration()

            claim_token = uuid.uuid4().hex
            lease_expires_at = now + _GENERATION_LEASE_TTL
            record.active_generation = _ActiveGeneration(
                claim_token=claim_token,
                request_id=request_id,
                content_sha256=content_sha256,
                lease_expires_at=lease_expires_at,
            )
            record.updated_at = now
            _store_record(session_setting, record)

            if request_id is not None:
                idempotency = _IdempotencyRecord(
                    request_id=request_id,
                    content_sha256=content_sha256,
                    session_id=resolved_session_id,
                    generation=control.generation,
                    status="pending",
                    claim_token=claim_token,
                    lease_expires_at=lease_expires_at,
                )
                if request_setting is None:
                    request_setting = UserSetting(
                        user_id=user.id,
                        key=_request_setting_key(request_id),
                        value={},
                    )
                    db.add(request_setting)
                _store_idempotency(request_setting, idempotency)

            await db.flush()
            await _prune_idempotency_settings(
                db,
                user=user,
                generation=control.generation,
                now=now,
            )
            await _prune_session_settings(
                db,
                user=user,
                preserve_session_id=resolved_session_id,
                now=now,
            )
            await db.commit()
            return PicoChatTurnClaim(
                session_id=resolved_session_id,
                generation=control.generation,
                claim_token=claim_token,
                request_id=request_id,
                content_sha256=content_sha256,
                history=record.visible_history(),
            )
    except BaseException:
        await db.rollback()
        raise


async def prepare_chat_turn(
    db: AsyncSession,
    *,
    user: User,
    message: str,
    session_id: str | None,
    request_id: str | None,
) -> PicoChatTurnClaim | PicoChatResponse:
    """Reserve a serialized durable turn, waiting for an earlier claimant if needed."""
    deadline = time.monotonic() + _GENERATION_WAIT_SECONDS
    while True:
        outcome = await _try_prepare_chat_turn(
            db,
            user=user,
            message=message,
            session_id=session_id,
            request_id=request_id,
        )
        if not isinstance(outcome, _WaitForGeneration):
            return outcome
        if time.monotonic() >= deadline:
            raise PicoOnboardingGenerationBusyError
        await asyncio.sleep(_GENERATION_POLL_SECONDS)


async def append_chat_turn(
    db: AsyncSession,
    *,
    user: User,
    record: PicoOnboardingSessionRecord,
    user_message: str,
    response: PicoChatResponse,
    request_id: str | None,
) -> PicoChatResponse:
    """Compatibility helper for callers that construct an empty session record directly."""
    try:
        async with _lock_user(db, user=user):
            _, control = await _ensure_control_setting(db, user=user)
            setting = await _get_setting(
                db,
                user=user,
                session_id=record.session_id,
                for_update=True,
            )
            if setting is None:
                record.generation = control.generation
                setting = UserSetting(
                    user_id=user.id,
                    key=_setting_key(record.session_id),
                    value={},
                )
                db.add(setting)
                _store_record(setting, record)
            await db.commit()
    except BaseException:
        await db.rollback()
        raise

    prepared = await prepare_chat_turn(
        db,
        user=user,
        message=user_message,
        session_id=record.session_id,
        request_id=request_id,
    )
    if isinstance(prepared, PicoChatResponse):
        return prepared
    return await complete_chat_turn(
        db,
        user=user,
        claim=prepared,
        user_message=user_message,
        response=response,
    )


async def maintain_chat_turn_claim(
    db: AsyncSession,
    *,
    user: User,
    claim: PicoChatTurnClaim,
    stop: asyncio.Event,
) -> None:
    """Extend a live durable lease while a model call runs without a database lock."""
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=_GENERATION_HEARTBEAT_SECONDS)
            return
        except TimeoutError:
            pass

        try:
            async with _lock_user(db, user=user):
                _, control = await _ensure_control_setting(db, user=user)
                if control.generation != claim.generation:
                    await db.commit()
                    return

                setting = await _get_setting(
                    db,
                    user=user,
                    session_id=claim.session_id,
                    for_update=True,
                )
                if setting is None:
                    await db.commit()
                    return
                record = _parse_record(setting)
                active = record.active_generation
                if active is None or active.claim_token != claim.claim_token:
                    await db.commit()
                    return

                lease_expires_at = _utcnow() + _GENERATION_LEASE_TTL
                active.lease_expires_at = lease_expires_at
                record.active_generation = active
                _store_record(setting, record)

                if claim.request_id is not None:
                    request_setting = await _get_request_setting(
                        db,
                        user=user,
                        request_id=claim.request_id,
                        for_update=True,
                    )
                    if request_setting is None:
                        await db.rollback()
                        return
                    idempotency = _parse_idempotency(request_setting)
                    if (
                        idempotency.status != "pending"
                        or idempotency.claim_token != claim.claim_token
                    ):
                        await db.commit()
                        return
                    idempotency.lease_expires_at = lease_expires_at
                    _store_idempotency(request_setting, idempotency)

                await db.commit()
        except BaseException as exc:
            await db.rollback()
            if isinstance(exc, asyncio.CancelledError):
                raise
            logger.warning(
                "Unable to renew Pico onboarding generation lease for session %s: %s",
                claim.session_id,
                exc,
            )
            return


async def complete_chat_turn(
    db: AsyncSession,
    *,
    user: User,
    claim: PicoChatTurnClaim,
    user_message: str,
    response: PicoChatResponse,
) -> PicoChatResponse:
    """Commit a claimed turn only if its session and user epoch are still current."""
    try:
        async with _lock_user(db, user=user):
            _, control = await _ensure_control_setting(db, user=user)
            if control.generation != claim.generation:
                raise PicoOnboardingSessionAbandonedError

            setting = await _get_setting(
                db,
                user=user,
                session_id=claim.session_id,
                for_update=True,
            )
            if setting is None:
                raise PicoOnboardingSessionNotFoundError
            record = _parse_record(setting)
            if _is_abandoned(record, generation=control.generation):
                raise PicoOnboardingSessionAbandonedError
            if _is_expired(record):
                raise PicoOnboardingSessionExpiredError

            active = record.active_generation
            if active is None or active.claim_token != claim.claim_token:
                if claim.request_id is not None:
                    request_setting = await _get_request_setting(
                        db,
                        user=user,
                        request_id=claim.request_id,
                        for_update=True,
                    )
                    if request_setting is not None:
                        idempotency = _parse_idempotency(request_setting)
                        if idempotency.status == "completed" and idempotency.response is not None:
                            cached = PicoChatResponse.model_validate(idempotency.response)
                            await db.commit()
                            return cached
                raise PicoOnboardingGenerationBusyError
            if active.content_sha256 != claim.content_sha256:
                raise PicoOnboardingIdempotencyConflictError

            bounded_response = _bound_chat_response(response)
            merged_state = _merge_onboarding_state(
                record.onboarding_state,
                bounded_response.onboarding_state,
            )
            now = _utcnow()
            record.onboarding_state = merged_state
            record.history.extend(
                [
                    CoachMessage(role="user", content=user_message),
                    CoachMessage(
                        role="assistant",
                        content=bounded_response.reply,
                        onboarding_state=merged_state,
                    ),
                ]
            )
            record.revision += 1
            record.active_generation = None
            record.updated_at = now
            record.expires_at = now + PICO_ONBOARDING_SESSION_TTL

            persisted_response = bounded_response.model_copy(
                update={
                    "session_id": record.session_id,
                    "session_persisted": True,
                    "onboarding_state": merged_state,
                    "ready_for_package": merged_state.ready,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    "expires_at": record.expires_at,
                }
            )
            _store_record(setting, record)

            if claim.request_id is not None:
                request_setting = await _get_request_setting(
                    db,
                    user=user,
                    request_id=claim.request_id,
                    for_update=True,
                )
                if request_setting is None:
                    raise RuntimeError("Pico idempotency reservation disappeared before completion")
                idempotency = _parse_idempotency(request_setting)
                if (
                    idempotency.content_sha256 != claim.content_sha256
                    or idempotency.claim_token != claim.claim_token
                    or idempotency.generation != claim.generation
                ):
                    raise PicoOnboardingIdempotencyConflictError
                idempotency.status = "completed"
                idempotency.response = persisted_response.model_dump(mode="json")
                _store_idempotency(request_setting, idempotency)

            await _prune_idempotency_settings(
                db,
                user=user,
                generation=control.generation,
                now=now,
            )
            await db.commit()
            return persisted_response
    except BaseException:
        await db.rollback()
        raise


async def abort_chat_turn(
    db: AsyncSession,
    *,
    user: User,
    claim: PicoChatTurnClaim,
) -> None:
    """Release a live claim after local generation failure without crossing a reset barrier."""
    try:
        async with _lock_user(db, user=user):
            _, control = await _ensure_control_setting(db, user=user)
            if control.generation != claim.generation:
                await db.commit()
                return

            setting = await _get_setting(
                db,
                user=user,
                session_id=claim.session_id,
                for_update=True,
            )
            if setting is not None:
                record = _parse_record(setting)
                active = record.active_generation
                if active is not None and active.claim_token == claim.claim_token:
                    record.active_generation = None
                    _store_record(setting, record)

            if claim.request_id is not None:
                request_setting = await _get_request_setting(
                    db,
                    user=user,
                    request_id=claim.request_id,
                    for_update=True,
                )
                if request_setting is not None:
                    idempotency = _parse_idempotency(request_setting)
                    if (
                        idempotency.status == "pending"
                        and idempotency.claim_token == claim.claim_token
                    ):
                        await db.delete(request_setting)

            await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def record_package_generation(
    db: AsyncSession,
    *,
    user: User,
    session_id: str,
    filename: str,
    state: OnboardingState,
    expected_revision: int,
) -> str:
    """Record a package only when its captured session snapshot is still authoritative."""
    try:
        async with _lock_user(db, user=user):
            _, control = await _ensure_control_setting(db, user=user)
            setting = await _get_setting(
                db,
                user=user,
                session_id=session_id,
                for_update=True,
            )
            if setting is None:
                raise PicoOnboardingSessionNotFoundError
            record = _parse_record(setting)
            if _is_abandoned(record, generation=control.generation):
                raise PicoOnboardingSessionAbandonedError
            if _is_expired(record):
                raise PicoOnboardingSessionExpiredError

            state_sha256 = _onboarding_state_sha256(state)
            current_state_sha256 = _onboarding_state_sha256(record.onboarding_state)
            active_generation = record.active_generation
            if (
                record.revision != expected_revision
                or current_state_sha256 != state_sha256
                or (
                    active_generation is not None
                    and _lease_is_active(active_generation, now=_utcnow())
                )
            ):
                raise PicoOnboardingSessionChangedError

            record.package_generations.append(
                {
                    "filename": filename[:120],
                    "generated_at": _utcnow().isoformat(),
                    "state_sha256": state_sha256,
                }
            )
            record.updated_at = _utcnow()
            _store_record(setting, record)
            await db.commit()
            return state_sha256
    except BaseException:
        await db.rollback()
        raise
