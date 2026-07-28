"""Contract tests for mutx.security SDK module."""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from mutx.security import (
    ActionEvaluateResponse,
    ApprovalRequest,
    GovernanceMetrics,
    Security,
)


# ---------------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------------


def _action_evaluate_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "decision": "permit",
        "rule_id": "rule-42",
        "rule_name": "allow-all",
        "reason": "Policy allows this action.",
        "would_modify": False,
        "evaluation_id": str(uuid.uuid4()),
        "receipt_id": str(uuid.uuid4()),
        "action_id": str(uuid.uuid4()),
        "action_hash": "abc123",
    }
    payload.update(overrides)
    return payload


def _approval_request_payload(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    payload = {
        "request_id": str(uuid.uuid4()),
        "owner_id": str(uuid.uuid4()),
        "reviewer_id": str(uuid.uuid4()),
        "can_resolve": True,
        "status": "pending",
        "tool_name": "http_request",
        "reason": "Test approval",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "remaining_seconds": 300,
    }
    payload.update(overrides)
    return payload


def _governance_metrics_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "total_evaluations": 100,
        "permits": 80,
        "denials": 10,
        "defers": 10,
        "pending_approvals": 3,
        "intent_drifts": 2,
        "active_sessions": 5,
        "avg_latency_ms": 12.5,
        "decisions_per_minute": 15,
        "decisions_per_hour": 900,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Client helper
# ---------------------------------------------------------------------------


def _make_client(handler) -> httpx.Client:
    return httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# Response model tests
# ---------------------------------------------------------------------------


def test_action_evaluate_response_parsable() -> None:
    payload = _action_evaluate_payload()
    resp = ActionEvaluateResponse(payload)

    assert resp.decision == "permit"
    assert resp.rule_id == "rule-42"
    assert resp.rule_name == "allow-all"
    assert resp.reason == "Policy allows this action."
    assert resp.would_modify is False
    assert resp.evaluation_id == payload["evaluation_id"]
    assert resp.receipt_id == payload["receipt_id"]
    assert resp.action_id == payload["action_id"]
    assert resp.action_hash == "abc123"
    assert resp._data == payload


def test_action_evaluate_response_optional_fields_missing() -> None:
    payload = {
        "decision": "deny",
        "reason": "Blocked.",
        "evaluation_id": str(uuid.uuid4()),
        "receipt_id": str(uuid.uuid4()),
        "action_id": str(uuid.uuid4()),
        "action_hash": "xyz",
    }
    resp = ActionEvaluateResponse(payload)

    assert resp.decision == "deny"
    assert resp.rule_id is None
    assert resp.rule_name is None
    assert resp.would_modify is False


def test_approval_request_parsable() -> None:
    payload = _approval_request_payload()
    req = ApprovalRequest(payload)

    assert req.request_id == payload["request_id"]
    assert req.owner_id == uuid.UUID(payload["owner_id"])
    assert req.reviewer_id == uuid.UUID(payload["reviewer_id"])
    assert req.can_resolve is True
    assert req.status == "pending"
    assert req.tool_name == "http_request"
    assert isinstance(req.created_at, datetime)
    assert isinstance(req.expires_at, datetime)
    assert req.remaining_seconds == 300
    assert req._data == payload


def test_approval_request_repr() -> None:
    payload = _approval_request_payload()
    req = ApprovalRequest(payload)
    assert f"id={req.request_id}" in repr(req)
    assert "status=pending" in repr(req)


def test_governance_metrics_parsable() -> None:
    payload = _governance_metrics_payload()
    metrics = GovernanceMetrics(payload)

    assert metrics.total_evaluations == 100
    assert metrics.permits == 80
    assert metrics.denials == 10
    assert metrics.defers == 10
    assert metrics.pending_approvals == 3
    assert metrics.intent_drifts == 2
    assert metrics.active_sessions == 5
    assert metrics.avg_latency_ms == 12.5
    assert metrics.decisions_per_minute == 15
    assert metrics.decisions_per_hour == 900


def test_governance_metrics_optional_fields_missing() -> None:
    payload = {
        "total_evaluations": 0,
        "permits": 0,
        "denials": 0,
        "defers": 0,
        "pending_approvals": 0,
    }
    metrics = GovernanceMetrics(payload)

    assert metrics.intent_drifts == 0
    assert metrics.active_sessions == 0
    assert metrics.avg_latency_ms == 0.0
    assert metrics.decisions_per_minute == 0
    assert metrics.decisions_per_hour == 0


# ---------------------------------------------------------------------------
# Security resource: route + return-type contract tests (sync only)
# ---------------------------------------------------------------------------


def test_evaluate_action_uses_correct_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_action_evaluate_payload())

    sec = Security(_make_client(handler))

    result = sec.evaluate_action(
        tool_name="http_request",
        tool_args={"url": "https://example.com"},
        agent_id="agent-1",
        session_id="sess-1",
        trigger="manual",
        runtime="mutx",
    )

    assert captured["path"] == "/v1/security/actions/evaluate"
    assert captured["json"]["tool_name"] == "http_request"
    assert captured["json"]["agent_id"] == "agent-1"
    assert captured["json"]["session_id"] == "sess-1"
    assert "user_id" not in captured["json"]
    assert isinstance(result, ActionEvaluateResponse)


