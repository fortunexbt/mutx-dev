"""Durability, authorization, isolation, and SSRF tests for /v1/scheduler."""

import asyncio
from datetime import datetime, timedelta, timezone
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.models.scheduler import ScheduledTask
from src.api.models.scheduler_schemas import SchedulerTaskCreate, SchedulerWebhookPayload
import src.api.routes.scheduler as scheduler_route
from src.api.services.scheduler_service import SchedulerService
import src.api.services.scheduler_webhook as scheduler_webhook


@pytest_asyncio.fixture(autouse=True)
async def scheduler_test_state(db_session, test_user):
    """Use a developer by default and clean up only process-local execution handles."""
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    try:
        yield
    finally:
        running = list(scheduler_route._execution_tasks.values())
        for execution in running:
            if not execution.done():
                execution.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)
        scheduler_route._execution_tasks.clear()
        scheduler_route._execution_ids.clear()


@pytest_asyncio.fixture
async def internal_other_user(db_session, other_user):
    other_user.email = "other@mutx.dev"
    other_user.is_email_verified = True
    other_user.roles = ["DEVELOPER"]
    await db_session.commit()
    return other_user


def _session_factory(test_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def _load_task(db: AsyncSession, task_id: str) -> ScheduledTask:
    return (
        await db.execute(
            select(ScheduledTask)
            .where(ScheduledTask.id == uuid.UUID(task_id))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _task_count(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(ScheduledTask))).scalar_one())


@pytest.mark.asyncio
async def test_scheduler_requires_authentication(client_no_auth: AsyncClient):
    assert (await client_no_auth.get("/v1/scheduler")).status_code == 401
    assert (
        await client_no_auth.post(
            "/v1/scheduler",
            json={"name": "test-task", "interval_seconds": 60},
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_scheduler_preserves_internal_user_restriction(other_user_client: AsyncClient):
    assert (await other_user_client.get("/v1/scheduler")).status_code == 403
    assert (
        await other_user_client.post(
            "/v1/scheduler",
            json={"name": "test-task", "interval_seconds": 60},
        )
    ).status_code == 403


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        pytest.param("VIEWER", 200, id="viewer"),
        pytest.param("DEVELOPER", 200, id="developer"),
        pytest.param("ADMIN", 200, id="admin-implicit"),
        pytest.param("AUDIT_ADMIN", 403, id="unrelated-role"),
    ],
)
@pytest.mark.asyncio
async def test_scheduler_safe_owner_reads_use_persisted_role_matrix(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    role: str,
    expected: int,
):
    task = await SchedulerService(db_session).create_task(
        test_user.id,
        SchedulerTaskCreate(name="owned-readable", interval_seconds=60),
    )
    test_user.roles = [role]
    await db_session.commit()
    assert (await client.get("/v1/scheduler")).status_code == expected
    assert (await client.get(f"/v1/scheduler/{task.id}")).status_code == expected


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        pytest.param("VIEWER", 403, id="viewer"),
        pytest.param("DEVELOPER", 201, id="developer"),
        pytest.param("ADMIN", 201, id="admin-implicit"),
        pytest.param("AUDIT_ADMIN", 403, id="unrelated-role"),
    ],
)
@pytest.mark.asyncio
async def test_scheduler_mutations_use_persisted_role_matrix(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    role: str,
    expected: int,
):
    test_user.roles = [role]
    await db_session.commit()
    response = await client.post(
        "/v1/scheduler",
        json={"name": f"{role}-task", "interval_seconds": 60},
    )
    assert response.status_code == expected
    if expected != 201:
        return

    task_id = response.json()["id"]
    assert (
        await client.patch(f"/v1/scheduler/{task_id}", json={"name": "role-updated"})
    ).status_code == 200
    assert (await client.post(f"/v1/scheduler/{task_id}/trigger")).status_code == 200
    assert (await client.delete(f"/v1/scheduler/{task_id}")).status_code == 204


@pytest.mark.parametrize(
    ("method", "suffix", "payload"),
    [
        pytest.param("PATCH", "", {"name": "denied"}, id="update"),
        pytest.param("DELETE", "", None, id="delete"),
        pytest.param("POST", "/trigger", None, id="trigger"),
    ],
)
@pytest.mark.asyncio
async def test_viewer_cannot_mutate_existing_owned_task(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    method: str,
    suffix: str,
    payload: dict | None,
):
    task = await SchedulerService(db_session).create_task(
        test_user.id,
        SchedulerTaskCreate(name="viewer-owned", interval_seconds=60),
    )
    test_user.roles = ["VIEWER"]
    await db_session.commit()

    response = await client.request(
        method,
        f"/v1/scheduler/{task.id}{suffix}",
        json=payload,
    )

    assert response.status_code == 403
    persisted = await _load_task(db_session, str(task.id))
    assert persisted.name == "viewer-owned"
    assert persisted.active_execution_id is None


