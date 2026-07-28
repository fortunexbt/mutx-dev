from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx

from mutx._http import api_path


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    # FastAPI serializers may emit UTC timestamps with a trailing "Z".
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    return datetime.fromisoformat(value)


class DeploymentEvent:
    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.deployment_id = UUID(data["deployment_id"])
        self.event_type = data["event_type"]
        self.status = data["status"]
        self.node_id = data.get("node_id")
        self.error_message = data.get("error_message")
        self.created_at = _parse_datetime(data["created_at"])
        self._data = data


class DeploymentEventHistory:
    def __init__(self, data: dict[str, Any]):
        self.deployment_id = UUID(data["deployment_id"])
        self.deployment_status = data["deployment_status"]
        self.items = [DeploymentEvent(item) for item in data.get("items", [])]
        self.total = data["total"]
        self.skip = data["skip"]
        self.limit = data["limit"]
        self.event_type = data.get("event_type")
        self.status = data.get("status")
        self._data = data


class Deployment:
    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.agent_id = UUID(data["agent_id"])
        self.status = data["status"]
        self.replicas = data["replicas"]
        self.node_id = data.get("node_id")
        self.started_at = _parse_datetime(data.get("started_at"))
        self.ended_at = _parse_datetime(data.get("ended_at"))
        self.error_message = data.get("error_message")
        self.events = [DeploymentEvent(item) for item in data.get("events", [])]
        self._data = data

    def __repr__(self) -> str:
        return f"Deployment(id={self.id}, agent_id={self.agent_id}, status={self.status})"


