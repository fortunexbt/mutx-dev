import pytest
import pytest_asyncio
from httpx import AsyncClient

from src.api.models.pico_tutor import PicoTutorGenerationProof, PicoTutorResponse
from src.api.services.pico_tutor import OfficialEvidence, PicoTutorGenerationFailure


@pytest_asyncio.fixture(autouse=True)
async def live_tutor_contract(db_session, test_user, monkeypatch: pytest.MonkeyPatch):
    test_user.plan = "STARTER"
    db_session.add(test_user)
    await db_session.commit()
    monkeypatch.setenv("OPENAI_API_KEY", "platform-openai-key")

    async def fake_generate_with_model(*, fallback_reply, entitlement, **_kwargs):
        return PicoTutorResponse(
            **fallback_reply.model_dump(),
            entitlement=entitlement,
            generation=PicoTutorGenerationProof(
                source="platform",
                model="gpt-5-mini",
                responseId="chatcmpl-pytest-proof",
                completedAt="2026-07-28T12:00:00Z",
            ),
        )

    monkeypatch.setattr(
        "src.api.services.pico_tutor._generate_with_model",
        fake_generate_with_model,
    )


@pytest.mark.asyncio
async def test_pico_tutor_returns_structured_install_guidance(client: AsyncClient):
    response = await client.post(
        "/v1/pico/tutor",
        json={
            "question": "Hermes is not on my path after install. What should I do first?",
            "lessonSlug": "install-hermes-locally",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "install"
    assert data["structured"]["steps"]
    assert data["recommendedLessonIds"][0] == "install-hermes-locally"
    assert data["structured"]["sources"][0]["kind"] in {"lesson", "knowledge_pack"}
    assert data["entitlement"]["plan"] == "starter"
    assert data["generation"] == {
        "provider": "openai",
        "source": "platform",
        "model": "gpt-5-mini",
        "responseId": "chatcmpl-pytest-proof",
        "completedAt": "2026-07-28T12:00:00Z",
    }


@pytest.mark.asyncio
async def test_pico_tutor_requires_authentication(client_no_auth: AsyncClient):
    response = await client_no_auth.post(
        "/v1/pico/tutor",
        json={
            "question": "How do I reach my Hermes gateway over Tailscale without exposing it to the public internet?",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pico_tutor_denies_free_plan_without_generating(
    client: AsyncClient,
    db_session,
    test_user,
):
    test_user.plan = "FREE"
    db_session.add(test_user)
    await db_session.commit()

    response = await client.post(
        "/v1/pico/tutor",
        json={"question": "Which Academy step should I inspect?"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TUTOR_PLAN_REQUIRED"


@pytest.mark.asyncio
async def test_pico_tutor_distinguishes_missing_provider(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = await client.post(
        "/v1/pico/tutor",
        json={"question": "What should I verify next?"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TUTOR_PROVIDER_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (
            PicoTutorGenerationFailure(
                status_code=429,
                code="TUTOR_RATE_LIMITED",
                message="The Tutor model is rate limited.",
            ),
            429,
        ),
        (
            PicoTutorGenerationFailure(
                status_code=503,
                code="TUTOR_MODEL_UNAVAILABLE",
                message="The Tutor model is unavailable.",
            ),
            503,
        ),
    ],
)
async def test_pico_tutor_preserves_transient_model_failure(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    failure: PicoTutorGenerationFailure,
    expected_status: int,
):
    async def fail_generation(**_kwargs):
        return failure

    monkeypatch.setattr("src.api.services.pico_tutor._generate_with_model", fail_generation)

    response = await client.post(
        "/v1/pico/tutor",
        json={"question": "What should I verify next?"},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == failure.code


@pytest.mark.asyncio
async def test_pico_tutor_prefers_private_tailscale_guidance(client: AsyncClient):
    response = await client.post(
        "/v1/pico/tutor",
        json={
            "question": "How do I reach my Hermes gateway over Tailscale without exposing it to the public internet?",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "tailscale"
    assert "private tailnet" in data["structured"]["diagnosis"].lower()
    assert any(
        "tailscale" in step.lower() or "tailnet" in step.lower()
        for step in data["structured"]["steps"]
    )


@pytest.mark.asyncio
async def test_pico_tutor_escalates_risky_requests(client: AsyncClient):
    response = await client.post(
        "/v1/pico/tutor",
        json={
            "question": "I may have leaked a production token. Should I disable protections and expose the admin port while I debug?",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["escalate"] is True
    assert "High-risk topic" in data["escalationReason"]
    assert data["confidence"] == "low"


@pytest.mark.asyncio
async def test_pico_tutor_uses_official_fallback_for_version_sensitive_questions(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_fetch_official_evidence(url: str) -> OfficialEvidence:
        return OfficialEvidence(
            title="Hermes Releases",
            href=url,
            excerpt="Latest official release notes confirm the current install path and flags.",
        )

    monkeypatch.setattr(
        "src.api.services.pico_tutor.fetch_official_evidence",
        fake_fetch_official_evidence,
    )

    response = await client.post(
        "/v1/pico/tutor",
        json={
            "question": "What is the latest Hermes install command and current release path?",
            "lessonSlug": "install-hermes-locally",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["usedOfficialFallback"] is True
    assert any(source["kind"] == "official" for source in data["structured"]["sources"])
    assert any(link["href"].startswith("https://") for link in data["structured"]["officialLinks"])