def test_evaluate_action_raises_on_async_client() -> None:
    import asyncio

    async_client = httpx.AsyncClient(base_url="https://api.test/v1/")
    sec = Security(async_client)

    try:
        sec.evaluate_action(
            tool_name="http_request",
            tool_args={},
            agent_id="agent-1",
            session_id="sess-1",
        )
    except RuntimeError as e:
        assert "sync" in str(e).lower()
    finally:
        asyncio.run(async_client.aclose())


def test_request_approval_uses_correct_route() -> None:
    captured: dict[str, Any] = {}
    reviewer_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_approval_request_payload())

    sec = Security(_make_client(handler))

    result = sec.request_approval(
        tool_name="http_request",
        tool_args={"url": "https://example.com"},
        agent_id="agent-1",
        session_id="sess-1",
        reason="Need approval",
        timeout_minutes=10,
        reviewer_id=reviewer_id,
    )

    assert captured["path"] == "/v1/security/approvals/request"
    assert captured["json"]["tool_name"] == "http_request"
    assert captured["json"]["reason"] == "Need approval"
    assert captured["json"]["timeout_minutes"] == 10
    assert captured["json"]["reviewer_id"] == str(reviewer_id)
    assert "user_id" not in captured["json"]
    assert isinstance(result, ApprovalRequest)


def test_get_approval_uses_correct_route() -> None:
    captured: dict[str, Any] = {}
    request_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_approval_request_payload(request_id=request_id))

    sec = Security(_make_client(handler))
    result = sec.get_approval(request_id=request_id)

    assert captured["path"] == f"/v1/security/approvals/{request_id}"
    assert isinstance(result, ApprovalRequest)


def test_list_pending_approvals_uses_correct_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=[_approval_request_payload(), _approval_request_payload()])

    sec = Security(_make_client(handler))
    result = sec.list_pending_approvals()

    assert captured["path"] == "/v1/security/approvals"
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(r, ApprovalRequest) for r in result)


def test_approve_uses_correct_route_and_body() -> None:
    captured: dict[str, Any] = {}
    request_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "approved"})

    sec = Security(_make_client(handler))
    result = sec.approve(request_id=request_id, comment="Looks fine")

    assert captured["path"] == f"/v1/security/approvals/{request_id}/approve"
    assert "reviewer" not in captured["json"]
    assert captured["json"]["comment"] == "Looks fine"
    assert isinstance(result, dict)


def test_deny_uses_correct_route_and_body() -> None:
    captured: dict[str, Any] = {}
    request_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "denied"})

    sec = Security(_make_client(handler))
    result = sec.deny(request_id=request_id, reason="Not safe")

    assert captured["path"] == f"/v1/security/approvals/{request_id}/deny"
    assert captured["json"]["comment"] == "Not safe"
    assert isinstance(result, dict)


def test_get_receipt_uses_correct_route() -> None:
    captured: dict[str, Any] = {}
    receipt_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"receipt_id": receipt_id, "status": "logged"})

    sec = Security(_make_client(handler))
    result = sec.get_receipt(receipt_id=receipt_id)

    assert captured["path"] == f"/v1/security/receipts/{receipt_id}"
    assert isinstance(result, dict)


