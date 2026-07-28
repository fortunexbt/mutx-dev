"""Swarms API SDK - /swarms endpoints for multi-agent swarm management."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import httpx

from mutx._http import api_path


class SwarmAgent:
    """Represents an agent within a swarm."""

    def __init__(self, data: dict[str, Any]):
        self.agent_id: str = data["agent_id"]
        self.agent_name: str = data["agent_name"]
        self.status: str = data["status"]
        self.replicas: int = data["replicas"]
        self._data = data


class Swarm:
    """Represents a multi-agent swarm."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.description: Optional[str] = data.get("description")
        self.agent_ids: list[str] = data["agent_ids"]
        self.min_replicas: int = data["min_replicas"]
        self.max_replicas: int = data["max_replicas"]
        self.created_at: datetime = datetime.fromisoformat(data["created_at"])
        self.updated_at: datetime = datetime.fromisoformat(data["updated_at"])
        self.agents: list[SwarmAgent] = [SwarmAgent(a) for a in data.get("agents", [])]
        self._data = data

    def __repr__(self) -> str:
        return f"Swarm(id={self.id}, name={self.name}, agents={len(self.agent_ids)})"


class SwarmBlueprintRole:
    """Represents a recommended role inside a curated swarm blueprint."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.title: str = data["title"]
        self.bundle_id: str = data["bundle_id"]
        self.goal: str = data["goal"]
        self._data = data


class SwarmBlueprint:
    """Represents a curated multi-agent swarm blueprint."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.summary: str = data.get("summary", "")
        self.description: str = data.get("description", "")
        self.roles: list[SwarmBlueprintRole] = [
            SwarmBlueprintRole(item) for item in data.get("roles", [])
        ]
        self.recommended_min_agents: int = int(data.get("recommended_min_agents", 1))
        self.recommended_max_agents: int = int(data.get("recommended_max_agents", 1))
        self.coordination_notes: str = data.get("coordination_notes", "")
        self.tags: list[str] = list(data.get("tags") or [])
        self._data = data

    def __repr__(self) -> str:
        return f"SwarmBlueprint(id={self.id}, roles={len(self.roles)})"


class Swarms:
    """SDK resource for /swarms endpoints."""

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

    def list(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Swarm], int]:
        """List all swarms for the current user.

        Returns:
            Tuple of (list of swarms, total count)
        """
        self._require_sync_client()
        response = self._client.get(
            "swarms",
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        data = response.json()
        return [Swarm(s) for s in data["items"]], data["total"]

    def list_blueprints(self) -> list[SwarmBlueprint]:
        """List curated multi-agent swarm blueprints."""
        self._require_sync_client()
        response = self._client.get("swarms/blueprints")
        response.raise_for_status()
        return [SwarmBlueprint(item) for item in response.json()]

    async def alist(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Swarm], int]:
        """List all swarms (async)."""
        self._require_async_client()
        response = await self._client.get(
            "swarms",
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        data = response.json()
        return [Swarm(s) for s in data["items"]], data["total"]

    async def alist_blueprints(self) -> list[SwarmBlueprint]:
        """List curated multi-agent swarm blueprints (async)."""
        self._require_async_client()
        response = await self._client.get("swarms/blueprints")
        response.raise_for_status()
        return [SwarmBlueprint(item) for item in response.json()]

    def get(
        self,
        swarm_id: str,
    ) -> Swarm:
        """Get swarm details."""
        self._require_sync_client()
        response = self._client.get(api_path("swarms/{swarm_id}", swarm_id=swarm_id))
        response.raise_for_status()
        return Swarm(response.json())

    async def aget(
        self,
        swarm_id: str,
    ) -> Swarm:
        """Get swarm details (async)."""
        self._require_async_client()
        response = await self._client.get(api_path("swarms/{swarm_id}", swarm_id=swarm_id))
        response.raise_for_status()
        return Swarm(response.json())

    def create(
        self,
        name: str,
        agent_ids: list[str],
        description: Optional[str] = None,
        min_replicas: int = 1,
        max_replicas: int = 10,
    ) -> Swarm:
        """Create a new swarm.

        Args:
            name: Swarm name
            agent_ids: List of agent UUIDs to include in the swarm
            description: Optional description
            min_replicas: Minimum replicas per agent (default 1)
            max_replicas: Maximum replicas per agent (default 10)
        """
        self._require_sync_client()
        payload: dict[str, Any] = {
            "name": name,
            "agent_ids": [str(a) for a in agent_ids],
            "min_replicas": min_replicas,
            "max_replicas": max_replicas,
        }
        if description:
            payload["description"] = description

        response = self._client.post("swarms", json=payload)
        response.raise_for_status()
        return Swarm(response.json())

    async def acreate(
        self,
        name: str,
        agent_ids: list[str],
        description: Optional[str] = None,
        min_replicas: int = 1,
        max_replicas: int = 10,
    ) -> Swarm:
        """Create a new swarm (async)."""
        self._require_async_client()
        payload: dict[str, Any] = {
            "name": name,
            "agent_ids": [str(a) for a in agent_ids],
            "min_replicas": min_replicas,
            "max_replicas": max_replicas,
        }
        if description:
            payload["description"] = description

        response = await self._client.post("swarms", json=payload)
        response.raise_for_status()
        return Swarm(response.json())

    def scale(
        self,
        swarm_id: str,
        replicas: int,
    ) -> Swarm:
        """Scale all agents in a swarm to the specified replicas.

        Args:
            swarm_id: The swarm UUID
            replicas: Target replicas per agent
        """
        self._require_sync_client()
        response = self._client.post(
            api_path("swarms/{swarm_id}/scale", swarm_id=swarm_id),
            json={"replicas": replicas},
        )
        response.raise_for_status()
        return Swarm(response.json())

    async def ascale(
        self,
        swarm_id: str,
        replicas: int,
    ) -> Swarm:
        """Scale all agents in a swarm (async)."""
        self._require_async_client()
        response = await self._client.post(
            api_path("swarms/{swarm_id}/scale", swarm_id=swarm_id),
            json={"replicas": replicas},
        )
        response.raise_for_status()
        return Swarm(response.json())
