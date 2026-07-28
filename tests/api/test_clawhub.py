"""Lifecycle contract tests for /clawhub endpoints."""

import json
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.models import Agent, AgentStatus
from src.api.services.assistant_control_plane import record_assistant_skill_reconciliation


@pytest_asyncio.fixture(autouse=True)
async def developer_principals(db_session, test_user, other_user):
    test_user.roles = ["DEVELOPER"]
    other_user.roles = ["DEVELOPER"]
    await db_session.commit()


async def _create_assistant(client: AsyncClient, name: str = "Skills Assistant") -> str:
    response = await client.post(
        "/v1/templates/personal_assistant/deploy",
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["agent"]["id"]


def _skill(payload: list[dict], skill_id: str) -> dict:
    return next(item for item in payload if item["id"] == skill_id)


class TestClawHubSkillManagement:
    @pytest.mark.asyncio
    async def test_install_skill_requires_auth(self, client_no_auth: AsyncClient, test_agent):
        response = await client_no_auth.post(
            "/v1/clawhub/install",
            json={"agent_id": str(test_agent.id), "skill_id": "web_search"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_install_bundle_requires_auth(self, client_no_auth: AsyncClient, test_agent):
        response = await client_no_auth.post(
            "/v1/clawhub/install-bundle",
            json={"agent_id": str(test_agent.id), "bundle_id": "orchestra-research-foundation"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_install_skill_other_user_forbidden(
        self,
        other_user_client: AsyncClient,
        db_session: AsyncSession,
        test_user,
    ):
        agent = Agent(
            name="owned-by-test-user",
            description="for clawhub auth test",
            config="{}",
            user_id=test_user.id,
            status=AgentStatus.CREATING,
        )
        db_session.add(agent)
        await db_session.commit()
        await db_session.refresh(agent)

        response = await other_user_client.post(
            "/v1/clawhub/install",
            json={"agent_id": str(agent.id), "skill_id": "web_search"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_catalog_reports_available_without_claiming_ready(
        self, client: AsyncClient, tmp_path, monkeypatch
    ):
        skill_dir = tmp_path / "workspace-skills" / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "# Demo Skill\nA workspace-discovered skill.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "src.api.services.assistant_control_plane._candidate_skill_roots",
            lambda: [tmp_path / "workspace-skills"],
        )

        response = await client.get("/v1/clawhub/skills")

        assert response.status_code == 200
        skill = _skill(response.json(), "demo-skill")
        assert skill["status"] == "available"
        assert skill["available"] is True
        assert skill["configured"] is False
        assert skill["runtime_ready"] is False
        assert skill["installed"] is False

    @pytest.mark.asyncio
    async def test_list_bundles_reports_artifact_availability(self, client: AsyncClient):
        response = await client.get("/v1/clawhub/bundles")

        assert response.status_code == 200
        payload = response.json()
        bundle = next(item for item in payload if item["id"] == "orchestra-research-foundation")
        assert bundle["available_skill_count"] <= bundle["skill_count"]
        assert len(bundle["unavailable_skill_ids"]) == (
            bundle["skill_count"] - bundle["available_skill_count"]
        )

    @pytest.mark.asyncio
    async def test_created_assistant_skills_are_configured_until_reconciled(
        self, client: AsyncClient
    ):
        agent_id = await _create_assistant(client)

        response = await client.get(f"/v1/assistant/{agent_id}/skills")

        assert response.status_code == 200
        skill = _skill(response.json(), "web_search")
        assert skill["status"] == "configured"
        assert skill["configured"] is True
        assert skill["reconciliation_required"] is True
        assert skill["runtime_ready"] is False
        assert skill["installed"] is False

    @pytest.mark.asyncio
    async def test_install_persists_configured_state_and_reloads(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        agent_id = await _create_assistant(client)

        response = await client.post(
            "/v1/clawhub/install",
            json={"agent_id": agent_id, "skill_id": "browser_control"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "configured"
        assert payload["operation"] == "configure"
        assert payload["configured"] is True
        assert payload["runtime_ready"] is False
        assert payload["reconciliation_required"] is True
        assert payload["skill"]["installed"] is False

        agent = await db_session.get(Agent, uuid.UUID(agent_id))
        assert agent is not None
        persisted_config = json.loads(agent.config)
        assert "browser_control" in persisted_config["skills"]
        assert (
            persisted_config["metadata"]["skill_reconciliation"]["browser_control"]["status"]
            == "configured"
        )

        reload_response = await client.get(f"/v1/assistant/{agent_id}/skills")
        reloaded_skill = _skill(reload_response.json(), "browser_control")
        assert reloaded_skill["status"] == "configured"
        assert reloaded_skill["configured"] is True
        assert reloaded_skill["runtime_ready"] is False

    @pytest.mark.asyncio
    async def test_runtime_reconciliation_and_failure_are_reported_from_persisted_evidence(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        agent_id = await _create_assistant(client)
        install_response = await client.post(
            "/v1/clawhub/install",
            json={"agent_id": agent_id, "skill_id": "browser_control"},
        )
        assert install_response.status_code == 200

        agent = await db_session.get(Agent, uuid.UUID(agent_id))
        assert agent is not None
        record_assistant_skill_reconciliation(
            agent,
            skill_id="browser_control",
            status="runtime_ready",
            detail="OpenClaw acknowledged the skill manifest.",
        )
        record_assistant_skill_reconciliation(
            agent,
            skill_id="workspace_memory",
            status="failed",
            detail="OpenClaw rejected the skill manifest.",
        )
        await db_session.commit()

        response = await client.get(f"/v1/assistant/{agent_id}/skills")

        runtime_ready = _skill(response.json(), "browser_control")
        assert runtime_ready["status"] == "runtime_ready"
        assert runtime_ready["runtime_ready"] is True
        assert runtime_ready["installed"] is True
        assert runtime_ready["reconciliation_required"] is False

        failed = _skill(response.json(), "workspace_memory")
        assert failed["status"] == "failed"
        assert failed["runtime_ready"] is False
        assert failed["installed"] is False
        assert failed["reconciliation_required"] is True
        assert failed["reconciliation_error"] == "OpenClaw rejected the skill manifest."

    @pytest.mark.asyncio
    async def test_remove_clears_configuration_and_reconciliation_on_reload(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        agent_id = await _create_assistant(client)
        install_response = await client.post(
            "/v1/clawhub/install",
            json={"agent_id": agent_id, "skill_id": "browser_control"},
        )
        assert install_response.status_code == 200

        response = await client.post(
            "/v1/clawhub/uninstall",
            json={"agent_id": agent_id, "skill_id": "browser_control"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "removed"
        assert payload["operation"] == "remove"
        assert payload["configured"] is False
        assert payload["runtime_ready"] is False
        assert payload["reconciliation_required"] is False
        assert payload["skill"]["status"] == "available"

        agent = await db_session.get(Agent, uuid.UUID(agent_id))
        assert agent is not None
        persisted_config = json.loads(agent.config)
        assert "browser_control" not in persisted_config["skills"]
        assert "browser_control" not in persisted_config["metadata"]["skill_reconciliation"]

        reload_response = await client.get(f"/v1/assistant/{agent_id}/skills")
        reloaded_skill = _skill(reload_response.json(), "browser_control")
        assert reloaded_skill["status"] == "available"
        assert reloaded_skill["configured"] is False

    @pytest.mark.asyncio
    async def test_bundle_response_separates_configured_ready_and_unavailable(
        self, client: AsyncClient, tmp_path, monkeypatch
    ):
        skill_root = tmp_path / "skills"
        for skill_id in ("langchain", "llamaindex"):
            skill_dir = skill_root / skill_id
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"# {skill_id}\nAvailable for bundle testing.\n",
                encoding="utf-8",
            )
        monkeypatch.setattr(
            "src.api.services.assistant_control_plane._candidate_skill_roots",
            lambda: [skill_root],
        )
        agent_id = await _create_assistant(client)

        response = await client.post(
            "/v1/clawhub/install-bundle",
            json={"agent_id": agent_id, "bundle_id": "orchestra-research-foundation"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "configured"
        assert payload["configured_skill_ids"] == ["langchain", "llamaindex"]
        assert payload["newly_configured_skill_ids"] == ["langchain", "llamaindex"]
        assert payload["runtime_ready_skill_ids"] == []
        assert payload["installed_skill_ids"] == []
        assert payload["reconciliation_required_skill_ids"] == ["langchain", "llamaindex"]
        assert payload["reconciliation_required"] is True
        assert "0-autoresearch-skill" in payload["unavailable_skill_ids"]
        assert _skill(payload["skills"], "langchain")["status"] == "configured"

        reload_response = await client.get(f"/v1/assistant/{agent_id}/skills")
        assert _skill(reload_response.json(), "langchain")["status"] == "configured"

    @pytest.mark.asyncio
    async def test_install_errors_use_failed_lifecycle_envelopes(
        self, client: AsyncClient, monkeypatch
    ):
        monkeypatch.setattr(
            "src.api.services.assistant_control_plane._candidate_skill_roots", lambda: []
        )
        agent_id = await _create_assistant(client)

        unknown = await client.post(
            "/v1/clawhub/install",
            json={"agent_id": agent_id, "skill_id": "not-a-real-skill"},
        )
        assert unknown.status_code == 404
        assert unknown.json() == {
            "status": "failed",
            "operation": "configure",
            "detail": "Unknown skill: not-a-real-skill",
            "skill_id": "not-a-real-skill",
        }

        unavailable = await client.post(
            "/v1/clawhub/install",
            json={"agent_id": agent_id, "skill_id": "0-autoresearch-skill"},
        )
        assert unavailable.status_code == 409
        assert unavailable.json()["status"] == "failed"
        assert unavailable.json()["operation"] == "configure"
        assert "unavailable" in unavailable.json()["detail"]
