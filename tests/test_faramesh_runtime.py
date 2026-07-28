from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cli.faramesh_runtime import (
    ActionResult,
    FAREMESH_INSTALL_REF,
    FAREMESH_INSTALL_VERSION,
    FarameshDaemonHealth,
    FarameshDecision,
    GateDecision,
    GateOutcome,
    GovernanceDecisionStatus,
    GovernanceEffect,
    _GovernanceTimeoutError,
    _GovernanceUnavailableError,
    collect_faramesh_snapshot,
    ensure_faramesh_installed,
    execute_if_allowed,
    gate_decide,
    get_daemon_status,
    get_faramesh_health,
    get_pending_defers,
    get_recent_decisions,
    is_socket_reachable,
    start_faramesh_daemon,
    submit_action,
    _count_decisions_by_effect,
)


class TestFarameshInstall:
    @patch("cli.faramesh_runtime.find_faramesh_bin")
    @patch("cli.faramesh_runtime.subprocess.run")
    def test_uses_immutable_installer_and_pinned_release(self, mock_run, mock_bin):
        mock_bin.side_effect = [None, "/home/user/.local/bin/faramesh"]
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        installed, bin_path = ensure_faramesh_installed()

        assert installed is True
        assert bin_path == "/home/user/.local/bin/faramesh"
        download_command = mock_run.call_args_list[0].args[0]
        assert FAREMESH_INSTALL_REF in download_command[2]
        install_command = mock_run.call_args_list[2].args[0]
        assert install_command[1:3] == ["--version", FAREMESH_INSTALL_VERSION]
        assert "--no-interactive" in install_command


class TestSocketReachability:
    def test_returns_false_when_socket_not_found(self, tmp_path):
        result = is_socket_reachable("/nonexistent/faramesh.sock")
        assert result is False

    @patch("cli.faramesh_runtime.os.path.exists")
    @patch("cli.faramesh_runtime.socket.socket")
    def test_returns_true_when_socket_is_reachable(self, mock_socket, mock_exists):
        mock_exists.return_value = True
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock

        result = is_socket_reachable("/tmp/faramesh.sock", timeout=0.5)

        assert result is True
        mock_sock.connect.assert_called_once()
        mock_sock.settimeout.assert_called_once_with(0.5)


class TestDecisionCounting:
    def test_counts_permit_deny_defer(self):
        decisions = [
            FarameshDecision(
                effect="PERMIT",
                agent_id="a",
                tool_id="t",
                rule_id=None,
                reason_code=None,
                defer_token=None,
                latency_ms=10,
                timestamp=None,
            ),
            FarameshDecision(
                effect="PERMIT",
                agent_id="a",
                tool_id="t",
                rule_id=None,
                reason_code=None,
                defer_token=None,
                latency_ms=10,
                timestamp=None,
            ),
            FarameshDecision(
                effect="DENY",
                agent_id="a",
                tool_id="t",
                rule_id=None,
                reason_code=None,
                defer_token=None,
                latency_ms=10,
                timestamp=None,
            ),
            FarameshDecision(
                effect="DEFER",
                agent_id="a",
                tool_id="t",
                rule_id=None,
                reason_code=None,
                defer_token=None,
                latency_ms=10,
                timestamp=None,
            ),
        ]
        permit, deny, defer = _count_decisions_by_effect(decisions)
        assert permit == 2
        assert deny == 1
        assert defer == 1

    def test_empty_list_returns_zeros(self):
        permit, deny, defer = _count_decisions_by_effect([])
        assert permit == 0
        assert deny == 0
        assert defer == 0


class TestGetDaemonStatus:
    @patch("cli.faramesh_runtime._send_socket_request")
    def test_returns_unreachable_when_no_responses(self, mock_send):
        mock_send.return_value = []

        result = get_daemon_status()

        assert result["reachable"] is False
        assert result["subscribed"] is False

    @patch("cli.faramesh_runtime._send_socket_request")
    def test_returns_subscribed_when_daemon_responds(self, mock_send):
        mock_send.return_value = [{"subscribed": True}]

        result = get_daemon_status()

        assert result["reachable"] is True
        assert result["subscribed"] is True


