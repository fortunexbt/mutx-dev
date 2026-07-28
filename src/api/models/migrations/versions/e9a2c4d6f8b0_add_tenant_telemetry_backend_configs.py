"""Add durable tenant-owned telemetry backend configurations.

Revision ID: e9a2c4d6f8b0
Revises: d8f1a3c5e7b9
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e9a2c4d6f8b0"
down_revision: Union[str, None] = "d8f1a3c5e7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "telemetry_backend_configs"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table() -> bool:
    return _inspector().has_table(TABLE_NAME)


def _validate_existing_table() -> None:
    expected = {"id", "owner_id", "endpoint", "protocol", "created_at", "updated_at"}
    existing = {column["name"] for column in _inspector().get_columns(TABLE_NAME)}
    missing = expected - existing
    if missing:
        raise RuntimeError(
            "Cannot safely converge partial telemetry_backend_configs table; missing columns: "
            f"{', '.join(sorted(missing))}"
        )
    if _inspector().get_pk_constraint(TABLE_NAME).get("constrained_columns") != ["id"]:
        raise RuntimeError(
            "Cannot safely converge telemetry_backend_configs without its id primary key"
        )
    unique_columns = {
        tuple(constraint.get("column_names") or [])
        for constraint in _inspector().get_unique_constraints(TABLE_NAME)
    }
    if ("owner_id",) not in unique_columns:
        raise RuntimeError(
            "Cannot safely converge telemetry_backend_configs without owner uniqueness"
        )
    foreign_keys = {
        (
            tuple(foreign_key.get("constrained_columns") or []),
            foreign_key.get("referred_table"),
            tuple(foreign_key.get("referred_columns") or []),
        )
        for foreign_key in _inspector().get_foreign_keys(TABLE_NAME)
    }
    if (("owner_id",), "users", ("id",)) not in foreign_keys:
        raise RuntimeError(
            "Cannot safely converge telemetry_backend_configs without its owner foreign key"
        )
    check_names = {
        constraint.get("name") for constraint in _inspector().get_check_constraints(TABLE_NAME)
    }
    if "ck_telemetry_backend_configs_protocol" not in check_names:
        raise RuntimeError(
            "Cannot safely converge telemetry_backend_configs without its protocol check"
        )


def upgrade() -> None:
    if not _inspector().has_table("users"):
        raise RuntimeError(
            "Cannot provision telemetry_backend_configs before the users table exists"
        )
    if not _has_table():
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("owner_id", sa.UUID(), nullable=False),
            sa.Column("endpoint", sa.String(length=2048), nullable=False),
            sa.Column("protocol", sa.String(length=8), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "protocol IN ('grpc', 'http')",
                name="ck_telemetry_backend_configs_protocol",
            ),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_id",
                name="uq_telemetry_backend_configs_owner_id",
            ),
        )
    else:
        _validate_existing_table()


def downgrade() -> None:
    if _has_table():
        op.drop_table(TABLE_NAME)
