"""Governance Supervision API SDK - /runtime/governance/supervised endpoints (Faramesh)."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from mutx._http import api_path


class SupervisedAgent:
    """Represents a supervised agent."""

    def __init__(self, data: dict[str, Any]):
        self.agent_id: str = data.get("agent_id", "")
        self.status: str = data.get("status", "")
        self.pid: Optional[int] = data.get("pid")
        self.started_at: Optional[str] = data.get("started_at")
        self.restart_count: int = data.get("restart_count", 0)
        self._data = data

    def __repr__(self) -> str:
        return f"SupervisedAgent(id={self.agent_id}, status={self.status})"


class LaunchProfile:
    """Represents a launch profile for supervised agents."""

    def __init__(self, data: dict[str, Any]):
        self.name: str = data["name"]
        self.command: list[str] = data["command"]
        self.env_keys: list[str] = data.get("env_keys", [])
        self.faram_mesh_policy: Optional[str] = data.get("faramesh_policy")
        self._data = data


class GovernanceSupervision:
    """SDK resource for /runtime/governance/supervised endpoints.

    Requires internal user authentication (verified email from allowed domain).
    """

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

    def list_agents(self) -> list[SupervisedAgent]:
        """List all supervised agents. Requires internal user auth."""
        self._require_sync_client()
        response = self._client.get("runtime/governance/supervised/")
        response.raise_for_status()
        return [SupervisedAgent(d) for d in response.json()]

    async def alist_agents(self) -> list[SupervisedAgent]:
        """List all supervised agents (async)."""
        self._require_async_client()
        response = await self._client.get("runtime/governance/supervised/")
        response.raise_for_status()
        return [SupervisedAgent(d) for d in response.json()]

    def list_profiles(self) -> list[LaunchProfile]:
        """List configured launch profiles for supervised agents."""
        self._require_sync_client()
        response = self._client.get("runtime/governance/supervised/profiles")
        response.raise_for_status()
        return [LaunchProfile(d) for d in response.json()]

    async def alist_profiles(self) -> list[LaunchProfile]:
        """List configured launch profiles (async)."""
        self._require_async_client()
        response = await self._client.get("runtime/governance/supervised/profiles")
        response.raise_for_status()
        return [LaunchProfile(d) for d in response.json()]

    def get_agent(
        self,
        agent_id: str,
    ) -> SupervisedAgent:
        """Get status of a supervised agent."""
        self._require_sync_client()
        response = self._client.get(
            api_path("runtime/governance/supervised/{agent_id}", agent_id=agent_id)
        )
        response.raise_for_status()
        return SupervisedAgent(response.json())

    async def aget_agent(
        self,
        agent_id: str,
    ) -> SupervisedAgent:
        """Get status of a supervised agent (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("runtime/governance/supervised/{agent_id}", agent_id=agent_id)
        )
        response.raise_for_status()
        return SupervisedAgent(response.json())

    def start_agent(
        self,
        agent_id: str,
        command: list[str],
        profile: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        faramesh_policy: Optional[str] = None,
    ) -> SupervisedAgent:
        """Start an agent under Faramesh supervision."""
        self._require_sync_client()
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "command": command,
        }
        if profile:
            payload["profile"] = profile
        if env:
            payload["env"] = env
        if faramesh_policy:
            payload["faramesh_policy"] = faramesh_policy

        response = self._client.post("runtime/governance/supervised/start", json=payload)
        response.raise_for_status()
        return SupervisedAgent(response.json())

    async def astart_agent(
        self,
        agent_id: str,
        command: list[str],
        profile: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        faramesh_policy: Optional[str] = None,
    ) -> SupervisedAgent:
        """Start an agent under Faramesh supervision (async)."""
        self._require_async_client()
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "command": command,
        }
        if profile:
            payload["profile"] = profile
        if env:
            payload["env"] = env
        if faramesh_policy:
            payload["faramesh_policy"] = faramesh_policy

        response = await self._client.post("runtime/governance/supervised/start", json=payload)
        response.raise_for_status()
        return SupervisedAgent(response.json())

    def stop_agent(
        self,
        agent_id: str,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """Stop a supervised agent."""
        self._require_sync_client()
        response = self._client.post(
            api_path("runtime/governance/supervised/{agent_id}/stop", agent_id=agent_id),
            json={"timeout": timeout},
        )
        response.raise_for_status()
        return response.json()

    async def astop_agent(
        self,
        agent_id: str,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """Stop a supervised agent (async)."""
        self._require_async_client()
        response = await self._client.post(
            api_path("runtime/governance/supervised/{agent_id}/stop", agent_id=agent_id),
            json={"timeout": timeout},
        )
        response.raise_for_status()
        return response.json()

    def restart_agent(
        self,
        agent_id: str,
    ) -> SupervisedAgent:
        """Restart a supervised agent."""
        self._require_sync_client()
        response = self._client.post(
            api_path("runtime/governance/supervised/{agent_id}/restart", agent_id=agent_id)
        )
        response.raise_for_status()
        return SupervisedAgent(response.json())

    async def arestart_agent(
        self,
        agent_id: str,
    ) -> SupervisedAgent:
        """Restart a supervised agent (async)."""
        self._require_async_client()
        response = await self._client.post(
            api_path("runtime/governance/supervised/{agent_id}/restart", agent_id=agent_id)
        )
        response.raise_for_status()
        return SupervisedAgent(response.json())
