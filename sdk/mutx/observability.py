"""
MUTX Observability SDK.

Client SDK for the MUTX Observability Schema - agent run observability.

Usage:
    from mutx import MutxClient
    client = MutxClient("your-api-key")

    # Report a run
    run = client.observability.report_run({...})

    # List runs
    run_page = client.observability.list_runs(agent_id="agent-123")
    runs = run_page["items"]

    # Submit an eval
    eval_result = client.observability.submit_eval("run-id", {...})

Based on the agent-run open standard for agent observability.
https://github.com/builderz-labs/agent-run

MIT License - Copyright (c) 2026 Builderz Labs
https://github.com/builderz-labs/agent-run/blob/9c7c3fa68413de878fae2d605c90fb334a0201f6/LICENSE

Schema adaptation only. The current upstream package is quarantined pending
maintainer security review and is not required by this module.
"""

from datetime import datetime
from typing import Optional

import httpx

from mutx._http import api_path


class Observability:
    """
    Observability resource for MUTX.

    Provides methods for reporting agent runs, tracking steps,
    and submitting evaluation results.
    """

    def __init__(self, client: httpx.Client | httpx.AsyncClient):
        self._client = client

    def _require_sync_client(self) -> None:
        if isinstance(self._client, httpx.AsyncClient):
            raise TypeError(
                "This method is only available on MutxClient (sync). "
                "Use a-prefixed methods (areport_run, alist_runs, etc.) with async client."
            )

    def _require_async_client(self) -> None:
        if not isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError(
                "This async resource helper requires an async httpx.AsyncClient "
                "and an `a*` method call."
            )

    def report_run(self, run: dict) -> dict:
        """
        Report a new agent run.

        Args:
            run: MutxRun dict with required fields:
                - id: str (UUID)
                - agent_id: str
                - status: str
                - started_at: str (ISO datetime)
                - steps: list[dict]
                - cost: dict (input_tokens, output_tokens)
                - provenance: dict (run_hash)

        Returns:
            The created MutxRun with full details including run_id
        """
        self._require_sync_client()
        response = self._client.post("observability/runs", json=run)
        response.raise_for_status()
        return response.json()

    async def areport_run(self, run: dict) -> dict:
        """
        Async version of report_run.
        """
        self._require_async_client()
        response = await self._client.post("observability/runs", json=run)
        response.raise_for_status()
        return response.json()

    def list_runs(
        self,
        skip: int = 0,
        limit: int = 50,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
        runtime: Optional[str] = None,
        trigger: Optional[str] = None,
    ) -> dict:
        """
        List agent runs with optional filters.

        Args:
            skip: Number of records to skip (pagination)
            limit: Max records to return (max 200)
            agent_id: Filter by agent ID
            status: Filter by run status (pending, running, completed, failed, etc.)
            runtime: Filter by runtime
            trigger: Filter by trigger (manual, cron, webhook, agent, pipeline, queue)

        Returns:
            dict with items (list), total, has_more, skip, limit, and filter values
        """
        self._require_sync_client()
        params = {"skip": skip, "limit": limit}
        if agent_id:
            params["agent_id"] = agent_id
        if status:
            params["status"] = status
        if runtime:
            params["runtime"] = runtime
        if trigger:
            params["trigger"] = trigger

        response = self._client.get("observability/runs", params=params)
        response.raise_for_status()
        result = response.json()
        # Backwards-compat: older servers may not include has_more
        result.setdefault("has_more", False)
        return result

    async def alist_runs(
        self,
        skip: int = 0,
        limit: int = 50,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
        runtime: Optional[str] = None,
        trigger: Optional[str] = None,
    ) -> dict:
        """
        Async version of list_runs.
        """
        self._require_async_client()
        params = {"skip": skip, "limit": limit}
        if agent_id:
            params["agent_id"] = agent_id
        if status:
            params["status"] = status
        if runtime:
            params["runtime"] = runtime
        if trigger:
            params["trigger"] = trigger

        response = await self._client.get("observability/runs", params=params)
        response.raise_for_status()
        result = response.json()
        # Backwards-compat: older servers may not include has_more
        result.setdefault("has_more", False)
        return result

    def get_run(self, run_id: str) -> dict:
        """
        Get a specific run with full step details.

        Args:
            run_id: The run ID

        Returns:
            MutxRunDetailResponse with steps array
        """
        self._require_sync_client()
        response = self._client.get(api_path("observability/runs/{run_id}", run_id=run_id))
        response.raise_for_status()
        return response.json()

    async def aget_run(self, run_id: str) -> dict:
        """
        Async version of get_run.
        """
        self._require_async_client()
        response = await self._client.get(api_path("observability/runs/{run_id}", run_id=run_id))
        response.raise_for_status()
        return response.json()

    def add_steps(self, run_id: str, steps: list[dict]) -> dict:
        """
        Add steps to an existing run.

        Args:
            run_id: The run ID to add steps to
            steps: List of step dicts with required fields:
                - type: str (reasoning, tool_call, tool_result, message, error, handoff)
                - started_at: str (ISO datetime)

        Returns:
            Summary of added steps
        """
        self._require_sync_client()
        response = self._client.post(
            api_path("observability/runs/{run_id}/steps", run_id=run_id),
            json=steps,
        )
        response.raise_for_status()
        return response.json()

    async def aadd_steps(self, run_id: str, steps: list[dict]) -> dict:
        """
        Async version of add_steps.
        """
        self._require_async_client()
        response = await self._client.post(
            api_path("observability/runs/{run_id}/steps", run_id=run_id),
            json=steps,
        )
        response.raise_for_status()
        return response.json()

    def get_eval(self, run_id: str) -> Optional[dict]:
        """
        Get the evaluation for a run.

        Args:
            run_id: The run ID

        Returns:
            MutxEval dict or None if not evaluated
        """
        self._require_sync_client()
        response = self._client.get(api_path("observability/runs/{run_id}/eval", run_id=run_id))
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def aget_eval(self, run_id: str) -> Optional[dict]:
        """
        Async version of get_eval.
        """
        self._require_async_client()
        response = await self._client.get(
            api_path("observability/runs/{run_id}/eval", run_id=run_id)
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def submit_eval(self, run_id: str, eval_data: dict) -> dict:
        """
        Submit or update an evaluation for a run.

        Args:
            run_id: The run ID to evaluate
            eval_data: Evaluation dict with required fields:
                - pass: bool
                - score: float (0-100)
                Optional:
                - task_type: str
                - eval_layer: str
                - expected_outcome: str
                - actual_outcome: str
                - metrics: dict (cost_usd, duration_s, tool_calls, etc.)
                - regression_from: str (run ID to compare against)
                - detail: str (human-readable notes)
                - benchmark_id: str

        Returns:
            The created MutxEval
        """
        self._require_sync_client()
        response = self._client.post(
            api_path("observability/runs/{run_id}/eval", run_id=run_id),
            json=eval_data,
        )
        response.raise_for_status()
        return response.json()

    async def asubmit_eval(self, run_id: str, eval_data: dict) -> dict:
        """
        Async version of submit_eval.
        """
        self._require_async_client()
        response = await self._client.post(
            api_path("observability/runs/{run_id}/eval", run_id=run_id),
            json=eval_data,
        )
        response.raise_for_status()
        return response.json()

    def get_provenance(self, run_id: str) -> Optional[dict]:
        """
        Get the provenance record for a run.

        Args:
            run_id: The run ID

        Returns:
            MutxProvenance dict or None
        """
        self._require_sync_client()
        response = self._client.get(
            api_path("observability/runs/{run_id}/provenance", run_id=run_id)
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def aget_provenance(self, run_id: str) -> Optional[dict]:
        """
        Async version of get_provenance.
        """
        self._require_async_client()
        response = await self._client.get(
            api_path("observability/runs/{run_id}/provenance", run_id=run_id)
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def update_status(
        self,
        run_id: str,
        status: Optional[str] = None,
        outcome: Optional[str] = None,
        ended_at: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> dict:
        """
        Update the status of a run.

        Args:
            run_id: The run ID
            status: New status (pending, running, completed, failed, cancelled, timeout)
            outcome: Outcome (success, failed, partial, abandoned)
            ended_at: ISO datetime when run ended
            duration_ms: Total duration in milliseconds
            error: Error message if failed

        Returns:
            Updated MutxRunResponse
        """
        self._require_sync_client()
        payload = {}
        if status:
            payload["status"] = status
        if outcome:
            payload["outcome"] = outcome
        if ended_at:
            payload["ended_at"] = ended_at
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if error:
            payload["error"] = error

        response = self._client.patch(
            api_path("observability/runs/{run_id}/status", run_id=run_id),
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def aupdate_status(
        self,
        run_id: str,
        status: Optional[str] = None,
        outcome: Optional[str] = None,
        ended_at: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> dict:
        """
        Async version of update_status.
        """
        self._require_async_client()
        payload = {}
        if status:
            payload["status"] = status
        if outcome:
            payload["outcome"] = outcome
        if ended_at:
            payload["ended_at"] = ended_at
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if error:
            payload["error"] = error

        response = await self._client.patch(
            api_path("observability/runs/{run_id}/status", run_id=run_id),
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def _build_run_from_steps(
    agent_id: str,
    steps: list[dict],
    cost: dict,
    status: str = "completed",
    runtime: str = "mutx",
    trigger: str = "manual",
    metadata: Optional[dict] = None,
) -> dict:
    """
    Helper to build a MutxRun dict from step data.

    Computes run_hash from inputs and structures the run for reporting.

    Args:
        agent_id: The agent ID
        steps: List of step dicts
        cost: Cost dict with input_tokens and output_tokens
        status: Run status
        runtime: Runtime identifier
        trigger: What triggered the run
        metadata: Additional metadata

    Returns:
        A MutxRun dict ready for report_run()
    """
    import hashlib
    import uuid
    from datetime import timezone

    run_id_factory = getattr(uuid, "uuid7", uuid.uuid4)
    run_id = str(run_id_factory())
    started_at = datetime.now(timezone.utc).isoformat()

    provenance = {
        "run_hash": hashlib.sha256(f"{agent_id}|{runtime}|{trigger}".encode()).hexdigest(),
        "runtime": runtime,
    }

    run = {
        "id": run_id,
        "agent_id": agent_id,
        "status": status,
        "started_at": started_at,
        "steps": steps,
        "cost": cost,
        "provenance": provenance,
        "runtime": runtime,
        "trigger": trigger,
    }

    if metadata:
        run["metadata"] = metadata

    return run


__all__ = [
    "Observability",
    "_build_run_from_steps",
]
