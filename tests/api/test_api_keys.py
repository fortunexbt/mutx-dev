"""
Tests for /api-keys endpoints.
"""

import hashlib
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.jwt import create_access_token
from src.api.models.models import APIKey
from src.api.models import get_quota, PlanTier
from src.api.services.user_service import extract_api_key_prefix, verify_api_key


@pytest_asyncio.fixture(autouse=True)
async def developer_principals(db_session, test_user, other_user):
    test_user.roles = ["DEVELOPER"]
    other_user.roles = ["DEVELOPER"]
    await db_session.commit()


class TestListAPIKeys:
    """Tests for GET /api-keys endpoint."""

    @pytest.mark.asyncio
    async def test_list_api_keys_empty(self, client: AsyncClient):
        """Test listing API keys when none exist."""
        response = await client.get("/v1/api-keys")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["skip"] == 0
        assert data["limit"] == 50

    @pytest.mark.asyncio
    async def test_list_api_keys_with_data(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test listing API keys returns only the current user's keys in reverse chronological order."""
        older_key = APIKey(
            id=uuid.uuid4(),
            user_id=test_user.id,
            key_hash="older_hash",
            name="older-key",
            is_active=True,
        )
        db_session.add(older_key)
        await db_session.commit()

        newer_key = APIKey(
            id=uuid.uuid4(),
            user_id=test_user.id,
            key_hash="newer_hash",
            name="newer-key",
            is_active=False,
        )
        db_session.add(newer_key)
        await db_session.commit()

        response = await client.get("/v1/api-keys")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert [item["name"] for item in data["items"]] == ["newer-key", "older-key"]
        assert data["items"][0]["is_active"] is False
        assert data["items"][1]["is_active"] is True


class TestCreateAPIKey:
    """Tests for POST /api-keys endpoint."""

    @pytest.mark.asyncio
    async def test_create_api_key_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test creating an API key successfully."""
        response = await client.post(
            "/v1/api-keys",
            json={
                "name": "new-key",
                "expires_in_days": 30,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new-key"
        assert "key" in data
        assert data["key"].startswith("mutx_live_")

        result = await db_session.execute(select(APIKey).where(APIKey.user_id == test_user.id))
        stored_key = result.scalar_one()
        assert stored_key.name == "new-key"
        assert stored_key.key_prefix == extract_api_key_prefix(data["key"])
        assert verify_api_key(data["key"], stored_key.key_hash)
        assert stored_key.is_active is True
        assert stored_key.expires_at is not None

    @pytest.mark.asyncio
    async def test_create_api_key_minimal(self, client: AsyncClient):
        """Test creating an API key with minimal data."""
        response = await client.post(
            "/v1/api-keys",
            json={"name": "minimal-key"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "minimal-key"

    @pytest.mark.asyncio
    async def test_create_api_key_enforces_active_limit(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test that creating an API key fails once the active key limit is reached."""
        # Set user to PRO plan (50 keys) for this test
        test_user.plan = PlanTier.PRO
        db_session.add(test_user)
        await db_session.commit()

        quota = get_quota(test_user.plan)
        for index in range(quota.max_api_keys):
            db_session.add(
                APIKey(
                    id=uuid.uuid4(),
                    user_id=test_user.id,
                    key_hash=f"hash-{index}",
                    name=f"key-{index}",
                    is_active=True,
                )
            )
        await db_session.commit()

        response = await client.post("/v1/api-keys", json={"name": "overflow-key"})
        assert response.status_code == 409
        assert "Active API key limit reached" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_api_key_ignores_revoked_keys_for_limit(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test that revoked keys do not count against the active key limit."""
        # Set user to PRO plan (50 keys) for this test
        test_user.plan = PlanTier.PRO
        db_session.add(test_user)
        await db_session.commit()

        quota = get_quota(test_user.plan)
        for index in range(quota.max_api_keys):
            db_session.add(
                APIKey(
                    id=uuid.uuid4(),
                    user_id=test_user.id,
                    key_hash=f"hash-{index}",
                    name=f"key-{index}",
                    is_active=index != 0,
                )
            )
        await db_session.commit()

        response = await client.post("/v1/api-keys", json={"name": "replacement-key"})
        assert response.status_code == 201
        assert response.json()["name"] == "replacement-key"


class TestGetAPIKey:
    """Tests for GET /api-keys/{key_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_api_key_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test getting an API key by ID returns the key details."""
        key = APIKey(
            id=uuid.uuid4(),
            user_id=test_user.id,
            key_hash="test_hash",
            name="my-key",
            is_active=True,
        )
        db_session.add(key)
        await db_session.commit()

        response = await client.get(f"/v1/api-keys/{key.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(key.id)
        assert data["name"] == "my-key"
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_get_api_key_returns_revoked_key(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test getting a revoked API key still returns its details."""
        key = APIKey(
            id=uuid.uuid4(),
            user_id=test_user.id,
            key_hash="revoked_hash",
            name="revoked-key",
            is_active=False,
        )
        db_session.add(key)
        await db_session.commit()

        response = await client.get(f"/v1/api-keys/{key.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(key.id)
        assert data["name"] == "revoked-key"
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_get_api_key_not_found(self, client: AsyncClient):
        """Test getting non-existent API key returns 404."""
        response = await client.get(f"/v1/api-keys/{uuid.uuid4()}")
        assert response.status_code == 404
        assert response.json()["detail"] == "API key not found"

    @pytest.mark.asyncio
    async def test_get_other_user_api_key_not_found(
        self, client: AsyncClient, db_session: AsyncSession, other_user
    ):
        """Test getting another user's API key does not leak its existence."""
        key = APIKey(
            id=uuid.uuid4(),
            user_id=other_user.id,
            key_hash="other_hash",
            name="other-key",
            is_active=True,
        )
        db_session.add(key)
        await db_session.commit()

        response = await client.get(f"/v1/api-keys/{key.id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "API key not found"


class TestRevokeAPIKey:
    """Tests for DELETE /api-keys/{key_id} endpoint."""

    @pytest.mark.asyncio
    async def test_revoke_api_key_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test revoking an API key marks it inactive instead of deleting it."""
        key = APIKey(
            id=uuid.uuid4(),
            user_id=test_user.id,
            key_hash="hashed_key",
            name="to-revoke",
            is_active=True,
        )
        db_session.add(key)
        await db_session.commit()

        response = await client.delete(f"/v1/api-keys/{key.id}")
        assert response.status_code == 204

        result = await db_session.get(APIKey, key.id)
        assert result is not None
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_revoke_api_key_is_idempotent(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test revoking an already revoked API key stays a no-op."""
        key = APIKey(
            id=uuid.uuid4(),
            user_id=test_user.id,
            key_hash="hashed_key",
            name="already-revoked",
            is_active=False,
        )
        db_session.add(key)
        await db_session.commit()

        response = await client.delete(f"/v1/api-keys/{key.id}")
        assert response.status_code == 204

        result = await db_session.get(APIKey, key.id)
        assert result is not None
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_revoke_api_key_not_found(self, client: AsyncClient):
        """Test revoking non-existent API key returns 404."""
        response = await client.delete(f"/v1/api-keys/{uuid.uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_other_user_forbidden(
        self, client: AsyncClient, db_session: AsyncSession, other_user
    ):
        """Test that users cannot revoke other users' API keys."""
        key = APIKey(
            id=uuid.uuid4(),
            user_id=other_user.id,
            key_hash="other_hash",
            name="other-key",
            is_active=True,
        )
        db_session.add(key)
        await db_session.commit()

        response = await client.delete(f"/v1/api-keys/{key.id}")
        assert response.status_code == 404


class TestRotateAPIKey:
    """Tests for POST /api-keys/{key_id}/rotate endpoint."""

    @pytest.mark.asyncio
    async def test_rotate_api_key_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test rotating an API key revokes the old record and creates a new one."""
        key = APIKey(
            id=uuid.uuid4(),
            user_id=test_user.id,
            key_hash="old_hash",
            name="to-rotate",
            is_active=True,
        )
        db_session.add(key)
        await db_session.commit()

        response = await client.post(f"/v1/api-keys/{key.id}/rotate")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "to-rotate"
        assert "key" in data
        assert data["key"].startswith("mutx_live_")
        assert data["id"] != str(key.id)

        old_record = await db_session.get(APIKey, key.id)
        assert old_record is not None
        assert old_record.is_active is False

        result = await db_session.execute(select(APIKey).where(APIKey.user_id == test_user.id))
        keys = result.scalars().all()
        assert len(keys) == 2
        active_keys = [item for item in keys if item.is_active]
        assert len(active_keys) == 1
        assert active_keys[0].name == "to-rotate"
        assert active_keys[0].key_prefix == extract_api_key_prefix(data["key"])
        assert verify_api_key(data["key"], active_keys[0].key_hash)

    @pytest.mark.asyncio
    async def test_rotate_revoked_api_key_conflicts(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test rotating a revoked API key returns a conflict."""
        key = APIKey(
            id=uuid.uuid4(),
            user_id=test_user.id,
            key_hash="old_hash",
            name="revoked-key",
            is_active=False,
        )
        db_session.add(key)
        await db_session.commit()

        response = await client.post(f"/v1/api-keys/{key.id}/rotate")
        assert response.status_code == 409
        assert "already revoked" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_rotate_other_user_api_key_not_found(
        self, client: AsyncClient, db_session: AsyncSession, other_user
    ):
        """Test rotating another user's API key does not leak its existence."""
        key = APIKey(
            id=uuid.uuid4(),
            user_id=other_user.id,
            key_hash="other_hash",
            name="other-users-key",
            is_active=True,
        )
        db_session.add(key)
        await db_session.commit()

        response = await client.post(f"/v1/api-keys/{key.id}/rotate")
        assert response.status_code == 404
        assert response.json()["detail"] == "API key not found"


class TestVerifyAPIKeyCompatibility:
    """Compatibility tests for legacy API key hashes."""

    def test_verify_api_key_accepts_legacy_sha256_hash(self):
        plain_key = "mutx_live_legacy_example"
        legacy_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        assert verify_api_key(plain_key, legacy_hash)


class TestBearerAPIKeyAuth:
    """Authentication compatibility tests for Bearer API key automation flows."""

    @pytest.mark.asyncio
    async def test_list_api_keys_with_bearer_managed_api_key(
        self, client_no_auth: AsyncClient, test_user
    ):
        access_token, _ = create_access_token(test_user.id)

        create_response = await client_no_auth.post(
            "/v1/api-keys",
            json={"name": "automation-key"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert create_response.status_code == 201
        created_key = create_response.json()

        list_response = await client_no_auth.get(
            "/v1/api-keys",
            headers={"Authorization": f"Bearer {created_key['key']}"},
        )
        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == created_key["id"]

    @pytest.mark.asyncio
    async def test_list_api_keys_with_invalid_bearer_api_key_is_unauthorized(
        self, client_no_auth: AsyncClient
    ):
        response = await client_no_auth.get(
            "/v1/api-keys",
            headers={"Authorization": "Bearer mutx_live_invalid"},
        )

        assert response.status_code == 401
