"""Tests for /v1/templates route — template listing and deployment."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select

from src.api.models import Agent


@pytest_asyncio.fixture(autouse=True)
async def developer_principals(db_session, test_user, other_user):
    test_user.roles = ["DEVELOPER"]
    other_user.roles = ["DEVELOPER"]
    await db_session.commit()


def custom_template_payload(template_id: str = "custom-contract") -> dict[str, object]:
    return {
        "id": template_id,
        "name": "Contract Template",
        "summary": "A custom contract template.",
        "description": "Owned by the current test user.",
        "starter_prompt": "Start the contract workflow.",
        "system_prompt": "You are the contract test assistant.",
        "category": "custom",
        "tags": ["custom", "contract"],
        "version": "1",
        "metadata": {"kind": "custom_template", "files": ["SYSTEM.md"]},
    }


# ---------------------------------------------------------------------------
# GET /v1/templates  — list templates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_templates_returns_list(client: AsyncClient):
    """Template list returns 200 with a list of templates."""
    response = await client.get("/v1/templates")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_templates_has_required_fields(client: AsyncClient):
    """Each template entry has the required schema fields."""
    response = await client.get("/v1/templates")
    assert response.status_code == 200
    data = response.json()
    if data:
        template = data[0]
        assert "id" in template
        assert "name" in template
        assert "summary" in template
        assert "description" in template
        assert "agent_type" in template


@pytest.mark.asyncio
async def test_list_templates_includes_orchestra_research_presets(client: AsyncClient):
    response = await client.get("/v1/templates")
    assert response.status_code == 200
    template_ids = {item["id"] for item in response.json()}
    assert "orchestra_research_foundation" in template_ids
    assert "orchestra_rag_lab" in template_ids
    assert "orchestra_multimodal_guardrails" in template_ids


# ---------------------------------------------------------------------------
# POST /v1/templates/{template_id}/deploy  — deploy template
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_template_not_found(client: AsyncClient):
    """Deploying a non-existent template returns 404."""
    response = await client.post(
        "/v1/templates/nonexistent/deploy",
        json={"name": "Test Agent"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_deploy_template_default_success(client: AsyncClient):
    """Deploying the default starter template creates agent + deployment."""
    list_resp = await client.get("/v1/templates")
    templates = list_resp.json()
    if not templates:
        pytest.skip("No templates available in catalog")

    default_id = templates[0]["id"]

    response = await client.post(
        f"/v1/templates/{default_id}/deploy",
        json={"name": "Test Starter Agent", "description": "Created by test"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "template_id" in data
    assert "agent" in data
    assert "deployment" in data
    assert data["agent"]["name"] == "Test Starter Agent"


@pytest.mark.asyncio
async def test_deploy_template_with_options(client: AsyncClient):
    """Deploying with extra options like model and workspace works."""
    list_resp = await client.get("/v1/templates")
    templates = list_resp.json()
    if not templates:
        pytest.skip("No templates available in catalog")

    default_id = templates[0]["id"]

    response = await client.post(
        f"/v1/templates/{default_id}/deploy",
        json={
            "name": "Configured Agent",
            "description": "Test with options",
            "model": "gpt-4",
            "workspace": "/tmp/test-workspace",
            "replicas": 2,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["agent"]["name"] == "Configured Agent"


@pytest.mark.asyncio
async def test_deploy_template_respects_explicit_empty_skills_and_disabled_channels(
    client: AsyncClient,
):
    response = await client.post(
        "/v1/templates/personal_assistant/deploy",
        json={
            "name": "Minimal Starter",
            "skills": [],
            "channels": {
                "telegram": {
                    "label": "Telegram",
                    "enabled": False,
                    "mode": "pairing",
                    "allow_from": [],
                }
            },
        },
    )

    assert response.status_code == 201
    config = response.json()["agent"]["config"]
    assert config["skills"] == []
    assert config["channels"]["telegram"]["enabled"] is False


@pytest.mark.asyncio
async def test_deploy_template_invalid_name(client: AsyncClient):
    """Deploying with empty name returns 422 validation error."""
    list_resp = await client.get("/v1/templates")
    templates = list_resp.json()
    if not templates:
        pytest.skip("No templates available in catalog")

    default_id = templates[0]["id"]

    response = await client.post(
        f"/v1/templates/{default_id}/deploy",
        json={"name": ""},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# User-scoped catalog state and custom template lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_catalog_state_is_durable_and_user_scoped(
    client: AsyncClient,
    other_user_client: AsyncClient,
):
    state = {
        "pinned_template_ids": ["personal_assistant"],
        "recent_template_ids": ["orchestra_rag_lab"],
        "deployment_count_by_template": {"personal_assistant": 3},
    }

    updated = await client.put("/v1/templates/state", json=state)
    assert updated.status_code == 200
    assert updated.json() == {**state, "updated_at": updated.json()["updated_at"]}
    assert updated.json()["updated_at"] is not None

    persisted = await client.get("/v1/templates/state")
    assert persisted.status_code == 200
    assert persisted.json()["pinned_template_ids"] == ["personal_assistant"]
    assert persisted.json()["deployment_count_by_template"] == {"personal_assistant": 3}

    other_state = await other_user_client.get("/v1/templates/state")
    assert other_state.status_code == 200
    assert other_state.json() == {
        "pinned_template_ids": [],
        "recent_template_ids": [],
        "deployment_count_by_template": {},
        "updated_at": None,
    }


@pytest.mark.asyncio
async def test_custom_template_crud_is_user_scoped_and_cleans_catalog_state(
    client: AsyncClient,
    other_user_client: AsyncClient,
):
    created = await client.post("/v1/templates/custom", json=custom_template_payload())
    assert created.status_code == 201
    assert created.json()["id"] == "custom-contract"
    assert created.json()["category"] == "custom"
    assert created.json()["is_official"] is False

    own_catalog = await client.get("/v1/templates")
    assert "custom-contract" in {item["id"] for item in own_catalog.json()}
    other_catalog = await other_user_client.get("/v1/templates")
    assert "custom-contract" not in {item["id"] for item in other_catalog.json()}

    cross_user_update = await other_user_client.put(
        "/v1/templates/custom/custom-contract",
        json={"name": "Not mine"},
    )
    assert cross_user_update.status_code == 404

    updated = await client.put(
        "/v1/templates/custom/custom-contract",
        json={
            "name": "Updated Contract Template",
            "system_prompt": "You are the updated contract assistant.",
            "tags": ["updated"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Contract Template"
    assert updated.json()["default_config"]["system_prompt"] == (
        "You are the updated contract assistant."
    )

    await client.put(
        "/v1/templates/state",
        json={
            "pinned_template_ids": ["custom-contract"],
            "recent_template_ids": ["custom-contract"],
            "deployment_count_by_template": {"custom-contract": 2},
        },
    )
    deleted = await client.delete("/v1/templates/custom/custom-contract")
    assert deleted.status_code == 204
    assert deleted.content == b""

    state = (await client.get("/v1/templates/state")).json()
    assert state["pinned_template_ids"] == []
    assert state["recent_template_ids"] == []
    assert state["deployment_count_by_template"] == {}
    assert (await client.delete("/v1/templates/custom/custom-contract")).status_code == 404


@pytest.mark.asyncio
async def test_built_in_templates_are_immutable(client: AsyncClient):
    create_response = await client.post(
        "/v1/templates/custom",
        json=custom_template_payload("personal_assistant"),
    )
    assert create_response.status_code == 409
    assert "immutable" in create_response.json()["detail"].lower()

    update_response = await client.put(
        "/v1/templates/custom/personal_assistant",
        json={"name": "Mutated built-in"},
    )
    assert update_response.status_code == 403
    assert "immutable" in update_response.json()["detail"].lower()

    delete_response = await client.delete("/v1/templates/custom/personal_assistant")
    assert delete_response.status_code == 403
    assert "immutable" in delete_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_clone_builtin_creates_editable_user_owned_copy(client: AsyncClient):
    response = await client.post(
        "/v1/templates/personal_assistant/clone",
        json={
            "id": "personal-assistant-copy",
            "name": "Personal Assistant Copy",
            "category": "ignored-by-server",
            "version": "7",
        },
    )

    assert response.status_code == 201
    clone = response.json()
    assert clone["id"] == "personal-assistant-copy"
    assert clone["category"] == "custom"
    assert clone["is_official"] is False
    assert clone["version"] == "7"
    assert clone["default_config"]["metadata"]["template"]["source_template_id"] == (
        "personal_assistant"
    )


@pytest.mark.asyncio
async def test_custom_template_can_be_deployed_with_its_saved_config(client: AsyncClient):
    created = await client.post(
        "/v1/templates/custom",
        json=custom_template_payload("custom-deployable"),
    )
    assert created.status_code == 201

    deployed = await client.post(
        "/v1/templates/custom-deployable/deploy",
        json={"name": "Custom Deployment", "replicas": 1},
    )
    assert deployed.status_code == 201
    receipt = deployed.json()
    assert receipt["template_id"] == "custom-deployable"
    assert receipt["agent"]["config"]["template"] == "custom-deployable"
    assert receipt["agent"]["config"]["system_prompt"] == ("You are the contract test assistant.")


# ---------------------------------------------------------------------------
# Deployment idempotency and auxiliary persistence failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_template_idempotency_replays_authoritative_receipt(
    client: AsyncClient,
    db_session,
    test_user,
):
    user_id = test_user.id
    payload = {"name": "Idempotent Starter", "description": "Create once"}
    headers = {"Idempotency-Key": "templates-contract-create-once"}

    first = await client.post(
        "/v1/templates/personal_assistant/deploy",
        json=payload,
        headers=headers,
    )
    second = await client.post(
        "/v1/templates/personal_assistant/deploy",
        json=payload,
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["agent"]["id"] == first.json()["agent"]["id"]
    assert second.json()["deployment"]["id"] == first.json()["deployment"]["id"]
    agent_count = await db_session.scalar(
        select(func.count()).select_from(Agent).where(Agent.user_id == user_id)
    )
    assert agent_count == 1

    conflict = await client.post(
        "/v1/templates/personal_assistant/deploy",
        json={"name": "Different request"},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert "different deployment" in conflict.json()["detail"].lower()


@pytest.mark.asyncio
async def test_deploy_success_survives_idempotency_receipt_persistence_failure(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
):
    from src.api.routes import templates as templates_route

    user_id = test_user.id

    async def fail_to_finalize(*_args, **_kwargs):
        raise RuntimeError("setting store unavailable")

    monkeypatch.setattr(
        templates_route.template_catalog_service,
        "complete_deployment_idempotency",
        fail_to_finalize,
    )

    response = await client.post(
        "/v1/templates/personal_assistant/deploy",
        json={"name": "Authoritative Deployment"},
        headers={"Idempotency-Key": "receipt-write-failure"},
    )

    assert response.status_code == 201
    assert response.json()["agent"]["name"] == "Authoritative Deployment"
    agent_count = await db_session.scalar(
        select(func.count()).select_from(Agent).where(Agent.user_id == user_id)
    )
    assert agent_count == 1


@pytest.mark.asyncio
async def test_failed_deploy_releases_idempotency_claim_for_retry(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
):
    from src.api.routes import templates as templates_route

    original_create_deployment_record = templates_route.create_deployment_record

    async def fail_primary_deployment(*_args, **_kwargs):
        raise RuntimeError("deployment write failed")

    monkeypatch.setattr(
        templates_route,
        "create_deployment_record",
        fail_primary_deployment,
    )
    headers = {"Idempotency-Key": "retry-after-primary-failure"}
    payload = {"name": "Retryable Deployment"}

    with pytest.raises(RuntimeError, match="deployment write failed"):
        await client.post(
            "/v1/templates/personal_assistant/deploy",
            json=payload,
            headers=headers,
        )

    await db_session.refresh(test_user)
    monkeypatch.setattr(
        templates_route,
        "create_deployment_record",
        original_create_deployment_record,
    )
    retry = await client.post(
        "/v1/templates/personal_assistant/deploy",
        json=payload,
        headers=headers,
    )

    assert retry.status_code == 201
    assert retry.json()["agent"]["name"] == "Retryable Deployment"
