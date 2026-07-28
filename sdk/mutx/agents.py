from __future__ import annotations

import json
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Generator, Optional
from uuid import UUID

import httpx

from mutx._http import api_path
from mutx.pagination import Page, parse_page


class Agent:
    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.name = data["name"]
        self.description = data.get("description")
        self.status = data["status"]
        self.config_json = data.get("config")
        self.config = self._parse_config(self.config_json)
        self.created_at = datetime.fromisoformat(data["created_at"])
        self.updated_at = datetime.fromisoformat(data["updated_at"])
        self.user_id = data.get("user_id")
        self._data = data

    @staticmethod
    def _parse_config(raw_config: Any) -> Any:
        if not isinstance(raw_config, str):
            return raw_config

        try:
            return json.loads(raw_config)
        except json.JSONDecodeError:
            return raw_config

    def __repr__(self) -> str:
        return f"Agent(id={self.id}, name={self.name}, status={self.status})"


class DeploymentEvent:
    def __init__(self, data: dict[str, Any]) -> None:
        self.id = UUID(data["id"])
        self.deployment_id = UUID(data["deployment_id"])
        self.event_type = data["event_type"]
        self.status = data["status"]
        self.node_id = data.get("node_id")
        self.error_message = data.get("error_message")
        self.created_at = datetime.fromisoformat(data["created_at"])
        self._data = data


class Deployment:
    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.agent_id = UUID(data["agent_id"])
        self.status = data["status"]
        self.replicas = data["replicas"]
        self.node_id = data.get("node_id")
        self.started_at = (
            datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
        )
        self.ended_at = datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None
        self.error_message = data.get("error_message")
        self.events = [DeploymentEvent(item) for item in data.get("events", [])]
        self._data = data


class AgentDetail(Agent):
    def __init__(self, data: dict[str, Any]):
        super().__init__(data)
        self.deployments = [Deployment(d) for d in data.get("deployments", [])]


class AgentLog:
    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.agent_id = UUID(data["agent_id"])
        self.level = data["level"]
        self.message = data["message"]
        self.timestamp = datetime.fromisoformat(data["timestamp"])
        self.extra_data = data.get("extra_data")
        self.metadata = data.get("metadata", self.extra_data)
        self._data = data


class AgentMetric:
    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.agent_id = UUID(data["agent_id"])
        self.cpu_usage = data.get("cpu_usage")
        self.memory_usage = data.get("memory_usage")
        self.timestamp = datetime.fromisoformat(data["timestamp"])
        self._data = data


class AgentConfig:
    """The normalized config returned by GET /v1/agents/{id}/config."""

    def __init__(self, data: dict[str, Any]):
        self.agent_id = UUID(data["agent_id"])
        self.type = data.get("type")
        self.config = data.get("config", {})
        self.config_version = data.get("config_version")
        self.updated_at = datetime.fromisoformat(data["updated_at"])
        self._data = data


class AgentVersion:
    """A single snapshot from the agent version history."""

    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.agent_id = UUID(data["agent_id"])
        self.version = data["version"]
        self.config_snapshot = data.get("config_snapshot")
        self.status = data.get("status")
        self.created_at = datetime.fromisoformat(data["created_at"])
        self._data = data


class AgentResourceUsage:
    """A single resource-usage record for an agent."""

    def __init__(self, data: dict[str, Any]):
        self.id = UUID(data["id"])
        self.agent_id = UUID(data["agent_id"])
        self.prompt_tokens = data.get("prompt_tokens")
        self.completion_tokens = data.get("completion_tokens")
        self.total_tokens = data.get("total_tokens")
        self.api_calls = data.get("api_calls")
        self.cost_usd = data.get("cost_usd")
        self.model = data.get("model")
        self.extra_metadata = data.get("extra_metadata")
        self.period_start = data.get("period_start")
        self.period_end = data.get("period_end")
        self._data = data


