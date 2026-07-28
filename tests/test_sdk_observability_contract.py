"""Contract tests for sdk/mutx/observability.py."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from sdk.mutx.observability import Observability, _build_run_from_steps
from tests.sdk_contract_utils import assert_v1_request


def _run_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "agent_id": "agent-001",
        "status": "running",
        "started_at": "2026-04-03T01:00:00+00:00",
        "steps": [
            {
                "type": "reasoning",
                "started_at": "2026-04-03T01:00:00+00:00",
                "content": "thinking...",
            }
        ],
        "cost": {"input_tokens": 100, "output_tokens": 200},
        "provenance": {"run_hash": "abc123"},
        "runtime": "mutx",
        "trigger": "manual",
    }
    payload.update(overrides)
    return payload


def _step_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "type": "tool_call",
        "started_at": "2026-04-03T01:00:05+00:00",
        "name": "http_request",
        "input": {"url": "https://api.example.com"},
    }
    payload.update(overrides)
    return payload


def _eval_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "run_id": "550e8400-e29b-41d4-a716-446655440000",
        "pass": True,
        "score": 92.5,
        "task_type": "question_answering",
        "eval_layer": "automated",
    }
    payload.update(overrides)
    return payload


def _provenance_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "run_id": "550e8400-e29b-41d4-a716-446655440000",
        "run_hash": "abc123def456",
        "runtime": "mutx",
        "agent_id": "agent-001",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Type guard: sync methods require httpx.Client
# ---------------------------------------------------------------------------


class TestObservabilitySyncClientGuard:
    def test_report_run_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        obs = Observability(mock_client)
        with pytest.raises(TypeError, match="only available on MutxClient"):
            obs.report_run(_run_payload())

    def test_list_runs_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        obs = Observability(mock_client)
        with pytest.raises(TypeError, match="only available on MutxClient"):
            obs.list_runs()

    def test_get_run_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        obs = Observability(mock_client)
        with pytest.raises(TypeError, match="only available on MutxClient"):
            obs.get_run("run-id")

    def test_add_steps_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        obs = Observability(mock_client)
        with pytest.raises(TypeError, match="only available on MutxClient"):
            obs.add_steps("run-id", [_step_payload()])

    def test_get_eval_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        obs = Observability(mock_client)
        with pytest.raises(TypeError, match="only available on MutxClient"):
            obs.get_eval("run-id")

    def test_submit_eval_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        obs = Observability(mock_client)
        with pytest.raises(TypeError, match="only available on MutxClient"):
            obs.submit_eval("run-id", _eval_payload())

    def test_get_provenance_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        obs = Observability(mock_client)
        with pytest.raises(TypeError, match="only available on MutxClient"):
            obs.get_provenance("run-id")

    def test_update_status_raises_on_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        obs = Observability(mock_client)
        with pytest.raises(TypeError, match="only available on MutxClient"):
            obs.update_status("run-id")


# ---------------------------------------------------------------------------
# Sync methods - report_run
# ---------------------------------------------------------------------------


class TestObservabilityReportRun:
    def test_report_run_success(self):
        returned = _run_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        obs = Observability(mock_client)

        result = obs.report_run(_run_payload())

        assert result == returned
        request = assert_v1_request(mock_client.post, "POST", "/v1/observability/runs")
        assert json.loads(request.content) == _run_payload()
        mock_response.raise_for_status.assert_called_once()

    def test_report_run_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        obs = Observability(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            obs.report_run(_run_payload())


# ---------------------------------------------------------------------------
# Sync methods - list_runs
# ---------------------------------------------------------------------------


class TestObservabilityListRuns:
    def test_list_runs_defaults(self):
        payload = {"items": [], "total": 0, "skip": 0, "limit": 50}
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = obs.list_runs()

        assert result == payload
        request = assert_v1_request(mock_client.get, "GET", "/v1/observability/runs")
        assert dict(request.url.params) == {"skip": "0", "limit": "50"}
        mock_response.raise_for_status.assert_called_once()

    def test_list_runs_with_all_filters(self):
        payload = {"items": [_run_payload()], "total": 1, "skip": 10, "limit": 20}
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = obs.list_runs(
            skip=10, limit=20, agent_id="agent-x", status="failed", runtime="mutx", trigger="cron"
        )

        assert result == payload
        request = assert_v1_request(mock_client.get, "GET", "/v1/observability/runs")
        assert dict(request.url.params) == {
            "skip": "10",
            "limit": "20",
            "agent_id": "agent-x",
            "status": "failed",
            "runtime": "mutx",
            "trigger": "cron",
        }

    def test_list_runs_partial_filters(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"items": [], "total": 0}
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        obs.list_runs(agent_id="agent-only", status="completed")

        request = assert_v1_request(mock_client.get, "GET", "/v1/observability/runs")
        assert dict(request.url.params) == {
            "skip": "0",
            "limit": "50",
            "agent_id": "agent-only",
            "status": "completed",
        }

    def test_list_runs_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503", request=MagicMock(), response=MagicMock(status_code=503)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            obs.list_runs()


# ---------------------------------------------------------------------------
# Sync methods - get_run
# ---------------------------------------------------------------------------


class TestObservabilityGetRun:
    def test_get_run_success(self):
        payload = _run_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = obs.get_run("run-123")

        assert result == payload
        assert_v1_request(mock_client.get, "GET", "/v1/observability/runs/run-123")
        mock_response.raise_for_status.assert_called_once()

    def test_get_run_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            obs.get_run("run-404")


# ---------------------------------------------------------------------------
# Sync methods - add_steps
# ---------------------------------------------------------------------------


class TestObservabilityAddSteps:
    def test_add_steps_success(self):
        payload = {"added": 2, "run_id": "run-abc"}
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        obs = Observability(mock_client)
        steps = [_step_payload(), _step_payload(type="tool_result")]

        result = obs.add_steps("run-abc", steps)

        assert result == payload
        request = assert_v1_request(
            mock_client.post,
            "POST",
            "/v1/observability/runs/run-abc/steps",
        )
        assert json.loads(request.content) == steps
        mock_response.raise_for_status.assert_called_once()

    def test_add_steps_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "422", request=MagicMock(), response=MagicMock(status_code=422)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        obs = Observability(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            obs.add_steps("run-bad", [_step_payload()])


# ---------------------------------------------------------------------------
# Sync methods - get_eval
# ---------------------------------------------------------------------------


class TestObservabilityGetEval:
    def test_get_eval_success(self):
        payload = _eval_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = obs.get_eval("run-eval-001")

        assert result == payload
        assert_v1_request(
            mock_client.get,
            "GET",
            "/v1/observability/runs/run-eval-001/eval",
        )
        mock_response.raise_for_status.assert_called_once()

    def test_get_eval_not_found_returns_none(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = obs.get_eval("run-no-eval")

        assert result is None

    def test_get_eval_other_error_raises(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            obs.get_eval("run-err")


# ---------------------------------------------------------------------------
# Sync methods - submit_eval
# ---------------------------------------------------------------------------


class TestObservabilitySubmitEval:
    def test_submit_eval_success(self):
        payload = _eval_payload(score=85.0)
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        obs = Observability(mock_client)

        result = obs.submit_eval("run-submit", {"pass": True, "score": 85.0})

        assert result == payload
        request = assert_v1_request(
            mock_client.post,
            "POST",
            "/v1/observability/runs/run-submit/eval",
        )
        assert json.loads(request.content) == {"pass": True, "score": 85.0}
        mock_response.raise_for_status.assert_called_once()

    def test_submit_eval_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "422", request=MagicMock(), response=MagicMock(status_code=422)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        obs = Observability(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            obs.submit_eval("run-eval", {"pass": False, "score": 0.0})


# ---------------------------------------------------------------------------
# Sync methods - get_provenance
# ---------------------------------------------------------------------------


class TestObservabilityGetProvenance:
    def test_get_provenance_success(self):
        payload = _provenance_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = obs.get_provenance("run-prov-001")

        assert result == payload
        assert_v1_request(
            mock_client.get,
            "GET",
            "/v1/observability/runs/run-prov-001/provenance",
        )
        mock_response.raise_for_status.assert_called_once()

    def test_get_provenance_not_found_returns_none(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = obs.get_provenance("run-no-prov")

        assert result is None

    def test_get_provenance_other_error_raises(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            obs.get_provenance("run-err")


# ---------------------------------------------------------------------------
# Sync methods - update_status
# ---------------------------------------------------------------------------


class TestObservabilityUpdateStatus:
    def test_update_status_full(self):
        payload = {"run_id": "run-upd", "status": "completed", "outcome": "success"}
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.patch.return_value = mock_response
        obs = Observability(mock_client)

        result = obs.update_status(
            run_id="run-upd",
            status="completed",
            outcome="success",
            ended_at="2026-04-03T02:00:00+00:00",
            duration_ms=3600000,
            error=None,
        )

        assert result == payload
        request = assert_v1_request(
            mock_client.patch,
            "PATCH",
            "/v1/observability/runs/run-upd/status",
        )
        assert json.loads(request.content) == {
            "status": "completed",
            "outcome": "success",
            "ended_at": "2026-04-03T02:00:00+00:00",
            "duration_ms": 3600000,
        }
        mock_response.raise_for_status.assert_called_once()

    def test_update_status_partial(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"run_id": "run-partial", "status": "running"}
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.patch.return_value = mock_response
        obs = Observability(mock_client)

        obs.update_status(run_id="run-partial", status="running")

        request = assert_v1_request(
            mock_client.patch,
            "PATCH",
            "/v1/observability/runs/run-partial/status",
        )
        assert json.loads(request.content) == {"status": "running"}

    def test_update_status_empty_payload(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"run_id": "run-empty"}
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.patch.return_value = mock_response
        obs = Observability(mock_client)

        obs.update_status(run_id="run-empty")

        request = assert_v1_request(
            mock_client.patch,
            "PATCH",
            "/v1/observability/runs/run-empty/status",
        )
        assert json.loads(request.content) == {}

    def test_update_status_error_field(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"run_id": "run-err", "status": "failed", "error": "oops"}
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.patch.return_value = mock_response
        obs = Observability(mock_client)

        obs.update_status(run_id="run-err", status="failed", error="oops")

        request = assert_v1_request(
            mock_client.patch,
            "PATCH",
            "/v1/observability/runs/run-err/status",
        )
        assert json.loads(request.content) == {"status": "failed", "error": "oops"}

    def test_update_status_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.patch.return_value = mock_response
        obs = Observability(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            obs.update_status(run_id="run-500", status="failed")


# ---------------------------------------------------------------------------
# Async methods
# ---------------------------------------------------------------------------


class TestObservabilityAsyncMethods:
    @pytest.mark.asyncio
    async def test_areport_run_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = _run_payload()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        obs = Observability(mock_client)

        result = await obs.areport_run(_run_payload())

        assert result["id"] == "550e8400-e29b-41d4-a716-446655440000"
        mock_client.post.assert_called_once()
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_alist_runs_success(self):
        payload = {"items": [], "total": 0, "skip": 0, "limit": 50}
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = await obs.alist_runs(agent_id="async-agent")

        assert result == payload
        request = assert_v1_request(mock_client.get, "GET", "/v1/observability/runs")
        assert dict(request.url.params) == {
            "skip": "0",
            "limit": "50",
            "agent_id": "async-agent",
        }

    @pytest.mark.asyncio
    async def test_aget_run_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = _run_payload()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = await obs.aget_run("async-run")

        assert result["id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert_v1_request(mock_client.get, "GET", "/v1/observability/runs/async-run")

    @pytest.mark.asyncio
    async def test_aadd_steps_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"added": 1}
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        obs = Observability(mock_client)

        result = await obs.aadd_steps("async-run", [_step_payload()])

        assert result["added"] == 1
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_eval_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = _eval_payload()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = await obs.aget_eval("async-eval")

        assert result["pass"] is True
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_eval_not_found(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = await obs.aget_eval("async-no-eval")

        assert result is None

    @pytest.mark.asyncio
    async def test_asubmit_eval_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = _eval_payload(score=100.0)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        obs = Observability(mock_client)

        result = await obs.asubmit_eval("async-eval", {"pass": True, "score": 100.0})

        assert result["score"] == 100.0
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_provenance_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = _provenance_payload()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = await obs.aget_provenance("async-prov")

        assert result["run_hash"] == "abc123def456"
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_provenance_not_found(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        obs = Observability(mock_client)

        result = await obs.aget_provenance("async-no-prov")

        assert result is None

    @pytest.mark.asyncio
    async def test_aupdate_status_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"run_id": "async-upd", "status": "completed"}
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.patch.return_value = mock_response
        obs = Observability(mock_client)

        result = await obs.aupdate_status("async-upd", status="completed", duration_ms=5000)

        assert result["status"] == "completed"
        mock_client.patch.assert_called_once()


# ---------------------------------------------------------------------------
# _build_run_from_steps helper
# ---------------------------------------------------------------------------


class TestBuildRunFromSteps:
    def test_required_fields(self):
        steps = [{"type": "reasoning", "started_at": "2026-04-03T01:00:00+00:00"}]
        cost = {"input_tokens": 10, "output_tokens": 20}
        result = _build_run_from_steps(agent_id="my-agent", steps=steps, cost=cost)

        assert result["agent_id"] == "my-agent"
        assert result["steps"] == steps
        assert result["cost"] == cost
        assert result["status"] == "completed"
        assert result["runtime"] == "mutx"
        assert result["trigger"] == "manual"
        assert "id" in result
        assert "started_at" in result
        assert "provenance" in result
        assert "run_hash" in result["provenance"]

    def test_custom_status(self):
        steps = [_step_payload()]
        cost = {"input_tokens": 1, "output_tokens": 1}
        result = _build_run_from_steps(
            agent_id="agent-y",
            steps=steps,
            cost=cost,
            status="failed",
            runtime="custom-runtime",
            trigger="cron",
        )

        assert result["status"] == "failed"
        assert result["runtime"] == "custom-runtime"
        assert result["trigger"] == "cron"

    def test_metadata_included(self):
        steps = [_step_payload()]
        cost = {"input_tokens": 1, "output_tokens": 1}
        metadata = {"user": "tester", "version": "v1"}
        result = _build_run_from_steps(
            agent_id="agent-z",
            steps=steps,
            cost=cost,
            metadata=metadata,
        )

        assert result["metadata"] == metadata

    def test_provenance_contains_sha256_hash(self):
        steps = [_step_payload()]
        cost = {"input_tokens": 5, "output_tokens": 5}
        result = _build_run_from_steps(
            agent_id="agent-hash",
            steps=steps,
            cost=cost,
            runtime="test",
            trigger="agent",
        )

        prov = result["provenance"]
        assert "run_hash" in prov
        assert isinstance(prov["run_hash"], str)
        assert len(prov["run_hash"]) == 64  # SHA-256 hex = 64 chars

    def test_id_is_uuid_format(self):
        steps = [_step_payload()]
        cost = {"input_tokens": 1, "output_tokens": 1}
        result = _build_run_from_steps(agent_id="agent-uuid", steps=steps, cost=cost)

        # UUID v7 format: 36 chars with hyphens
        assert len(result["id"]) == 36
        assert result["id"].count("-") == 4
