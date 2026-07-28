"""
Faramesh Gateway - MUTX integration with Faramesh.

Use Faramesh as an AARM-aligned policy enforcement backend.
Faramesh provides deterministic policy evaluation via FPL (Faramesh Policy Language).

https://github.com/faramesh/faramesh-core

Faramesh integration provides:
- Deterministic FPL policy evaluation
- Pre-execution blocking of tool calls
- Human approval (DEFER) workflows
- Credential broker for API key management
- Cryptographic decision audit trail

Faramesh Core current main and FPL current main are Apache-2.0. The pinned
Faramesh Core v0.2.0 release and historical v1.2.9 tag are MPL-2.0; honor the
license at the exact installed ref.
https://github.com/faramesh/faramesh-core/blob/01476cfb8bcbce83c199df3497af746a46318f8f/LICENSE
https://github.com/faramesh/faramesh-core/blob/v0.2.0/LICENSE
https://github.com/faramesh/faramesh-core/blob/v1.2.9/LICENSE
"""

import json
import logging
import os
from pathlib import Path
import socket
import time
import uuid
from dataclasses import dataclass, field

from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


FAREMESH_DEFAULT_DAEMON_PORT = 7777
FAREMESH_INSTALL_REF = "ae3ebc9066d65e4e930164881c2f2ce2be554c7f"
FAREMESH_INSTALL_VERSION = "0.2.0"
FAREMESH_INSTALL_URL = (
    f"https://raw.githubusercontent.com/faramesh/faramesh-core/{FAREMESH_INSTALL_REF}/install.sh"
)


def _default_faramesh_socket_path() -> str:
    configured_path = os.environ.get("FAREMESH_SOCKET") or os.environ.get(
        "FAREMESH_SOCKET_PATH"
    )
    if configured_path:
        return configured_path

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return str(Path(runtime_dir).expanduser() / "faramesh.sock")

    return str(Path.home() / ".mutx" / "run" / "faramesh.sock")


FAREMESH_SOCKET_PATH = _default_faramesh_socket_path()


class FarameshDecision(str, Enum):
    """Faramesh decision effects."""

    PERMIT = "PERMIT"
    DENY = "DENY"
    DEFER = "DEFER"


@dataclass
class FarameshAction:
    """Action to submit to Faramesh for evaluation."""

    tool_id: str
    agent_id: str
    session_id: str
    tool_args: dict[str, Any] = field(default_factory=dict)
    input_preview: Optional[str] = None


@dataclass
class FarameshResponse:
    """Response from Faramesh daemon."""

    effect: str
    tool_id: str
    agent_id: str
    rule_id: Optional[str] = None
    reason: str = ""
    latency_ms: Optional[int] = None
    defer_token: Optional[str] = None
    timestamp: Optional[str] = None

    @property
    def decision(self) -> FarameshDecision:
        return FarameshDecision(self.effect)


@dataclass
class FarameshHealth:
    """Faramesh daemon health status."""

    socket_reachable: bool = False
    daemon_reachable: bool = False
    version: Optional[str] = None
    policy_name: Optional[str] = None
    decisions_total: int = 0
    denied_today: int = 0
    deferred_today: int = 0
    pending_approvals: int = 0


def _send_socket_request(socket_path: str, request: dict, timeout: float = 5.0) -> list[dict]:
    """Send a request to the Faramesh Unix socket."""
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(socket_path)

        sock.sendall((json.dumps(request) + "\n").encode())
        sock.shutdown(socket.SHUT_WR)

        response_data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_data += chunk

        if not response_data:
            return []

        try:
            responses = []
            for line in response_data.decode().splitlines():
                if line.strip():
                    responses.append(json.loads(line))
            return responses
        except json.JSONDecodeError:
            return [{"raw": response_data.decode()}]

    except (socket.error, socket.timeout, ConnectionRefusedError) as e:
        logger.debug(f"Faramesh socket error: {e}")
        return []
    finally:
        if sock is not None:
            sock.close()


