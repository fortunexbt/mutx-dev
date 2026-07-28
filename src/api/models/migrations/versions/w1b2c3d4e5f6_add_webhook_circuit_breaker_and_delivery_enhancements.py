"""Add webhook circuit breaker and delivery enhancements

Revision ID: w1b2c3d4e5f6
Revises: f7e2a1c8d9b4
Create Date: 2026-04-16

Adds:
- webhooks.name: Optional human-readable name
- webhooks.consecutive_failures: Circuit breaker tracking
- webhook_delivery_logs.duration_ms: Delivery timing
- webhook_delivery_logs.parent_delivery_id: Manual retry linking
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "w1b2c3d4e5f6"
down_revision: Union[str, None] = "f7e2a1c8d9b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


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


def _validate_existing_table(
    table_name: str,
    required_columns: set[str],
    foreign_key: tuple[tuple[str, ...], str, tuple[str, ...]],
) -> None:
    columns = {column["name"] for column in _inspector().get_columns(table_name)}
    missing = required_columns - columns
    if missing:
        raise RuntimeError(
            f"Cannot safely converge partial {table_name} table; missing columns: "
            f"{', '.join(sorted(missing))}"
        )
    if _inspector().get_pk_constraint(table_name).get("constrained_columns") != ["id"]:
        raise RuntimeError(f"Cannot safely converge {table_name} without its id primary key")
    foreign_keys = {
        (
            tuple(item.get("constrained_columns") or []),
            item.get("referred_table"),
            tuple(item.get("referred_columns") or []),
        )
        for item in _inspector().get_foreign_keys(table_name)
    }
    if foreign_key not in foreign_keys:
        raise RuntimeError(
            f"Cannot safely converge {table_name} without its foreign key to {foreign_key[1]}"
        )


def _preflight() -> None:
    if not _has_table("users"):
        raise RuntimeError("Cannot provision webhooks before the users table exists")
    if _has_table("webhooks"):
        _validate_existing_table(
            "webhooks",
            {"id", "user_id", "url", "events", "secret", "is_active", "created_at"},
            (("user_id",), "users", ("id",)),
        )
    if _has_table("webhook_delivery_logs"):
        _validate_existing_table(
            "webhook_delivery_logs",
            {
                "id",
                "webhook_id",
                "event",
                "payload",
                "status_code",
                "response_body",
                "success",
                "error_message",
                "attempts",
                "created_at",
                "delivered_at",
            },
            (("webhook_id",), "webhooks", ("id",)),
        )


def _webhook_events_type():
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ARRAY(sa.String())
    return sa.Text()


def _ensure_webhooks() -> None:
    # Some live databases were stamped past the migration that assumed this
    # foundational table already existed. Recreate the model-compatible table
    # before applying this branch's enhancements.
    if not _has_table("webhooks"):
        op.create_table(
            "webhooks",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=True),
            sa.Column("url", sa.String(length=512), nullable=False),
            sa.Column("events", _webhook_events_type(), nullable=False),
            sa.Column("secret", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column(
                "consecutive_failures",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_column("webhooks", "name"):
        op.add_column("webhooks", sa.Column("name", sa.String(length=120), nullable=True))
    if not _has_column("webhooks", "consecutive_failures"):
        op.add_column(
            "webhooks",
            sa.Column(
                "consecutive_failures",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    _create_index_if_missing("webhooks", op.f("ix_webhooks_user_id"), ["user_id"])
    _create_index_if_missing("webhooks", op.f("ix_webhooks_is_active"), ["is_active"])


def _ensure_webhook_delivery_logs() -> None:
    # This table depends on webhooks and must be created second so PostgreSQL
    # can validate its foreign key during CREATE TABLE.
    if not _has_table("webhook_delivery_logs"):
        op.create_table(
            "webhook_delivery_logs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("webhook_id", sa.UUID(), nullable=False),
            sa.Column("event", sa.String(length=100), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("response_body", sa.Text(), nullable=True),
            sa.Column("success", sa.Boolean(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("parent_delivery_id", sa.UUID(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("delivered_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["webhook_id"], ["webhooks.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_column("webhook_delivery_logs", "duration_ms"):
        op.add_column(
            "webhook_delivery_logs",
            sa.Column("duration_ms", sa.Integer(), nullable=True),
        )
    if not _has_column("webhook_delivery_logs", "parent_delivery_id"):
        op.add_column(
            "webhook_delivery_logs",
            sa.Column("parent_delivery_id", sa.UUID(), nullable=True),
        )

    _create_index_if_missing(
        "webhook_delivery_logs",
        op.f("ix_webhook_delivery_logs_webhook_id"),
        ["webhook_id"],
    )


def upgrade() -> None:
    _preflight()
    _ensure_webhooks()
    _ensure_webhook_delivery_logs()


def downgrade() -> None:
    # Remove from webhook_delivery_logs
    if _has_column("webhook_delivery_logs", "parent_delivery_id"):
        op.drop_column("webhook_delivery_logs", "parent_delivery_id")

    if _has_column("webhook_delivery_logs", "duration_ms"):
        op.drop_column("webhook_delivery_logs", "duration_ms")

    # Remove from webhooks
    if _has_column("webhooks", "consecutive_failures"):
        op.drop_column("webhooks", "consecutive_failures")

    if _has_column("webhooks", "name"):
        op.drop_column("webhooks", "name")
