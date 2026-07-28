"""Durable, tenant-scoped policy repository and evaluator."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from fnmatch import fnmatch
from typing import Literal

from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.policy import PolicyRecord


class Rule(BaseModel):
    """A policy rule matching mechanism and enforcement action."""

    type: Literal["block", "allow", "warn"]
    pattern: str = Field(min_length=1)
    action: str
    scope: Literal["input", "output", "tool"]


class Policy(BaseModel):
    """A named collection of rules with versioning and enablement."""

    id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    rules: list[Rule]
    enabled: bool
    version: int = Field(ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PolicyUpdate(BaseModel):
    """Complete policy replacement guarded by the caller's observed version."""

    id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    rules: list[Rule]
    enabled: bool
    expected_version: int = Field(ge=1)


class PolicyEvaluationContext(BaseModel):
    """Inputs used to evaluate the authenticated tenant's stored policies."""

    input: str | None = None
    output: str | None = None
    tool: str | None = None
    tool_args: dict[str, JsonValue] | None = None
    run_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class PolicyRuleMatch(BaseModel):
    """A stored policy rule that matched an evaluation context."""

    policy_id: str
    policy_name: str
    policy_version: int
    rule_type: Literal["block", "allow", "warn"]
    rule_scope: Literal["input", "output", "tool"]
    pattern: str
    action: str


class PolicyEvaluationResult(BaseModel):
    """Decision returned by policy evaluation."""

    decision: Literal["allow", "warn", "block", "require_approval"]
    reason: str
    matches: list[PolicyRuleMatch] = Field(default_factory=list)
    evaluated_policy_count: int
    run_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None


class PolicyConflictError(Exception):
    """A policy name or ID is already assigned within this tenant."""


class PolicyNotFoundError(Exception):
    """The named policy does not exist within this tenant."""


class PolicyIdentityMismatchError(Exception):
    """The update path and body do not identify the same stored policy."""


class PolicyVersionConflictError(Exception):
    """The policy changed after the caller observed it."""


def _normalize_match_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _rule_matches(pattern: str, value: object) -> bool:
    if not pattern or value is None:
        return False
    candidate = _normalize_match_value(value).casefold()
    normalized_pattern = pattern.casefold()
    return fnmatch(candidate, normalized_pattern) or normalized_pattern in candidate


def _decision_for_match(
    match: PolicyRuleMatch,
) -> Literal["allow", "warn", "block", "require_approval"]:
    if match.rule_type == "block":
        return "block"
    if match.action.casefold() in {"approval", "require_approval", "request_approval"}:
        return "require_approval"
    if match.rule_type == "warn":
        return "warn"
    return "allow"


def _select_decision(
    matches: list[PolicyRuleMatch],
) -> Literal["allow", "warn", "block", "require_approval"]:
    decisions = {_decision_for_match(match) for match in matches}
    for decision in ("block", "require_approval", "warn"):
        if decision in decisions:
            return decision
    return "allow"


