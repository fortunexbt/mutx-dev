"""Contract tests for sdk/mutx/runtime.py."""

from __future__ import annotations

import json as jsonlib
from typing import Any

import httpx
import pytest

from mutx.runtime import GovernanceStatus, Runtime, RuntimeProviderSnapshot


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _provider_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "provider": "openai",
        "credentials": {"api_key": "sk-test"},
        "config": {"model": "gpt-4o"},
        "status": "active",
        "updated_at": "2026-03-12T09:00:00",
    }
    payload.update(overrides)
    return payload


def _governance_status_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "daemon_reachable": True,
        "socket_reachable": True,
        "policy_loaded": True,
        "version": "1.2.3",
        "policy_name": "default",
        "decisions_total": 42,
        "permits_today": 30,
        "denies_today": 10,
        "defers_today": 2,
        "pending_approvals": 0,
        "status": "running",
        "error": None,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# RuntimeProviderSnapshot
# ---------------------------------------------------------------------------


def test_runtime_provider_snapshot_parses_all_fields() -> None:
    raw = _provider_payload()
    snap = RuntimeProviderSnapshot(raw)

    assert snap.provider == "openai"
    assert snap.credentials == {"api_key": "sk-test"}
    assert snap.config == {"model": "gpt-4o"}
    assert snap.status == "active"
    assert snap.updated_at == "2026-03-12T09:00:00"
    assert snap._data == raw


def test_runtime_provider_snapshot_uses_defaults_when_fields_missing() -> None:
    snap = RuntimeProviderSnapshot({"provider": "anthropic"})

    assert snap.provider == "anthropic"
    assert snap.credentials is None
    assert snap.config == {}
    assert snap.status == "unknown"
    assert snap.updated_at is None


def test_runtime_provider_snapshot_repr() -> None:
    snap = RuntimeProviderSnapshot({"provider": "google"})
    assert repr(snap) == "RuntimeProviderSnapshot(provider=google)"


# ---------------------------------------------------------------------------
# GovernanceStatus
# ---------------------------------------------------------------------------


def test_governance_status_parses_all_fields() -> None:
    raw = _governance_status_payload()
    status = GovernanceStatus(raw)

    assert status.daemon_reachable is True
    assert status.socket_reachable is True
    assert status.policy_loaded is True
    assert status.version == "1.2.3"
    assert status.policy_name == "default"
    assert status.decisions_total == 42
    assert status.permits_today == 30
    assert status.denies_today == 10
    assert status.defers_today == 2
    assert status.pending_approvals == 0
    assert status.status == "running"
    assert status.error is None
    assert status._data == raw


def test_governance_status_uses_defaults_when_fields_missing() -> None:
    status = GovernanceStatus({})

    assert status.daemon_reachable is False
    assert status.socket_reachable is False
    assert status.policy_loaded is False
    assert status.version is None
    assert status.policy_name is None
    assert status.decisions_total == 0
    assert status.permits_today == 0
    assert status.denies_today == 0
    assert status.defers_today == 0
    assert status.pending_approvals == 0
    assert status.status == "unknown"
    assert status.error is None


# ---------------------------------------------------------------------------
# Runtime – sync methods
# ---------------------------------------------------------------------------


def test_get_provider_state_calls_correct_endpoint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_provider_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    runtime = Runtime(client)
    result = runtime.get_provider_state("openai")

    assert captured["path"] == "/v1/runtime/providers/openai"
    assert isinstance(result, RuntimeProviderSnapshot)
    assert result.provider == "openai"


def test_upsert_provider_state_calls_put_endpoint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = dict(jsonlib.loads(request.content.decode()))
        return httpx.Response(200, json=_provider_payload(provider="anthropic"))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    runtime = Runtime(client)
    result = runtime.upsert_provider_state(
        provider="anthropic",
        credentials={"api_key": "sk-ant"},
        config={"model": "claude-3"},
    )

    assert captured["path"] == "/v1/runtime/providers/anthropic"
    assert captured["json"]["provider"] == "anthropic"
    assert captured["json"]["credentials"] == {"api_key": "sk-ant"}
    assert captured["json"]["config"] == {"model": "claude-3"}
    assert isinstance(result, RuntimeProviderSnapshot)


def test_upsert_provider_state_omits_optional_fields_when_not_provided() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = dict(jsonlib.loads(request.content.decode()))
        return httpx.Response(200, json=_provider_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    runtime = Runtime(client)
    runtime.upsert_provider_state(provider="openai")

    assert "credentials" not in captured["json"]
    assert "config" not in captured["json"]


def test_get_governance_metrics_calls_correct_endpoint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, text="governance_metric_total 42\n")

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    runtime = Runtime(client)
    result = runtime.get_governance_metrics()

    assert captured["path"] == "/v1/runtime/governance/metrics"
    assert isinstance(result, str)
    assert "governance_metric_total" in result


def test_get_governance_status_calls_correct_endpoint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_governance_status_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    runtime = Runtime(client)
    result = runtime.get_governance_status()

    assert captured["path"] == "/v1/runtime/governance/status"
    assert isinstance(result, GovernanceStatus)
    assert result.daemon_reachable is True
    assert result.decisions_total == 42


@pytest.mark.asyncio
async def test_runtime_sync_methods_reject_async_client() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_provider_payload())

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        runtime = Runtime(client)
        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            runtime.get_provider_state("openai")
        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            runtime.upsert_provider_state("openai")
        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            runtime.get_governance_metrics()
        with pytest.raises(RuntimeError, match="sync httpx.Client"):
            runtime.get_governance_status()


# ---------------------------------------------------------------------------
# Runtime – async methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aget_provider_state_calls_correct_endpoint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_provider_payload(provider="google"))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        runtime = Runtime(client)
        result = await runtime.aget_provider_state("google")

    assert captured["path"] == "/v1/runtime/providers/google"
    assert isinstance(result, RuntimeProviderSnapshot)
    assert result.provider == "google"


@pytest.mark.asyncio
async def test_aupsert_provider_state_calls_put_endpoint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = dict(jsonlib.loads(request.content.decode()))
        return httpx.Response(200, json=_provider_payload(provider="openai"))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        runtime = Runtime(client)
        result = await runtime.aupsert_provider_state(
            provider="openai",
            credentials={"api_key": "sk-test"},
            config={"model": "gpt-4o"},
        )

    assert captured["path"] == "/v1/runtime/providers/openai"
    assert captured["json"]["credentials"] == {"api_key": "sk-test"}
    assert isinstance(result, RuntimeProviderSnapshot)


@pytest.mark.asyncio
async def test_aget_governance_metrics_calls_correct_endpoint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, text="metric_a 1\nmetric_b 2\n")

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        runtime = Runtime(client)
        result = await runtime.aget_governance_metrics()

    assert captured["path"] == "/v1/runtime/governance/metrics"
    assert isinstance(result, str)
    assert "metric_a" in result


@pytest.mark.asyncio
async def test_aget_governance_status_calls_correct_endpoint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_governance_status_payload(version="2.0.0"))

    async with httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    ) as client:
        runtime = Runtime(client)
        result = await runtime.aget_governance_status()

    assert captured["path"] == "/v1/runtime/governance/status"
    assert isinstance(result, GovernanceStatus)
    assert result.version == "2.0.0"


@pytest.mark.asyncio
async def test_runtime_async_methods_reject_sync_client() -> None:
    client = httpx.Client(base_url="https://api.test/v1/")
    runtime = Runtime(client)
    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await runtime.aget_provider_state("openai")
    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await runtime.aupsert_provider_state("openai")
    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await runtime.aget_governance_metrics()
    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await runtime.aget_governance_status()
