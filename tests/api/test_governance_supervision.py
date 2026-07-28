"""
Tests for governance supervision route: /v1/runtime/governance/supervised/*

These tests cover the internal-user gate, CRUD operations on supervised agents,
start/stop/restart lifecycle, and validation error handling.
"""

import pytest
from httpx import AsyncClient

from src.api.services.faramesh_supervisor import SupervisionValidationError


@pytest.fixture(autouse=True)
def administrator_principal(test_user):
    test_user.roles = ["ADMIN"]


class _MockPreparedLaunch:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id


class _MockSupervisor:
    """Full mock of FarameshSupervisor for route-level tests."""

    def __init__(
        self,
        *,
        start_prepared_success: bool = True,
        stop_success: bool = True,
        restart_success: bool = True,
        validation_error: str | None = None,
    ):
        self.statuses: dict[str, dict] = {
            "agent-1": {"agent_id": "agent-1", "state": "running"},
            "agent-2": {"agent_id": "agent-2", "state": "idle"},
        }
        self.profiles = [
            {
                "name": "default",
                "command": ["python", "-m", "mutx"],
                "env_keys": ["MUTX_ENV"],
                "faramesh_policy": "trusted",
            }
        ]
        self.validation_error = validation_error
        self.start_prepared_success = start_prepared_success
        self.stop_success = stop_success
        self.restart_success = restart_success
        # Track calls for assertions
        self.stop_calls: list[tuple[str, float | None]] = []
        self.restart_calls: list[str] = []

    def list_agents(self):
        return list(self.statuses.values())

    def list_profiles(self):
        return list(self.profiles)

    def get_agent_status(self, agent_id: str):
        return self.statuses.get(agent_id)

    def prepare_launch_request(
        self,
        agent_id: str,
        command=None,
        env=None,
        faramesh_policy=None,
        profile_name=None,
    ):
        if self.validation_error:
            raise SupervisionValidationError(self.validation_error)
        return _MockPreparedLaunch(agent_id)

    async def start_prepared_agent(self, prepared):
        if self.start_prepared_success:
            self.statuses[prepared.agent_id] = {
                "agent_id": prepared.agent_id,
                "state": "running",
            }
        return self.start_prepared_success

    async def stop_agent(self, agent_id: str, timeout: float | None = None):
        self.stop_calls.append((agent_id, timeout))
        return self.stop_success

    async def restart_agent(self, agent_id: str):
        self.restart_calls.append(agent_id)
        return self.restart_success


def _patch_supervisor(monkeypatch, supervisor: _MockSupervisor):
    from src.api.routes import governance_supervision

    monkeypatch.setattr(
        governance_supervision,
        "get_faramesh_supervisor",
        lambda: supervisor,
    )


# ---------------------------------------------------------------------------
# GET / — list supervised agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_supervised_agents_returns_list_for_internal_user(
    client: AsyncClient, monkeypatch
):
    supervisor = _MockSupervisor()
    _patch_supervisor(monkeypatch, supervisor)

    response = await client.get("/v1/runtime/governance/supervised/")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]["agent_id"] == "agent-1"


