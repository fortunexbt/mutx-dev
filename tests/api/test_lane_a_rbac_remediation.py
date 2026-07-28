"""Regression coverage for lane A authorization remediation."""

import json
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.jwt import create_access_token
from src.api.models import (
    APIKey,
    Agent,
    AgentLog,
    AgentMetric,
    AgentResourceUsage,
    AgentType,
    AgentVersion,
    Command,
    Deployment,
    DeploymentEvent,
    UserSetting,
)


async def _row_counts(db_session: AsyncSession) -> dict[type, int]:
    models = (
        Agent,
        AgentLog,
        AgentMetric,
        AgentResourceUsage,
        AgentVersion,
        APIKey,
        Deployment,
        DeploymentEvent,
        UserSetting,
    )
    return {
        model: await db_session.scalar(select(func.count()).select_from(model)) or 0
        for model in models
    }


@pytest.mark.asyncio
async def test_viewer_mutations_never_reach_control_plane_side_effects(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    test_agent,
    test_deployment,
):
    test_user.roles = ["VIEWER"]
    test_agent.type = AgentType.OPENCLAW
    test_agent.config = json.dumps({"skills": []})
    await db_session.commit()
    original_config = test_agent.config
    original_replicas = test_deployment.replicas
    counts_before = await _row_counts(db_session)
    missing_id = uuid.uuid4()
    now = datetime.now(timezone.utc).isoformat()
    custom_template = {
        "id": "viewer-template",
        "name": "Viewer Template",
        "system_prompt": "Viewer requests must not create this template.",
    }

    requests = [
        ("POST", "/v1/agents/register", {"name": "viewer-runtime"}),
        ("POST", "/v1/agents", {"name": "viewer-agent"}),
        (
            "PATCH",
            f"/v1/agents/{test_agent.id}/config",
            {"config": {"model": "gpt-4o-mini"}},
        ),
        ("DELETE", f"/v1/agents/{test_agent.id}", None),
        ("POST", f"/v1/agents/{test_agent.id}/deploy", None),
        ("POST", f"/v1/agents/{test_agent.id}/stop", None),
        (
            "POST",
            f"/v1/agents/{test_agent.id}/resource-usage",
            {"period_start": now, "total_tokens": 1},
        ),
        ("POST", f"/v1/agents/{test_agent.id}/rollback", {"version": 1}),
        ("POST", "/v1/api-keys", {"name": "viewer-key"}),
        ("DELETE", f"/v1/api-keys/{missing_id}", None),
        ("POST", f"/v1/api-keys/{missing_id}/rotate", None),
        ("POST", f"/v1/assistant/{test_agent.id}/skills/web_search", None),
        ("DELETE", f"/v1/assistant/{test_agent.id}/skills/web_search", None),
        (
            "POST",
            "/v1/clawhub/install",
            {"agent_id": str(test_agent.id), "skill_id": "web_search"},
        ),
        (
            "POST",
            "/v1/clawhub/install-bundle",
            {
                "agent_id": str(test_agent.id),
                "bundle_id": "orchestra-research-foundation",
            },
        ),
        (
            "POST",
            "/v1/clawhub/uninstall",
            {"agent_id": str(test_agent.id), "skill_id": "web_search"},
        ),
        (
            "POST",
            f"/v1/deployments/{test_deployment.id}/scale",
            {"replicas": original_replicas + 1},
        ),
        ("DELETE", f"/v1/deployments/{test_deployment.id}", None),
        (
            "POST",
            "/v1/deployments",
            {"agent_id": str(test_agent.id), "replicas": 1},
        ),
        ("POST", f"/v1/deployments/{test_deployment.id}/restart", None),
        (
            "POST",
            f"/v1/deployments/{test_deployment.id}/rollback",
            {"version": 1},
        ),
        ("PUT", "/v1/templates/state", {"pinned_template_ids": ["personal_assistant"]}),
        ("POST", "/v1/templates/custom", custom_template),
        ("PUT", "/v1/templates/custom/viewer-template", {"name": "Mutated"}),
        ("DELETE", "/v1/templates/custom/viewer-template", None),
        (
            "POST",
            "/v1/templates/personal_assistant/clone",
            {"id": "viewer-template-clone"},
        ),
        (
            "POST",
            "/v1/templates/personal_assistant/deploy",
            {"name": "Viewer Assistant"},
        ),
    ]

    for method, path, payload in requests:
        response = await client.request(method, path, json=payload)
        assert response.status_code == 403, (method, path, response.text)

    await db_session.refresh(test_agent)
    await db_session.refresh(test_deployment)
    assert test_agent.config == original_config
    assert test_deployment.replicas == original_replicas
    assert await _row_counts(db_session) == counts_before


