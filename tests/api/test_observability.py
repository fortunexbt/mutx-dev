"""Tests for observability API routes."""

import uuid

import pytest


@pytest.fixture(autouse=True)
def developer_principal(test_user):
    test_user.roles = ["DEVELOPER"]


@pytest.mark.asyncio
async def test_create_observability_run(client):
    """Test creating an observability run with minimal fields."""
    response = await client.post(
        "/v1/observability/runs",
        json={
            "agent_id": "test-agent-001",
            "status": "running",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["agent_id"] == "test-agent-001"
    assert payload["status"] == "running"


@pytest.mark.asyncio
async def test_list_observability_runs(client):
    """Test listing observability runs."""
    await client.post(
        "/v1/observability/runs",
        json={
            "agent_id": "test-agent-002",
            "status": "completed",
        },
    )

    response = await client.get("/v1/observability/runs")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "has_more" in payload


@pytest.mark.asyncio
async def test_get_observability_run(client):
    """Test getting a specific observability run."""
    create_response = await client.post(
        "/v1/observability/runs",
        json={
            "agent_id": "test-agent-003",
            "status": "running",
        },
    )
    run_id = create_response.json()["id"]

    response = await client.get(f"/v1/observability/runs/{run_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == run_id
    assert payload["agent_id"] == "test-agent-003"


@pytest.mark.asyncio
async def test_get_nonexistent_run(client):
    """Test getting a run that doesn't exist."""
    response = await client.get(f"/v1/observability/runs/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_steps_accepts_step_list(client):
    create_response = await client.post(
        "/v1/observability/runs",
        json={
            "agent_id": "test-agent-steps",
            "status": "running",
        },
    )
    run_id = create_response.json()["id"]

    response = await client.post(
        f"/v1/observability/runs/{run_id}/steps",
        json=[
            {
                "type": "tool_call",
                "tool_name": "bash",
                "started_at": "2026-03-25T10:00:00+00:00",
                "step_metadata": {"source": "openclaw"},
            }
        ],
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["total"] == 1

    detail_response = await client.get(f"/v1/observability/runs/{run_id}")
    detail_payload = detail_response.json()
    assert len(detail_payload["steps"]) == 1
    assert detail_payload["steps"][0]["tool_name"] == "bash"


@pytest.mark.asyncio
async def test_update_run_status_updates_cost_fields(client):
    create_response = await client.post(
        "/v1/observability/runs",
        json={
            "agent_id": "test-agent-costs",
            "status": "running",
        },
    )
    run_id = create_response.json()["id"]

    response = await client.patch(
        f"/v1/observability/runs/{run_id}/status",
        json={
            "status": "completed",
            "ended_at": "2026-03-25T10:05:00+00:00",
            "input_tokens": 120,
            "output_tokens": 80,
            "cost_usd": 0.42,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["cost"]["input_tokens"] == 120
    assert payload["cost"]["output_tokens"] == 80
    assert payload["cost"]["total_tokens"] == 200
    assert payload["cost"]["cost_usd"] == 0.42


@pytest.mark.asyncio
async def test_update_run_status_rejects_invalid_status(client):
    """Status must be a valid MutxRunStatus enum value."""
    create_response = await client.post(
        "/v1/observability/runs",
        json={"agent_id": "test-agent-bad-status", "status": "running"},
    )
    run_id = create_response.json()["id"]

    response = await client.patch(
        f"/v1/observability/runs/{run_id}/status",
        json={"status": "not_a_real_status"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_run_status_rejects_negative_tokens(client):
    """Token counts must be non-negative."""
    create_response = await client.post(
        "/v1/observability/runs",
        json={"agent_id": "test-agent-neg-tokens", "status": "running"},
    )
    run_id = create_response.json()["id"]

    response = await client.patch(
        f"/v1/observability/runs/{run_id}/status",
        json={"input_tokens": -5},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_security_evaluate_endpoint(client):
    """Test the security action evaluation endpoint."""
    response = await client.post(
        "/v1/security/actions/evaluate",
        json={
            "tool_name": "bash",
            "tool_args": {"command": "ls"},
            "agent_id": "test-agent",
            "session_id": "test-session",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "decision" in payload


@pytest.mark.asyncio
async def test_security_metrics_endpoint(client, test_user):
    """Test the security metrics endpoint."""
    test_user.roles = ["ADMIN"]
    response = await client.get("/v1/security/metrics")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_security_compliance_endpoint(client, test_user):
    """Test the security compliance endpoint."""
    test_user.roles = ["ADMIN"]
    response = await client.get("/v1/security/compliance")
    assert response.status_code == 200
    payload = response.json()
    assert "version" in payload
