from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import tomllib

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from src.api import document_worker, reasoning_worker
from src.api import main as main_module


ROOT = Path(__file__).resolve().parents[2]
WORKER_CASES = (
    (
        document_worker,
        "run_document_worker",
        "DocumentWorkerRuntimeState",
        "claim_next_document_job",
        "execute_document_job",
        "update_document_queue_depth",
        "documents_enabled",
        "document_worker_poll_seconds",
    ),
    (
        reasoning_worker,
        "run_reasoning_worker",
        "ReasoningWorkerRuntimeState",
        "claim_next_reasoning_job",
        "execute_reasoning_job",
        "update_reasoning_queue_depth",
        "reasoning_enabled",
        "reasoning_worker_poll_seconds",
    ),
)


def _settings(*, enabled_name: str, poll_name: str, enabled: bool) -> SimpleNamespace:
    values = {
        "log_level": "INFO",
        "json_logging": False,
        "log_file": None,
        enabled_name: enabled,
        poll_name: 1,
    }
    return SimpleNamespace(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "worker_module",
        "run_name",
        "state_name",
        "claim_name",
        "execute_name",
        "depth_name",
        "_enabled_name",
        "_poll_name",
    ),
    WORKER_CASES,
)
async def test_worker_loop_claims_executes_and_updates_depth(
    monkeypatch,
    worker_module,
    run_name,
    state_name,
    claim_name,
    execute_name,
    depth_name,
    _enabled_name,
    _poll_name,
):
    session = object()
    claimed_job = object()
    claim_calls = 0
    executed: list[tuple[object, object]] = []
    first_iteration_complete = asyncio.Event()

    @asynccontextmanager
    async def session_maker():
        yield session

    async def claim(candidate_session):
        nonlocal claim_calls
        assert candidate_session is session
        claim_calls += 1
        return claimed_job if claim_calls == 1 else None

    async def execute(candidate_session, *, claimed_job):
        executed.append((candidate_session, claimed_job))

    async def update_depth(candidate_session):
        assert candidate_session is session
        first_iteration_complete.set()

    monkeypatch.setattr(worker_module.database, "async_session_maker", session_maker)
    monkeypatch.setattr(worker_module, claim_name, claim)
    monkeypatch.setattr(worker_module, execute_name, execute)
    monkeypatch.setattr(worker_module, depth_name, update_depth)

    state = getattr(worker_module, state_name)()
    task = asyncio.create_task(
        getattr(worker_module, run_name)(poll_seconds=3600, runtime_state=state)
    )
    await asyncio.wait_for(first_iteration_complete.wait(), timeout=1)
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert executed == [(session, claimed_job)]
    assert state.started_at is not None
    assert state.last_success_at is not None
    assert state.stopped_at is not None
    assert state.total_failures == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "worker_module",
        "run_name",
        "state_name",
        "claim_name",
        "_execute_name",
        "depth_name",
        "_enabled_name",
        "_poll_name",
    ),
    WORKER_CASES,
)
async def test_worker_loop_retries_after_iteration_failure(
    monkeypatch,
    worker_module,
    run_name,
    state_name,
    claim_name,
    _execute_name,
    depth_name,
    _enabled_name,
    _poll_name,
):
    claim_calls = 0
    recovered = asyncio.Event()

    @asynccontextmanager
    async def session_maker():
        yield object()

    async def claim(_session):
        nonlocal claim_calls
        claim_calls += 1
        if claim_calls == 1:
            raise RuntimeError("transient queue failure")
        return None

    async def update_depth(_session):
        recovered.set()

    monkeypatch.setattr(worker_module.database, "async_session_maker", session_maker)
    monkeypatch.setattr(worker_module, claim_name, claim)
    monkeypatch.setattr(worker_module, depth_name, update_depth)

    state = getattr(worker_module, state_name)()
    task = asyncio.create_task(
        getattr(worker_module, run_name)(poll_seconds=0, runtime_state=state)
    )
    await asyncio.wait_for(recovered.wait(), timeout=1)
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert claim_calls >= 2
    assert state.total_failures == 1
    assert state.last_failure_at is not None
    assert state.consecutive_failures == 0
    assert state.last_error is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "worker_module",
        "run_name",
        "state_name",
        "claim_name",
        "_execute_name",
        "_depth_name",
        "_enabled_name",
        "_poll_name",
    ),
    WORKER_CASES,
)
async def test_worker_loop_propagates_cancellation_during_claim(
    monkeypatch,
    worker_module,
    run_name,
    state_name,
    claim_name,
    _execute_name,
    _depth_name,
    _enabled_name,
    _poll_name,
):
    claim_started = asyncio.Event()
    never_complete = asyncio.Event()

    @asynccontextmanager
    async def session_maker():
        yield object()

    async def claim(_session):
        claim_started.set()
        await never_complete.wait()

    monkeypatch.setattr(worker_module.database, "async_session_maker", session_maker)
    monkeypatch.setattr(worker_module, claim_name, claim)

    state = getattr(worker_module, state_name)()
    task = asyncio.create_task(
        getattr(worker_module, run_name)(poll_seconds=1, runtime_state=state)
    )
    await asyncio.wait_for(claim_started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert state.stopped_at is not None
    assert state.total_failures == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "worker_module",
        "run_name",
        "_state_name",
        "_claim_name",
        "_execute_name",
        "_depth_name",
        "enabled_name",
        "poll_name",
    ),
    WORKER_CASES,
)
@pytest.mark.parametrize("enabled", [False, True])
async def test_standalone_worker_honors_flag_and_owns_engine_lifecycle(
    monkeypatch,
    worker_module,
    run_name,
    _state_name,
    _claim_name,
    _execute_name,
    _depth_name,
    enabled_name,
    poll_name,
    enabled,
):
    calls: list[str] = []

    async def init_db():
        calls.append("init")

    async def run_worker(**_kwargs):
        calls.append("run")

    async def dispose_engine():
        calls.append("dispose")

    monkeypatch.setattr(
        worker_module,
        "get_settings",
        lambda: _settings(enabled_name=enabled_name, poll_name=poll_name, enabled=enabled),
    )
    monkeypatch.setattr(worker_module, "setup_json_logging", lambda **_kwargs: None)
    monkeypatch.setattr(worker_module.database, "init_db", init_db)
    monkeypatch.setattr(worker_module.database, "dispose_engine", dispose_engine)
    monkeypatch.setattr(worker_module, run_name, run_worker)

    await worker_module._run()

    assert calls == (["init", "run", "dispose"] if enabled else [])


