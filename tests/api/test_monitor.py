import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.api.services import monitor as monitor_module
from src.api.services.monitoring import STALE_THRESHOLD_SECONDS


class _FakeExecuteResult:
    def __init__(self, *, scalar_value=None, scalar_values=None):
        self._scalar_value = scalar_value
        self._scalar_values = scalar_values or []

    def scalar_one_or_none(self):
        return self._scalar_value

    def scalars(self):
        return self

    def all(self):
        return self._scalar_values


class _FakeSession:
    def __init__(self, result: _FakeExecuteResult):
        self.result = result
        self.committed = False
        self.added = []

    async def execute(self, _query):
        return self.result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


class _FakeSessionManager:
    def __init__(self, result: _FakeExecuteResult):
        self.result = result

    async def __aenter__(self):
        return _FakeSession(self.result)

    async def __aexit__(self, _exc_type, _exc, _tb):
        return False


def _fake_session_maker(result: _FakeExecuteResult):
    return _FakeSessionManager(result)


class _TrackedSession(_FakeSession):
    def __init__(self, result: _FakeExecuteResult):
        super().__init__(result)
        self.commit_calls = 0
        self.rollback_calls = 0
        self.commit_event: asyncio.Event | None = None
        self.rollback_event: asyncio.Event | None = None

    async def commit(self):
        self.commit_calls += 1
        if self.commit_event is not None:
            self.commit_event.set()

    async def rollback(self):
        self.rollback_calls += 1
        if self.rollback_event is not None:
            self.rollback_event.set()


class _TrackedSessionManager:
    def __init__(self, session: _TrackedSession):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, _exc_type, _exc, _tb):
        return False


class _FakeSelfHealing:
    def __init__(self, tracked_agents):
        self.registered = []
        self.unregistered = []
        self.health_check_scheduler = SimpleNamespace(
            get_all_health=lambda: tracked_agents,
        )

    def register_agent(self, agent_id, health_check_fn):
        self.registered.append((agent_id, health_check_fn))

    def unregister_agent(self, agent_id):
        self.unregistered.append(agent_id)


