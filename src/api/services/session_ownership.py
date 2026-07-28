"""Fail-closed ownership resolution for externally hosted assistant sessions."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Any
import uuid

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.models import Agent, User, UserSetting

SESSION_OWNERSHIP_PREFIX = "sessions.ownership.v1."
_BINDING_VERSION = 1
_MAX_SESSION_KEY_LENGTH = 2048


@dataclass(frozen=True)
class OwnedSession:
    """A persisted, authenticated principal-to-provider-session binding."""

    canonical_key: str
    source: str
    agent_id: uuid.UUID


def _clean_session_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_SESSION_KEY_LENGTH:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in cleaned):
        return None
    return cleaned


def validate_session_key(value: str) -> str:
    """Validate an externally supplied key without decoding or normalizing aliases."""
    cleaned = _clean_session_key(value)
    if cleaned is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return cleaned


def _exact_agent_uuid(value: Any) -> uuid.UUID | None:
    """Accept only the canonical textual form of an immutable Agent UUID."""
    cleaned = _clean_session_key(value)
    if cleaned is None:
        return None
    try:
        parsed = uuid.UUID(cleaned)
    except (ValueError, AttributeError):
        return None
    if cleaned.casefold() != str(parsed):
        return None
    return parsed


def _structured_session_agent_id(value: Any) -> uuid.UUID | None:
    """Extract an immutable UUID from a documented ``agent:<uuid>:...`` key."""
    cleaned = _clean_session_key(value)
    if cleaned is None:
        return None
    parts = cleaned.split(":", 2)
    if len(parts) != 3 or parts[0].casefold() != "agent":
        return None
    return _exact_agent_uuid(parts[1])


def _session_agent_ids(session: dict[str, Any]) -> set[uuid.UUID]:
    """Return only explicit immutable ownership identities carried by a provider."""
    identities: set[uuid.UUID] = set()
    direct_agent_id = _exact_agent_uuid(session.get("agent_id"))
    if direct_agent_id is not None:
        identities.add(direct_agent_id)
    for key_name in ("key", "session_key", "session", "id"):
        structured = _structured_session_agent_id(session.get(key_name))
        if structured is not None:
            identities.add(structured)
    return identities


def _session_aliases(session: dict[str, Any]) -> set[str]:
    return {
        alias
        for key_name in ("id", "key", "session_key", "session")
        if (alias := _clean_session_key(session.get(key_name))) is not None
    }


def _canonical_session_key(session: dict[str, Any]) -> str | None:
    for key_name in ("key", "session_key", "session", "id"):
        cleaned = _clean_session_key(session.get(key_name))
        if cleaned is not None:
            return cleaned
    return None


def _binding_key(alias: str) -> str:
    digest = hashlib.sha256(alias.encode("utf-8")).hexdigest()
    return f"{SESSION_OWNERSHIP_PREFIX}{digest}"


def _advisory_lock_id(binding_key: str) -> int:
    """Derive a stable signed bigint for a PostgreSQL transaction lock."""
    digest = hashlib.sha256(binding_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def _lock_binding_keys(db: AsyncSession, binding_keys: set[str]) -> bool:
    """Serialize alias claims in production without requiring a schema change."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql" or not binding_keys:
        return False

    for binding_key in sorted(binding_keys):
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _advisory_lock_id(binding_key)},
        )
    return True