def test_get_session_receipts_uses_correct_route_and_params() -> None:
    captured: dict[str, Any] = {}
    session_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"receipts": []})

    sec = Security(_make_client(handler))
    result = sec.get_session_receipts(session_id=session_id, limit=50, offset=10)

    assert captured["path"] == f"/v1/security/receipts/session/{session_id}"
    assert captured["params"] == {"limit": "50", "offset": "10"}
    assert isinstance(result, dict)


def test_run_compliance_check_uses_correct_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"compliant": True, "checks": []})

    sec = Security(_make_client(handler))
    result = sec.run_compliance_check()

    assert captured["path"] == "/v1/security/compliance"
    assert isinstance(result, dict)


def test_get_metrics_uses_correct_route_and_returns_governance_metrics() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_governance_metrics_payload())

    sec = Security(_make_client(handler))
    result = sec.get_metrics()

    assert captured["path"] == "/v1/security/metrics"
    assert isinstance(result, GovernanceMetrics)


def test_get_prometheus_metrics_uses_correct_route_and_returns_text() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, text="metric_a 42\nmetric_b 7\n")

    sec = Security(_make_client(handler))
    result = sec.get_prometheus_metrics()

    assert captured["path"] == "/v1/security/metrics/prometheus"
    assert isinstance(result, str)
    assert "metric_a" in result


def test_create_session_uses_correct_route_and_params() -> None:
    captured: dict[str, Any] = {}
    session_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"session_id": session_id, "status": "active"})

    sec = Security(_make_client(handler))
    result = sec.create_session(
        session_id=session_id,
        agent_id=agent_id,
        original_request="test request",
        stated_intent="test intent",
    )

    assert captured["path"] == "/v1/security/sessions"
    assert captured["params"]["session_id"] == session_id
    assert captured["params"]["agent_id"] == agent_id
    assert captured["params"]["original_request"] == "test request"
    assert "user_id" not in captured["params"]
    assert isinstance(result, dict)


def test_get_session_uses_correct_route() -> None:
    captured: dict[str, Any] = {}
    session_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"session_id": session_id, "status": "active"})

    sec = Security(_make_client(handler))
    result = sec.get_session(session_id=session_id)

    assert captured["path"] == f"/v1/security/sessions/{session_id}"
    assert isinstance(result, dict)


def test_close_session_uses_correct_route() -> None:
    captured: dict[str, Any] = {}
    session_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"session_id": session_id, "status": "closed"})

    sec = Security(_make_client(handler))
    result = sec.close_session(session_id=session_id)

    assert captured["path"] == f"/v1/security/sessions/{session_id}"
    assert captured["method"] == "DELETE"
    assert isinstance(result, dict)


def test_identity_fields_absent_from_sync_and_async_sdk_contracts() -> None:
    for method_name in (
        "evaluate_action",
        "aevaluate_action",
        "request_approval",
        "arequest_approval",
        "create_session",
        "acreate_session",
    ):
        assert "user_id" not in inspect.signature(getattr(Security, method_name)).parameters
    for method_name in ("approve", "aapprove", "deny", "adeny"):
        assert "reviewer" not in inspect.signature(getattr(Security, method_name)).parameters


def test_async_security_writes_derive_identity_from_authentication() -> None:
    captured: list[tuple[str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        captured.append((request.url.path, body))
        if request.url.path.endswith("/actions/evaluate"):
            return httpx.Response(200, json=_action_evaluate_payload())
        if request.url.path.endswith("/approvals/request"):
            return httpx.Response(201, json=_approval_request_payload())
        return httpx.Response(200, json={"status": "ok"})

    async def exercise() -> None:
        async with httpx.AsyncClient(
            base_url="https://api.test/v1/",
            transport=httpx.MockTransport(handler),
        ) as http:
            security = Security(http)
            await security.aevaluate_action("tool", {}, "agent-id", "session-id")
            await security.arequest_approval("tool", {}, "agent-id", "session-id")
            request_id = str(uuid.uuid4())
            await security.aapprove(request_id, comment="approved")
            await security.adeny(request_id, reason="denied")
            await security.acreate_session("session-id", "agent-id")

    asyncio.run(exercise())

    assert captured
    assert all("user_id" not in body for _, body in captured)
    assert all("reviewer" not in body for _, body in captured)
