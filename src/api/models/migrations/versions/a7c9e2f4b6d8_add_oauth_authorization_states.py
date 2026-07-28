"""Add one-time OAuth authorization state storage.

Revision ID: a7c9e2f4b6d8
Revises: t2c4d6e8f0a1
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7c9e2f4b6d8"
down_revision: Union[str, None] = "t2c4d6e8f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table() -> bool:
    return _inspector().has_table("oauth_authorization_states")


def _has_index(
    index_name: str,
    expected_columns: list[str] | None = None,
    *,
    unique: bool | None = None,
) -> bool:
    if not _has_table():
        return False
    for index in _inspector().get_indexes("oauth_authorization_states"):
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


def _validate_existing_table() -> None:
    columns = {column["name"] for column in _inspector().get_columns("oauth_authorization_states")}
    expected = {
        "id",
        "state_hash",
        "flow",
        "provider",
        "redirect_uri",
        "created_at",
        "expires_at",
        "consumed_at",
    }
    missing = expected - columns
    if missing:
        raise RuntimeError(
            "Cannot safely converge partial oauth_authorization_states table; "
            f"missing columns: {', '.join(sorted(missing))}"
        )

    primary_key = _inspector().get_pk_constraint("oauth_authorization_states")
    if primary_key.get("constrained_columns") != ["id"]:
        raise RuntimeError(
            "Cannot safely converge oauth_authorization_states without its id primary key"
        )


def upgrade() -> None:
    if not _has_table():
        op.create_table(
            "oauth_authorization_states",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("state_hash", sa.String(length=64), nullable=False),
            sa.Column("flow", sa.String(length=16), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("redirect_uri", sa.String(length=1024), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        _validate_existing_table()

    state_hash_index = op.f("ix_oauth_authorization_states_state_hash")
    if not _has_index(state_hash_index, ["state_hash"], unique=True):
        op.create_index(
            state_hash_index,
            "oauth_authorization_states",
            ["state_hash"],
            unique=True,
        )
    expires_at_index = op.f("ix_oauth_authorization_states_expires_at")
    if not _has_index(expires_at_index, ["expires_at"], unique=False):
        op.create_index(
            expires_at_index,
            "oauth_authorization_states",
            ["expires_at"],
            unique=False,
        )


def downgrade() -> None:
    if not _has_table():
        return
    expires_at_index = op.f("ix_oauth_authorization_states_expires_at")
    if _has_index(expires_at_index):
        op.drop_index(expires_at_index, table_name="oauth_authorization_states")
    state_hash_index = op.f("ix_oauth_authorization_states_state_hash")
    if _has_index(state_hash_index):
        op.drop_index(state_hash_index, table_name="oauth_authorization_states")
    op.drop_table("oauth_authorization_states")
