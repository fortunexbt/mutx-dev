"""Add durable MUTX agent-run observability storage.

Revision ID: f0b4d6e8a2c5
Revises: e9a2c4d6f8b0
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f0b4d6e8a2c5"
down_revision: Union[str, None] = "e9a2c4d6f8b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_ORDER = (
    "mutx_runs",
    "mutx_steps",
    "mutx_costs",
    "mutx_provenance",
    "mutx_eval_results",
)

COLUMN_SPECS: dict[str, tuple[tuple[str, sa.types.TypeEngine, bool], ...]] = {
    "mutx_runs": (
        ("id", sa.String(length=64), False),
        ("agent_id", sa.String(length=255), False),
        ("user_id", sa.UUID(), False),
        ("agent_name", sa.String(length=255), True),
        ("model", sa.String(length=100), True),
        ("provider", sa.String(length=50), True),
        ("runtime", sa.String(length=100), True),
        ("runtime_version", sa.String(length=50), True),
        ("trigger", sa.String(length=50), True),
        ("parent_run_id", sa.String(length=64), True),
        ("task_id", sa.String(length=255), True),
        ("status", sa.String(length=50), False),
        ("outcome", sa.String(length=50), True),
        ("started_at", sa.DateTime(timezone=True), False),
        ("ended_at", sa.DateTime(timezone=True), True),
        ("duration_ms", sa.Integer(), True),
        ("tools_available", sa.Text(), True),
        ("git_branch", sa.String(length=255), True),
        ("git_commit", sa.String(length=40), True),
        ("workspace_id", sa.String(length=255), True),
        ("tags", sa.Text(), True),
        ("run_metadata", sa.Text(), True),
        ("error", sa.Text(), True),
        ("created_at", sa.DateTime(timezone=True), False),
    ),
    "mutx_steps": (
        ("id", sa.String(length=64), False),
        ("run_id", sa.String(length=64), False),
        ("type", sa.String(length=50), False),
        ("tool_name", sa.String(length=255), True),
        ("mcp_server", sa.String(length=255), True),
        ("input_preview", sa.Text(), True),
        ("output_preview", sa.Text(), True),
        ("success", sa.Boolean(), True),
        ("error", sa.Text(), True),
        ("started_at", sa.DateTime(timezone=True), False),
        ("ended_at", sa.DateTime(timezone=True), True),
        ("duration_ms", sa.Integer(), True),
        ("tokens_used", sa.Integer(), True),
        ("sequence", sa.Integer(), False),
        ("step_metadata", sa.Text(), True),
        ("created_at", sa.DateTime(timezone=True), False),
    ),
    "mutx_costs": (
        ("id", sa.UUID(), False),
        ("run_id", sa.String(length=64), False),
        ("input_tokens", sa.Integer(), False),
        ("output_tokens", sa.Integer(), False),
        ("cache_read_tokens", sa.Integer(), True),
        ("cache_write_tokens", sa.Integer(), True),
        ("total_tokens", sa.Integer(), True),
        ("cost_usd", sa.Float(), True),
        ("model", sa.String(length=100), True),
        ("created_at", sa.DateTime(timezone=True), False),
    ),
    "mutx_provenance": (
        ("id", sa.UUID(), False),
        ("run_id", sa.String(length=64), False),
        ("run_hash", sa.String(length=64), False),
        ("parent_run_hash", sa.String(length=64), True),
        ("lineage", sa.Text(), True),
        ("model_version", sa.String(length=100), True),
        ("config_hash", sa.String(length=64), True),
        ("runtime", sa.String(length=100), True),
        ("signed_by", sa.String(length=255), True),
        ("signature", sa.Text(), True),
        ("created_at", sa.DateTime(timezone=True), False),
    ),
    "mutx_eval_results": (
        ("id", sa.UUID(), False),
        ("run_id", sa.String(length=64), False),
        ("task_type", sa.String(length=100), True),
        ("eval_layer", sa.String(length=100), True),
        ("eval_pass", sa.Boolean(), False),
        ("score", sa.Float(), False),
        ("expected_outcome", sa.Text(), True),
        ("actual_outcome", sa.Text(), True),
        ("metrics", sa.Text(), True),
        ("regression_from", sa.String(length=64), True),
        ("detail", sa.Text(), True),
        ("benchmark_id", sa.String(length=255), True),
        ("created_at", sa.DateTime(timezone=True), False),
    ),
}

PRIMARY_KEYS = {table_name: (f"pk_{table_name}", ("id",)) for table_name in TABLE_ORDER}

FOREIGN_KEYS = {
    "mutx_runs": (
        (
            "fk_mutx_runs_user_id_users",
            ("user_id",),
            "users",
            ("id",),
            None,
        ),
    ),
    "mutx_steps": (
        (
            "fk_mutx_steps_run_id_mutx_runs",
            ("run_id",),
            "mutx_runs",
            ("id",),
            "CASCADE",
        ),
    ),
    "mutx_costs": (
        (
            "fk_mutx_costs_run_id_mutx_runs",
            ("run_id",),
            "mutx_runs",
            ("id",),
            "CASCADE",
        ),
    ),
    "mutx_provenance": (
        (
            "fk_mutx_provenance_run_id_mutx_runs",
            ("run_id",),
            "mutx_runs",
            ("id",),
            "CASCADE",
        ),
    ),
    "mutx_eval_results": (
        (
            "fk_mutx_eval_results_run_id_mutx_runs",
            ("run_id",),
            "mutx_runs",
            ("id",),
            "CASCADE",
        ),
    ),
}

INDEXES = {
    "mutx_runs": (
        ("ix_mutx_runs_agent_id", ("agent_id",), False),
        ("ix_mutx_runs_model", ("model",), False),
        ("ix_mutx_runs_parent_run_id", ("parent_run_id",), False),
        ("ix_mutx_runs_started_at", ("started_at",), False),
        ("ix_mutx_runs_status", ("status",), False),
        ("ix_mutx_runs_task_id", ("task_id",), False),
        ("ix_mutx_runs_trigger", ("trigger",), False),
        ("ix_mutx_runs_user_id", ("user_id",), False),
        ("ix_mutx_runs_user_started", ("user_id", "started_at"), False),
        ("ix_mutx_runs_user_status", ("user_id", "status"), False),
        ("ix_mutx_runs_workspace_id", ("workspace_id",), False),
    ),
    "mutx_steps": (
        ("ix_mutx_steps_run_id", ("run_id",), False),
        ("ix_mutx_steps_run_sequence", ("run_id", "sequence"), False),
        ("ix_mutx_steps_tool_name", ("tool_name",), False),
        ("ix_mutx_steps_type", ("type",), False),
    ),
    "mutx_costs": (("ix_mutx_costs_run_id", ("run_id",), True),),
    "mutx_provenance": (
        ("ix_mutx_provenance_run_hash", ("run_hash",), False),
        ("ix_mutx_provenance_run_id", ("run_id",), True),
    ),
    "mutx_eval_results": (
        ("ix_mutx_eval_results_run_id", ("run_id",), True),
        ("ix_mutx_eval_results_run_pass", ("run_id", "eval_pass"), False),
        ("ix_mutx_eval_results_task_type", ("task_type",), False),
    ),
}


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _columns(table_name: str) -> list[sa.Column]:
    return [
        sa.Column(column_name, column_type.copy(), nullable=nullable)
        for column_name, column_type, nullable in COLUMN_SPECS[table_name]
    ]


def _types_are_identical(
    actual: sa.types.TypeEngine,
    expected: sa.types.TypeEngine,
) -> bool:
    if isinstance(expected, sa.UUID):
        return isinstance(actual, sa.UUID) or (
            op.get_bind().dialect.name == "sqlite"
            and isinstance(actual, sa.CHAR)
            and actual.length == 36
        )
    if isinstance(expected, sa.DateTime):
        if not isinstance(actual, sa.DateTime):
            return False
        return op.get_bind().dialect.name == "sqlite" or actual.timezone == expected.timezone
    if isinstance(expected, sa.Text):
        return isinstance(actual, sa.Text)
    if isinstance(expected, sa.String):
        return isinstance(actual, sa.String) and actual.length == expected.length
    if isinstance(expected, sa.Boolean):
        return isinstance(actual, sa.Boolean)
    if isinstance(expected, sa.Integer):
        return isinstance(actual, sa.Integer) and not isinstance(actual, sa.Boolean)
    if isinstance(expected, sa.Float):
        return isinstance(actual, sa.Float)
    return type(actual) is type(expected)


def _foreign_key_contracts(
    table_name: str,
) -> set[tuple[str | None, tuple[str, ...], str | None, tuple[str, ...], str | None]]:
    return {
        (
            foreign_key.get("name"),
            tuple(foreign_key.get("constrained_columns") or []),
            foreign_key.get("referred_table"),
            tuple(foreign_key.get("referred_columns") or []),
            (foreign_key.get("options") or {}).get("ondelete"),
        )
        for foreign_key in _inspector().get_foreign_keys(table_name)
    }


def _validate_existing_table(table_name: str) -> None:
    expected_columns = COLUMN_SPECS[table_name]
    actual_columns = _inspector().get_columns(table_name)
    expected_names = [column_name for column_name, _column_type, _nullable in expected_columns]
    actual_names = [column["name"] for column in actual_columns]
    if actual_names != expected_names:
        raise RuntimeError(
            f"Cannot safely converge {table_name}; columns {actual_names} do not match "
            f"{expected_names}"
        )

    for actual, (_column_name, expected_type, expected_nullable) in zip(
        actual_columns,
        expected_columns,
        strict=True,
    ):
        if not _types_are_identical(actual["type"], expected_type):
            raise RuntimeError(
                f"Cannot safely converge {table_name}.{actual['name']}; type "
                f"{actual['type']} does not match {expected_type}"
            )
        if actual["nullable"] is not expected_nullable:
            raise RuntimeError(
                f"Cannot safely converge {table_name}.{actual['name']}; nullable="
                f"{actual['nullable']} does not match {expected_nullable}"
            )
        if actual.get("default") is not None:
            raise RuntimeError(
                f"Cannot safely converge {table_name}.{actual['name']}; unexpected server "
                f"default {actual['default']}"
            )

    primary_key = _inspector().get_pk_constraint(table_name)
    expected_primary_key = PRIMARY_KEYS[table_name]
    actual_primary_key = (
        primary_key.get("name"),
        tuple(primary_key.get("constrained_columns") or []),
    )
    if actual_primary_key != expected_primary_key:
        raise RuntimeError(
            f"Cannot safely converge {table_name}; primary key {actual_primary_key} does not "
            f"match {expected_primary_key}"
        )

    expected_foreign_keys = set(FOREIGN_KEYS[table_name])
    actual_foreign_keys = _foreign_key_contracts(table_name)
    if actual_foreign_keys != expected_foreign_keys:
        raise RuntimeError(
            f"Cannot safely converge {table_name}; foreign keys {actual_foreign_keys} do not "
            f"match {expected_foreign_keys}"
        )

    unique_constraints = _inspector().get_unique_constraints(table_name)
    if unique_constraints:
        raise RuntimeError(
            f"Cannot safely converge {table_name}; unexpected unique constraints "
            f"{unique_constraints}"
        )
    check_constraints = _inspector().get_check_constraints(table_name)
    if check_constraints:
        raise RuntimeError(
            f"Cannot safely converge {table_name}; unexpected check constraints {check_constraints}"
        )


def _preflight_indexes(table_name: str) -> None:
    expected_by_name = {
        index_name: (columns, unique) for index_name, columns, unique in INDEXES[table_name]
    }
    actual_by_name = {index["name"]: index for index in _inspector().get_indexes(table_name)}
    unexpected = set(actual_by_name) - set(expected_by_name)
    if unexpected:
        raise RuntimeError(
            f"Cannot safely converge {table_name}; unexpected indexes: "
            f"{', '.join(sorted(unexpected))}"
        )

    for index_name, index in actual_by_name.items():
        actual = (tuple(index.get("column_names") or []), bool(index.get("unique")))
        expected = expected_by_name[index_name]
        if actual != expected:
            raise RuntimeError(
                f"Cannot safely converge {table_name}; index {index_name} has contract "
                f"{actual}, expected {expected}"
            )

    table = op.get_bind().dialect.identifier_preparer.quote(table_name)
    for index_name, columns, unique in INDEXES[table_name]:
        if index_name in actual_by_name or not unique:
            continue
        quoted_columns = ", ".join(
            op.get_bind().dialect.identifier_preparer.quote(column) for column in columns
        )
        duplicate = op.get_bind().execute(
            sa.text(f"SELECT 1 FROM {table} GROUP BY {quoted_columns} HAVING COUNT(*) > 1 LIMIT 1")
        )
        if duplicate.first() is not None:
            raise RuntimeError(
                f"Cannot safely create unique index {index_name}; {table_name} contains "
                "duplicate values"
            )


def _create_tables() -> None:
    op.create_table(
        "mutx_runs",
        *_columns("mutx_runs"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_mutx_runs_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mutx_runs"),
    )
    op.create_table(
        "mutx_steps",
        *_columns("mutx_steps"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["mutx_runs.id"],
            name="fk_mutx_steps_run_id_mutx_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mutx_steps"),
    )
    op.create_table(
        "mutx_costs",
        *_columns("mutx_costs"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["mutx_runs.id"],
            name="fk_mutx_costs_run_id_mutx_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mutx_costs"),
    )
    op.create_table(
        "mutx_provenance",
        *_columns("mutx_provenance"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["mutx_runs.id"],
            name="fk_mutx_provenance_run_id_mutx_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mutx_provenance"),
    )
    op.create_table(
        "mutx_eval_results",
        *_columns("mutx_eval_results"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["mutx_runs.id"],
            name="fk_mutx_eval_results_run_id_mutx_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mutx_eval_results"),
    )


def _ensure_indexes(table_name: str) -> None:
    existing_names = {index["name"] for index in _inspector().get_indexes(table_name)}
    for index_name, columns, unique in INDEXES[table_name]:
        if index_name not in existing_names:
            op.create_index(index_name, table_name, list(columns), unique=unique)


def upgrade() -> None:
    if not _has_table("users"):
        raise RuntimeError("Cannot provision MUTX observability before the users table exists")

    existing_tables = {table_name for table_name in TABLE_ORDER if _has_table(table_name)}
    for table_name in existing_tables:
        _validate_existing_table(table_name)
        _preflight_indexes(table_name)

    if not existing_tables:
        _create_tables()
    else:
        missing_tables = set(TABLE_ORDER) - existing_tables
        if missing_tables:
            raise RuntimeError(
                "Cannot safely converge a partial MUTX observability table family; missing: "
                f"{', '.join(sorted(missing_tables))}"
            )

    for table_name in TABLE_ORDER:
        _ensure_indexes(table_name)


def downgrade() -> None:
    for table_name in reversed(TABLE_ORDER):
        if not _has_table(table_name):
            continue
        existing_indexes = {index["name"] for index in _inspector().get_indexes(table_name)}
        for index_name, _columns, _unique in reversed(INDEXES[table_name]):
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=table_name)
        op.drop_table(table_name)
