"""Add durable tenant-owned scheduler tasks.

Revision ID: c7e9a1b3d5f7
Revises: b6d8f0a2c4e6
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7e9a1b3d5f7"
down_revision: Union[str, None] = "b6d8f0a2c4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "scheduled_tasks"
INDEXES = (
    ("ix_scheduled_tasks_owner_id", ["owner_id"]),
    ("ix_scheduled_tasks_owner_created_at", ["owner_id", "created_at"]),
    ("ix_scheduled_tasks_due", ["enabled", "next_run"]),
    ("ix_scheduled_tasks_active_execution_id", ["active_execution_id"]),
    ("ix_scheduled_tasks_claim_expires_at", ["claim_expires_at"]),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table() -> bool:
    return _inspector().has_table(TABLE_NAME)


def _has_index(index_name: str, expected_columns: list[str] | None = None) -> bool:
    if not _has_table():
        return False
    for index in _inspector().get_indexes(TABLE_NAME):
        if index["name"] != index_name:
            continue
        actual = list(index.get("column_names") or [])
        if expected_columns is not None and actual != expected_columns:
            raise RuntimeError(
                f"Index {index_name} has incompatible columns {actual}; expected {expected_columns}"
            )
        return True
    return False


def _validate_existing_table() -> None:
    expected_columns = {
        "id",
        "owner_id",
        "name",
        "description",
        "enabled",
        "schedule",
        "interval_seconds",
        "task_type",
        "payload",
        "last_run",
        "next_run",
        "run_count",
        "success_count",
        "failure_count",
        "status",
        "last_started_at",
        "last_finished_at",
        "last_succeeded_at",
        "last_failed_at",
        "last_error",
        "last_error_code",
        "last_error_status_code",
        "active_execution_id",
        "claim_expires_at",
        "created_at",
        "updated_at",
    }
    existing_columns = {column["name"] for column in _inspector().get_columns(TABLE_NAME)}
    missing = expected_columns - existing_columns
    if missing:
        raise RuntimeError(
            "Cannot safely converge partial scheduled_tasks table; missing columns: "
            f"{', '.join(sorted(missing))}"
        )
    if _inspector().get_pk_constraint(TABLE_NAME).get("constrained_columns") != ["id"]:
        raise RuntimeError("Cannot safely converge scheduled_tasks without its id primary key")
    expected_foreign_key = (("owner_id",), "users", ("id",))
    foreign_keys = {
        (
            tuple(foreign_key.get("constrained_columns") or []),
            foreign_key.get("referred_table"),
            tuple(foreign_key.get("referred_columns") or []),
        )
        for foreign_key in _inspector().get_foreign_keys(TABLE_NAME)
    }
    if expected_foreign_key not in foreign_keys:
        raise RuntimeError("Cannot safely converge scheduled_tasks without its owner foreign key")
    check_names = {
        constraint.get("name") for constraint in _inspector().get_check_constraints(TABLE_NAME)
    }
    expected_checks = {
        "ck_scheduled_tasks_has_schedule",
        "ck_scheduled_tasks_task_type",
        "ck_scheduled_tasks_status",
    }
    if not expected_checks <= check_names:
        missing_checks = expected_checks - check_names
        raise RuntimeError(
            "Cannot safely converge scheduled_tasks without check constraints: "
            f"{', '.join(sorted(missing_checks))}"
        )


def upgrade() -> None:
    if not _inspector().has_table("users"):
        raise RuntimeError("Cannot provision scheduled_tasks before the users table exists")
    if not _has_table():
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("owner_id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(length=1000), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("schedule", sa.String(length=255), nullable=True),
            sa.Column("interval_seconds", sa.Integer(), nullable=True),
            sa.Column("task_type", sa.String(length=32), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_run", sa.DateTime(timezone=True), nullable=True),
            sa.Column("run_count", sa.Integer(), nullable=False),
            sa.Column("success_count", sa.Integer(), nullable=False),
            sa.Column("failure_count", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_succeeded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("last_error_code", sa.String(length=64), nullable=True),
            sa.Column("last_error_status_code", sa.Integer(), nullable=True),
            sa.Column("active_execution_id", sa.UUID(), nullable=True),
            sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "schedule IS NOT NULL OR interval_seconds IS NOT NULL",
                name="ck_scheduled_tasks_has_schedule",
            ),
            sa.CheckConstraint(
                "task_type IN ('log', 'webhook', 'agent_heartbeat')",
                name="ck_scheduled_tasks_task_type",
            ),
            sa.CheckConstraint(
                "status IN ('scheduled', 'running', 'succeeded', 'failed')",
                name="ck_scheduled_tasks_status",
            ),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        _validate_existing_table()

    for index_name, columns in INDEXES:
        if not _has_index(index_name, columns):
            op.create_index(index_name, TABLE_NAME, columns, unique=False)


def downgrade() -> None:
    if not _has_table():
        return
    for index_name, _columns in reversed(INDEXES):
        if _has_index(index_name):
            op.drop_index(index_name, table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
