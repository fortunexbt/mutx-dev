"""Adversarial tenant-isolation tests for every sessions API surface."""

import asyncio
import json
from pathlib import Path
import uuid

from fastapi import HTTPException
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.api.models import Agent, AgentStatus, User, UserSetting
import src.api.routes.sessions as sessions_mod
from src.api.services.session_ownership import (
    SESSION_OWNERSHIP_PREFIX,
    filter_and_claim_owned_sessions,
)


def _session(
    session_id: str,
    *,
    agent_id: uuid.UUID | str | None = None,
    agent: str | None = None,
    assistant_id: str | None = None,
    workspace: str | None = None,
    source: str = "openclaw",
    key: str | None = None,
    last_activity: int = 1,
) -> dict[str, object]:
    session: dict[str, object] = {
        "id": session_id,
        "key": key or session_id,
        "source": source,
        "last_activity": last_activity,
    }
    if agent_id is not None:
        session["agent_id"] = str(agent_id)
    if agent is not None:
        session["agent"] = agent
    if assistant_id is not None:
        session["assistant_id"] = assistant_id
    if workspace is not None:
        session["workspace"] = workspace
    return session


async def _add_foreign_agent(
    db_session,
    other_user,
    *,
    name: str = "Other Agent",
    assistant_id: str = "other-agent",
) -> Agent:
    agent = Agent(
        id=uuid.uuid4(),
        name=name,
        config=json.dumps({"assistant_id": assistant_id, "workspace": assistant_id}),
        user_id=other_user.id,
        status=AgentStatus.RUNNING,
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


async def _grant_developer(db_session, user) -> None:
    user.roles = ["DEVELOPER"]
    await db_session.commit()


async def _bind_owner_session(db_session, test_user, session):
    visible = await filter_and_claim_owned_sessions(
        db_session,
        user=test_user,
        sessions=[session],
    )
    assert visible == [session]


def _empty_local_providers(monkeypatch) -> None:
    monkeypatch.setattr(sessions_mod, "get_local_claude_sessions", lambda: [])
    monkeypatch.setattr(sessions_mod, "get_local_codex_sessions", lambda: [])
    monkeypatch.setattr(sessions_mod, "get_local_hermes_sessions", lambda: [])


async def _request_sensitive_operation(
    client: AsyncClient,
    operation: str,
    session_key: str,
):
    if operation == "transcript":
        return await client.get(f"/v1/sessions/{session_key}/transcript")
    if operation == "control":
        return await client.post(
            f"/v1/sessions/{session_key}/control",
            json={"action": "kill"},
        )
    if operation == "mutation":
        return await client.post(
            "/v1/sessions?action=set-thinking",
            json={"session_key": session_key, "level": "high"},
        )
    if operation == "delete":
        return await client.request(
            "DELETE",
            "/v1/sessions",
            json={"session_key": session_key},
        )
    raise AssertionError(f"Unhandled operation: {operation}")


@pytest.mark.asyncio
async def test_list_filters_gateway_and_every_local_provider_by_immutable_agent_uuid(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_agent,
    other_user,
    monkeypatch,
):
    foreign_agent = await _add_foreign_agent(db_session, other_user)
    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: [
            _session("gateway-owner", agent_id=test_agent.id, last_activity=80),
            _session("gateway-foreign", agent_id=foreign_agent.id, last_activity=70),
        ],
    )
    monkeypatch.setattr(
        sessions_mod,
        "get_local_claude_sessions",
        lambda: [
            _session("claude:owner", agent_id=test_agent.id, source="claude", last_activity=60),
            _session(
                "claude:foreign",
                agent_id=foreign_agent.id,
                source="claude",
                last_activity=50,
            ),
        ],
    )
    monkeypatch.setattr(
        sessions_mod,
        "get_local_codex_sessions",
        lambda: [
            _session("codex:owner", agent_id=test_agent.id, source="codex", last_activity=40),
            _session(
                "codex:foreign",
                agent_id=foreign_agent.id,
                source="codex",
                last_activity=30,
            ),
        ],
    )
    monkeypatch.setattr(
        sessions_mod,
        "get_local_hermes_sessions",
        lambda: [
            _session("hermes:owner", agent_id=test_agent.id, source="hermes", last_activity=20),
            _session(
                "hermes:foreign",
                agent_id=foreign_agent.id,
                source="hermes",
                last_activity=10,
            ),
            _session("hermes:unbound", agent="test-agent", source="hermes"),
        ],
    )

    owner_response = await client.get("/v1/sessions")
    foreign_response = await other_user_client.get("/v1/sessions")

    assert owner_response.status_code == 200
    assert [item["id"] for item in owner_response.json()["sessions"]] == [
        "gateway-owner",
        "claude:owner",
        "codex:owner",
        "hermes:owner",
    ]
    assert foreign_response.status_code == 200
    assert [item["id"] for item in foreign_response.json()["sessions"]] == [
        "gateway-foreign",
        "claude:foreign",
        "codex:foreign",
        "hermes:foreign",
    ]


