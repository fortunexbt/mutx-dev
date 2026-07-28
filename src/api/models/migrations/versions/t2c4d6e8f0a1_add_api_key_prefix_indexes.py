"""Add lookup prefixes for managed and agent API keys.

Revision ID: t2c4d6e8f0a1
Revises: s1b2c3d4e5f6
Create Date: 2026-04-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "t2c4d6e8f0a1"
down_revision: Union[str, None] = "s1b2c3d4e5f6"
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


def _ensure_prefix_index(
    table_name: str,
    column_name: str,
    column_type: sa.String,
    index_name: str,
) -> None:
    # Legacy live schemas can be intentionally sparse even when stamped past
    # the initial migration. This optional optimization must not manufacture a
    # missing parent table or prevent the rest of the DAG from converging.
    if not _has_table(table_name):
        return
    if not _has_column(table_name, column_name):
        op.add_column(table_name, sa.Column(column_name, column_type, nullable=True))
    if not _has_index(table_name, index_name, [column_name]):
        op.create_index(index_name, table_name, [column_name], unique=False)


def upgrade() -> None:
    _ensure_prefix_index(
        "api_keys",
        "key_prefix",
        sa.String(length=32),
        op.f("ix_api_keys_key_prefix"),
    )
    _ensure_prefix_index(
        "agents",
        "api_key_prefix",
        sa.String(length=64),
        op.f("ix_agents_api_key_prefix"),
    )


def downgrade() -> None:
    agents_index = op.f("ix_agents_api_key_prefix")
    if _has_index("agents", agents_index):
        op.drop_index(agents_index, table_name="agents")
    if _has_column("agents", "api_key_prefix"):
        op.drop_column("agents", "api_key_prefix")

    api_keys_index = op.f("ix_api_keys_key_prefix")
    if _has_index("api_keys", api_keys_index):
        op.drop_index(api_keys_index, table_name="api_keys")
    if _has_column("api_keys", "key_prefix"):
        op.drop_column("api_keys", "key_prefix")
