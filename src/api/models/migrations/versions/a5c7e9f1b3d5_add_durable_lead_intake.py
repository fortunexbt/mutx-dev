"""Add durable, idempotent public lead intake fields.

Revision ID: a5c7e9f1b3d5
Revises: f4d6a8c0e2b1
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a5c7e9f1b3d5"
down_revision: Union[str, None] = "f4d6a8c0e2b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(
    table_name: str,
    index_name: str,
    expected_columns: list[str] | None = None,
    *,
    unique: bool | None = None,
) -> bool:
    if not _has_table(table_name):
        return False
    for index in _inspector().get_indexes(table_name):
        if index["name"] != index_name:
            continue
        actual_columns = list(index.get("column_names") or [])
        if expected_columns is not None and actual_columns != expected_columns:
            raise RuntimeError(
                f"Index {index_name} has incompatible columns {actual_columns}; "
                f"expected {expected_columns}"
            )
        if unique is not None and bool(index.get("unique")) is not unique:
            raise RuntimeError(
                f"Index {index_name} has incompatible uniqueness; expected unique={unique}"
            )
        return True
    return False


def _add_column_if_missing(column: sa.Column) -> None:
    if not _has_column("leads", column.name):
        op.add_column("leads", column)


def _validate_existing_leads_table() -> None:
    columns = {column["name"] for column in _inspector().get_columns("leads")}
    foundational = {"id", "email", "name", "company", "message", "source", "created_at"}
    missing = foundational - columns
    if missing:
        raise RuntimeError(
            "Cannot safely converge partial leads table; missing foundational columns: "
            f"{', '.join(sorted(missing))}"
        )
    if _inspector().get_pk_constraint("leads").get("constrained_columns") != ["id"]:
        raise RuntimeError("Cannot safely converge leads without its id primary key")


def upgrade() -> None:
    # Some deployed databases were stamped beyond the historical live-mode
    # convergence migration without ever receiving the original leads table.
    # Keep this forward repair safe for both those databases and normal upgrades.
    if not _has_table("leads"):
        op.create_table(
            "leads",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("company", sa.String(length=255), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        _validate_existing_leads_table()

    _add_column_if_missing(sa.Column("tier", sa.String(length=50), nullable=True))
    _add_column_if_missing(sa.Column("interest", sa.String(length=80), nullable=True))
    _add_column_if_missing(sa.Column("locale", sa.String(length=16), nullable=True))
    _add_column_if_missing(
        sa.Column(
            "product_updates_consent",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    _add_column_if_missing(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    _add_column_if_missing(sa.Column("content_hash", sa.String(length=64), nullable=True))
    _add_column_if_missing(
        sa.Column("notification_scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    for index_name, columns, unique in (
        (op.f("ix_leads_email"), ["email"], False),
        (op.f("ix_leads_created_at"), ["created_at"], False),
        (op.f("ix_leads_idempotency_key"), ["idempotency_key"], True),
    ):
        if not _has_index("leads", index_name, columns, unique=unique):
            op.create_index(index_name, "leads", columns, unique=unique)


def downgrade() -> None:
    if not _has_table("leads"):
        return
    idempotency_index = op.f("ix_leads_idempotency_key")
    if _has_index("leads", idempotency_index):
        op.drop_index(idempotency_index, table_name="leads")
    for column_name in (
        "notification_scheduled_at",
        "content_hash",
        "idempotency_key",
        "product_updates_consent",
        "locale",
        "interest",
        "tier",
    ):
        if _has_column("leads", column_name):
            op.drop_column("leads", column_name)
