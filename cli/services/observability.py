"""
Observability and Security API service for CLI and TUI.

Provides access to MUTX Observability Schema (MutxRun, MutxStep, etc.)
and AARM-alignment security capabilities (evaluations, approvals, receipts, gap checks).
"""

from __future__ import annotations

from typing import Any

from cli.services.base import APIService


class ObservabilityService(APIService):
    """Service for MUTX Observability API."""

    def list_runs(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        skip: int = 0,
        runtime: str | None = None,
        trigger: str | None = None,
    ) -> list[dict[str, Any]]:
        """List agent runs with optional filters."""
        return self.list_runs_page(
            agent_id=agent_id,
            status=status,
            limit=limit,
            skip=skip,
            runtime=runtime,
            trigger=trigger,
        ).get("items", [])

    def list_runs_page(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        skip: int = 0,
        runtime: str | None = None,
        trigger: str | None = None,
    ) -> dict[str, Any]:
        """Return the mounted paginated run-history envelope."""
        params = {"limit": limit, "skip": skip}
        if agent_id:
            params["agent_id"] = agent_id
        if status:
            params["status"] = status
        if runtime:
            params["runtime"] = runtime
        if trigger:
            params["trigger"] = trigger

        response = self._request("GET", "/v1/observability/runs", params=params)
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Get a specific run with steps and cost."""
        response = self._request("GET", f"/v1/observability/runs/{run_id}")
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def create_run(self, run_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new agent run."""
        response = self._request("POST", "/v1/observability/runs", json=run_data)
        self._expect_status(response, {201})
        return self._decode_json(response, expected_type=dict)

    def add_steps(self, run_id: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        """Add steps to an existing run.

        Args:
            run_id: The run ID to add steps to.
            steps: List of step dicts. Each dict must have a "type" field.

        Returns:
            Dict with 'total' (total steps in run) and 'added' (steps in this batch).
        """
        response = self._request("POST", f"/v1/observability/runs/{run_id}/steps", json=steps)
        self._expect_status(response, {201})
        return self._decode_json(response, expected_type=dict)

    def update_status(self, run_id: str, status: str, **kwargs) -> dict[str, Any]:
        """Update run status."""
        data = {"status": status, **kwargs}
        response = self._request("PATCH", f"/v1/observability/runs/{run_id}/status", json=data)
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def get_eval(self, run_id: str) -> dict[str, Any] | None:
        """Get evaluation for a run."""
        response = self._request("GET", f"/v1/observability/runs/{run_id}/eval")
        if response.status_code == 404:
            return None
        self._expect_status(response, {200})
        payload = self._decode_json(response, expected_type=(dict, type(None)))
        return payload

    def submit_eval(self, run_id: str, eval_data: dict[str, Any]) -> dict[str, Any]:
        """Submit an evaluation for a run."""
        response = self._request("POST", f"/v1/observability/runs/{run_id}/eval", json=eval_data)
        self._expect_status(response, {201})
        return self._decode_json(response, expected_type=dict)

    def get_provenance(self, run_id: str) -> dict[str, Any] | None:
        """Get provenance for a run."""
        response = self._request("GET", f"/v1/observability/runs/{run_id}/provenance")
        if response.status_code == 404:
            return None
        self._expect_status(response, {200})
        payload = self._decode_json(response, expected_type=(dict, type(None)))
        return payload


class SecurityService(APIService):
    """Service for MUTX runtime-security and AARM-alignment API."""

    def evaluate_action(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        agent_id: str,
        session_id: str,
        trigger: str = "manual",
        runtime: str = "mutx",
    ) -> dict[str, Any]:
        """Evaluate an action against policy (dry-run)."""
        data = {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "agent_id": agent_id,
            "session_id": session_id,
            "trigger": trigger,
            "runtime": runtime,
        }
        response = self._request("POST", "/v1/security/actions/evaluate", json=data)
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def get_compliance_report(self) -> dict[str, Any]:
        """Run the local AARM-alignment gap check (not conformance)."""
        response = self._request("GET", "/v1/security/compliance")
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def get_metrics(self) -> dict[str, Any]:
        """Get governance metrics."""
        response = self._request("GET", "/v1/security/metrics")
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        response = self._request("GET", "/v1/security/metrics/prometheus")
        self._expect_status(response, {200})
        return response.text

    def list_approvals(self) -> list[dict[str, Any]]:
        """List pending approval requests."""
        response = self._request("GET", "/v1/security/approvals")
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=list)

    def get_approval(self, request_id: str) -> dict[str, Any]:
        """Get a specific approval request."""
        response = self._request("GET", f"/v1/security/approvals/{request_id}")
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def request_approval(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        agent_id: str,
        session_id: str,
        reason: str = "",
        reviewer_id: str | None = None,
    ) -> dict[str, Any]:
        """Request human approval for an action."""
        data = {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "agent_id": agent_id,
            "session_id": session_id,
            "reason": reason,
        }
        if reviewer_id is not None:
            data["reviewer_id"] = reviewer_id
        response = self._request("POST", "/v1/security/approvals/request", json=data)
        self._expect_status(response, {201})
        return self._decode_json(response, expected_type=dict)

    def approve_request(self, request_id: str, comment: str = "") -> dict[str, Any]:
        """Approve a pending request."""
        data = {"comment": comment}
        response = self._request("POST", f"/v1/security/approvals/{request_id}/approve", json=data)
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def deny_request(self, request_id: str, comment: str = "") -> dict[str, Any]:
        """Deny a pending request."""
        data = {"comment": comment}
        response = self._request("POST", f"/v1/security/approvals/{request_id}/deny", json=data)
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def get_receipt(self, receipt_id: str) -> dict[str, Any]:
        """Get an action receipt."""
        response = self._request("GET", f"/v1/security/receipts/{receipt_id}")
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def get_session_receipts(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get receipts for a session."""
        response = self._request(
            "GET",
            f"/v1/security/receipts/session/{session_id}",
            params={"limit": limit},
        )
        self._expect_status(response, {200})
        data = self._decode_json(response, expected_type=dict)
        return data.get("receipts", [])

    def create_session(
        self,
        session_id: str,
        agent_id: str,
        original_request: str = "",
        stated_intent: str = "",
    ) -> dict[str, Any]:
        """Create a new session context."""
        params = {
            "session_id": session_id,
            "agent_id": agent_id,
            "original_request": original_request,
            "stated_intent": stated_intent,
        }
        response = self._request("POST", "/v1/security/sessions", params=params)
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def get_session(self, session_id: str) -> dict[str, Any]:
        """Get session context."""
        response = self._request("GET", f"/v1/security/sessions/{session_id}")
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)

    def close_session(self, session_id: str) -> dict[str, Any]:
        """Close a session."""
        response = self._request("DELETE", f"/v1/security/sessions/{session_id}")
        self._expect_status(response, {200})
        return self._decode_json(response, expected_type=dict)
