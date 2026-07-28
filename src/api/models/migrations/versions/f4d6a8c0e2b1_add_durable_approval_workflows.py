"""Add durable approval workflows and notification outbox.

Revision ID: f4d6a8c0e2b1
Revises: e3c5a7b9d1f2
Create Date: 2026-07-28
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f4d6a8c0e2b1"
down_revision: Union[str, None] = "e3c5a7b9d1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPROVAL_KEY_PREFIX = "approval.request."
SECURITY_APPROVAL_KEY_PREFIX = "legacy_security.approval."
VALID_STATUSES = {"PENDING", "APPROVED", "REJECTED", "EXPIRED"}


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _require_columns(table_name: str, required: set[str]) -> None:
    existing = {column["name"] for column in _inspector().get_columns(table_name)}
    missing = required - existing
    if missing:
        raise RuntimeError(
            f"Cannot safely converge partial {table_name} table; missing columns: "
            f"{', '.join(sorted(missing))}"
        )


def _require_primary_key(table_name: str) -> None:
    columns = _inspector().get_pk_constraint(table_name).get("constrained_columns") or []
    if columns != ["id"]:
        raise RuntimeError(f"Cannot safely converge {table_name} without its id primary key")


def _require_unique(table_name: str, expected_columns: tuple[str, ...]) -> None:
    constraints = _inspector().get_unique_constraints(table_name)
    if not any(
        tuple(constraint.get("column_names") or []) == expected_columns
        for constraint in constraints
    ):
        joined = ", ".join(expected_columns)
        raise RuntimeError(f"Cannot safely converge {table_name} without uniqueness on ({joined})")


def _require_foreign_key(
    table_name: str,
    constrained_columns: tuple[str, ...],
    referred_table: str,
    referred_columns: tuple[str, ...],
) -> None:
    expected = (constrained_columns, referred_table, referred_columns)
    for foreign_key in _inspector().get_foreign_keys(table_name):
        actual = (
            tuple(foreign_key.get("constrained_columns") or []),
            foreign_key.get("referred_table"),
            tuple(foreign_key.get("referred_columns") or []),
        )
        if actual == expected:
            return
    raise RuntimeError(
        f"Cannot safely converge {table_name} without its foreign key to {referred_table}"
    )


def _require_check(table_name: str, constraint_name: str) -> None:
    if not any(
        constraint.get("name") == constraint_name
        for constraint in _inspector().get_check_constraints(table_name)
    ):
        raise RuntimeError(
            f"Cannot safely converge {table_name} without check constraint {constraint_name}"
        )


def _validate_approval_request_constraints() -> None:
    _require_primary_key("approval_requests")
    _require_unique("approval_requests", ("owner_id", "idempotency_key"))
    _require_foreign_key("approval_requests", ("owner_id",), "users", ("id",))
    _require_foreign_key("approval_requests", ("reviewer_id",), "users", ("id",))
    _require_check("approval_requests", "ck_approval_requests_reviewer_not_owner")


def _validate_approval_outbox_constraints() -> None:
    _require_primary_key("approval_notification_outbox")
    _require_unique("approval_notification_outbox", ("approval_id",))
    _require_foreign_key(
        "approval_notification_outbox",
        ("approval_id",),
        "approval_requests",
        ("id",),
    )


def _has_index(
    table_name: str,
    index_name: str,
    expected_columns: list[str] | None = None,
) -> bool:
    if not _has_table(table_name):
        return False
    for index in _inspector().get_indexes(table_name):
        if index["name"] != index_name:
            continue
        actual = list(index.get("column_names") or [])
        if expected_columns is not None and actual != expected_columns:
            raise RuntimeError(
                f"Index {index_name} has incompatible columns {actual}; expected {expected_columns}"
            )
        return True
    return False


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    if not _has_index(table_name, index_name, columns):
        op.create_index(index_name, table_name, columns, unique=False)


def _ensure_approval_requests() -> None:
    if not _has_table("approval_requests"):
        op.create_table(
            "approval_requests",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("owner_id", sa.UUID(), nullable=False),
            sa.Column("reviewer_id", sa.UUID(), nullable=True),
            sa.Column("agent_id", sa.String(length=255), nullable=False),
            sa.Column("session_id", sa.String(length=255), nullable=False),
            sa.Column("action_type", sa.String(length=255), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("requester", sa.String(length=255), nullable=False),
            sa.Column("approver", sa.String(length=255), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=255), nullable=True),
            sa.Column("request_hash", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "reviewer_id IS NULL OR reviewer_id <> owner_id",
                name="ck_approval_requests_reviewer_not_owner",
            ),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_id",
                "idempotency_key",
                name="uq_approval_requests_owner_idempotency_key",
            ),
        )
    else:
        _require_columns(
            "approval_requests",
            {
                "id",
                "owner_id",
                "reviewer_id",
                "agent_id",
                "session_id",
                "action_type",
                "payload",
                "status",
                "requester",
                "approver",
                "comment",
                "idempotency_key",
                "request_hash",
                "created_at",
                "updated_at",
                "resolved_at",
            },
        )

    _create_index_if_missing(
        "approval_requests",
        "ix_approval_requests_owner_status_created_at",
        ["owner_id", "status", "created_at"],
    )
    _create_index_if_missing(
        "approval_requests",
        "ix_approval_requests_reviewer_status_created_at",
        ["reviewer_id", "status", "created_at"],
    )
    _create_index_if_missing(
        "approval_requests",
        "ix_approval_requests_agent_status_created_at",
        ["agent_id", "status", "created_at"],
    )


def _ensure_approval_outbox() -> None:
    if not _has_table("approval_notification_outbox"):
        op.create_table(
            "approval_notification_outbox",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("approval_id", sa.UUID(), nullable=False),
            sa.Column("destination_url", sa.String(length=2048), nullable=False),
            sa.Column("event_payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["approval_id"],
                ["approval_requests.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "approval_id",
                name="uq_approval_notification_outbox_approval_id",
            ),
        )
    else:
        _require_columns(
            "approval_notification_outbox",
            {
                "id",
                "approval_id",
                "destination_url",
                "event_payload",
                "status",
                "attempt_count",
                "last_error",
                "next_attempt_at",
                "locked_at",
                "delivered_at",
                "created_at",
                "updated_at",
            },
        )

    _create_index_if_missing(
        "approval_notification_outbox",
        "ix_approval_notification_outbox_status_next_attempt_at",
        ["status", "next_attempt_at"],
    )


def _decode_legacy_value(raw_value: object) -> dict | None:
    if isinstance(raw_value, dict):
        return raw_value
    if not isinstance(raw_value, str):
        return None
    try:
        decoded = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _parse_uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _parse_datetime(value: object, fallback: object = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    else:
        parsed = None

    if parsed is None and fallback is not None and fallback is not value:
        return _parse_datetime(fallback)
    if parsed is None:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _required_text(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 255:
        return None
    return value


def _request_hash(value: dict) -> str:
    canonical = json.dumps(
        {
            "action_type": value["action_type"],
            "agent_id": value["agent_id"],
            "payload": value["payload"],
            "reviewer_id": (
                str(value["reviewer_id"]) if value.get("reviewer_id") is not None else None
            ),
            "session_id": value["session_id"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _legacy_approval(row: sa.RowMapping) -> dict | None:
    value = _decode_legacy_value(row["value"])
    if value is None:
        return None

    key = row["key"]
    if not isinstance(key, str) or not key.startswith(APPROVAL_KEY_PREFIX):
        return None
    key_id = _parse_uuid(key.removeprefix(APPROVAL_KEY_PREFIX))
    value_id = _parse_uuid(value.get("id"))
    owner_id = _parse_uuid(row["user_id"])
    if key_id is None or value_id != key_id or owner_id is None:
        return None

    status = value.get("status", "PENDING")
    payload = value.get("payload", {})
    agent_id = _required_text(value.get("agent_id"))
    session_id = _required_text(value.get("session_id"))
    action_type = _required_text(value.get("action_type"))
    requester = _required_text(value.get("requester"))
    approver = value.get("approver")
    comment = value.get("comment")
    resolved_at_value = value.get("resolved_at")
    resolved_at = _optional_datetime(resolved_at_value)
    if (
        not isinstance(status, str)
        or status not in VALID_STATUSES
        or not isinstance(payload, dict)
        or agent_id is None
        or session_id is None
        or action_type is None
        or requester is None
        or (approver is not None and (not isinstance(approver, str) or len(approver) > 255))
        or (comment is not None and not isinstance(comment, str))
        or (resolved_at_value is not None and resolved_at is None)
    ):
        return None

    normalized = {
        "agent_id": agent_id,
        "session_id": session_id,
        "action_type": action_type,
        "payload": payload,
    }
    return {
        "id": key_id,
        "owner_id": owner_id,
        "reviewer_id": None,
        **normalized,
        "status": status,
        "requester": requester,
        "approver": approver,
        "comment": comment,
        "idempotency_key": None,
        "request_hash": _request_hash(normalized),
        "created_at": _parse_datetime(value.get("created_at"), row["created_at"]),
        "updated_at": _parse_datetime(row["updated_at"], row["created_at"]),
        "resolved_at": resolved_at,
    }


def _legacy_security_approval(row: sa.RowMapping) -> dict | None:
    """Converge the token-era security record without carrying its bearer secret."""
    value = _decode_legacy_value(row["value"])
    if value is None:
        return None

    key = row["key"]
    if not isinstance(key, str) or not key.startswith(SECURITY_APPROVAL_KEY_PREFIX):
        return None
    key_id = _parse_uuid(key.removeprefix(SECURITY_APPROVAL_KEY_PREFIX))
    value_id = _parse_uuid(value.get("request_id"))
    owner_id = _parse_uuid(row["user_id"])
    state_owner_id = _parse_uuid(value.get("owner_id"))
    reviewer_id = _parse_uuid(value.get("reviewer_id"))
    if key_id is None or value_id != key_id or owner_id is None or state_owner_id != owner_id:
        return None

    status = {
        "pending": "PENDING",
        "approved": "APPROVED",
        "denied": "REJECTED",
        "expired": "EXPIRED",
    }.get(value.get("status"))
    tool_name = _required_text(value.get("tool_name"))
    agent_id = _required_text(value.get("agent_id"))
    session_id = _required_text(value.get("session_id"))
    tool_args = value.get("tool_args", {})
    reason = value.get("reason", "")
    created_at = _parse_datetime(value.get("created_at"), row["created_at"])
    expires_at = _optional_datetime(value.get("expires_at"))
    if (
        status is None
        or tool_name is None
        or agent_id is None
        or session_id is None
        or not isinstance(tool_args, dict)
        or not isinstance(reason, str)
        or expires_at is None
    ):
        return None

    timeout_minutes = max(1, min(60, round((expires_at - created_at).total_seconds() / 60)))
    normalized = {
        "agent_id": agent_id,
        "session_id": session_id,
        "action_type": tool_name,
        "payload": {
            "tool_args": tool_args,
            "reason": reason,
            "timeout_minutes": timeout_minutes,
            "source": "legacy_security",
        },
        "reviewer_id": reviewer_id,
    }
    decided_by = value.get("decided_by")
    comment = value.get("reviewer_comment")
    if decided_by is not None and not isinstance(decided_by, str):
        decided_by = None
    if comment is not None and not isinstance(comment, str):
        comment = None
    return {
        "id": key_id,
        "owner_id": owner_id,
        "reviewer_id": reviewer_id,
        "agent_id": agent_id,
        "session_id": session_id,
        "action_type": tool_name,
        "payload": normalized["payload"],
        "status": status,
        "requester": str(owner_id),
        "approver": decided_by,
        "comment": comment,
        "idempotency_key": None,
        "request_hash": _request_hash(normalized),
        "created_at": created_at,
        "updated_at": _parse_datetime(row["updated_at"], created_at),
        "resolved_at": _optional_datetime(value.get("decided_at")),
    }


def _backfill_legacy_approvals() -> None:
    if not _has_table("user_settings"):
        return

    bind = op.get_bind()
    metadata = sa.MetaData()
    user_settings = sa.Table("user_settings", metadata, autoload_with=bind)
    approvals = sa.Table("approval_requests", metadata, autoload_with=bind)
    rows = bind.execute(
        sa.select(
            user_settings.c.user_id,
            user_settings.c.key,
            user_settings.c.value,
            user_settings.c.created_at,
            user_settings.c.updated_at,
        ).where(
            sa.or_(
                user_settings.c.key.like(f"{APPROVAL_KEY_PREFIX}%"),
                user_settings.c.key.like(f"{SECURITY_APPROVAL_KEY_PREFIX}%"),
            )
        )
    ).mappings()

    for row in rows:
        approval = (
            _legacy_security_approval(row)
            if str(row["key"]).startswith(SECURITY_APPROVAL_KEY_PREFIX)
            else _legacy_approval(row)
        )
        if approval is None:
            continue
        approval_values = dict(approval)
        if bind.dialect.name == "sqlite":
            approval_values["id"] = str(approval_values["id"])
            approval_values["owner_id"] = str(approval_values["owner_id"])
            if approval_values["reviewer_id"] is not None:
                approval_values["reviewer_id"] = str(approval_values["reviewer_id"])
        existing = (
            bind.execute(
                sa.select(
                    approvals.c.id,
                    approvals.c.owner_id,
                    approvals.c.request_hash,
                ).where(approvals.c.id == approval_values["id"])
            )
            .mappings()
            .one_or_none()
        )
        if existing is None:
            bind.execute(approvals.insert().values(**approval_values))
        elif (
            _parse_uuid(existing["owner_id"]) != approval["owner_id"]
            or existing["request_hash"] != approval["request_hash"]
        ):
            raise RuntimeError(
                f"Legacy approval {approval['id']} conflicts with an existing durable record"
            )


def _preflight() -> None:
    if not _has_table("users"):
        raise RuntimeError("Cannot provision durable approvals before the users table exists")
    if _has_table("approval_requests"):
        _require_columns(
            "approval_requests",
            {
                "id",
                "owner_id",
                "reviewer_id",
                "agent_id",
                "session_id",
                "action_type",
                "payload",
                "status",
                "requester",
                "approver",
                "comment",
                "idempotency_key",
                "request_hash",
                "created_at",
                "updated_at",
                "resolved_at",
            },
        )
        _validate_approval_request_constraints()
    if _has_table("approval_notification_outbox"):
        _require_columns(
            "approval_notification_outbox",
            {
                "id",
                "approval_id",
                "destination_url",
                "event_payload",
                "status",
                "attempt_count",
                "last_error",
                "next_attempt_at",
                "locked_at",
                "delivered_at",
                "created_at",
                "updated_at",
            },
        )
        _validate_approval_outbox_constraints()
    if _has_table("user_settings"):
        _require_columns(
            "user_settings",
            {"user_id", "key", "value", "created_at", "updated_at"},
        )


def upgrade() -> None:
    _preflight()
    _ensure_approval_requests()
    _ensure_approval_outbox()
    _backfill_legacy_approvals()


def downgrade() -> None:
    if _has_table("approval_notification_outbox"):
        op.drop_table("approval_notification_outbox")
    if _has_table("approval_requests"):
        op.drop_table("approval_requests")
