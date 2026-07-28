"""Approvals API SDK - /v1/approvals endpoints (Prompt 7 human-in-the-loop workflows)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx

from mutx._http import api_path
from mutx.pagination import Page, parse_page


class ApprovalRequest:
    """Represents an approval request returned by the API.

    Attributes:
        id: Unique identifier for the approval request.
        owner_id: Authenticated owner that created the request.
        reviewer_id: Explicit reviewer assignment, if any.
        can_resolve: Server-computed resolution capability for the current caller.
        agent_id: ID of the agent that triggered the approval.
        session_id: ID of the session during which the approval was requested.
        action_type: Type of action requiring approval (e.g. "deploy", "delete").
        payload: Arbitrary context payload passed when creating the request.
        status: Current status — PENDING, APPROVED, REJECTED, or EXPIRED.
        requester: Email of the user who submitted the request.
        approver: Email of the user who approved or rejected (None if pending).
        created_at: Timestamp when the request was created.
        resolved_at: Timestamp when the request was resolved (None if pending).
        comment: Optional comment from the approver.
    """

    def __init__(self, data: dict[str, Any]):
        self.id: UUID = UUID(data["id"])
        self.owner_id: UUID = UUID(data["owner_id"])
        reviewer_id = data["reviewer_id"]
        self.reviewer_id: Optional[UUID] = UUID(reviewer_id) if reviewer_id else None
        self.can_resolve: bool = data["can_resolve"]
        self.agent_id: str = data["agent_id"]
        self.session_id: str = data["session_id"]
        self.action_type: str = data["action_type"]
        self.payload: dict[str, Any] = data.get("payload", {})
        self.status: str = data["status"]
        self.requester: str = data["requester"]
        self.approver: Optional[str] = data.get("approver")
        self.created_at: datetime = datetime.fromisoformat(data["created_at"])
        self.resolved_at: Optional[datetime] = (
            datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None
        )
        self.comment: Optional[str] = data.get("comment")
        self._data = data

    def __repr__(self) -> str:
        return (
            f"ApprovalRequest(id={self.id}, agent_id={self.agent_id!r}, "
            f"action_type={self.action_type!r}, status={self.status!r})"
        )


class EligibleReviewer:
    """A discoverable active user eligible for explicit assignment."""

    def __init__(self, data: dict[str, Any]):
        self.id: UUID = UUID(data["id"])
        self.email: str = data["email"]
        self.name: str = data["name"]
        self.roles: list[str] = list(data.get("roles", []))
        self._data = data

    def __repr__(self) -> str:
        return f"EligibleReviewer(id={self.id}, email={self.email!r})"


class Approvals:
    """SDK resource for /v1/approvals endpoints.

    Supports both sync and async clients. Async methods are prefixed with ``a``.

    Example (sync)::

        >>> client = MutxClient(api_key="...")
        >>> req = client.approvals.create(
        ...     agent_id="agent-123",
        ...     session_id="session-456",
        ...     action_type="deploy",
        ...     payload={"target": "production"},
        ... )
        >>> print(req.status)
        PENDING

    Example (async)::

        >>> import httpx
        >>> async_client = httpx.AsyncClient(
        ...     base_url="https://api.mutx.dev/v1",
        ...     headers={"Authorization": "Bearer ..."},
        ... )
        >>> approvals = Approvals(async_client)
        >>> req = await approvals.acreate(
        ...     agent_id="agent-123",
        ...     session_id="session-456",
        ...     action_type="deploy",
        ...     payload={"target": "production"},
        ... )
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

    # ------------------------------------------------------------------
    # Sync methods
    # ------------------------------------------------------------------

    def create(
        self,
        agent_id: str,
        session_id: str,
        action_type: str,
        payload: Optional[dict[str, Any]] = None,
        reviewer_id: str | UUID | None = None,
        idempotency_key: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Submit a new approval request (sync).

        Returns the created ``ApprovalRequest`` in ``PENDING`` status.
        """
        self._require_sync_client()
        request_body = {
            "agent_id": agent_id,
            "session_id": session_id,
            "action_type": action_type,
            "payload": payload or {},
        }
        if reviewer_id is not None:
            request_body["reviewer_id"] = str(reviewer_id)
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key is not None else None
        response = self._client.post("approvals", json=request_body, headers=headers)
        response.raise_for_status()
        return ApprovalRequest(response.json())

    def get(self, request_id: str) -> ApprovalRequest:
        """Fetch a single approval request by ID."""
        self._require_sync_client()
        response = self._client.get(api_path("approvals/{request_id}", request_id=request_id))
        response.raise_for_status()
        return ApprovalRequest(response.json())

    def list_reviewers(self) -> list[EligibleReviewer]:
        """List active users eligible for reviewer assignment."""
        self._require_sync_client()
        response = self._client.get("approvals/reviewers")
        response.raise_for_status()
        return [EligibleReviewer(item) for item in response.json()]

    def list(
        self,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Page[ApprovalRequest]:
        """
        List approval requests.

        Args:
            status: Filter by status (e.g. "PENDING", "APPROVED").
            agent_id: Filter by agent ID.
            skip: Number of records to skip.
            limit: Maximum number of records to return.
        """
        self._require_sync_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if status is not None:
            params["status"] = status
        if agent_id is not None:
            params["agent_id"] = agent_id

        response = self._client.get("approvals", params=params)
        response.raise_for_status()
        return parse_page(
            response.json(),
            ApprovalRequest,
            requested_skip=skip,
            requested_limit=limit,
        )

    def approve(
        self,
        request_id: str,
        comment: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Approve a pending request (sync).

        Requires the authenticated user to have DEVELOPER or ADMIN role.
        """
        self._require_sync_client()
        response = self._client.post(
            api_path("approvals/{request_id}/approve", request_id=request_id),
            json={"comment": comment},
        )
        response.raise_for_status()
        return ApprovalRequest(response.json())

    def reject(
        self,
        request_id: str,
        comment: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Reject a pending request (sync).

        Requires the authenticated user to have DEVELOPER or ADMIN role.
        """
        self._require_sync_client()
        response = self._client.post(
            api_path("approvals/{request_id}/reject", request_id=request_id),
            json={"comment": comment},
        )
        response.raise_for_status()
        return ApprovalRequest(response.json())

    # ------------------------------------------------------------------
    # Async methods
    # ------------------------------------------------------------------

    async def acreate(
        self,
        agent_id: str,
        session_id: str,
        action_type: str,
        payload: Optional[dict[str, Any]] = None,
        reviewer_id: str | UUID | None = None,
        idempotency_key: Optional[str] = None,
    ) -> ApprovalRequest:
        """Submit a new approval request (async)."""
        self._require_async_client()
        request_body = {
            "agent_id": agent_id,
            "session_id": session_id,
            "action_type": action_type,
            "payload": payload or {},
        }
        if reviewer_id is not None:
            request_body["reviewer_id"] = str(reviewer_id)
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key is not None else None
        response = await self._client.post("approvals", json=request_body, headers=headers)
        response.raise_for_status()
        return ApprovalRequest(response.json())

    async def aget(self, request_id: str) -> ApprovalRequest:
        """Fetch a single approval request by ID (async)."""
        self._require_async_client()
        response = await self._client.get(api_path("approvals/{request_id}", request_id=request_id))
        response.raise_for_status()
        return ApprovalRequest(response.json())

    async def alist_reviewers(self) -> list[EligibleReviewer]:
        """List active users eligible for reviewer assignment (async)."""
        self._require_async_client()
        response = await self._client.get("approvals/reviewers")
        response.raise_for_status()
        return [EligibleReviewer(item) for item in response.json()]

    async def alist(
        self,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Page[ApprovalRequest]:
        """List approval requests (async)."""
        self._require_async_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if status is not None:
            params["status"] = status
        if agent_id is not None:
            params["agent_id"] = agent_id

        response = await self._client.get("approvals", params=params)
        response.raise_for_status()
        return parse_page(
            response.json(),
            ApprovalRequest,
            requested_skip=skip,
            requested_limit=limit,
        )

    async def aapprove(
        self,
        request_id: str,
        comment: Optional[str] = None,
    ) -> ApprovalRequest:
        """Approve a pending request (async)."""
        self._require_async_client()
        response = await self._client.post(
            api_path("approvals/{request_id}/approve", request_id=request_id),
            json={"comment": comment},
        )
        response.raise_for_status()
        return ApprovalRequest(response.json())

    async def areject(
        self,
        request_id: str,
        comment: Optional[str] = None,
    ) -> ApprovalRequest:
        """Reject a pending request (async)."""
        self._require_async_client()
        response = await self._client.post(
            api_path("approvals/{request_id}/reject", request_id=request_id),
            json={"comment": comment},
        )
        response.raise_for_status()
        return ApprovalRequest(response.json())
