"""Runtime API SDK - /runtime endpoints for runtime provider state and governance."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from mutx._http import api_path


class RuntimeProviderSnapshot:
    """Represents a runtime provider snapshot."""

    def __init__(self, data: dict[str, Any]):
        self.provider: str = data["provider"]
        self.credentials: Optional[dict[str, Any]] = data.get("credentials")
        self.config: dict[str, Any] = data.get("config", {})
        self.status: str = data.get("status", "unknown")
        self.updated_at: Optional[str] = data.get("updated_at")
        self._data = data

    def __repr__(self) -> str:
        return f"RuntimeProviderSnapshot(provider={self.provider})"


class GovernanceStatus:
    """Represents governance daemon status."""

    def __init__(self, data: dict[str, Any]):
        self.daemon_reachable: bool = data.get("daemon_reachable", False)
        self.socket_reachable: bool = data.get("socket_reachable", False)
        self.policy_loaded: bool = data.get("policy_loaded", False)
        self.version: Optional[str] = data.get("version")
        self.policy_name: Optional[str] = data.get("policy_name")
        self.decisions_total: int = data.get("decisions_total", 0)
        self.permits_today: int = data.get("permits_today", 0)
        self.denies_today: int = data.get("denies_today", 0)
        self.defers_today: int = data.get("defers_today", 0)
        self.pending_approvals: int = data.get("pending_approvals", 0)
        self.status: str = data.get("status", "unknown")
        self.error: Optional[str] = data.get("error")
        self._data = data


class Runtime:
    """SDK resource for /runtime endpoints."""

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

    def get_provider_state(
        self,
        provider: str,
    ) -> RuntimeProviderSnapshot:
        """Get runtime provider snapshot."""
        self._require_sync_client()
        response = self._client.get(api_path("runtime/providers/{provider}", provider=provider))
        response.raise_for_status()
        return RuntimeProviderSnapshot(response.json())

    async def aget_provider_state(
        self,
        provider: str,
    ) -> RuntimeProviderSnapshot:
        """Get runtime provider snapshot (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("runtime/providers/{provider}", provider=provider)
        )
        response.raise_for_status()
        return RuntimeProviderSnapshot(response.json())

    def upsert_provider_state(
        self,
        provider: str,
        credentials: Optional[dict[str, Any]] = None,
        config: Optional[dict[str, Any]] = None,
    ) -> RuntimeProviderSnapshot:
        """Create or update runtime provider snapshot."""
        self._require_sync_client()
        payload: dict[str, Any] = {"provider": provider}
        if credentials:
            payload["credentials"] = credentials
        if config:
            payload["config"] = config

        response = self._client.put(
            api_path("runtime/providers/{provider}", provider=provider), json=payload
        )
        response.raise_for_status()
        return RuntimeProviderSnapshot(response.json())

    async def aupsert_provider_state(
        self,
        provider: str,
        credentials: Optional[dict[str, Any]] = None,
        config: Optional[dict[str, Any]] = None,
    ) -> RuntimeProviderSnapshot:
        """Create or update runtime provider snapshot (async)."""
        self._require_async_client()
        payload: dict[str, Any] = {"provider": provider}
        if credentials:
            payload["credentials"] = credentials
        if config:
            payload["config"] = config

        response = await self._client.put(
            api_path("runtime/providers/{provider}", provider=provider), json=payload
        )
        response.raise_for_status()
        return RuntimeProviderSnapshot(response.json())

    def get_governance_metrics(self) -> str:
        """Get governance metrics in Prometheus format."""
        self._require_sync_client()
        response = self._client.get("runtime/governance/metrics")
        response.raise_for_status()
        return response.text

    async def aget_governance_metrics(self) -> str:
        """Get governance metrics in Prometheus format (async)."""
        self._require_async_client()
        response = await self._client.get("runtime/governance/metrics")
        response.raise_for_status()
        return response.text

    def get_governance_status(self) -> GovernanceStatus:
        """Get governance daemon health and status."""
        self._require_sync_client()
        response = self._client.get("runtime/governance/status")
        response.raise_for_status()
        return GovernanceStatus(response.json())

    async def aget_governance_status(self) -> GovernanceStatus:
        """Get governance daemon health and status (async)."""
        self._require_async_client()
        response = await self._client.get("runtime/governance/status")
        response.raise_for_status()
        return GovernanceStatus(response.json())