class Deployments:
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

    def create(self, agent_id: UUID | str, replicas: int = 1) -> Deployment:
        """Create a deployment via /deployments (canonical backend route)."""
        self._require_sync_client()
        response = self._client.post(
            "deployments",
            json={"agent_id": str(agent_id), "replicas": replicas},
        )
        response.raise_for_status()
        return Deployment(response.json())

    async def acreate(self, agent_id: UUID | str, replicas: int = 1) -> Deployment:
        """Create a deployment via /deployments (canonical backend route)."""
        self._require_async_client()
        response = await self._client.post(
            "deployments",
            json={"agent_id": str(agent_id), "replicas": replicas},
        )
        response.raise_for_status()
        return Deployment(response.json())

    def create_for_agent(self, agent_id: UUID | str) -> dict[str, Any]:
        """Create deployment via legacy/live route /agents/{agent_id}/deploy.

        This endpoint currently returns a lightweight payload:
        {"deployment_id": ..., "status": ...}
        """
        self._require_sync_client()
        response = self._client.post(api_path("agents/{agent_id}/deploy", agent_id=agent_id))
        response.raise_for_status()
        return response.json()

    async def acreate_for_agent(self, agent_id: UUID | str) -> dict[str, Any]:
        """Create deployment via legacy/live route /agents/{agent_id}/deploy."""
        self._require_async_client()
        response = await self._client.post(api_path("agents/{agent_id}/deploy", agent_id=agent_id))
        response.raise_for_status()
        return response.json()

    def list(
        self,
        skip: int = 0,
        limit: int = 50,
        agent_id: Optional[UUID | str] = None,
        status: Optional[str] = None,
    ) -> list[Deployment]:
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if agent_id:
            params["agent_id"] = str(agent_id)
        if status:
            params["status"] = status

        self._require_sync_client()
        response = self._client.get("deployments", params=params)
        response.raise_for_status()
        body = response.json()
        # Support new envelope {items, total, ...} and legacy bare-array format
        items = body.get("items", body) if isinstance(body, dict) else body
        return [Deployment(data) for data in items]

    async def alist(
        self,
        skip: int = 0,
        limit: int = 50,
        agent_id: Optional[UUID | str] = None,
        status: Optional[str] = None,
    ) -> list[Deployment]:
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if agent_id:
            params["agent_id"] = str(agent_id)
        if status:
            params["status"] = status

        self._require_async_client()
        response = await self._client.get("deployments", params=params)
        response.raise_for_status()
        body = response.json()
        # Support new envelope {items, total, ...} and legacy bare-array format
        items = body.get("items", body) if isinstance(body, dict) else body
        return [Deployment(data) for data in items]

    def get(self, deployment_id: UUID | str) -> Deployment:
        self._require_sync_client()
        response = self._client.get(
            api_path("deployments/{deployment_id}", deployment_id=deployment_id)
        )
        response.raise_for_status()
        return Deployment(response.json())

    async def aget(self, deployment_id: UUID | str) -> Deployment:
        self._require_async_client()
        response = await self._client.get(
            api_path("deployments/{deployment_id}", deployment_id=deployment_id)
        )
        response.raise_for_status()
        return Deployment(response.json())

    def events(
        self,
        deployment_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> DeploymentEventHistory:
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if event_type:
            params["event_type"] = event_type
        if status:
            params["status"] = status

        self._require_sync_client()
        response = self._client.get(
            api_path("deployments/{deployment_id}/events", deployment_id=deployment_id),
            params=params,
        )
        response.raise_for_status()
        return DeploymentEventHistory(response.json())

    async def aevents(
        self,
        deployment_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> DeploymentEventHistory:
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if event_type:
            params["event_type"] = event_type
        if status:
            params["status"] = status

        self._require_async_client()
        response = await self._client.get(
            api_path("deployments/{deployment_id}/events", deployment_id=deployment_id),
            params=params,
        )
        response.raise_for_status()
        return DeploymentEventHistory(response.json())

    def scale(self, deployment_id: UUID | str, replicas: int) -> Deployment:
        self._require_sync_client()
        response = self._client.post(
            api_path("deployments/{deployment_id}/scale", deployment_id=deployment_id),
            json={"replicas": replicas},
        )
        response.raise_for_status()
        return Deployment(response.json())

    async def ascale(self, deployment_id: UUID | str, replicas: int) -> Deployment:
        self._require_async_client()
        response = await self._client.post(
            api_path("deployments/{deployment_id}/scale", deployment_id=deployment_id),
            json={"replicas": replicas},
        )
        response.raise_for_status()
        return Deployment(response.json())

    def restart(self, deployment_id: UUID | str) -> Deployment:
        self._require_sync_client()
        response = self._client.post(
            api_path("deployments/{deployment_id}/restart", deployment_id=deployment_id)
        )
        response.raise_for_status()
        return Deployment(response.json())

    async def arestart(self, deployment_id: UUID | str) -> Deployment:
        self._require_async_client()
        response = await self._client.post(
            api_path("deployments/{deployment_id}/restart", deployment_id=deployment_id)
        )
        response.raise_for_status()
        return Deployment(response.json())

    def delete(self, deployment_id: UUID | str) -> None:
        self._require_sync_client()
        response = self._client.delete(
            api_path("deployments/{deployment_id}", deployment_id=deployment_id)
        )
        response.raise_for_status()

    async def adelete(self, deployment_id: UUID | str) -> None:
        self._require_async_client()
        response = await self._client.delete(
            api_path("deployments/{deployment_id}", deployment_id=deployment_id)
        )
        response.raise_for_status()

    def logs(
        self,
        deployment_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
        level: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if level:
            params["level"] = level

        self._require_sync_client()
        response = self._client.get(
            api_path("deployments/{deployment_id}/logs", deployment_id=deployment_id),
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def alogs(
        self,
        deployment_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
        level: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if level:
            params["level"] = level

        self._require_async_client()
        response = await self._client.get(
            api_path("deployments/{deployment_id}/logs", deployment_id=deployment_id),
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def metrics(
        self,
        deployment_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_sync_client()
        response = self._client.get(
            api_path("deployments/{deployment_id}/metrics", deployment_id=deployment_id),
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        return response.json()

    async def ametrics(
        self,
        deployment_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_async_client()
        response = await self._client.get(
            api_path("deployments/{deployment_id}/metrics", deployment_id=deployment_id),
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        return response.json()