@pytest.mark.asyncio
async def test_attacker_created_matching_labels_and_same_name_agents_cannot_claim(
    client: AsyncClient,
    db_session,
    test_user,
    test_agent,
    monkeypatch,
):
    target = "host-global-victim"
    test_agent.name = target
    test_agent.config = json.dumps({"assistant_id": target, "workspace": target})
    db_session.add(
        Agent(
            id=uuid.uuid4(),
            name=target,
            config=json.dumps({"assistant_id": target, "workspace": target}),
            user_id=test_user.id,
            status=AgentStatus.RUNNING,
        )
    )
    await _grant_developer(db_session, test_user)

    label_only_sessions = [
        _session("gateway-label", agent=target, assistant_id=target, workspace=target),
        _session("claude:label", agent=target, workspace=target, source="claude"),
        _session("codex:label", assistant_id=target, workspace=target, source="codex"),
        _session("hermes:label", agent=target, workspace=target, source="hermes"),
    ]
    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: label_only_sessions[:1],
    )
    monkeypatch.setattr(sessions_mod, "get_local_claude_sessions", lambda: label_only_sessions[1:2])
    monkeypatch.setattr(sessions_mod, "get_local_codex_sessions", lambda: label_only_sessions[2:3])
    monkeypatch.setattr(sessions_mod, "get_local_hermes_sessions", lambda: label_only_sessions[3:])

    gateway_calls = 0

    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        nonlocal gateway_calls
        gateway_calls += 1
        return {"message": "unexpected"}

    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)

    listed = await client.get("/v1/sessions")
    guessed = await client.get("/v1/sessions/gateway-label/transcript")
    settings = await db_session.execute(
        select(UserSetting).where(UserSetting.key.like(f"{SESSION_OWNERSHIP_PREFIX}%"))
    )

    assert listed.status_code == 200
    assert listed.json()["sessions"] == []
    assert guessed.status_code == 404
    assert list(settings.scalars().all()) == []
    assert gateway_calls == 0


@pytest.mark.asyncio
async def test_foreign_and_guessed_encoded_aliases_are_denied_before_gateway_call(
    other_user_client: AsyncClient,
    db_session,
    test_user,
    other_user,
    test_agent,
    monkeypatch,
):
    canonical_key = f"agent:{test_agent.id}:base/private"
    owner_session = _session(
        "owner-alias",
        agent_id=test_agent.id,
        key=canonical_key,
    )
    await _bind_owner_session(db_session, test_user, owner_session)
    await _grant_developer(db_session, other_user)

    gateway_calls: list[tuple[str, str]] = []

    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        gateway_calls.append((method, path))
        return {"message": "unexpected"}

    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)
    monkeypatch.setattr(sessions_mod, "list_gateway_sessions", lambda assistant_id=None: [])
    _empty_local_providers(monkeypatch)
    encoded_key = canonical_key.replace(":", "%3A").replace("/", "%2F")

    requests = [
        other_user_client.post(
            "/v1/sessions?action=set-thinking",
            json={"session_key": "owner-alias", "level": "high"},
        ),
        other_user_client.request("DELETE", "/v1/sessions", json={"session_key": "owner-alias"}),
        other_user_client.post(
            f"/v1/sessions/{encoded_key}/control",
            json={"action": "kill"},
        ),
        other_user_client.get(f"/v1/sessions/{encoded_key}/transcript"),
        other_user_client.get("/v1/sessions/completely-guessed/transcript"),
        other_user_client.get("/v1/sessions/owner-alias%252Fextra/transcript"),
    ]
    responses = [await request for request in requests]

    assert [response.status_code for response in responses] == [404, 404, 404, 404, 404, 404]
    assert {response.json()["detail"] for response in responses} == {"Session not found"}
    assert gateway_calls == []


