from __future__ import annotations

from unittest.mock import patch, MagicMock

from cli.faramesh_runtime import (
    FAREMESH_INSTALL_REF,
    FAREMESH_INSTALL_SCRIPT_SHA256,
    FAREMESH_INSTALL_VERSION,
    FarameshDaemonHealth,
    FarameshDecision,
    collect_faramesh_snapshot,
    ensure_faramesh_installed,
    get_daemon_status,
    get_faramesh_health,
    get_pending_defers,
    get_recent_decisions,
    is_socket_reachable,
    start_faramesh_daemon,
    _count_decisions_by_effect,
)


class TestFarameshInstall:
    @patch("cli.faramesh_runtime.hashlib.sha256")
    @patch("cli.faramesh_runtime.find_faramesh_bin")
    @patch("cli.faramesh_runtime.subprocess.run")
    def test_uses_immutable_installer_and_pinned_release(self, mock_run, mock_bin, mock_sha256):
        mock_bin.side_effect = [None, "/home/user/.local/bin/faramesh"]
        mock_sha256.return_value.hexdigest.return_value = FAREMESH_INSTALL_SCRIPT_SHA256
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
        mock_sha256.assert_called_once()
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

    @patch("cli.faramesh_runtime._send_socket_request")
    def test_returns_status_when_daemon_responds(self, mock_send):
        mock_send.return_value = [
            {
                "running": True,
                "policy_loaded": True,
                "policy_version": "abc123",
                "uptime_seconds": 4,
            }
        ]

        result = get_daemon_status()

        assert result["reachable"] is True
        assert result["policy_loaded"] is True
        assert mock_send.call_args.args[1] == {"type": "status"}
        assert mock_send.call_args.kwargs["timeout"] == 1.0


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
        assert mock_send.call_args.args[1] == {"type": "audit_subscribe"}


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
                "items": [
                    {
                        "defer_token": "tok123",
                        "agent_id": "agent1",
                        "tool_id": "stripe/refund",
                        "status": "pending",
                        "reason": "high value",
                    }
                ]
            }
        ]

        defers = get_pending_defers()

        assert len(defers) == 1
        assert defers[0].defer_token == "tok123"
        assert defers[0].status == "pending"
        assert mock_send.call_args.args[1] == {"type": "agent", "op": "pending"}


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
