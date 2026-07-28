from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli import faramesh_runtime
from scripts import check_faramesh_v020_compat
from src.runtime.gateways import faramesh as gateway_module


def test_release_contract_is_immutable_and_digest_pinned() -> None:
    assert check_faramesh_v020_compat.VERSION == "0.2.0"
    assert check_faramesh_v020_compat.RELEASE_REF == (
        "ae3ebc9066d65e4e930164881c2f2ce2be554c7f"
    )
    assert set(check_faramesh_v020_compat.ASSET_SHA256) == {
        "darwin-amd64",
        "darwin-arm64",
        "linux-amd64",
        "linux-arm64",
    }
    assert all(len(digest) == 64 for digest in check_faramesh_v020_compat.ASSET_SHA256.values())


def test_official_socket_environment_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAREMESH_SOCKET", "/tmp/official.sock")
    monkeypatch.setenv("FAREMESH_SOCKET_PATH", "/tmp/legacy.sock")

    assert faramesh_runtime._default_faramesh_socket_path() == "/tmp/official.sock"
    assert gateway_module._default_faramesh_socket_path() == "/tmp/official.sock"


@patch("cli.faramesh_runtime.find_faramesh_bin", return_value="/opt/bin/faramesh")
@patch("cli.faramesh_runtime.subprocess.run")
def test_version_detection_uses_published_cli_flag(mock_run: MagicMock, _mock_bin: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="0.2.0\n")

    assert faramesh_runtime.detect_faramesh_version() == "0.2.0"
    assert mock_run.call_args.args[0] == ["/opt/bin/faramesh", "--version"]


@patch("cli.faramesh_runtime.is_socket_reachable", return_value=True)
@patch("cli.faramesh_runtime._send_socket_request")
def test_gate_decide_sends_v020_govern_shape(
    mock_send: MagicMock,
    _mock_reachable: MagicMock,
) -> None:
    mock_send.return_value = [
        {"call_id": "call-1", "effect": "PERMIT", "latency_ms": 2}
    ]

    decision = faramesh_runtime.gate_decide(
        "agent-1",
        "api/read",
        {"id": 42},
        {"call_id": "call-1", "session_id": "session-1"},
        "/tmp/faramesh.sock",
    )

    assert decision.outcome == "EXECUTE"
    assert mock_send.call_args.args[1] == {
        "type": "govern",
        "call_id": "call-1",
        "agent_id": "agent-1",
        "session_id": "session-1",
        "tool_id": "api/read",
        "args": {"id": 42},
    }


@patch("cli.faramesh_runtime._send_socket_request")
def test_approval_and_kill_operations_match_v020_socket_contract(mock_send: MagicMock) -> None:
    mock_send.return_value = [{"ok": True}]

    assert faramesh_runtime.approve_defer("/tmp/faramesh.sock", "defer-1") is True
    approve_request = mock_send.call_args.args[1]
    assert approve_request == {
        "type": "approve_defer",
        "defer_token": "defer-1",
        "approved": True,
        "reason": "approved via MUTX",
    }

    assert faramesh_runtime.deny_defer("/tmp/faramesh.sock", "defer-1") is True
    assert mock_send.call_args.args[1]["approved"] is False

    assert faramesh_runtime.kill_agent(
        "/tmp/faramesh.sock", "agent-1", admin_token="secret"
    ) is True
    assert mock_send.call_args.args[1] == {
        "type": "kill",
        "agent_id": "agent-1",
        "admin_token": "secret",
    }


@patch("cli.faramesh_runtime._send_socket_request")
def test_wait_for_decision_polls_defer_status_directly(mock_send: MagicMock) -> None:
    mock_send.return_value = [{"defer_token": "defer-1", "status": "approved"}]

    result = faramesh_runtime.wait_for_decision(
        "defer-1",
        timeout=1,
        socket_path="/tmp/faramesh.sock",
        agent_id="agent-1",
    )

    assert result.status == "approved"
    assert result.executed is True
    assert mock_send.call_args.args[1] == {
        "type": "poll_defer",
        "agent_id": "agent-1",
        "defer_token": "defer-1",
    }


@pytest.mark.asyncio
async def test_gateway_uses_govern_and_approval_contracts() -> None:
    gateway = gateway_module.FarameshGateway("/tmp/faramesh.sock")
    with (
        patch.object(gateway, "_check_socket", return_value=True),
        patch.object(gateway, "_check_daemon", return_value=True),
        patch.object(
            gateway_module,
            "_send_socket_request",
            side_effect=[
                [{"call_id": "call-1", "effect": "DENY", "latency_ms": 3}],
                [{"ok": True}],
                [{"ok": True}],
            ],
        ) as send,
    ):
        response = await gateway.evaluate_action(
            tool_id="shell/run",
            agent_id="agent-1",
            session_id="session-1",
            tool_args={"cmd": "rm -rf /"},
        )
        approved = await gateway.approve("defer-1")
        denied = await gateway.deny("defer-2", "unsafe")

    assert response is not None and response.effect == "DENY"
    govern_request = send.call_args_list[0].args[1]
    assert govern_request["type"] == "govern"
    assert govern_request["args"] == {"cmd": "rm -rf /"}
    assert "call_id" in govern_request
    assert approved is True
    assert denied is True
    assert send.call_args_list[1].args[1]["type"] == "approve_defer"
    assert send.call_args_list[1].args[1]["approved"] is True
    assert send.call_args_list[2].args[1]["approved"] is False


def test_gateway_normalizes_v020_pending_token() -> None:
    gateway = gateway_module.FarameshGateway("/tmp/faramesh.sock")
    with patch(
        "src.runtime.gateways.faramesh._send_socket_request",
        return_value=[{"items": [{"token": "defer-1", "agent_id": "agent-1"}]}],
    ):
        pending = gateway.get_pending_approvals()

    assert pending == [
        {"token": "defer-1", "defer_token": "defer-1", "agent_id": "agent-1"}
    ]


def test_bundled_policies_retain_v020_compatible_constructs() -> None:
    policies = Path(__file__).resolve().parents[1] / "cli" / "policies"
    customer_support = (policies / "customer-support.fpl").read_text()
    payment = (policies / "payment-bot.fpl").read_text()

    assert "scope read_customer get_order search_kb send_email issue_credit" in customer_support
    assert 'args_array_len("recipients")' in customer_support
    assert 'history_tool_count("stripe/refund") > 20' in payment
    assert "session.sum(" not in payment
    assert len(list(policies.glob("*.fpl"))) == 4
