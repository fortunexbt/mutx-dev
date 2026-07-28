"""Compatibility resource for the currently unmounted newsletter router."""

from __future__ import annotations

from typing import Any, NoReturn

import httpx


class Newsletter:
    """Compatibility resource retained while newsletter is absent from public ``/v1``."""

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

    @staticmethod
    def _unavailable() -> NoReturn:
        raise RuntimeError("Newsletter endpoints are not available in the mounted public /v1 API.")

    def get_count(self) -> int:
        """Get the total waitlist signup count."""
        self._require_sync_client()
        self._unavailable()

    async def acount(self) -> int:
        """Get the total waitlist signup count (async)."""
        self._require_async_client()
        self._unavailable()

    def signup(
        self,
        email: str,
        source: str = "coming-soon",
    ) -> dict[str, Any]:
        """Submit a waitlist signup.

        Args:
            email: Email address to subscribe
            source: Signup source (e.g. "coming-soon", "website")

        Returns:
            Dict with 'message' and 'duplicate' fields
        """
        self._require_sync_client()
        self._unavailable()

    async def asignup(
        self,
        email: str,
        source: str = "coming-soon",
    ) -> dict[str, Any]:
        """Submit a waitlist signup (async)."""
        self._require_async_client()
        self._unavailable()