@pytest.mark.asyncio
async def test_list_supervised_agents_forbidden_for_non_internal_user(
    other_user_client: AsyncClient, monkeypatch
):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await other_user_client.get("/v1/runtime/governance/supervised/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_supervised_agents_requires_auth(client_no_auth: AsyncClient, monkeypatch):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await client_no_auth.get("/v1/runtime/governance/supervised/")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /profiles — list launch profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_launch_profiles_returns_profiles(client: AsyncClient, monkeypatch):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await client.get("/v1/runtime/governance/supervised/profiles")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "default"
    assert body[0]["command"] == ["python", "-m", "mutx"]


@pytest.mark.asyncio
async def test_list_launch_profiles_forbidden_for_non_internal_user(
    other_user_client: AsyncClient, monkeypatch
):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await other_user_client.get("/v1/runtime/governance/supervised/profiles")

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /{agent_id} — get supervised agent status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_supervised_agent_returns_status(client: AsyncClient, monkeypatch):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await client.get("/v1/runtime/governance/supervised/agent-1")

    assert response.status_code == 200
    assert response.json()["agent_id"] == "agent-1"
    assert response.json()["state"] == "running"


@pytest.mark.asyncio
async def test_get_supervised_agent_returns_404_for_unknown(client: AsyncClient, monkeypatch):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await client.get("/v1/runtime/governance/supervised/missing-agent")

    assert response.status_code == 404
    assert response.json() == {"detail": "Agent 'missing-agent' not found"}


@pytest.mark.asyncio
async def test_get_supervised_agent_forbidden_for_non_internal_user(
    other_user_client: AsyncClient, monkeypatch
):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await other_user_client.get("/v1/runtime/governance/supervised/agent-1")

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /start — start supervised agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_supervised_agent_success(client: AsyncClient, monkeypatch):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await client.post(
        "/v1/runtime/governance/supervised/start",
        json={"agent_id": "agent-new", "command": ["python", "-V"]},
    )

    assert response.status_code == 200
    assert response.json()["agent_id"] == "agent-new"


@pytest.mark.asyncio
async def test_start_supervised_agent_returns_400_on_validation_error(
    client: AsyncClient, monkeypatch
):
    _patch_supervisor(
        monkeypatch,
        _MockSupervisor(validation_error="profile not allowed"),
    )

    response = await client.post(
        "/v1/runtime/governance/supervised/start",
        json={"agent_id": "agent-3", "command": ["python", "-V"]},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "profile not allowed"}


@pytest.mark.asyncio
async def test_start_supervised_agent_returns_500_when_launch_fails(
    client: AsyncClient, monkeypatch
):
    _patch_supervisor(
        monkeypatch,
        _MockSupervisor(start_prepared_success=False),
    )

    response = await client.post(
        "/v1/runtime/governance/supervised/start",
        json={"agent_id": "agent-fail", "command": ["python", "-V"]},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to start agent"}


@pytest.mark.asyncio
async def test_start_supervised_agent_forbidden_for_non_internal_user(
    other_user_client: AsyncClient, monkeypatch
):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await other_user_client.post(
        "/v1/runtime/governance/supervised/start",
        json={"agent_id": "agent-1", "command": ["python", "-V"]},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_start_supervised_agent_returns_422_on_missing_fields(
    client: AsyncClient, monkeypatch
):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    # Missing required field `command`
    response = await client.post(
        "/v1/runtime/governance/supervised/start",
        json={"agent_id": "agent-x"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /{agent_id}/stop — stop supervised agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_supervised_agent_success(client: AsyncClient, monkeypatch):
    supervisor = _MockSupervisor()
    _patch_supervisor(monkeypatch, supervisor)

    response = await client.post(
        "/v1/runtime/governance/supervised/agent-1/stop",
        json={"timeout": 5.0},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "stopped", "agent_id": "agent-1"}
    assert supervisor.stop_calls == [("agent-1", 5.0)]


@pytest.mark.asyncio
async def test_stop_supervised_agent_uses_default_timeout(client: AsyncClient, monkeypatch):
    supervisor = _MockSupervisor()
    _patch_supervisor(monkeypatch, supervisor)

    response = await client.post(
        "/v1/runtime/governance/supervised/agent-1/stop",
        json={},
    )

    assert response.status_code == 200
    # Default timeout is 10.0 from the Pydantic model
    assert supervisor.stop_calls == [("agent-1", 10.0)]


@pytest.mark.asyncio
async def test_stop_supervised_agent_returns_500_when_supervisor_fails(
    client: AsyncClient, monkeypatch
):
    _patch_supervisor(monkeypatch, _MockSupervisor(stop_success=False))

    response = await client.post(
        "/v1/runtime/governance/supervised/agent-1/stop",
        json={},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to stop agent"}


@pytest.mark.asyncio
async def test_stop_supervised_agent_forbidden_for_non_internal_user(
    other_user_client: AsyncClient, monkeypatch
):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await other_user_client.post(
        "/v1/runtime/governance/supervised/agent-1/stop",
        json={},
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /{agent_id}/restart — restart supervised agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_supervised_agent_success(client: AsyncClient, monkeypatch):
    supervisor = _MockSupervisor()
    _patch_supervisor(monkeypatch, supervisor)

    response = await client.post("/v1/runtime/governance/supervised/agent-1/restart")

    assert response.status_code == 200
    assert response.json()["agent_id"] == "agent-1"
    assert supervisor.restart_calls == ["agent-1"]


@pytest.mark.asyncio
async def test_restart_supervised_agent_returns_500_when_supervisor_fails(
    client: AsyncClient, monkeypatch
):
    _patch_supervisor(monkeypatch, _MockSupervisor(restart_success=False))

    response = await client.post("/v1/runtime/governance/supervised/agent-1/restart")

    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to restart agent"}


@pytest.mark.asyncio
async def test_restart_supervised_agent_forbidden_for_non_internal_user(
    other_user_client: AsyncClient, monkeypatch
):
    _patch_supervisor(monkeypatch, _MockSupervisor())

    response = await other_user_client.post("/v1/runtime/governance/supervised/agent-1/restart")

    assert response.status_code == 403