@pytest.mark.asyncio
async def test_owner_can_use_signed_id_and_encoded_path_aliases_across_every_endpoint(
    client: AsyncClient,
    db_session,
    test_user,
    test_agent,
    monkeypatch,
):
    await _grant_developer(db_session, test_user)
    canonical_key = f"agent:{test_agent.id}:base/run"
    owner_session = _session(
        "opaque-owner-id",
        agent_id=test_agent.id,
        key=canonical_key,
        last_activity=100,
    )
    live_sessions = [owner_session]
    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: list(live_sessions),
    )
    _empty_local_providers(monkeypatch)

    gateway_calls: list[tuple[str, str, object]] = []

    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        gateway_calls.append((method, path, json))
        if method == "DELETE":
            live_sessions.clear()
            return {"status": 204}
        if path.endswith("/history"):
            return {"messages": [{"role": "assistant", "content": "owner-only"}]}
        return {"message": "ok"}

    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)
    encoded_key = canonical_key.replace(":", "%3A").replace("/", "%2F")

    listed = await client.get("/v1/sessions")
    action = await client.post(
        "/v1/sessions?action=set-label",
        json={"session_key": "opaque-owner-id", "label": "Owner lane"},
    )
    transcript = await client.get(f"/v1/sessions/{encoded_key}/transcript")
    control = await client.post(
        f"/v1/sessions/{encoded_key}/control",
        json={"action": "kill"},
    )
    deleted = await client.request(
        "DELETE", "/v1/sessions", json={"session_key": "opaque-owner-id"}
    )
    after_delete = await client.get(f"/v1/sessions/{encoded_key}/transcript")

    quoted_key = canonical_key.replace(":", "%3A").replace("/", "%2F")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["sessions"]] == ["opaque-owner-id"]
    assert action.status_code == 200
    assert transcript.status_code == 200
    assert transcript.json()["messages"][0]["content"] == "owner-only"
    assert control.status_code == 200
    assert control.json()["current_state"] == "terminated"
    assert deleted.status_code == 200
    assert after_delete.status_code == 404
    assert gateway_calls == [
        ("PATCH", "/api/sessions/label", {"session": canonical_key, "label": "Owner lane"}),
        ("GET", f"/api/sessions/{quoted_key}/history", None),
        ("POST", f"/api/sessions/{quoted_key}/control", {"action": "kill"}),
        ("DELETE", f"/api/sessions/{quoted_key}", None),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["transcript", "control", "mutation", "delete"])
@pytest.mark.parametrize(
    "failure_mode",
    [
        "missing-record",
        "ambiguous-record",
        "recycled-key",
        "missing-identity",
        "ambiguous-identity",
        "mismatched-identity",
        "agent-owner-changed",
    ],
)
async def test_sensitive_operations_live_resolve_and_revoke_stale_bindings(
    client: AsyncClient,
    db_session,
    test_user,
    test_agent,
    other_user,
    monkeypatch,
    operation: str,
    failure_mode: str,
):
    await _grant_developer(db_session, test_user)
    requested_alias = "recycled-alias"
    canonical_key = "stable-canonical"
    bound_session = _session(
        requested_alias,
        agent_id=test_agent.id,
        key=canonical_key,
    )
    await _bind_owner_session(db_session, test_user, bound_session)

    foreign_agent_id = uuid.uuid4()
    if failure_mode == "missing-record":
        live_sessions = []
    elif failure_mode == "ambiguous-record":
        live_sessions = [bound_session, dict(bound_session)]
    elif failure_mode == "recycled-key":
        live_sessions = [
            _session(
                requested_alias,
                agent_id=test_agent.id,
                key="replacement-canonical",
            )
        ]
    elif failure_mode == "missing-identity":
        live_sessions = [_session(requested_alias, key=canonical_key)]
    elif failure_mode == "ambiguous-identity":
        ambiguous = _session(
            requested_alias,
            agent_id=test_agent.id,
            key=canonical_key,
        )
        ambiguous["session_key"] = f"agent:{foreign_agent_id}:replacement"
        live_sessions = [ambiguous]
    elif failure_mode == "mismatched-identity":
        live_sessions = [
            _session(
                requested_alias,
                agent_id=foreign_agent_id,
                key=canonical_key,
            )
        ]
    else:
        live_sessions = [bound_session]
        test_agent.user_id = other_user.id
        await db_session.commit()

    discovery_calls = 0
    gateway_calls = 0

    def discover():
        nonlocal discovery_calls
        discovery_calls += 1
        return live_sessions

    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        nonlocal gateway_calls
        gateway_calls += 1
        return {"message": "unexpected"}

    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: discover(),
    )
    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)

    response = await _request_sensitive_operation(client, operation, requested_alias)
    settings = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key.like(f"{SESSION_OWNERSHIP_PREFIX}%"),
        )
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"
    assert discovery_calls == 1
    assert gateway_calls == 0
    assert list(settings.scalars().all()) == []