class TestGetRecentDecisions:
    @patch("cli.faramesh_runtime._send_socket_request")
    @patch("cli.faramesh_runtime.is_socket_reachable")
    def test_returns_empty_when_no_responses(self, mock_reachable, mock_send):
        mock_reachable.return_value = True
        mock_send.return_value = []

        decisions = get_recent_decisions(limit=10)

        assert decisions == []

    @patch("cli.faramesh_runtime._send_socket_request")
    @patch("cli.faramesh_runtime.is_socket_reachable")
    def test_parses_decision_responses(self, mock_reachable, mock_send):
        mock_reachable.return_value = True
        mock_send.return_value = [
            {
                "effect": "PERMIT",
                "agent_id": "agent1",
                "tool_id": "stripe/refund",
                "rule_id": "allow-stripe",
                "reason_code": None,
                "latency_ms": 15,
            },
            {
                "effect": "DENY",
                "agent_id": "agent1",
                "tool_id": "shell/run",
                "rule_id": "deny!",
                "reason_code": "FORBIDDEN",
                "latency_ms": 3,
            },
        ]

        decisions = get_recent_decisions(limit=10)

        assert len(decisions) == 2
        assert decisions[0].effect == "PERMIT"
        assert decisions[0].tool_id == "stripe/refund"
        assert decisions[1].effect == "DENY"
        assert decisions[1].tool_id == "shell/run"


class TestGetPendingDefers:
    @patch("cli.faramesh_runtime._send_socket_request")
    @patch("cli.faramesh_runtime.is_socket_reachable")
    def test_returns_empty_when_no_defers(self, mock_reachable, mock_send):
        mock_reachable.return_value = True
        mock_send.return_value = []

        defers = get_pending_defers()

        assert defers == []

    @patch("cli.faramesh_runtime._send_socket_request")
    @patch("cli.faramesh_runtime.is_socket_reachable")
    def test_parses_defer_responses(self, mock_reachable, mock_send):
        mock_reachable.return_value = True
        mock_send.return_value = [
            {
                "defer_token": "tok123",
                "agent_id": "agent1",
                "tool_id": "stripe/refund",
                "status": "pending",
                "reason": "high value",
            },
        ]

        defers = get_pending_defers()

        assert len(defers) == 1
        assert defers[0].defer_token == "tok123"
        assert defers[0].status == "pending"


class TestGetFarameshHealth:
    @patch("cli.faramesh_runtime.find_faramesh_bin")
    @patch("cli.faramesh_runtime.is_socket_reachable")
    def test_not_installed_when_bin_not_found(self, mock_reachable, mock_bin):
        mock_bin.return_value = None
        mock_reachable.return_value = False

        health = get_faramesh_health()

        assert health.version is None
        assert "not installed" in health.doctor_summary.lower()

    @patch("cli.faramesh_runtime.find_faramesh_bin")
    @patch("cli.faramesh_runtime.is_socket_reachable")
    @patch("cli.faramesh_runtime.detect_faramesh_version")
    def test_installed_but_stopped(self, mock_version, mock_reachable, mock_bin):
        mock_bin.return_value = "/usr/local/bin/faramesh"
        mock_version.return_value = "faramesh v1.0.0"
        mock_reachable.return_value = False

        health = get_faramesh_health()

        assert health.version == "faramesh v1.0.0"
        assert "not running" in health.doctor_summary.lower()


class TestStartFarameshDaemon:
    @patch("cli.faramesh_runtime.time.sleep")
    @patch("cli.faramesh_runtime.subprocess.Popen")
    @patch("cli.faramesh_runtime.find_faramesh_bin")
    def test_creates_socket_parent_directory(self, mock_bin, mock_popen, mock_sleep, tmp_path):
        socket_path = tmp_path / "run" / "faramesh.sock"
        proc = MagicMock()
        proc.poll.return_value = None
        mock_bin.return_value = "/usr/local/bin/faramesh"
        mock_popen.return_value = proc

        result = start_faramesh_daemon(socket_path=str(socket_path))

        assert result is proc
        assert socket_path.parent.exists()
        mock_popen.assert_called_once()
        command = mock_popen.call_args.args[0]
        assert command == [
            "/usr/local/bin/faramesh",
            "serve",
            "--socket",
            str(socket_path),
        ]