class Agents:
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
        name: str,
        description: Optional[str] = None,
        type: str = "openai",
        config: Optional[dict[str, Any] | str] = None,
    ) -> Agent:
        self._require_sync_client()
        response = self._client.post(
            "agents",
            json={
                "name": name,
                "description": description,
                "type": type,
                "config": config,
            },
        )
        response.raise_for_status()
        return Agent(response.json())

    async def acreate(
        self,
        name: str,
        description: Optional[str] = None,
        type: str = "openai",
        config: Optional[dict[str, Any] | str] = None,
    ) -> Agent:
        self._require_async_client()
        response = await self._client.post(
            "agents",
            json={
                "name": name,
                "description": description,
                "type": type,
                "config": config,
            },
        )
        response.raise_for_status()
        return Agent(response.json())

    def list(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> Page[Agent]:
        self._require_sync_client()
        response = self._client.get(
            "agents",
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        return parse_page(
            response.json(),
            Agent,
            requested_skip=skip,
            requested_limit=limit,
            require_has_more=True,
        )

    async def alist(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> Page[Agent]:
        self._require_async_client()
        response = await self._client.get(
            "agents",
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        return parse_page(
            response.json(),
            Agent,
            requested_skip=skip,
            requested_limit=limit,
            require_has_more=True,
        )

    def get(self, agent_id: UUID | str) -> AgentDetail:
        self._require_sync_client()
        response = self._client.get(api_path("agents/{agent_id}", agent_id=agent_id))
        response.raise_for_status()
        return AgentDetail(response.json())

    async def aget(self, agent_id: UUID | str) -> AgentDetail:
        self._require_async_client()
        response = await self._client.get(api_path("agents/{agent_id}", agent_id=agent_id))
        response.raise_for_status()
        return AgentDetail(response.json())

    def delete(self, agent_id: UUID | str) -> None:
        self._require_sync_client()
        response = self._client.delete(api_path("agents/{agent_id}", agent_id=agent_id))
        response.raise_for_status()

    async def adelete(self, agent_id: UUID | str) -> None:
        self._require_async_client()
        response = await self._client.delete(api_path("agents/{agent_id}", agent_id=agent_id))
        response.raise_for_status()

    def deploy(self, agent_id: UUID | str) -> dict[str, Any]:
        self._require_sync_client()
        response = self._client.post(api_path("agents/{agent_id}/deploy", agent_id=agent_id))
        response.raise_for_status()
        return response.json()

    async def adeploy(self, agent_id: UUID | str) -> dict[str, Any]:
        self._require_async_client()
        response = await self._client.post(api_path("agents/{agent_id}/deploy", agent_id=agent_id))
        response.raise_for_status()
        return response.json()

    def stop(self, agent_id: UUID | str) -> dict[str, Any]:
        self._require_sync_client()
        response = self._client.post(api_path("agents/{agent_id}/stop", agent_id=agent_id))
        response.raise_for_status()
        return response.json()

    async def astop(self, agent_id: UUID | str) -> dict[str, Any]:
        self._require_async_client()
        response = await self._client.post(api_path("agents/{agent_id}/stop", agent_id=agent_id))
        response.raise_for_status()
        return response.json()

    def logs(
        self,
        agent_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
        level: Optional[str] = None,
    ) -> list[AgentLog]:
        self._require_sync_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if level is not None:
            params["level"] = level
        response = self._client.get(
            api_path("agents/{agent_id}/logs", agent_id=agent_id),
            params=params,
        )
        response.raise_for_status()
        return [AgentLog(data) for data in response.json()["items"]]

    async def alogs(
        self,
        agent_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
        level: Optional[str] = None,
    ) -> list[AgentLog]:
        self._require_async_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if level is not None:
            params["level"] = level
        response = await self._client.get(
            api_path("agents/{agent_id}/logs", agent_id=agent_id),
            params=params,
        )
        response.raise_for_status()
        return [AgentLog(data) for data in response.json()["items"]]

    def metrics(
        self,
        agent_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AgentMetric]:
        self._require_sync_client()
        response = self._client.get(
            api_path("agents/{agent_id}/metrics", agent_id=agent_id),
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        return [AgentMetric(data) for data in response.json()["items"]]

    async def ametrics(
        self,
        agent_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AgentMetric]:
        self._require_async_client()
        response = await self._client.get(
            api_path("agents/{agent_id}/metrics", agent_id=agent_id),
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        return [AgentMetric(data) for data in response.json()["items"]]

    def update_config(
        self,
        agent_id: UUID | str,
        config: dict[str, Any] | str,
    ) -> AgentDetail:
        """Update agent configuration.

        Args:
            agent_id: The agent UUID
            config: New configuration as dict or JSON string
        """
        self._require_sync_client()
        payload = {"config": config if isinstance(config, str) else json.dumps(config)}
        response = self._client.patch(
            api_path("agents/{agent_id}/config", agent_id=agent_id),
            json=payload,
        )
        response.raise_for_status()
        return AgentDetail(response.json())

    async def aupdate_config(
        self,
        agent_id: UUID | str,
        config: dict[str, Any] | str,
    ) -> AgentDetail:
        """Update agent configuration (async).

        Args:
            agent_id: The agent UUID
            config: New configuration as dict or JSON string
        """
        self._require_async_client()
        payload = {"config": config if isinstance(config, str) else json.dumps(config)}
        response = await self._client.patch(
            api_path("agents/{agent_id}/config", agent_id=agent_id),
            json=payload,
        )
        response.raise_for_status()
        return AgentDetail(response.json())

    def get_config(self, agent_id: UUID | str) -> AgentConfig:
        """Read the normalized config and version for an agent.

        Args:
            agent_id: The agent UUID
        """
        self._require_sync_client()
        response = self._client.get(api_path("agents/{agent_id}/config", agent_id=agent_id))
        response.raise_for_status()
        return AgentConfig(response.json())

    async def aget_config(self, agent_id: UUID | str) -> AgentConfig:
        """Read the normalized config and version for an agent (async).

        Args:
            agent_id: The agent UUID
        """
        self._require_async_client()
        response = await self._client.get(api_path("agents/{agent_id}/config", agent_id=agent_id))
        response.raise_for_status()
        return AgentConfig(response.json())

    def versions(
        self,
        agent_id: UUID | str,
        skip: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List version history for an agent.

        Args:
            agent_id: The agent UUID
            skip: Number of records to skip (for pagination)
            limit: Maximum number of versions to return (default 50)

        Returns:
            dict with items (list of AgentVersion), total, has_more, skip, and limit
        """
        self._require_sync_client()
        response = self._client.get(
            api_path("agents/{agent_id}/versions", agent_id=agent_id),
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        result = response.json()
        # Backwards-compat: older servers may not include has_more
        result.setdefault("has_more", False)
        return result

    async def aversions(
        self,
        agent_id: UUID | str,
        skip: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List version history for an agent (async).

        Args:
            agent_id: The agent UUID
            skip: Number of records to skip (for pagination)
            limit: Maximum number of versions to return (default 50)
        """
        self._require_async_client()
        response = await self._client.get(
            api_path("agents/{agent_id}/versions", agent_id=agent_id),
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        result = response.json()
        # Backwards-compat: older servers may not include has_more
        result.setdefault("has_more", False)
        return result

    def rollback(self, agent_id: UUID | str, version: int) -> Agent:
        """Roll back an agent to a specific config version.

        Args:
            agent_id: The agent UUID
            version: The config version number to roll back to
        """
        self._require_sync_client()
        response = self._client.post(
            api_path("agents/{agent_id}/rollback", agent_id=agent_id),
            json={"version": version},
        )
        response.raise_for_status()
        return Agent(response.json())

    async def arollback(self, agent_id: UUID | str, version: int) -> Agent:
        """Roll back an agent to a specific config version (async).

        Args:
            agent_id: The agent UUID
            version: The config version number to roll back to
        """
        self._require_async_client()
        response = await self._client.post(
            api_path("agents/{agent_id}/rollback", agent_id=agent_id),
            json={"version": version},
        )
        response.raise_for_status()
        return Agent(response.json())

    def record_resource_usage(
        self,
        agent_id: UUID | str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        api_calls: int = 0,
        cost_usd: float = 0.0,
        model: Optional[str] = None,
        extra_metadata: Optional[dict[str, Any]] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> AgentResourceUsage:
        """Record resource usage (tokens, cost, API calls) for an agent.

        Args:
            agent_id: The agent UUID
            prompt_tokens: Number of prompt tokens used
            completion_tokens: Number of completion tokens generated
            total_tokens: Total tokens used (prompt + completion)
            api_calls: Number of API calls made
            cost_usd: Cost in USD
            model: Model name used
            extra_metadata: Arbitrary key/value metadata
            period_start: ISO-8601 start of the billing period
            period_end: ISO-8601 end of the billing period
        """
        self._require_sync_client()
        payload: dict[str, Any] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "api_calls": api_calls,
            "cost_usd": cost_usd,
        }
        if model is not None:
            payload["model"] = model
        if extra_metadata is not None:
            payload["extra_metadata"] = extra_metadata
        if period_start is not None:
            payload["period_start"] = period_start
        if period_end is not None:
            payload["period_end"] = period_end
        response = self._client.post(
            api_path("agents/{agent_id}/resource-usage", agent_id=agent_id),
            json=payload,
        )
        response.raise_for_status()
        return AgentResourceUsage(response.json())

    async def arecord_resource_usage(
        self,
        agent_id: UUID | str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        api_calls: int = 0,
        cost_usd: float = 0.0,
        model: Optional[str] = None,
        extra_metadata: Optional[dict[str, Any]] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> AgentResourceUsage:
        """Record resource usage for an agent (async). See sync docstring."""
        self._require_async_client()
        payload: dict[str, Any] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "api_calls": api_calls,
            "cost_usd": cost_usd,
        }
        if model is not None:
            payload["model"] = model
        if extra_metadata is not None:
            payload["extra_metadata"] = extra_metadata
        if period_start is not None:
            payload["period_start"] = period_start
        if period_end is not None:
            payload["period_end"] = period_end
        response = await self._client.post(
            api_path("agents/{agent_id}/resource-usage", agent_id=agent_id),
            json=payload,
        )
        response.raise_for_status()
        return AgentResourceUsage(response.json())

    def list_resource_usage(
        self,
        agent_id: UUID | str,
        skip: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List recorded resource usage for an agent.

        Args:
            agent_id: The agent UUID
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return (default 50, max 100)

        Returns:
            dict with items (list of AgentResourceUsage), total, has_more, skip, and limit
        """
        self._require_sync_client()
        response = self._client.get(
            api_path("agents/{agent_id}/resource-usage", agent_id=agent_id),
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        result = response.json()
        # Normalise: newer servers return {items,total,has_more,...}, older returned a raw list
        if isinstance(result, list):
            result = {
                "items": result,
                "total": len(result),
                "skip": skip,
                "limit": limit,
                "has_more": False,
            }
        else:
            result.setdefault("has_more", False)
        return result

    async def alist_resource_usage(
        self,
        agent_id: UUID | str,
        skip: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List recorded resource usage for an agent (async).

        Args:
            agent_id: The agent UUID
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return (default 50, max 100)

        Returns:
            dict with items (list of AgentResourceUsage), total, has_more, skip, and limit
        """
        self._require_async_client()
        response = await self._client.get(
            api_path("agents/{agent_id}/resource-usage", agent_id=agent_id),
            params={"skip": skip, "limit": limit},
        )
        response.raise_for_status()
        result = response.json()
        # Normalise: newer servers return {items,total,has_more,...}, older returned a raw list
        if isinstance(result, list):
            result = {
                "items": result,
                "total": len(result),
                "skip": skip,
                "limit": limit,
                "has_more": False,
            }
        else:
            result.setdefault("has_more", False)
        return result

    def stream_logs(
        self,
        agent_id: UUID | str,
        callback: Callable[[AgentLog], None],
        level: Optional[str] = None,
    ) -> Generator[AgentLog, None, None]:
        self._require_sync_client()
        logs = self.logs(agent_id=agent_id, limit=500, level=level)
        for log in logs:
            callback(log)
            yield log

    async def astream_logs(
        self,
        agent_id: UUID | str,
        callback: Callable[[AgentLog], None],
        level: Optional[str] = None,
    ) -> AsyncGenerator[AgentLog, None]:
        self._require_async_client()
        logs = await self.alogs(agent_id=agent_id, limit=500, level=level)
        for log in logs:
            callback(log)
            yield log
