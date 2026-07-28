"""Focused persisted-principal RBAC matrix for lane A control-plane routes."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.jwt import create_access_token
from src.api.models import Agent, AgentLog, APIKey, Deployment, DeploymentEvent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/v1/agents/register", {"name": "unauthenticated-runtime"}),
        ("GET", "/v1/agents", None),
        ("GET", "/v1/api-keys", None),
        ("GET", "/v1/assistant/overview", None),
        ("GET", "/v1/budgets", None),
        (
            "POST",
            "/v1/clawhub/install",
            {"agent_id": "33333333-3333-4333-a333-333333333333", "skill_id": "web_search"},
        ),
        ("GET", "/v1/deployments", None),
        ("GET", "/v1/templates", None),
    ],
)
async def test_control_plane_routes_reject_missing_authentication(
    client_no_auth: AsyncClient,
    method: str,
    path: str,
    payload: dict[str, object] | None,
):
    response = await client_no_auth.request(method, path, json=payload)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_public_clawhub_catalog_reads_remain_public(client_no_auth: AsyncClient):
    skills = await client_no_auth.get("/v1/clawhub/skills")
    bundles = await client_no_auth.get("/v1/clawhub/bundles")

    assert skills.status_code == 200
    assert bundles.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/v1/agents",
        "/v1/agents/33333333-3333-4333-a333-333333333333",
        "/v1/agents/33333333-3333-4333-a333-333333333333/config",
        "/v1/agents/33333333-3333-4333-a333-333333333333/versions",
        "/v1/api-keys",
        "/v1/assistant/overview",
        "/v1/budgets",
        "/v1/budgets/usage",
        "/v1/deployments",
        "/v1/deployments/44444444-4444-4444-a444-444444444444",
        "/v1/deployments/44444444-4444-4444-a444-444444444444/events",
        "/v1/deployments/44444444-4444-4444-a444-444444444444/versions",
        "/v1/templates",
        "/v1/templates/state",
    ],
)
async def test_viewer_can_read_owner_scoped_control_plane_resources(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    test_agent,
    test_deployment,
    path: str,
):
    test_user.roles = ["VIEWER"]
    await db_session.commit()

    response = await client.get(path)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_viewer_mutations_are_denied_before_any_side_effect(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    test_agent,
    test_deployment,
):
    test_user.roles = ["VIEWER"]
    await db_session.commit()
    original_config = test_agent.config
    original_replicas = test_deployment.replicas
    counts_before = {
        "agents": await db_session.scalar(select(func.count()).select_from(Agent)),
        "api_keys": await db_session.scalar(select(func.count()).select_from(APIKey)),
        "deployments": await db_session.scalar(select(func.count()).select_from(Deployment)),
        "deployment_events": await db_session.scalar(
            select(func.count()).select_from(DeploymentEvent)
        ),
        "agent_logs": await db_session.scalar(select(func.count()).select_from(AgentLog)),
    }

    responses = [
        await client.post("/v1/agents/register", json={"name": "viewer-runtime"}),
        await client.post("/v1/agents", json={"name": "viewer-agent"}),
        await client.post("/v1/api-keys", json={"name": "viewer-secret"}),
        await client.post(f"/v1/assistant/{test_agent.id}/skills/web_search"),
        await client.post(
            "/v1/clawhub/install",
            json={"agent_id": str(test_agent.id), "skill_id": "web_search"},
        ),
        await client.post(
            f"/v1/deployments/{test_deployment.id}/scale",
            json={"replicas": original_replicas + 1},
        ),
        await client.post(
            "/v1/templates/personal_assistant/deploy",
            json={"name": "Viewer Template Deployment"},
        ),
        await client.post(
            f"/v1/agents/{test_agent.id}/rollback",
            json={"version": 1},
        ),
    ]

    assert {response.status_code for response in responses} == {403}
    await db_session.refresh(test_agent)
    await db_session.refresh(test_deployment)
    assert test_agent.config == original_config
    assert test_deployment.replicas == original_replicas
    assert counts_before == {
        "agents": await db_session.scalar(select(func.count()).select_from(Agent)),
        "api_keys": await db_session.scalar(select(func.count()).select_from(APIKey)),
        "deployments": await db_session.scalar(select(func.count()).select_from(Deployment)),
        "deployment_events": await db_session.scalar(
            select(func.count()).select_from(DeploymentEvent)
        ),
        "agent_logs": await db_session.scalar(select(func.count()).select_from(AgentLog)),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["DEVELOPER", "ADMIN"])
async def test_developer_and_admin_can_mutate_owned_resources(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user,
    role: str,
):
    test_user.roles = [role]
    await db_session.commit()

    created = await client.post(
        "/v1/agents",
        json={"name": f"{role.lower()}-owned-agent"},
    )

    assert created.status_code == 201
    assert created.json()["user_id"] == str(test_user.id)
    assert (await client.get(f"/v1/agents/{created.json()['id']}")).status_code == 200


@pytest.mark.asyncio
async def test_developer_cannot_cross_owner_boundaries(
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
    foreign_key = APIKey(
        id=uuid.uuid4(),
        user_id=test_user.id,
        key_hash="foreign-owner-hash",
        name="foreign-owner-key",
        is_active=True,
    )
    db_session.add(foreign_key)
    await db_session.commit()

    responses = [
        await other_user_client.get(f"/v1/agents/{test_agent.id}"),
        await other_user_client.patch(
            f"/v1/agents/{test_agent.id}/config",
            json={"config": {"model": "gpt-4o-mini"}},
        ),
        await other_user_client.get(f"/v1/agents/{test_agent.id}/versions"),
        await other_user_client.post(f"/v1/assistant/{test_agent.id}/skills/web_search"),
        await other_user_client.post(
            "/v1/clawhub/install",
            json={"agent_id": str(test_agent.id), "skill_id": "web_search"},
        ),
        await other_user_client.get(f"/v1/deployments/{test_deployment.id}"),
        await other_user_client.post(
            f"/v1/deployments/{test_deployment.id}/scale",
            json={"replicas": 2},
        ),
        await other_user_client.get(f"/v1/api-keys/{foreign_key.id}"),
        await other_user_client.post(f"/v1/api-keys/{foreign_key.id}/rotate"),
    ]

    assert {response.status_code for response in responses} == {404}
    await db_session.refresh(test_deployment)
    await db_session.refresh(foreign_key)
    assert test_deployment.replicas == 1
    assert foreign_key.is_active is True


@pytest.mark.asyncio
async def test_role_revocation_uses_persisted_principal_before_side_effects(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
    test_user,
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    access_token, _ = create_access_token(test_user.id)

    test_user.roles = ["VIEWER"]
    await db_session.commit()
    headers = {"Authorization": f"Bearer {access_token}"}

    denied = await client_no_auth.post(
        "/v1/agents",
        json={"name": "revoked-developer"},
        headers=headers,
    )
    allowed_read = await client_no_auth.get("/v1/agents", headers=headers)

    assert denied.status_code == 403
    assert allowed_read.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(Agent)) == 0
