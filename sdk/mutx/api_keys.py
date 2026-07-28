from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx

from mutx._http import api_path
from mutx.pagination import Page, parse_page


class APIKey:
    """Represents an API key (without the raw secret)."""

    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.name = data["name"]
        self.is_active = data.get("is_active", True)
        self.last_used = (
            datetime.fromisoformat(data["last_used"]) if data.get("last_used") else None
        )
        self.created_at = datetime.fromisoformat(data["created_at"])
        self.expires_at = (
            datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
        )
        self._data = data

    def __repr__(self) -> str:
        return f"APIKey(id={self.id}, name={self.name}, active={self.is_active})"


class APIKeyWithSecret(APIKey):
    """Returned on create/rotate — includes the plain key (shown once)."""

    def __init__(self, data: dict[str, Any]):
        super().__init__(data)
        self.key: str = data["key"]

    def __repr__(self) -> str:
        prefix = self.key[:16] + "…" if len(self.key) > 16 else self.key
        return f"APIKeyWithSecret(id={self.id}, name={self.name}, key={prefix})"


class APIKeys:
    """SDK resource for /api-keys endpoints."""

    def __init__(self, client: httpx.Client | httpx.AsyncClient):
        self._client = client

    @staticmethod
    def _required_sync_client() -> None:
        raise RuntimeError(
            "This resource requires a sync httpx.Client. For async clients, use the `a*` methods"
        )

    @staticmethod
    def _required_async_client() -> None:
        raise RuntimeError(
            "This async resource helper requires an async httpx.AsyncClient and an `a*` method call"
        )

    def _require_sync_client(self) -> None:
        if isinstance(self._client, httpx.AsyncClient):
            self._required_sync_client()

    def _require_async_client(self) -> None:
        if not isinstance(self._client, httpx.AsyncClient):
            self._required_async_client()

    def list(self, skip: int = 0, limit: int = 50) -> Page[APIKey]:
        """List all API keys for the authenticated user."""
        self._require_sync_client()
        response = self._client.get("api-keys", params={"skip": skip, "limit": limit})
        response.raise_for_status()
        return parse_page(
            response.json(),
            APIKey,
            requested_skip=skip,
            requested_limit=limit,
            require_has_more=True,
        )

    async def alist(self, skip: int = 0, limit: int = 50) -> Page[APIKey]:
        """List all API keys for the authenticated user (async)."""
        self._require_async_client()
        response = await self._client.get("api-keys", params={"skip": skip, "limit": limit})
        response.raise_for_status()
        return parse_page(
            response.json(),
            APIKey,
            requested_skip=skip,
            requested_limit=limit,
            require_has_more=True,
        )

    def create(
        self,
        name: str,
        expires_in_days: Optional[int] = None,
    ) -> APIKeyWithSecret:
        """Create a new API key.  The plain key is only returned once."""
        payload: dict[str, Any] = {"name": name}
        if expires_in_days is not None:
            payload["expires_in_days"] = expires_in_days

        self._require_sync_client()
        response = self._client.post("api-keys", json=payload)
        response.raise_for_status()
        return APIKeyWithSecret(response.json())

    async def acreate(
        self,
        name: str,
        expires_in_days: Optional[int] = None,
    ) -> APIKeyWithSecret:
        """Create a new API key (async)."""
        payload: dict[str, Any] = {"name": name}
        if expires_in_days is not None:
            payload["expires_in_days"] = expires_in_days

        self._require_async_client()
        response = await self._client.post("api-keys", json=payload)
        response.raise_for_status()
        return APIKeyWithSecret(response.json())

    def revoke(self, key_id: UUID | str) -> None:
        """Revoke (delete) an API key."""
        self._require_sync_client()
        response = self._client.delete(api_path("api-keys/{key_id}", key_id=key_id))
        response.raise_for_status()

    async def arevoke(self, key_id: UUID | str) -> None:
        """Revoke (delete) an API key (async)."""
        self._require_async_client()
        response = await self._client.delete(api_path("api-keys/{key_id}", key_id=key_id))
        response.raise_for_status()

    def rotate(self, key_id: UUID | str) -> APIKeyWithSecret:
        """Rotate an API key — revokes the old one and returns a new one."""
        self._require_sync_client()
        response = self._client.post(api_path("api-keys/{key_id}/rotate", key_id=key_id))
        response.raise_for_status()
        return APIKeyWithSecret(response.json())

    async def arotate(self, key_id: UUID | str) -> APIKeyWithSecret:
        """Rotate an API key (async)."""
        self._require_async_client()
        response = await self._client.post(api_path("api-keys/{key_id}/rotate", key_id=key_id))
        response.raise_for_status()
        return APIKeyWithSecret(response.json())
