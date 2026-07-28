"""Sessions API SDK - /sessions endpoints."""

from __future__ import annotations

from typing import Any, Optional

import httpx


class Session:
    """Represents an assistant session."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data.get("id", "")
        self.source: str = data.get("source", "unknown")
        self.name: str = data.get("name", "")
        self.status: str = data.get("status", "")
        self.agent_id: Optional[str] = data.get("agent_id")
        self.assistant_id: Optional[str] = data.get("assistant_id")
        self.last_activity: int = data.get("last_activity", 0)
        self.model: Optional[str] = data.get("model")
        self.thinking_level: Optional[str] = data.get("thinking_level")
        self.verbose: Optional[str] = data.get("verbose")
        self.reasoning: Optional[str] = data.get("reasoning")
        self.label: Optional[str] = data.get("label")
        self._data = data

    def __repr__(self) -> str:
        return f"Session(id={self.id}, source={self.source}, status={self.status})"


class Sessions:
    """SDK resource for /sessions endpoints."""

    VALID_THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh"]
    VALID_VERBOSE_LEVELS = ["off", "on", "full"]
    VALID_REASONING_LEVELS = ["off", "on", "stream"]

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
        agent_id: Optional[str] = None,
    ) -> list[Session]:
        """List sessions, optionally filtered by agent."""
        self._require_sync_client()
        params: dict[str, Any] = {}
        if agent_id:
            params["agent_id"] = str(agent_id)
        response = self._client.get("sessions", params=params)
        response.raise_for_status()
        return [Session(d) for d in response.json().get("sessions", [])]

    async def alist(
        self,
        agent_id: Optional[str] = None,
    ) -> list[Session]:
        """List sessions (async)."""
        self._require_async_client()
        params: dict[str, Any] = {}
        if agent_id:
            params["agent_id"] = str(agent_id)
        response = await self._client.get("sessions", params=params)
        response.raise_for_status()
        return [Session(d) for d in response.json().get("sessions", [])]

    def set_thinking(
        self,
        session_key: str,
        level: str,
    ) -> dict[str, Any]:
        """Set thinking level for a session."""
        self._require_sync_client()
        if level not in self.VALID_THINKING_LEVELS:
            raise ValueError(
                f"Invalid thinking level. Must be one of: {self.VALID_THINKING_LEVELS}"
            )
        response = self._client.post(
            "sessions",
            params={"action": "set-thinking"},
            json={"session_key": session_key, "level": level},
        )
        response.raise_for_status()
        return response.json()

    async def aset_thinking(
        self,
        session_key: str,
        level: str,
    ) -> dict[str, Any]:
        """Set thinking level for a session (async)."""
        self._require_async_client()
        if level not in self.VALID_THINKING_LEVELS:
            raise ValueError(
                f"Invalid thinking level. Must be one of: {self.VALID_THINKING_LEVELS}"
            )
        response = await self._client.post(
            "sessions",
            params={"action": "set-thinking"},
            json={"session_key": session_key, "level": level},
        )
        response.raise_for_status()
        return response.json()

    def set_reasoning(
        self,
        session_key: str,
        level: str,
    ) -> dict[str, Any]:
        """Set reasoning level for a session."""
        self._require_sync_client()
        if level not in self.VALID_REASONING_LEVELS:
            raise ValueError(
                f"Invalid reasoning level. Must be one of: {self.VALID_REASONING_LEVELS}"
            )
        response = self._client.post(
            "sessions",
            params={"action": "set-reasoning"},
            json={"session_key": session_key, "level": level},
        )
        response.raise_for_status()
        return response.json()

    async def aset_reasoning(
        self,
        session_key: str,
        level: str,
    ) -> dict[str, Any]:
        """Set reasoning level for a session (async)."""
        self._require_async_client()
        if level not in self.VALID_REASONING_LEVELS:
            raise ValueError(
                f"Invalid reasoning level. Must be one of: {self.VALID_REASONING_LEVELS}"
            )
        response = await self._client.post(
            "sessions",
            params={"action": "set-reasoning"},
            json={"session_key": session_key, "level": level},
        )
        response.raise_for_status()
        return response.json()

    def set_label(
        self,
        session_key: str,
        label: str,
    ) -> dict[str, Any]:
        """Set label for a session."""
        self._require_sync_client()
        if len(label) > 100:
            raise ValueError("Label must be a string up to 100 characters")
        response = self._client.post(
            "sessions",
            params={"action": "set-label"},
            json={"session_key": session_key, "label": label},
        )
        response.raise_for_status()
        return response.json()

    async def aset_label(
        self,
        session_key: str,
        label: str,
    ) -> dict[str, Any]:
        """Set label for a session (async)."""
        self._require_async_client()
        if len(label) > 100:
            raise ValueError("Label must be a string up to 100 characters")
        response = await self._client.post(
            "sessions",
            params={"action": "set-label"},
            json={"session_key": session_key, "label": label},
        )
        response.raise_for_status()
        return response.json()

    def delete(
        self,
        session_key: str,
    ) -> dict[str, Any]:
        """Delete a session."""
        self._require_sync_client()
        response = self._client.delete("sessions", json={"session_key": session_key})
        response.raise_for_status()
        return response.json()

    async def adelete(
        self,
        session_key: str,
    ) -> dict[str, Any]:
        """Delete a session (async)."""
        self._require_async_client()
        response = await self._client.delete("sessions", json={"session_key": session_key})
        response.raise_for_status()
        return response.json()