@pytest.mark.asyncio
async def test_viewer_reads_but_mutations_are_denied_before_discovery_or_gateway(
    client: AsyncClient,
    db_session,
    test_user,
    test_agent,
    monkeypatch,
):
    owner_session = _session("viewer-session", agent_id=test_agent.id)
    await _bind_owner_session(db_session, test_user, owner_session)
    assert test_user.roles == ["VIEWER"]

    discovery_calls = 0
    gateway_calls = 0

    def discover():
        nonlocal discovery_calls
        discovery_calls += 1
        return [owner_session]

    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        nonlocal gateway_calls
        gateway_calls += 1
        return {"messages": []}

    monkeypatch.setattr(sessions_mod, "list_gateway_sessions", lambda assistant_id=None: discover())
    _empty_local_providers(monkeypatch)
    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)

    listed = await client.get("/v1/sessions")
    transcript = await client.get("/v1/sessions/viewer-session/transcript")
    discovery_calls = 0
    gateway_calls = 0
    denied = [
        await client.post(
            "/v1/sessions?action=set-thinking",
            json={"session_key": "unbound", "level": "high"},
        ),
        await client.request("DELETE", "/v1/sessions", json={"session_key": "viewer-session"}),
        await client.post(
            "/v1/sessions/viewer-session/control",
            json={"action": "kill"},
        ),
    ]

    assert listed.status_code == 200
    assert transcript.status_code == 200
    assert [response.status_code for response in denied] == [403, 403, 403]
    assert discovery_calls == 0
    assert gateway_calls == 0


@pytest.mark.asyncio
async def test_admin_role_is_implicit_for_session_mutation(
    client: AsyncClient,
    db_session,
    test_user,
    test_agent,
    monkeypatch,
):
    test_user.roles = ["ADMIN"]
    await db_session.commit()
    admin_session = _session("admin-session", agent_id=test_agent.id)
    await _bind_owner_session(db_session, test_user, admin_session)
    calls = 0

    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        nonlocal calls
        calls += 1
        return {"message": "ok"}

    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)
    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: [admin_session],
    )

    response = await client.post(
        "/v1/sessions?action=set-thinking",
        json={"session_key": "admin-session", "level": "high"},
    )

    assert response.status_code == 200
    assert calls == 1


@pytest.mark.asyncio
async def test_actual_local_provider_files_require_immutable_agent_uuid(
    client: AsyncClient,
    test_agent,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(sessions_mod, "list_gateway_sessions", lambda assistant_id=None: [])

    claude_dir = tmp_path / ".claude" / "projects" / "-workspace-owner"
    claude_dir.mkdir(parents=True)
    (claude_dir / "owned.jsonl").write_text(
        json.dumps({"cwd": "/workspace/owner", "agent_id": str(test_agent.id)}) + "\n"
    )
    (claude_dir / "label-only.jsonl").write_text(
        json.dumps({"cwd": "test-agent", "assistant_id": "test-agent"}) + "\n"
    )

    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "session_index.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "owned", "agent_id": str(test_agent.id)}),
                json.dumps({"id": "label-only", "assistant_id": "test-agent"}),
            ]
        )
        + "\n"
    )

    hermes_dir = tmp_path / ".hermes" / "sessions"
    hermes_dir.mkdir(parents=True)
    (hermes_dir / "sessions.json").write_text(
        json.dumps(
            {
                "owned-key": {"session_id": "owned", "agent_id": str(test_agent.id)},
                "label-key": {"session_id": "label-only", "assistant_id": "test-agent"},
            }
        )
    )

    response = await client.get("/v1/sessions")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["sessions"]} == {
        "claude:owned",
        "codex:owned",
        "hermes:owned",
    }