@pytest.mark.asyncio
async def test_api_lifespan_starts_enabled_worker_after_database_and_cancels_before_disposal(
    monkeypatch,
):
    database_initialization_started = asyncio.Event()
    release_database = asyncio.Event()
    document_worker_started = asyncio.Event()
    document_worker_cancelled = asyncio.Event()
    shutdown_order: list[str] = []

    async def initialize_database_with_retries(app):
        database_initialization_started.set()
        await release_database.wait()
        app.state.database_ready = True
        app.state.database_ready_event.set()

    async def run_document_worker(**_kwargs):
        document_worker_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            shutdown_order.append("worker_cancelled")
            document_worker_cancelled.set()

    async def unexpected_reasoning_worker(**_kwargs):
        raise AssertionError("disabled reasoning worker started")

    async def no_op():
        return None

    async def dispose_engine():
        assert document_worker_cancelled.is_set()
        shutdown_order.append("engine_disposed")

    monkeypatch.setattr(
        main_module,
        "_initialize_database_with_retries",
        initialize_database_with_retries,
    )
    monkeypatch.setattr(main_module, "run_document_worker", run_document_worker)
    monkeypatch.setattr(main_module, "run_reasoning_worker", unexpected_reasoning_worker)
    monkeypatch.setattr(main_module, "get_buffered_audit_log", no_op)
    monkeypatch.setattr(main_module, "close_buffered_audit_log", no_op)
    monkeypatch.setattr(main_module, "dispose_engine", dispose_engine)

    lifespan = main_module._build_lifespan(
        background_monitor_enabled=False,
        database_required_on_startup=False,
        document_worker_enabled=True,
        reasoning_worker_enabled=False,
    )
    app = FastAPI()

    async with lifespan(app):
        await asyncio.wait_for(database_initialization_started.wait(), timeout=1)
        assert not document_worker_started.is_set()
        assert app.state.document_worker_task is not None
        assert app.state.reasoning_worker_task is None

        release_database.set()
        await asyncio.wait_for(document_worker_started.wait(), timeout=1)

    assert shutdown_order == ["worker_cancelled", "engine_disposed"]


@pytest.mark.asyncio
async def test_readiness_reports_enabled_worker_waiting_and_failures(monkeypatch):
    monkeypatch.setattr(main_module.settings, "allowed_hosts", ["testserver"])
    app = main_module.create_app(
        enable_lifespan=False,
        background_monitor_enabled=False,
        database_required_on_startup=False,
        document_worker_enabled=True,
        reasoning_worker_enabled=False,
    )
    app.state.database_ready = True

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        waiting_response = await client.get("/ready")
        assert waiting_response.status_code == 503
        assert waiting_response.json()["workers"]["document_worker"]["status"] == "waiting"

        app.state.document_worker_state.started_at = datetime.now(timezone.utc)
        running_response = await client.get("/ready")
        assert running_response.status_code == 200
        assert running_response.json()["workers"]["document_worker"]["status"] == "running"

        app.state.document_worker_state.consecutive_failures = 1
        app.state.document_worker_state.total_failures = 1
        degraded_response = await client.get("/ready")
        health_response = await client.get("/health")

    assert degraded_response.status_code == 503
    assert degraded_response.json()["workers"]["document_worker"]["status"] == "degraded"
    assert health_response.json()["status"] == "degraded"
    assert health_response.json()["components"]["document_worker"] == {
        "status": "degraded",
        "consecutive_failures": 1,
        "total_failures": 1,
    }


def test_cli_distribution_does_not_publish_server_worker_entrypoints():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"] == {"mutx": "cli.main:cli"}
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["include"] == ["cli*"]