class FarameshGateway:
    """
    Faramesh as an AARM-aligned policy enforcement backend.

    The FarameshGateway wraps the Faramesh daemon to provide
    Faramesh-backed governance for MUTX; this does not establish AARM conformance.

    Usage:
        gateway = FarameshGateway()

        # Evaluate an action
        result = await gateway.evaluate_action(
            tool_id="send_email",
            agent_id="agent-123",
            session_id="session-456",
            tool_args={"to": "user@example.com"},
        )

        if result.decision == FarameshDecision.PERMIT:
            execute(action)
        elif result.decision == FarameshDecision.DENY:
            blocked()
        elif result.decision == FarameshDecision.DEFER:
            await request_approval(result.defer_token)
    """

    def __init__(
        self,
        socket_path: str = FAREMESH_SOCKET_PATH,
        daemon_port: int = FAREMESH_DEFAULT_DAEMON_PORT,
    ):
        self._socket_path = socket_path
        self._daemon_port = daemon_port
        self._installed = False
        self._version: Optional[str] = None

    @property
    def is_available(self) -> bool:
        """Check if Faramesh daemon is available."""
        return self._check_socket() and self._check_daemon()

    def _check_socket(self) -> bool:
        """Check if socket file exists."""
        sock: socket.socket | None = None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect(self._socket_path)
            return True
        except (socket.error, ConnectionRefusedError):
            return False
        finally:
            if sock is not None:
                sock.close()

    def _check_daemon(self) -> bool:
        """Check if daemon is responding."""
        responses = _send_socket_request(self._socket_path, {"type": "status"}, timeout=1.0)
        return any(
            isinstance(response, dict)
            and not response.get("error")
            and response.get("running") is True
            for response in responses
        )

    def get_health(self) -> FarameshHealth:
        """Get Faramesh daemon health status."""
        health = FarameshHealth()

        health.socket_reachable = self._check_socket()

        if health.socket_reachable:
            responses = _send_socket_request(
                self._socket_path,
                {"type": "status"},
                timeout=2.0,
            )

            for resp in responses:
                if not isinstance(resp, dict) or resp.get("error"):
                    continue
                health.daemon_reachable = resp.get("running") is True
                health.policy_name = resp.get("policy_version")

            if health.daemon_reachable:
                health.pending_approvals = len(self.get_pending_approvals())

        return health

    async def evaluate_action(
        self,
        tool_id: str,
        agent_id: str,
        session_id: str,
        tool_args: Optional[dict[str, Any]] = None,
    ) -> Optional[FarameshResponse]:
        """
        Evaluate an action through Faramesh.

        Args:
            tool_id: Name/ID of the tool being called
            agent_id: Agent making the call
            session_id: Session context
            tool_args: Tool arguments

        Returns:
            FarameshResponse with decision or None if unavailable
        """
        if not self.is_available:
            logger.warning("Faramesh daemon not available")
            return None

        action = FarameshAction(
            tool_id=tool_id,
            agent_id=agent_id,
            session_id=session_id,
            tool_args=tool_args or {},
        )

        request = {
            "type": "govern",
            "call_id": str(uuid.uuid4()),
            "tool_id": action.tool_id,
            "agent_id": action.agent_id,
            "session_id": action.session_id,
            "args": action.tool_args,
        }

        start_time = time.time()
        responses = _send_socket_request(self._socket_path, request, timeout=5.0)
        latency_ms = int((time.time() - start_time) * 1000)

        for resp in responses:
            if isinstance(resp, dict) and resp.get("effect"):
                return FarameshResponse(
                    effect=resp.get("effect", "DENY"),
                    tool_id=resp.get("tool_id", tool_id),
                    agent_id=resp.get("agent_id", agent_id),
                    rule_id=resp.get("rule_id"),
                    reason=(
                        resp.get("reason")
                        or (
                            resp.get("structured_denial", {}).get("reason", "")
                            if isinstance(resp.get("structured_denial"), dict)
                            else ""
                        )
                    ),
                    latency_ms=resp.get("latency_ms", latency_ms),
                    defer_token=resp.get("defer_token"),
                    timestamp=resp.get("timestamp"),
                )

        return None

    async def approve(self, defer_token: str) -> bool:
        """
        Approve a deferred action.

        Args:
            defer_token: Token from DEFER response

        Returns:
            True if approved successfully
        """
        request = {
            "type": "approve_defer",
            "defer_token": defer_token,
            "approved": True,
            "reason": "approved via MUTX",
        }

        responses = _send_socket_request(self._socket_path, request, timeout=5.0)

        for resp in responses:
            if isinstance(resp, dict):
                return resp.get("ok") is True

        return False

    async def deny(self, defer_token: str, reason: str = "") -> bool:
        """
        Deny a deferred action.

        Args:
            defer_token: Token from DEFER response
            reason: Reason for denial

        Returns:
            True if denied successfully
        """
        request = {
            "type": "approve_defer",
            "defer_token": defer_token,
            "approved": False,
            "reason": reason,
        }

        responses = _send_socket_request(self._socket_path, request, timeout=5.0)

        for resp in responses:
            if isinstance(resp, dict):
                return resp.get("ok") is True

        return False

    def get_recent_decisions(self, limit: int = 50) -> list[FarameshResponse]:
        """
        Get recent governance decisions.

        Args:
            limit: Maximum number of decisions to return

        Returns:
            List of recent FarameshResponse objects
        """
        request = {
            "type": "audit_subscribe",
        }

        responses = _send_socket_request(self._socket_path, request, timeout=5.0)

        decisions = []
        for resp in responses:
            if isinstance(resp, dict) and resp.get("effect"):
                decisions.append(
                    FarameshResponse(
                        effect=resp.get("effect", "DENY"),
                        tool_id=resp.get("tool_id", ""),
                        agent_id=resp.get("agent_id", ""),
                        rule_id=resp.get("rule_id"),
                        reason=resp.get("reason", ""),
                        latency_ms=resp.get("latency_ms"),
                        defer_token=resp.get("defer_token"),
                        timestamp=resp.get("timestamp"),
                    )
                )
                if limit > 0 and len(decisions) >= limit:
                    break

        return decisions

    def get_pending_approvals(self) -> list[dict]:
        """
        Get pending approval requests.

        Returns:
            List of pending defer items
        """
        request = {"type": "agent", "op": "pending"}

        responses = _send_socket_request(self._socket_path, request, timeout=5.0)

        pending = []
        for resp in responses:
            if not isinstance(resp, dict):
                continue
            items = resp.get("items")
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    normalized = dict(item)
                    normalized["defer_token"] = (
                        item.get("defer_token")
                        or item.get("approval_id")
                        or item.get("token")
                    )
                    pending.append(normalized)

        return pending

    def install(self, non_interactive: bool = True) -> tuple[bool, Optional[str]]:
        """
        Install Faramesh if not present.

        Args:
            non_interactive: Run without user prompts

        Returns:
            Tuple of (success, bin_path)
        """
        from cli.faramesh_runtime import ensure_faramesh_installed

        success, result = ensure_faramesh_installed(
            install_if_missing=True,
            non_interactive=non_interactive,
        )
        if success:
            self._installed = True
            return True, result
        logger.error("Faramesh install failed: %s", result)
        return False, None

    def _find_bin(self) -> Optional[str]:
        """Find the faramesh binary."""
        import shutil

        if shutil.which("faramesh"):
            return shutil.which("faramesh")

        local_bin = Path.home() / ".local" / "bin" / "faramesh"
        if local_bin.is_file():
            return str(local_bin)

        for path in ["/usr/local/bin/faramesh", "/usr/bin/faramesh"]:
            if os.path.exists(path):
                return path

        return None

    def is_installed(self) -> bool:
        """Check if Faramesh is installed."""
        return self._find_bin() is not None


_gateway: Optional[FarameshGateway] = None


def get_faramesh_gateway() -> FarameshGateway:
    """Get the global FarameshGateway instance."""
    global _gateway
    if _gateway is None:
        _gateway = FarameshGateway()
    return _gateway