@pytest.mark.asyncio
async def test_duplicate_live_aliases_and_cross_user_claims_fail_closed(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_agent,
    other_user,
    monkeypatch,
):
    foreign_agent = await _add_foreign_agent(db_session, other_user)
    duplicates = [
        _session(
            "duplicate-id",
            agent_id=foreign_agent.id,
            key=f"agent:{foreign_agent.id}:base",
            last_activity=200,
        ),
        _session(
            "duplicate-id",
            agent_id=test_agent.id,
            key=f"agent:{test_agent.id}:base",
            last_activity=100,
        ),
    ]
    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: duplicates,
    )
    _empty_local_providers(monkeypatch)

    owner_response = await client.get("/v1/sessions")
    foreign_response = await other_user_client.get("/v1/sessions")

    assert owner_response.status_code == 200
    assert owner_response.json()["sessions"] == []
    assert foreign_response.status_code == 200
    assert foreign_response.json()["sessions"] == []


@pytest.mark.asyncio
async def test_persisted_alias_cannot_be_claimed_by_another_user(
    db_session,
    test_user,
    test_agent,
    other_user,
):
    foreign_agent = await _add_foreign_agent(db_session, other_user)
    owner_session = _session("shared-alias", agent_id=test_agent.id)
    foreign_session = _session("shared-alias", agent_id=foreign_agent.id)

    owner_visible = await filter_and_claim_owned_sessions(
        db_session,
        user=test_user,
        sessions=[owner_session],
    )
    foreign_visible = await filter_and_claim_owned_sessions(
        db_session,
        user=other_user,
        sessions=[foreign_session],
    )
    settings = await db_session.execute(
        select(UserSetting).where(UserSetting.key.like(f"{SESSION_OWNERSHIP_PREFIX}%"))
    )

    assert owner_visible == [owner_session]
    assert foreign_visible == []
    assert [setting.user_id for setting in settings.scalars().all()] == [test_user.id]


@pytest.mark.asyncio
async def test_concurrent_same_owner_binding_claim_is_idempotent(
    test_engine,
    test_user,
    test_agent,
):
    session_record = _session("concurrent-alias", agent_id=test_agent.id)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def claim():
        async with session_factory() as session:
            user = await session.get(User, test_user.id)
            assert user is not None
            return await filter_and_claim_owned_sessions(
                session,
                user=user,
                sessions=[session_record],
            )

    claims = await asyncio.gather(claim(), claim())
    async with session_factory() as session:
        settings = await session.execute(
            select(UserSetting).where(UserSetting.key.like(f"{SESSION_OWNERSHIP_PREFIX}%"))
        )

    assert claims == [[session_record], [session_record]]
    assert len(settings.scalars().all()) == 1


@pytest.mark.asyncio
async def test_tampered_hmac_binding_fails_closed_without_gateway_call(
    client: AsyncClient,
    db_session,
    test_user,
    test_agent,
    monkeypatch,
):
    session_record = _session("tampered-alias", agent_id=test_agent.id)
    await _bind_owner_session(db_session, test_user, session_record)
    setting_result = await db_session.execute(
        select(UserSetting).where(UserSetting.key.like(f"{SESSION_OWNERSHIP_PREFIX}%"))
    )
    setting = setting_result.scalar_one()
    assert isinstance(setting.value, dict)
    setting.value = {**setting.value, "signature": "0" * 64}
    await db_session.commit()

    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: [session_record],
    )
    _empty_local_providers(monkeypatch)
    gateway_calls = 0

    async def fake_call_gateway(method: str, path: str, json=None, params=None):
        nonlocal gateway_calls
        gateway_calls += 1
        return {"messages": []}

    monkeypatch.setattr(sessions_mod, "_call_gateway", fake_call_gateway)

    listed = await client.get("/v1/sessions")
    transcript = await client.get("/v1/sessions/tampered-alias/transcript")

    assert listed.status_code == 200
    assert listed.json()["sessions"] == []
    assert transcript.status_code == 404
    assert gateway_calls == 0


