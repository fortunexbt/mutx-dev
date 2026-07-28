"""Tests for /v1/templates route — template listing and deployment."""

import pytest
from httpx import AsyncClient

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
