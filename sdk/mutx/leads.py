from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx

from mutx._http import api_path


class Lead:
    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.email = data["email"]
        self.name = data.get("name")
        self.company = data.get("company")
        self.message = data.get("message")
        self.source = data.get("source")
        self.created_at = datetime.fromisoformat(data["created_at"])
        self._data = data

    def __repr__(self) -> str:
        return f"Lead(id={self.id}, email={self.email}, name={self.name})"


class Leads:
    def __init__(self, client: httpx.Client | httpx.AsyncClient):
        self._client = client

    @staticmethod
    def _required_sync_client() -> None:
        raise RuntimeError(
            "This resource requires a sync httpx.Client. For async clients, use the a* methods"
        )

    @staticmethod
    def _required_async_client() -> None:
        raise RuntimeError(
            "This async resource helper requires an async httpx.AsyncClient and an a* method call"
        )

    def _require_sync_client(self) -> None:
        if isinstance(self._client, httpx.AsyncClient):
            self._required_sync_client()

    def _require_async_client(self) -> None:
        if not isinstance(self._client, httpx.AsyncClient):
            self._required_async_client()

    def create(
        self,
        email: str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        message: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Lead:
        self._require_sync_client()
        response = self._client.post(
            "leads",
            json={
                "email": email,
                "name": name,
                "company": company,
                "message": message,
                "source": source,
            },
        )
        response.raise_for_status()
        return Lead(response.json())

    async def acreate(
        self,
        email: str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        message: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Lead:
        self._require_async_client()
        response = await self._client.post(
            "leads",
            json={
                "email": email,
                "name": name,
                "company": company,
                "message": message,
                "source": source,
            },
        )
        response.raise_for_status()
        return Lead(response.json())

    def list(self, skip: int = 0, limit: int = 50) -> list[Lead]:
        self._require_sync_client()
        response = self._client.get("leads", params={"skip": skip, "limit": limit})
        response.raise_for_status()
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        return [Lead(item) for item in items]

    async def alist(self, skip: int = 0, limit: int = 50) -> list[Lead]:
        self._require_async_client()
        response = await self._client.get("leads", params={"skip": skip, "limit": limit})
        response.raise_for_status()
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        return [Lead(item) for item in items]

    def get(self, lead_id: UUID | str) -> Lead:
        self._require_sync_client()
        response = self._client.get(api_path("leads/{lead_id}", lead_id=lead_id))
        response.raise_for_status()
        return Lead(response.json())

    async def aget(self, lead_id: UUID | str) -> Lead:
        self._require_async_client()
        response = await self._client.get(api_path("leads/{lead_id}", lead_id=lead_id))
        response.raise_for_status()
        return Lead(response.json())

    def update(
        self,
        lead_id: UUID | str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        message: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Lead:
        self._require_sync_client()
        payload = {}
        if name is not None:
            payload["name"] = name
        if company is not None:
            payload["company"] = company
        if message is not None:
            payload["message"] = message
        if source is not None:
            payload["source"] = source

        response = self._client.patch(api_path("leads/{lead_id}", lead_id=lead_id), json=payload)
        response.raise_for_status()
        return Lead(response.json())

    async def aupdate(
        self,
        lead_id: UUID | str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        message: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Lead:
        self._require_async_client()
        payload = {}
        if name is not None:
            payload["name"] = name
        if company is not None:
            payload["company"] = company
        if message is not None:
            payload["message"] = message
        if source is not None:
            payload["source"] = source

        response = await self._client.patch(
            api_path("leads/{lead_id}", lead_id=lead_id), json=payload
        )
        response.raise_for_status()
        return Lead(response.json())

    def delete(self, lead_id: UUID | str) -> None:
        self._require_sync_client()
        response = self._client.delete(api_path("leads/{lead_id}", lead_id=lead_id))
        response.raise_for_status()

    async def adelete(self, lead_id: UUID | str) -> None:
        self._require_async_client()
        response = await self._client.delete(api_path("leads/{lead_id}", lead_id=lead_id))
        response.raise_for_status()


class Contacts(Leads):
    """Alias for Leads backed by the compatibility routes under /v1/leads/contacts."""

    def create(
        self,
        email: str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        message: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Lead:
        self._require_sync_client()
        response = self._client.post(
            "leads/contacts",
            json={
                "email": email,
                "name": name,
                "company": company,
                "message": message,
                "source": source,
            },
        )
        response.raise_for_status()
        return Lead(response.json())

    async def acreate(
        self,
        email: str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        message: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Lead:
        self._require_async_client()
        response = await self._client.post(
            "leads/contacts",
            json={
                "email": email,
                "name": name,
                "company": company,
                "message": message,
                "source": source,
            },
        )
        response.raise_for_status()
        return Lead(response.json())

    def list(self, skip: int = 0, limit: int = 50) -> list[Lead]:
        self._require_sync_client()
        response = self._client.get("leads/contacts", params={"skip": skip, "limit": limit})
        response.raise_for_status()
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        return [Lead(item) for item in items]

    async def alist(self, skip: int = 0, limit: int = 50) -> list[Lead]:
        self._require_async_client()
        response = await self._client.get("leads/contacts", params={"skip": skip, "limit": limit})
        response.raise_for_status()
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        return [Lead(item) for item in items]

    def get(self, contact_id: UUID | str) -> Lead:
        self._require_sync_client()
        response = self._client.get(api_path("leads/contacts/{contact_id}", contact_id=contact_id))
        response.raise_for_status()
        return Lead(response.json())

    async def aget(self, contact_id: UUID | str) -> Lead:
        self._require_async_client()
        response = await self._client.get(
            api_path("leads/contacts/{contact_id}", contact_id=contact_id)
        )
        response.raise_for_status()
        return Lead(response.json())

    def update(
        self,
        contact_id: UUID | str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        message: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Lead:
        self._require_sync_client()
        payload = {}
        if name is not None:
            payload["name"] = name
        if company is not None:
            payload["company"] = company
        if message is not None:
            payload["message"] = message
        if source is not None:
            payload["source"] = source

        response = self._client.patch(
            api_path("leads/contacts/{contact_id}", contact_id=contact_id), json=payload
        )
        response.raise_for_status()
        return Lead(response.json())

    async def aupdate(
        self,
        contact_id: UUID | str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        message: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Lead:
        self._require_async_client()
        payload = {}
        if name is not None:
            payload["name"] = name
        if company is not None:
            payload["company"] = company
        if message is not None:
            payload["message"] = message
        if source is not None:
            payload["source"] = source

        response = await self._client.patch(
            api_path("leads/contacts/{contact_id}", contact_id=contact_id), json=payload
        )
        response.raise_for_status()
        return Lead(response.json())

    def delete(self, contact_id: UUID | str) -> None:
        self._require_sync_client()
        response = self._client.delete(
            api_path("leads/contacts/{contact_id}", contact_id=contact_id)
        )
        response.raise_for_status()

    async def adelete(self, contact_id: UUID | str) -> None:
        self._require_async_client()
        response = await self._client.delete(
            api_path("leads/contacts/{contact_id}", contact_id=contact_id)
        )
        response.raise_for_status()
