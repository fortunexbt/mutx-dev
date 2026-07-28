from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

FAREMESH_PROVIDER_ID = "faramesh"
FAREMESH_DEFAULT_DAEMON_PORT = 7777
FAREMESH_INSTALL_REF = "ae3ebc9066d65e4e930164881c2f2ce2be554c7f"
FAREMESH_INSTALL_VERSION = "0.2.0"
FAREMESH_INSTALL_URL = (
    f"https://raw.githubusercontent.com/faramesh/faramesh-core/{FAREMESH_INSTALL_REF}/install.sh"
)


def _default_faramesh_socket_path() -> str:
    configured_path = os.environ.get("FAREMESH_SOCKET_PATH")
    if configured_path:
        return configured_path

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return str(Path(runtime_dir).expanduser() / "faramesh.sock")

    return str(Path.home() / ".mutx" / "run" / "faramesh.sock")


FAREMESH_SOCKET_PATH = _default_faramesh_socket_path()


class GovernanceDecisionStatus(str, Enum):
    """Stable fail-closed statuses returned by governance decision helpers."""

    PERMITTED = "permitted"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"
    UNAVAILABLE = "unavailable"
    NO_DECISION = "no_decision"
    MALFORMED = "malformed"
    TIMEOUT = "timeout"
    POLICY_DISABLED = "policy_disabled"
    ERROR = "error"


class GovernanceEffect(str, Enum):
    PERMIT = "PERMIT"
    DENY = "DENY"
    DEFER = "DEFER"


class GateOutcome(str, Enum):
    EXECUTE = "EXECUTE"
    HALT = "HALT"
    ABSTAIN = "ABSTAIN"


class _GovernanceUnavailableError(ConnectionError):
    pass


class _GovernanceTimeoutError(TimeoutError):
    pass


class _GovernanceMalformedResponseError(ValueError):
    pass


def _ensure_socket_parent(socket_path: str) -> None:
    parent = Path(socket_path).expanduser().parent
    if parent != Path("."):
        parent.mkdir(parents=True, exist_ok=True)


@dataclass
class FarameshDaemonHealth:
    daemon_reachable: bool = False
    socket_reachable: bool = False
    policy_loaded: bool = False
    policy_name: str | None = None
    policy_path: str | None = None
    decisions_total: int = 0
    pending_approvals: int = 0
    denied_today: int = 0
    deferred_today: int = 0
    uptime_seconds: float = 0.0
    version: str | None = None
    doctor_summary: str | None = None


@dataclass
class FarameshDecision:
    effect: str | None = None
    agent_id: str | None = None
    tool_id: str | None = None
    rule_id: str | None = None
    reason_code: str | None = None
    defer_token: str | None = None
    latency_ms: int | None = None
    timestamp: str | None = None


@dataclass
class FarameshDeferItem:
    defer_token: str | None = None
    agent_id: str | None = None
    tool_id: str | None = None
    status: str | None = None
    reason: str | None = None


@dataclass
class FarameshSnapshot:
    provider: str = FAREMESH_PROVIDER_ID
    status: str = "unknown"
    version: str | None = None
    decisions_total: int = 0
    permits_today: int = 0
    denies_today: int = 0
    defers_today: int = 0
    pending_approvals: int = 0
    last_decision_at: str | None = None
    observed_at: str | None = None
    payload: dict | None = None


def is_socket_reachable(socket_path: str = FAREMESH_SOCKET_PATH, timeout: float = 0.5) -> bool:
    try:
        if not os.path.exists(socket_path):
            return False
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(socket_path)
        sock.close()
        return True
    except (OSError, socket.error, socket.timeout):
        return False


