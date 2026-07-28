"""Add durable owner-keyed legacy security evidence.

Revision ID: d8f1a3c5e7b9
Revises: c7e9a1b3d5f7
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d8f1a3c5e7b9"
down_revision: Union[str, None] = "c7e9a1b3d5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EVALUATION_INDEXES = (
    ("ix_security_evaluations_owner_id", ["owner_id"]),
    ("ix_security_evaluations_agent_id", ["agent_id"]),
    ("ix_security_evaluations_created_at", ["created_at"]),
    (
        "ix_security_evaluations_owner_session_created",
        ["owner_id", "session_id", "created_at"],
    ),
)
RECEIPT_INDEXES = (
    ("ix_security_receipts_owner_id", ["owner_id"]),
    ("ix_security_receipts_agent_id", ["agent_id"]),
    ("ix_security_receipts_timestamp", ["timestamp"]),
    (
        "ix_security_receipts_owner_session_timestamp",
        ["owner_id", "session_id", "timestamp"],
    ),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


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


def _foreign_key_identities(table_name: str) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(foreign_key.get("constrained_columns") or []),
            foreign_key.get("referred_table"),
            tuple(foreign_key.get("referred_columns") or []),
        )
        for foreign_key in _inspector().get_foreign_keys(table_name)
    }


def _unique_identities(table_name: str) -> set[tuple[str, ...]]:
    return {
        tuple(constraint.get("column_names") or [])
        for constraint in _inspector().get_unique_constraints(table_name)
    }


def _validate_existing_table(table_name: str, expected_columns: set[str]) -> None:
    existing_columns = {column["name"] for column in _inspector().get_columns(table_name)}
    missing = expected_columns - existing_columns
    if missing:
        raise RuntimeError(
            f"Cannot safely converge partial {table_name} table; missing columns: "
            f"{', '.join(sorted(missing))}"
        )
    if _inspector().get_pk_constraint(table_name).get("constrained_columns") != ["id"]:
        raise RuntimeError(f"Cannot safely converge {table_name} without its id primary key")
    foreign_keys = _foreign_key_identities(table_name)
    if (("owner_id",), "users", ("id",)) not in foreign_keys:
        raise RuntimeError(f"Cannot safely converge {table_name} without its owner foreign key")
    if table_name == "security_evaluations":
        expected_unique = {("id", "owner_id"), ("owner_id", "action_id")}
        missing_unique = expected_unique - _unique_identities(table_name)
        if missing_unique:
            raise RuntimeError(
                "Cannot safely converge security_evaluations without its tenant uniqueness "
                "constraints"
            )
    elif (
        ("evaluation_id", "owner_id"),
        "security_evaluations",
        ("id", "owner_id"),
    ) not in foreign_keys:
        raise RuntimeError(
            "Cannot safely converge security_receipts without its tenant-bound evaluation "
            "foreign key"
        )


def _ensure_indexes(
    table_name: str,
    indexes: tuple[tuple[str, list[str]], ...],
) -> None:
    for index_name, columns in indexes:
        if not _has_index(table_name, index_name, columns):
            op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    if not _inspector().has_table("users"):
        raise RuntimeError(
            "Cannot provision durable security evidence before the users table exists"
        )
    if not _has_table("security_evaluations"):
        op.create_table(
            "security_evaluations",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("owner_id", sa.UUID(), nullable=False),
            sa.Column("agent_id", sa.UUID(), nullable=False),
            sa.Column("session_id", sa.String(length=180), nullable=False),
            sa.Column("action_id", sa.UUID(), nullable=False),
            sa.Column("action_hash", sa.String(length=64), nullable=False),
            sa.Column("tool_name", sa.String(length=255), nullable=False),
            sa.Column("tool_args", sa.JSON(), nullable=False),
            sa.Column("trigger", sa.String(length=120), nullable=False),
            sa.Column("runtime", sa.String(length=120), nullable=False),
            sa.Column("decision", sa.String(length=32), nullable=False),
            sa.Column("policy_rule_id", sa.String(length=255), nullable=True),
            sa.Column("policy_rule_name", sa.String(length=255), nullable=True),
            sa.Column("decision_reason", sa.Text(), nullable=False),
            sa.Column("would_modify", sa.Boolean(), nullable=False),
            sa.Column("latency_ms", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("id", "owner_id", name="uq_security_evaluations_id_owner"),
            sa.UniqueConstraint(
                "owner_id",
                "action_id",
                name="uq_security_evaluations_owner_action",
            ),
        )
    else:
        _validate_existing_table(
            "security_evaluations",
            {
                "id",
                "owner_id",
                "agent_id",
                "session_id",
                "action_id",
                "action_hash",
                "tool_name",
                "tool_args",
                "trigger",
                "runtime",
                "decision",
                "policy_rule_id",
                "policy_rule_name",
                "decision_reason",
                "would_modify",
                "latency_ms",
                "created_at",
            },
        )
    _ensure_indexes("security_evaluations", EVALUATION_INDEXES)

    if not _has_table("security_receipts"):
        op.create_table(
            "security_receipts",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("owner_id", sa.UUID(), nullable=False),
            sa.Column("evaluation_id", sa.UUID(), nullable=False),
            sa.Column("agent_id", sa.UUID(), nullable=False),
            sa.Column("session_id", sa.String(length=180), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["evaluation_id", "owner_id"],
                ["security_evaluations.id", "security_evaluations.owner_id"],
                name="fk_security_receipts_evaluation_owner",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        _validate_existing_table(
            "security_receipts",
            {
                "id",
                "owner_id",
                "evaluation_id",
                "agent_id",
                "session_id",
                "timestamp",
                "payload",
            },
        )
    _ensure_indexes("security_receipts", RECEIPT_INDEXES)


def downgrade() -> None:
    if _has_table("security_receipts"):
        for index_name, _columns in reversed(RECEIPT_INDEXES):
            if _has_index("security_receipts", index_name):
                op.drop_index(index_name, table_name="security_receipts")
        op.drop_table("security_receipts")

    if _has_table("security_evaluations"):
        for index_name, _columns in reversed(EVALUATION_INDEXES):
            if _has_index("security_evaluations", index_name):
                op.drop_index(index_name, table_name="security_evaluations")
        op.drop_table("security_evaluations")