@pytest.mark.asyncio
async def test_role_denial_happens_before_body_validation_and_side_effects(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
):
    test_user.roles = ["VIEWER"]
    await db_session.commit()

    response = await client.post(
        "/v1/scheduler",
        json={"name": "", "interval_seconds": 0, "task_type": "not-real"},
    )

    assert response.status_code == 403
    assert "Insufficient permissions" in response.json()["detail"]
    assert await _task_count(db_session) == 0


@pytest.mark.asyncio
async def test_scheduler_list_and_crud_are_scoped_to_owner(
    client: AsyncClient,
    other_user_client: AsyncClient,
    internal_other_user,
):
    primary = await client.post(
        "/v1/scheduler",
        json={"name": "primary-task", "interval_seconds": 60},
    )
    secondary = await other_user_client.post(
        "/v1/scheduler",
        json={"name": "secondary-task", "interval_seconds": 60},
    )
    assert primary.status_code == secondary.status_code == 201

    primary_list = (await client.get("/v1/scheduler")).json()
    secondary_list = (await other_user_client.get("/v1/scheduler")).json()
    assert primary_list == {"tasks": [primary.json()], "total": 1}
    assert secondary_list == {"tasks": [secondary.json()], "total": 1}

    task_id = primary.json()["id"]
    updated = await client.patch(f"/v1/scheduler/{task_id}", json={"name": "updated"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "updated"
    triggered = await client.post(f"/v1/scheduler/{task_id}/trigger")
    assert triggered.status_code == 200
    assert triggered.json()["task_id"] == task_id
    assert (await client.delete(f"/v1/scheduler/{task_id}")).status_code == 204
    assert (await client.get(f"/v1/scheduler/{task_id}")).status_code == 404


@pytest.mark.parametrize(
    ("method", "payload", "suffix"),
    [
        pytest.param("GET", None, "", id="get"),
        pytest.param("PATCH", {"name": "hijacked"}, "", id="update"),
        pytest.param("DELETE", None, "", id="delete"),
        pytest.param("POST", None, "/trigger", id="trigger"),
    ],
)
@pytest.mark.asyncio
async def test_foreign_scheduler_task_is_indistinguishable_from_missing(
    client: AsyncClient,
    other_user_client: AsyncClient,
    internal_other_user,
    db_session: AsyncSession,
    method: str,
    payload: dict | None,
    suffix: str,
):
    created = await client.post(
        "/v1/scheduler",
        json={"name": "private-task", "interval_seconds": 60},
    )
    task_id = created.json()["id"]
    before = (await _load_task(db_session, task_id)).updated_at

    foreign = await other_user_client.request(
        method,
        f"/v1/scheduler/{task_id}{suffix}",
        json=payload,
    )
    missing = await other_user_client.request(
        method,
        f"/v1/scheduler/{uuid.uuid4()}{suffix}",
        json=payload,
    )

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Task not found"}
    assert (await _load_task(db_session, task_id)).updated_at == before


@pytest.mark.asyncio
async def test_interval_task_contract_uses_unix_seconds(client: AsyncClient):
    response = await client.post(
        "/v1/scheduler",
        json={"name": "interval-check", "interval_seconds": 90},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["next_run"] - body["created_at"] == 90
    assert body["run_count"] == body["success_count"] == body["failure_count"] == 0
    assert body["status"] == "scheduled"


@pytest.mark.asyncio
async def test_task_survives_service_and_session_restart(
    client: AsyncClient,
    test_engine,
):
    created = await client.post(
        "/v1/scheduler",
        json={"name": "restart-safe", "interval_seconds": 60},
    )
    task_id = created.json()["id"]

    factory = _session_factory(test_engine)
    async with factory() as restarted_session:
        restarted_service = SchedulerService(restarted_session)
        restored = await restarted_service.get_owned_task(
            task_id,
            uuid.UUID("11111111-1111-4111-a111-111111111111"),
        )

    assert restored.name == "restart-safe"
    assert str(restored.id) == task_id


@pytest.mark.asyncio
async def test_competing_workers_atomically_claim_one_due_execution(
    db_session: AsyncSession,
    test_engine,
    test_user,
):
    task = await SchedulerService(db_session).create_task(
        test_user.id,
        SchedulerTaskCreate(name="claim-once", interval_seconds=60),
        now=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    factory = _session_factory(test_engine)

    async def claim_as_worker():
        async with factory() as worker_session:
            return await SchedulerService(worker_session).claim_due_tasks(
                now=datetime.now(timezone.utc)
            )

    worker_claims = await asyncio.gather(claim_as_worker(), claim_as_worker())
    claims = [claim for result in worker_claims for claim in result]

    assert len(claims) == 1
    assert claims[0].task_id == task.id
    persisted = await _load_task(db_session, str(task.id))
    assert persisted.status == "running"
    assert persisted.active_execution_id == claims[0].execution_id


@pytest.mark.asyncio
async def test_expired_claim_is_released_and_late_worker_cannot_overwrite_outcome(
    db_session: AsyncSession,
    test_user,
):
    service = SchedulerService(db_session)
    task = await service.create_task(
        test_user.id,
        SchedulerTaskCreate(name="recover-claim", interval_seconds=1),
        now=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    first = await service.claim_owned_task(task.id, test_user.id)
    persisted = await _load_task(db_session, str(task.id))
    persisted.claim_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()

    second = await service.claim_owned_task(task.id, test_user.id)
    assert second.execution_id != first.execution_id
    assert (await _load_task(db_session, str(task.id))).failure_count == 1

    assert not await service.finalize_execution(task.id, first.execution_id, error=None)
    assert await service.finalize_execution(task.id, second.execution_id, error=None)
    recovered = await _load_task(db_session, str(task.id))
    assert recovered.status == "succeeded"
    assert recovered.run_count == recovered.success_count == 1
    assert recovered.failure_count == 1
    assert recovered.active_execution_id is None


@pytest.mark.asyncio
async def test_heartbeat_task_updates_owned_agent_and_records_success(
    client: AsyncClient,
    db_session: AsyncSession,
    test_agent,
    test_deployment,
):
    test_deployment.status = "deploying"
    await db_session.commit()
    created = await client.post(
        "/v1/scheduler",
        json={
            "name": "agent-heartbeat",
            "interval_seconds": 60,
            "task_type": "agent_heartbeat",
            "payload": {"agent_id": str(test_agent.id)},
        },
    )
    task_id = created.json()["id"]

    triggered = await client.post(f"/v1/scheduler/{task_id}/trigger")
    assert triggered.status_code == 200
    await db_session.refresh(test_agent)
    await db_session.refresh(test_deployment)
    assert test_agent.last_heartbeat is not None
    assert test_agent.status == "running"
    assert test_deployment.status == "running"

    task = (await client.get(f"/v1/scheduler/{task_id}")).json()
    assert task["status"] == "succeeded"
    assert task["run_count"] == task["success_count"] == 1
    assert task["failure_count"] == 0
    assert task["last_succeeded_at"] == task["last_finished_at"]
    assert task["last_error"] is None


@pytest.mark.asyncio
async def test_heartbeat_never_targets_another_tenants_agent(
    client: AsyncClient,
    db_session: AsyncSession,
    other_user,
):
    from src.api.models import Agent

    foreign_agent = Agent(
        name="foreign-agent",
        description="Owned by another user",
        config="{}",
        user_id=other_user.id,
    )
    db_session.add(foreign_agent)
    await db_session.commit()

    response = await client.post(
        "/v1/scheduler",
        json={
            "name": "foreign-heartbeat",
            "interval_seconds": 60,
            "task_type": "agent_heartbeat",
            "payload": {"agent_id": str(foreign_agent.id)},
        },
    )
    assert response.status_code == 404
    await db_session.refresh(foreign_agent)
    assert foreign_agent.last_heartbeat is None


@pytest.mark.asyncio
async def test_foreign_trigger_never_executes_another_tenants_webhook(
    client: AsyncClient,
    other_user_client: AsyncClient,
    internal_other_user,
    monkeypatch,
):
    calls = 0

    async def public_dns(_hostname: str, _port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    async def capture_delivery(_payload: SchedulerWebhookPayload) -> int:
        nonlocal calls
        calls += 1
        return 204

    monkeypatch.setattr(scheduler_webhook, "resolve_scheduler_webhook_ips", public_dns)
    monkeypatch.setattr(scheduler_route, "deliver_scheduler_webhook", capture_delivery)
    created = await client.post(
        "/v1/scheduler",
        json={
            "name": "owner-webhook",
            "interval_seconds": 60,
            "task_type": "webhook",
            "payload": {"url": "https://hooks.example.com/deliver"},
        },
    )
    task_id = created.json()["id"]

    response = await other_user_client.post(f"/v1/scheduler/{task_id}/trigger")
    assert response.status_code == 404
    assert calls == 0


@pytest.mark.asyncio
async def test_runtime_failure_is_persisted_and_returned(
    client: AsyncClient,
    monkeypatch,
):
    async def fail_action(task, *, db):
        raise scheduler_route.ScheduledActionError(
            "runtime refused",
            status_code=502,
            code="runtime_refused",
        )

    monkeypatch.setattr(scheduler_route, "_execute_task_action", fail_action)
    created = await client.post(
        "/v1/scheduler",
        json={"name": "failure", "interval_seconds": 60},
    )
    task_id = created.json()["id"]
    triggered = await client.post(f"/v1/scheduler/{task_id}/trigger")
    assert triggered.status_code == 502
    assert "runtime refused" in triggered.json()["detail"]

    task = (await client.get(f"/v1/scheduler/{task_id}")).json()
    assert task["status"] == "failed"
    assert task["run_count"] == task["success_count"] == 0
    assert task["failure_count"] == 1
    assert task["last_failed_at"] == task["last_finished_at"]
    assert task["last_error"] == "runtime refused"
    assert task["active_execution_id"] is None


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("http://127.0.0.1/hook", id="loopback"),
        pytest.param("http://[::1]/hook", id="ipv6-loopback"),
        pytest.param("http://169.254.169.254/latest/meta-data", id="metadata"),
        pytest.param("http://metadata.google.internal/computeMetadata/v1", id="metadata-host"),
        pytest.param("http://10.2.3.4/hook", id="private-ipv4"),
        pytest.param("ftp://example.com/hook", id="unsupported-scheme"),
        pytest.param("http://user:password@example.com/hook", id="userinfo"),
        pytest.param("https://example.com/hook#fragment", id="fragment"),
        pytest.param("https://2130706433/hook", id="integer-ipv4"),
        pytest.param("https://0177.0.0.1/hook", id="octal-ipv4"),
        pytest.param("https://0x7f000001/hook", id="hex-ipv4"),
        pytest.param("https://127.1/hook", id="short-ipv4"),
    ],
)
@pytest.mark.asyncio
async def test_webhook_registration_rejects_unsafe_and_ambiguous_targets(
    client: AsyncClient,
    db_session: AsyncSession,
    url: str,
):
    response = await client.post(
        "/v1/scheduler",
        json={
            "name": "unsafe-webhook",
            "interval_seconds": 60,
            "task_type": "webhook",
            "payload": {"url": url},
        },
    )
    assert response.status_code == 400
    assert "scheduler webhook target" in response.json()["detail"].lower()
    assert await _task_count(db_session) == 0


@pytest.mark.asyncio
async def test_webhook_registration_rejects_mixed_public_and_private_dns(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    async def mixed_dns(hostname: str, port: int) -> tuple[str, ...]:
        assert (hostname, port) == ("hooks.example.com", 443)
        return ("93.184.216.34", "10.20.30.40")

    monkeypatch.setattr(scheduler_webhook, "resolve_scheduler_webhook_ips", mixed_dns)
    response = await client.post(
        "/v1/scheduler",
        json={
            "name": "mixed-dns-webhook",
            "interval_seconds": 60,
            "task_type": "webhook",
            "payload": {"url": "https://hooks.example.com/deliver"},
        },
    )
    assert response.status_code == 400
    assert "10.20.30.40" in response.json()["detail"]
    assert await _task_count(db_session) == 0


@pytest.mark.asyncio
async def test_webhook_registration_and_update_preserve_safe_target(
    client: AsyncClient,
    monkeypatch,
):
    async def public_dns(hostname: str, port: int) -> tuple[str, ...]:
        assert hostname == "hooks.example.com"
        assert port in {443, 8443}
        return ("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946")

    monkeypatch.setattr(scheduler_webhook, "resolve_scheduler_webhook_ips", public_dns)
    url = "https://hooks.example.com:8443/deliver?tenant=public"
    created = await client.post(
        "/v1/scheduler",
        json={
            "name": "public-webhook",
            "interval_seconds": 60,
            "task_type": "webhook",
            "payload": {"url": url, "method": "PATCH", "body": {"ok": True}},
        },
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    original_payload = created.json()["payload"]

    rejected = await client.patch(
        f"/v1/scheduler/{task_id}",
        json={"payload": {"url": "http://127.0.0.1/admin"}},
    )
    assert rejected.status_code == 400
    assert (await client.get(f"/v1/scheduler/{task_id}")).json()["payload"] == original_payload


@pytest.mark.asyncio
async def test_due_webhook_reresolves_and_blocks_dns_rebinding(
    client: AsyncClient,
    db_session: AsyncSession,
    test_engine,
    monkeypatch,
):
    dns_answers = iter([("93.184.216.34",), ("169.254.169.254",)])
    transport_calls = 0

    async def changing_dns(hostname: str, port: int) -> tuple[str, ...]:
        assert (hostname, port) == ("hooks.example.com", 443)
        return next(dns_answers)

    async def capture_transport(target, payload):
        nonlocal transport_calls
        transport_calls += 1
        return 204

    monkeypatch.setattr(scheduler_webhook, "resolve_scheduler_webhook_ips", changing_dns)
    monkeypatch.setattr(scheduler_webhook, "_send_pinned_webhook_request", capture_transport)
    created = await client.post(
        "/v1/scheduler",
        json={
            "name": "rebound-webhook",
            "interval_seconds": 1,
            "task_type": "webhook",
            "payload": {"url": "https://hooks.example.com/deliver"},
        },
    )
    task_id = created.json()["id"]
    task = await _load_task(db_session, task_id)
    task.next_run = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()

    executions = await scheduler_route._schedule_due_tasks(
        datetime.now(timezone.utc),
        session_factory=_session_factory(test_engine),
    )
    await asyncio.gather(*executions)

    task = await _load_task(db_session, task_id)
    assert task.status == "failed"
    assert task.last_error_code == "unsafe_webhook_target"
    assert "cloud metadata destination" in task.last_error
    assert transport_calls == 0


@pytest.mark.asyncio
async def test_webhook_redirects_are_never_followed_or_retried(monkeypatch):
    request_calls: list[dict] = []
    resolution_calls = 0

    async def public_dns(hostname: str, port: int) -> tuple[str, ...]:
        nonlocal resolution_calls
        resolution_calls += 1
        return ("93.184.216.34",)

    class RedirectResponse:
        status = 302

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    class FakeSession:
        def __init__(self, *, connector, timeout, trust_env):
            assert trust_env is False
            self.connector = connector

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            await self.connector.close()

        def request(self, method, url, **kwargs):
            request_calls.append({"method": method, "url": url, **kwargs})
            return RedirectResponse()

    monkeypatch.setattr(scheduler_webhook, "resolve_scheduler_webhook_ips", public_dns)
    monkeypatch.setattr(scheduler_webhook.aiohttp, "ClientSession", FakeSession)
    payload = SchedulerWebhookPayload(
        url="https://hooks.example.com/redirect",
        max_retries=3,
    )
    with pytest.raises(
        scheduler_webhook.SchedulerWebhookDeliveryError,
        match="redirects are not followed",
    ):
        await scheduler_webhook.deliver_scheduler_webhook(payload)

    assert resolution_calls == 1
    assert len(request_calls) == 1
    assert request_calls[0]["allow_redirects"] is False
    assert request_calls[0]["url"] == payload.url


@pytest.mark.asyncio
async def test_webhook_retry_reresolves_and_fails_closed_on_rebinding(
    client: AsyncClient,
    monkeypatch,
):
    dns_answers = iter(
        [
            ("93.184.216.34",),
            ("93.184.216.34",),
            ("93.184.216.34", "127.0.0.1"),
        ]
    )
    transport_addresses: list[tuple[str, ...]] = []

    async def changing_dns(hostname: str, port: int) -> tuple[str, ...]:
        return next(dns_answers)

    async def fail_transport(target, payload):
        transport_addresses.append(tuple(address.compressed for address in target.addresses))
        raise scheduler_webhook.aiohttp.ClientConnectionError("connection reset")

    async def skip_retry_wait(attempt: int) -> None:
        assert attempt == 0

    monkeypatch.setattr(scheduler_webhook, "resolve_scheduler_webhook_ips", changing_dns)
    monkeypatch.setattr(scheduler_webhook, "_send_pinned_webhook_request", fail_transport)
    monkeypatch.setattr(scheduler_webhook, "_retry_wait", skip_retry_wait)
    created = await client.post(
        "/v1/scheduler",
        json={
            "name": "retry-rebind-webhook",
            "interval_seconds": 60,
            "task_type": "webhook",
            "payload": {
                "url": "https://hooks.example.com/deliver",
                "max_retries": 1,
            },
        },
    )
    task_id = created.json()["id"]
    triggered = await client.post(f"/v1/scheduler/{task_id}/trigger")

    assert triggered.status_code == 400
    assert "127.0.0.1" in triggered.json()["detail"]
    assert transport_addresses == [("93.184.216.34",)]
    task = (await client.get(f"/v1/scheduler/{task_id}")).json()
    assert task["failure_count"] == 1
    assert task["status"] == "failed"
