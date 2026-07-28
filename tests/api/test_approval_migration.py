"""Migration coverage for durable approval persistence and legacy backfill."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT / "src/api/models/migrations/versions/f4d6a8c0e2b1_add_durable_approval_workflows.py"
)


def _current_head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("durable_approval_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_current_head_database(database_url: str) -> tuple[str, str]:
    owner_id = str(uuid.uuid4())
    approval_id = str(uuid.uuid4())
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                sa.text("INSERT INTO alembic_version (version_num) VALUES ('e3c5a7b9d1f2')")
            )
            connection.execute(sa.text("CREATE TABLE users (id CHAR(36) NOT NULL PRIMARY KEY)"))
            connection.execute(
                sa.text(
                    "CREATE TABLE user_settings ("
                    "id CHAR(36) NOT NULL PRIMARY KEY, "
                    "user_id CHAR(36) NOT NULL, "
                    "key VARCHAR(255) NOT NULL, "
                    "value TEXT, "
                    "created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL)"
                )
            )
            connection.execute(
                sa.text("INSERT INTO users (id) VALUES (:owner_id)"),
                {"owner_id": owner_id},
            )
            valid_value = json.dumps(
                {
                    "id": approval_id,
                    "agent_id": "agent-legacy",
                    "session_id": "session-legacy",
                    "action_type": "deploy",
                    "payload": {"target": "production"},
                    "status": "PENDING",
                    "requester": "legacy-owner@example.com",
                    "approver": None,
                    "created_at": "2026-07-28T12:00:00+00:00",
                    "resolved_at": None,
                    "comment": None,
                }
            )
            rows = [
                (str(uuid.uuid4()), f"approval.request.{approval_id}", valid_value),
                (str(uuid.uuid4()), f"approval.request.{uuid.uuid4()}", "{not-json"),
                (
                    str(uuid.uuid4()),
                    f"approval.request.{uuid.uuid4()}",
                    json.dumps({"status": ["malformed"]}),
                ),
                (str(uuid.uuid4()), "pico.unrelated", json.dumps({"value": True})),
            ]
            for setting_id, key, value in rows:
                connection.execute(
                    sa.text(
                        "INSERT INTO user_settings "
                        "(id, user_id, key, value, created_at, updated_at) "
                        "VALUES (:id, :user_id, :key, :value, :created_at, :updated_at)"
                    ),
                    {
                        "id": setting_id,
                        "user_id": owner_id,
                        "key": key,
                        "value": value,
                        "created_at": "2026-07-28 12:00:00",
                        "updated_at": "2026-07-28 12:00:00",
                    },
                )
    finally:
        engine.dispose()
    return owner_id, approval_id


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
        f"alembic upgrade failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_upgrade_from_current_head_backfills_only_valid_legacy_approvals(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'approval-upgrade.sqlite3'}"
    owner_id, approval_id = _create_current_head_database(database_url)

    _run_alembic_upgrade(database_url)

    engine = sa.create_engine(database_url)
    try:
        inspector = sa.inspect(engine)
        assert {"approval_requests", "approval_notification_outbox"} <= set(
            inspector.get_table_names()
        )
        assert {
            "ix_approval_requests_owner_status_created_at",
            "ix_approval_requests_reviewer_status_created_at",
            "ix_approval_requests_agent_status_created_at",
        } <= {index["name"] for index in inspector.get_indexes("approval_requests")}
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("approval_requests")
        } == {"uq_approval_requests_owner_idempotency_key"}

        with engine.connect() as connection:
            backfilled = (
                connection.execute(
                    sa.text("SELECT id, owner_id, agent_id, status, payload FROM approval_requests")
                )
                .mappings()
                .all()
            )
            legacy_count = connection.execute(
                sa.text("SELECT count(*) FROM user_settings")
            ).scalar_one()
            revision = connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()

        assert len(backfilled) == 1
        assert uuid.UUID(backfilled[0]["id"]) == uuid.UUID(approval_id)
        assert uuid.UUID(backfilled[0]["owner_id"]) == uuid.UUID(owner_id)
        assert backfilled[0]["agent_id"] == "agent-legacy"
        assert backfilled[0]["status"] == "PENDING"
        assert json.loads(backfilled[0]["payload"]) == {"target": "production"}
        assert legacy_count == 4
        assert revision == _current_head()
    finally:
        engine.dispose()


def test_approval_migration_upgrade_is_idempotent(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'approval-idempotent.sqlite3'}"
    _create_current_head_database(database_url)
    module = _load_migration_module()
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(module, "op", operations)
            module.upgrade()
            module.upgrade()

            assert (
                connection.execute(sa.text("SELECT count(*) FROM approval_requests")).scalar_one()
                == 1
            )
    finally:
        engine.dispose()


def test_approval_migration_fails_before_mutating_partial_schema(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'approval-partial.sqlite3'}"
    module = _load_migration_module()
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE users (id CHAR(36) NOT NULL PRIMARY KEY)"))
            connection.execute(
                sa.text("CREATE TABLE approval_requests (id CHAR(36) NOT NULL PRIMARY KEY)")
            )
            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(module, "op", operations)

            with pytest.raises(RuntimeError, match="partial approval_requests"):
                module.upgrade()

            assert "approval_notification_outbox" not in sa.inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_approval_migration_rejects_conflicting_legacy_backfill(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'approval-conflict.sqlite3'}"
    _create_current_head_database(database_url)
    module = _load_migration_module()
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(module, "op", operations)
            module.upgrade()
            connection.execute(
                sa.text("UPDATE approval_requests SET request_hash = :request_hash"),
                {"request_hash": "0" * 64},
            )

            with pytest.raises(RuntimeError, match="conflicts with an existing durable record"):
                module.upgrade()
    finally:
        engine.dispose()


def test_legacy_security_backfill_discards_bearer_secret_and_preserves_assignment():
    module = _load_migration_module()
    owner_id = uuid.uuid4()
    reviewer_id = uuid.uuid4()
    approval_id = uuid.uuid4()
    row = {
        "user_id": str(owner_id),
        "key": f"legacy_security.approval.{approval_id}",
        "value": json.dumps(
            {
                "request_id": str(approval_id),
                "owner_id": str(owner_id),
                "reviewer_id": str(reviewer_id),
                "token": "undisclosed-one-time-secret",
                "status": "pending",
                "tool_name": "outbound_message_send",
                "tool_args": {"recipient": "customer@example.com"},
                "agent_id": "agent-legacy-security",
                "session_id": "session-legacy-security",
                "reason": "Review before sending",
                "created_at": "2026-07-28T12:00:00+00:00",
                "expires_at": "2026-07-28T12:05:00+00:00",
            }
        ),
        "created_at": "2026-07-28 12:00:00",
        "updated_at": "2026-07-28 12:00:00",
    }

    converged = module._legacy_security_approval(row)

    assert converged is not None
    assert converged["id"] == approval_id
    assert converged["owner_id"] == owner_id
    assert converged["reviewer_id"] == reviewer_id
    assert converged["payload"] == {
        "tool_args": {"recipient": "customer@example.com"},
        "reason": "Review before sending",
        "timeout_minutes": 5,
        "source": "legacy_security",
    }
    assert "undisclosed-one-time-secret" not in json.dumps(converged, default=str)
