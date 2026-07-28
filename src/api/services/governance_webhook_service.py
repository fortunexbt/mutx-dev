"""
Governance webhook service for MUTX.

Handles:
- Streaming governance events from Faramesh Unix socket
- Mapping FPL `notify` directives to webhook subscriptions
- Dispatching governance events to registered webhooks
"""

import asyncio
import json
import logging
import os
from pathlib import Path
import socket
import threading
from typing import Optional

from src.api.services.webhook_handler import (
    create_governance_decision_payload,
    create_governance_pending_payload,
    create_governance_approved_payload,
    create_governance_denied_payload,
    create_governance_killed_payload,
)

logger = logging.getLogger(__name__)


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

GOVERNANCE_EVENT_TYPES = {
    "governance.decision.permit",
    "governance.decision.deny",
    "governance.decision.defer",
    "governance.pending",
    "governance.approved",
    "governance.denied",
    "governance.killed",
}


class GovernanceEventListener:
    """
    Streams governance events from Faramesh Unix socket.

    Uses the `audit_subscribe` socket command to receive live
    governance decisions and approval state changes.
    """

    def __init__(
        self,
        socket_path: str = FAREMESH_SOCKET_PATH,
        on_decision: Optional[callable] = None,
        on_pending: Optional[callable] = None,
        on_approved: Optional[callable] = None,
        on_denied: Optional[callable] = None,
        on_killed: Optional[callable] = None,
    ):
        self.socket_path = socket_path
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._callbacks = {
            "decision": on_decision,
            "pending": on_pending,
            "approved": on_approved,
            "denied": on_denied,
            "killed": on_killed,
        }

    def _is_socket_reachable(self, timeout: float = 0.5) -> bool:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(self.socket_path)
            sock.close()
            return True
        except (OSError, socket.error):
            return False

    def _send_socket_request(self, request: dict, timeout: float = 5.0) -> list[dict]:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(self.socket_path)
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

    def _process_response(self, resp: dict) -> None:
        if not isinstance(resp, dict):
            return

        effect = resp.get("effect")
        if effect in ("PERMIT", "DENY", "DEFER"):
            callback = self._callbacks.get("decision")
            if callback:
                payload = create_governance_decision_payload(
                    effect=effect,
                    agent_id=resp.get("agent_id", ""),
                    tool_id=resp.get("tool_id", ""),
                    rule_id=resp.get("rule_id"),
                    reason_code=resp.get("reason_code"),
                    defer_token=resp.get("defer_token"),
                    latency_ms=resp.get("latency_ms"),
                )
                try:
                    callback(payload)
                except Exception as e:
                    logger.error(f"Error in decision callback: {e}")

        defer_status = resp.get("status")
        if defer_status == "pending":
            callback = self._callbacks.get("pending")
            if callback:
                payload = create_governance_pending_payload(
                    defer_token=resp.get("defer_token", ""),
                    agent_id=resp.get("agent_id", ""),
                    tool_id=resp.get("tool_id", ""),
                    reason=resp.get("reason"),
                )
                try:
                    callback(payload)
                except Exception as e:
                    logger.error(f"Error in pending callback: {e}")
        elif defer_status == "approved":
            callback = self._callbacks.get("approved")
            if callback:
                payload = create_governance_approved_payload(
                    defer_token=resp.get("defer_token", ""),
                    agent_id=resp.get("agent_id", ""),
                )
                try:
                    callback(payload)
                except Exception as e:
                    logger.error(f"Error in approved callback: {e}")
        elif defer_status == "denied":
            callback = self._callbacks.get("denied")
            if callback:
                payload = create_governance_denied_payload(
                    defer_token=resp.get("defer_token", ""),
                    agent_id=resp.get("agent_id", ""),
                    reason=resp.get("reason"),
                )
                try:
                    callback(payload)
                except Exception as e:
                    logger.error(f"Error in denied callback: {e}")

        if resp.get("killed"):
            callback = self._callbacks.get("killed")
            if callback:
                payload = create_governance_killed_payload(
                    agent_id=resp.get("agent_id", ""),
                )
                try:
                    callback(payload)
                except Exception as e:
                    logger.error(f"Error in killed callback: {e}")

    def _stream_loop(self) -> None:
        while self._running:
            if not self._is_socket_reachable():
                threading.Event().wait(1.0)
                continue

            request = {"type": "audit_subscribe"}
            try:
                responses = self._send_socket_request(request, timeout=1.0)
                for resp in responses:
                    self._process_response(resp)
            except Exception as e:
                logger.warning(f"Error in governance stream: {e}")
                threading.Event().wait(0.5)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()
        logger.info("Governance event listener started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Governance event listener stopped")

    def is_running(self) -> bool:
        return self._running


class GovernanceWebhookDispatcher:
    """
    Dispatches governance events to registered webhooks.

    Integrates with the Faramesh event stream and maps
    FPL `notify` directives to webhook subscriptions.
    """

    def __init__(self):
        self._listener: Optional[GovernanceEventListener] = None
        self._webhook_queue: asyncio.Queue = asyncio.Queue()
        self._dispatcher_task: Optional[asyncio.Task] = None

    async def _dispatch_loop(self, db_session_factory) -> None:
        while self._listener and self._listener.is_running():
            try:
                payload = await asyncio.wait_for(self._webhook_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            try:
                from src.api.services.webhook_service import trigger_webhook_event
                from src.api.database import async_session_maker

                async with async_session_maker() as db:
                    event_type = payload.get("event_type")
                    if event_type in GOVERNANCE_EVENT_TYPES:
                        await trigger_webhook_event(
                            db,
                            user_id=None,
                            event=event_type,
                            payload=payload.get("data", {}),
                        )
            except Exception as e:
                logger.error(f"Error dispatching governance webhook: {e}")

    def _on_governance_event(self, payload: dict) -> None:
        asyncio.create_task(self._webhook_queue.put(payload))

    async def start(self, db_session_factory) -> None:
        if self._listener and self._listener.is_running():
            return

        self._listener = GovernanceEventListener(
            on_decision=self._on_governance_event,
            on_pending=self._on_governance_event,
            on_approved=self._on_governance_event,
            on_denied=self._on_governance_event,
            on_killed=self._on_governance_event,
        )
        self._listener.start()

        self._dispatcher_task = asyncio.create_task(self._dispatch_loop(db_session_factory))
        logger.info("Governance webhook dispatcher started")

    async def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
            self._dispatcher_task = None

        logger.info("Governance webhook dispatcher stopped")

    def is_running(self) -> bool:
        return self._listener is not None and self._listener.is_running()


_dispatcher: Optional[GovernanceWebhookDispatcher] = None


def get_governance_webhook_dispatcher() -> GovernanceWebhookDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = GovernanceWebhookDispatcher()
    return _dispatcher


async def start_governance_webhooks(db_session_factory) -> None:
    dispatcher = get_governance_webhook_dispatcher()
    await dispatcher.start(db_session_factory)


async def stop_governance_webhooks() -> None:
    dispatcher = get_governance_webhook_dispatcher()
    await dispatcher.stop()
