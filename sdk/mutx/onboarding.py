"""Onboarding API SDK - /onboarding endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import httpx


class OnboardingStep:
    """Represents a single onboarding step."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.status: str = data.get("status", "pending")
        self.completed_at: Optional[datetime] = (
            datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
        )
        self._data = data


class OnboardingState:
    """Represents the full onboarding state."""

    def __init__(self, data: dict[str, Any]):
        self.user_id: str = data["user_id"]
        self.provider: str = data["provider"]
        self.current_step: str = data.get("current_step", "")
        self.status: str = data.get("status", "active")
        self.steps: list[OnboardingStep] = [OnboardingStep(s) for s in data.get("steps", [])]
        self.created_at: Optional[datetime] = (
            datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        )
        self.updated_at: Optional[datetime] = (
            datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
        )
        self._data = data

    def __repr__(self) -> str:
        return f"OnboardingState(provider={self.provider}, step={self.current_step})"


class Onboarding:
    """SDK resource for /onboarding endpoints."""

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

    def get_state(
        self,
        provider: str = "openclaw",
    ) -> OnboardingState:
        """Get the current onboarding state."""
        self._require_sync_client()
        response = self._client.get("onboarding", params={"provider": provider})
        response.raise_for_status()
        return OnboardingState(response.json())

    async def aget_state(
        self,
        provider: str = "openclaw",
    ) -> OnboardingState:
        """Get the current onboarding state (async)."""
        self._require_async_client()
        response = await self._client.get("onboarding", params={"provider": provider})
        response.raise_for_status()
        return OnboardingState(response.json())

    def update(
        self,
        action: str,
        provider: str = "openclaw",
        step: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> OnboardingState:
        """Update onboarding state.

        Args:
            action: Action to perform (complete_step, skip_step, etc.)
            provider: Provider name (default: openclaw)
            step: Step ID to act upon
            payload: Optional payload data
        """
        self._require_sync_client()
        request_payload: dict[str, Any] = {
            "action": action,
            "provider": provider,
        }
        if step:
            request_payload["step"] = step
        if payload:
            request_payload["payload"] = payload

        response = self._client.post("onboarding", json=request_payload)
        response.raise_for_status()
        return OnboardingState(response.json())

    async def aupdate(
        self,
        action: str,
        provider: str = "openclaw",
        step: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> OnboardingState:
        """Update onboarding state (async)."""
        self._require_async_client()
        request_payload: dict[str, Any] = {
            "action": action,
            "provider": provider,
        }
        if step:
            request_payload["step"] = step
        if payload:
            request_payload["payload"] = payload

        response = await self._client.post("onboarding", json=request_payload)
        response.raise_for_status()
        return OnboardingState(response.json())