def _signature_payload(
    *,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    alias: str,
    canonical_key: str,
    source: str,
) -> bytes:
    return json.dumps(
        {
            "agent_id": str(agent_id),
            "alias": alias,
            "canonical_key": canonical_key,
            "source": source,
            "user_id": str(user_id),
            "version": _BINDING_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sign_binding(
    *,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    alias: str,
    canonical_key: str,
    source: str,
) -> str:
    secret = get_settings().jwt_secret.encode("utf-8")
    return hmac.new(
        secret,
        _signature_payload(
            user_id=user_id,
            agent_id=agent_id,
            alias=alias,
            canonical_key=canonical_key,
            source=source,
        ),
        hashlib.sha256,
    ).hexdigest()


def _binding_value(
    *,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    alias: str,
    canonical_key: str,
    source: str,
) -> dict[str, Any]:
    return {
        "version": _BINDING_VERSION,
        "user_id": str(user_id),
        "agent_id": str(agent_id),
        "alias": alias,
        "canonical_key": canonical_key,
        "source": source,
        "signature": _sign_binding(
            user_id=user_id,
            agent_id=agent_id,
            alias=alias,
            canonical_key=canonical_key,
            source=source,
        ),
    }


def _parse_binding(setting: UserSetting, *, expected_alias: str) -> OwnedSession | None:
    value = setting.value
    if not isinstance(value, dict) or value.get("version") != _BINDING_VERSION:
        return None

    alias = _clean_session_key(value.get("alias"))
    canonical_key = _clean_session_key(value.get("canonical_key"))
    source = _clean_session_key(value.get("source"))
    signature = value.get("signature")
    try:
        value_user_id = uuid.UUID(str(value.get("user_id")))
        agent_id = uuid.UUID(str(value.get("agent_id")))
    except (TypeError, ValueError, AttributeError):
        return None

    if (
        alias != expected_alias
        or canonical_key is None
        or source is None
        or not isinstance(signature, str)
        or value_user_id != setting.user_id
    ):
        return None

    expected_signature = _sign_binding(
        user_id=setting.user_id,
        agent_id=agent_id,
        alias=alias,
        canonical_key=canonical_key,
        source=source,
    )
    if not hmac.compare_digest(signature, expected_signature):
        return None

    return OwnedSession(canonical_key=canonical_key, source=source, agent_id=agent_id)


async def get_owned_session_agent(
    db: AsyncSession,
    *,
    user: User,
    agent_id: uuid.UUID,
) -> Agent:
    """Resolve an agent inside the persisted principal boundary without an ID oracle."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.user_id == user.id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def filter_and_claim_owned_sessions(
    db: AsyncSession,
    *,
    user: User,
    sessions: list[dict[str, Any]],
    required_agent_id: uuid.UUID | None = None,
    _allow_conflict_retry: bool = True,
) -> list[dict[str, Any]]:
    """Return sessions backed by an immutable UUID or an existing valid binding."""
    user_id = user.id
    records: list[tuple[dict[str, Any], str, set[str], set[uuid.UUID]]] = []
    alias_counts: dict[str, int] = {}
    for session in sessions:
        canonical_key = _canonical_session_key(session)
        aliases = _session_aliases(session)
        if canonical_key is None or not aliases:
            continue
        records.append((session, canonical_key, aliases, _session_agent_ids(session)))
        for alias in aliases:
            alias_counts[alias] = alias_counts.get(alias, 0) + 1

    # A provider alias must identify exactly one live record. This check runs
    # before persistence so duplicate IDs/keys cannot race to become authority.
    records = [record for record in records if all(alias_counts[alias] == 1 for alias in record[2])]

    binding_keys: set[str] = set()
    for _, _, aliases, _ in records:
        binding_keys.update(_binding_key(alias) for alias in aliases)

    locks_acquired = await _lock_binding_keys(db, binding_keys)

    existing_by_key: dict[str, list[UserSetting]] = {}
    if binding_keys:
        existing_result = await db.execute(
            select(UserSetting).where(UserSetting.key.in_(binding_keys))
        )
        for setting in existing_result.scalars().all():
            existing_by_key.setdefault(setting.key, []).append(setting)

    owned_agent_result = await db.execute(select(Agent.id).where(Agent.user_id == user_id))
    owned_agent_ids = set(owned_agent_result.scalars().all())

    visible: list[dict[str, Any]] = []
    added = False
    for session, canonical_key, aliases, provider_agent_ids in records:
        source = _clean_session_key(session.get("source")) or "unknown"
        existing_bindings: list[tuple[UserSetting, OwnedSession]] = []
        binding_conflict = False
        for alias in aliases:
            settings = existing_by_key.get(_binding_key(alias), [])
            if len(settings) > 1:
                binding_conflict = True
                break
            if not settings:
                continue
            setting = settings[0]
            binding = _parse_binding(setting, expected_alias=alias)
            if binding is None:
                binding_conflict = True
                break
            existing_bindings.append((setting, binding))

        if binding_conflict:
            continue

        if existing_bindings:
            bound_agent_ids = {binding.agent_id for _, binding in existing_bindings}
            if len(bound_agent_ids) != 1:
                continue
            agent_id = next(iter(bound_agent_ids))
            if any(
                setting.user_id != user_id
                or binding.agent_id not in owned_agent_ids
                or binding.agent_id != agent_id
                or binding.canonical_key != canonical_key
                for setting, binding in existing_bindings
            ):
                continue
            if provider_agent_ids and provider_agent_ids != {agent_id}:
                continue
        else:
            if len(provider_agent_ids) != 1:
                continue
            agent_id = next(iter(provider_agent_ids))
            if agent_id not in owned_agent_ids:
                continue

        if required_agent_id is not None and agent_id != required_agent_id:
            continue

        for alias in aliases:
            key = _binding_key(alias)
            if existing_by_key.get(key):
                continue
            setting = UserSetting(
                user_id=user_id,
                key=key,
                value=_binding_value(
                    user_id=user_id,
                    agent_id=agent_id,
                    alias=alias,
                    canonical_key=canonical_key,
                    source=source,
                ),
            )
            db.add(setting)
            existing_by_key[key] = [setting]
            added = True

        visible.append(session)

    if added or locks_acquired:
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            if not _allow_conflict_retry:
                raise
            retry_user = await db.get(User, user_id)
            if retry_user is None:
                return []
            # A concurrent request may have claimed the same aliases for this
            # principal. Re-read the persisted authority and fail closed on any
            # conflicting owner or canonical key.
            return await filter_and_claim_owned_sessions(
                db,
                user=retry_user,
                sessions=sessions,
                required_agent_id=required_agent_id,
                _allow_conflict_retry=False,
            )
    return visible


async def require_owned_session(
    db: AsyncSession,
    *,
    user: User,
    session_key: str,
) -> OwnedSession:
    """Resolve a session alias for this principal, returning 404 for every denial."""
    alias = validate_session_key(session_key)
    result = await db.execute(select(UserSetting).where(UserSetting.key == _binding_key(alias)))
    settings = list(result.scalars().all())
    if len(settings) != 1 or settings[0].user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    binding = _parse_binding(settings[0], expected_alias=alias)
    if binding is None:
        raise HTTPException(status_code=404, detail="Session not found")

    agent_result = await db.execute(
        select(Agent.id).where(
            Agent.id == binding.agent_id,
            Agent.user_id == user.id,
        )
    )
    if agent_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return binding


async def require_live_owned_gateway_session(
    db: AsyncSession,
    *,
    user: User,
    session_key: str,
    gateway_sessions: list[dict[str, Any]],
) -> OwnedSession:
    """Resolve a signed binding against exactly one current gateway record."""
    alias = validate_session_key(session_key)

    # Preserve first-use behavior for an unbound session, but only gateway
    # records carrying an unambiguous immutable Agent UUID can establish a
    # binding. Existing bindings are never refreshed from mutable labels.
    await filter_and_claim_owned_sessions(
        db,
        user=user,
        sessions=gateway_sessions,
    )

    result = await db.execute(select(UserSetting).where(UserSetting.key == _binding_key(alias)))
    settings = list(result.scalars().all())
    caller_bindings = [
        binding
        for setting in settings
        if setting.user_id == user.id
        and (binding := _parse_binding(setting, expected_alias=alias)) is not None
    ]
    if len(settings) != 1 or len(caller_bindings) != 1:
        for binding in caller_bindings:
            await forget_owned_session(
                db,
                user=user,
                canonical_key=binding.canonical_key,
            )
        raise HTTPException(status_code=404, detail="Session not found")
    binding = caller_bindings[0]

    records: list[tuple[str, set[str], set[uuid.UUID]]] = []
    alias_counts: dict[str, int] = {}
    for session in gateway_sessions:
        canonical_key = _canonical_session_key(session)
        aliases = _session_aliases(session)
        if canonical_key is None or not aliases:
            continue
        records.append((canonical_key, aliases, _session_agent_ids(session)))
        for record_alias in aliases:
            alias_counts[record_alias] = alias_counts.get(record_alias, 0) + 1

    matching_records = [record for record in records if alias in record[1]]
    live_record_is_valid = len(matching_records) == 1
    if live_record_is_valid:
        canonical_key, aliases, provider_agent_ids = matching_records[0]
        live_record_is_valid = (
            canonical_key == binding.canonical_key
            and provider_agent_ids == {binding.agent_id}
            and all(alias_counts[record_alias] == 1 for record_alias in aliases)
        )

    agent_result = await db.execute(
        select(Agent.id).where(
            Agent.id == binding.agent_id,
            Agent.user_id == user.id,
        )
    )
    if not live_record_is_valid or agent_result.scalar_one_or_none() is None:
        # A missing, duplicated, recycled, or identity-less gateway record must
        # invalidate every signed alias for the old canonical session.
        await forget_owned_session(
            db,
            user=user,
            canonical_key=binding.canonical_key,
        )
        raise HTTPException(status_code=404, detail="Session not found")

    return binding


async def forget_owned_session(
    db: AsyncSession,
    *,
    user: User,
    canonical_key: str,
) -> None:
    """Remove all valid aliases for a canonical session binding."""
    result = await db.execute(
        select(UserSetting).where(
            UserSetting.user_id == user.id,
            UserSetting.key.like(f"{SESSION_OWNERSHIP_PREFIX}%"),
        )
    )
    removed = False
    for setting in result.scalars().all():
        value = setting.value
        alias = value.get("alias") if isinstance(value, dict) else None
        binding = _parse_binding(setting, expected_alias=alias) if isinstance(alias, str) else None
        if binding is not None and binding.canonical_key == canonical_key:
            await db.delete(setting)
            removed = True
    if removed:
        await db.commit()
