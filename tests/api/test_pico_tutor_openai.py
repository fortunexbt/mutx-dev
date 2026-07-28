import asyncio

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.api.database import Base
from src.api.models import UserSetting
from src.api.services.pico_tutor_openai import (
    PICO_TUTOR_OPENAI_KEY,
    PicoTutorOpenAIConnectionError,
    _build_user_setting_upsert,
    connect_pico_tutor_openai,
    resolve_pico_tutor_api_key,
    validate_openai_api_key,
)


@pytest_asyncio.fixture(autouse=True)
async def pro_plan(db_session, test_user):
    test_user.plan = "PRO"
    db_session.add(test_user)
    await db_session.commit()
    await db_session.refresh(test_user)
    yield


@pytest.mark.asyncio
async def test_pico_tutor_openai_connection_roundtrip(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_validate_openai_api_key(api_key: str) -> None:
        assert api_key.endswith("1234")

    monkeypatch.setattr(
        "src.api.services.pico_tutor_openai.validate_openai_api_key",
        fake_validate_openai_api_key,
    )

    status_response = await client.get("/v1/pico/tutor/openai")
    assert status_response.status_code == 200
    assert status_response.json()["status"] in {"disconnected", "platform"}

    connect_response = await client.put(
        "/v1/pico/tutor/openai",
        json={"apiKey": "sk-proj-test-openai-connection-1234"},
    )
    assert connect_response.status_code == 200
    connected = connect_response.json()
    assert connected["connected"] is True
    assert connected["source"] == "user"
    assert connected["maskedKey"].endswith("1234")
    assert connected["providerAvailable"] is True
    assert connected["entitlement"]["plan"] == "pro"
    assert connected["proof"]["kind"] == "validated_user_key"
    assert connected["proof"]["validatedAt"] == connected["validatedAt"]

    result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key == PICO_TUTOR_OPENAI_KEY,
        )
    )
    setting = result.scalar_one()
    assert setting.value["api_key_encrypted"] != "sk-proj-test-openai-connection-1234"
    assert setting.value["api_key_encrypted"].startswith("enc:")

    disconnect_response = await client.delete("/v1/pico/tutor/openai")
    assert disconnect_response.status_code == 200
    assert disconnect_response.json()["connected"] is False
    assert disconnect_response.json()["source"] in {"none", "platform"}


