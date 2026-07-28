"""Usage API SDK - /usage endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx

from mutx._http import api_path


class UsageEvent:
    """Represents a usage event."""

    def __init__(self, data: dict[str, Any]):
        self.id: UUID = UUID(data["id"])
        self.event_type: str = data["event_type"]
        self.resource_type: Optional[str] = data.get("resource_type")
        self.resource_id: Optional[str] = data.get("resource_id")
        self.credits_used: float = data.get("credits_used", 0.0)
        self.metadata: dict[str, Any] = data.get("metadata", {})
        self.created_at: datetime = datetime.fromisoformat(data["created_at"])
        self._data = data

    def __repr__(self) -> str:
        return f"UsageEvent(id={self.id}, type={self.event_type})"


class UsageEvents:
    """SDK resource for /usage endpoints."""

    def __init__(self, client: httpx.Client | httpx.AsyncClient):
        self._client = client

    def _require_sync_client(self) -> None:
        if isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError(
                "This resource requires a sync httpx.Client. For async clients, use the `a*` methods."
            )

    def _require_async_client(self) -> None:
        if not isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError(
                "This async resource helper requires an async httpx.AsyncClient and an `a*` method call."
            )

    def create_event(
        self,
        event_type: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        credits_used: float = 0.0,
    ) -> UsageEvent:
        """Record a usage event.

        Args:
            event_type: Type of usage event (e.g. api_call, starter_deployment_create)
            resource_type: Type of resource (e.g. agent, deployment)
            resource_id: UUID of the resource
            metadata: Additional event metadata
            credits_used: Credits consumed by this event
        """
        self._require_sync_client()
        payload: dict[str, Any] = {
            "event_type": event_type,
            "credits_used": credits_used,
        }
        if resource_type:
            payload["resource_type"] = resource_type
        if resource_id:
            payload["resource_id"] = str(resource_id)
        if metadata:
            payload["metadata"] = metadata

        response = self._client.post("usage/events", json=payload)
        response.raise_for_status()
        return UsageEvent(response.json())

    async def acreate_event(
        self,
        event_type: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        credits_used: float = 0.0,
    ) -> UsageEvent:
        """Record a usage event (async)."""
        self._require_async_client()
        payload: dict[str, Any] = {
            "event_type": event_type,
            "credits_used": credits_used,
        }
        if resource_type:
            payload["resource_type"] = resource_type
        if resource_id:
            payload["resource_id"] = str(resource_id)
        if metadata:
            payload["metadata"] = metadata

        response = await self._client.post("usage/events", json=payload)
        response.raise_for_status()
        return UsageEvent(response.json())

    def list(
        self,
        skip: int = 0,
        limit: int = 50,
        event_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> tuple[list[UsageEvent], int]:
        """List usage events for the authenticated user.

        Returns:
            Tuple of (list of events, total count)
        """
        self._require_sync_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if event_type:
            params["event_type"] = event_type
        if resource_id:
            params["resource_id"] = str(resource_id)

        response = self._client.get("usage/events", params=params)
        response.raise_for_status()
        data = response.json()
        return [UsageEvent(e) for e in data["items"]], data["total"]

    async def alist(
        self,
        skip: int = 0,
        limit: int = 50,
        event_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> tuple[list[UsageEvent], int]:
        """List usage events (async)."""
        self._require_async_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if event_type:
            params["event_type"] = event_type
        if resource_id:
            params["resource_id"] = str(resource_id)

        response = await self._client.get("usage/events", params=params)
        response.raise_for_status()
        data = response.json()
        return [UsageEvent(e) for e in data["items"]], data["total"]

    def get(
        self,
        event_id: str,
    ) -> UsageEvent:
        """Get a specific usage event."""
        self._require_sync_client()
        response = self._client.get(api_path("usage/events/{event_id}", event_id=event_id))
        response.raise_for_status()
        return UsageEvent(response.json())

    async def aget(
        self,
        event_id: str,
    ) -> UsageEvent:
        """Get a specific usage event (async)."""
        self._require_async_client()
        response = await self._client.get(api_path("usage/events/{event_id}", event_id=event_id))
        response.raise_for_status()
        return UsageEvent(response.json())
