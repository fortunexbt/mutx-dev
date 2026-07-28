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
    def __init__(self):
        self.statuses = {
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
        self.validation_error: str | None = None
        self.stop_success = True
        self.restart_success = True
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
        self.statuses[prepared.agent_id] = {"agent_id": prepared.agent_id, "state": "running"}
        return True

    async def stop_agent(self, agent_id: str, timeout: float | None = None):
        self.stop_calls.append((agent_id, timeout))
        return self.stop_success

    async def restart_agent(self, agent_id: str):
        self.restart_calls.append(agent_id)
        return self.restart_success


@pytest.mark.asyncio
async def test_list_supervised_agents_requires_auth(client_no_auth: AsyncClient, monkeypatch):
    from src.api.routes import governance_supervision

    monkeypatch.setattr(
        governance_supervision,
        "get_faramesh_supervisor",
        lambda: _MockSupervisor(),
    )

    response = await client_no_auth.get("/v1/runtime/governance/supervised/")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_supervised_agents_forbidden_for_non_internal_user(
    other_user_client: AsyncClient,
    monkeypatch,
):
    from src.api.routes import governance_supervision

    monkeypatch.setattr(
        governance_supervision,
        "get_faramesh_supervisor",
        lambda: _MockSupervisor(),
    )

    response = await other_user_client.get("/v1/runtime/governance/supervised/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_supervised_launch_profiles_returns_profiles(client: AsyncClient, monkeypatch):
    from src.api.routes import governance_supervision

    supervisor = _MockSupervisor()
    monkeypatch.setattr(governance_supervision, "get_faramesh_supervisor", lambda: supervisor)

    response = await client.get("/v1/runtime/governance/supervised/profiles")

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "default",
            "command": ["python", "-m", "mutx"],
            "env_keys": ["MUTX_ENV"],
            "faramesh_policy": "trusted",
        }
    ]


@pytest.mark.asyncio
async def test_list_supervised_launch_profiles_forbidden_for_non_internal_user(
    other_user_client: AsyncClient,
    monkeypatch,
):
    from src.api.routes import governance_supervision

    monkeypatch.setattr(
        governance_supervision,
        "get_faramesh_supervisor",
        lambda: _MockSupervisor(),
    )

    response = await other_user_client.get("/v1/runtime/governance/supervised/profiles")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_supervised_agent_returns_404_for_unknown_agent(client: AsyncClient, monkeypatch):
    from src.api.routes import governance_supervision

    monkeypatch.setattr(
        governance_supervision,
        "get_faramesh_supervisor",
        lambda: _MockSupervisor(),
    )

    response = await client.get("/v1/runtime/governance/supervised/missing-agent")

    assert response.status_code == 404
    assert response.json() == {"detail": "Agent 'missing-agent' not found"}


@pytest.mark.asyncio
async def test_start_supervised_agent_returns_validation_error(client: AsyncClient, monkeypatch):
    from src.api.routes import governance_supervision

    supervisor = _MockSupervisor()
    supervisor.validation_error = "profile not allowed"
    monkeypatch.setattr(governance_supervision, "get_faramesh_supervisor", lambda: supervisor)

    response = await client.post(
        "/v1/runtime/governance/supervised/start",
        json={
            "agent_id": "agent-3",
            "command": ["python", "-m", "mutx"],
            "profile": "blocked",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "profile not allowed"}


@pytest.mark.asyncio
async def test_stop_supervised_agent_passes_timeout_to_supervisor(client: AsyncClient, monkeypatch):
    from src.api.routes import governance_supervision

    supervisor = _MockSupervisor()
    monkeypatch.setattr(governance_supervision, "get_faramesh_supervisor", lambda: supervisor)

    response = await client.post(
        "/v1/runtime/governance/supervised/agent-1/stop",
        json={"timeout": 2.5},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "stopped", "agent_id": "agent-1"}
    assert supervisor.stop_calls == [("agent-1", 2.5)]


@pytest.mark.asyncio
async def test_restart_supervised_agent_returns_500_when_supervisor_fails(
    client: AsyncClient,
    monkeypatch,
):
    from src.api.routes import governance_supervision

    supervisor = _MockSupervisor()
    supervisor.restart_success = False
    monkeypatch.setattr(governance_supervision, "get_faramesh_supervisor", lambda: supervisor)

    response = await client.post("/v1/runtime/governance/supervised/agent-1/restart")

    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to restart agent"}
    assert supervisor.restart_calls == ["agent-1"]
