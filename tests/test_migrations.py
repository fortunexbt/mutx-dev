import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = ROOT / "src/api/models/migrations/versions"


def _current_head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def test_alembic_has_single_head():
    config = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()
    assert len(heads) == 1, f"expected one alembic head, found {heads}"
    assert script.get_current_head() == heads[0]


def _load_migration_module(module_name: str, file_name: str):
    module_path = VERSIONS_DIR / file_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_alembic_upgrade(database_url: str) -> None:
    env = os.environ.copy()
    env.update(
        {
            "MUTX_SETTINGS_ENV_FILE": "/dev/null",
            "DATABASE_URL": database_url,
            "ENVIRONMENT": "development",
            "JWT_SECRET": "test-secret-key-that-is-long-enough-32",
            "DATABASE_REQUIRED_ON_STARTUP": "false",
            "BACKGROUND_MONITOR_ENABLED": "false",
            "ENABLE_RAG_API": "false",
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _stamp_database(connection, revision: str) -> None:
    connection.execute(
        sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
    )
    connection.execute(
        sa.text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
        {"revision": revision},
    )


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _index_contracts(
    inspector,
    table_name: str,
) -> set[tuple[str, tuple[str, ...], bool]]:
    return {
        (
            index["name"],
            tuple(index.get("column_names") or []),
            bool(index.get("unique")),
        )
        for index in inspector.get_indexes(table_name)
    }


def _unique_constraint_columns(inspector, table_name: str) -> set[tuple[str, ...]]:
    return {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    }


def _unique_constraint_contracts(
    inspector,
    table_name: str,
) -> set[tuple[str | None, tuple[str, ...]]]:
    return {
        (
            constraint.get("name"),
            tuple(constraint.get("column_names") or []),
        )
        for constraint in inspector.get_unique_constraints(table_name)
    }


def _foreign_key_targets(
    inspector, table_name: str
) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }


def _foreign_key_contracts(
    inspector,
    table_name: str,
) -> set[tuple[str | None, tuple[str, ...], str, tuple[str, ...], str | None]]:
    return {
        (
            foreign_key.get("name"),
            tuple(foreign_key.get("constrained_columns") or []),
            foreign_key["referred_table"],
            tuple(foreign_key.get("referred_columns") or []),
            (foreign_key.get("options") or {}).get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }


def _column_type_contract(column_type) -> tuple[str, int | None]:
    if isinstance(column_type, sa.UUID) or (
        isinstance(column_type, sa.CHAR) and column_type.length == 36
    ):
        return ("uuid", None)
    if isinstance(column_type, sa.DateTime):
        return ("datetime", None)
    if isinstance(column_type, sa.Text):
        return ("text", None)
    if isinstance(column_type, sa.String):
        return ("string", column_type.length)
    if isinstance(column_type, sa.Boolean):
        return ("boolean", None)
    if isinstance(column_type, sa.Integer):
        return ("integer", None)
    if isinstance(column_type, sa.Float):
        return ("float", None)
    raise AssertionError(f"unexpected reflected column type: {column_type!r}")


def _column_schema_contracts(
    inspector,
    table_name: str,
) -> dict[str, tuple[tuple[str, int | None], bool, str | None]]:
    return {
        column["name"]: (
            _column_type_contract(column["type"]),
            bool(column["nullable"]),
            column.get("default"),
        )
        for column in inspector.get_columns(table_name)
    }


MUTX_OBSERVABILITY_COLUMN_CONTRACTS = {
    "mutx_runs": {
        "id": (("string", 64), False, None),
        "agent_id": (("string", 255), False, None),
        "user_id": (("uuid", None), False, None),
        "agent_name": (("string", 255), True, None),
        "model": (("string", 100), True, None),
        "provider": (("string", 50), True, None),
        "runtime": (("string", 100), True, None),
        "runtime_version": (("string", 50), True, None),
        "trigger": (("string", 50), True, None),
        "parent_run_id": (("string", 64), True, None),
        "task_id": (("string", 255), True, None),
        "status": (("string", 50), False, None),
        "outcome": (("string", 50), True, None),
        "started_at": (("datetime", None), False, None),
        "ended_at": (("datetime", None), True, None),
        "duration_ms": (("integer", None), True, None),
        "tools_available": (("text", None), True, None),
        "git_branch": (("string", 255), True, None),
        "git_commit": (("string", 40), True, None),
        "workspace_id": (("string", 255), True, None),
        "tags": (("text", None), True, None),
        "run_metadata": (("text", None), True, None),
        "error": (("text", None), True, None),
        "created_at": (("datetime", None), False, None),
    },
    "mutx_steps": {
        "id": (("string", 64), False, None),
        "run_id": (("string", 64), False, None),
        "type": (("string", 50), False, None),
        "tool_name": (("string", 255), True, None),
        "mcp_server": (("string", 255), True, None),
        "input_preview": (("text", None), True, None),
        "output_preview": (("text", None), True, None),
        "success": (("boolean", None), True, None),
        "error": (("text", None), True, None),
        "started_at": (("datetime", None), False, None),
        "ended_at": (("datetime", None), True, None),
        "duration_ms": (("integer", None), True, None),
        "tokens_used": (("integer", None), True, None),
        "sequence": (("integer", None), False, None),
        "step_metadata": (("text", None), True, None),
        "created_at": (("datetime", None), False, None),
    },
    "mutx_costs": {
        "id": (("uuid", None), False, None),
        "run_id": (("string", 64), False, None),
        "input_tokens": (("integer", None), False, None),
        "output_tokens": (("integer", None), False, None),
        "cache_read_tokens": (("integer", None), True, None),
        "cache_write_tokens": (("integer", None), True, None),
        "total_tokens": (("integer", None), True, None),
        "cost_usd": (("float", None), True, None),
        "model": (("string", 100), True, None),
        "created_at": (("datetime", None), False, None),
    },
    "mutx_provenance": {
        "id": (("uuid", None), False, None),
        "run_id": (("string", 64), False, None),
        "run_hash": (("string", 64), False, None),
        "parent_run_hash": (("string", 64), True, None),
        "lineage": (("text", None), True, None),
        "model_version": (("string", 100), True, None),
        "config_hash": (("string", 64), True, None),
        "runtime": (("string", 100), True, None),
        "signed_by": (("string", 255), True, None),
        "signature": (("text", None), True, None),
        "created_at": (("datetime", None), False, None),
    },
    "mutx_eval_results": {
        "id": (("uuid", None), False, None),
        "run_id": (("string", 64), False, None),
        "task_type": (("string", 100), True, None),
        "eval_layer": (("string", 100), True, None),
        "eval_pass": (("boolean", None), False, None),
        "score": (("float", None), False, None),
        "expected_outcome": (("text", None), True, None),
        "actual_outcome": (("text", None), True, None),
        "metrics": (("text", None), True, None),
        "regression_from": (("string", 64), True, None),
        "detail": (("text", None), True, None),
        "benchmark_id": (("string", 255), True, None),
        "created_at": (("datetime", None), False, None),
    },
}


def _assert_webhook_schema(inspector) -> None:
    assert {"webhooks", "webhook_delivery_logs"} <= set(inspector.get_table_names())
    assert {
        "id",
        "user_id",
        "name",
        "url",
        "events",
        "secret",
        "is_active",
        "consecutive_failures",
        "created_at",
    } <= _column_names(inspector, "webhooks")
    assert {
        "id",
        "webhook_id",
        "event",
        "payload",
        "status_code",
        "response_body",
        "success",
        "error_message",
        "attempts",
        "duration_ms",
        "parent_delivery_id",
        "created_at",
        "delivered_at",
    } <= _column_names(inspector, "webhook_delivery_logs")
    assert {"ix_webhooks_user_id", "ix_webhooks_is_active"} <= _index_names(inspector, "webhooks")
    assert {"ix_webhook_delivery_logs_webhook_id"} <= _index_names(
        inspector, "webhook_delivery_logs"
    )
    assert inspector.get_pk_constraint("webhooks")["constrained_columns"] == ["id"]
    assert inspector.get_pk_constraint("webhook_delivery_logs")["constrained_columns"] == ["id"]
    assert (("user_id",), "users", ("id",)) in _foreign_key_targets(inspector, "webhooks")
    assert (("webhook_id",), "webhooks", ("id",)) in _foreign_key_targets(
        inspector, "webhook_delivery_logs"
    )


def _assert_scheduler_schema(inspector) -> None:
    assert "scheduled_tasks" in inspector.get_table_names()
    assert {
        "id",
        "owner_id",
        "name",
        "enabled",
        "schedule",
        "interval_seconds",
        "task_type",
        "payload",
        "next_run",
        "status",
        "active_execution_id",
        "claim_expires_at",
        "success_count",
        "failure_count",
        "last_error",
    } <= _column_names(inspector, "scheduled_tasks")
    assert {
        "ix_scheduled_tasks_owner_id",
        "ix_scheduled_tasks_owner_created_at",
        "ix_scheduled_tasks_due",
        "ix_scheduled_tasks_active_execution_id",
        "ix_scheduled_tasks_claim_expires_at",
    } <= _index_names(inspector, "scheduled_tasks")
    assert (("owner_id",), "users", ("id",)) in _foreign_key_targets(inspector, "scheduled_tasks")


def _assert_mutx_observability_schema(inspector) -> None:
    expected_tables = set(MUTX_OBSERVABILITY_COLUMN_CONTRACTS)
    assert expected_tables <= set(inspector.get_table_names())

    expected_indexes = {
        "mutx_runs": {
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
        },
        "mutx_steps": {
            ("ix_mutx_steps_run_id", ("run_id",), False),
            ("ix_mutx_steps_run_sequence", ("run_id", "sequence"), False),
            ("ix_mutx_steps_tool_name", ("tool_name",), False),
            ("ix_mutx_steps_type", ("type",), False),
        },
        "mutx_costs": {("ix_mutx_costs_run_id", ("run_id",), True)},
        "mutx_provenance": {
            ("ix_mutx_provenance_run_hash", ("run_hash",), False),
            ("ix_mutx_provenance_run_id", ("run_id",), True),
        },
        "mutx_eval_results": {
            ("ix_mutx_eval_results_run_id", ("run_id",), True),
            ("ix_mutx_eval_results_run_pass", ("run_id", "eval_pass"), False),
            ("ix_mutx_eval_results_task_type", ("task_type",), False),
        },
    }
    expected_foreign_keys = {
        "mutx_runs": {
            (
                "fk_mutx_runs_user_id_users",
                ("user_id",),
                "users",
                ("id",),
                None,
            )
        },
        "mutx_steps": {
            (
                "fk_mutx_steps_run_id_mutx_runs",
                ("run_id",),
                "mutx_runs",
                ("id",),
                "CASCADE",
            )
        },
        "mutx_costs": {
            (
                "fk_mutx_costs_run_id_mutx_runs",
                ("run_id",),
                "mutx_runs",
                ("id",),
                "CASCADE",
            )
        },
        "mutx_provenance": {
            (
                "fk_mutx_provenance_run_id_mutx_runs",
                ("run_id",),
                "mutx_runs",
                ("id",),
                "CASCADE",
            )
        },
        "mutx_eval_results": {
            (
                "fk_mutx_eval_results_run_id_mutx_runs",
                ("run_id",),
                "mutx_runs",
                ("id",),
                "CASCADE",
            )
        },
    }

    for table_name, expected_columns in MUTX_OBSERVABILITY_COLUMN_CONTRACTS.items():
        assert _column_schema_contracts(inspector, table_name) == expected_columns
        assert inspector.get_pk_constraint(table_name) == {
            "constrained_columns": ["id"],
            "name": f"pk_{table_name}",
        }
        assert _foreign_key_contracts(inspector, table_name) == expected_foreign_keys[table_name]
        assert _index_contracts(inspector, table_name) == expected_indexes[table_name]
        assert _unique_constraint_contracts(inspector, table_name) == set()
        assert inspector.get_check_constraints(table_name) == []


def test_durable_scheduler_migration_follows_tenant_storage_head():
    module = _load_migration_module(
        "add_durable_scheduler_tasks",
        "c7e9a1b3d5f7_add_durable_scheduler_tasks.py",
    )

    assert module.revision == "c7e9a1b3d5f7"
    assert module.down_revision == "b6d8f0a2c4e6"


def test_mutx_observability_migration_is_the_single_follow_up_head():
    module = _load_migration_module(
        "add_durable_mutx_observability",
        "f0b4d6e8a2c5_add_durable_mutx_observability.py",
    )

    assert module.revision == "f0b4d6e8a2c5"
    assert module.down_revision == "e9a2c4d6f8b0"
    assert _current_head() == module.revision


def test_live_mode_schema_hardening_upgrade_is_idempotent_for_existing_live_schema(monkeypatch):
    module = _load_migration_module(
        "live_mode_schema_hardening",
        "0f4d7b2c9a11_live_mode_schema_hardening.py",
    )

    existing_tables = {
        "agents",
        "agent_logs",
        "commands",
        "deployment_versions",
        "webhook_delivery_logs",
        "waitlist_signups",
        "leads",
        "usage_events",
        "agent_resource_usage",
    }
    existing_columns = {
        ("agents", "api_key"),
        ("agents", "last_heartbeat"),
        ("agent_logs", "meta_data"),
    }
    existing_indexes = {
        "ix_agents_api_key",
        "ix_commands_agent_id",
        "ix_deployment_versions_deployment_id",
        "ix_webhook_delivery_logs_webhook_id",
        "ix_waitlist_signups_email",
        "ix_waitlist_signups_created_at",
        "ix_leads_email",
        "ix_leads_created_at",
        "ix_usage_events_event_type",
        "ix_usage_events_user_id",
        "ix_usage_events_resource_type",
        "ix_usage_events_created_at",
        "ix_agent_resource_usage_agent_id",
    }
    calls: list[tuple] = []

    monkeypatch.setattr(module, "_has_table", lambda table_name: table_name in existing_tables)
    monkeypatch.setattr(
        module,
        "_has_column",
        lambda table_name, column_name: (table_name, column_name) in existing_columns,
    )
    monkeypatch.setattr(
        module,
        "_has_index",
        lambda _table_name, index_name, *_args, **_kwargs: index_name in existing_indexes,
    )
    monkeypatch.setattr(module.op, "f", lambda name: name)
    monkeypatch.setattr(
        module.op,
        "add_column",
        lambda table_name, column: calls.append(("add_column", table_name, column.name)),
    )
    monkeypatch.setattr(
        module.op,
        "create_table",
        lambda table_name, *args, **kwargs: calls.append(("create_table", table_name)),
    )
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda index_name, table_name, columns, unique=False: calls.append(
            ("create_index", index_name, table_name, tuple(columns), unique)
        ),
    )

    module.upgrade()

    assert calls == [
        ("create_table", "refresh_token_sessions"),
        (
            "create_index",
            "ix_refresh_token_sessions_user_id",
            "refresh_token_sessions",
            ("user_id",),
            False,
        ),
        (
            "create_index",
            "ix_refresh_token_sessions_token_jti",
            "refresh_token_sessions",
            ("token_jti",),
            True,
        ),
        (
            "create_index",
            "ix_refresh_token_sessions_family_id",
            "refresh_token_sessions",
            ("family_id",),
            False,
        ),
    ]


def test_repair_live_auth_schema_drift_repairs_missing_objects(monkeypatch):
    module = _load_migration_module(
        "repair_live_auth_schema_drift",
        "8b3a6f1d2c4e_repair_live_auth_schema_drift.py",
    )

    existing_tables = {"agent_logs", "users"}
    existing_columns = set()
    existing_indexes = set()
    calls: list[tuple] = []

    monkeypatch.setattr(module, "_has_table", lambda table_name: table_name in existing_tables)
    monkeypatch.setattr(
        module,
        "_has_column",
        lambda table_name, column_name: (table_name, column_name) in existing_columns,
    )
    monkeypatch.setattr(
        module,
        "_has_index",
        lambda _table_name, index_name, *_args, **_kwargs: index_name in existing_indexes,
    )
    monkeypatch.setattr(module.op, "f", lambda name: name)

    def add_column(table_name, column):
        calls.append(("add_column", table_name, column.name))
        existing_columns.add((table_name, column.name))

    def create_table(table_name, *args, **kwargs):
        calls.append(("create_table", table_name))
        existing_tables.add(table_name)

    def create_index(index_name, table_name, columns, unique=False):
        calls.append(("create_index", index_name, table_name, tuple(columns), unique))
        existing_indexes.add(index_name)

    monkeypatch.setattr(module.op, "add_column", add_column)
    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", create_index)

    module.upgrade()

    assert calls == [
        ("add_column", "agent_logs", "meta_data"),
        ("create_table", "refresh_token_sessions"),
        (
            "create_index",
            "ix_refresh_token_sessions_user_id",
            "refresh_token_sessions",
            ("user_id",),
            False,
        ),
        (
            "create_index",
            "ix_refresh_token_sessions_token_jti",
            "refresh_token_sessions",
            ("token_jti",),
            True,
        ),
        (
            "create_index",
            "ix_refresh_token_sessions_family_id",
            "refresh_token_sessions",
            ("family_id",),
            False,
        ),
    ]


def test_user_settings_migration_uses_uuid_user_foreign_key(monkeypatch):
    module = _load_migration_module(
        "add_user_settings_table",
        "7f3e2c1b4a6d_add_user_settings_table.py",
    )

    captured: dict[str, object] = {}

    def create_table(table_name, *items, **kwargs):
        captured["table_name"] = table_name
        captured["items"] = items

    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(module.op, "f", lambda name: name)

    module.upgrade()

    assert captured["table_name"] == "user_settings"
    columns = {item.name: item for item in captured["items"] if isinstance(item, sa.Column)}

    assert isinstance(columns["id"].type, sa.UUID)
    assert isinstance(columns["user_id"].type, sa.UUID)


def test_webhook_migration_recreates_missing_tables_in_dependency_order(monkeypatch):
    module = _load_migration_module(
        "add_webhook_circuit_breaker",
        "w1b2c3d4e5f6_add_webhook_circuit_breaker_and_delivery_enhancements.py",
    )
    existing_tables: set[str] = {"users"}
    existing_columns: set[tuple[str, str]] = set()
    existing_indexes: set[str] = set()
    calls: list[tuple] = []

    monkeypatch.setattr(module, "_has_table", lambda table_name: table_name in existing_tables)
    monkeypatch.setattr(
        module,
        "_has_column",
        lambda table_name, column_name: (table_name, column_name) in existing_columns,
    )
    monkeypatch.setattr(
        module,
        "_has_index",
        lambda _table_name, index_name, *_args, **_kwargs: index_name in existing_indexes,
    )
    monkeypatch.setattr(module, "_webhook_events_type", sa.Text)
    monkeypatch.setattr(module.op, "f", lambda name: name)

    def create_table(table_name, *items, **_kwargs):
        calls.append(("create_table", table_name))
        existing_tables.add(table_name)
        existing_columns.update(
            (table_name, item.name) for item in items if isinstance(item, sa.Column)
        )

    def create_index(index_name, table_name, columns, unique=False):
        calls.append(("create_index", index_name, table_name, tuple(columns), unique))
        existing_indexes.add(index_name)

    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", create_index)
    monkeypatch.setattr(
        module.op,
        "add_column",
        lambda table_name, column: calls.append(("add_column", table_name, column.name)),
    )

    module.upgrade()

    assert calls == [
        ("create_table", "webhooks"),
        ("create_index", "ix_webhooks_user_id", "webhooks", ("user_id",), False),
        ("create_index", "ix_webhooks_is_active", "webhooks", ("is_active",), False),
        ("create_table", "webhook_delivery_logs"),
        (
            "create_index",
            "ix_webhook_delivery_logs_webhook_id",
            "webhook_delivery_logs",
            ("webhook_id",),
            False,
        ),
    ]


def test_api_key_prefix_migration_skips_missing_parent_table(monkeypatch):
    module = _load_migration_module(
        "add_api_key_prefix_indexes",
        "t2c4d6e8f0a1_add_api_key_prefix_indexes.py",
    )
    existing_tables = {"agents"}
    existing_columns: set[tuple[str, str]] = set()
    existing_indexes: set[str] = set()
    calls: list[tuple] = []

    monkeypatch.setattr(module, "_has_table", lambda table_name: table_name in existing_tables)
    monkeypatch.setattr(
        module,
        "_has_column",
        lambda table_name, column_name: (table_name, column_name) in existing_columns,
    )
    monkeypatch.setattr(
        module,
        "_has_index",
        lambda _table_name, index_name, *_args, **_kwargs: index_name in existing_indexes,
    )
    monkeypatch.setattr(module.op, "f", lambda name: name)
    monkeypatch.setattr(
        module.op,
        "add_column",
        lambda table_name, column: calls.append(("add_column", table_name, column.name)),
    )
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda index_name, table_name, columns, unique=False: calls.append(
            ("create_index", index_name, table_name, tuple(columns), unique)
        ),
    )

    module.upgrade()

    assert calls == [
        ("add_column", "agents", "api_key_prefix"),
        (
            "create_index",
            "ix_agents_api_key_prefix",
            "agents",
            ("api_key_prefix",),
            False,
        ),
    ]


