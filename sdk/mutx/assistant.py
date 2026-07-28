"""Assistant API SDK - /assistant endpoints."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from mutx._http import api_path


class AssistantSkill:
    """Represents an assistant skill."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.name: str = data.get("name", "")
        self.description: str = data.get("description", "")
        self.version: str = data.get("version", "")
        self.installed: bool = data.get("installed", False)
        self.enabled: bool = data.get("enabled", True)
        self._data = data

    def __repr__(self) -> str:
        return f"AssistantSkill(id={self.id}, installed={self.installed})"


class AssistantChannel:
    """Represents an assistant channel."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.name: str = data.get("name", "")
        self.type: str = data.get("type", "")
        self.status: str = data.get("status", "")
        self.config: dict[str, Any] = data.get("config", {})
        self._data = data


class AssistantWakeup:
    """Represents an assistant wakeup phrase."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.phrase: str = data.get("phrase", "")
        self.enabled: bool = data.get("enabled", True)
        self._data = data


class AssistantHealth:
    """Represents assistant health status."""

    def __init__(self, data: dict[str, Any]):
        self.status: str = data.get("status", "unknown")
        self.version: Optional[str] = data.get("version")
        self.uptime_seconds: Optional[float] = data.get("uptime_seconds")
        self.gateway_url: Optional[str] = data.get("gateway_url")
        self.last_check: Optional[str] = data.get("last_check")
        self._data = data


class AssistantSession:
    """Represents an assistant session."""

    def __init__(self, data: dict[str, Any]):
        self.session_id: str = data.get("session_id", "")
        self.assistant_id: str = data.get("assistant_id", "")
        self.status: str = data.get("status", "")
        self.model: Optional[str] = data.get("model")
        self.created_at: Optional[str] = data.get("created_at")
        self.last_activity: Optional[str] = data.get("last_activity")
        self._data = data


class AssistantOverview:
    """Represents an assistant overview."""

    def __init__(self, data: dict[str, Any]):
        self.has_assistant: bool = data.get("has_assistant", False)
        self.recommended_template_id: Optional[str] = data.get("recommended_template_id")
        self.assistant: Optional[dict[str, Any]] = data.get("assistant")
        self._data = data