class TestCollectFarameshSnapshot:
    @patch("cli.faramesh_runtime.get_faramesh_health")
    def test_snapshot_reflects_health(self, mock_health):
        mock_health.return_value = FarameshDaemonHealth(
            daemon_reachable=False,
            socket_reachable=False,
            policy_loaded=False,
            policy_name=None,
            policy_path=None,
            decisions_total=0,
            pending_approvals=0,
            denied_today=0,
            deferred_today=0,
            uptime_seconds=None,
            version="v1.0.0",
            doctor_summary="not running",
        )

        snapshot = collect_faramesh_snapshot()

        assert snapshot.provider == "faramesh"
        assert snapshot.status in ("not_installed", "stopped", "disconnected")
        assert snapshot.version == "v1.0.0"
        assert "faramesh" in snapshot.payload.get("provider", "")

    @patch("cli.faramesh_runtime.get_faramesh_health")
    def test_snapshot_payload_has_role_governance(self, mock_health):
        mock_health.return_value = FarameshDaemonHealth(
            daemon_reachable=False,
            socket_reachable=False,
            policy_loaded=False,
            policy_name=None,
            policy_path=None,
            decisions_total=0,
            pending_approvals=0,
            denied_today=0,
            deferred_today=0,
            uptime_seconds=None,
            version="v1.0.0",
            doctor_summary="not running",
        )

        snapshot = collect_faramesh_snapshot()

        assert snapshot.payload.get("role") == "governance"


class TestFailClosedGateDecision:
    @pytest.mark.parametrize(
        ("response", "expected_status", "expected_effect"),
        [
            (
                {"effect": "DENY", "reason": "blocked", "reason_code": "policy_deny"},
                GovernanceDecisionStatus.DENIED,
                GovernanceEffect.DENY,
            ),
            (
                {"effect": "DEFER", "reason": "review", "defer_token": "defer-1"},
                GovernanceDecisionStatus.APPROVAL_REQUIRED,
                GovernanceEffect.DEFER,
            ),
            ({}, GovernanceDecisionStatus.MALFORMED, None),
            (
                {"effect": "PERMIT", "policy_loaded": False},
                GovernanceDecisionStatus.POLICY_DISABLED,
                None,
            ),
        ],
    )
    @patch("cli.faramesh_runtime._send_socket_request")
    def test_distinguishes_non_permit_responses(
        self,
        mock_send,
        response,
        expected_status,
        expected_effect,
    ):
        mock_send.return_value = [response]

        decision = gate_decide("agent-1", "openclaw/action", {"value": 1})

        assert decision.status == expected_status
        assert decision.effect == expected_effect
        assert decision.is_authoritative_permit is False
        assert decision.outcome != GateOutcome.EXECUTE

    @patch("cli.faramesh_runtime._send_socket_request")
    def test_distinguishes_no_decision(self, mock_send):
        mock_send.return_value = []

        decision = gate_decide("agent-1", "openclaw/action", {})

        assert decision.status == GovernanceDecisionStatus.NO_DECISION
        assert decision.effect is None
        assert decision.reason_code == "governance_no_decision"

    @patch("cli.faramesh_runtime._send_socket_request")
    def test_distinguishes_timeout(self, mock_send):
        mock_send.side_effect = _GovernanceTimeoutError("decision timed out")

        decision = gate_decide("agent-1", "openclaw/action", {})

        assert decision.status == GovernanceDecisionStatus.TIMEOUT
        assert decision.effect is None
        assert decision.reason == "decision timed out"

    @patch("cli.faramesh_runtime._send_socket_request")
    def test_distinguishes_unavailable(self, mock_send):
        mock_send.side_effect = _GovernanceUnavailableError("socket unavailable")

        decision = gate_decide("agent-1", "openclaw/action", {})

        assert decision.status == GovernanceDecisionStatus.UNAVAILABLE
        assert decision.effect is None
        assert decision.reason == "socket unavailable"

    @patch("cli.faramesh_runtime._send_socket_request")
    def test_authoritative_permit_preserves_receipt_and_audit_context(self, mock_send):
        response = {
            "effect": "PERMIT",
            "action_id": "action-1",
            "receipt": {"receipt_id": "receipt-1", "signature": "signed"},
            "audit_context": {"trace_id": "trace-1", "span_id": "span-1"},
        }
        mock_send.return_value = [response]

        decision = gate_decide("agent-1", "openclaw/action", {})

        assert decision.is_authoritative_permit is True
        assert decision.receipt_id == "receipt-1"
        assert decision.receipt == response["receipt"]
        assert decision.audit_context == response["audit_context"]
        assert decision.decision_payload == response


