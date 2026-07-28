"""Governance Credentials API SDK - /governance/credentials endpoints (Credential Broker)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import httpx

from mutx._http import api_path


class CredentialBackend:
    """Represents a registered credential backend."""

    def __init__(self, data: dict[str, Any]):
        self.name: str = data["name"]
        self.backend: str = data["backend"]
        self.path: str = data["path"]
        self.ttl: int = data["ttl"]
        self.is_active: bool = data.get("is_active", True)
        self.is_healthy: bool = data.get("is_healthy", False)
        self._data = data

    def __repr__(self) -> str:
        return f"CredentialBackend(name={self.name}, backend={self.backend})"


class Credential:
    """Represents a retrieved credential."""

    def __init__(self, data: dict[str, Any]):
        self.name: str = data["name"]
        self.backend: str = data["backend"]
        self.path: str = data["path"]
        self.has_value: bool = data.get("has_value", False)
        self.expires_at: Optional[datetime] = (
            datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
        )
        self.metadata: dict[str, Any] = data.get("metadata", {})
        self._data = data


class GovernanceCredentials:
    """SDK resource for /governance/credentials endpoints (Credential Broker)."""

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

    def list_backends(self) -> list[CredentialBackend]:
        """List all registered credential backends."""
        self._require_sync_client()
        response = self._client.get("governance/credentials/backends")
        response.raise_for_status()
        return [CredentialBackend(d) for d in response.json()]

    async def alist_backends(self) -> list[CredentialBackend]:
        """List all registered credential backends (async)."""
        self._require_async_client()
        response = await self._client.get("governance/credentials/backends")
        response.raise_for_status()
        return [CredentialBackend(d) for d in response.json()]

    def register_backend(
        self,
        name: str,
        backend: str,
        path: str,
        ttl: int = 900,
        config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Register a new credential backend.

        Args:
            name: Name for this backend
            backend: Backend type (vault, awssecrets, gcpsm, azurekv, onepassword, infisical)
            path: Path/URL to the backend
            ttl: Time-to-live for cached credentials in seconds (default 900)
            config: Optional backend-specific configuration
        """
        self._require_sync_client()
        payload: dict[str, Any] = {
            "name": name,
            "backend": backend,
            "path": path,
            "ttl": ttl,
        }
        if config:
            payload["config"] = config

        response = self._client.post("governance/credentials/backends", json=payload)
        response.raise_for_status()
        return response.json()

    async def aregister_backend(
        self,
        name: str,
        backend: str,
        path: str,
        ttl: int = 900,
        config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Register a new credential backend (async)."""
        self._require_async_client()
        payload: dict[str, Any] = {
            "name": name,
            "backend": backend,
            "path": path,
            "ttl": ttl,
        }
        if config:
            payload["config"] = config

        response = await self._client.post("governance/credentials/backends", json=payload)
        response.raise_for_status()
        return response.json()

    def unregister_backend(
        self,
        backend_name: str,
    ) -> dict[str, Any]:
        """Unregister a credential backend."""
        self._require_sync_client()
        response = self._client.delete(
            api_path("governance/credentials/backends/{backend_name}", backend_name=backend_name)
        )
        response.raise_for_status()
        return response.json()

    async def aunregister_backend(
        self,
        backend_name: str,
    ) -> dict[str, Any]:
        """Unregister a credential backend (async)."""
        self._require_async_client()
        response = await self._client.delete(
            api_path("governance/credentials/backends/{backend_name}", backend_name=backend_name)
        )
        response.raise_for_status()
        return response.json()

    def check_backend_health(
        self,
        backend_name: str,
    ) -> dict[str, Any]:
        """Check health of a specific credential backend."""
        self._require_sync_client()
        response = self._client.get(
            api_path(
                "governance/credentials/backends/{backend_name}/health",
                backend_name=backend_name,
            )
        )
        response.raise_for_status()
        return response.json()

    async def acheck_backend_health(
        self,
        backend_name: str,
    ) -> dict[str, Any]:
        """Check health of a specific credential backend (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path(
                "governance/credentials/backends/{backend_name}/health",
                backend_name=backend_name,
            )
        )
        response.raise_for_status()
        return response.json()

    def health_check(self) -> dict[str, Any]:
        """Check health of all registered credential backends."""
        self._require_sync_client()
        response = self._client.get("governance/credentials/health")
        response.raise_for_status()
        return response.json()

    async def ahealth_check(self) -> dict[str, Any]:
        """Check health of all backends (async)."""
        self._require_async_client()
        response = await self._client.get("governance/credentials/health")
        response.raise_for_status()
        return response.json()

    def get_credential(
        self,
        full_path: str,
    ) -> Credential:
        """Retrieve a credential by its full path.

        Args:
            full_path: Full path in format backend:/path/to/secret
                       e.g. vault:/secret/myapp/api-key
                            awssecrets:/prod/myapp/api-key
                            gcpsm:/my-project/my-secret
        """
        self._require_sync_client()
        response = self._client.get(
            api_path(
                "governance/credentials/get/{full_path}",
                full_path=full_path,
                path_parameters={"full_path"},
            )
        )
        response.raise_for_status()
        return Credential(response.json())

    async def aget_credential(
        self,
        full_path: str,
    ) -> Credential:
        """Retrieve a credential by its full path (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path(
                "governance/credentials/get/{full_path}",
                full_path=full_path,
                path_parameters={"full_path"},
            )
        )
        response.raise_for_status()
        return Credential(response.json())