@pytest.mark.asyncio
async def test_machine_runtime_endpoints_use_production_agent_key_authentication(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
    test_user,
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    access_token, _ = create_access_token(test_user.id)
    human_headers = {"Authorization": f"Bearer {access_token}"}

    registered = await client_no_auth.post(
        "/v1/agents/register",
        headers=human_headers,
        json={"name": "production-path-runtime"},
    )
    assert registered.status_code == 200
    agent_id = registered.json()["agent_id"]
    agent_key = registered.json()["api_key"]
    agent_headers = {"Authorization": f"Bearer {agent_key}"}
    command = Command(
        agent_id=uuid.UUID(agent_id),
        action="refresh",
        parameters={"source": "rbac-remediation"},
        status="pending",
    )
    db_session.add(command)
    await db_session.commit()
    await db_session.refresh(command)
    now = datetime.now(timezone.utc).isoformat()

    machine_requests = [
        (
            "POST",
            "/v1/agents/heartbeat",
            {"agent_id": agent_id, "status": "running", "timestamp": now},
            None,
        ),
        (
            "POST",
            "/v1/agents/metrics",
            {"agent_id": agent_id, "cpu_usage": 0.25, "timestamp": now},
            None,
        ),
        (
            "POST",
            "/v1/agents/logs",
            {"agent_id": agent_id, "message": "machine-authenticated", "timestamp": now},
            None,
        ),
        ("GET", "/v1/agents/commands", None, {"agent_id": agent_id}),
        (
            "POST",
            "/v1/agents/commands/acknowledge",
            {
                "command_id": str(command.id),
                "agent_id": agent_id,
                "success": True,
                "completed_at": now,
            },
            None,
        ),
        ("GET", f"/v1/agents/{agent_id}/status", None, None),
    ]

    for method, path, payload, params in machine_requests:
        rejected = await client_no_auth.request(
            method,
            path,
            headers=human_headers,
            json=payload,
            params=params,
        )
        assert rejected.status_code == 401, (method, path, rejected.text)

    for method, path, payload, params in machine_requests:
        accepted = await client_no_auth.request(
            method,
            path,
            headers=agent_headers,
            json=payload,
            params=params,
        )
        assert accepted.status_code == 200, (method, path, accepted.text)


async def _create_assistant_agent(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> Agent:
    agent = Agent(
        name="Tenant Assistant",
        description="RBAC remediation assistant",
        type=AgentType.OPENCLAW,
        config=json.dumps(
            {
                "assistant_id": "tenant-assistant",
                "template": "personal_assistant",
                "workspace": "tenant-workspace",
            }
        ),
        user_id=user_id,
        status="running",
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["VIEWER", "DEVELOPER"])
async def test_owner_assistant_health_and_overview_redact_shared_host_details(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    tmp_path,
    monkeypatch,
    role: str,
):
    test_user.roles = [role]
    assistant = await _create_assistant_agent(db_session, user_id=test_user.id)
    state_dir = tmp_path / "shared-openclaw-state"
    state_dir.mkdir()
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane.get_detected_gateway_port", lambda: 29999
    )
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane.get_detected_gateway_token",
        lambda: "shared-host-secret",
    )
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane.get_detected_openclaw_config_path",
        lambda: tmp_path / "shared-openclaw.json",
    )
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane.get_detected_openclaw_state_dir",
        lambda: state_dir,
    )
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane._request_gateway_json",
        lambda _paths: {"status": "ok"},
    )

    health_response = await client.get(f"/v1/assistant/{assistant.id}/health")
    overview_response = await client.get(f"/v1/assistant/overview?agent_id={assistant.id}")

    assert health_response.status_code == 200
    assert overview_response.status_code == 200
    health_payloads = [
        health_response.json(),
        overview_response.json()["assistant"]["gateway"],
    ]
    for health in health_payloads:
        assert health["status"] == "restricted"
        assert (
            health["doctor_summary"] == "Gateway host diagnostics are restricted to administrators."
        )
        for field in (
            "cli_available",
            "gateway_configured",
            "gateway_reachable",
            "gateway_port",
            "gateway_url",
            "credential_detected",
            "config_path",
            "state_dir",
        ):
            assert health[field] is None