def _send_socket_request(
    socket_path: str,
    request: dict,
    timeout: float = 5.0,
    *,
    strict: bool = False,
) -> list[dict]:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(socket_path)
    except socket.timeout as exc:
        try:
            sock.close()
        except Exception:
            pass
        if strict:
            raise _GovernanceTimeoutError("governance request timed out while connecting") from exc
        return []
    except (OSError, socket.error) as exc:
        try:
            sock.close()
        except Exception:
            pass
        if strict:
            raise _GovernanceUnavailableError("governance socket is unavailable") from exc
        return []

    try:
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)

        buf = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout as exc:
                if strict:
                    raise _GovernanceTimeoutError(
                        "governance request timed out while awaiting a decision"
                    ) from exc
                break
            if not chunk:
                break
            buf += chunk

        if not buf:
            return []

        try:
            response_text = buf.decode("utf-8")
        except UnicodeDecodeError as exc:
            if strict:
                raise _GovernanceMalformedResponseError(
                    "governance response was not valid UTF-8"
                ) from exc
            return []

        results = []
        for line in response_text.splitlines():
            line = line.strip()
            if line:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    if strict:
                        raise _GovernanceMalformedResponseError(
                            "governance response was not valid JSON"
                        ) from exc
                    continue
                if not isinstance(item, dict):
                    if strict:
                        raise _GovernanceMalformedResponseError(
                            "governance response must be a JSON object"
                        )
                    continue
                results.append(item)
        return results
    except _GovernanceTimeoutError:
        raise
    except socket.timeout as exc:
        if strict:
            raise _GovernanceTimeoutError("governance request timed out") from exc
        return []
    except OSError as exc:
        if strict:
            raise _GovernanceUnavailableError("governance socket is unavailable") from exc
        return []
    finally:
        try:
            sock.close()
        except Exception:
            pass


def get_daemon_status(socket_path: str = FAREMESH_SOCKET_PATH, timeout: float = 1.0) -> dict:
    result = _send_socket_request(socket_path, {"type": "audit_subscribe"}, timeout=timeout)
    subscribed = len(result) > 0 and any(r.get("subscribed") for r in result)
    return {"reachable": bool(result), "subscribed": subscribed}


def get_recent_decisions(
    socket_path: str = FAREMESH_SOCKET_PATH, limit: int = 50, timeout: float = 1.0
) -> list[FarameshDecision]:
    result = _send_socket_request(
        socket_path,
        {"type": "decisions_recent", "limit": limit},
        timeout=timeout,
    )
    decisions = []
    for item in result:
        decisions.append(
            FarameshDecision(
                effect=item.get("effect"),
                agent_id=item.get("agent_id"),
                tool_id=item.get("tool_id"),
                rule_id=item.get("rule_id"),
                reason_code=item.get("reason_code"),
                defer_token=item.get("defer_token"),
                latency_ms=item.get("latency_ms"),
                timestamp=item.get("timestamp"),
            )
        )
    return decisions


def get_pending_defers(
    socket_path: str = FAREMESH_SOCKET_PATH, timeout: float = 1.0
) -> list[FarameshDeferItem]:
    result = _send_socket_request(socket_path, {"type": "defers_pending"}, timeout=timeout)
    defers = []
    for item in result:
        defers.append(
            FarameshDeferItem(
                defer_token=item.get("defer_token"),
                agent_id=item.get("agent_id"),
                tool_id=item.get("tool_id"),
                status=item.get("status"),
                reason=item.get("reason"),
            )
        )
    return defers


def find_faramesh_bin() -> str | None:
    bin_path = shutil.which("faramesh")
    if bin_path:
        return bin_path
    local_bin = Path.home() / ".local" / "bin" / "faramesh"
    if local_bin.exists():
        return str(local_bin)
    return None


