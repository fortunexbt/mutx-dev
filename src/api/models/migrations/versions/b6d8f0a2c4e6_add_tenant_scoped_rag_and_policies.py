"""Add durable tenant-scoped RAG and policy storage.

Revision ID: b6d8f0a2c4e6
Revises: a5c7e9f1b3d5
Create Date: 2026-07-28

This is also a convergence migration for databases whose Alembic stamp moved
forward while an earlier draft of these tables was only partially provisioned.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b6d8f0a2c4e6"
down_revision: Union[str, None] = "a5c7e9f1b3d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_EMBEDDING_BACKEND = "legacy_unknown"


def _bind():
    return op.get_bind()


def _inspector():
    return sa.inspect(_bind())


def _quote(identifier: str) -> str:
    return _bind().dialect.identifier_preparer.quote(identifier)


def _byte_length_expression(column: str) -> str:
    if _bind().dialect.name == "sqlite":
        return f"length(CAST({column} AS BLOB))"
    return f"octet_length(CAST({column} AS TEXT))"


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _columns(table_name: str) -> dict[str, dict]:
    if not _has_table(table_name):
        return {}
    return {column["name"]: column for column in _inspector().get_columns(table_name)}


def _table_has_rows(table_name: str) -> bool:
    table = _quote(table_name)
    return _bind().execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() is not None


def _has_null(table_name: str, column_name: str) -> bool:
    table = _quote(table_name)
    column = _quote(column_name)
    statement = sa.text(f"SELECT 1 FROM {table} WHERE {column} IS NULL LIMIT 1")
    return _bind().execute(statement).first() is not None


def _has_duplicate(table_name: str, column_names: list[str]) -> bool:
    table = _quote(table_name)
    columns = ", ".join(_quote(column_name) for column_name in column_names)
    statement = sa.text(f"SELECT 1 FROM {table} GROUP BY {columns} HAVING COUNT(*) > 1 LIMIT 1")
    return _bind().execute(statement).first() is not None


def _types_are_compatible(
    actual: sa.types.TypeEngine,
    expected: sa.types.TypeEngine,
) -> bool:
    if isinstance(expected, sa.Uuid):
        return isinstance(actual, sa.Uuid) or (
            _bind().dialect.name == "sqlite" and isinstance(actual, sa.String)
        )
    if isinstance(expected, sa.JSON):
        return isinstance(actual, sa.JSON)
    if isinstance(expected, sa.Boolean):
        return isinstance(actual, sa.Boolean)
    if isinstance(expected, sa.Integer):
        return isinstance(actual, sa.Integer) and not isinstance(actual, sa.Boolean)
    if isinstance(expected, sa.DateTime):
        return isinstance(actual, sa.DateTime)
    if isinstance(expected, sa.Text):
        return isinstance(actual, sa.String)
    if isinstance(expected, sa.String):
        if not isinstance(actual, sa.String):
            return False
        actual_length = getattr(actual, "length", None)
        expected_length = getattr(expected, "length", None)
        return actual_length is None or expected_length is None or actual_length >= expected_length
    return actual._type_affinity is expected._type_affinity


def _ensure_required_columns(
    table_name: str,
    definitions: list[tuple[str, sa.types.TypeEngine, str | None]],
) -> None:
    """Add absent required columns without inventing unsafe identity values."""
    existing = _columns(table_name)
    has_rows = _table_has_rows(table_name)
    missing_columns: list[tuple[str, sa.types.TypeEngine, str | None]] = []
    make_not_null: list[tuple[str, sa.types.TypeEngine, str | None]] = []

    # Validate the complete repair before the first DDL statement. SQLite uses
    # non-transactional DDL here, so discovering an unsafe identity column only
    # after adding an earlier convenience column would leave a half-repaired DB.
    for column_name, column_type, backfill_sql in definitions:
        current = existing.get(column_name)
        if current is not None and not _types_are_compatible(current["type"], column_type):
            raise RuntimeError(
                f"Column '{table_name}.{column_name}' has incompatible type "
                f"'{current['type']}'; expected a type compatible with '{column_type}'"
            )
        if current is None:
            if has_rows and backfill_sql is None:
                raise RuntimeError(
                    f"Cannot safely add required column '{table_name}.{column_name}' to a "
                    "populated partial table. Back up and repair that identity-bearing "
                    "column before rerunning the migration."
                )
            missing_columns.append((column_name, column_type, backfill_sql))
        elif current.get("nullable", True):
            if backfill_sql is None and _has_null(table_name, column_name):
                raise RuntimeError(
                    f"Cannot make '{table_name}.{column_name}' required while NULL values exist"
                )
            make_not_null.append((column_name, column_type, backfill_sql))

    for column_name, column_type, backfill_sql in missing_columns:
        op.add_column(
            table_name,
            sa.Column(column_name, column_type, nullable=True),
        )
        make_not_null.append((column_name, column_type, backfill_sql))

    for column_name, _column_type, backfill_sql in make_not_null:
        if backfill_sql is not None:
            table = _quote(table_name)
            column = _quote(column_name)
            op.execute(
                sa.text(f"UPDATE {table} SET {column} = {backfill_sql} WHERE {column} IS NULL")
            )
        if _has_null(table_name, column_name):
            raise RuntimeError(
                f"Cannot make '{table_name}.{column_name}' required while NULL values exist"
            )

    if make_not_null:
        with op.batch_alter_table(table_name) as batch_op:
            for column_name, column_type, _backfill_sql in make_not_null:
                batch_op.alter_column(
                    column_name,
                    existing_type=column_type,
                    nullable=False,
                )


def _has_primary_key(table_name: str, column_names: list[str]) -> bool:
    constrained = _inspector().get_pk_constraint(table_name).get("constrained_columns") or []
    if constrained and tuple(constrained) != tuple(column_names):
        raise RuntimeError(
            f"Table '{table_name}' has incompatible primary key columns "
            f"{tuple(constrained)}; expected {tuple(column_names)}"
        )
    return tuple(constrained) == tuple(column_names)


def _has_unique_constraint(
    table_name: str,
    constraint_name: str,
    column_names: list[str],
) -> bool:
    expected = tuple(column_names)
    for constraint in _inspector().get_unique_constraints(table_name):
        actual = tuple(constraint.get("column_names") or [])
        if constraint.get("name") == constraint_name and actual != expected:
            raise RuntimeError(
                f"Constraint '{constraint_name}' exists with incompatible columns {actual}; "
                f"expected {expected}"
            )
        if actual == expected:
            return True
    for index in _inspector().get_indexes(table_name):
        actual = tuple(index.get("column_names") or [])
        if index.get("name") == constraint_name and (not index.get("unique") or actual != expected):
            raise RuntimeError(
                f"Unique object '{constraint_name}' exists with incompatible columns {actual}; "
                f"expected {expected}"
            )
        if index.get("unique") and actual == expected:
            return True
    return False


def _has_foreign_key(
    table_name: str,
    constraint_name: str,
    constrained_columns: list[str],
    referred_table: str,
    referred_columns: list[str],
) -> bool:
    expected = (tuple(constrained_columns), referred_table, tuple(referred_columns))
    for foreign_key in _inspector().get_foreign_keys(table_name):
        actual = (
            tuple(foreign_key.get("constrained_columns") or []),
            foreign_key.get("referred_table"),
            tuple(foreign_key.get("referred_columns") or []),
        )
        if foreign_key.get("name") == constraint_name and actual != expected:
            raise RuntimeError(
                f"Foreign key '{constraint_name}' exists with incompatible identity {actual}; "
                f"expected {expected}"
            )
        if actual == expected:
            return True
    return False


def _validate_unique_data(table_name: str, column_names: list[str]) -> None:
    for column_name in column_names:
        if _has_null(table_name, column_name):
            raise RuntimeError(
                f"Cannot add a required uniqueness constraint to '{table_name}' while "
                f"'{column_name}' contains NULL values"
            )
    if _has_duplicate(table_name, column_names):
        joined = ", ".join(column_names)
        raise RuntimeError(
            f"Cannot add uniqueness constraint on '{table_name}({joined})' while duplicate "
            "values exist; existing rows were left unchanged"
        )


def _validate_foreign_key_data(
    table_name: str,
    constrained_columns: list[str],
    referred_table: str,
    referred_columns: list[str],
) -> None:
    if not _has_table(referred_table):
        raise RuntimeError(
            f"Cannot repair '{table_name}' because required table '{referred_table}' is missing"
        )

    child = _quote(table_name)
    parent = _quote(referred_table)
    comparisons = " AND ".join(
        f"child.{_quote(local)} = parent.{_quote(remote)}"
        for local, remote in zip(constrained_columns, referred_columns, strict=True)
    )
    present = " AND ".join(
        f"child.{_quote(column_name)} IS NOT NULL" for column_name in constrained_columns
    )
    missing = f"parent.{_quote(referred_columns[0])} IS NULL"
    statement = sa.text(
        f"SELECT 1 FROM {child} AS child LEFT JOIN {parent} AS parent ON {comparisons} "
        f"WHERE {present} AND {missing} LIMIT 1"
    )
    if _bind().execute(statement).first() is not None:
        raise RuntimeError(
            f"Cannot add foreign key from '{table_name}' to '{referred_table}' while orphaned "
            "rows exist; existing rows were left unchanged"
        )


def _ensure_constraints(
    table_name: str,
    *,
    primary_key: tuple[str, list[str]],
    unique_constraints: list[tuple[str, list[str]]],
    foreign_keys: list[tuple[str, list[str], str, list[str], str | None]],
) -> None:
    missing_primary_key = not _has_primary_key(table_name, primary_key[1])
    missing_unique = [
        constraint
        for constraint in unique_constraints
        if not _has_unique_constraint(table_name, constraint[0], constraint[1])
    ]
    missing_foreign_keys = [
        foreign_key
        for foreign_key in foreign_keys
        if not _has_foreign_key(
            table_name,
            foreign_key[0],
            foreign_key[1],
            foreign_key[2],
            foreign_key[3],
        )
    ]

    if missing_primary_key:
        _validate_unique_data(table_name, primary_key[1])
    for _name, column_names in missing_unique:
        _validate_unique_data(table_name, column_names)
    for _name, local_columns, remote_table, remote_columns, _ondelete in missing_foreign_keys:
        _validate_foreign_key_data(
            table_name,
            local_columns,
            remote_table,
            remote_columns,
        )

    if not (missing_primary_key or missing_unique or missing_foreign_keys):
        return

    with op.batch_alter_table(table_name) as batch_op:
        if missing_primary_key:
            batch_op.create_primary_key(primary_key[0], primary_key[1])
        for name, column_names in missing_unique:
            batch_op.create_unique_constraint(name, column_names)
        for name, local_columns, remote_table, remote_columns, ondelete in missing_foreign_keys:
            batch_op.create_foreign_key(
                name,
                remote_table,
                local_columns,
                remote_columns,
                ondelete=ondelete,
            )


def _ensure_index(
    table_name: str,
    index_name: str,
    column_names: list[str],
) -> None:
    expected = tuple(column_names)
    for index in _inspector().get_indexes(table_name):
        actual = tuple(index.get("column_names") or [])
        if index.get("name") == index_name and actual != expected:
            raise RuntimeError(
                f"Index '{index_name}' exists with incompatible columns {actual}; expected "
                f"{expected}"
            )
        if index.get("name") == index_name or actual == expected:
            return
    op.create_index(index_name, table_name, column_names, unique=False)


def _ensure_rag_indexes() -> None:
    if not _has_table("rag_indexes"):
        op.create_table(
            "rag_indexes",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("owner_id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("embedding_backend", sa.String(length=40), nullable=False),
            sa.Column("embedding_model", sa.String(length=120), nullable=False),
            sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("id", "owner_id", name="uq_rag_indexes_id_owner"),
            sa.UniqueConstraint("owner_id", "name", name="uq_rag_indexes_owner_name"),
        )
    else:
        _ensure_required_columns(
            "rag_indexes",
            [
                ("id", sa.UUID(), None),
                ("owner_id", sa.UUID(), None),
                ("name", sa.String(length=255), None),
                (
                    "embedding_backend",
                    sa.String(length=40),
                    f"'{LEGACY_EMBEDDING_BACKEND}'",
                ),
                ("embedding_model", sa.String(length=120), None),
                ("embedding_dimensions", sa.Integer(), None),
                ("created_at", sa.DateTime(timezone=True), "CURRENT_TIMESTAMP"),
                ("updated_at", sa.DateTime(timezone=True), "CURRENT_TIMESTAMP"),
            ],
        )

    _ensure_constraints(
        "rag_indexes",
        primary_key=("pk_rag_indexes", ["id"]),
        unique_constraints=[
            ("uq_rag_indexes_id_owner", ["id", "owner_id"]),
            ("uq_rag_indexes_owner_name", ["owner_id", "name"]),
        ],
        foreign_keys=[
            ("fk_rag_indexes_owner", ["owner_id"], "users", ["id"], None),
        ],
    )
    _ensure_index("rag_indexes", "ix_rag_indexes_owner_id", ["owner_id"])
    _ensure_index(
        "rag_indexes",
        "ix_rag_indexes_owner_created_at",
        ["owner_id", "created_at"],
    )


def _ensure_rag_documents() -> None:
    if not _has_table("rag_documents"):
        op.create_table(
            "rag_documents",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("owner_id", sa.UUID(), nullable=False),
            sa.Column("index_id", sa.UUID(), nullable=False),
            sa.Column("external_id", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("extra_metadata", sa.JSON(), nullable=False),
            sa.Column("embedding", sa.JSON(), nullable=False),
            sa.Column("storage_bytes", sa.BigInteger(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["index_id", "owner_id"],
                ["rag_indexes.id", "rag_indexes.owner_id"],
                name="fk_rag_documents_index_owner",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "index_id",
                "external_id",
                name="uq_rag_documents_index_external_id",
            ),
        )
    else:
        _ensure_required_columns(
            "rag_documents",
            [
                ("id", sa.UUID(), None),
                ("owner_id", sa.UUID(), None),
                ("index_id", sa.UUID(), None),
                ("external_id", sa.String(length=255), None),
                ("content", sa.Text(), None),
                ("extra_metadata", sa.JSON(), "'{}'"),
                ("embedding", sa.JSON(), None),
                ("storage_bytes", sa.BigInteger(), "0"),
                ("created_at", sa.DateTime(timezone=True), "CURRENT_TIMESTAMP"),
            ],
        )

        documents = _quote("rag_documents")
        storage_bytes = _quote("storage_bytes")
        external_id = _quote("external_id")
        content = _quote("content")
        extra_metadata = _quote("extra_metadata")
        embedding = _quote("embedding")
        op.execute(
            sa.text(
                f"UPDATE {documents} SET {storage_bytes} = "
                f"{_byte_length_expression(external_id)} + "
                f"{_byte_length_expression(content)} + "
                f"{_byte_length_expression(extra_metadata)} + "
                f"(8 * json_array_length({embedding})) "
                f"WHERE {storage_bytes} = 0"
            )
        )

    _ensure_constraints(
        "rag_documents",
        primary_key=("pk_rag_documents", ["id"]),
        unique_constraints=[
            ("uq_rag_documents_index_external_id", ["index_id", "external_id"]),
        ],
        foreign_keys=[
            ("fk_rag_documents_owner", ["owner_id"], "users", ["id"], None),
            (
                "fk_rag_documents_index_owner",
                ["index_id", "owner_id"],
                "rag_indexes",
                ["id", "owner_id"],
                "CASCADE",
            ),
        ],
    )
    _ensure_index("rag_documents", "ix_rag_documents_owner_id", ["owner_id"])
    _ensure_index(
        "rag_documents",
        "ix_rag_documents_owner_index",
        ["owner_id", "index_id"],
    )


def _ensure_stored_policies() -> None:
    if not _has_table("stored_policies"):
        op.create_table(
            "stored_policies",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("owner_id", sa.UUID(), nullable=False),
            sa.Column("policy_id", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("rules", sa.JSON(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_id",
                "policy_id",
                name="uq_stored_policies_owner_policy_id",
            ),
            sa.UniqueConstraint("owner_id", "name", name="uq_stored_policies_owner_name"),
        )
    else:
        _ensure_required_columns(
            "stored_policies",
            [
                ("id", sa.UUID(), None),
                ("owner_id", sa.UUID(), None),
                ("policy_id", sa.String(length=255), None),
                ("name", sa.String(length=255), None),
                ("rules", sa.JSON(), "'[]'"),
                ("enabled", sa.Boolean(), "1"),
                ("version", sa.Integer(), "1"),
                ("created_at", sa.DateTime(timezone=True), "CURRENT_TIMESTAMP"),
                ("updated_at", sa.DateTime(timezone=True), "CURRENT_TIMESTAMP"),
            ],
        )

    _ensure_constraints(
        "stored_policies",
        primary_key=("pk_stored_policies", ["id"]),
        unique_constraints=[
            ("uq_stored_policies_owner_policy_id", ["owner_id", "policy_id"]),
            ("uq_stored_policies_owner_name", ["owner_id", "name"]),
        ],
        foreign_keys=[
            ("fk_stored_policies_owner", ["owner_id"], "users", ["id"], None),
        ],
    )
    _ensure_index("stored_policies", "ix_stored_policies_owner_id", ["owner_id"])
    _ensure_index(
        "stored_policies",
        "ix_stored_policies_owner_enabled",
        ["owner_id", "enabled"],
    )


def upgrade() -> None:
    if not _has_table("users"):
        raise RuntimeError(
            "Cannot provision tenant-scoped RAG and policies before the users table exists"
        )
    _ensure_rag_indexes()
    _ensure_rag_documents()
    _ensure_stored_policies()


def downgrade() -> None:
    # These objects may have existed before this convergence revision and can
    # contain live tenant data. Their provenance is unknowable, so destructive
    # rollback would be unsafe; a later forward migration may retire them.
    pass
