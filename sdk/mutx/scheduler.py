"""Scheduler API SDK for the mounted ``/v1/scheduler`` endpoints."""

from __future__ import annotations

from typing import Any

import httpx

from mutx._http import api_path


class SchedulerTask:
    """Represents a scheduled task."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.enabled: bool = data["enabled"]
        self.schedule: str = data.get("schedule")
        self.last_run: int = data.get("last_run")
        self.next_run: int = data.get("next_run")
        self._data = data

    def __repr__(self) -> str:
        return f"SchedulerTask(id={self.id}, name={self.name}, enabled={self.enabled})"


class Scheduler:
    """SDK resource for scheduler status and manual task triggers."""

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

    def get_status(self) -> dict[str, Any]:
        """Get scheduler status. Admin role required.

        Raises:
            httpx.HTTPStatusError: If the scheduler request fails.
        """
        self._require_sync_client()
        response = self._client.get("scheduler")
        response.raise_for_status()
        return response.json()

    async def aget_status(self) -> dict[str, Any]:
        """Get scheduler status (async)."""
        self._require_async_client()
        response = await self._client.get("scheduler")
        response.raise_for_status()
        return response.json()

    def trigger_task(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        """Manually trigger a scheduled task. Admin role required.

        Args:
            task_id: The ID of the task to trigger

        Raises:
            httpx.HTTPStatusError: If the trigger request fails.
        """
        self._require_sync_client()
        response = self._client.post(api_path("scheduler/{task_id}/trigger", task_id=task_id))
        response.raise_for_status()
        return response.json()

    async def atrigger_task(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        """Manually trigger a scheduled task (async)."""
        self._require_async_client()
        response = await self._client.post(api_path("scheduler/{task_id}/trigger", task_id=task_id))
        response.raise_for_status()
        return response.json()
