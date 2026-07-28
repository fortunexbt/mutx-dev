"""Add database-authoritative roles to users.

Revision ID: b8d0f3a1c5e7
Revises: a7c9e2f4b6d8
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b8d0f3a1c5e7"
down_revision: Union[str, None] = "a7c9e2f4b6d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _roles_column(*, require_users: bool = True) -> dict | None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("users"):
        if require_users:
            raise RuntimeError("Cannot add persisted roles before the users table exists")
        return None
    return next(
        (column for column in inspector.get_columns("users") if column["name"] == "roles"),
        None,
    )


def upgrade() -> None:
    # The server default both backfills existing rows and keeps direct inserts
    # least-privileged. Admin roles are never inferred or bootstrapped here.
    column = _roles_column()
    if column is None:
        op.add_column(
            "users",
            sa.Column(
                "roles",
                sa.JSON(),
                server_default=sa.text("'[\"VIEWER\"]'"),
                nullable=False,
            ),
        )
        return

    if not isinstance(column["type"], sa.JSON):
        raise RuntimeError(
            "Cannot safely converge users.roles because its existing type is not JSON"
        )
    if column.get("nullable", True):
        op.execute(sa.text("UPDATE users SET roles = '[\"VIEWER\"]' WHERE roles IS NULL"))
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "roles",
                existing_type=sa.JSON(),
                nullable=False,
                server_default=sa.text("'[\"VIEWER\"]'"),
            )


def downgrade() -> None:
    if _roles_column(require_users=False) is not None:
        op.drop_column("users", "roles")