class TestExecuteIfAllowed:
    @pytest.mark.parametrize(
        "status",
        [
            GovernanceDecisionStatus.UNAVAILABLE,
            GovernanceDecisionStatus.DENIED,
            GovernanceDecisionStatus.NO_DECISION,
            GovernanceDecisionStatus.MALFORMED,
            GovernanceDecisionStatus.TIMEOUT,
            GovernanceDecisionStatus.ERROR,
        ],
    )
    @patch("cli.faramesh_runtime.gate_decide")
    def test_does_not_execute_for_non_permit_statuses(self, mock_decide, status):
        effect = GovernanceEffect.DENY if status == GovernanceDecisionStatus.DENIED else None
        mock_decide.return_value = GateDecision(
            outcome=GateOutcome.HALT,
            effect=effect,
            status=status,
            reason="blocked diagnostic",
            reason_code=f"test_{status.value}",
            authoritative=status == GovernanceDecisionStatus.DENIED,
            decision_payload={"diagnostic": status.value},
        )
        executor = MagicMock()

        result = execute_if_allowed("agent-1", "openclaw/action", {}, executor)

        executor.assert_not_called()
        assert result.executed is False
        assert result.governance_status == status
        assert result.reason == "blocked diagnostic"
        assert result.decision_payload == {"diagnostic": status.value}

    @patch("cli.faramesh_runtime.submit_action")
    @patch("cli.faramesh_runtime.gate_decide")
    def test_does_not_execute_when_approval_is_required(self, mock_decide, mock_submit):
        gate_payload = {"effect": "DEFER", "defer_token": "defer-1", "rule_id": "review"}
        mock_decide.return_value = GateDecision(
            outcome=GateOutcome.ABSTAIN,
            effect=GovernanceEffect.DEFER,
            status=GovernanceDecisionStatus.APPROVAL_REQUIRED,
            reason="human review required",
            defer_token="defer-1",
            authoritative=True,
            receipt_id="receipt-defer",
            receipt={"receipt_id": "receipt-defer"},
            audit_context={"trace_id": "trace-defer"},
            decision_payload=gate_payload,
        )
        mock_submit.return_value = ActionResult(
            status="pending_approval",
            executed=False,
            defer_token="defer-1",
            governance_status=GovernanceDecisionStatus.APPROVAL_REQUIRED,
            effect=GovernanceEffect.DEFER,
            authoritative=True,
        )
        executor = MagicMock()

        result = execute_if_allowed("agent-1", "openclaw/action", {}, executor)

        executor.assert_not_called()
        assert result.status == "pending_approval"
        assert result.governance_status == GovernanceDecisionStatus.APPROVAL_REQUIRED
        assert result.receipt_id == "receipt-defer"
        assert result.audit_context == {"trace_id": "trace-defer"}
        assert result.gate_decision_payload == gate_payload

    def test_does_not_execute_when_policy_is_disabled(self):
        executor = MagicMock()

        result = execute_if_allowed(
            "agent-1",
            "openclaw/action",
            {},
            executor,
            governance_enabled=False,
        )

        executor.assert_not_called()
        assert result.governance_status == GovernanceDecisionStatus.POLICY_DISABLED
        assert result.status == "policy_disabled"

    @patch("cli.faramesh_runtime.gate_decide")
    def test_does_not_execute_when_governance_throws(self, mock_decide):
        mock_decide.side_effect = RuntimeError("governance bridge exploded")
        executor = MagicMock()

        result = execute_if_allowed("agent-1", "openclaw/action", {}, executor)

        executor.assert_not_called()
        assert result.governance_status == GovernanceDecisionStatus.ERROR
        assert result.reason == "governance bridge exploded"
        assert result.decision_payload == {"exception_type": "RuntimeError"}

    @patch("cli.faramesh_runtime.gate_decide")
    def test_does_not_execute_non_authoritative_permit(self, mock_decide):
        mock_decide.return_value = GateDecision(
            outcome=GateOutcome.EXECUTE,
            effect=GovernanceEffect.PERMIT,
            status=GovernanceDecisionStatus.PERMITTED,
            authoritative=False,
        )
        executor = MagicMock()

        result = execute_if_allowed("agent-1", "openclaw/action", {}, executor)

        executor.assert_not_called()
        assert result.governance_status == GovernanceDecisionStatus.MALFORMED
        assert result.reason_code == "governance_non_authoritative_permit"

    @patch("cli.faramesh_runtime.gate_decide")
    def test_executes_once_for_authoritative_permit_and_preserves_context(self, mock_decide):
        decision_payload = {
            "effect": "PERMIT",
            "action_id": "action-1",
            "receipt": {"receipt_id": "receipt-1", "signature": "signed"},
            "audit_context": {"trace_id": "trace-1"},
        }
        mock_decide.return_value = GateDecision(
            outcome=GateOutcome.EXECUTE,
            effect=GovernanceEffect.PERMIT,
            status=GovernanceDecisionStatus.PERMITTED,
            authoritative=True,
            action_id="action-1",
            receipt_id="receipt-1",
            receipt=decision_payload["receipt"],
            audit_context=decision_payload["audit_context"],
            decision_payload=decision_payload,
        )
        executor = MagicMock(return_value={"ok": True})

        result = execute_if_allowed(
            "agent-1",
            "openclaw/action",
            {"value": 1},
            executor,
        )

        executor.assert_called_once_with("openclaw/action", {"value": 1})
        assert result.status == "executed"
        assert result.executed is True
        assert result.payload == {"ok": True}
        assert result.receipt_id == "receipt-1"
        assert result.receipt == decision_payload["receipt"]
        assert result.audit_context == {"trace_id": "trace-1"}
        assert result.decision_payload == decision_payload


class TestSubmitActionCompatibility:
    @pytest.mark.parametrize(
        ("response", "expected_status", "expected_governance_status", "expected_executed"),
        [
            (
                {"effect": "PERMIT", "action_id": "action-1", "payload": {"ok": True}},
                "executed",
                GovernanceDecisionStatus.PERMITTED,
                True,
            ),
            (
                {"effect": "DENY", "action_id": "action-2", "reason": "policy denied"},
                "denied",
                GovernanceDecisionStatus.DENIED,
                False,
            ),
            (
                {"effect": "DEFER", "action_id": "action-3", "defer_token": "defer-3"},
                "pending_approval",
                GovernanceDecisionStatus.APPROVAL_REQUIRED,
                False,
            ),
        ],
    )
    @patch("cli.faramesh_runtime._send_socket_request")
    def test_preserves_legitimate_action_statuses(
        self,
        mock_send,
        response,
        expected_status,
        expected_governance_status,
        expected_executed,
    ):
        mock_send.return_value = [response]

        result = submit_action("agent-1", "openclaw/action", {})

        assert result.status == expected_status
        assert result.governance_status == expected_governance_status
        assert result.executed is expected_executed
        assert result.action_id == response["action_id"]
