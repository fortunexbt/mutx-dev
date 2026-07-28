"""Durable, principal-owned state for the legacy ``/v1/security`` API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.approval import ApprovalRecord
from src.api.models.models import Agent, User, UserSetting
from src.api.models.security_schemas import (
    MetricsResponse,
    SecuritySessionState,
)
from src.api.models.security_state import SecurityEvaluation, SecurityReceipt
from src.security.context import IntentSignal, SessionContext
from src.security.mediator import NormalizedAction
from src.security.policy import PolicyDecisionResult
from src.security.receipts import ActionReceipt, ReceiptGenerator

SESSION_KEY_PREFIX = "legacy_security.session."
MAX_SESSION_ID_LENGTH = 180

StateModel = TypeVar("StateModel", bound=BaseModel)


class SecurityStateNotFoundError(Exception):
    """The requested record does not exist in the caller's visible scope."""


class SecurityStateConflictError(Exception):
    """The requested transition is invalid or persisted state is ambiguous."""


class SecurityStateForbiddenError(Exception):
    """The principal is not allowed to perform the requested global operation."""


def is_admin(user: User) -> bool:
    """Return whether the authenticated, database-backed principal is an ADMIN."""
    roles = user.roles if isinstance(user.roles, list) else []
    return any(isinstance(role, str) and role.strip().upper() == "ADMIN" for role in roles)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


def _dump_state(state: BaseModel) -> dict[str, Any]:
    return state.model_dump(mode="json")


def _validate_state(model: type[StateModel], value: Any) -> StateModel | None:
    if not isinstance(value, dict):
        return None
    try:
        return model.model_validate(value)
    except ValidationError:
        return None


def _parse_session(setting: UserSetting) -> SecuritySessionState | None:
    state = _validate_state(SecuritySessionState, setting.value)
    if state is None:
        return None
    if state.owner_id != setting.user_id:
        return None
    if setting.key != _session_key(state.session_id):
        return None
    if state.user_id != str(setting.user_id):
        return None
    return state


async def _select_settings(
    db: AsyncSession,
    *,
    user: User,
    key: str | None = None,
    prefix: str | None = None,
    global_scope: bool = False,
    for_update: bool = False,
) -> list[UserSetting]:
    statement = select(UserSetting)
    if key is not None:
        statement = statement.where(UserSetting.key == key)
    elif prefix is not None:
        statement = statement.where(UserSetting.key.like(f"{prefix}%"))
    else:
        raise ValueError("A key or prefix is required")

    if not global_scope:
        statement = statement.where(UserSetting.user_id == user.id)
    if for_update:
        statement = statement.with_for_update()

    with db.no_autoflush:
        return list((await db.execute(statement)).scalars().all())


def _single_valid_state(
    settings: list[UserSetting],
    parser,
) -> tuple[UserSetting, Any]:
    valid = [(setting, parser(setting)) for setting in settings]
    valid = [(setting, state) for setting, state in valid if state is not None]
    if len(valid) != 1:
        raise SecurityStateNotFoundError
    return valid[0]


async def get_owned_agent(
    db: AsyncSession,
    *,
    owner: User,
    agent_id: uuid.UUID,
) -> Agent:
    """Resolve a persisted agent without disclosing another tenant's ownership."""
    statement = select(Agent).where(Agent.id == agent_id, Agent.user_id == owner.id)
    agent = (await db.execute(statement)).scalar_one_or_none()
    if agent is None:
        raise SecurityStateNotFoundError
    return agent


async def validate_approval_context(
    db: AsyncSession,
    *,
    owner: User,
    agent_id: uuid.UUID,
    session_id: str,
) -> Agent:
    """Validate legacy security ownership before writing a canonical approval."""
    agent = await get_owned_agent(db, owner=owner, agent_id=agent_id)
    session_record = await _get_optional_owned_session_record(
        db,
        user=owner,
        session_id=session_id,
        for_update=False,
    )
    session = session_record[1] if session_record is not None else None
    if session is not None and session.agent_id != str(agent.id):
        raise SecurityStateConflictError("Security session belongs to a different agent")
    return agent


