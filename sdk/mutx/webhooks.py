from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx

from mutx._http import api_path


class Webhook:
    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.url = data["url"]
        self.events = data.get("events", [])
        self.secret = data.get("secret")
        self.has_secret = data.get("has_secret", bool(self.secret))
        # Contract parity: backend uses `is_active`; keep `.active` as compatibility alias.
        self.is_active = data.get("is_active", data.get("active", True))
        self.active = self.is_active
        self.created_at = datetime.fromisoformat(data["created_at"])
        self._data = data

    def __repr__(self) -> str:
        return f"Webhook(id={self.id}, url={self.url}, is_active={self.is_active})"


class WebhookDelivery:
    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.webhook_id = UUID(data["webhook_id"])
        self.event = data["event"]
        self.payload = data["payload"]
        self.status_code = data.get("status_code")
        self.success = data["success"]
        self.error_message = data.get("error_message")
        self.attempts = data["attempts"]
        self.created_at = datetime.fromisoformat(data["created_at"])
        delivered_at = data.get("delivered_at")
        self.delivered_at = datetime.fromisoformat(delivered_at) if delivered_at else None
        self._data = data

    def __repr__(self) -> str:
        return f"WebhookDelivery(id={self.id}, event={self.event}, success={self.success})"


class Webhooks:
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

    def create(
        self,
        url: str,
        events: list[str],
        secret: Optional[str] = None,
        is_active: bool = True,
    ) -> Webhook:
        self._require_sync_client()
        response = self._client.post(
            "webhooks/",
            json={
                "url": url,
                "events": events,
                "secret": secret,
                "is_active": is_active,
            },
        )
        response.raise_for_status()
        return Webhook(response.json())

    async def acreate(
        self,
        url: str,
        events: list[str],
        secret: Optional[str] = None,
        is_active: bool = True,
    ) -> Webhook:
        self._require_async_client()
        response = await self._client.post(
            "webhooks/",
            json={
                "url": url,
                "events": events,
                "secret": secret,
                "is_active": is_active,
            },
        )
        response.raise_for_status()
        return Webhook(response.json())

    def list(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Webhook]:
        self._require_sync_client()
        response = self._client.get(
            "webhooks/",
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        body = response.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        return [Webhook(data) for data in items]

    async def alist(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Webhook]:
        self._require_async_client()
        response = await self._client.get(
            "webhooks/",
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        body = response.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        return [Webhook(data) for data in items]

    def get(self, webhook_id: UUID | str) -> Webhook:
        self._require_sync_client()
        response = self._client.get(api_path("webhooks/{webhook_id}", webhook_id=webhook_id))
        response.raise_for_status()
        return Webhook(response.json())

    async def aget(self, webhook_id: UUID | str) -> Webhook:
        self._require_async_client()
        response = await self._client.get(api_path("webhooks/{webhook_id}", webhook_id=webhook_id))
        response.raise_for_status()
        return Webhook(response.json())

    def delete(self, webhook_id: UUID | str) -> None:
        self._require_sync_client()
        response = self._client.delete(api_path("webhooks/{webhook_id}", webhook_id=webhook_id))
        response.raise_for_status()

    async def adelete(self, webhook_id: UUID | str) -> None:
        self._require_async_client()
        response = await self._client.delete(
            api_path("webhooks/{webhook_id}", webhook_id=webhook_id)
        )
        response.raise_for_status()

    def get_deliveries(
        self,
        webhook_id: UUID | str,
        skip: int = 0,
        limit: int = 50,
        event: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> list[WebhookDelivery]:
        self._require_sync_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if event is not None:
            params["event"] = event
        if success is not None:
            params["success"] = success

        response = self._client.get(
            api_path("webhooks/{webhook_id}/deliveries", webhook_id=webhook_id),
            params=params,
        )
        response.raise_for_status()
        body = response.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        return [WebhookDelivery(data) for data in items]

    async def aget_deliveries(
        self,
        webhook_id: UUID | str,
        skip: int = 0,
        limit: int = 50,
        event: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> list[WebhookDelivery]:
        self._require_async_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if event is not None:
            params["event"] = event
        if success is not None:
            params["success"] = success

        response = await self._client.get(
            api_path("webhooks/{webhook_id}/deliveries", webhook_id=webhook_id),
            params=params,
        )
        response.raise_for_status()
        body = response.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        return [WebhookDelivery(data) for data in items]

    def update(
        self,
        webhook_id: UUID | str,
        url: Optional[str] = None,
        events: Optional[list[str]] = None,
        is_active: Optional[bool] = None,
        active: Optional[bool] = None,
    ) -> Webhook:
        self._require_sync_client()
        payload = {}
        if url is not None:
            payload["url"] = url
        if events is not None:
            payload["events"] = events
        # Preserve backward compatibility for callers using `active=`.
        if is_active is None and active is not None:
            is_active = active
        if is_active is not None:
            payload["is_active"] = is_active

        response = self._client.patch(
            api_path("webhooks/{webhook_id}", webhook_id=webhook_id), json=payload
        )
        response.raise_for_status()
        return Webhook(response.json())

    async def aupdate(
        self,
        webhook_id: UUID | str,
        url: Optional[str] = None,
        events: Optional[list[str]] = None,
        is_active: Optional[bool] = None,
        active: Optional[bool] = None,
    ) -> Webhook:
        self._require_async_client()
        payload = {}
        if url is not None:
            payload["url"] = url
        if events is not None:
            payload["events"] = events
        # Preserve backward compatibility for callers using `active=`.
        if is_active is None and active is not None:
            is_active = active
        if is_active is not None:
            payload["is_active"] = is_active

        response = await self._client.patch(
            api_path("webhooks/{webhook_id}", webhook_id=webhook_id), json=payload
        )
        response.raise_for_status()
        return Webhook(response.json())

    def test(self, webhook_id: UUID | str) -> dict[str, Any]:
        self._require_sync_client()
        response = self._client.post(api_path("webhooks/{webhook_id}/test", webhook_id=webhook_id))
        response.raise_for_status()
        return response.json()

    async def atest(self, webhook_id: UUID | str) -> dict[str, Any]:
        self._require_async_client()
        response = await self._client.post(
            api_path("webhooks/{webhook_id}/test", webhook_id=webhook_id)
        )
        response.raise_for_status()
        return response.json()
