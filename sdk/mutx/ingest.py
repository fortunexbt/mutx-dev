"""Ingest API SDK - /ingest endpoints for agent metrics and status reporting."""

from __future__ import annotations

from typing import Any, Optional

import httpx


class Ingest:
    """SDK resource for /ingest endpoints.

    Used by agents to report status, deployment events, and metrics.
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

    def report_agent_status(
        self,
        agent_id: str,
        status: str,
        node_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> dict[str, Any]:
        """Report agent status update.

        Args:
            agent_id: The agent UUID
            status: New agent status (running, idle, error, stopped, etc.)
            node_id: Optional node ID where the agent is running
            error_message: Optional error message if status is error/failed
        """
        self._require_sync_client()
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "status": status,
        }
        if node_id:
            payload["node_id"] = node_id
        if error_message:
            payload["error_message"] = error_message

        response = self._client.post("ingest/agent-status", json=payload)
        response.raise_for_status()
        return response.json()

    async def areport_agent_status(
        self,
        agent_id: str,
        status: str,
        node_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> dict[str, Any]:
        """Report agent status update (async)."""
        self._require_async_client()
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "status": status,
        }
        if node_id:
            payload["node_id"] = node_id
        if error_message:
            payload["error_message"] = error_message

        response = await self._client.post("ingest/agent-status", json=payload)
        response.raise_for_status()
        return response.json()

    def report_deployment_event(
        self,
        deployment_id: str,
        event: str,
        status: Optional[str] = None,
        node_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> dict[str, Any]:
        """Report a deployment lifecycle event.

        Args:
            deployment_id: The deployment UUID
            event: Event type (created, starting, healthy, stopped, failed)
            status: Optional status override
            node_id: Optional node ID
            error_message: Optional error message
        """
        self._require_sync_client()
        payload: dict[str, Any] = {
            "deployment_id": deployment_id,
            "event": event,
        }
        if status:
            payload["status"] = status
        if node_id:
            payload["node_id"] = node_id
        if error_message:
            payload["error_message"] = error_message

        response = self._client.post("ingest/deployment", json=payload)
        response.raise_for_status()
        return response.json()

    async def areport_deployment_event(
        self,
        deployment_id: str,
        event: str,
        status: Optional[str] = None,
        node_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> dict[str, Any]:
        """Report a deployment lifecycle event (async)."""
        self._require_async_client()
        payload: dict[str, Any] = {
            "deployment_id": deployment_id,
            "event": event,
        }
        if status:
            payload["status"] = status
        if node_id:
            payload["node_id"] = node_id
        if error_message:
            payload["error_message"] = error_message

        response = await self._client.post("ingest/deployment", json=payload)
        response.raise_for_status()
        return response.json()

    def report_metrics(
        self,
        agent_id: str,
        cpu_usage: Optional[float] = None,
        memory_usage: Optional[float] = None,
    ) -> dict[str, Any]:
        """Report agent metrics.

        Args:
            agent_id: The agent UUID
            cpu_usage: CPU usage percentage
            memory_usage: Memory usage in MB
        """
        self._require_sync_client()
        payload: dict[str, Any] = {"agent_id": agent_id}
        if cpu_usage is not None:
            payload["cpu_usage"] = cpu_usage
        if memory_usage is not None:
            payload["memory_usage"] = memory_usage

        response = self._client.post("ingest/metrics", json=payload)
        response.raise_for_status()
        return response.json()

    async def areport_metrics(
        self,
        agent_id: str,
        cpu_usage: Optional[float] = None,
        memory_usage: Optional[float] = None,
    ) -> dict[str, Any]:
        """Report agent metrics (async)."""
        self._require_async_client()
        payload: dict[str, Any] = {"agent_id": agent_id}
        if cpu_usage is not None:
            payload["cpu_usage"] = cpu_usage
        if memory_usage is not None:
            payload["memory_usage"] = memory_usage

        response = await self._client.post("ingest/metrics", json=payload)
        response.raise_for_status()
        return response.json()