async def create_or_replace_session(
    db: AsyncSession,
    *,
    owner: User,
    session_id: str,
    agent_id: uuid.UUID,
    original_request: str,
    stated_intent: str,
) -> SecuritySessionState:
    """Create a durable owner-scoped session, preserving its original creation time."""
    agent = await get_owned_agent(db, owner=owner, agent_id=agent_id)
    owner_id = owner.id
    now = datetime.now(timezone.utc)
    settings = await _select_settings(
        db,
        user=owner,
        key=_session_key(session_id),
        for_update=True,
    )
    existing_setting = settings[0] if len(settings) == 1 else None
    existing_state = _parse_session(existing_setting) if existing_setting is not None else None
    if settings and existing_state is None:
        raise SecurityStateConflictError("Security session state is invalid")
    if existing_state is not None and existing_state.agent_id != str(agent.id):
        raise SecurityStateConflictError("Security session belongs to a different agent")

    state = SecuritySessionState(
        owner_id=owner_id,
        session_id=session_id,
        agent_id=str(agent.id),
        user_id=str(owner_id),
        original_request=original_request,
        stated_intent=stated_intent,
        created_at=existing_state.created_at if existing_state else now,
        updated_at=now,
        total_actions=existing_state.total_actions if existing_state else 0,
        permits=existing_state.permits if existing_state else 0,
        denials=existing_state.denials if existing_state else 0,
        defers=existing_state.defers if existing_state else 0,
        errors=existing_state.errors if existing_state else 0,
        intent_alignment=existing_state.intent_alignment if existing_state else "unknown",
    )
    if existing_setting is None:
        db.add(
            UserSetting(
                user_id=owner_id,
                key=_session_key(session_id),
                value=_dump_state(state),
            )
        )
    else:
        existing_setting.value = _dump_state(state)
    try:
        await db.commit()
    except IntegrityError as exc:
        # Another worker may have created this owner/key after our initial
        # missing-row read. Reload under a row lock and apply the same update.
        await db.rollback()
        statement = (
            select(UserSetting)
            .where(
                UserSetting.user_id == owner_id,
                UserSetting.key == _session_key(session_id),
            )
            .with_for_update()
        )
        concurrent_settings = list((await db.execute(statement)).scalars().all())
        if len(concurrent_settings) != 1:
            raise SecurityStateConflictError("Security session could not be created") from exc
        concurrent_state = _parse_session(concurrent_settings[0])
        if concurrent_state is None:
            raise SecurityStateConflictError("Security session state is invalid") from exc
        if concurrent_state.agent_id != str(agent.id):
            raise SecurityStateConflictError(
                "Security session belongs to a different agent"
            ) from exc
        retry_now = datetime.now(timezone.utc)
        state = state.model_copy(
            update={
                "created_at": concurrent_state.created_at,
                "updated_at": retry_now,
                "total_actions": concurrent_state.total_actions,
                "permits": concurrent_state.permits,
                "denials": concurrent_state.denials,
                "defers": concurrent_state.defers,
                "errors": concurrent_state.errors,
                "intent_alignment": concurrent_state.intent_alignment,
            }
        )
        concurrent_settings[0].value = _dump_state(state)
        await db.commit()
    return state


async def _get_session_record(
    db: AsyncSession,
    *,
    user: User,
    session_id: str,
    allow_admin: bool,
    for_update: bool = False,
) -> tuple[UserSetting, SecuritySessionState]:
    if len(session_id) > MAX_SESSION_ID_LENGTH:
        raise SecurityStateNotFoundError
    settings = await _select_settings(
        db,
        user=user,
        key=_session_key(session_id),
        global_scope=allow_admin and is_admin(user),
        for_update=for_update,
    )
    return _single_valid_state(settings, _parse_session)


async def _get_optional_owned_session_record(
    db: AsyncSession,
    *,
    user: User,
    session_id: str,
    for_update: bool = False,
) -> tuple[UserSetting, SecuritySessionState] | None:
    """Return no row for absence, but fail closed for persisted invalid state."""
    if len(session_id) > MAX_SESSION_ID_LENGTH:
        raise SecurityStateNotFoundError
    settings = await _select_settings(
        db,
        user=user,
        key=_session_key(session_id),
        for_update=for_update,
    )
    if not settings:
        return None
    try:
        return _single_valid_state(settings, _parse_session)
    except SecurityStateNotFoundError as exc:
        raise SecurityStateConflictError("Security session state is invalid") from exc


async def get_visible_session(
    db: AsyncSession,
    *,
    user: User,
    session_id: str,
) -> SecuritySessionState:
    _, state = await _get_session_record(
        db,
        user=user,
        session_id=session_id,
        allow_admin=True,
    )
    return state


def _session_context(state: SecuritySessionState) -> SessionContext:
    signals: list[IntentSignal] = []
    try:
        signals = [IntentSignal(state.intent_alignment)]
    except ValueError:
        pass
    return SessionContext(
        session_id=state.session_id,
        agent_id=state.agent_id,
        user_id=state.user_id,
        created_at=_as_utc(state.created_at),
        updated_at=_as_utc(state.updated_at),
        original_request=state.original_request,
        stated_intent=state.stated_intent,
        intent_signals=signals,
        tool_call_count=state.permits,
        error_count=state.errors,
        denied_count=state.denials,
    )


