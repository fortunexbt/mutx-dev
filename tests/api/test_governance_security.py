from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from src.api.services.credential_broker import Credential
from src.api.services.faramesh_supervisor import SupervisionValidationError


@pytest.fixture(autouse=True)
def administrator_principal(test_user):
    test_user.roles = ["ADMIN"]


@pytest.mark.asyncio
async def test_governance_credentials_require_internal_user_and_redact_secret(
    client: AsyncClient, other_user_client: AsyncClient, monkeypatch
):
    import src.api.routes.governance_credentials as governance_credentials

    captured_namespaces: list[str | None] = []

    class FakeBroker:
        async def list_backends(self):
            return [
                {
                    "name": "vault-prod",
                    "backend": "vault",
                    "path": "secret/prod",
                    "ttl": 900,
                    "is_active": True,
                    "is_healthy": True,
                }
            ]

        async def get_credential_by_path(self, full_path: str, requester_id: str | None = None):
            return Credential(
                name="api-key",
                backend="vault",
                path="secret/prod/api-key",
                value="super-secret-token",
                expires_at=datetime.now(timezone.utc),
                metadata={"scope": "prod"},
            )

    monkeypatch.setattr(
        governance_credentials,
        "get_credential_broker",
        lambda namespace=None: captured_namespaces.append(namespace) or FakeBroker(),
    )

    list_response = await client.get("/v1/governance/credentials/backends")
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "vault-prod"

    credential_response = await client.get(
        "/v1/governance/credentials/get/vault:/secret/prod/api-key"
    )
    assert credential_response.status_code == 200
    payload = credential_response.json()
    assert payload["value"] is None
    assert payload["has_value"] is True
    assert payload["metadata"] == {"scope": "prod"}

    forbidden_response = await other_user_client.get("/v1/governance/credentials/backends")
    assert forbidden_response.status_code == 403
    assert captured_namespaces
    assert all(
        namespace == "11111111-1111-4111-a111-111111111111" for namespace in captured_namespaces
    )


@pytest.mark.asyncio
async def test_governance_supervision_requires_internal_user(
    client: AsyncClient, other_user_client: AsyncClient, monkeypatch
):
    import src.api.routes.governance_supervision as governance_supervision

    class FakeSupervisor:
        def list_agents(self):
            return [{"agent_id": "agent-1", "status": "running"}]

        def list_profiles(self):
            return [{"name": "assistant-runner", "command": ["python", "agent.py"], "env_keys": []}]

    monkeypatch.setattr(
        governance_supervision,
        "get_faramesh_supervisor",
        lambda: FakeSupervisor(),
    )

    allowed_response = await client.get("/v1/runtime/governance/supervised/")
    assert allowed_response.status_code == 200
    assert allowed_response.json() == [{"agent_id": "agent-1", "status": "running"}]

    forbidden_response = await other_user_client.get("/v1/runtime/governance/supervised/")
    assert forbidden_response.status_code == 403

    profiles_response = await client.get("/v1/runtime/governance/supervised/profiles")
    assert profiles_response.status_code == 200
    assert profiles_response.json()[0]["name"] == "assistant-runner"


@pytest.mark.asyncio
async def test_governance_supervision_start_returns_400_for_rejected_launch(
    client: AsyncClient, monkeypatch
):
    import src.api.routes.governance_supervision as governance_supervision

    class FakeSupervisor:
        def prepare_launch_request(
            self,
            agent_id,
            command=None,
            env=None,
            faramesh_policy=None,
            profile_name=None,
        ):
            raise SupervisionValidationError(
                "Direct supervised commands are disabled. Use a configured launch profile."
            )

        async def start_prepared_agent(self, *args, **kwargs):
            raise AssertionError("start_prepared_agent should not be called for rejected launches")

    monkeypatch.setattr(
        governance_supervision,
        "get_faramesh_supervisor",
        lambda: FakeSupervisor(),
    )

    response = await client.post(
        "/v1/runtime/governance/supervised/start",
        json={"agent_id": "agent-1", "command": ["bash", "-lc", "id"]},
    )

    assert response.status_code == 400
    assert "launch profile" in response.json()["detail"]


@pytest.mark.asyncio
async def test_governance_runtime_metrics_require_internal_user(
    client: AsyncClient, other_user_client: AsyncClient, monkeypatch
):
    import cli.faramesh_runtime as faramesh_runtime

    class FakeSnapshot:
        decisions_total = 4
        permits_today = 2
        denies_today = 1
        defers_today = 1
        pending_approvals = 3
        status = "running"

    monkeypatch.setattr(faramesh_runtime, "collect_faramesh_snapshot", lambda: FakeSnapshot())
    monkeypatch.setattr(
        faramesh_runtime,
        "generate_prometheus_metrics",
        lambda _snapshot: "mutx_governance_decisions_total 4\n",
    )

    allowed_response = await client.get("/v1/runtime/governance/metrics")
    assert allowed_response.status_code == 200
    assert "mutx_governance_decisions_total" in allowed_response.text

    forbidden_response = await other_user_client.get("/v1/runtime/governance/metrics")
    assert forbidden_response.status_code == 403


@pytest.mark.asyncio
async def test_governance_runtime_status_require_internal_user(
    client: AsyncClient, other_user_client: AsyncClient, monkeypatch
):
    import cli.faramesh_runtime as faramesh_runtime

    class FakeHealth:
        daemon_reachable = True
        socket_reachable = True
        policy_loaded = True
        version = "1.2.3"
        policy_name = "starter"

    class FakeSnapshot:
        decisions_total = 4
        permits_today = 2
        denies_today = 1
        defers_today = 1
        pending_approvals = 3
        status = "running"

    monkeypatch.setattr(faramesh_runtime, "get_faramesh_health", lambda: FakeHealth())
    monkeypatch.setattr(faramesh_runtime, "collect_faramesh_snapshot", lambda: FakeSnapshot())

    allowed_response = await client.get("/v1/runtime/governance/status")
    assert allowed_response.status_code == 200
    assert allowed_response.json()["policy_name"] == "starter"

    forbidden_response = await other_user_client.get("/v1/runtime/governance/status")
    assert forbidden_response.status_code == 403