def detect_faramesh_version() -> str | None:
    bin_path = find_faramesh_bin()
    if not bin_path:
        return None
    try:
        result = subprocess.run(
            [bin_path, "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None


def is_faramesh_installed() -> bool:
    return find_faramesh_bin() is not None


def is_faramesh_available() -> bool:
    return is_socket_reachable()


def ensure_faramesh_installed(
    install_if_missing: bool = True, non_interactive: bool = True
) -> tuple[bool, str | None]:
    if is_faramesh_installed():
        return True, find_faramesh_bin()

    if not install_if_missing:
        return False, None

    try:
        with tempfile.NamedTemporaryFile(
            prefix="faramesh-install-",
            suffix=".sh",
            delete=False,
        ) as install_script:
            install_script_path = Path(install_script.name)

        try:
            subprocess.run(
                ["curl", "-fsSL", FAREMESH_INSTALL_URL, "-o", str(install_script_path)],
                check=True,
                timeout=30,
            )
            subprocess.run(
                ["chmod", "+x", str(install_script_path)],
                check=True,
                timeout=5,
            )

            cmd = [
                str(install_script_path),
                "--version",
                FAREMESH_INSTALL_VERSION,
                "--install-dir",
                str(Path.home() / ".local" / "bin"),
            ]
            if non_interactive:
                cmd.append("--no-interactive")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        finally:
            install_script_path.unlink(missing_ok=True)

        if result.returncode == 0:
            bin_path = find_faramesh_bin()
            return True, bin_path
        else:
            return False, result.stderr if result.stderr else result.stdout
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def _count_decisions_by_effect(decisions: list) -> tuple:
    permit_count = 0
    deny_count = 0
    defer_count = 0

    for decision in decisions:
        effect = getattr(decision, "effect", None)
        if effect is None:
            continue
        effect_lower = effect.lower()
        if effect_lower == "permit":
            permit_count += 1
        elif effect_lower == "deny":
            deny_count += 1
        elif effect_lower == "defer":
            defer_count += 1

    return permit_count, deny_count, defer_count


def collect_faramesh_snapshot() -> FarameshSnapshot:
    health = get_faramesh_health()
    decisions = get_recent_decisions()
    pending_defers = get_pending_defers()

    permit_count, deny_count, defer_count = _count_decisions_by_effect(decisions)

    last_decision_at = None
    if decisions:
        for d in reversed(decisions):
            ts = getattr(d, "timestamp", None)
            if ts:
                last_decision_at = ts
                break

    status = "not_installed"
    if health.socket_reachable and health.daemon_reachable:
        status = "running"
    elif health.socket_reachable:
        status = "degraded"
    elif find_faramesh_bin():
        status = "stopped"

    payload = {
        "provider": "faramesh",
        "role": "governance",
        "decisions_total": len(decisions),
        "permits_today": permit_count,
        "denies_today": deny_count,
        "defers_today": defer_count,
        "pending_approvals": len(pending_defers),
        "last_decision_at": last_decision_at,
    }

    return FarameshSnapshot(
        provider="faramesh",
        status=status,
        version=health.version,
        decisions_total=len(decisions),
        permits_today=permit_count,
        denies_today=deny_count,
        defers_today=defer_count,
        pending_approvals=len(pending_defers),
        last_decision_at=last_decision_at,
        observed_at=datetime.now(timezone.utc).isoformat(),
        payload=payload,
    )


def get_faramesh_health() -> FarameshDaemonHealth:
    health = FarameshDaemonHealth()

    bin_path = find_faramesh_bin()
    health.version = detect_faramesh_version() if bin_path else None
    health.socket_reachable = is_socket_reachable()

    if not bin_path:
        health.doctor_summary = "Faramesh is not installed."
        return health

    if not health.socket_reachable:
        health.doctor_summary = "Faramesh is installed but the daemon is not running."
        return health

    if health.socket_reachable:
        status = get_daemon_status()
        health.daemon_reachable = status.get("reachable", False)

        if health.daemon_reachable:
            health.doctor_summary = "Faramesh governance daemon is running and reachable."
            try:
                decisions = get_recent_decisions(limit=100)
                health.decisions_total = len(decisions)
                _, denied, deferred = _count_decisions_by_effect(decisions)
                health.denied_today = denied
                health.deferred_today = deferred
            except Exception:
                pass

            try:
                pending = get_pending_defers()
                health.pending_approvals = len(pending)
            except Exception:
                pass
        else:
            health.doctor_summary = (
                "Faramesh daemon socket is reachable but not responding correctly."
            )
    else:
        health.doctor_summary = "Faramesh is installed but the daemon is not running."

    return health


def start_faramesh_daemon(
    policy_path: str | None = None, socket_path: str = FAREMESH_SOCKET_PATH
) -> subprocess.Popen | None:
    bin_path = find_faramesh_bin()
    if not bin_path:
        return None

    cmd = [bin_path, "serve"]

    if policy_path:
        cmd.extend(["--policy", policy_path])

    cmd.extend(["--socket", socket_path])

    try:
        _ensure_socket_parent(socket_path)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        time.sleep(0.5)

        if proc.poll() is not None:
            return None

        return proc
    except (OSError, subprocess.SubprocessError):
        return None


def install_faramesh(non_interactive: bool = True) -> str:
    success, result = ensure_faramesh_installed(
        install_if_missing=True, non_interactive=non_interactive
    )

    if success:
        return result if result else "installed"
    else:
        raise Exception(f"Faramesh installation failed: {result}")


def get_default_policy_path() -> str | None:
    """Look for bundled starter policy in standard locations."""
    bundled = Path(__file__).parent / "policies" / "starter.fpl"
    if bundled.exists():
        return str(bundled)

    user_policy_1 = Path.home() / ".mutx" / "policies" / "starter.fpl"
    if user_policy_1.exists():
        return str(user_policy_1)

    user_policy_2 = Path.home() / ".faramesh" / "policy.fpl"
    if user_policy_2.exists():
        return str(user_policy_2)

    return None


def approve_defer(socket_path: str, token: str) -> bool:
    """Approve a deferred governance decision."""
    result = _send_socket_request(
        socket_path, {"type": "agent_approve", "token": token}, timeout=5.0
    )
    if not result:
        return False
    for r in result:
        if isinstance(r, dict) and r.get("approved"):
            return True
    return False


def deny_defer(socket_path: str, token: str) -> bool:
    """Deny a deferred governance decision."""
    result = _send_socket_request(socket_path, {"type": "agent_deny", "token": token}, timeout=5.0)
    if not result:
        return False
    for r in result:
        if isinstance(r, dict) and r.get("denied"):
            return True
    return False


def kill_agent(socket_path: str, agent_id: str) -> bool:
    """Emergency kill an agent."""
    result = _send_socket_request(
        socket_path, {"type": "agent_kill", "agent_id": agent_id}, timeout=5.0
    )
    if not result:
        return False
    for r in result:
        if isinstance(r, dict) and r.get("killed"):
            return True
    return False


def validate_policy(socket_path: str, policy_path: str) -> dict:
    """Validate an FPL policy file."""
    bin_path = find_faramesh_bin()
    if not bin_path:
        return {"valid": False, "error": "faramesh not installed"}

    try:
        proc = subprocess.run(
            [bin_path, "policy", "validate", policy_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return {"valid": True, "output": proc.stdout.strip()}
        else:
            return {"valid": False, "error": proc.stderr.strip() or proc.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"valid": False, "error": "validation timed out"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def reload_policy(socket_path: str, policy_path: str | None = None) -> bool:
    """Hot-reload the running policy."""
    request = {"type": "policy_reload"}
    if policy_path:
        request["policy_path"] = policy_path
    result = _send_socket_request(socket_path, request, timeout=5.0)
    for r in result:
        if isinstance(r, dict) and r.get("reloaded"):
            return True
    return False


def list_policy_packs() -> list[dict]:
    """List all bundled policy packs available."""
    policies_dir = Path(__file__).parent / "policies"
    packs = []
    if policies_dir.exists():
        for f in sorted(policies_dir.glob("*.fpl")):
            packs.append(
                {
                    "name": f.stem,
                    "path": str(f),
                    "description": _get_policy_description(f),
                }
            )
    return packs


def _get_policy_description(path: Path) -> str:
    """Extract description from policy file."""
    try:
        content = path.read_text()
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("#"):
                desc = line.lstrip("#").strip()
                if desc and len(desc) > 5:
                    return desc[:60]
            elif line.startswith("agent "):
                break
    except Exception:
        pass
    return "No description"


def generate_prometheus_metrics(snapshot: FarameshSnapshot) -> str:
    """Generate Prometheus metrics text format."""
    lines = [
        "# HELP mutx_governance_decisions_total Total governance decisions by effect",
        "# TYPE mutx_governance_decisions_total counter",
        f'mutx_governance_decisions_total{{effect="permit"}} {snapshot.permits_today}',
        f'mutx_governance_decisions_total{{effect="deny"}} {snapshot.denies_today}',
        f'mutx_governance_decisions_total{{effect="defer"}} {snapshot.defers_today}',
        "# HELP mutx_governance_pending_approvals Pending approval count",
        "# TYPE mutx_governance_pending_approvals gauge",
        f"mutx_governance_pending_approvals {snapshot.pending_approvals}",
        "# HELP mutx_governance_daemon_up Daemon availability",
        "# TYPE mutx_governance_daemon_up gauge",
        f"mutx_governance_daemon_up {1 if snapshot.status == 'running' else 0}",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class GateDecision:
    outcome: GateOutcome | str
    effect: GovernanceEffect | str | None
    reason_code: str | None = None
    reason: str | None = None
    defer_token: str | None = None
    latency_ms: int | None = None
    status: GovernanceDecisionStatus = GovernanceDecisionStatus.MALFORMED
    authoritative: bool = False
    action_id: str | None = None
    receipt_id: str | None = None
    receipt: dict[str, Any] | None = None
    audit_context: dict[str, Any] | None = None
    decision_payload: dict[str, Any] | None = None

    @property
    def is_authoritative_permit(self) -> bool:
        return (
            self.authoritative
            and self.status == GovernanceDecisionStatus.PERMITTED
            and self.outcome == GateOutcome.EXECUTE
            and self.effect == GovernanceEffect.PERMIT
        )


@dataclass
class ActionResult:
    action_id: str | None = None
    status: str | None = None
    executed: bool = False
    payload: dict | None = None
    error: str | None = None
    defer_token: str | None = None
    governance_status: GovernanceDecisionStatus | None = None
    effect: GovernanceEffect | str | None = None
    reason_code: str | None = None
    reason: str | None = None
    authoritative: bool = False
    receipt_id: str | None = None
    receipt: dict[str, Any] | None = None
    audit_context: dict[str, Any] | None = None
    decision_payload: dict[str, Any] | None = None
    gate_decision_payload: dict[str, Any] | None = None

    @property
    def is_authoritative_permit(self) -> bool:
        return (
            self.authoritative
            and self.governance_status == GovernanceDecisionStatus.PERMITTED
            and self.effect == GovernanceEffect.PERMIT
        )


def _response_context(
    response: dict[str, Any],
) -> tuple[str | None, str | None, dict[str, Any] | None, dict[str, Any] | None]:
    receipt = response.get("receipt")
    if not isinstance(receipt, dict):
        receipt = response.get("authorization_receipt")
    if not isinstance(receipt, dict):
        receipt = None

    receipt_id = response.get("receipt_id")
    if receipt_id is None and receipt is not None:
        receipt_id = receipt.get("receipt_id")

    audit_context = response.get("audit_context")
    if not isinstance(audit_context, dict):
        audit_context = response.get("audit")
    if not isinstance(audit_context, dict):
        audit_context = None

    action_id = response.get("action_id")
    return (
        str(action_id) if action_id is not None else None,
        str(receipt_id) if receipt_id is not None else None,
        receipt,
        audit_context,
    )


def _failure_decision(
    status: GovernanceDecisionStatus,
    reason: str,
    reason_code: str,
    *,
    decision_payload: dict[str, Any] | None = None,
) -> GateDecision:
    return GateDecision(
        outcome=GateOutcome.HALT,
        effect=None,
        status=status,
        reason=reason,
        reason_code=reason_code,
        authoritative=False,
        decision_payload=decision_payload,
    )


def _policy_is_disabled(response: dict[str, Any]) -> bool:
    response_status = str(response.get("status") or "").strip().lower()
    effect = str(response.get("effect") or "").strip().upper()
    return (
        response.get("policy_enabled") is False
        or response.get("policy_loaded") is False
        or response_status in {"disabled", "policy_disabled", "policy_not_loaded", "no_policy"}
        or effect in {"DISABLED", "POLICY_DISABLED"}
    )


def _parse_gate_response(response: Any) -> GateDecision:
    if not isinstance(response, dict):
        return _failure_decision(
            GovernanceDecisionStatus.MALFORMED,
            "governance response must be an object",
            "governance_malformed_response",
        )

    decision_payload = dict(response)
    action_id, receipt_id, receipt, audit_context = _response_context(response)

    if _policy_is_disabled(response):
        return GateDecision(
            outcome=GateOutcome.HALT,
            effect=None,
            status=GovernanceDecisionStatus.POLICY_DISABLED,
            reason_code=str(response.get("reason_code") or "governance_policy_disabled"),
            reason=str(response.get("reason") or "governance policy is disabled"),
            authoritative=False,
            action_id=action_id,
            receipt_id=receipt_id,
            receipt=receipt,
            audit_context=audit_context,
            decision_payload=decision_payload,
        )

    if response.get("error"):
        return GateDecision(
            outcome=GateOutcome.HALT,
            effect=None,
            status=GovernanceDecisionStatus.ERROR,
            reason_code=str(response.get("reason_code") or "governance_error"),
            reason=str(response.get("reason") or response["error"]),
            authoritative=False,
            action_id=action_id,
            receipt_id=receipt_id,
            receipt=receipt,
            audit_context=audit_context,
            decision_payload=decision_payload,
        )

    if response.get("authoritative") is False:
        return GateDecision(
            outcome=GateOutcome.HALT,
            effect=None,
            status=GovernanceDecisionStatus.MALFORMED,
            reason_code="governance_non_authoritative_response",
            reason="governance response was explicitly non-authoritative",
            authoritative=False,
            action_id=action_id,
            receipt_id=receipt_id,
            receipt=receipt,
            audit_context=audit_context,
            decision_payload=decision_payload,
        )

    raw_effect = response.get("effect")
    if not isinstance(raw_effect, str):
        return GateDecision(
            outcome=GateOutcome.HALT,
            effect=None,
            status=GovernanceDecisionStatus.MALFORMED,
            reason_code="governance_malformed_response",
            reason="governance response did not include a valid effect",
            authoritative=False,
            action_id=action_id,
            receipt_id=receipt_id,
            receipt=receipt,
            audit_context=audit_context,
            decision_payload=decision_payload,
        )

    try:
        effect = GovernanceEffect(raw_effect.strip().upper())
    except ValueError:
        return GateDecision(
            outcome=GateOutcome.HALT,
            effect=None,
            status=GovernanceDecisionStatus.MALFORMED,
            reason_code="governance_unknown_effect",
            reason=f"governance returned unsupported effect: {raw_effect}",
            authoritative=False,
            action_id=action_id,
            receipt_id=receipt_id,
            receipt=receipt,
            audit_context=audit_context,
            decision_payload=decision_payload,
        )

    common = {
        "effect": effect,
        "reason_code": response.get("reason_code"),
        "reason": response.get("reason"),
        "defer_token": response.get("defer_token"),
        "latency_ms": response.get("latency_ms"),
        "authoritative": True,
        "action_id": action_id,
        "receipt_id": receipt_id,
        "receipt": receipt,
        "audit_context": audit_context,
        "decision_payload": decision_payload,
    }
    if effect == GovernanceEffect.PERMIT:
        return GateDecision(
            outcome=GateOutcome.EXECUTE,
            status=GovernanceDecisionStatus.PERMITTED,
            **common,
        )
    if effect == GovernanceEffect.DENY:
        common["reason"] = common["reason"] or "denied by policy"
        return GateDecision(
            outcome=GateOutcome.HALT,
            status=GovernanceDecisionStatus.DENIED,
            **common,
        )
    common["reason"] = common["reason"] or "approval required"
    return GateDecision(
        outcome=GateOutcome.ABSTAIN,
        status=GovernanceDecisionStatus.APPROVAL_REQUIRED,
        **common,
    )


def _action_result_from_decision(
    decision: GateDecision,
    *,
    denied_status: str = "denied",
) -> ActionResult:
    legacy_status = {
        GovernanceDecisionStatus.PERMITTED: "executed",
        GovernanceDecisionStatus.DENIED: denied_status,
        GovernanceDecisionStatus.APPROVAL_REQUIRED: "pending_approval",
        GovernanceDecisionStatus.UNAVAILABLE: "governance_unavailable",
        GovernanceDecisionStatus.NO_DECISION: "no_response",
        GovernanceDecisionStatus.MALFORMED: "malformed_response",
        GovernanceDecisionStatus.TIMEOUT: "timeout",
        GovernanceDecisionStatus.POLICY_DISABLED: "policy_disabled",
        GovernanceDecisionStatus.ERROR: "error",
    }
    return ActionResult(
        action_id=decision.action_id,
        status=legacy_status[decision.status],
        executed=decision.is_authoritative_permit,
        error=None if decision.is_authoritative_permit else decision.reason,
        defer_token=decision.defer_token,
        governance_status=decision.status,
        effect=decision.effect,
        reason_code=decision.reason_code,
        reason=decision.reason,
        authoritative=decision.authoritative,
        receipt_id=decision.receipt_id,
        receipt=decision.receipt,
        audit_context=decision.audit_context,
        decision_payload=decision.decision_payload,
    )


def gate_decide(
    agent_id: str,
    tool_id: str,
    params: dict,
    context: dict | None = None,
    socket_path: str = FAREMESH_SOCKET_PATH,
) -> GateDecision:
    """Ask Faramesh for an authoritative decision, failing closed on indeterminate states."""
    try:
        request = {
            "type": "gate_decide",
            "agent_id": agent_id,
            "tool_id": tool_id,
            "params": params,
            "context": context or {},
        }
        responses = _send_socket_request(socket_path, request, timeout=2.0, strict=True)
        if not responses:
            return _failure_decision(
                GovernanceDecisionStatus.NO_DECISION,
                "governance returned no decision",
                "governance_no_decision",
            )
        return _parse_gate_response(responses[0])
    except _GovernanceTimeoutError as exc:
        return _failure_decision(
            GovernanceDecisionStatus.TIMEOUT,
            str(exc),
            "governance_timeout",
        )
    except _GovernanceUnavailableError as exc:
        return _failure_decision(
            GovernanceDecisionStatus.UNAVAILABLE,
            str(exc),
            "governance_unavailable",
        )
    except _GovernanceMalformedResponseError as exc:
        return _failure_decision(
            GovernanceDecisionStatus.MALFORMED,
            str(exc),
            "governance_malformed_response",
        )
    except Exception as exc:
        return _failure_decision(
            GovernanceDecisionStatus.ERROR,
            str(exc) or "governance error",
            "governance_error",
            decision_payload={"exception_type": type(exc).__name__},
        )


def submit_action(
    agent_id: str,
    tool_id: str,
    params: dict,
    context: dict | None = None,
    socket_path: str = FAREMESH_SOCKET_PATH,
) -> ActionResult:
    """Submit an action for governance review without inferring permission from failures."""
    try:
        request = {
            "type": "action_submit",
            "agent_id": agent_id,
            "tool_id": tool_id,
            "params": params,
            "context": context or {},
        }
        responses = _send_socket_request(socket_path, request, timeout=5.0, strict=True)
        if not responses:
            return _action_result_from_decision(
                _failure_decision(
                    GovernanceDecisionStatus.NO_DECISION,
                    "governance returned no decision",
                    "governance_no_decision",
                )
            )
        response = responses[0]
        result = _action_result_from_decision(_parse_gate_response(response))
        if result.is_authoritative_permit:
            result.payload = response.get("payload")
        return result
    except _GovernanceTimeoutError as exc:
        decision = _failure_decision(
            GovernanceDecisionStatus.TIMEOUT,
            str(exc),
            "governance_timeout",
        )
    except _GovernanceUnavailableError as exc:
        decision = _failure_decision(
            GovernanceDecisionStatus.UNAVAILABLE,
            str(exc),
            "governance_unavailable",
        )
    except _GovernanceMalformedResponseError as exc:
        decision = _failure_decision(
            GovernanceDecisionStatus.MALFORMED,
            str(exc),
            "governance_malformed_response",
        )
    except Exception as exc:
        decision = _failure_decision(
            GovernanceDecisionStatus.ERROR,
            str(exc) or "governance error",
            "governance_error",
            decision_payload={"exception_type": type(exc).__name__},
        )
    return _action_result_from_decision(decision)


def wait_for_decision(
    defer_token: str,
    timeout: float = 300.0,
    socket_path: str = FAREMESH_SOCKET_PATH,
) -> ActionResult:
    """Wait for a deferred action without treating disappearance as approval."""
    start = time.time()
    poll_interval = 1.0

    try:
        while time.time() - start < timeout:
            matching = next(
                (
                    item
                    for item in get_pending_defers(socket_path)
                    if item.defer_token == defer_token
                ),
                None,
            )
            if matching is None:
                recent = next(
                    (
                        item
                        for item in reversed(
                            get_recent_decisions(socket_path=socket_path, limit=100)
                        )
                        if item.defer_token == defer_token
                    ),
                    None,
                )
                if recent is None:
                    return _action_result_from_decision(
                        _failure_decision(
                            GovernanceDecisionStatus.NO_DECISION,
                            "deferred decision resolved without an authoritative result",
                            "governance_no_decision",
                        )
                    )

                result = _action_result_from_decision(
                    _parse_gate_response(
                        {
                            "effect": recent.effect,
                            "reason_code": recent.reason_code,
                            "defer_token": recent.defer_token,
                            "latency_ms": recent.latency_ms,
                        }
                    ),
                    denied_status="denied_by_approver",
                )
                if result.is_authoritative_permit:
                    result.status = "approved"
                return result

            defer_status = str(matching.status or "pending").strip().lower()
            if defer_status in {"denied", "rejected", "expired", "cancelled"}:
                return _action_result_from_decision(
                    GateDecision(
                        outcome=GateOutcome.HALT,
                        effect=GovernanceEffect.DENY,
                        status=GovernanceDecisionStatus.DENIED,
                        reason=matching.reason or "deferred action was not approved",
                        reason_code=f"governance_{defer_status}",
                        defer_token=defer_token,
                        authoritative=True,
                        decision_payload={
                            "defer_token": defer_token,
                            "status": matching.status,
                            "reason": matching.reason,
                        },
                    ),
                    denied_status="denied_by_approver",
                )
            if defer_status in {"approved", "permitted"}:
                return _action_result_from_decision(
                    _failure_decision(
                        GovernanceDecisionStatus.MALFORMED,
                        "approval did not include an authoritative PERMIT decision",
                        "governance_approval_missing_permit",
                        decision_payload={
                            "defer_token": defer_token,
                            "status": matching.status,
                            "reason": matching.reason,
                        },
                    )
                )
            if defer_status not in {"pending", "deferred", "approval_required"}:
                return _action_result_from_decision(
                    _failure_decision(
                        GovernanceDecisionStatus.MALFORMED,
                        f"governance returned unsupported defer status: {matching.status}",
                        "governance_unknown_defer_status",
                    )
                )

            time.sleep(poll_interval)
    except Exception as exc:
        return _action_result_from_decision(
            _failure_decision(
                GovernanceDecisionStatus.ERROR,
                str(exc) or "governance error while waiting for approval",
                "governance_error",
                decision_payload={"exception_type": type(exc).__name__},
            )
        )

    return _action_result_from_decision(
        _failure_decision(
            GovernanceDecisionStatus.TIMEOUT,
            "governance approval timed out",
            "governance_timeout",
            decision_payload={"defer_token": defer_token},
        )
    )


def execute_if_allowed(
    agent_id: str,
    tool_id: str,
    params: dict,
    executor: Callable[[str, dict], dict | None],
    context: dict | None = None,
    socket_path: str = FAREMESH_SOCKET_PATH,
    governance_enabled: bool = True,
) -> ActionResult:
    """Execute exactly once only after a valid authoritative PERMIT decision."""
    if not governance_enabled:
        return _action_result_from_decision(
            _failure_decision(
                GovernanceDecisionStatus.POLICY_DISABLED,
                "governance policy is disabled",
                "governance_policy_disabled",
            )
        )

    try:
        decision = gate_decide(agent_id, tool_id, params, context, socket_path)
    except Exception as exc:
        decision = _failure_decision(
            GovernanceDecisionStatus.ERROR,
            str(exc) or "governance decision failed",
            "governance_error",
            decision_payload={"exception_type": type(exc).__name__},
        )

    if not isinstance(decision, GateDecision):
        decision = _failure_decision(
            GovernanceDecisionStatus.MALFORMED,
            "governance helper returned an invalid decision object",
            "governance_malformed_decision",
        )

    if decision.status == GovernanceDecisionStatus.APPROVAL_REQUIRED:
        submit_result = submit_action(agent_id, tool_id, params, context, socket_path)
        submit_result.gate_decision_payload = decision.decision_payload
        if submit_result.receipt is None:
            submit_result.receipt = decision.receipt
            submit_result.receipt_id = decision.receipt_id
        if submit_result.audit_context is None:
            submit_result.audit_context = decision.audit_context
        return submit_result

    if not decision.is_authoritative_permit:
        if decision.status == GovernanceDecisionStatus.PERMITTED:
            decision = GateDecision(
                outcome=GateOutcome.HALT,
                effect=None,
                status=GovernanceDecisionStatus.MALFORMED,
                reason="governance permit was not authoritative",
                reason_code="governance_non_authoritative_permit",
                authoritative=False,
                action_id=decision.action_id,
                receipt_id=decision.receipt_id,
                receipt=decision.receipt,
                audit_context=decision.audit_context,
                decision_payload=decision.decision_payload,
            )
        blocked_result = _action_result_from_decision(decision, denied_status="blocked")
        if decision.status == GovernanceDecisionStatus.DENIED:
            blocked_result.error = f"Tool {tool_id} denied: {decision.reason_code}"
        return blocked_result

    result = executor(tool_id, params)
    return ActionResult(
        action_id=decision.action_id,
        status="executed",
        executed=True,
        payload=result if result else {},
        governance_status=decision.status,
        effect=decision.effect,
        reason_code=decision.reason_code,
        reason=decision.reason,
        authoritative=decision.authoritative,
        receipt_id=decision.receipt_id,
        receipt=decision.receipt,
        audit_context=decision.audit_context,
        decision_payload=decision.decision_payload,
        gate_decision_payload=decision.decision_payload,
    )
