"""Security API SDK - /security capability and AARM-alignment endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx

from mutx._http import api_path


class ActionEvaluateResponse:
    """Response from action evaluation."""

    def __init__(self, data: dict[str, Any]):
        self.decision: str = data["decision"]
        self.rule_id: Optional[str] = data.get("rule_id")
        self.rule_name: Optional[str] = data.get("rule_name")
        self.reason: str = data["reason"]
        self.would_modify: bool = data.get("would_modify", False)
        self.evaluation_id: str = data["evaluation_id"]
        self.receipt_id: str = data["receipt_id"]
        self.action_id: str = data["action_id"]
        self.action_hash: str = data["action_hash"]
        self._data = data


class ApprovalRequest:
    """Represents an approval request."""

    def __init__(self, data: dict[str, Any]):
        self.request_id: str = data["request_id"]
        self.owner_id: UUID = UUID(data["owner_id"])
        reviewer_id = data["reviewer_id"]
        self.reviewer_id: Optional[UUID] = UUID(reviewer_id) if reviewer_id else None
        self.can_resolve: bool = data["can_resolve"]
        self.status: str = data["status"]
        self.tool_name: str = data["tool_name"]
        self.reason: str = data.get("reason", "")
        self.created_at: datetime = datetime.fromisoformat(data["created_at"])
        self.expires_at: datetime = datetime.fromisoformat(data["expires_at"])
        self.remaining_seconds: int = data["remaining_seconds"]
        self._data = data

    def __repr__(self) -> str:
        return f"ApprovalRequest(id={self.request_id}, status={self.status})"


class GovernanceMetrics:
    """Governance metrics response."""

    def __init__(self, data: dict[str, Any]):
        self.total_evaluations: int = data["total_evaluations"]
        self.permits: int = data["permits"]
        self.denials: int = data["denials"]
        self.defers: int = data["defers"]
        self.pending_approvals: int = data["pending_approvals"]
        self.intent_drifts: int = data.get("intent_drifts", 0)
        self.active_sessions: int = data.get("active_sessions", 0)
        self.avg_latency_ms: float = data.get("avg_latency_ms", 0.0)
        self.decisions_per_minute: int = data.get("decisions_per_minute", 0)
        self.decisions_per_hour: int = data.get("decisions_per_hour", 0)
        self._data = data


class Security:
    """SDK resource for runtime-security and AARM-alignment endpoints."""

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

    def evaluate_action(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        agent_id: str,
        session_id: str,
        trigger: str = "manual",
        runtime: str = "mutx",
    ) -> ActionEvaluateResponse:
        """Evaluate an action against policy without executing.

        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            agent_id: Agent ID
            session_id: Session ID
            trigger: What triggered this action
            runtime: Runtime identifier
        """
        self._require_sync_client()
        response = self._client.post(
            "security/actions/evaluate",
            json={
                "tool_name": tool_name,
                "tool_args": tool_args,
                "agent_id": agent_id,
                "session_id": session_id,
                "trigger": trigger,
                "runtime": runtime,
            },
        )
        response.raise_for_status()
        return ActionEvaluateResponse(response.json())

    async def aevaluate_action(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        agent_id: str,
        session_id: str,
        trigger: str = "manual",
        runtime: str = "mutx",
    ) -> ActionEvaluateResponse:
        """Evaluate an action against policy (async)."""
        self._require_async_client()
        response = await self._client.post(
            "security/actions/evaluate",
            json={
                "tool_name": tool_name,
                "tool_args": tool_args,
                "agent_id": agent_id,
                "session_id": session_id,
                "trigger": trigger,
                "runtime": runtime,
            },
        )
        response.raise_for_status()
        return ActionEvaluateResponse(response.json())

    def request_approval(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        agent_id: str,
        session_id: str,
        reason: str = "",
        timeout_minutes: int = 5,
        reviewer_id: str | UUID | None = None,
    ) -> ApprovalRequest:
        """Request human approval for a deferred action."""
        self._require_sync_client()
        payload = {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "agent_id": agent_id,
            "session_id": session_id,
            "reason": reason,
            "timeout_minutes": timeout_minutes,
        }
        if reviewer_id is not None:
            payload["reviewer_id"] = str(reviewer_id)
        response = self._client.post(
            "security/approvals/request",
            json=payload,
        )
        response.raise_for_status()
        return ApprovalRequest(response.json())

    async def arequest_approval(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        agent_id: str,
        session_id: str,
        reason: str = "",
        timeout_minutes: int = 5,
        reviewer_id: str | UUID | None = None,
    ) -> ApprovalRequest:
        """Request human approval (async)."""
        self._require_async_client()
        payload = {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "agent_id": agent_id,
            "session_id": session_id,
            "reason": reason,
            "timeout_minutes": timeout_minutes,
        }
        if reviewer_id is not None:
            payload["reviewer_id"] = str(reviewer_id)
        response = await self._client.post(
            "security/approvals/request",
            json=payload,
        )
        response.raise_for_status()
        return ApprovalRequest(response.json())

    def get_approval(
        self,
        request_id: str,
    ) -> ApprovalRequest:
        """Get the status of an approval request."""
        self._require_sync_client()
        response = self._client.get(
            api_path("security/approvals/{request_id}", request_id=request_id)
        )
        response.raise_for_status()
        return ApprovalRequest(response.json())

    async def aget_approval(
        self,
        request_id: str,
    ) -> ApprovalRequest:
        """Get the status of an approval request (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("security/approvals/{request_id}", request_id=request_id)
        )
        response.raise_for_status()
        return ApprovalRequest(response.json())

    def list_pending_approvals(self) -> list[ApprovalRequest]:
        """List all pending approval requests."""
        self._require_sync_client()
        response = self._client.get("security/approvals")
        response.raise_for_status()
        return [ApprovalRequest(d) for d in response.json()]

    async def alist_pending_approvals(self) -> list[ApprovalRequest]:
        """List all pending approval requests (async)."""
        self._require_async_client()
        response = await self._client.get("security/approvals")
        response.raise_for_status()
        return [ApprovalRequest(d) for d in response.json()]

    def approve(
        self,
        request_id: str,
        comment: str = "",
    ) -> dict[str, Any]:
        """Approve a pending request."""
        self._require_sync_client()
        response = self._client.post(
            api_path("security/approvals/{request_id}/approve", request_id=request_id),
            json={"comment": comment},
        )
        response.raise_for_status()
        return response.json()

    async def aapprove(
        self,
        request_id: str,
        comment: str = "",
    ) -> dict[str, Any]:
        """Approve a pending request (async)."""
        self._require_async_client()
        response = await self._client.post(
            api_path("security/approvals/{request_id}/approve", request_id=request_id),
            json={"comment": comment},
        )
        response.raise_for_status()
        return response.json()

    def deny(
        self,
        request_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Deny a pending request."""
        self._require_sync_client()
        response = self._client.post(
            api_path("security/approvals/{request_id}/deny", request_id=request_id),
            json={"comment": reason},
        )
        response.raise_for_status()
        return response.json()

    async def adeny(
        self,
        request_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Deny a pending request (async)."""
        self._require_async_client()
        response = await self._client.post(
            api_path("security/approvals/{request_id}/deny", request_id=request_id),
            json={"comment": reason},
        )
        response.raise_for_status()
        return response.json()

    def get_receipt(
        self,
        receipt_id: str,
    ) -> dict[str, Any]:
        """Get a receipt by ID."""
        self._require_sync_client()
        response = self._client.get(
            api_path("security/receipts/{receipt_id}", receipt_id=receipt_id)
        )
        response.raise_for_status()
        return response.json()

    async def aget_receipt(
        self,
        receipt_id: str,
    ) -> dict[str, Any]:
        """Get a receipt by ID (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("security/receipts/{receipt_id}", receipt_id=receipt_id)
        )
        response.raise_for_status()
        return response.json()

    def get_session_receipts(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get receipts for a session."""
        self._require_sync_client()
        response = self._client.get(
            api_path("security/receipts/session/{session_id}", session_id=session_id),
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return response.json()

    async def aget_session_receipts(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get receipts for a session (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("security/receipts/session/{session_id}", session_id=session_id),
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return response.json()

    def run_compliance_check(self) -> dict[str, Any]:
        """Run the local AARM-alignment gap check (not conformance)."""
        self._require_sync_client()
        response = self._client.get("security/compliance")
        response.raise_for_status()
        return response.json()

    async def arun_compliance_check(self) -> dict[str, Any]:
        """Run the local AARM-alignment gap check asynchronously."""
        self._require_async_client()
        response = await self._client.get("security/compliance")
        response.raise_for_status()
        return response.json()

    def get_metrics(self) -> GovernanceMetrics:
        """Get governance metrics."""
        self._require_sync_client()
        response = self._client.get("security/metrics")
        response.raise_for_status()
        return GovernanceMetrics(response.json())

    async def aget_metrics(self) -> GovernanceMetrics:
        """Get governance metrics (async)."""
        self._require_async_client()
        response = await self._client.get("security/metrics")
        response.raise_for_status()
        return GovernanceMetrics(response.json())

    def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        self._require_sync_client()
        response = self._client.get("security/metrics/prometheus")
        response.raise_for_status()
        return response.text

    async def aget_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus format (async)."""
        self._require_async_client()
        response = await self._client.get("security/metrics/prometheus")
        response.raise_for_status()
        return response.text

    def create_session(
        self,
        session_id: str,
        agent_id: str,
        original_request: str = "",
        stated_intent: str = "",
    ) -> dict[str, Any]:
        """Create a new session context for security tracking."""
        self._require_sync_client()
        response = self._client.post(
            "security/sessions",
            params={
                "session_id": session_id,
                "agent_id": agent_id,
                "original_request": original_request,
                "stated_intent": stated_intent,
            },
        )
        response.raise_for_status()
        return response.json()

    async def acreate_session(
        self,
        session_id: str,
        agent_id: str,
        original_request: str = "",
        stated_intent: str = "",
    ) -> dict[str, Any]:
        """Create a new session context (async)."""
        self._require_async_client()
        response = await self._client.post(
            "security/sessions",
            params={
                "session_id": session_id,
                "agent_id": agent_id,
                "original_request": original_request,
                "stated_intent": stated_intent,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """Get session context."""
        self._require_sync_client()
        response = self._client.get(
            api_path("security/sessions/{session_id}", session_id=session_id)
        )
        response.raise_for_status()
        return response.json()

    async def aget_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """Get session context (async)."""
        self._require_async_client()
        response = await self._client.get(
            api_path("security/sessions/{session_id}", session_id=session_id)
        )
        response.raise_for_status()
        return response.json()

    def close_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """Close a session."""
        self._require_sync_client()
        response = self._client.delete(
            api_path("security/sessions/{session_id}", session_id=session_id)
        )
        response.raise_for_status()
        return response.json()

    async def aclose_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """Close a session (async)."""
        self._require_async_client()
        response = await self._client.delete(
            api_path("security/sessions/{session_id}", session_id=session_id)
        )
        response.raise_for_status()
        return response.json()