def _policy_from_record(record: PolicyRecord) -> Policy:
    return Policy(
        id=record.policy_id,
        name=record.name,
        rules=[Rule.model_validate(rule) for rule in record.rules],
        enabled=record.enabled,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class PolicyStore:
    """Database-backed policy repository bound to one authenticated owner."""

    def __init__(self, db: AsyncSession, owner_id: uuid.UUID) -> None:
        self._db = db
        self._owner_id = owner_id

    async def _get_record(self, name: str) -> PolicyRecord | None:
        return (
            await self._db.execute(
                select(PolicyRecord)
                .where(
                    PolicyRecord.owner_id == self._owner_id,
                    PolicyRecord.name == name,
                )
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    async def get_policy(self, name: str) -> Policy | None:
        record = await self._get_record(name)
        return _policy_from_record(record) if record is not None else None

    async def list_policies(self) -> list[Policy]:
        records = (
            (
                await self._db.execute(
                    select(PolicyRecord)
                    .where(PolicyRecord.owner_id == self._owner_id)
                    .order_by(PolicyRecord.name)
                )
            )
            .scalars()
            .all()
        )
        return [_policy_from_record(record) for record in records]

    async def create_policy(self, policy: Policy) -> Policy:
        now = datetime.now(timezone.utc)
        record = PolicyRecord(
            owner_id=self._owner_id,
            policy_id=policy.id,
            name=policy.name,
            rules=[rule.model_dump(mode="json") for rule in policy.rules],
            enabled=policy.enabled,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self._db.add(record)
        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            raise PolicyConflictError(
                f"Policy '{policy.name}' or ID '{policy.id}' already exists"
            ) from exc
        return _policy_from_record(record)

    async def update_policy(self, name: str, policy: PolicyUpdate) -> Policy:
        """Atomically replace an owned policy if its identity and version still match."""
        record = await self._get_record(policy.name)
        if name != policy.name:
            record = await self._get_record(name)
        if record is None:
            raise PolicyNotFoundError(name)
        if name != policy.name:
            raise PolicyIdentityMismatchError(
                f"Policy path name '{name}' does not match body name '{policy.name}'"
            )
        if record.policy_id != policy.id:
            raise PolicyIdentityMismatchError(
                f"Policy ID '{policy.id}' does not match the stored policy ID"
            )

        updated_at = datetime.now(timezone.utc)
        statement = (
            update(PolicyRecord)
            .where(
                PolicyRecord.owner_id == self._owner_id,
                PolicyRecord.name == name,
                PolicyRecord.policy_id == policy.id,
                PolicyRecord.version == policy.expected_version,
            )
            .values(
                rules=[rule.model_dump(mode="json") for rule in policy.rules],
                enabled=policy.enabled,
                version=PolicyRecord.version + 1,
                updated_at=updated_at,
            )
            .returning(
                PolicyRecord.policy_id,
                PolicyRecord.name,
                PolicyRecord.rules,
                PolicyRecord.enabled,
                PolicyRecord.version,
                PolicyRecord.created_at,
                PolicyRecord.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        try:
            result = await self._db.execute(statement)
        except IntegrityError as exc:
            await self._db.rollback()
            raise PolicyConflictError(
                f"Policy '{policy.name}' or ID '{policy.id}' already exists"
            ) from exc

        updated = result.one_or_none()
        if updated is None:
            current = await self._get_record(name)
            if current is None:
                raise PolicyNotFoundError(name)
            if current.policy_id != policy.id:
                raise PolicyIdentityMismatchError(
                    f"Policy ID '{policy.id}' does not match the stored policy ID"
                )
            raise PolicyVersionConflictError(
                f"Policy '{name}' is at version {current.version}; expected version "
                f"{policy.expected_version}. Fetch the latest policy and retry the update."
            )

        await self._db.commit()
        return Policy(
            id=updated.policy_id,
            name=updated.name,
            rules=[Rule.model_validate(rule) for rule in updated.rules],
            enabled=updated.enabled,
            version=updated.version,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )

    async def upsert_policy(self, policy: Policy) -> Policy:
        """Compatibility helper that creates or performs a version-guarded replacement."""
        record = await self._get_record(policy.name)
        if record is None:
            return await self.create_policy(policy)
        return await self.update_policy(
            policy.name,
            PolicyUpdate(
                id=record.policy_id,
                name=policy.name,
                rules=policy.rules,
                enabled=policy.enabled,
                expected_version=policy.version,
            ),
        )

    async def delete_policy(self, name: str) -> bool:
        record = await self._get_record(name)
        if record is None:
            return False
        await self._db.delete(record)
        await self._db.commit()
        return True

    async def evaluate(self, context: PolicyEvaluationContext) -> PolicyEvaluationResult:
        records = (
            (
                await self._db.execute(
                    select(PolicyRecord).where(
                        PolicyRecord.owner_id == self._owner_id,
                        PolicyRecord.enabled.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        policies = [_policy_from_record(record) for record in records]

        matches: list[PolicyRuleMatch] = []
        for policy in policies:
            for rule in policy.rules:
                scoped_value: object
                if rule.scope == "input":
                    scoped_value = context.input
                elif rule.scope == "output":
                    scoped_value = context.output
                else:
                    scoped_value = context.tool

                if not _rule_matches(rule.pattern, scoped_value):
                    continue

                matches.append(
                    PolicyRuleMatch(
                        policy_id=policy.id,
                        policy_name=policy.name,
                        policy_version=policy.version,
                        rule_type=rule.type,
                        rule_scope=rule.scope,
                        pattern=rule.pattern,
                        action=rule.action,
                    )
                )

        decision = _select_decision(matches)
        reason = (
            f"{len(matches)} policy rule(s) matched"
            if matches
            else "No enabled policy rules matched"
        )
        return PolicyEvaluationResult(
            decision=decision,
            reason=reason,
            matches=matches,
            evaluated_policy_count=len(policies),
            run_id=context.run_id,
            agent_id=context.agent_id,
            session_id=context.session_id,
        )