@pytest.mark.asyncio
async def test_admin_owner_can_read_shared_host_diagnostics_in_health_and_overview(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    tmp_path,
    monkeypatch,
):
    test_user.roles = ["ADMIN"]
    assistant = await _create_assistant_agent(db_session, user_id=test_user.id)
    config_path = tmp_path / "openclaw.json"
    state_dir = tmp_path / "openclaw-state"
    state_dir.mkdir()
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane.get_detected_gateway_port", lambda: 29999
    )
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane.get_detected_gateway_token",
        lambda: "admin-visible-presence-only",
    )
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane.get_detected_openclaw_config_path",
        lambda: config_path,
    )
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane.get_detected_openclaw_state_dir",
        lambda: state_dir,
    )
    monkeypatch.setattr(
        "src.api.services.assistant_control_plane._request_gateway_json",
        lambda _paths: {"status": "ok"},
    )

    health_response = await client.get(f"/v1/assistant/{assistant.id}/health")
    overview_response = await client.get(f"/v1/assistant/overview?agent_id={assistant.id}")

    assert health_response.status_code == 200
    assert overview_response.status_code == 200
    for health in (
        health_response.json(),
        overview_response.json()["assistant"]["gateway"],
    ):
        assert health["status"] == "healthy"
        assert health["gateway_port"] == 29999
        assert health["gateway_url"] == "http://127.0.0.1:29999"
        assert health["credential_detected"] is True
        assert health["config_path"] == str(config_path)
        assert health["state_dir"] == str(state_dir)


@pytest.mark.asyncio
async def test_foreign_and_missing_resources_are_indistinguishable(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    other_user,
    test_agent,
    test_deployment,
):
    test_user.roles = ["DEVELOPER"]
    other_user.roles = ["DEVELOPER"]
    test_agent.type = AgentType.OPENCLAW
    foreign_key = APIKey(
        user_id=test_user.id,
        key_hash="foreign-key-hash",
        name="foreign-key",
        is_active=True,
    )
    db_session.add(foreign_key)
    await db_session.commit()
    await db_session.refresh(foreign_key)
    missing_id = uuid.uuid4()

    read_pairs = [
        (
            f"/v1/agents/{test_agent.id}",
            f"/v1/agents/{missing_id}",
        ),
        (
            f"/v1/assistant/{test_agent.id}/skills",
            f"/v1/assistant/{missing_id}/skills",
        ),
        (
            f"/v1/deployments/{test_deployment.id}",
            f"/v1/deployments/{missing_id}",
        ),
        (
            f"/v1/deployments?agent_id={test_agent.id}",
            f"/v1/deployments?agent_id={missing_id}",
        ),
        (
            f"/v1/api-keys/{foreign_key.id}",
            f"/v1/api-keys/{missing_id}",
        ),
    ]
    for foreign_path, missing_path in read_pairs:
        foreign = await other_user_client.get(foreign_path)
        missing = await other_user_client.get(missing_path)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()

    foreign = await other_user_client.post(
        "/v1/clawhub/install",
        json={"agent_id": str(test_agent.id), "skill_id": "web_search"},
    )
    missing = await other_user_client.post(
        "/v1/clawhub/install",
        json={"agent_id": str(missing_id), "skill_id": "web_search"},
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()

    created_template = await client.post(
        "/v1/templates/custom",
        json={
            "id": "tenant-private-template",
            "name": "Tenant Private Template",
            "system_prompt": "Private tenant instructions.",
        },
    )
    assert created_template.status_code == 201
    foreign_template = await other_user_client.put(
        "/v1/templates/custom/tenant-private-template",
        json={"name": "Foreign mutation"},
    )
    missing_template = await other_user_client.put(
        "/v1/templates/custom/missing-private-template",
        json={"name": "Missing mutation"},
    )
    assert foreign_template.status_code == missing_template.status_code == 404
    assert foreign_template.json() == missing_template.json()
