import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

import src.api.routes.assistant as assistant_routes
from src.api.models import UserSetting
from src.api.services.session_ownership import (
    SESSION_OWNERSHIP_PREFIX,
    filter_and_claim_owned_sessions,
)


def _gateway_session(
    session_id: str,
    *,
    agent_id: str | uuid.UUID | None = None,
    agent: str = "shared-label",
) -> dict[str, object]:
    session: dict[str, object] = {
        "id": session_id,
        "key": session_id,
        "agent": agent,
        "kind": "session",
        "age": "1m",
        "model": "openai/gpt-5",
        "tokens": "20",
        "channel": "webchat",
        "flags": [],
        "active": True,
        "start_time": 1_700_000_000,
        "last_activity": 1_700_000_100,
        "source": "openclaw",
    }
    if agent_id is not None:
        session["agent_id"] = str(agent_id)
    return session


@pytest_asyncio.fixture(autouse=True)
async def developer_principals(db_session, test_user, other_user):
    test_user.roles = ["DEVELOPER"]
    other_user.roles = ["DEVELOPER"]
    await db_session.commit()


class TestAssistantTemplates:
    @pytest.mark.asyncio
    async def test_list_templates_returns_personal_assistant(self, client: AsyncClient):
        response = await client.get("/v1/templates")

        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["id"] == "personal_assistant"
        assert payload[0]["agent_type"] == "openclaw"

    @pytest.mark.asyncio
    async def test_template_deploy_creates_agent_and_deployment(self, client: AsyncClient):
        response = await client.post(
            "/v1/templates/personal_assistant/deploy",
            json={
                "name": "Personal Assistant",
                "assistant_id": "personal-assistant",
                "workspace": "/tmp/openclaw/workspace-personal-assistant",
                "runtime_metadata": {
                    "managed_by_mutx": True,
                    "install_method": "npm",
                },
                "skills": ["web_search", "workspace_memory"],
                "channels": {
                    "webchat": {
                        "label": "WebChat",
                        "enabled": True,
                        "mode": "pairing",
                        "allow_from": [],
                    }
                },
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["template_id"] == "personal_assistant"
        assert payload["agent"]["type"] == "openclaw"
        assert payload["agent"]["config"]["assistant_id"] == "personal-assistant"
        assert (
            payload["agent"]["config"]["workspace"] == "/tmp/openclaw/workspace-personal-assistant"
        )
        assert payload["agent"]["config"]["metadata"]["runtime"]["managed_by_mutx"] is True
        assert payload["deployment"]["status"] == "pending"


class TestAssistantOverview:
    @pytest.mark.asyncio
    async def test_overview_returns_empty_state_without_assistant(self, client: AsyncClient):
        response = await client.get("/v1/assistant/overview")

        assert response.status_code == 200
        payload = response.json()
        assert payload["has_assistant"] is False
        assert payload["assistant"] is None

    @pytest.mark.asyncio
    async def test_overview_returns_created_assistant(self, client: AsyncClient):
        create_response = await client.post(
            "/v1/templates/personal_assistant/deploy",
            json={"name": "Ops Assistant"},
        )
        agent_id = create_response.json()["agent"]["id"]

        response = await client.get(f"/v1/assistant/overview?agent_id={agent_id}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["has_assistant"] is True
        assert payload["assistant"]["name"] == "Ops Assistant"
        assert payload["assistant"]["template_id"] == "personal_assistant"
        assert payload["assistant"]["gateway"]["status"] == "restricted"
        assert "restricted to administrators" in payload["assistant"]["gateway"]["doctor_summary"]

    @pytest.mark.asyncio
    async def test_assistant_skill_install_round_trip(self, client: AsyncClient):
        create_response = await client.post(
            "/v1/templates/personal_assistant/deploy",
            json={"name": "Ops Assistant"},
        )
        agent_id = create_response.json()["agent"]["id"]

        install_response = await client.post(f"/v1/assistant/{agent_id}/skills/browser_control")
        assert install_response.status_code == 200
        assert any(
            item["id"] == "browser_control"
            and item["configured"]
            and item["status"] == "configured"
            and not item["installed"]
            for item in install_response.json()
        )

        uninstall_response = await client.delete(f"/v1/assistant/{agent_id}/skills/browser_control")
        assert uninstall_response.status_code == 200
        assert any(
            item["id"] == "browser_control"
            and not item["configured"]
            and item["status"] == "available"
            for item in uninstall_response.json()
        )

    @pytest.mark.asyncio
    async def test_assistant_sessions_returns_gateway_data(self, client: AsyncClient, monkeypatch):
        create_response = await client.post(
            "/v1/templates/personal_assistant/deploy",
            json={"name": "Ops Assistant", "assistant_id": "ops-assistant"},
        )
        agent_id = create_response.json()["agent"]["id"]

        monkeypatch.setattr(
            "src.api.services.assistant_control_plane._request_gateway_json",
            lambda _paths: {
                "sessions": [
                    {
                        "id": "session-123",
                        "session_key": "session-123",
                        "agent_id": agent_id,
                        "assistant_id": "ops-assistant",
                        "model": "openai/gpt-5",
                        "channel": "webchat",
                        "status": "active",
                        "created_at": 1_700_000_000,
                        "updated_at": 1_700_000_100,
                        "input_tokens": 12,
                        "output_tokens": 8,
                    }
                ]
            },
        )

        response = await client.get(f"/v1/assistant/{agent_id}/sessions")

        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["id"] == "session-123"
        assert payload[0]["agent"] == "ops-assistant"
        assert payload[0]["tokens"] == "20"
        assert payload[0]["active"] is True

    @pytest.mark.asyncio
    async def test_assistant_sessions_isolates_same_label_across_tenants(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        monkeypatch,
    ):
        owner_create = await client.post(
            "/v1/templates/personal_assistant/deploy",
            json={"name": "Shared Assistant", "assistant_id": "shared-label"},
        )
        foreign_create = await other_user_client.post(
            "/v1/templates/personal_assistant/deploy",
            json={"name": "Shared Assistant", "assistant_id": "shared-label"},
        )
        owner_id = uuid.UUID(owner_create.json()["agent"]["id"])
        foreign_id = uuid.UUID(foreign_create.json()["agent"]["id"])

        monkeypatch.setattr(
            assistant_routes,
            "list_gateway_sessions",
            lambda: [
                _gateway_session("owner-session", agent_id=owner_id),
                _gateway_session("foreign-session", agent_id=foreign_id),
            ],
        )

        owner_response = await client.get(f"/v1/assistant/{owner_id}/sessions")
        foreign_response = await other_user_client.get(f"/v1/assistant/{foreign_id}/sessions")

        assert owner_response.status_code == 200
        assert [item["id"] for item in owner_response.json()] == ["owner-session"]
        assert foreign_response.status_code == 200
        assert [item["id"] for item in foreign_response.json()] == ["foreign-session"]

    @pytest.mark.asyncio
    async def test_assistant_sessions_hides_foreign_and_unknown_agent_equally(
        self,
        client: AsyncClient,
        other_user_client: AsyncClient,
        monkeypatch,
    ):
        foreign_create = await other_user_client.post(
            "/v1/templates/personal_assistant/deploy",
            json={"name": "Foreign Assistant"},
        )
        foreign_id = foreign_create.json()["agent"]["id"]
        unknown_id = str(uuid.uuid4())
        discovery_calls = 0

        def discover_sessions():
            nonlocal discovery_calls
            discovery_calls += 1
            return []

        monkeypatch.setattr(assistant_routes, "list_gateway_sessions", discover_sessions)

        foreign_response = await client.get(f"/v1/assistant/{foreign_id}/sessions")
        unknown_response = await client.get(f"/v1/assistant/{unknown_id}/sessions")

        assert foreign_response.status_code == unknown_response.status_code == 404
        assert foreign_response.json() == unknown_response.json() == {"detail": "Agent not found"}
        assert discovery_calls == 0

    @pytest.mark.asyncio
    async def test_assistant_sessions_rejects_malformed_agent_id_before_discovery(
        self,
        client: AsyncClient,
        monkeypatch,
    ):
        discovery_calls = 0

        def discover_sessions():
            nonlocal discovery_calls
            discovery_calls += 1
            return []

        monkeypatch.setattr(assistant_routes, "list_gateway_sessions", discover_sessions)

        response = await client.get("/v1/assistant/not-a-uuid/sessions")

        assert response.status_code == 422
        assert discovery_calls == 0

    @pytest.mark.asyncio
    async def test_assistant_sessions_keeps_signed_legacy_binding_but_not_unclaimed_labels(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        monkeypatch,
    ):
        create_response = await client.post(
            "/v1/templates/personal_assistant/deploy",
            json={"name": "Legacy Assistant", "assistant_id": "legacy-label"},
        )
        agent_id = uuid.UUID(create_response.json()["agent"]["id"])
        claimed = _gateway_session("claimed-legacy", agent_id=agent_id, agent="legacy-label")
        assert await filter_and_claim_owned_sessions(
            db_session,
            user=test_user,
            sessions=[claimed],
            required_agent_id=agent_id,
        ) == [claimed]

        legacy_without_uuid = _gateway_session("claimed-legacy", agent="legacy-label")
        unclaimed_same_label = _gateway_session("unclaimed-legacy", agent="legacy-label")
        malformed_identity = _gateway_session(
            "malformed-provider-id",
            agent_id="not-a-uuid",
            agent="legacy-label",
        )
        monkeypatch.setattr(
            assistant_routes,
            "list_gateway_sessions",
            lambda: [legacy_without_uuid, unclaimed_same_label, malformed_identity],
        )

        response = await client.get(f"/v1/assistant/{agent_id}/sessions")
        settings = await db_session.execute(
            select(UserSetting).where(UserSetting.key.like(f"{SESSION_OWNERSHIP_PREFIX}%"))
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == ["claimed-legacy"]
        assert len(settings.scalars().all()) == 1