class _FakeSelfHealingMissingScheduler:
    def __init__(self, fail_stop: bool = False):
        self.start_calls = 0
        self.stop_calls = 0
        self.fail_stop = fail_stop

    async def start(self):
        self.start_calls += 1

    async def stop(self):
        self.stop_calls += 1
        if self.fail_stop:
            raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_start_background_monitor_stops_self_healing_on_cancel(monkeypatch):
    monitor_cycle_started = asyncio.Event()
    fake_self_healing = _FakeSelfHealingMissingScheduler()

    async def fake_monitor_agent_health(_session):
        monitor_cycle_started.set()

    monkeypatch.setattr(
        monitor_module,
        "get_self_healing_service",
        lambda: fake_self_healing,
    )
    monkeypatch.setattr(
        monitor_module,
        "monitor_agent_health",
        fake_monitor_agent_health,
    )
    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _fake_session_maker(_FakeExecuteResult()),
    )

    task = asyncio.create_task(monitor_module.start_background_monitor())
    await asyncio.wait_for(monitor_cycle_started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert fake_self_healing.start_calls == 1
    assert fake_self_healing.stop_calls == 1


@pytest.mark.asyncio
async def test_start_background_monitor_cancellation_survives_stop_failure(monkeypatch):
    monitor_cycle_started = asyncio.Event()
    fake_self_healing = _FakeSelfHealingMissingScheduler(fail_stop=True)

    async def fake_monitor_agent_health(_session):
        monitor_cycle_started.set()

    monkeypatch.setattr(
        monitor_module,
        "get_self_healing_service",
        lambda: fake_self_healing,
    )
    monkeypatch.setattr(
        monitor_module,
        "monitor_agent_health",
        fake_monitor_agent_health,
    )
    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _fake_session_maker(_FakeExecuteResult()),
    )

    task = asyncio.create_task(monitor_module.start_background_monitor())
    await asyncio.wait_for(monitor_cycle_started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert fake_self_healing.start_calls == 1
    assert fake_self_healing.stop_calls == 1


@pytest.mark.asyncio
async def test_start_background_monitor_commits_successful_iteration(monkeypatch, tmp_path):
    fake_self_healing = _FakeSelfHealingMissingScheduler()
    session = _TrackedSession(_FakeExecuteResult())
    session.commit_event = asyncio.Event()
    heartbeat_file = tmp_path / "monitor.heartbeat"
    runtime_state = monitor_module.MonitorRuntimeState(heartbeat_file=heartbeat_file)

    async def fake_monitor_agent_health(_session):
        return None

    monkeypatch.setattr(
        monitor_module,
        "get_self_healing_service",
        lambda: fake_self_healing,
    )
    monkeypatch.setattr(
        monitor_module,
        "monitor_agent_health",
        fake_monitor_agent_health,
    )
    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _TrackedSessionManager(session),
    )

    task = asyncio.create_task(monitor_module.start_background_monitor(runtime_state))
    await asyncio.wait_for(session.commit_event.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert session.commit_calls >= 1
    assert session.rollback_calls == 0
    assert runtime_state.last_success_at is not None
    assert runtime_state.consecutive_failures == 0
    assert monitor_module.heartbeat_is_fresh(heartbeat_file, 30)


@pytest.mark.asyncio
async def test_start_background_monitor_rolls_back_failed_iteration(monkeypatch):
    real_sleep = asyncio.sleep
    fake_self_healing = _FakeSelfHealingMissingScheduler()
    session = _TrackedSession(_FakeExecuteResult())
    session.rollback_event = asyncio.Event()
    runtime_state = monitor_module.MonitorRuntimeState()

    async def fake_monitor_agent_health(_session):
        raise RuntimeError("boom")

    async def fake_sleep(_delay):
        await real_sleep(0)

    monkeypatch.setattr(
        monitor_module,
        "get_self_healing_service",
        lambda: fake_self_healing,
    )
    monkeypatch.setattr(
        monitor_module,
        "monitor_agent_health",
        fake_monitor_agent_health,
    )
    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _TrackedSessionManager(session),
    )
    monkeypatch.setattr(monitor_module.asyncio, "sleep", fake_sleep)

    task = asyncio.create_task(monitor_module.start_background_monitor(runtime_state))
    await asyncio.wait_for(session.rollback_event.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert session.commit_calls == 0
    assert session.rollback_calls >= 1
    assert runtime_state.last_error == "boom"
    assert runtime_state.last_error_at is not None
    assert runtime_state.consecutive_failures >= 1


@pytest.mark.asyncio
async def test_start_background_monitor_exits_after_bounded_consecutive_failures(monkeypatch):
    real_sleep = asyncio.sleep
    fake_self_healing = _FakeSelfHealingMissingScheduler()
    session = _TrackedSession(_FakeExecuteResult())
    runtime_state = monitor_module.MonitorRuntimeState()

    async def fake_monitor_agent_health(_session):
        raise RuntimeError("database unavailable")

    async def fake_sleep(_delay):
        await real_sleep(0)

    monkeypatch.setattr(
        monitor_module,
        "get_self_healing_service",
        lambda: fake_self_healing,
    )
    monkeypatch.setattr(
        monitor_module,
        "monitor_agent_health",
        fake_monitor_agent_health,
    )
    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _TrackedSessionManager(session),
    )
    monkeypatch.setattr(monitor_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match=r"consecutive failure limit \(2\)"):
        await monitor_module.start_background_monitor(
            runtime_state,
            max_consecutive_failures=2,
        )

    assert runtime_state.consecutive_failures == 2
    assert session.rollback_calls == 2
    assert fake_self_healing.stop_calls == 1


def test_monitor_heartbeat_rejects_missing_stale_and_future_values(tmp_path):
    heartbeat_file = tmp_path / "monitor.heartbeat"
    now = datetime.now(timezone.utc)

    assert not monitor_module.heartbeat_is_fresh(heartbeat_file, 30, now=now)

    heartbeat_file.write_text(f"{(now - timedelta(seconds=31)).timestamp()}\n")
    assert not monitor_module.heartbeat_is_fresh(heartbeat_file, 30, now=now)

    heartbeat_file.write_text(f"{(now + timedelta(seconds=6)).timestamp()}\n")
    assert not monitor_module.heartbeat_is_fresh(heartbeat_file, 30, now=now)

    heartbeat_file.write_text(f"{(now - timedelta(seconds=5)).timestamp()}\n")
    assert monitor_module.heartbeat_is_fresh(heartbeat_file, 30, now=now)


