"""Durability and tenant-boundary contracts for Pico onboarding sessions."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from src.api.auth.dependencies import get_current_user, get_current_user_optional
from src.api.auth.jwt import ALGORITHM, settings as jwt_settings
from src.api.database import get_db
from src.api.models import UserSetting
from src.api.models.pico_onboarding import OnboardingState, PicoChatResponse
from src.api.services.pico_onboarding_sessions import (
    PICO_ONBOARDING_REQUEST_PREFIX,
    PICO_ONBOARDING_SESSION_PREFIX,
    PicoOnboardingSessionChangedError,
    get_onboarding_session,
    record_package_generation,
)


@pytest_asyncio.fixture(autouse=True)
async def starter_users(db_session, test_user, other_user):
    test_user.plan = "STARTER"
    other_user.plan = "STARTER"
    db_session.add_all([test_user, other_user])
    await db_session.commit()


@pytest_asyncio.fixture
async def concurrent_client(test_engine, test_user):
    """Use one database session per request, matching production concurrency."""
    from src.api.main import create_app

    app = create_app(
        enable_lifespan=False,
        background_monitor_enabled=False,
        database_required_on_startup=False,
    )
    request_session_factory = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with request_session_factory() as request_db:
            yield request_db

    async def override_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_user_optional] = override_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as request_client:
        yield request_client

    app.dependency_overrides.clear()


def _coach_response(**state):
    return PicoChatResponse(
        reply="Saved this setup turn.",
        onboarding_state=OnboardingState(**state),
    )


@pytest.mark.asyncio
async def test_anonymous_coaching_is_explicitly_not_persisted(client_no_auth, monkeypatch):
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(return_value=_coach_response(stack="hermes")),
    )

    response = await client_no_auth.post(
        "/v1/pico/chat",
        json={"message": "What can Pico help me install?"},
    )

    assert response.status_code == 200
    assert response.json()["session_id"] is None
    assert response.json()["session_persisted"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer definitely-not-a-valid-token",
        "Basic supplied-but-not-bearer",
    ],
)
async def test_supplied_invalid_credentials_never_downgrade_to_anonymous(
    client_no_auth,
    monkeypatch,
    authorization,
):
    coach = AsyncMock(return_value=_coach_response(stack="hermes"))
    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", coach)

    response = await client_no_auth.post(
        "/v1/pico/chat",
        headers={"Authorization": authorization},
        json={"message": "Do not treat this as anonymous"},
    )

    assert response.status_code == 401
    assert coach.await_count == 0


@pytest.mark.asyncio
async def test_supplied_invalid_api_key_never_downgrades_to_anonymous(
    client_no_auth,
    monkeypatch,
):
    async def mark_invalid_api_key(request, _token):
        request.state.auth_credential_error = "invalid"

    coach = AsyncMock(return_value=_coach_response(stack="hermes"))
    monkeypatch.setattr("src.api.middleware.auth._populate_api_key_context", mark_invalid_api_key)
    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", coach)

    response = await client_no_auth.post(
        "/v1/pico/chat",
        headers={"X-API-Key": "definitely-not-a-valid-key"},
        json={"message": "Do not treat this API key as anonymous"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "API-Key"
    assert coach.await_count == 0


@pytest.mark.asyncio
async def test_api_key_lookup_failure_is_retryable_and_never_anonymous(
    client_no_auth,
    monkeypatch,
):
    async def mark_failed_api_key_lookup(request, _token):
        request.state.auth_credential_error = "lookup_failed"

    coach = AsyncMock(return_value=_coach_response(stack="hermes"))
    monkeypatch.setattr(
        "src.api.middleware.auth._populate_api_key_context",
        mark_failed_api_key_lookup,
    )
    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", coach)

    response = await client_no_auth.post(
        "/v1/pico/chat",
        headers={"X-API-Key": "temporarily-unavailable-key"},
        json={"message": "Retry authentication instead of going anonymous"},
    )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert coach.await_count == 0


@pytest.mark.asyncio
async def test_valid_api_key_context_persists_the_coaching_session(
    client_no_auth,
    test_user,
    monkeypatch,
):
    async def mark_valid_api_key(request, _token):
        request.state.auth_user_id = test_user.id
        request.state.auth_method = "api_key"
        request.state.auth_credential_error = None

    monkeypatch.setattr("src.api.middleware.auth._populate_api_key_context", mark_valid_api_key)
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(return_value=_coach_response(stack="hermes")),
    )

    response = await client_no_auth.post(
        "/v1/pico/chat",
        headers={"X-API-Key": "mutx_live_test"},
        json={"message": "Persist this authenticated setup"},
    )

    assert response.status_code == 200
    assert response.json()["session_persisted"] is True
    assert response.json()["session_id"]


@pytest.mark.asyncio
async def test_expired_bearer_never_downgrades_to_anonymous(client_no_auth, monkeypatch):
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "11111111-1111-4111-a111-111111111111",
            "type": "access",
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        jwt_settings.jwt_secret,
        algorithm=ALGORITHM,
    )
    coach = AsyncMock(return_value=_coach_response(stack="hermes"))
    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", coach)

    response = await client_no_auth.post(
        "/v1/pico/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "This session is stale"},
    )

    assert response.status_code == 401
    assert coach.await_count == 0


@pytest.mark.asyncio
async def test_session_survives_fresh_app_instance(
    client: AsyncClient,
    db_session,
    test_engine,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(return_value=_coach_response(stack="hermes", os="macos")),
    )
    created = await client.post(
        "/v1/pico/chat",
        json={"message": "Hermes on my Mac", "request_id": "restart-proof"},
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    stored_result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key == f"{PICO_ONBOARDING_SESSION_PREFIX}{session_id}",
        )
    )
    assert stored_result.scalar_one().value["history"][0]["content"] == "Hermes on my Mac"

    from src.api.routes import pico as pico_routes

    assert not hasattr(pico_routes, "_sessions")

    from src.api.main import create_app

    fresh_app = create_app(
        enable_lifespan=False,
        background_monitor_enabled=False,
        database_required_on_startup=False,
    )

    restarted_session_factory = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with restarted_session_factory() as restarted_db:
            yield restarted_db

    async def override_user():
        return test_user

    fresh_app.dependency_overrides[get_db] = override_get_db
    fresh_app.dependency_overrides[get_current_user] = override_user
    fresh_app.dependency_overrides[get_current_user_optional] = override_user

    async with AsyncClient(
        transport=ASGITransport(app=fresh_app),
        base_url="http://test",
    ) as restarted_client:
        resumed = await restarted_client.get(
            "/v1/pico/session",
            params={"session_id": session_id},
        )

    assert resumed.status_code == 200
    assert resumed.json()["history"][0]["content"] == "Hermes on my Mac"
    assert resumed.json()["onboarding_state"]["stack"] == "hermes"


@pytest.mark.asyncio
async def test_canonical_history_merges_state_and_deduplicates_request(
    client: AsyncClient,
    monkeypatch,
):
    coach = AsyncMock(
        side_effect=[
            _coach_response(stack="hermes", os="linux"),
            _coach_response(provider="openai", goal="install"),
        ]
    )
    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", coach)

    first = await client.post(
        "/v1/pico/chat",
        json={"message": "Use Hermes on Linux", "request_id": "turn-1"},
    )
    session_id = first.json()["session_id"]
    duplicate = await client.post(
        "/v1/pico/chat",
        json={
            "message": "Use Hermes on Linux",
            "session_id": session_id,
            "request_id": "turn-1",
        },
    )
    second = await client.post(
        "/v1/pico/chat",
        json={
            "message": "OpenAI for a fresh install",
            "session_id": session_id,
            "request_id": "turn-2",
        },
    )
    resumed = await client.get("/v1/pico/session", params={"session_id": session_id})

    assert duplicate.json() == first.json()
    assert second.json()["ready_for_package"] is True
    assert len(resumed.json()["history"]) == 4
    state = resumed.json()["onboarding_state"]
    assert state["stack"] == "hermes"
    assert state["os"] == "linux"
    assert state["provider"] == "openai"
    assert state["goal"] == "install"
    assert coach.await_count == 2


@pytest.mark.asyncio
async def test_request_id_conflict_is_user_scoped_and_precedes_model_invocation(
    client: AsyncClient,
    monkeypatch,
):
    coach = AsyncMock(return_value=_coach_response(stack="hermes"))
    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", coach)

    first = await client.post(
        "/v1/pico/chat",
        json={"message": "Original content", "request_id": "same-user-key"},
    )
    conflict = await client.post(
        "/v1/pico/chat",
        json={"message": "Different content", "request_id": "same-user-key"},
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert coach.await_count == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_request_invokes_model_once_and_replays_result(
    concurrent_client: AsyncClient,
    monkeypatch,
):
    generation_started = asyncio.Event()
    release_generation = asyncio.Event()
    calls = 0

    async def blocking_coach(**_kwargs):
        nonlocal calls
        calls += 1
        generation_started.set()
        await release_generation.wait()
        return _coach_response(stack="hermes", os="linux")

    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", blocking_coach)
    payload = {"message": "One durable request", "request_id": "concurrent-duplicate"}

    first_task = asyncio.create_task(concurrent_client.post("/v1/pico/chat", json=payload))
    await asyncio.wait_for(generation_started.wait(), timeout=2)
    duplicate_task = asyncio.create_task(concurrent_client.post("/v1/pico/chat", json=payload))
    await asyncio.sleep(0.1)

    assert calls == 1
    release_generation.set()
    first, duplicate = await asyncio.gather(first_task, duplicate_task)

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json() == first.json()
    assert calls == 1


@pytest.mark.asyncio
async def test_reset_during_initial_generation_prevents_session_persistence(
    concurrent_client: AsyncClient,
    test_engine,
    test_user,
    monkeypatch,
):
    generation_started = asyncio.Event()
    release_generation = asyncio.Event()

    async def blocking_coach(**_kwargs):
        generation_started.set()
        await release_generation.wait()
        return _coach_response(stack="hermes")

    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", blocking_coach)
    chat_task = asyncio.create_task(
        concurrent_client.post(
            "/v1/pico/chat",
            json={"message": "This turn must lose to reset", "request_id": "reset-race"},
        )
    )
    await asyncio.wait_for(generation_started.wait(), timeout=2)

    reset = await concurrent_client.delete("/v1/pico/session")
    release_generation.set()
    chat = await chat_task

    assert reset.status_code == 204
    assert chat.status_code == 410

    inspection_factory = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with inspection_factory() as inspection_db:
        result = await inspection_db.execute(
            select(UserSetting).where(
                UserSetting.user_id == test_user.id,
                UserSetting.key.like(f"{PICO_ONBOARDING_SESSION_PREFIX}%"),
            )
        )
        stored = result.scalar_one().value
    assert stored["history"] == []
    assert stored["abandoned_at"] is not None


@pytest.mark.asyncio
async def test_concurrent_distinct_turn_waits_and_generates_from_fresh_history(
    concurrent_client: AsyncClient,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(return_value=_coach_response(stack="hermes")),
    )
    created = await concurrent_client.post("/v1/pico/chat", json={"message": "Initial turn"})
    session_id = created.json()["session_id"]

    first_started = asyncio.Event()
    release_first = asyncio.Event()
    observed_histories: dict[str, list[str]] = {}

    async def serialized_coach(*, request, history, **_kwargs):
        observed_histories[request.message] = [message.content for message in history]
        if request.message == "Concurrent turn A":
            first_started.set()
            await release_first.wait()
            return _coach_response(os="linux")
        return _coach_response(provider="openai", goal="install")

    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", serialized_coach)
    first_task = asyncio.create_task(
        concurrent_client.post(
            "/v1/pico/chat",
            json={
                "message": "Concurrent turn A",
                "session_id": session_id,
                "request_id": "serialized-a",
            },
        )
    )
    await asyncio.wait_for(first_started.wait(), timeout=2)
    second_task = asyncio.create_task(
        concurrent_client.post(
            "/v1/pico/chat",
            json={
                "message": "Concurrent turn B",
                "session_id": session_id,
                "request_id": "serialized-b",
            },
        )
    )
    await asyncio.sleep(0.1)

    assert "Concurrent turn B" not in observed_histories
    release_first.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert first.status_code == 200
    assert second.status_code == 200
    assert "Concurrent turn A" in observed_histories["Concurrent turn B"]
    assert second.json()["ready_for_package"] is True


@pytest.mark.asyncio
async def test_start_over_durably_prevents_reload_from_resuming_any_older_session(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(return_value=_coach_response(stack="hermes")),
    )
    older = await client.post("/v1/pico/chat", json={"message": "First attempt"})
    latest = await client.post("/v1/pico/chat", json={"message": "Second attempt"})
    latest_session_id = latest.json()["session_id"]

    reset = await client.delete("/v1/pico/session")
    reloaded = await client.get("/v1/pico/session")
    exact_abandoned = await client.get(
        "/v1/pico/session",
        params={"session_id": latest_session_id},
    )
    older_exact = await client.get(
        "/v1/pico/session",
        params={"session_id": older.json()["session_id"]},
    )

    stored_result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key == f"{PICO_ONBOARDING_SESSION_PREFIX}{latest_session_id}",
        )
    )

    assert reset.status_code == 204
    assert reloaded.status_code == 204
    assert exact_abandoned.status_code == 410
    assert "reset" in exact_abandoned.json()["detail"].lower()
    assert older_exact.status_code == 410
    assert stored_result.scalar_one().value["abandoned_at"] is not None


@pytest.mark.asyncio
async def test_start_over_requires_authentication(client_no_auth: AsyncClient):
    response = await client_no_auth.delete("/v1/pico/session")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_foreign_session_id_is_not_resumable_or_downloadable(
    client: AsyncClient,
    other_user_client: AsyncClient,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(
            return_value=_coach_response(
                stack="hermes",
                os="macos",
                provider="openai",
                goal="install",
            )
        ),
    )
    created = await client.post("/v1/pico/chat", json={"message": "Ready setup"})
    session_id = created.json()["session_id"]

    resumed = await other_user_client.get(
        "/v1/pico/session",
        params={"session_id": session_id},
    )
    downloaded = await other_user_client.post(
        "/v1/pico/generate-package",
        json={"session_id": session_id},
    )
    reset = await other_user_client.delete(
        "/v1/pico/session",
        params={"session_id": session_id},
    )

    assert resumed.status_code == 404
    assert downloaded.status_code == 404
    assert reset.status_code == 404


@pytest.mark.asyncio
async def test_expired_session_requires_a_new_conversation(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(
            return_value=_coach_response(
                stack="hermes",
                os="macos",
                provider="openai",
                goal="install",
            )
        ),
    )
    created = await client.post("/v1/pico/chat", json={"message": "Ready setup"})
    session_id = created.json()["session_id"]

    result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key == f"{PICO_ONBOARDING_SESSION_PREFIX}{session_id}",
        )
    )
    setting = result.scalar_one()
    value = dict(setting.value)
    value["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    setting.value = value
    await db_session.commit()

    resumed = await client.get("/v1/pico/session", params={"session_id": session_id})
    downloaded = await client.post(
        "/v1/pico/generate-package",
        json={"session_id": session_id},
    )

    assert resumed.status_code == 410
    assert downloaded.status_code == 410
    assert "expired" in resumed.json()["detail"].lower()


@pytest.mark.asyncio
async def test_package_record_rejects_a_session_that_changed_after_snapshot(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch,
):
    coach = AsyncMock(
        return_value=_coach_response(
            stack="hermes",
            os="linux",
            provider="openai",
            goal="install",
        )
    )
    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", coach)
    created = await client.post(
        "/v1/pico/chat",
        json={"message": "Build the first package", "request_id": "package-snapshot"},
    )
    session_id = created.json()["session_id"]
    captured = await get_onboarding_session(
        db_session,
        user=test_user,
        session_id=session_id,
    )

    coach.return_value = _coach_response(
        stack="hermes",
        os="linux",
        provider="anthropic",
        goal="install",
    )
    updated = await client.post(
        "/v1/pico/chat",
        json={
            "message": "Switch the provider",
            "session_id": session_id,
            "request_id": "package-newer-turn",
        },
    )

    assert updated.status_code == 200
    with pytest.raises(PicoOnboardingSessionChangedError):
        await record_package_generation(
            db_session,
            user=test_user,
            session_id=session_id,
            filename="stale-package.zip",
            state=captured.onboarding_state,
            expected_revision=captured.revision,
        )


@pytest.mark.asyncio
async def test_package_route_returns_retryable_conflict_when_snapshot_changes(
    client: AsyncClient,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(
            return_value=_coach_response(
                stack="hermes",
                os="linux",
                provider="openai",
                goal="install",
            )
        ),
    )
    created = await client.post("/v1/pico/chat", json={"message": "Ready package"})
    monkeypatch.setattr(
        "src.api.routes.pico.record_package_generation",
        AsyncMock(side_effect=PicoOnboardingSessionChangedError),
    )

    response = await client.post(
        "/v1/pico/generate-package",
        json={"session_id": created.json()["session_id"]},
    )

    assert response.status_code == 409
    assert response.headers["retry-after"] == "0"
    assert "changed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_history_idempotency_and_package_metadata_stay_bounded(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch,
):
    coach = AsyncMock(
        return_value=PicoChatResponse(
            reply="x" * 20_000,
            onboarding_state=OnboardingState(
                stack="hermes",
                os="linux",
                provider="openai",
                goal="install",
            ),
        )
    )
    monkeypatch.setattr("src.api.routes.pico.handle_coach_chat", coach)

    session_id = None
    for turn in range(55):
        response = await client.post(
            "/v1/pico/chat",
            json={
                "message": f"Bounded turn {turn}",
                **({"session_id": session_id} if session_id else {}),
                "request_id": f"bounded-{turn}",
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]

    resumed = await client.get("/v1/pico/session", params={"session_id": session_id})
    assert resumed.status_code == 200
    assert "compacted" in resumed.json()["history"][0]["content"]
    assert resumed.json()["ready_for_package"] is True

    current_record = await get_onboarding_session(
        db_session,
        user=test_user,
        session_id=session_id,
    )

    for generation in range(25):
        await record_package_generation(
            db_session,
            user=test_user,
            session_id=session_id,
            filename=f"package-{generation}.zip",
            state=OnboardingState(
                stack="hermes",
                os="linux",
                provider="openai",
                goal="install",
            ),
            expected_revision=current_record.revision,
        )

    stored_result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key == f"{PICO_ONBOARDING_SESSION_PREFIX}{session_id}",
        )
    )
    stored = stored_result.scalar_one().value
    request_result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key.like(f"{PICO_ONBOARDING_REQUEST_PREFIX}%"),
        )
    )

    assert len(stored["history"]) <= 24
    assert stored["compacted_messages"] > 0
    assert len(stored["package_generations"]) == 20
    assert len(json.dumps(stored, separators=(",", ":")).encode("utf-8")) <= 64 * 1024
    assert len(list(request_result.scalars())) == 50


@pytest.mark.asyncio
async def test_durable_session_count_is_bounded_and_eviction_is_honest(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(return_value=_coach_response(stack="hermes")),
    )

    session_ids = []
    for turn in range(12):
        response = await client.post(
            "/v1/pico/chat",
            json={"message": f"Independent session {turn}"},
        )
        assert response.status_code == 200
        session_ids.append(response.json()["session_id"])

    stored_result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key.like(f"{PICO_ONBOARDING_SESSION_PREFIX}%"),
        )
    )
    evicted = await client.get(
        "/v1/pico/session",
        params={"session_id": session_ids[0]},
    )
    latest = await client.get("/v1/pico/session")

    assert len(list(stored_result.scalars())) == 10
    assert evicted.status_code == 404
    assert latest.status_code == 200
    assert latest.json()["session_id"] == session_ids[-1]
