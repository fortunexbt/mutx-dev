"""Add durable refresh-token rotation overlap metadata.

Revision ID: c9e1a4b6d8f0
Revises: b8d0f3a1c5e7
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c9e1a4b6d8f0"
down_revision: Union[str, None] = "b8d0f3a1c5e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("refresh_token_sessions"):
        raise RuntimeError(
            "Cannot add refresh rotation metadata before refresh_token_sessions exists"
        )
    return {column["name"] for column in inspector.get_columns("refresh_token_sessions")}


def upgrade() -> None:
    # These claims are non-secret JWT metadata. Persisting them allows the server
    # to reconstruct one exact successor without storing a bearer token at rest.
    existing = _column_names()
    if "original_issued_at" not in existing:
        op.add_column(
            "refresh_token_sessions",
            sa.Column("original_issued_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "token_nonce" not in existing:
        op.add_column(
            "refresh_token_sessions",
            sa.Column("token_nonce", sa.String(length=64), nullable=True),
        )
    if "rotation_grace_expires_at" not in existing:
        op.add_column(
            "refresh_token_sessions",
            sa.Column("rotation_grace_expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("refresh_token_sessions"):
        return
    existing = _column_names()
    if "rotation_grace_expires_at" in existing:
        op.drop_column("refresh_token_sessions", "rotation_grace_expires_at")
    if "token_nonce" in existing:
        op.drop_column("refresh_token_sessions", "token_nonce")
    if "original_issued_at" in existing:
        op.drop_column("refresh_token_sessions", "original_issued_at")