class Assistant:
    """SDK resource for /assistant endpoints."""

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

    def overview(
        self,
        agent_id: Optional[str] = None,
    ) -> AssistantOverview:
        """Get assistant overview, optionally for a specific agent."""
        self._require_sync_client()
        params: dict[str, Any] = {}
        if agent_id:
            params["agent_id"] = str(agent_id)
        response = self._client.get("assistant/overview", params=params)
        response.raise_for_status()
        return AssistantOverview(response.json())

    async def aoverview(
        self,
        agent_id: Optional[str] = None,
    ) -> AssistantOverview:
        """Get assistant overview (async)."""
        self._require_async_client()
        params: dict[str, Any] = {}
        if agent_id:
            params["agent_id"] = str(agent_id)
        response = await self._client.get("assistant/overview", params=params)
        response.raise_for_status()
        return AssistantOverview(response.json())

    def skills(
        self,
        agent_id: str,
    ) -> list[AssistantSkill]:
        """List skills for an assistant."""
        self._require_sync_client()
        response = self._client.get(api_path("assistant/{agent_id}/skills", agent_id=agent_id))
        response.raise_for_status()
        return [AssistantSkill(d) for d in response.json()]

    async def askills(
        self,
        agent_id: str,
    ) -> list[AssistantSkill]:
        """List skills for an assistant (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("assistant/{agent_id}/skills", agent_id=agent_id)
        )
        response.raise_for_status()
        return [AssistantSkill(d) for d in response.json()]

    def install_skill(
        self,
        agent_id: str,
        skill_id: str,
    ) -> list[AssistantSkill]:
        """Install a skill for an assistant."""
        self._require_sync_client()
        response = self._client.post(
            api_path("assistant/{agent_id}/skills/{skill_id}", agent_id=agent_id, skill_id=skill_id)
        )
        response.raise_for_status()
        return [AssistantSkill(d) for d in response.json()]

    async def ainstall_skill(
        self,
        agent_id: str,
        skill_id: str,
    ) -> list[AssistantSkill]:
        """Install a skill for an assistant (async)."""
        self._require_async_client()
        response = await self._client.post(
            api_path("assistant/{agent_id}/skills/{skill_id}", agent_id=agent_id, skill_id=skill_id)
        )
        response.raise_for_status()
        return [AssistantSkill(d) for d in response.json()]

    def uninstall_skill(
        self,
        agent_id: str,
        skill_id: str,
    ) -> list[AssistantSkill]:
        """Uninstall a skill from an assistant."""
        self._require_sync_client()
        response = self._client.delete(
            api_path("assistant/{agent_id}/skills/{skill_id}", agent_id=agent_id, skill_id=skill_id)
        )
        response.raise_for_status()
        return [AssistantSkill(d) for d in response.json()]

    async def auninstall_skill(
        self,
        agent_id: str,
        skill_id: str,
    ) -> list[AssistantSkill]:
        """Uninstall a skill from an assistant (async)."""
        self._require_async_client()
        response = await self._client.delete(
            api_path("assistant/{agent_id}/skills/{skill_id}", agent_id=agent_id, skill_id=skill_id)
        )
        response.raise_for_status()
        return [AssistantSkill(d) for d in response.json()]

    def channels(
        self,
        agent_id: str,
    ) -> list[AssistantChannel]:
        """List channels for an assistant."""
        self._require_sync_client()
        response = self._client.get(api_path("assistant/{agent_id}/channels", agent_id=agent_id))
        response.raise_for_status()
        return [AssistantChannel(d) for d in response.json()]

    async def achannels(
        self,
        agent_id: str,
    ) -> list[AssistantChannel]:
        """List channels for an assistant (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("assistant/{agent_id}/channels", agent_id=agent_id)
        )
        response.raise_for_status()
        return [AssistantChannel(d) for d in response.json()]

    def wakeups(
        self,
        agent_id: str,
    ) -> list[AssistantWakeup]:
        """List wakeup phrases for an assistant."""
        self._require_sync_client()
        response = self._client.get(api_path("assistant/{agent_id}/wakeups", agent_id=agent_id))
        response.raise_for_status()
        return [AssistantWakeup(d) for d in response.json()]

    async def awakeups(
        self,
        agent_id: str,
    ) -> list[AssistantWakeup]:
        """List wakeup phrases for an assistant (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("assistant/{agent_id}/wakeups", agent_id=agent_id)
        )
        response.raise_for_status()
        return [AssistantWakeup(d) for d in response.json()]

    def health(
        self,
        agent_id: str,
    ) -> AssistantHealth:
        """Get health status for an assistant."""
        self._require_sync_client()
        response = self._client.get(api_path("assistant/{agent_id}/health", agent_id=agent_id))
        response.raise_for_status()
        return AssistantHealth(response.json())

    async def ahealth(
        self,
        agent_id: str,
    ) -> AssistantHealth:
        """Get health status for an assistant (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("assistant/{agent_id}/health", agent_id=agent_id)
        )
        response.raise_for_status()
        return AssistantHealth(response.json())

    def sessions(
        self,
        agent_id: str,
    ) -> list[AssistantSession]:
        """List sessions for an assistant."""
        self._require_sync_client()
        response = self._client.get(api_path("assistant/{agent_id}/sessions", agent_id=agent_id))
        response.raise_for_status()
        return [AssistantSession(d) for d in response.json()]

    async def asessions(
        self,
        agent_id: str,
    ) -> list[AssistantSession]:
        """List sessions for an assistant (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("assistant/{agent_id}/sessions", agent_id=agent_id)
        )
        response.raise_for_status()
        return [AssistantSession(d) for d in response.json()]
