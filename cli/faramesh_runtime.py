from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

FAREMESH_PROVIDER_ID = "faramesh"
FAREMESH_DEFAULT_DAEMON_PORT = 7777
FAREMESH_INSTALL_REF = "ae3ebc9066d65e4e930164881c2f2ce2be554c7f"
FAREMESH_INSTALL_VERSION = "0.2.0"
FAREMESH_INSTALL_SCRIPT_SHA256 = (
    "9cce09b37079c6d0e391e9744577f151fc0fa4f71792659d81683a2f92e59f20"
)
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

    def to_payload(self) -> dict:
        """Return the stable JSON shape consumed by CLI and desktop surfaces."""
        return {
            "provider": self.provider,
            "status": self.status,
            "version": self.version,
            "decisions_total": self.decisions_total,
            "permits_today": self.permits_today,
            "denies_today": self.denies_today,
            "defers_today": self.defers_today,
            "pending_approvals": self.pending_approvals,
            "last_decision_at": self.last_decision_at,
            "observed_at": self.observed_at,
            "payload": self.payload or {},
        }


def is_socket_reachable(socket_path: str = FAREMESH_SOCKET_PATH, timeout: float = 0.5) -> bool:
    sock: socket.socket | None = None
    try:
        if not os.path.exists(socket_path):
            return False
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(socket_path)
        return True
    except (OSError, socket.error, socket.timeout):
        return False
    finally:
        if sock is not None:
            sock.close()


