import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.database import Base
from src.api.models.models import Lead
from src.api.models.schemas import LeadCreate
from src.api.routes import leads as leads_routes


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, db_session: AsyncSession, test_user):
    test_user.roles = ["ADMIN"]
    await db_session.commit()
    return client


@pytest.fixture(autouse=True)
def scheduled_lead_notifications(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    scheduled: list[dict[str, object]] = []

    def capture_schedule(lead: Lead) -> None:
        scheduled.append(
            {
                "id": lead.id,
                "email": lead.email,
                "consent": lead.product_updates_consent,
            }
        )

    monkeypatch.setattr(leads_routes, "_schedule_notification", capture_schedule)
    return scheduled


@pytest.mark.asyncio
async def test_capture_lead_success(client: AsyncClient, db_session: AsyncSession):
    """Test capturing a lead successfully."""
    response = await client.post(
        "/v1/leads",
        json={
            "email": "lead@example.com",
            "name": "Lead Name",
            "company": "Lead Co",
            "message": "Hello, I am interested.",
            "source": "onboarding",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "lead@example.com"
    assert data["name"] == "Lead Name"
    assert data["company"] == "Lead Co"
    assert data["message"] == "Hello, I am interested."
    assert data["source"] == "onboarding"
    assert data["persisted"] is True
    assert data["notification_scheduled"] is True
    assert "best-effort" in data["message_to_submitter"]
    assert "id" in data

    persisted = await db_session.get(Lead, uuid.UUID(data["id"]))
    assert persisted is not None
    assert persisted.notification_scheduled_at is not None


@pytest.mark.asyncio
async def test_capture_lead_minimal(client: AsyncClient):
    """Test capturing a lead with minimal data."""
    response = await client.post(
        "/v1/leads",
        json={
            "email": "minimal@example.com",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "minimal@example.com"
    assert data["source"] == "direct"  # Default value


@pytest.mark.asyncio
async def test_capture_lead_replays_a_lost_response_once(
    client: AsyncClient,
    db_session: AsyncSession,
    scheduled_lead_notifications: list[dict[str, object]],
):
    headers = {"Idempotency-Key": "12345678-1234-4123-8123-123456789abc"}
    payload = {
        "email": " Replay@Example.com ",
        "name": " Replay Lead ",
        "message": " Same request ",
        "source": " pico-landing ",
        "tier": " build ",
        "interest": " build ",
        "locale": "EN-us",
        "product_updates_consent": False,
    }

    first = await client.post("/v1/leads", headers=headers, json=payload)
    second = await client.post("/v1/leads", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert len(scheduled_lead_notifications) == 1
    count = await db_session.scalar(select(func.count()).select_from(Lead))
    assert count == 1


@pytest.mark.asyncio
async def test_capture_lead_rejects_key_reuse_with_different_content(
    client: AsyncClient,
    scheduled_lead_notifications: list[dict[str, object]],
):
    headers = {"Idempotency-Key": "conflict-12345678-1234-4123-8123-123456789abc"}
    first = await client.post(
        "/v1/leads",
        headers=headers,
        json={"email": "conflict@example.com", "message": "First"},
    )
    second = await client.post(
        "/v1/leads",
        headers=headers,
        json={"email": "conflict@example.com", "message": "Different"},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert "different lead content" in second.json()["detail"]
    assert len(scheduled_lead_notifications) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("consent", [False, True])
async def test_capture_lead_persists_only_explicit_product_update_consent(
    client: AsyncClient,
    db_session: AsyncSession,
    scheduled_lead_notifications: list[dict[str, object]],
    consent: bool,
):
    response = await client.post(
        "/v1/leads",
        headers={"Idempotency-Key": f"consent-{str(consent).lower()}-1234567890"},
        json={
            "email": f"consent-{str(consent).lower()}@example.com",
            "product_updates_consent": consent,
        },
    )

    assert response.status_code == 201
    persisted = await db_session.get(Lead, uuid.UUID(response.json()["id"]))
    assert persisted is not None
    assert persisted.product_updates_consent is consent
    assert scheduled_lead_notifications == [
        {"id": persisted.id, "email": persisted.email, "consent": consent}
    ]


@pytest.mark.asyncio
async def test_concurrent_duplicate_capture_creates_and_schedules_once(
    tmp_path,
    scheduled_lead_notifications: list[dict[str, object]],
):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'concurrent-leads.db'}",
        connect_args={"timeout": 10},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    key = "concurrent-12345678-1234-4123-8123-123456789abc"
    payload = LeadCreate(
        email="concurrent@example.com",
        message="Create this once",
        source="pico-landing",
    )

    async def submit():
        async with session_factory() as session:
            return await leads_routes.capture_lead(payload, key, session)

    try:
        first, second = await asyncio.gather(submit(), submit())
        async with session_factory() as session:
            count = await session.scalar(select(func.count()).select_from(Lead))
    finally:
        await engine.dispose()

    assert first.id == second.id
    assert {first.replayed, second.replayed} == {False, True}
    assert count == 1
    assert len(scheduled_lead_notifications) == 1


@pytest.mark.asyncio
async def test_capture_lead_rejects_malformed_idempotency_key(client: AsyncClient):
    response = await client.post(
        "/v1/leads",
        headers={"Idempotency-Key": "short"},
        json={"email": "invalid-key@example.com"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_capture_contact_alias_success(client: AsyncClient):
    """Test /contacts alias captures leads."""
    response = await client.post(
        "/v1/leads/contacts",
        json={
            "email": "contact@example.com",
            "name": "Contact Name",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "contact@example.com"
    assert data["name"] == "Contact Name"


@pytest.mark.asyncio
async def test_list_leads_admin_user(admin_client: AsyncClient):
    """Test listing leads for a persisted administrator."""
    response = await admin_client.get("/v1/leads")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "has_more" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_list_contacts_alias_admin_user(admin_client: AsyncClient):
    """Test /contacts alias for listing."""
    response = await admin_client.get("/v1/leads/contacts")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_list_leads_non_internal_forbidden(other_user_client: AsyncClient):
    """Test listing leads is forbidden for non-internal users."""
    response = await other_user_client.get("/v1/leads")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_leads_internal_viewer_forbidden(client: AsyncClient):
    """An internal email address does not replace persisted administrative authority."""
    response = await client.get("/v1/leads")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_leads_unauthorized(client_no_auth: AsyncClient):
    """Test listing leads without auth fails."""
    response = await client_no_auth.get("/v1/leads")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_leads_internal_unverified_forbidden(client_no_auth: AsyncClient):
    """Test listing leads is forbidden for internal-domain users without verified email."""
    import uuid

    from src.api.middleware.auth import get_current_user
    from src.api.models.models import User

    async def override_get_current_user():
        return User(
            id=uuid.uuid4(),
            email="attacker@mutx.dev",
            password_hash="hashedpassword",
            is_active=True,
            is_email_verified=False,
            name="Attacker",
        )

    client_no_auth.app.dependency_overrides[get_current_user] = override_get_current_user
    response = await client_no_auth.get("/v1/leads")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_lead_admin_user(admin_client: AsyncClient, db_session: AsyncSession):
    """Test fetching a single lead as an administrator."""
    lead = Lead(
        email="reader@example.com",
        name="Reader",
        company="Read Co",
        message="Tell me more.",
        source="docs",
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    response = await admin_client.get(f"/v1/leads/{lead.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(lead.id)
    assert data["email"] == "reader@example.com"


@pytest.mark.asyncio
async def test_get_lead_non_internal_forbidden(
    other_user_client: AsyncClient, db_session: AsyncSession
):
    """Test fetching a lead is forbidden for non-internal users."""
    lead = Lead(email="private@example.com", source="homepage")
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    response = await other_user_client.get(f"/v1/leads/{lead.id}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_lead_unauthorized(client_no_auth: AsyncClient, db_session: AsyncSession):
    """Test fetching a single lead without auth fails."""
    lead = Lead(email="private@example.com", source="homepage")
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    response = await client_no_auth.get(f"/v1/leads/{lead.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_lead_not_found(admin_client: AsyncClient):
    """Test fetching an unknown lead returns 404."""
    response = await admin_client.get("/v1/leads/00000000-0000-0000-0000-999999999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_lead_admin_user(admin_client: AsyncClient, db_session: AsyncSession):
    lead = Lead(
        email="update-me@example.com",
        name="Old Name",
        company="Old Co",
        source="docs",
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    response = await admin_client.patch(
        f"/v1/leads/{lead.id}",
        json={
            "name": "New Name",
            "company": "New Co",
            "message": "Interested in enterprise.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["company"] == "New Co"
    assert data["message"] == "Interested in enterprise."


@pytest.mark.asyncio
async def test_update_contact_alias_admin_user(
    admin_client: AsyncClient,
    db_session: AsyncSession,
):
    lead = Lead(
        email="alias-update@example.com",
        name="Alias",
        source="docs",
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    response = await admin_client.patch(
        f"/v1/leads/contacts/{lead.id}",
        json={"source": "partner-referral"},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "partner-referral"


@pytest.mark.asyncio
async def test_update_lead_requires_payload(
    admin_client: AsyncClient,
    db_session: AsyncSession,
):
    lead = Lead(email="empty-update@example.com", source="docs")
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    response = await admin_client.patch(f"/v1/leads/{lead.id}", json={})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delete_lead_admin_user(admin_client: AsyncClient, db_session: AsyncSession):
    lead = Lead(email="delete-me@example.com", source="docs")
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    delete_response = await admin_client.delete(f"/v1/leads/{lead.id}")
    assert delete_response.status_code == 204

    get_response = await admin_client.get(f"/v1/leads/{lead.id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_contact_alias_non_internal_forbidden(
    other_user_client: AsyncClient, db_session: AsyncSession
):
    lead = Lead(email="forbidden-delete@example.com", source="docs")
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    response = await other_user_client.delete(f"/v1/leads/contacts/{lead.id}")
    assert response.status_code == 403
