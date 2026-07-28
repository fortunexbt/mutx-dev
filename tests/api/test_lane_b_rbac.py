"""Focused persisted-principal RBAC matrix for lane-B control-plane routes."""

from datetime import datetime, timezone
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.jwt import create_access_token
from src.api.models import (
    Agent,
    AgentMetric,
    AgentRun,
    AgentStatus,
    Alert,
    AlertType,
    Deployment,
    DeploymentEvent,
    MutxRun,
    Swarm,
    UsageEvent,
    User,
)
from src.api.services.user_service import UserService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module_name", "side_effect_name", "method", "path", "payload"),
    [
        (
            "events",
            "process_ingest_event",
            "post",
            "/v1/events",
            {"event_type": "agent_action"},
        ),
        (
            "ingest",
            "process_ingest_event",
            "post",
            "/v1/ingest/events",
            {"event_type": "agent_action"},
        ),
        (
            "documents",
            "create_document_job",
            "post",
            "/v1/documents/jobs",
            {"template_id": "document_analysis", "execution_mode": "local"},
        ),
        (
            "approvals",
            "create_approval_record",
            "post",
            "/v1/approvals",
            {
                "agent_id": "agent-rbac",
                "session_id": "session-rbac",
                "action_type": "deploy",
            },
        ),
    ],
)
async def test_viewer_mutations_are_denied_before_route_side_effects(
    client: AsyncClient,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    side_effect_name: str,
    method: str,
    path: str,
    payload: dict[str, object],
) -> None:
    route_module = __import__(f"src.api.routes.{module_name}", fromlist=[module_name])
    side_effect_called = False

    def forbidden_side_effect(*_args, **_kwargs):
        nonlocal side_effect_called
        side_effect_called = True
        raise AssertionError("route side effect ran before RBAC denial")

    test_user.roles = ["VIEWER"]
    test_user.plan = "STARTER"
    monkeypatch.setattr(route_module, side_effect_name, forbidden_side_effect)

    response = await client.request(method, path, json=payload)

    assert response.status_code == 403
    assert side_effect_called is False