def _send_socket_request(socket_path: str, request: dict, timeout: float = 5.0) -> list[dict]:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(socket_path)
    except (OSError, socket.error):
        return []

    try:
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)

        buf = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk

        if not buf:
            return []

        results = []
        for line in buf.decode("utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return results
    finally:
        try:
            sock.close()
        except Exception:
            pass


def get_daemon_status(socket_path: str = FAREMESH_SOCKET_PATH, timeout: float = 1.0) -> dict:
    result = _send_socket_request(socket_path, {"type": "status"}, timeout=timeout)
    for response in result:
        if not isinstance(response, dict) or response.get("error"):
            continue
        if "running" in response:
            return {"reachable": True, **response}
    return {"reachable": False}


def get_recent_decisions(
    socket_path: str = FAREMESH_SOCKET_PATH, limit: int = 50, timeout: float = 1.0
) -> list[FarameshDecision]:
    # v0.2.0 has no historical ``decisions_recent`` socket operation. Its
    # supported contract is a bounded read from the live audit subscription.
    result = _send_socket_request(socket_path, {"type": "audit_subscribe"}, timeout=timeout)
    decisions = []
    for item in result:
        if not isinstance(item, dict) or not item.get("effect"):
            continue
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
        if limit > 0 and len(decisions) >= limit:
            break
    return decisions


def get_pending_defers(
    socket_path: str = FAREMESH_SOCKET_PATH, timeout: float = 1.0
) -> list[FarameshDeferItem]:
    result = _send_socket_request(
        socket_path,
        {"type": "agent", "op": "pending"},
        timeout=timeout,
    )
    items: list[dict] = []
    for response in result:
        if not isinstance(response, dict):
            continue
        response_items = response.get("items")
        if isinstance(response_items, list):
            items.extend(item for item in response_items if isinstance(item, dict))
        elif response.get("defer_token"):
            items.append(response)

    defers = []
    for item in items:
        defers.append(
            FarameshDeferItem(
                defer_token=(
                    item.get("defer_token")
                    or item.get("approval_id")
                    or item.get("token")
                ),
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
            [bin_path, "--version"],
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
            installer_digest = hashlib.sha256(install_script_path.read_bytes()).hexdigest()
            if installer_digest != FAREMESH_INSTALL_SCRIPT_SHA256:
                return (
                    False,
                    "Faramesh installer integrity check failed: "
                    f"expected {FAREMESH_INSTALL_SCRIPT_SHA256}, got {installer_digest}",
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
        health.policy_loaded = bool(status.get("policy_loaded", False))
        health.policy_name = status.get("policy_version")
        health.uptime_seconds = float(status.get("uptime_seconds", 0.0) or 0.0)

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
        socket_path,
        {
            "type": "approve_defer",
            "defer_token": token,
            "approved": True,
            "reason": "approved via MUTX",
        },
        timeout=5.0,
    )
    if not result:
        return False
    for r in result:
        if isinstance(r, dict) and r.get("ok") is True:
            return True
    return False


def deny_defer(socket_path: str, token: str) -> bool:
    """Deny a deferred governance decision."""
    result = _send_socket_request(
        socket_path,
        {
            "type": "approve_defer",
            "defer_token": token,
            "approved": False,
            "reason": "denied via MUTX",
        },
        timeout=5.0,
    )
    if not result:
        return False
    for r in result:
        if isinstance(r, dict) and r.get("ok") is True:
            return True
    return False


def kill_agent(socket_path: str, agent_id: str, admin_token: str | None = None) -> bool:
    """Emergency kill an agent."""
    resolved_token = (
        admin_token
        or os.environ.get("FARAMESH_STANDING_ADMIN_TOKEN")
        or os.environ.get("FARAMESH_POLICY_ADMIN_TOKEN")
        or ""
    )
    result = _send_socket_request(
        socket_path,
        {"type": "kill", "agent_id": agent_id, "admin_token": resolved_token},
        timeout=5.0,
    )
    if not result:
        return False
    for r in result:
        if isinstance(r, dict) and r.get("ok") is True:
            return True
    return False


def validate_policy(socket_path: str, policy_path: str) -> dict:
    """Validate FPL by loading it with the pinned release's supported daemon CLI."""
    del socket_path  # Validation uses an isolated socket and data directory.
    bin_path = find_faramesh_bin()
    if not bin_path:
        return {"valid": False, "error": "faramesh not installed"}

    try:
        # Darwin limits Unix-domain socket paths to roughly 104 bytes. Keep the
        # isolated validation socket rooted at the short, portable /tmp path.
        with tempfile.TemporaryDirectory(prefix="mfx-val-", dir="/tmp") as temp_dir:
            validation_socket = Path(temp_dir) / "faramesh.sock"
            validation_data = Path(temp_dir) / "data"
            process = subprocess.Popen(
                [
                    bin_path,
                    "serve",
                    "--policy",
                    str(Path(policy_path).expanduser().resolve()),
                    "--socket",
                    str(validation_socket),
                    "--data-dir",
                    str(validation_data),
                    "--log-level",
                    "error",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    if validation_socket.exists():
                        return {"valid": True, "output": "policy loaded by Faramesh v0.2.0"}
                    if process.poll() is not None:
                        stdout, stderr = process.communicate()
                        return {
                            "valid": False,
                            "error": (stderr.strip() or stdout.strip() or "policy load failed"),
                        }
                    time.sleep(0.05)
                return {"valid": False, "error": "validation timed out before socket readiness"}
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"valid": False, "error": str(exc)}


def reload_policy(socket_path: str, policy_path: str | None = None) -> bool:
    """Reload an applied governance stack through the supported ``apply`` CLI."""
    del socket_path  # v0.2.0 exposes no policy_reload socket operation.
    bin_path = find_faramesh_bin()
    if not bin_path:
        return False

    candidate = Path(policy_path).expanduser().resolve() if policy_path else Path.cwd()
    stack_dir = candidate if candidate.is_dir() else candidate.parent
    if not (stack_dir / "governance.fms").is_file():
        return False

    try:
        result = subprocess.run(
            [bin_path, "apply", "--dir", str(stack_dir)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
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
    outcome: str
    effect: str
    reason_code: str | None = None
    reason: str | None = None
    defer_token: str | None = None
    latency_ms: int | None = None


@dataclass
class ActionResult:
    action_id: str | None = None
    status: str | None = None
    executed: bool = False
    payload: dict | None = None
    error: str | None = None
    defer_token: str | None = None


def _govern_request(
    agent_id: str,
    tool_id: str,
    params: dict,
    context: dict | None = None,
) -> dict:
    """Build the newline-delimited JSON request supported by Faramesh v0.2.0."""
    governance_context = context or {}
    request = {
        "type": "govern",
        "call_id": str(governance_context.get("call_id") or uuid.uuid4()),
        "agent_id": agent_id,
        "session_id": str(
            governance_context.get("session_id") or governance_context.get("run_id") or ""
        ),
        "tool_id": tool_id,
        "args": params,
    }
    for field in (
        "action_type",
        "reasoning_summary",
        "principal_token",
        "delegation_token",
        "execution_timeout_ms",
        "model",
        "model_name",
        "model_fingerprint",
        "model_provider",
        "model_version",
    ):
        value = governance_context.get(field)
        if value is not None:
            request[field] = value
    return request


def gate_decide(
    agent_id: str,
    tool_id: str,
    params: dict,
    context: dict | None = None,
    socket_path: str = FAREMESH_SOCKET_PATH,
) -> GateDecision:
    """Ask Faramesh if a tool call is permitted. Returns immediately (sync)."""
    if not is_socket_reachable(socket_path):
        return GateDecision(outcome="ABSTAIN", effect="PERMIT", reason="governance unavailable")

    request = _govern_request(agent_id, tool_id, params, context)

    try:
        responses = _send_socket_request(socket_path, request, timeout=2.0)
        if not responses:
            return GateDecision(outcome="ABSTAIN", effect="PERMIT", reason="no governance response")

        resp = responses[0]
        if resp.get("error"):
            return GateDecision(
                outcome="HALT",
                effect="DENY",
                reason_code=resp.get("reason_code"),
                reason=str(resp["error"]),
            )
        effect = str(resp.get("effect", "DENY")).upper()

        if effect == "PERMIT":
            return GateDecision(
                outcome="EXECUTE",
                effect=effect,
                reason_code=resp.get("reason_code"),
                reason=resp.get("reason"),
                latency_ms=resp.get("latency_ms"),
            )
        elif effect == "DENY":
            return GateDecision(
                outcome="HALT",
                effect=effect,
                reason_code=resp.get("reason_code"),
                reason=resp.get("reason"),
            )
        else:  # DEFER
            return GateDecision(
                outcome="ABSTAIN",
                effect=effect,
                reason_code=resp.get("reason_code"),
                reason=resp.get("reason"),
                defer_token=resp.get("defer_token"),
            )
    except Exception:
        return GateDecision(outcome="ABSTAIN", effect="PERMIT", reason="governance error")


def submit_action(
    agent_id: str,
    tool_id: str,
    params: dict,
    context: dict | None = None,
    socket_path: str = FAREMESH_SOCKET_PATH,
) -> ActionResult:
    """Submit an action for governance review. Returns immediately with defer_token if DEFER."""
    if not is_socket_reachable(socket_path):
        return ActionResult(status="governance_unavailable", executed=True)

    request = _govern_request(agent_id, tool_id, params, context)

    try:
        responses = _send_socket_request(socket_path, request, timeout=5.0)
        if not responses:
            return ActionResult(status="no_response")

        resp = responses[0]
        if resp.get("error"):
            return ActionResult(status="error", error=str(resp["error"]))
        effect = str(resp.get("effect", "DENY")).upper()

        if effect == "PERMIT":
            return ActionResult(
                action_id=resp.get("call_id"),
                status="executed",
                executed=True,
            )
        elif effect == "DENY":
            return ActionResult(
                action_id=resp.get("call_id"),
                status="denied",
                executed=False,
                error=resp.get("denial_token") or "denied by policy",
            )
        else:  # DEFER
            return ActionResult(
                action_id=resp.get("call_id"),
                status="pending_approval",
                executed=False,
                defer_token=resp.get("defer_token"),
            )
    except Exception as e:
        return ActionResult(status="error", error=str(e))


def wait_for_decision(
    defer_token: str,
    timeout: float = 300.0,
    socket_path: str = FAREMESH_SOCKET_PATH,
    agent_id: str = "",
) -> ActionResult:
    """Wait for a deferred action to be approved or denied."""
    start = time.time()
    poll_interval = 1.0

    while time.time() - start < timeout:
        responses = _send_socket_request(
            socket_path,
            {
                "type": "poll_defer",
                "agent_id": agent_id,
                "defer_token": defer_token,
            },
            timeout=2.0,
        )
        if responses:
            response = responses[0]
            status = str(response.get("status") or "unknown").lower()
            if status in {"approved", "denied", "expired"}:
                return ActionResult(status=status, executed=status == "approved")
            if response.get("error"):
                return ActionResult(status="error", error=str(response["error"]))

        time.sleep(poll_interval)

    return ActionResult(status="timeout")


def execute_if_allowed(
    agent_id: str,
    tool_id: str,
    params: dict,
    executor: callable,
    context: dict | None = None,
    socket_path: str = FAREMESH_SOCKET_PATH,
) -> ActionResult:
    """Execute tool if governance permits, using submit_action for DEFER handling."""
    if not is_socket_reachable(socket_path):
        result = executor(tool_id, params)
        return ActionResult(executed=True, payload=result if result else {})

    decision = gate_decide(agent_id, tool_id, params, context, socket_path)

    if decision.outcome == "HALT":
        return ActionResult(
            status="blocked",
            executed=False,
            error=f"Tool {tool_id} denied: {decision.reason_code}",
        )

    if decision.outcome == "ABSTAIN" and decision.effect == "DEFER":
        if not decision.defer_token:
            return ActionResult(
                status="governance_error",
                executed=False,
                error="Faramesh returned DEFER without a defer token",
            )
        wait_result = wait_for_decision(
            decision.defer_token,
            socket_path=socket_path,
            agent_id=agent_id,
        )
        if wait_result.status == "approved":
            result = executor(tool_id, params)
            return ActionResult(executed=True, payload=result if result else {})
        return ActionResult(status="denied_by_approver", executed=False)

    result = executor(tool_id, params)
    return ActionResult(executed=True, payload=result if result else {})