async def get_owned_action_context(
    db: AsyncSession,
    *,
    user: User,
    agent_id: uuid.UUID,
    session_id: str,
) -> tuple[Agent, SessionContext | None]:
    """Resolve an owned agent and enforce any persisted session binding."""
    agent = await get_owned_agent(db, owner=user, agent_id=agent_id)
    session_record = await _get_optional_owned_session_record(
        db,
        user=user,
        session_id=session_id,
    )
    if session_record is None:
        return agent, None
    _, state = session_record
    if state.agent_id != str(agent.id):
        raise SecurityStateConflictError("Security session belongs to a different agent")
    return agent, _session_context(state)


async def close_visible_session(
    db: AsyncSession,
    *,
    user: User,
    session_id: str,
) -> SecuritySessionState:
    setting, state = await _get_session_record(
        db,
        user=user,
        session_id=session_id,
        allow_admin=True,
        for_update=True,
    )
    await db.delete(setting)
    await db.commit()
    return state


async def record_evaluation(
    db: AsyncSession,
    *,
    owner: User,
    action: NormalizedAction,
    result: PolicyDecisionResult,
    receipt: ActionReceipt,
    latency_ms: float,
    receipt_verifier: ReceiptGenerator | None = None,
    require_verified_receipt: bool = False,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Atomically persist evaluation provenance, its receipt, and session counters."""
    if require_verified_receipt:
        if receipt_verifier is None:
            raise SecurityStateConflictError(
                "A trusted receipt verifier is required before evaluation persistence"
            )
        is_valid, error = receipt_verifier.verify(receipt)
        if not is_valid:
            raise SecurityStateConflictError(
                f"Security receipt is not verifiable and cannot be persisted: {error}"
            )

    try:
        agent_id = uuid.UUID(action.agent_id)
        action_id = uuid.UUID(action.id)
        receipt_id = uuid.UUID(receipt.receipt_id)
    except (ValueError, AttributeError) as exc:
        raise SecurityStateConflictError("Security evaluation identity is invalid") from exc

    await get_owned_agent(db, owner=owner, agent_id=agent_id)
    session_record = await _get_optional_owned_session_record(
        db,
        user=owner,
        session_id=action.session_id,
        for_update=True,
    )
    if session_record is None:
        setting = None
        state = None
    else:
        setting, state = session_record
    if state is not None and state.agent_id != str(agent_id):
        raise SecurityStateConflictError("Security session belongs to a different agent")

    now = datetime.now(timezone.utc)
    evaluation_id = uuid.uuid4()
    evaluation = SecurityEvaluation(
        id=evaluation_id,
        owner_id=owner.id,
        agent_id=agent_id,
        session_id=action.session_id,
        action_id=action_id,
        action_hash=action.action_hash,
        tool_name=action.tool_name,
        tool_args=receipt.tool_args,
        trigger=action.trigger,
        runtime=action.runtime,
        decision=result.decision.value,
        policy_rule_id=result.rule_id,
        policy_rule_name=result.rule_name,
        decision_reason=result.reason,
        would_modify=result.is_modified,
        latency_ms=max(0.0, latency_ms),
        created_at=_as_utc(action.timestamp),
    )
    persisted_receipt = SecurityReceipt(
        id=receipt_id,
        owner_id=owner.id,
        evaluation_id=evaluation_id,
        agent_id=agent_id,
        session_id=action.session_id,
        timestamp=_as_utc(receipt.timestamp),
        payload=receipt.to_dict(),
    )
    db.add_all([evaluation, persisted_receipt])

    decision = result.decision.value
    if setting is not None and state is not None:
        changes: dict[str, Any] = {
            "total_actions": state.total_actions + 1,
            "updated_at": now,
        }
        if decision in {"permit", "allow"}:
            changes["permits"] = state.permits + 1
        elif decision == "deny":
            changes["denials"] = state.denials + 1
        elif decision == "defer":
            changes["defers"] = state.defers + 1
        setting.value = _dump_state(state.model_copy(update=changes))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise SecurityStateConflictError("Security evaluation could not be persisted") from exc
    return evaluation_id, receipt_id


def _receipt_payload(record: SecurityReceipt) -> dict[str, Any] | None:
    payload = record.payload
    if not isinstance(payload, dict):
        return None
    if payload.get("receipt_id") != str(record.id):
        return None
    if payload.get("session_id") != record.session_id:
        return None
    if payload.get("agent_id") != str(record.agent_id):
        return None
    if payload.get("user_id") != str(record.owner_id):
        return None
    return payload


async def get_visible_receipt(
    db: AsyncSession,
    *,
    user: User,
    receipt_id: str,
) -> dict[str, Any]:
    """Load a receipt through an owner-scoped query, with global ADMIN visibility."""
    try:
        parsed_id = uuid.UUID(receipt_id)
    except (ValueError, AttributeError) as exc:
        raise SecurityStateNotFoundError from exc

    statement = select(SecurityReceipt).where(SecurityReceipt.id == parsed_id)
    if not is_admin(user):
        statement = statement.where(SecurityReceipt.owner_id == user.id)
    record = (await db.execute(statement)).scalar_one_or_none()
    if record is None or (payload := _receipt_payload(record)) is None:
        raise SecurityStateNotFoundError
    return payload


async def list_visible_session_receipts(
    db: AsyncSession,
    *,
    user: User,
    session_id: str,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    """Filter by owner and session in SQL before applying offset and limit."""
    filters = [SecurityReceipt.session_id == session_id]
    if not is_admin(user):
        filters.append(SecurityReceipt.owner_id == user.id)

    total_statement = select(func.count()).select_from(SecurityReceipt).where(*filters)
    total = int((await db.execute(total_statement)).scalar_one())
    statement = (
        select(SecurityReceipt)
        .where(*filters)
        .order_by(SecurityReceipt.timestamp.desc(), SecurityReceipt.id.desc())
        .offset(offset)
        .limit(limit)
    )
    records = list((await db.execute(statement)).scalars().all())
    return [payload for record in records if (payload := _receipt_payload(record))], total


async def get_global_metrics(db: AsyncSession, *, user: User) -> MetricsResponse:
    """Aggregate persisted security state for an authenticated ADMIN."""
    if not is_admin(user):
        raise SecurityStateForbiddenError

    session_settings = await _select_settings(
        db,
        user=user,
        prefix=SESSION_KEY_PREFIX,
        global_scope=True,
    )
    sessions = [state for setting in session_settings if (state := _parse_session(setting))]
    evaluations = list((await db.execute(select(SecurityEvaluation))).scalars().all())
    pending_approvals = int(
        (
            await db.execute(
                select(func.count())
                .select_from(ApprovalRecord)
                .where(ApprovalRecord.status == "PENDING")
            )
        ).scalar_one()
    )
    now = datetime.now(timezone.utc)
    latencies = [state.latency_ms for state in evaluations]
    decisions = [state.decision for state in evaluations]

    return MetricsResponse(
        total_evaluations=len(evaluations),
        permits=sum(decision in {"permit", "allow"} for decision in decisions),
        denials=sum(decision == "deny" for decision in decisions),
        defers=sum(decision == "defer" for decision in decisions),
        pending_approvals=pending_approvals,
        intent_drifts=sum(session.intent_alignment == "drift_confirmed" for session in sessions),
        active_sessions=len(sessions),
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
        decisions_per_minute=sum(
            (now - _as_utc(evaluation.created_at)).total_seconds() < 60
            for evaluation in evaluations
        ),
        decisions_per_hour=sum(
            (now - _as_utc(evaluation.created_at)).total_seconds() < 3600
            for evaluation in evaluations
        ),
    )


def metrics_to_prometheus(metrics: MetricsResponse) -> str:
    """Render persisted metrics using the legacy Prometheus contract."""
    return "\n".join(
        [
            "# HELP mutx_governance_evaluations_total Total policy evaluations",
            "# TYPE mutx_governance_evaluations_total counter",
            f"mutx_governance_evaluations_total {metrics.total_evaluations}",
            "",
            "# HELP mutx_governance_decisions_total Policy decisions by type",
            "# TYPE mutx_governance_decisions_total counter",
            f'mutx_governance_decisions_total{{decision="permit"}} {metrics.permits}',
            f'mutx_governance_decisions_total{{decision="deny"}} {metrics.denials}',
            f'mutx_governance_decisions_total{{decision="defer"}} {metrics.defers}',
            "",
            f"mutx_governance_pending_approvals {metrics.pending_approvals}",
            f"mutx_governance_intent_drifts_total {metrics.intent_drifts}",
            f"mutx_governance_active_sessions {metrics.active_sessions}",
            f"mutx_governance_decision_latency_ms {metrics.avg_latency_ms}",
            f'mutx_governance_decision_rate{{window="minute"}} {metrics.decisions_per_minute}',
            f'mutx_governance_decision_rate{{window="hour"}} {metrics.decisions_per_hour}',
            "",
        ]
    )