@pytest.mark.asyncio
async def test_pico_tutor_openai_connection_requires_authentication(client_no_auth: AsyncClient):
    response = await client_no_auth.get("/v1/pico/tutor/openai")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pico_tutor_prefers_connected_user_key_over_platform_key(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_validate_openai_api_key(_api_key: str) -> None:
        return None

    monkeypatch.setattr(
        "src.api.services.pico_tutor_openai.validate_openai_api_key",
        fake_validate_openai_api_key,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "platform-openai-key")

    connect_response = await client.put(
        "/v1/pico/tutor/openai",
        json={"apiKey": "sk-proj-user-owned-openai-key-9999"},
    )
    assert connect_response.status_code == 200

    api_key, source = await resolve_pico_tutor_api_key(db_session, user=test_user)
    assert api_key == "sk-proj-user-owned-openai-key-9999"
    assert source == "user"


@pytest.mark.asyncio
async def test_starter_can_use_platform_but_cannot_manage_byok(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
):
    test_user.plan = "STARTER"
    db_session.add(test_user)
    await db_session.commit()
    monkeypatch.setenv("OPENAI_API_KEY", "platform-openai-key")

    status_response = await client.get("/v1/pico/tutor/openai")
    connect_response = await client.put(
        "/v1/pico/tutor/openai",
        json={"apiKey": "sk-proj-starter-key-1234"},
    )
    disconnect_response = await client.delete("/v1/pico/tutor/openai")

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "platform"
    assert status_response.json()["providerAvailable"] is False
    assert status_response.json()["proof"]["kind"] == "configured_platform_key"
    assert "not validated" in status_response.json()["message"]
    assert status_response.json()["canConnect"] is False
    assert connect_response.status_code == 403
    assert connect_response.json()["detail"]["code"] == "TUTOR_BYOK_PLAN_REQUIRED"
    assert disconnect_response.status_code == 403


@pytest.mark.asyncio
async def test_free_plan_is_denied_provider_status(
    client: AsyncClient,
    db_session,
    test_user,
):
    test_user.plan = "FREE"
    db_session.add(test_user)
    await db_session.commit()

    response = await client.get("/v1/pico/tutor/openai")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TUTOR_PLAN_REQUIRED"


@pytest.mark.asyncio
async def test_invalid_byok_is_not_persisted_or_reported_connected(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
):
    async def reject_openai_api_key(_api_key: str) -> None:
        raise PicoTutorOpenAIConnectionError("Failed to validate the OpenAI key.")

    monkeypatch.setattr(
        "src.api.services.pico_tutor_openai.validate_openai_api_key",
        reject_openai_api_key,
    )

    response = await client.put(
        "/v1/pico/tutor/openai",
        json={"apiKey": "sk-proj-invalid-openai-key-1234"},
    )

    assert response.status_code == 400
    assert "validate" in response.json()["detail"].lower()
    result = await db_session.execute(
        select(UserSetting).where(
            UserSetting.user_id == test_user.id,
            UserSetting.key == PICO_TUTOR_OPENAI_KEY,
        )
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_test_prefixed_key_still_requires_provider_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted: list[dict[str, object]] = []

    class RejectingCompletions:
        async def create(self, **kwargs: object) -> None:
            attempted.append(kwargs)
            raise RuntimeError("provider rejected key")

    class RejectingChat:
        completions = RejectingCompletions()

    class RejectingClient:
        def __init__(self, *, api_key: str, timeout: float, max_retries: int) -> None:
            assert api_key == "sk-test-unvalidated-prefix"
            assert timeout == 5.0
            assert max_retries == 0
            self.chat = RejectingChat()

    monkeypatch.setattr(
        "src.api.services.pico_tutor_openai.AsyncOpenAI",
        RejectingClient,
    )

    with pytest.raises(PicoTutorOpenAIConnectionError):
        await validate_openai_api_key("sk-test-unvalidated-prefix")

    assert attempted == [
        {
            "model": "gpt-5-mini",
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_completion_tokens": 1,
        }
    ]


@pytest.mark.asyncio
async def test_connection_rejects_whitespace_keys_without_provider_io(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnexpectedClient:
        def __init__(self, **_kwargs: object) -> None:
            pytest.fail("invalid keys must not reach the provider")

    monkeypatch.setattr(
        "src.api.services.pico_tutor_openai.AsyncOpenAI",
        UnexpectedClient,
    )

    whitespace_only = await client.put(
        "/v1/pico/tutor/openai",
        json={"apiKey": "            "},
    )
    internal_whitespace = await client.put(
        "/v1/pico/tutor/openai",
        json={"apiKey": "sk-proj invalid key"},
    )

    assert whitespace_only.status_code == 422
    assert internal_whitespace.status_code == 422


@pytest.mark.asyncio
async def test_whitespace_platform_key_is_not_reported_as_configured(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "   \t  ")

    response = await client.get("/v1/pico/tutor/openai")

    assert response.status_code == 200
    assert response.json()["status"] == "disconnected"
    assert response.json()["providerAvailable"] is False


@pytest.mark.asyncio
async def test_provider_validation_error_redacts_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sk-proj-do-not-expose-this-secret"

    class RejectingClient:
        def __init__(self, *, api_key: str, **_kwargs: object) -> None:
            raise RuntimeError(f"provider rejected {api_key}")

    monkeypatch.setattr(
        "src.api.services.pico_tutor_openai.AsyncOpenAI",
        RejectingClient,
    )

    with pytest.raises(PicoTutorOpenAIConnectionError) as exc_info:
        await validate_openai_api_key(secret)

    assert secret not in str(exc_info.value)


def test_postgresql_connection_upsert_targets_user_key_constraint(test_user) -> None:
    statement = _build_user_setting_upsert(
        "postgresql",
        user_id=test_user.id,
        key=PICO_TUTOR_OPENAI_KEY,
        value={"api_key_encrypted": "redacted"},
    )
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT (user_id, key) DO UPDATE" in compiled


@pytest.mark.asyncio
async def test_concurrent_first_connections_atomically_create_one_setting(
    tmp_path,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'pico-upsert.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    entered = 0
    both_entered = asyncio.Event()

    async def synchronized_validation(_api_key: str) -> None:
        nonlocal entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await both_entered.wait()

    monkeypatch.setattr(
        "src.api.services.pico_tutor_openai.validate_openai_api_key",
        synchronized_validation,
    )
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as first_session, session_factory() as second_session:
        first, second = await asyncio.gather(
            connect_pico_tutor_openai(
                first_session,
                user=test_user,
                api_key="sk-proj-concurrent-first-1111",
            ),
            connect_pico_tutor_openai(
                second_session,
                user=test_user,
                api_key="sk-proj-concurrent-second-2222",
            ),
        )

    async with session_factory() as inspection_session:
        count = await inspection_session.scalar(
            select(func.count())
            .select_from(UserSetting)
            .where(
                UserSetting.user_id == test_user.id,
                UserSetting.key == PICO_TUTOR_OPENAI_KEY,
            )
        )

    await engine.dispose()
    assert first.connected is True
    assert second.connected is True
    assert count == 1


@pytest.mark.asyncio
async def test_saved_key_without_validation_proof_is_reported_as_error(
    client: AsyncClient,
    db_session,
    test_user,
):
    db_session.add(
        UserSetting(
            user_id=test_user.id,
            key=PICO_TUTOR_OPENAI_KEY,
            value={
                "api_key_encrypted": "not-a-usable-encrypted-value",
                "masked_key": "••••0000",
            },
        )
    )
    await db_session.commit()

    response = await client.get("/v1/pico/tutor/openai")

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["connected"] is False
    assert response.json()["providerAvailable"] is False
    assert response.json()["proof"] is None