@pytest.mark.asyncio
async def test_developer_can_create_and_read_an_owned_run(
    client: AsyncClient,
    test_agent: Agent,
    test_user,
) -> None:
    test_user.roles = ["DEVELOPER"]

    created = await client.post(
        "/v1/runs",
        json={
            "agent_id": str(test_agent.id),
            "status": "completed",
            "input_text": "RBAC owner test",
        },
    )

    assert created.status_code == 201
    fetched = await client.get(f"/v1/runs/{created.json()['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["agent_id"] == str(test_agent.id)


@pytest.mark.asyncio
async def test_viewer_can_read_an_owned_run(
    client: AsyncClient,
    db_session: AsyncSession,
    test_agent: Agent,
    test_user,
) -> None:
    owned_run = AgentRun(
        id=uuid.uuid4(),
        agent_id=test_agent.id,
        user_id=test_user.id,
        status="completed",
    )
    db_session.add(owned_run)
    await db_session.commit()
    test_user.roles = ["VIEWER"]

    response = await client.get(f"/v1/runs/{owned_run.id}")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_developer_and_admin_cannot_cross_tenant_run_ownership(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    other_user,
) -> None:
    foreign_agent = Agent(
        id=uuid.uuid4(),
        user_id=other_user.id,
        name="foreign-rbac-agent",
        status=AgentStatus.RUNNING.value,
    )
    foreign_run = AgentRun(
        id=uuid.uuid4(),
        agent=foreign_agent,
        user_id=other_user.id,
        status="completed",
    )
    db_session.add_all([foreign_agent, foreign_run])
    await db_session.commit()

    for role in ("DEVELOPER", "ADMIN"):
        test_user.roles = [role]
        response = await client.get(f"/v1/runs/{foreign_run.id}")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_telemetry_is_internal_admin_only_and_denied_before_tenant_reconfiguration(
    client: AsyncClient,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.routes.telemetry as telemetry_route

    async def get_current_config(_db, *, owner_id):
        assert owner_id == test_user.id
        return {
            "endpoint": None,
            "protocol": None,
            "configured": False,
            "updated_at": None,
        }

    async def get_telemetry_health(_db, *, owner_id):
        assert owner_id == test_user.id
        return {
            "configured": True,
            "endpoint_reachable": True,
            "using_grpc": True,
            "endpoint": "http://8.8.8.8:4317",
            "status": "reachable",
            "checked_at": None,
            "failure_reason": None,
        }

    monkeypatch.setattr(telemetry_route, "get_current_config", get_current_config)
    monkeypatch.setattr(telemetry_route, "get_telemetry_health", get_telemetry_health)
    monkeypatch.setattr(
        telemetry_route,
        "get_runtime_telemetry_status",
        lambda: (True, "console"),
    )
    configured: list[str] = []

    async def configure_telemetry_backend(
        _db,
        *,
        owner_id,
        otlp_endpoint: str,
        protocol: str,
    ):
        assert owner_id == test_user.id
        configured.append(f"{protocol}:{otlp_endpoint}")
        return {
            "endpoint": otlp_endpoint,
            "protocol": protocol,
            "configured": True,
            "updated_at": datetime.now(timezone.utc),
        }

    monkeypatch.setattr(
        telemetry_route,
        "configure_telemetry_backend",
        configure_telemetry_backend,
    )

    for role in ("VIEWER", "DEVELOPER", "AUDIT_ADMIN"):
        test_user.roles = [role]
        denied_read = await client.get("/v1/telemetry/config")
        denied_write = await client.post(
            "/v1/telemetry/config",
            json={"otlp_endpoint": "http://8.8.8.8:4317", "protocol": "grpc"},
        )
        assert denied_read.status_code == 403
        assert denied_write.status_code == 403
        assert configured == []

    test_user.roles = ["ADMIN"]
    test_user.email = "external@example.com"
    external_admin = await client.get("/v1/telemetry/config")
    assert external_admin.status_code == 403

    test_user.email = "test@mutx.dev"
    allowed = await client.get("/v1/telemetry/config")
    configured_response = await client.post(
        "/v1/telemetry/config",
        json={"otlp_endpoint": "http://8.8.8.8:4317", "protocol": "grpc"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["otel_enabled"] is True
    assert configured_response.status_code == 200
    assert configured == ["grpc:http://8.8.8.8:4317"]


@pytest.mark.asyncio
async def test_only_root_platform_probes_remain_public(client_no_auth: AsyncClient) -> None:
    for path in ("/", "/health", "/ready", "/metrics"):
        response = await client_no_auth.get(path)
        assert response.status_code == 200, (path, response.text)

    for path in (
        "/v1/monitoring/health",
        "/v1/telemetry/health",
        "/v1/governance/credentials/health",
    ):
        response = await client_no_auth.get(path)
        assert response.status_code == 401, (path, response.text)


@pytest.mark.asyncio
async def test_monitoring_alerts_are_role_gated_owner_scoped_and_opaque(
    client: AsyncClient,
    db_session: AsyncSession,
    test_agent: Agent,
    test_user,
    other_user,
) -> None:
    foreign_agent = Agent(
        id=uuid.uuid4(),
        user_id=other_user.id,
        name="foreign-alert-agent",
        status=AgentStatus.RUNNING.value,
    )
    owned_alert = Alert(
        id=uuid.uuid4(),
        agent_id=test_agent.id,
        type=AlertType.AGENT_DOWN,
        message="Owned alert",
    )
    foreign_alert = Alert(
        id=uuid.uuid4(),
        agent=foreign_agent,
        type=AlertType.AGENT_DOWN,
        message="Foreign alert",
    )
    db_session.add_all([foreign_agent, owned_alert, foreign_alert])
    await db_session.commit()

    test_user.roles = ["VIEWER"]
    listed = await client.get("/v1/monitoring/alerts")
    viewer_mutation = await client.patch(
        f"/v1/monitoring/alerts/{owned_alert.id}",
        json={"resolved": True},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [str(owned_alert.id)]
    assert viewer_mutation.status_code == 403
    await db_session.refresh(owned_alert)
    assert owned_alert.resolved is False

    test_user.roles = ["DEVELOPER"]
    resolved = await client.patch(
        f"/v1/monitoring/alerts/{owned_alert.id}",
        json={"resolved": True},
    )
    assert resolved.status_code == 200

    missing_id = uuid.uuid4()
    for role in ("DEVELOPER", "ADMIN"):
        test_user.roles = [role]
        foreign = await client.patch(
            f"/v1/monitoring/alerts/{foreign_alert.id}",
            json={"resolved": True},
        )
        missing = await client.patch(
            f"/v1/monitoring/alerts/{missing_id}",
            json={"resolved": True},
        )
        assert foreign.status_code == missing.status_code == 404

    test_user.roles = ["AUDIT_ADMIN"]
    assert (await client.get("/v1/monitoring/alerts")).status_code == 403


@pytest.mark.asyncio
async def test_monitoring_health_is_explicitly_global_internal_admin_only(
    client: AsyncClient,
    test_user,
) -> None:
    for role in ("VIEWER", "DEVELOPER", "AUDIT_ADMIN"):
        test_user.roles = [role]
        assert (await client.get("/v1/monitoring/health")).status_code == 403

    test_user.roles = ["ADMIN"]
    test_user.email = "external@example.com"
    assert (await client.get("/v1/monitoring/health")).status_code == 403

    test_user.email = "test@mutx.dev"
    assert (await client.get("/v1/monitoring/health")).status_code == 200


def test_analytics_cost_attribution_never_trusts_foreign_agent_labels() -> None:
    from src.api.routes.analytics import _resolve_usage_agent_key

    owned_agent_id = str(uuid.uuid4())
    foreign_agent_id = str(uuid.uuid4())
    owned_agent_ids = {owned_agent_id}

    assert (
        _resolve_usage_agent_key(
            event_type="api_call",
            resource_type=None,
            resource_id=None,
            event_metadata=f'{{"agent_id":"{foreign_agent_id}"}}',
            owned_agent_ids=owned_agent_ids,
        )
        is None
    )
    assert (
        _resolve_usage_agent_key(
            event_type="api_call",
            resource_type="agent",
            resource_id=foreign_agent_id,
            event_metadata=None,
            owned_agent_ids=owned_agent_ids,
        )
        is None
    )
    assert (
        _resolve_usage_agent_key(
            event_type="api_call",
            resource_type=None,
            resource_id=None,
            event_metadata=f'{{"agent_id":"{owned_agent_id}"}}',
            owned_agent_ids=owned_agent_ids,
        )
        == owned_agent_id
    )


@pytest.mark.asyncio
async def test_analytics_agent_summary_is_owner_scoped_for_viewer_developer_and_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    test_agent: Agent,
    test_user,
    other_user,
) -> None:
    foreign_agent = Agent(
        id=uuid.uuid4(),
        user_id=other_user.id,
        name="foreign-analytics-agent",
        status=AgentStatus.RUNNING.value,
    )
    db_session.add(foreign_agent)
    await db_session.commit()
    missing_id = uuid.uuid4()

    for role in ("VIEWER", "DEVELOPER", "ADMIN"):
        test_user.roles = [role]
        owned = await client.get(f"/v1/analytics/agents/{test_agent.id}/summary")
        foreign = await client.get(f"/v1/analytics/agents/{foreign_agent.id}/summary")
        missing = await client.get(f"/v1/analytics/agents/{missing_id}/summary")
        assert owned.status_code == 200
        assert foreign.status_code == missing.status_code == 404

    test_user.roles = ["AUDIT_ADMIN"]
    assert (await client.get(f"/v1/analytics/agents/{test_agent.id}/summary")).status_code == 403


@pytest.mark.asyncio
async def test_financial_analytics_are_explicitly_global_internal_admin_only(
    client: AsyncClient,
    test_user,
) -> None:
    paths = (
        "/v1/analytics/revenue",
        "/v1/analytics/subscriptions",
        "/v1/analytics/payments",
    )
    for role in ("VIEWER", "DEVELOPER", "AUDIT_ADMIN"):
        test_user.roles = [role]
        for path in paths:
            assert (await client.get(path)).status_code == 403

    test_user.roles = ["ADMIN"]
    test_user.email = "external@example.com"
    for path in paths:
        assert (await client.get(path)).status_code == 403

    test_user.email = "test@mutx.dev"
    for path in paths:
        response = await client.get(path)
        assert response.status_code == 200, (path, response.text)


@pytest.mark.asyncio
async def test_governance_attestations_redact_global_runtime_state_for_non_admins(
    client: AsyncClient,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cli.faramesh_runtime as faramesh_runtime

    class FakeHealth:
        daemon_reachable = True
        socket_reachable = True
        policy_loaded = True
        version = "global-version"
        policy_name = "global-policy"

    class FakeSnapshot:
        decisions_total = 42
        pending_approvals = 7
        status = "healthy"

    monkeypatch.setattr(faramesh_runtime, "get_faramesh_health", lambda: FakeHealth())
    monkeypatch.setattr(faramesh_runtime, "collect_faramesh_snapshot", lambda: FakeSnapshot())

    for role in ("VIEWER", "DEVELOPER"):
        test_user.roles = [role]
        response = await client.get("/v1/governance/attestations")
        assert response.status_code == 200
        assert response.json()["runtime"] == {
            "daemon_reachable": False,
            "socket_reachable": False,
            "policy_loaded": False,
            "version": None,
            "policy_name": None,
            "decisions_total": 0,
            "pending_approvals": 0,
            "status": "restricted",
        }

    test_user.roles = ["ADMIN"]
    admin_response = await client.get("/v1/governance/attestations")
    assert admin_response.status_code == 200
    assert admin_response.json()["runtime"]["decisions_total"] == 42
    assert admin_response.json()["runtime"]["pending_approvals"] == 7
    assert admin_response.json()["runtime"]["version"] == "global-version"


@pytest.mark.asyncio
async def test_observability_eval_and_provenance_are_role_gated_owner_scoped_and_opaque(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    other_user,
) -> None:
    test_user.roles = ["DEVELOPER"]
    created = await client.post(
        "/v1/observability/runs",
        json={"agent_id": "owned-observability-agent", "status": "completed"},
    )
    assert created.status_code == 201
    owned_run_id = created.json()["id"]
    submitted_eval = await client.post(
        f"/v1/observability/runs/{owned_run_id}/eval",
        json={"pass": True, "score": 100},
    )
    assert submitted_eval.status_code == 201

    foreign_run = MutxRun(
        id="foreign-observability-run",
        agent_id="foreign-observability-agent",
        user_id=other_user.id,
        status="completed",
    )
    db_session.add(foreign_run)
    await db_session.commit()
    missing_run_id = "missing-observability-run"

    test_user.roles = ["VIEWER"]
    assert (await client.get(f"/v1/observability/runs/{owned_run_id}/eval")).status_code == 200
    assert (
        await client.get(f"/v1/observability/runs/{owned_run_id}/provenance")
    ).status_code == 200
    denied_eval_update = await client.post(
        f"/v1/observability/runs/{owned_run_id}/eval",
        json={"pass": False, "score": 0},
    )
    assert denied_eval_update.status_code == 403
    unchanged_eval = await client.get(f"/v1/observability/runs/{owned_run_id}/eval")
    assert unchanged_eval.json()["score"] == 100

    for role in ("VIEWER", "DEVELOPER", "ADMIN"):
        test_user.roles = [role]
        for suffix in ("eval", "provenance"):
            foreign = await client.get(f"/v1/observability/runs/{foreign_run.id}/{suffix}")
            missing = await client.get(f"/v1/observability/runs/{missing_run_id}/{suffix}")
            assert foreign.status_code == missing.status_code == 404

    test_user.roles = ["ADMIN"]
    admin_eval_update = await client.post(
        f"/v1/observability/runs/{owned_run_id}/eval",
        json={"pass": True, "score": 95},
    )
    assert admin_eval_update.status_code == 201

    for run_id in (foreign_run.id, missing_run_id):
        opaque_mutation = await client.post(
            f"/v1/observability/runs/{run_id}/eval",
            json={"pass": True, "score": 95},
        )
        assert opaque_mutation.status_code == 404

    test_user.roles = ["AUDIT_ADMIN"]
    assert (await client.get(f"/v1/observability/runs/{owned_run_id}/eval")).status_code == 403
    assert (
        await client.get(f"/v1/observability/runs/{owned_run_id}/provenance")
    ).status_code == 403


@pytest.mark.asyncio
async def test_swarms_blueprint_patch_and_delete_role_and_owner_matrix(
    client: AsyncClient,
    db_session: AsyncSession,
    test_agent: Agent,
    test_user,
    other_user,
) -> None:
    test_user.roles = ["VIEWER"]
    assert (await client.get("/v1/swarms/blueprints")).status_code == 200

    test_user.roles = ["AUDIT_ADMIN"]
    assert (await client.get("/v1/swarms/blueprints")).status_code == 403

    test_user.roles = ["DEVELOPER"]
    created = await client.post(
        "/v1/swarms",
        json={"name": "owned-lane-b-swarm", "agent_ids": [str(test_agent.id)]},
    )
    assert created.status_code == 201
    owned_swarm_id = created.json()["id"]

    test_user.roles = ["VIEWER"]
    denied_patch = await client.patch(
        f"/v1/swarms/{owned_swarm_id}",
        json={"name": "viewer-must-not-write"},
    )
    denied_delete = await client.delete(f"/v1/swarms/{owned_swarm_id}")
    assert denied_patch.status_code == denied_delete.status_code == 403

    test_user.roles = ["DEVELOPER"]
    updated = await client.patch(
        f"/v1/swarms/{owned_swarm_id}",
        json={"name": "developer-owned-update"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "developer-owned-update"

    foreign_swarm = Swarm(
        id=uuid.uuid4(),
        user_id=other_user.id,
        name="foreign-swarm",
        agent_ids=[],
        min_replicas=1,
        max_replicas=10,
    )
    db_session.add(foreign_swarm)
    await db_session.commit()
    missing_swarm_id = uuid.uuid4()

    for role in ("DEVELOPER", "ADMIN"):
        test_user.roles = [role]
        for method, resource_id in (
            ("PATCH", foreign_swarm.id),
            ("PATCH", missing_swarm_id),
            ("DELETE", foreign_swarm.id),
            ("DELETE", missing_swarm_id),
        ):
            response = await client.request(
                method,
                f"/v1/swarms/{resource_id}",
                json={"name": "must-not-change"} if method == "PATCH" else None,
            )
            assert response.status_code == 404

    test_user.roles = ["ADMIN"]
    deleted = await client.delete(f"/v1/swarms/{owned_swarm_id}")
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_ingest_deployment_and_metrics_are_authorized_before_side_effects_and_opaque(
    client: AsyncClient,
    db_session: AsyncSession,
    test_agent: Agent,
    test_deployment: Deployment,
    test_user,
    other_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.routes.ingest as ingest_route

    async def no_webhook(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(ingest_route, "trigger_deployment_event", no_webhook)
    monkeypatch.setattr(ingest_route, "trigger_webhook_event", no_webhook)

    foreign_agent = Agent(
        id=uuid.uuid4(),
        user_id=other_user.id,
        name="foreign-ingest-agent",
        status=AgentStatus.RUNNING.value,
    )
    foreign_deployment = Deployment(
        id=uuid.uuid4(),
        agent=foreign_agent,
        status="running",
        replicas=1,
    )
    db_session.add_all([foreign_agent, foreign_deployment])
    await db_session.commit()

    event_count_before = await db_session.scalar(select(func.count()).select_from(DeploymentEvent))
    metric_count_before = await db_session.scalar(select(func.count()).select_from(AgentMetric))
    test_user.roles = ["VIEWER"]
    denied_deployment = await client.post(
        "/v1/ingest/deployment",
        json={
            "deployment_id": str(test_deployment.id),
            "event": "healthy",
            "status": "running",
        },
    )
    denied_metrics = await client.post(
        "/v1/ingest/metrics",
        json={"agent_id": str(test_agent.id), "cpu_usage": 10, "memory_usage": 20},
    )
    assert denied_deployment.status_code == denied_metrics.status_code == 403
    assert (
        await db_session.scalar(select(func.count()).select_from(DeploymentEvent))
        == event_count_before
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(AgentMetric))
        == metric_count_before
    )

    test_user.roles = ["DEVELOPER"]
    accepted_deployment = await client.post(
        "/v1/ingest/deployment",
        json={
            "deployment_id": str(test_deployment.id),
            "event": "healthy",
            "status": "running",
        },
    )
    accepted_metrics = await client.post(
        "/v1/ingest/metrics",
        json={"agent_id": str(test_agent.id), "cpu_usage": 10, "memory_usage": 20},
    )
    assert accepted_deployment.status_code == accepted_metrics.status_code == 200

    missing_deployment_id = uuid.uuid4()
    missing_agent_id = uuid.uuid4()
    event_count_after_owned = await db_session.scalar(
        select(func.count()).select_from(DeploymentEvent)
    )
    metric_count_after_owned = await db_session.scalar(
        select(func.count()).select_from(AgentMetric)
    )
    for role in ("DEVELOPER", "ADMIN"):
        test_user.roles = [role]
        for deployment_id in (foreign_deployment.id, missing_deployment_id):
            response = await client.post(
                "/v1/ingest/deployment",
                json={
                    "deployment_id": str(deployment_id),
                    "event": "healthy",
                    "status": "running",
                },
            )
            assert response.status_code == 404
        for agent_id in (foreign_agent.id, missing_agent_id):
            response = await client.post(
                "/v1/ingest/metrics",
                json={"agent_id": str(agent_id), "cpu_usage": 10, "memory_usage": 20},
            )
            assert response.status_code == 404

    assert (
        await db_session.scalar(select(func.count()).select_from(DeploymentEvent))
        == event_count_after_owned
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(AgentMetric))
        == metric_count_after_owned
    )

    test_user.roles = ["ADMIN"]
    admin_metrics = await client.post(
        "/v1/ingest/metrics",
        json={"agent_id": str(test_agent.id), "cpu_usage": 30, "memory_usage": 40},
    )
    assert admin_metrics.status_code == 200

    test_user.roles = ["AUDIT_ADMIN"]
    audit_denied = await client.post(
        "/v1/ingest/metrics",
        json={"agent_id": str(test_agent.id), "cpu_usage": 50, "memory_usage": 60},
    )
    assert audit_denied.status_code == 403


@pytest.mark.asyncio
async def test_reasoning_role_inheritance_and_opaque_tenant_boundary(
    client: AsyncClient,
    other_user_client: AsyncClient,
    test_user,
    other_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.api.config import get_settings

    monkeypatch.setattr(get_settings(), "reasoning_enabled", True)
    create_payload = {
        "template_id": "autoreason_refine",
        "execution_mode": "local",
        "parameters": {"task_prompt": "Review tenant boundaries"},
    }

    test_user.roles = ["VIEWER"]
    assert (await client.get("/v1/reasoning/templates")).status_code == 200
    assert (await client.get("/v1/reasoning/jobs")).status_code == 200
    assert (await client.post("/v1/reasoning/jobs", json=create_payload)).status_code == 403

    other_user.roles = ["DEVELOPER"]
    foreign_created = await other_user_client.post("/v1/reasoning/jobs", json=create_payload)
    assert foreign_created.status_code == 201
    foreign_job_id = foreign_created.json()["id"]
    missing_job_id = uuid.uuid4()

    for role in ("VIEWER", "DEVELOPER", "ADMIN"):
        test_user.roles = [role]
        foreign_read = await client.get(f"/v1/reasoning/jobs/{foreign_job_id}")
        missing_read = await client.get(f"/v1/reasoning/jobs/{missing_job_id}")
        assert foreign_read.status_code == missing_read.status_code == 404

    test_user.roles = ["DEVELOPER"]
    foreign_mutation = await client.post(
        f"/v1/reasoning/jobs/{foreign_job_id}/events",
        json={"event_type": "reasoning.completed", "status": "completed"},
    )
    missing_mutation = await client.post(
        f"/v1/reasoning/jobs/{missing_job_id}/events",
        json={"event_type": "reasoning.completed", "status": "completed"},
    )
    assert foreign_mutation.status_code == missing_mutation.status_code == 404

    test_user.roles = ["ADMIN"]
    admin_created = await client.post("/v1/reasoning/jobs", json=create_payload)
    assert admin_created.status_code == 201

    test_user.roles = ["AUDIT_ADMIN"]
    assert (await client.get("/v1/reasoning/templates")).status_code == 403
    assert (await client.get("/v1/reasoning/jobs")).status_code == 403
    assert (await client.post("/v1/reasoning/jobs", json=create_payload)).status_code == 403


@pytest.mark.asyncio
async def test_runtime_owner_state_and_global_governance_role_matrix(
    client: AsyncClient,
    other_user_client: AsyncClient,
    test_user,
    other_user,
) -> None:
    provider_path = "/v1/runtime/providers/lane-b-provider"
    viewer_payload = {"label": "Viewer must not persist", "status": "healthy"}

    test_user.roles = ["VIEWER"]
    assert (await client.get(provider_path)).status_code == 200
    assert (await client.put(provider_path, json=viewer_payload)).status_code == 403
    unchanged = await client.get(provider_path)
    assert unchanged.status_code == 200
    assert unchanged.json()["label"] != viewer_payload["label"]
    assert (await client.get("/v1/runtime/governance/status")).status_code == 403

    test_user.roles = ["DEVELOPER"]
    developer_update = await client.put(
        provider_path,
        json={"label": "Developer tenant", "status": "healthy"},
    )
    assert developer_update.status_code == 200
    assert (await client.get("/v1/runtime/governance/status")).status_code == 403

    other_user.roles = ["DEVELOPER"]
    other_update = await other_user_client.put(
        provider_path,
        json={"label": "Other tenant", "status": "healthy"},
    )
    assert other_update.status_code == 200
    assert (await client.get(provider_path)).json()["label"] == "Developer tenant"
    assert (await other_user_client.get(provider_path)).json()["label"] == "Other tenant"

    test_user.roles = ["ADMIN"]
    test_user.email = "external@example.com"
    assert (await client.get("/v1/runtime/governance/status")).status_code == 403

    test_user.email = "test@mutx.dev"
    admin_update = await client.put(
        provider_path,
        json={"label": "Admin-owned tenant", "status": "healthy"},
    )
    assert admin_update.status_code == 200
    assert (await client.get("/v1/runtime/governance/status")).status_code == 200

    test_user.roles = ["AUDIT_ADMIN"]
    assert (await client.get(provider_path)).status_code == 403
    assert (
        await client.put(provider_path, json={"label": "Audit", "status": "healthy"})
    ).status_code == 403
    assert (await client.get("/v1/runtime/governance/status")).status_code == 403


@pytest.mark.asyncio
async def test_usage_mutation_admin_inheritance_and_opaque_owner_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    other_user,
) -> None:
    count_before = await db_session.scalar(select(func.count()).select_from(UsageEvent))
    test_user.roles = ["VIEWER"]
    assert (await client.get("/v1/usage/events")).status_code == 200
    viewer_write = await client.post(
        "/v1/usage/events",
        json={"event_type": "viewer_must_not_write"},
    )
    assert viewer_write.status_code == 403
    assert await db_session.scalar(select(func.count()).select_from(UsageEvent)) == count_before

    test_user.roles = ["DEVELOPER"]
    developer_event = await client.post(
        "/v1/usage/events",
        json={"event_type": "developer_owned_usage"},
    )
    assert developer_event.status_code == 201
    assert developer_event.json()["user_id"] == str(test_user.id)

    test_user.roles = ["ADMIN"]
    admin_event = await client.post(
        "/v1/usage/events",
        json={"event_type": "admin_owned_usage"},
    )
    assert admin_event.status_code == 201
    assert admin_event.json()["user_id"] == str(test_user.id)

    foreign_event = UsageEvent(
        id=uuid.uuid4(),
        user_id=other_user.id,
        event_type="foreign_usage",
    )
    db_session.add(foreign_event)
    await db_session.commit()
    missing_event_id = uuid.uuid4()
    for role in ("VIEWER", "DEVELOPER", "ADMIN"):
        test_user.roles = [role]
        foreign = await client.get(f"/v1/usage/events/{foreign_event.id}")
        missing = await client.get(f"/v1/usage/events/{missing_event_id}")
        assert foreign.status_code == missing.status_code == 404

    test_user.roles = ["AUDIT_ADMIN"]
    assert (await client.get("/v1/usage/events")).status_code == 403
    assert (
        await client.post(
            "/v1/usage/events",
            json={"event_type": "audit_must_not_write"},
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_bearer_and_managed_api_key_reload_persisted_roles_and_key_revocation(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
    test_user,
) -> None:
    user_id = test_user.id
    access_token, _ = create_access_token(user_id)
    api_key_record, managed_api_key = await UserService(db_session).create_api_key(
        user_id,
        "lane-b-role-reload",
    )
    managed_api_key_id = api_key_record.id
    credentials = (
        {"Authorization": f"Bearer {access_token}"},
        {"Authorization": f"Bearer {managed_api_key}"},
    )

    async def persist_roles(*roles: str) -> None:
        await db_session.execute(
            update(User)
            .where(User.id == user_id)
            .values(roles=list(roles))
            .execution_options(synchronize_session=False)
        )
        await db_session.commit()
        db_session.expire_all()

    for credential_index, headers in enumerate(credentials):
        await persist_roles("DEVELOPER")
        developer_write = await client_no_auth.post(
            "/v1/usage/events",
            headers=headers,
            json={"event_type": f"credential_{credential_index}_developer"},
        )
        assert developer_write.status_code == 201

        await persist_roles("VIEWER")
        viewer_read = await client_no_auth.get("/v1/usage/events", headers=headers)
        revoked_write = await client_no_auth.post(
            "/v1/usage/events",
            headers=headers,
            json={"event_type": f"credential_{credential_index}_revoked_write"},
        )
        assert viewer_read.status_code == 200
        assert revoked_write.status_code == 403

        await persist_roles("AUDIT_ADMIN")
        audit_read = await client_no_auth.get("/v1/usage/events", headers=headers)
        audit_write = await client_no_auth.post(
            "/v1/usage/events",
            headers=headers,
            json={"event_type": f"credential_{credential_index}_audit"},
        )
        assert audit_read.status_code == audit_write.status_code == 403

        await persist_roles("ADMIN")
        admin_read = await client_no_auth.get("/v1/usage/events", headers=headers)
        admin_write = await client_no_auth.post(
            "/v1/usage/events",
            headers=headers,
            json={"event_type": f"credential_{credential_index}_admin"},
        )
        assert admin_read.status_code == 200
        assert admin_write.status_code == 201

    await db_session.execute(
        update(api_key_record.__class__)
        .where(api_key_record.__class__.id == managed_api_key_id)
        .values(is_active=False)
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    revoked_key_response = await client_no_auth.get(
        "/v1/usage/events",
        headers={"Authorization": f"Bearer {managed_api_key}"},
    )
    assert revoked_key_response.status_code == 401