@pytest.mark.asyncio
async def test_duplicate_persisted_alias_fails_closed_for_both_users(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_user,
    test_agent,
    other_user,
    monkeypatch,
):
    session_record = _session("persisted-duplicate", agent_id=test_agent.id)
    await _bind_owner_session(db_session, test_user, session_record)
    setting_result = await db_session.execute(
        select(UserSetting).where(UserSetting.key.like(f"{SESSION_OWNERSHIP_PREFIX}%"))
    )
    setting = setting_result.scalar_one()
    db_session.add(
        UserSetting(
            user_id=other_user.id,
            key=setting.key,
            value=setting.value,
        )
    )
    await db_session.commit()

    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: [session_record],
    )
    _empty_local_providers(monkeypatch)

    owner_response = await client.get("/v1/sessions")
    foreign_response = await other_user_client.get("/v1/sessions")

    assert owner_response.status_code == 200
    assert owner_response.json()["sessions"] == []
    assert foreign_response.status_code == 200
    assert foreign_response.json()["sessions"] == []


@pytest.mark.asyncio
async def test_valid_binding_fails_closed_after_agent_owner_changes(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_user,
    test_agent,
    other_user,
    monkeypatch,
):
    session_record = _session("changed-owner", agent_id=test_agent.id)
    await _bind_owner_session(db_session, test_user, session_record)
    test_agent.user_id = other_user.id
    await db_session.commit()

    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: [session_record],
    )
    _empty_local_providers(monkeypatch)

    owner_response = await client.get("/v1/sessions")
    foreign_response = await other_user_client.get("/v1/sessions")

    assert owner_response.status_code == 200
    assert owner_response.json()["sessions"] == []
    assert foreign_response.status_code == 200
    assert foreign_response.json()["sessions"] == []


@pytest.mark.asyncio
async def test_existing_binding_remains_valid_without_mutable_provider_identity(
    client: AsyncClient,
    db_session,
    test_user,
    test_agent,
    monkeypatch,
):
    initial = _session("durable-alias", agent_id=test_agent.id, key="durable-canonical")
    await _bind_owner_session(db_session, test_user, initial)
    rebound = _session(
        "durable-alias",
        agent="renamed-agent",
        assistant_id="renamed-assistant",
        workspace="renamed-workspace",
        key="durable-canonical",
    )
    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: [rebound],
    )
    _empty_local_providers(monkeypatch)

    response = await client.get("/v1/sessions")

    assert response.status_code == 200
    assert response.json()["sessions"] == [rebound]


@pytest.mark.asyncio
async def test_owner_receives_gateway_failure_only_after_signed_authorization(
    client: AsyncClient,
    other_user_client: AsyncClient,
    db_session,
    test_user,
    test_agent,
    monkeypatch,
):
    owner_session = _session("owner-session", agent_id=test_agent.id)
    await _bind_owner_session(db_session, test_user, owner_session)
    calls = 0

    async def unavailable_gateway(method: str, path: str, json=None, params=None):
        nonlocal calls
        calls += 1
        raise HTTPException(status_code=503, detail="gateway offline")

    monkeypatch.setattr(sessions_mod, "_call_gateway", unavailable_gateway)
    monkeypatch.setattr(
        sessions_mod,
        "list_gateway_sessions",
        lambda assistant_id=None: [owner_session],
    )
    _empty_local_providers(monkeypatch)

    owner_response = await client.get("/v1/sessions/owner-session/transcript")
    foreign_response = await other_user_client.get("/v1/sessions/owner-session/transcript")

    assert owner_response.status_code == 503
    assert owner_response.json()["detail"] == "gateway offline"
    assert foreign_response.status_code == 404
    assert foreign_response.json()["detail"] == "Session not found"
    assert calls == 1
