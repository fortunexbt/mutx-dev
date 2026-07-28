"""Contract tests for public governance routes used by dashboard, CLI, and SDK clients."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import src.api.routes.governance as governance
from src.api.models import Agent, AgentStatus, UserSetting


@pytest.fixture(autouse=True)
def developer_principal(test_user):
    test_user.roles = ["DEVELOPER"]


async def _create_agent(db_session, *, user, name: str) -> Agent:
    agent = Agent(
        id=uuid.uuid4(),
        name=name,
        description=f"{name} description",
        config="{}",
        user_id=user.id,
        status=AgentStatus.CREATING,
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


def _identity_payload(agent_id: str, display_name: str) -> dict[str, object]:
    return governance.GovernedIdentity(
        agent_id=agent_id,
        display_name=display_name,
        updated_at="2026-04-30T00:00:00+00:00",
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_governance_contract_routes_are_mounted(client: AsyncClient):
    trust_response = await client.get("/v1/governance/trust")
    lifecycle_response = await client.get("/v1/governance/lifecycle")
    discovery_response = await client.get("/v1/governance/discovery")
    attestation_response = await client.get("/v1/governance/attestations")

    assert trust_response.status_code == 200
    assert trust_response.json() == {"items": []}
    assert lifecycle_response.status_code == 200
    assert lifecycle_response.json() == {"items": []}
    assert discovery_response.status_code == 200
    assert discovery_response.json() == {"items": []}
    assert attestation_response.status_code == 200
    assert attestation_response.json()["summary"]["identities"] == 0


@pytest.mark.asyncio
async def test_governance_updates_persist_and_preserve_unrelated_identity_state(
    client: AsyncClient,
    db_session,
    test_agent,
    test_user,
):
    trust_response = await client.post(
        f"/v1/governance/trust/{test_agent.id}",
        json={
            "score": 720,
            "reason": "production launch",
            "credential_status": "brokered",
            "capability_scope": ["tools:read"],
        },
    )
    lifecycle_response = await client.post(
        f"/v1/governance/lifecycle/{test_agent.id}",
        json={
            "state": "suspended",
            "reason": "operator pause",
            "apply_runtime_action": False,
        },
    )
    second_trust_response = await client.post(
        f"/v1/governance/trust/{test_agent.id}",
        json={"delta": 10, "resource_scope": ["cluster:staging"]},
    )

    assert trust_response.status_code == 200
    assert trust_response.json()["trust_tier"] == "elevated"
    assert lifecycle_response.status_code == 200
    assert lifecycle_response.json()["lifecycle_status"] == "suspended"
    assert second_trust_response.status_code == 200
    updated_identity = second_trust_response.json()
    assert updated_identity["trust_score"] == 730
    assert updated_identity["lifecycle_status"] == "suspended"
    assert updated_identity["capability_scope"] == ["tools:read"]
    assert updated_identity["resource_scope"] == ["cluster:staging"]

    # Drop SQLAlchemy's identity map to simulate losing all process-local state.
    db_session.expunge_all()
    list_response = await client.get("/v1/governance/lifecycle")

    assert list_response.status_code == 200
    assert list_response.json()["items"] == [second_trust_response.json()]
    result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key == governance._identity_setting_key(str(test_agent.id)),
        )
    )
    assert result.scalar_one().value["lifecycle_status"] == "suspended"
    assert not hasattr(governance, "_IDENTITIES")


@pytest.mark.asyncio
async def test_governance_trust_reads_are_tenant_scoped(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_agent,
    test_user,
    other_user,
):
    other_user.email = "other@mutx.dev"
    other_user.is_email_verified = True
    other_agent = await _create_agent(db_session, user=other_user, name="other-agent")
    db_session.add_all(
        [
            UserSetting(
                user_id=test_user.id,
                key=governance._identity_setting_key(str(test_agent.id)),
                value=_identity_payload(str(test_agent.id), "Owned agent"),
            ),
            UserSetting(
                user_id=other_user.id,
                key=governance._identity_setting_key(str(other_agent.id)),
                value=_identity_payload(str(other_agent.id), "Other agent"),
            ),
        ]
    )
    await db_session.commit()

    owned_response = await client.get("/v1/governance/trust")
    other_response = await other_user_client.get("/v1/governance/trust")

    assert owned_response.status_code == 200
    assert [item["agent_id"] for item in owned_response.json()["items"]] == [str(test_agent.id)]
    assert other_response.status_code == 200
    assert [item["agent_id"] for item in other_response.json()["items"]] == [str(other_agent.id)]


@pytest.mark.asyncio
async def test_governance_mutations_reject_invalid_and_foreign_agents(
    client: AsyncClient,
    db_session,
    test_user,
    other_user,
):
    other_agent = await _create_agent(db_session, user=other_user, name="foreign-agent")

    invalid_response = await client.post(
        "/v1/governance/trust/not-an-agent-id",
        json={"score": 720},
    )
    foreign_trust_response = await client.post(
        f"/v1/governance/trust/{other_agent.id}",
        json={"score": 720},
    )
    foreign_lifecycle_response = await client.post(
        f"/v1/governance/lifecycle/{other_agent.id}",
        json={"state": "suspended"},
    )

    assert invalid_response.status_code == 404
    assert foreign_trust_response.status_code == 404
    assert foreign_lifecycle_response.status_code == 404
    result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key.like(f"{governance._IDENTITY_SETTING_PREFIX}%"),
        )
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_governance_scan_persists_owned_findings_and_preserves_identity(
    client: AsyncClient,
    db_session,
    test_agent,
    other_user,
    monkeypatch: pytest.MonkeyPatch,
):
    from src.api.services import faramesh_supervisor

    other_agent = await _create_agent(db_session, user=other_user, name="foreign-supervised")
    trust_response = await client.post(
        f"/v1/governance/trust/{test_agent.id}",
        json={"score": 810},
    )
    assert trust_response.status_code == 200

    class FakeSupervisor:
        agents = [
            {"agent_id": str(test_agent.id)},
            {"agent_id": str(other_agent.id)},
        ]

        def list_agents(self):
            return self.agents

    supervisor = FakeSupervisor()
    monkeypatch.setattr(faramesh_supervisor, "get_faramesh_supervisor", lambda: supervisor)

    scan_response = await client.post("/v1/governance/discovery/scan")
    assert scan_response.status_code == 200
    assert scan_response.json()["count"] == 1
    assert scan_response.json()["items"][0]["entity_id"] == str(test_agent.id)
    assert scan_response.json()["items"][0]["registration_status"] == "registered"

    db_session.expunge_all()
    list_response = await client.get("/v1/governance/discovery")
    assert list_response.status_code == 200
    assert list_response.json()["items"] == scan_response.json()["items"]
    assert not hasattr(governance, "_DISCOVERY_FINDINGS")

    supervisor.agents = []
    empty_scan_response = await client.post("/v1/governance/discovery/scan")
    discovery_response = await client.get("/v1/governance/discovery")
    identity_response = await client.get("/v1/governance/trust")

    assert empty_scan_response.status_code == 200
    assert empty_scan_response.json()["items"] == []
    assert discovery_response.json() == {"items": []}
    assert identity_response.json()["items"][0]["trust_score"] == 810


@pytest.mark.asyncio
async def test_governance_attestation_verification_reflects_stored_record_integrity(
    client: AsyncClient,
    db_session,
    test_agent,
    test_user,
    other_user,
    monkeypatch: pytest.MonkeyPatch,
):
    from src.api.services import faramesh_supervisor

    other_agent = await _create_agent(db_session, user=other_user, name="foreign-attestation")

    class FakeAttestationSupervisor:
        def list_agents(self):
            return [
                {"agent_id": str(test_agent.id)},
                {"agent_id": str(other_agent.id)},
            ]

    monkeypatch.setattr(
        faramesh_supervisor,
        "get_faramesh_supervisor",
        lambda: FakeAttestationSupervisor(),
    )
    trust_response = await client.post(
        f"/v1/governance/trust/{test_agent.id}",
        json={"score": 700},
    )
    assert trust_response.status_code == 200

    foreign_setting = UserSetting(
        user_id=test_user.id,
        key=governance._identity_setting_key(str(other_agent.id)),
        value=_identity_payload(str(other_agent.id), "Foreign agent"),
    )
    db_session.add(foreign_setting)
    await db_session.commit()
    db_session.expunge_all()

    get_response = await client.get("/v1/governance/attestations")
    invalid_verify_response = await client.post("/v1/governance/attestations/verify")

    assert get_response.status_code == 200
    assert get_response.json()["summary"]["identities"] == 1
    assert get_response.json()["summary"]["supervised_agents"] == 1
    assert get_response.json()["coverage"]["receipt_integrity"] is False
    assert invalid_verify_response.status_code == 200
    assert invalid_verify_response.json()["verified"] is False
    assert invalid_verify_response.json()["compliance"]["verified"] is False

    result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key == governance._identity_setting_key(str(other_agent.id)),
        )
    )
    await db_session.delete(result.scalar_one())
    await db_session.commit()

    valid_verify_response = await client.post("/v1/governance/attestations/verify")
    assert valid_verify_response.status_code == 200
    assert valid_verify_response.json()["verified"] is True
    assert valid_verify_response.json()["coverage"]["receipt_integrity"] is True


@pytest.mark.asyncio
async def test_governance_contract_routes_require_internal_user(
    other_user_client: AsyncClient,
):
    trust_response = await other_user_client.get("/v1/governance/trust")
    lifecycle_response = await other_user_client.post(
        "/v1/governance/lifecycle/agent-1",
        json={"state": "suspended"},
    )
    attestations_response = await other_user_client.get("/v1/governance/attestations")

    assert trust_response.status_code == 403
    assert lifecycle_response.status_code == 403
    assert attestations_response.status_code == 403