def test_forward_convergence_migration_is_idempotent_for_current_schema(monkeypatch):
    module = _load_migration_module(
        "converge_webhook_and_api_key_prefix_repairs",
        "e3c5a7b9d1f2_converge_webhook_and_api_key_prefix_repairs.py",
    )
    existing_tables = {"users", "webhooks", "webhook_delivery_logs", "api_keys", "agents"}
    existing_columns = {
        ("webhooks", "name"),
        ("webhooks", "consecutive_failures"),
        ("webhook_delivery_logs", "duration_ms"),
        ("webhook_delivery_logs", "parent_delivery_id"),
        ("api_keys", "key_prefix"),
        ("agents", "api_key_prefix"),
    }
    existing_indexes = {
        "ix_webhooks_user_id",
        "ix_webhooks_is_active",
        "ix_webhook_delivery_logs_webhook_id",
        "ix_api_keys_key_prefix",
        "ix_agents_api_key_prefix",
    }
    calls: list[tuple] = []

    monkeypatch.setattr(module, "_has_table", lambda table_name: table_name in existing_tables)
    monkeypatch.setattr(
        module,
        "_has_column",
        lambda table_name, column_name: (table_name, column_name) in existing_columns,
    )
    monkeypatch.setattr(
        module,
        "_has_index",
        lambda _table_name, index_name, *_args, **_kwargs: index_name in existing_indexes,
    )
    monkeypatch.setattr(module.op, "f", lambda name: name)
    monkeypatch.setattr(module, "_preflight", lambda: None)
    monkeypatch.setattr(
        module.op, "add_column", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    monkeypatch.setattr(
        module.op, "create_table", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    monkeypatch.setattr(
        module.op, "create_index", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    module.upgrade()
    module.upgrade()

    assert calls == []


def test_alembic_upgrade_repairs_database_already_stamped_at_former_head(tmp_path):
    db_path = tmp_path / "former-head.sqlite3"
    database_url = f"sqlite:///{db_path}"
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            _stamp_database(connection, "c9e1a4b6d8f0")
            connection.execute(sa.text("CREATE TABLE users (id CHAR(36) NOT NULL PRIMARY KEY)"))
            connection.execute(sa.text("CREATE TABLE agents (id CHAR(36) NOT NULL PRIMARY KEY)"))
            connection.execute(sa.text("CREATE TABLE api_keys (id CHAR(36) NOT NULL PRIMARY KEY)"))
    finally:
        engine.dispose()

    _run_alembic_upgrade(database_url)

    engine = sa.create_engine(database_url)
    try:
        inspector = sa.inspect(engine)
        _assert_webhook_schema(inspector)
        assert "api_key_prefix" in _column_names(inspector, "agents")
        assert "key_prefix" in _column_names(inspector, "api_keys")
        assert "ix_agents_api_key_prefix" in _index_names(inspector, "agents")
        assert "ix_api_keys_key_prefix" in _index_names(inspector, "api_keys")
        _assert_scheduler_schema(inspector)
        with engine.connect() as connection:
            assert (
                connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
                == _current_head()
            )
    finally:
        engine.dispose()


def test_persisted_user_roles_migration_is_least_privilege(monkeypatch):
    module = _load_migration_module(
        "add_persisted_user_roles",
        "b8d0f3a1c5e7_add_persisted_user_roles.py",
    )
    captured: dict[str, object] = {}

    def add_column(table_name, column):
        captured["table_name"] = table_name
        captured["column"] = column

    monkeypatch.setattr(module.op, "add_column", add_column)
    monkeypatch.setattr(module, "_roles_column", lambda: None)

    module.upgrade()

    column = captured["column"]
    assert module.down_revision == "a7c9e2f4b6d8"
    assert captured["table_name"] == "users"
    assert column.name == "roles"
    assert isinstance(column.type, sa.JSON)
    assert column.nullable is False
    assert str(column.server_default.arg) == "'[\"VIEWER\"]'"


def test_convergence_migration_converts_last_heartbeat_to_utc_aware_on_postgresql(monkeypatch):
    module = _load_migration_module(
        "converge_runtime_schema_repairs",
        "d91f0a7b6c5e_converge_runtime_schema_repairs.py",
    )

    existing_tables = {"agents", "agent_logs", "refresh_token_sessions", "usage_events", "users"}
    existing_columns = {
        ("agents", "last_heartbeat"),
        ("agent_logs", "meta_data"),
        ("usage_events", "resource_type"),
        ("usage_events", "resource_id"),
        ("usage_events", "credits_used"),
        ("usage_events", "event_metadata"),
    }
    existing_indexes = {
        "ix_refresh_token_sessions_user_id",
        "ix_refresh_token_sessions_token_jti",
        "ix_refresh_token_sessions_family_id",
        "ix_usage_events_event_type",
        "ix_usage_events_user_id",
        "ix_usage_events_resource_type",
        "ix_usage_events_created_at",
    }
    executed: list[str] = []

    monkeypatch.setattr(module, "_has_table", lambda table_name: table_name in existing_tables)
    monkeypatch.setattr(
        module,
        "_has_column",
        lambda table_name, column_name: (table_name, column_name) in existing_columns,
    )
    monkeypatch.setattr(
        module,
        "_has_index",
        lambda _table_name, index_name, *_args, **_kwargs: index_name in existing_indexes,
    )
    monkeypatch.setattr(
        module,
        "_get_column",
        lambda table_name, column_name: (
            {
                "name": column_name,
                "type": sa.DateTime(timezone=False),
            }
            if (table_name, column_name) == ("agents", "last_heartbeat")
            else None
        ),
    )
    monkeypatch.setattr(module, "_is_postgresql", lambda: True)
    monkeypatch.setattr(module.op, "f", lambda name: name)
    monkeypatch.setattr(module.op, "execute", lambda statement: executed.append(str(statement)))

    module.upgrade()

    assert executed == [
        "ALTER TABLE agents ALTER COLUMN last_heartbeat TYPE TIMESTAMP WITH TIME ZONE USING last_heartbeat AT TIME ZONE 'UTC'"
    ]


def test_convergence_migration_repairs_missing_runtime_drift(monkeypatch):
    module = _load_migration_module(
        "converge_runtime_schema_repairs",
        "d91f0a7b6c5e_converge_runtime_schema_repairs.py",
    )

    existing_tables = {"agents", "agent_logs", "usage_events", "users"}
    existing_columns = set()
    existing_indexes = set()
    calls: list[tuple] = []

    monkeypatch.setattr(module, "_has_table", lambda table_name: table_name in existing_tables)
    monkeypatch.setattr(
        module,
        "_has_column",
        lambda table_name, column_name: (table_name, column_name) in existing_columns,
    )
    monkeypatch.setattr(
        module,
        "_has_index",
        lambda _table_name, index_name, *_args, **_kwargs: index_name in existing_indexes,
    )
    monkeypatch.setattr(module, "_get_column", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "_is_postgresql", lambda: False)
    monkeypatch.setattr(module.op, "f", lambda name: name)

    def add_column(table_name, column):
        calls.append(("add_column", table_name, column.name))
        existing_columns.add((table_name, column.name))

    def create_table(table_name, *args, **kwargs):
        calls.append(("create_table", table_name))
        existing_tables.add(table_name)

    def create_index(index_name, table_name, columns, unique=False):
        calls.append(("create_index", index_name, table_name, tuple(columns), unique))
        existing_indexes.add(index_name)

    monkeypatch.setattr(module.op, "add_column", add_column)
    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", create_index)

    module.upgrade()

    assert calls == [
        ("add_column", "agent_logs", "meta_data"),
        ("create_table", "refresh_token_sessions"),
        (
            "create_index",
            "ix_refresh_token_sessions_user_id",
            "refresh_token_sessions",
            ("user_id",),
            False,
        ),
        (
            "create_index",
            "ix_refresh_token_sessions_token_jti",
            "refresh_token_sessions",
            ("token_jti",),
            True,
        ),
        (
            "create_index",
            "ix_refresh_token_sessions_family_id",
            "refresh_token_sessions",
            ("family_id",),
            False,
        ),
        ("add_column", "usage_events", "resource_type"),
        ("add_column", "usage_events", "resource_id"),
        ("add_column", "usage_events", "credits_used"),
        ("add_column", "usage_events", "event_metadata"),
        (
            "create_index",
            "ix_usage_events_event_type",
            "usage_events",
            ("event_type",),
            False,
        ),
        (
            "create_index",
            "ix_usage_events_user_id",
            "usage_events",
            ("user_id",),
            False,
        ),
        (
            "create_index",
            "ix_usage_events_resource_type",
            "usage_events",
            ("resource_type",),
            False,
        ),
        (
            "create_index",
            "ix_usage_events_created_at",
            "usage_events",
            ("created_at",),
            False,
        ),
        ("add_column", "agents", "last_heartbeat"),
    ]


def test_openclaw_repair_migration_repairs_postgresql_enum_and_alert_timestamps(monkeypatch):
    module = _load_migration_module(
        "repair_openclaw_agenttype_and_alert_timestamps",
        "6c5b4a3921de_repair_openclaw_agenttype_and_alert_timestamps.py",
    )

    executed: list[str] = []

    monkeypatch.setattr(module, "_is_postgresql", lambda: True)
    monkeypatch.setattr(module, "_has_postgresql_enum_value", lambda *_args: False)
    monkeypatch.setattr(module, "_has_table", lambda table_name: table_name == "alerts")
    monkeypatch.setattr(
        module,
        "_has_column",
        lambda table_name, column_name: (table_name, column_name) == ("alerts", "resolved_at"),
    )
    monkeypatch.setattr(
        module,
        "_get_column",
        lambda table_name, column_name: (
            {
                "name": column_name,
                "type": sa.DateTime(timezone=False),
            }
            if (table_name, column_name) == ("alerts", "resolved_at")
            else None
        ),
    )
    monkeypatch.setattr(module.op, "execute", lambda statement: executed.append(str(statement)))

    module.upgrade()

    assert executed == [
        "ALTER TYPE agenttype ADD VALUE IF NOT EXISTS 'OPENCLAW'",
        "ALTER TABLE alerts ALTER COLUMN resolved_at TYPE TIMESTAMP WITH TIME ZONE USING resolved_at AT TIME ZONE 'UTC'",
    ]


def test_openclaw_repair_migration_is_noop_when_schema_is_already_current(monkeypatch):
    module = _load_migration_module(
        "repair_openclaw_agenttype_and_alert_timestamps_noop",
        "6c5b4a3921de_repair_openclaw_agenttype_and_alert_timestamps.py",
    )

    executed: list[str] = []

    monkeypatch.setattr(module, "_is_postgresql", lambda: True)
    monkeypatch.setattr(module, "_has_postgresql_enum_value", lambda *_args: True)
    monkeypatch.setattr(module, "_has_table", lambda *_args: True)
    monkeypatch.setattr(module, "_has_column", lambda *_args: True)
    monkeypatch.setattr(
        module,
        "_get_column",
        lambda *_args: {"name": "resolved_at", "type": sa.DateTime(timezone=True)},
    )
    monkeypatch.setattr(module.op, "execute", lambda statement: executed.append(str(statement)))

    module.upgrade()

    assert executed == []


def test_alembic_upgrade_head_succeeds_on_empty_sqlite_database(tmp_path):
    db_path = tmp_path / "empty.sqlite3"
    _run_alembic_upgrade(f"sqlite:///{db_path}")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        inspector = sa.inspect(engine)

        assert {"agents", "agent_logs", "refresh_token_sessions", "usage_events"} <= set(
            inspector.get_table_names()
        )
        assert {
            "oauth_authorization_states",
            "approval_requests",
            "approval_notification_outbox",
            "leads",
            "scheduled_tasks",
            "security_evaluations",
            "security_receipts",
            "telemetry_backend_configs",
        } <= set(inspector.get_table_names())
        assert {"rag_indexes", "rag_documents", "stored_policies"} <= set(
            inspector.get_table_names()
        )
        assert {
            "owner_id",
            "name",
            "embedding_backend",
            "embedding_model",
        } <= _column_names(inspector, "rag_indexes")
        assert {
            "owner_id",
            "index_id",
            "external_id",
            "embedding",
            "storage_bytes",
        } <= _column_names(inspector, "rag_documents")
        assert {"owner_id", "policy_id", "name", "rules"} <= _column_names(
            inspector, "stored_policies"
        )
        assert _unique_constraint_contracts(inspector, "rag_indexes") == {
            ("uq_rag_indexes_id_owner", ("id", "owner_id")),
            ("uq_rag_indexes_owner_name", ("owner_id", "name")),
        }
        assert _unique_constraint_contracts(inspector, "rag_documents") == {
            ("uq_rag_documents_index_external_id", ("index_id", "external_id"))
        }
        assert {
            foreign_key
            for foreign_key in _foreign_key_contracts(inspector, "rag_documents")
            if len(foreign_key[1]) > 1
        } == {
            (
                "fk_rag_documents_index_owner",
                ("index_id", "owner_id"),
                "rag_indexes",
                ("id", "owner_id"),
                "CASCADE",
            )
        }
        assert {"meta_data"} <= _column_names(inspector, "agent_logs")
        assert {"last_heartbeat"} <= _column_names(inspector, "agents")
        assert {"roles"} <= _column_names(inspector, "users")
        assert {
            "original_issued_at",
            "token_nonce",
            "rotation_grace_expires_at",
        } <= _column_names(inspector, "refresh_token_sessions")
        assert {
            "resource_type",
            "resource_id",
            "credits_used",
            "event_metadata",
        } <= _column_names(inspector, "usage_events")
        assert {
            "ix_refresh_token_sessions_user_id",
            "ix_refresh_token_sessions_token_jti",
            "ix_refresh_token_sessions_family_id",
        } <= _index_names(inspector, "refresh_token_sessions")
        assert {
            "ix_usage_events_event_type",
            "ix_usage_events_user_id",
            "ix_usage_events_resource_type",
            "ix_usage_events_created_at",
        } <= _index_names(inspector, "usage_events")
        assert {
            "ix_oauth_authorization_states_state_hash",
            "ix_oauth_authorization_states_expires_at",
        } <= _index_names(inspector, "oauth_authorization_states")
        assert {
            "tier",
            "interest",
            "locale",
            "product_updates_consent",
            "idempotency_key",
            "content_hash",
            "notification_scheduled_at",
        } <= _column_names(inspector, "leads")
        assert {
            "ix_security_evaluations_owner_id",
            "ix_security_evaluations_owner_session_created",
        } <= _index_names(inspector, "security_evaluations")
        assert {
            "ix_security_receipts_owner_id",
            "ix_security_receipts_owner_session_timestamp",
        } <= _index_names(inspector, "security_receipts")
        assert (
            ("evaluation_id", "owner_id"),
            "security_evaluations",
            ("id", "owner_id"),
        ) in _foreign_key_targets(inspector, "security_receipts")
        _assert_webhook_schema(inspector)
        _assert_scheduler_schema(inspector)
        _assert_mutx_observability_schema(inspector)
    finally:
        engine.dispose()


def test_durability_migrations_are_idempotent_on_current_schema(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'current-schema-idempotence.sqlite3'}"
    _run_alembic_upgrade(database_url)
    migration_files = (
        "a7c9e2f4b6d8_add_oauth_authorization_states.py",
        "b8d0f3a1c5e7_add_persisted_user_roles.py",
        "c9e1a4b6d8f0_add_refresh_rotation_overlap.py",
        "e3c5a7b9d1f2_converge_webhook_and_api_key_prefix_repairs.py",
        "f4d6a8c0e2b1_add_durable_approval_workflows.py",
        "a5c7e9f1b3d5_add_durable_lead_intake.py",
        "b6d8f0a2c4e6_add_tenant_scoped_rag_and_policies.py",
        "c7e9a1b3d5f7_add_durable_scheduler_tasks.py",
        "d8f1a3c5e7b9_add_durable_security_evidence.py",
        "e9a2c4d6f8b0_add_tenant_telemetry_backend_configs.py",
        "f0b4d6e8a2c5_add_durable_mutx_observability.py",
    )
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            for position, file_name in enumerate(migration_files):
                module = _load_migration_module(f"idempotence_{position}", file_name)
                monkeypatch.setattr(module, "op", operations)
                module.upgrade()
                module.upgrade()

            assert (
                connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
                == _current_head()
            )
    finally:
        engine.dispose()


def test_durability_downgrades_tolerate_absent_objects(monkeypatch):
    migration_files = (
        "a7c9e2f4b6d8_add_oauth_authorization_states.py",
        "b8d0f3a1c5e7_add_persisted_user_roles.py",
        "c9e1a4b6d8f0_add_refresh_rotation_overlap.py",
        "e3c5a7b9d1f2_converge_webhook_and_api_key_prefix_repairs.py",
        "f4d6a8c0e2b1_add_durable_approval_workflows.py",
        "a5c7e9f1b3d5_add_durable_lead_intake.py",
        "b6d8f0a2c4e6_add_tenant_scoped_rag_and_policies.py",
        "c7e9a1b3d5f7_add_durable_scheduler_tasks.py",
        "d8f1a3c5e7b9_add_durable_security_evidence.py",
        "e9a2c4d6f8b0_add_tenant_telemetry_backend_configs.py",
        "f0b4d6e8a2c5_add_durable_mutx_observability.py",
    )
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            for position, file_name in enumerate(migration_files):
                module = _load_migration_module(f"absent_downgrade_{position}", file_name)
                monkeypatch.setattr(module, "op", operations)
                module.downgrade()
                module.downgrade()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("file_name", "table_name"),
    (
        ("a7c9e2f4b6d8_add_oauth_authorization_states.py", "oauth_authorization_states"),
        ("c7e9a1b3d5f7_add_durable_scheduler_tasks.py", "scheduled_tasks"),
        ("d8f1a3c5e7b9_add_durable_security_evidence.py", "security_evaluations"),
        (
            "e9a2c4d6f8b0_add_tenant_telemetry_backend_configs.py",
            "telemetry_backend_configs",
        ),
        ("f0b4d6e8a2c5_add_durable_mutx_observability.py", "mutx_runs"),
    ),
)
def test_durability_migrations_fail_safe_on_unsafe_partial_tables(
    file_name,
    table_name,
    monkeypatch,
):
    module = _load_migration_module(f"unsafe_partial_{table_name}", file_name)
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE users (id CHAR(36) NOT NULL PRIMARY KEY)"))
            connection.execute(
                sa.text(f'CREATE TABLE "{table_name}" (id CHAR(36) NOT NULL PRIMARY KEY)')
            )
            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(module, "op", operations)

            with pytest.raises(RuntimeError, match=table_name):
                module.upgrade()

            assert set(sa.inspect(connection).get_table_names()) == {table_name, "users"}
    finally:
        engine.dispose()


def test_lead_migration_fails_before_mutating_unsafe_partial_table(monkeypatch):
    module = _load_migration_module(
        "unsafe_partial_leads",
        "a5c7e9f1b3d5_add_durable_lead_intake.py",
    )
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text("CREATE TABLE leads (id CHAR(36) NOT NULL PRIMARY KEY, email TEXT)")
            )
            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(module, "op", operations)

            with pytest.raises(RuntimeError, match="partial leads"):
                module.upgrade()

            assert "tier" not in _column_names(sa.inspect(connection), "leads")
    finally:
        engine.dispose()


def test_tenant_storage_migration_repairs_partial_schema_and_preserves_data(tmp_path):
    db_path = tmp_path / "partial-tenant-storage.sqlite3"
    database_url = f"sqlite:///{db_path}"
    owner_id = "11111111-1111-4111-a111-111111111111"
    index_id = "22222222-2222-4222-a222-222222222222"
    document_id = "33333333-3333-4333-a333-333333333333"
    policy_row_id = "44444444-4444-4444-a444-444444444444"
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            _stamp_database(connection, "a5c7e9f1b3d5")
            connection.execute(sa.text("CREATE TABLE users (id CHAR(36) NOT NULL PRIMARY KEY)"))
            connection.execute(
                sa.text("INSERT INTO users (id) VALUES (:owner_id)"),
                {"owner_id": owner_id},
            )
            connection.execute(
                sa.text(
                    "CREATE TABLE rag_indexes ("
                    "id CHAR(36) NOT NULL PRIMARY KEY, "
                    "owner_id CHAR(36) NOT NULL, "
                    "name VARCHAR(255) NOT NULL, "
                    "embedding_model VARCHAR(120) NOT NULL, "
                    "embedding_dimensions INTEGER NOT NULL, "
                    "created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL"
                    ")"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO rag_indexes "
                    "(id, owner_id, name, embedding_model, embedding_dimensions, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'legacy-index', 'text-embedding-3-small', 1536, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": index_id, "owner_id": owner_id},
            )
            connection.execute(
                sa.text(
                    "CREATE TABLE rag_documents ("
                    "id CHAR(36) NOT NULL PRIMARY KEY, "
                    "owner_id CHAR(36) NOT NULL, "
                    "index_id CHAR(36) NOT NULL, "
                    "external_id VARCHAR(255) NOT NULL, "
                    "content TEXT NOT NULL, "
                    "embedding JSON NOT NULL, "
                    "created_at DATETIME NOT NULL"
                    ")"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO rag_documents "
                    "(id, owner_id, index_id, external_id, content, embedding, created_at) "
                    "VALUES (:id, :owner_id, :index_id, 'legacy-doc', 'preserve me', "
                    "'[0.1, 0.2]', CURRENT_TIMESTAMP)"
                ),
                {"id": document_id, "owner_id": owner_id, "index_id": index_id},
            )
            connection.execute(
                sa.text(
                    "CREATE TABLE stored_policies ("
                    "id CHAR(36) NOT NULL PRIMARY KEY, "
                    "owner_id CHAR(36) NOT NULL, "
                    "policy_id VARCHAR(255) NOT NULL, "
                    "name VARCHAR(255) NOT NULL, "
                    "rules JSON NOT NULL, "
                    "enabled BOOLEAN NOT NULL, "
                    "version INTEGER NOT NULL, "
                    "created_at DATETIME NOT NULL"
                    ")"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO stored_policies "
                    "(id, owner_id, policy_id, name, rules, enabled, version, created_at) "
                    "VALUES (:id, :owner_id, 'legacy-policy-id', 'legacy-policy', '[]', 1, "
                    "7, CURRENT_TIMESTAMP)"
                ),
                {"id": policy_row_id, "owner_id": owner_id},
            )
    finally:
        engine.dispose()

    _run_alembic_upgrade(database_url)

    engine = sa.create_engine(database_url)
    try:
        inspector = sa.inspect(engine)
        assert "embedding_backend" in _column_names(inspector, "rag_indexes")
        assert "extra_metadata" in _column_names(inspector, "rag_documents")
        assert "storage_bytes" in _column_names(inspector, "rag_documents")
        assert "updated_at" in _column_names(inspector, "stored_policies")
        assert _unique_constraint_contracts(inspector, "rag_indexes") == {
            ("uq_rag_indexes_id_owner", ("id", "owner_id")),
            ("uq_rag_indexes_owner_name", ("owner_id", "name")),
        }
        assert _unique_constraint_contracts(inspector, "rag_documents") == {
            ("uq_rag_documents_index_external_id", ("index_id", "external_id"))
        }
        assert {
            ("owner_id", "policy_id"),
            ("owner_id", "name"),
        } <= _unique_constraint_columns(inspector, "stored_policies")
        assert {
            foreign_key
            for foreign_key in _foreign_key_contracts(inspector, "rag_documents")
            if len(foreign_key[1]) > 1
        } == {
            (
                "fk_rag_documents_index_owner",
                ("index_id", "owner_id"),
                "rag_indexes",
                ("id", "owner_id"),
                "CASCADE",
            )
        }
        assert {
            "ix_rag_indexes_owner_id",
            "ix_rag_indexes_owner_created_at",
        } <= _index_names(inspector, "rag_indexes")

        with engine.connect() as connection:
            rag_index = connection.execute(
                sa.text(
                    "SELECT name, embedding_backend, embedding_model, embedding_dimensions "
                    "FROM rag_indexes WHERE id = :id"
                ),
                {"id": index_id},
            ).one()
            document = connection.execute(
                sa.text(
                    "SELECT external_id, content, embedding, extra_metadata, storage_bytes "
                    "FROM rag_documents WHERE id = :id"
                ),
                {"id": document_id},
            ).one()
            policy = connection.execute(
                sa.text(
                    "SELECT policy_id, name, version, updated_at FROM stored_policies "
                    "WHERE id = :id"
                ),
                {"id": policy_row_id},
            ).one()
            revision = connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()

        assert tuple(rag_index) == (
            "legacy-index",
            "legacy_unknown",
            "text-embedding-3-small",
            1536,
        )
        assert document.external_id == "legacy-doc"
        assert document.content == "preserve me"
        assert json.loads(document.embedding) == [0.1, 0.2]
        assert json.loads(document.extra_metadata) == {}
        assert document.storage_bytes > 0
        assert policy.policy_id == "legacy-policy-id"
        assert policy.name == "legacy-policy"
        assert policy.version == 7
        assert policy.updated_at is not None
        assert revision == _current_head()
    finally:
        engine.dispose()


def test_tenant_storage_migration_upgrade_and_downgrade_are_idempotent(
    tmp_path,
    monkeypatch,
):
    module = _load_migration_module(
        "tenant_storage_idempotence",
        "b6d8f0a2c4e6_add_tenant_scoped_rag_and_policies.py",
    )
    database_url = f"sqlite:///{tmp_path / 'tenant-storage-idempotent.sqlite3'}"
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE users (id CHAR(36) NOT NULL PRIMARY KEY)"))
            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(module, "op", operations)

            module.upgrade()
            module.upgrade()
            module.downgrade()
            module.downgrade()

            inspector = sa.inspect(connection)
            assert {"rag_indexes", "rag_documents", "stored_policies"} <= set(
                inspector.get_table_names()
            )
            assert "embedding_backend" in _column_names(inspector, "rag_indexes")
    finally:
        engine.dispose()


def test_tenant_storage_migration_fails_before_inventing_missing_owner_identity(
    tmp_path,
    monkeypatch,
):
    module = _load_migration_module(
        "tenant_storage_fail_safe",
        "b6d8f0a2c4e6_add_tenant_scoped_rag_and_policies.py",
    )
    database_url = f"sqlite:///{tmp_path / 'tenant-storage-unsafe-partial.sqlite3'}"
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE users (id CHAR(36) NOT NULL PRIMARY KEY)"))
            connection.execute(
                sa.text(
                    "CREATE TABLE rag_indexes ("
                    "id CHAR(36) NOT NULL PRIMARY KEY, "
                    "name VARCHAR(255) NOT NULL, "
                    "embedding_model VARCHAR(120) NOT NULL, "
                    "embedding_dimensions INTEGER NOT NULL, "
                    "created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL"
                    ")"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO rag_indexes "
                    "(id, name, embedding_model, embedding_dimensions, created_at, updated_at) "
                    "VALUES ('11111111-1111-4111-a111-111111111111', 'orphaned', "
                    "'text-embedding-3-small', 1536, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(module, "op", operations)

            with pytest.raises(RuntimeError, match="rag_indexes.owner_id"):
                module.upgrade()

            inspector = sa.inspect(connection)
            assert "embedding_backend" not in _column_names(inspector, "rag_indexes")
            assert connection.execute(sa.text("SELECT name FROM rag_indexes")).scalar_one() == (
                "orphaned"
            )
    finally:
        engine.dispose()


def test_tenant_storage_preflights_all_required_columns_before_mutating(
    monkeypatch,
):
    module = _load_migration_module(
        "tenant_storage_complete_preflight",
        "b6d8f0a2c4e6_add_tenant_scoped_rag_and_policies.py",
    )
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE users (id CHAR(36) NOT NULL PRIMARY KEY)"))
            connection.execute(
                sa.text(
                    "CREATE TABLE rag_indexes ("
                    "id CHAR(36) NOT NULL PRIMARY KEY, "
                    "owner_id CHAR(36) NOT NULL, "
                    "name VARCHAR(255) NOT NULL, "
                    "embedding_dimensions INTEGER NOT NULL, "
                    "created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL"
                    ")"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO rag_indexes "
                    "(id, owner_id, name, embedding_dimensions, created_at, updated_at) "
                    "VALUES ('11111111-1111-4111-a111-111111111111', "
                    "'22222222-2222-4222-a222-222222222222', 'unsafe', 1536, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(module, "op", operations)

            with pytest.raises(RuntimeError, match="rag_indexes.embedding_model"):
                module.upgrade()

            assert "embedding_backend" not in _column_names(
                sa.inspect(connection),
                "rag_indexes",
            )
    finally:
        engine.dispose()


def test_alembic_upgrade_repairs_representative_legacy_live_schema(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    legacy_user_id = "11111111-1111-1111-1111-111111111111"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                sa.text("INSERT INTO alembic_version (version_num) VALUES ('8b3a6f1d2c4e')")
            )
            connection.execute(sa.text("CREATE TABLE users (id CHAR(36) NOT NULL PRIMARY KEY)"))
            connection.execute(
                sa.text("INSERT INTO users (id) VALUES (:user_id)"),
                {"user_id": legacy_user_id},
            )
            connection.execute(
                sa.text(
                    "CREATE TABLE agents ("
                    "id CHAR(36) NOT NULL PRIMARY KEY, "
                    "user_id CHAR(36) NOT NULL, "
                    "name VARCHAR(255), "
                    "status VARCHAR(50), "
                    "created_at DATETIME, "
                    "updated_at DATETIME, "
                    "last_heartbeat DATETIME"
                    ")"
                )
            )
            connection.execute(
                sa.text(
                    "CREATE TABLE agent_logs ("
                    "id CHAR(36) NOT NULL PRIMARY KEY, "
                    "agent_id CHAR(36) NOT NULL, "
                    "level VARCHAR(20), "
                    "message TEXT, "
                    "extra_data TEXT, "
                    "timestamp DATETIME"
                    ")"
                )
            )
            connection.execute(
                sa.text(
                    "CREATE TABLE usage_events ("
                    "id CHAR(36) NOT NULL PRIMARY KEY, "
                    "event_type VARCHAR(100) NOT NULL, "
                    "user_id CHAR(36) NOT NULL, "
                    "created_at DATETIME NOT NULL"
                    ")"
                )
            )
    finally:
        engine.dispose()

    _run_alembic_upgrade(f"sqlite:///{db_path}")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        inspector = sa.inspect(engine)
        assert {"email_verification_expires_at"} <= _column_names(inspector, "users")
        assert {"roles"} <= _column_names(inspector, "users")
        assert {"meta_data"} <= _column_names(inspector, "agent_logs")
        assert {
            "resource_type",
            "resource_id",
            "credits_used",
            "event_metadata",
        } <= _column_names(inspector, "usage_events")
        assert {"last_heartbeat"} <= _column_names(inspector, "agents")
        assert "refresh_token_sessions" in inspector.get_table_names()
        assert {
            "ix_refresh_token_sessions_user_id",
            "ix_refresh_token_sessions_token_jti",
            "ix_refresh_token_sessions_family_id",
        } <= _index_names(inspector, "refresh_token_sessions")
        assert {
            "original_issued_at",
            "token_nonce",
            "rotation_grace_expires_at",
        } <= _column_names(inspector, "refresh_token_sessions")
        _assert_webhook_schema(inspector)

        with engine.connect() as connection:
            migrated_user = connection.execute(
                sa.text("SELECT id, roles FROM users WHERE id = :user_id"),
                {"user_id": legacy_user_id},
            ).one()
        assert migrated_user.id == legacy_user_id
        assert json.loads(migrated_user.roles) == ["VIEWER"]
    finally:
        engine.dispose()
