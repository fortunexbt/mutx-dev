"""
Test file for /v1/pico routes.

The pico router IS mounted in main.py (RouterRegistration("pico", pico.router)).
This file tests the mounted endpoints for correctness.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock

from src.api.models.pico_onboarding import OnboardingState, PicoChatResponse
from src.api.models.pico_tutor import PicoTutorGenerationProof, PicoTutorResponse


@pytest_asyncio.fixture(autouse=True)
async def paid_plan_user(test_user, db_session):
    """Exercise launch-gated Pico endpoints with a paid test operator."""
    test_user.plan = "PRO"
    db_session.add(test_user)
    await db_session.commit()


@pytest.mark.asyncio
async def test_pico_progress_get(client: AsyncClient):
    """Test GET /v1/pico/progress returns current user's progress."""
    response = await client.get("/v1/pico/progress")
    assert response.status_code == 200
    data = response.json()
    assert "selectedTrack" in data
    assert "completedLessons" in data


@pytest.mark.asyncio
async def test_pico_progress_update(client: AsyncClient):
    """Test POST /v1/pico/progress updates user progress."""
    response = await client.post(
        "/v1/pico/progress",
        json={"selectedTrack": "free-agent", "completedLessons": ["lesson-1"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["selectedTrack"] == "free-agent"
    assert "lesson-1" in data["completedLessons"]


@pytest.mark.asyncio
async def test_pico_progress_update_minimal_payload(client: AsyncClient):
    """Test POST with minimal payload sets defaults correctly."""
    response = await client.post("/v1/pico/progress", json={"selectedTrack": "controlled-agent"})
    assert response.status_code == 200
    data = response.json()
    assert data["selectedTrack"] == "controlled-agent"
    assert isinstance(data["completedLessons"], list)
    assert isinstance(data["autopilot"], dict)


@pytest.mark.asyncio
async def test_pico_tutor_post(client: AsyncClient, monkeypatch):
    """Test POST /v1/pico/tutor returns tutor reply."""
    monkeypatch.setenv("OPENAI_API_KEY", "platform-openai-key")

    async def generated_reply(*, fallback_reply, entitlement, **_kwargs):
        return PicoTutorResponse(
            **fallback_reply.model_dump(),
            entitlement=entitlement,
            generation=PicoTutorGenerationProof(
                source="platform",
                model="gpt-5-mini",
                responseId="chatcmpl-route-proof",
                completedAt="2026-07-28T12:00:00Z",
            ),
        )

    monkeypatch.setattr("src.api.services.pico_tutor._generate_with_model", generated_reply)
    response = await client.post(
        "/v1/pico/tutor",
        json={"message": "How do I start my first agent?", "lesson": "install-hermes-locally"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "nextLesson" in data
    assert data["generation"]["responseId"] == "chatcmpl-route-proof"


@pytest.mark.asyncio
async def test_pico_tutor_openai_get(client: AsyncClient):
    """Test GET /v1/pico/tutor/openai returns connection status."""
    response = await client.get("/v1/pico/tutor/openai")
    assert response.status_code == 200
    data = response.json()
    assert "connected" in data
    assert "apiKeySet" in data


@pytest.mark.asyncio
async def test_pico_chat_rejects_unknown_client_session(client: AsyncClient):
    """Unknown session IDs are never adopted as server-side session truth."""
    response = await client.post(
        "/v1/pico/chat",
        json={
            "message": "I'm having trouble setting up Hermes.",
            "session_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


@pytest.mark.asyncio
async def test_pico_chat_creates_session_if_missing(client: AsyncClient, monkeypatch):
    """Test POST /v1/pico/chat creates session when not provided."""
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(
            return_value=PicoChatResponse(
                reply="Let's choose the remaining setup details.",
                onboarding_state=OnboardingState(stack="hermes"),
            )
        ),
    )
    response = await client.post(
        "/v1/pico/chat",
        json={"message": "I need help with installation.", "request_id": "request-1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["session_id"]) == 36
    assert data["session_persisted"] is True
    assert data["onboarding_state"]["stack"] == "hermes"


@pytest.mark.asyncio
async def test_pico_generate_package_invalid_session(client: AsyncClient):
    """Test POST /v1/pico/generate-package returns 404 for invalid session_id."""
    response = await client.post(
        "/v1/pico/generate-package",
        json={"session_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
    )
    assert response.status_code == 404
    data = response.json()
    assert "Session not found" in data["detail"]


@pytest.mark.asyncio
async def test_pico_generate_package_not_ready(client: AsyncClient, monkeypatch):
    """Test POST /v1/pico/generate-package returns 422 when session state not ready."""
    # Create a session but don't complete it
    monkeypatch.setattr(
        "src.api.routes.pico.handle_coach_chat",
        AsyncMock(
            return_value=PicoChatResponse(
                reply="I still need your operating system and provider.",
                onboarding_state=OnboardingState(stack="hermes"),
            )
        ),
    )
    response = await client.post(
        "/v1/pico/chat",
        json={"message": "Just testing"},
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    # Try to generate package from incomplete session
    response = await client.post(
        "/v1/pico/generate-package",
        json={"session_id": session_id},
    )
    assert response.status_code == 422
    data = response.json()
    assert "Not enough information to generate a package" in data["detail"]


@pytest.mark.asyncio
async def test_pico_tutor_openai_connect(client: AsyncClient):
    """Test PUT /v1/pico/tutor/openai connects OpenAI."""
    response = await client.put(
        "/v1/pico/tutor/openai",
        json={"apiKey": "sk-test-key-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["apiKeySet"] is True


@pytest.mark.asyncio
async def test_pico_tutor_openai_disconnect(client: AsyncClient):
    """Test DELETE /v1/pico/tutor/openai disconnects OpenAI."""
    # First connect
    await client.put(
        "/v1/pico/tutor/openai",
        json={"apiKey": "sk-test-key-123"},
    )

    # Then disconnect
    response = await client.delete("/v1/pico/tutor/openai")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False


@pytest.mark.asyncio
async def test_pico_generate_package_legacy(client: AsyncClient):
    """Test POST /v1/pico/generate-package-legacy generates legacy package."""
    response = await client.post(
        "/v1/pico/generate-package-legacy",
        json={
            "agent_name": "Test Agent",
            "pain_points": ["slow execution", "complex setup"],
            "model": "gpt-4",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