@pytest.mark.asyncio
async def test_agent_heartbeat_check_returns_false_for_unknown_agent(monkeypatch):
    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _fake_session_maker(_FakeExecuteResult(scalar_value=None)),
    )

    check = monitor_module._agent_heartbeat_check(str(uuid.uuid4()))
    assert await check() is False


@pytest.mark.asyncio
async def test_agent_heartbeat_check_uses_stale_threshold_and_created_at_fallback(monkeypatch):
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with_fresh_heartbeat = SimpleNamespace(
        last_heartbeat=now - timedelta(seconds=STALE_THRESHOLD_SECONDS - 1),
        created_at=now,
    )
    with_stale_heartbeat = SimpleNamespace(
        last_heartbeat=now - timedelta(seconds=STALE_THRESHOLD_SECONDS + 1),
        created_at=now,
    )
    with_only_created_at = SimpleNamespace(
        last_heartbeat=None,
        created_at=now - timedelta(seconds=STALE_THRESHOLD_SECONDS - 1),
    )
    with_only_created_at_timezone_aware = SimpleNamespace(
        last_heartbeat=None,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS - 1),
    )
    without_timestamps = SimpleNamespace(last_heartbeat=None, created_at=None)

    agent_id = str(uuid.uuid4())

    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _fake_session_maker(_FakeExecuteResult(scalar_value=with_fresh_heartbeat)),
    )
    check = monitor_module._agent_heartbeat_check(agent_id)
    assert await check() is True

    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _fake_session_maker(_FakeExecuteResult(scalar_value=with_stale_heartbeat)),
    )
    check = monitor_module._agent_heartbeat_check(agent_id)
    assert await check() is False

    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _fake_session_maker(_FakeExecuteResult(scalar_value=with_only_created_at)),
    )
    check = monitor_module._agent_heartbeat_check(agent_id)
    assert await check() is True

    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _fake_session_maker(
            _FakeExecuteResult(scalar_value=with_only_created_at_timezone_aware)
        ),
    )
    check = monitor_module._agent_heartbeat_check(agent_id)
    assert await check() is True

    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _fake_session_maker(_FakeExecuteResult(scalar_value=without_timestamps)),
    )
    check = monitor_module._agent_heartbeat_check(agent_id)
    assert await check() is False


@pytest.mark.asyncio
async def test_sync_self_healing_agents_registers_and_unregisters_delta_agents(monkeypatch):
    active_agent_ids = [str(uuid.uuid4()) for _ in range(2)]
    stale_agent_id = str(uuid.uuid4())
    tracked_agent_ids = {
        active_agent_ids[1]: object(),
        stale_agent_id: object(),
    }
    query_result = _FakeExecuteResult(
        scalar_values=[uuid.UUID(agent_id) for agent_id in active_agent_ids],
    )
    fake_self_healing = _FakeSelfHealing(tracked_agent_ids)
    session = _FakeSession(query_result)

    await monitor_module._sync_self_healing_agents(session, fake_self_healing)

    assert [agent_id for agent_id, _ in fake_self_healing.registered] == [active_agent_ids[0]]
    assert fake_self_healing.unregistered == [stale_agent_id]


@pytest.mark.asyncio
async def test_sync_self_healing_agents_excludes_stopped_agents():
    running_agent_id = str(uuid.uuid4())
    session = _FakeSession(
        _FakeExecuteResult(
            scalar_values=[uuid.UUID(running_agent_id)],
        )
    )
    fake_self_healing = _FakeSelfHealing({})

    await monitor_module._sync_self_healing_agents(session, fake_self_healing)

    assert [agent_id for agent_id, _ in fake_self_healing.registered] == [running_agent_id]


@pytest.mark.asyncio
async def test_recover_agent_to_running_skips_stopped_agents(monkeypatch):
    stopped_agent = SimpleNamespace(
        id=uuid.uuid4(),
        status=monitor_module.AgentStatus.STOPPED.value,
        last_heartbeat=None,
    )
    fake_session = _FakeSession(_FakeExecuteResult(scalar_value=stopped_agent))

    class _InjectedSessionManager:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

    monkeypatch.setattr(
        monitor_module.database_module,
        "async_session_maker",
        lambda: _InjectedSessionManager(),
    )

    await monitor_module._recover_agent_to_running(str(stopped_agent.id), {})

    assert stopped_agent.status == monitor_module.AgentStatus.STOPPED.value
    assert fake_session.committed is False
    assert fake_session.added == []
