"""
MUTX Agent SDK - Client for agents to connect to MUTX platform.

This module provides the MutxAgentClient for agents to:
- Register with MUTX
- Send heartbeats
- Report metrics
- Receive commands from MUTX
"""

import asyncio
import logging
import platform
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import httpx

from mutx._http import DEFAULT_BASE_URL, api_path, normalize_api_base_url
from mutx.guardrails import (
    GuardrailMiddleware,
)
from mutx.policy import MutxPolicyClient

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    """Information about the registered agent."""

    agent_id: str
    name: str
    api_key: str
    status: str
    registered_at: datetime


@dataclass
class Command:
    """A command received from MUTX."""

    command_id: str
    action: str
    parameters: dict
    received_at: datetime


@dataclass
class AgentMetrics:
    """Metrics to report to MUTX."""

    cpu_usage: float = 0.0
    memory_usage: float = 0.0  # MB
    uptime_seconds: float = 0.0
    requests_processed: int = 0
    errors_count: int = 0
    custom: dict = field(default_factory=dict)


class MutxAgentClient:
    """
    Client for agents to connect to MUTX platform.

    Usage:
        client = MutxAgentClient(
            mutx_url="https://api.mutx.dev",
            api_key="your-agent-api-key"  # Or use agent_id for registration
        )

        # Register the agent
        await client.register(name="my-agent", description="My AI agent")

        # Start heartbeat loop
        client.start_heartbeat(interval=30)

        # Report metrics
        await client.report_metrics(AgentMetrics(cpu_usage=25.0, memory_usage=512.0))

        # Poll for commands
        commands = await client.poll_commands()

        # Cleanup
        client.stop()
    """

    def __init__(
        self,
        mutx_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout: float = 30.0,
        guardrail_middleware: Optional[GuardrailMiddleware] = None,
        policy_client: Optional[MutxPolicyClient] = None,
    ):
        self.mutx_url = mutx_url.rstrip("/")
        self.api_base_url = normalize_api_base_url(mutx_url)
        self.api_key = api_key
        self.agent_id = agent_id
        self.timeout = timeout

        self._client: Optional[httpx.AsyncClient] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_running = False
        self._heartbeat_interval = 30
        self._registered = False
        self._start_time = time.time()
        self._requests_processed = 0
        self._errors_count = 0

        # Callback for handling commands
        self._command_callback: Optional[Callable[[Command], Any]] = None

        # Guardrail middleware
        self._guardrail_middleware = guardrail_middleware
        self._policy_client = policy_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.api_base_url,
                timeout=self.timeout,
                headers=headers,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def register(
        self,
        name: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AgentInfo:
        """
        Register this agent with MUTX.

        Args:
            name: Agent name
            description: Agent description
            metadata: Additional metadata

        Returns:
            AgentInfo with agent_id and api_key
        """
        client = await self._get_client()

        payload = {
            "name": name,
            "description": description or "",
            "metadata": metadata or {},
            "capabilities": ["heartbeat", "metrics", "commands"],
        }

        try:
            response = await client.post("agents/register", json=payload)
            response.raise_for_status()
            data = response.json()

            self.agent_id = data["agent_id"]
            self.api_key = data["api_key"]
            self._registered = True

            # Update headers with new API key
            client.headers["Authorization"] = f"Bearer {self.api_key}"

            logger.info(f"Registered agent: {self.agent_id}")

            return AgentInfo(
                agent_id=self.agent_id,
                name=name,
                api_key=self.api_key,
                status=data.get("status", "registered"),
                registered_at=datetime.now(timezone.utc),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Try alternative endpoint for existing agent key
                raise ValueError(
                    "Invalid API key. Provide an agent_api_key or use register() first."
                )
            raise

    async def connect(
        self,
        agent_id: str,
        api_key: str,
    ) -> bool:
        """
        Connect using existing agent credentials.

        Args:
            agent_id: The agent ID
            api_key: The agent API key

        Returns:
            True if connection successful
        """
        self.agent_id = agent_id
        self.api_key = api_key

        client = await self._get_client()
        client.headers["Authorization"] = f"Bearer {self.api_key}"

        # Verify connection with a simple request
        try:
            response = await client.get(api_path("agents/{agent_id}/status", agent_id=agent_id))
            response.raise_for_status()
            self._registered = True
            logger.info(f"Connected to agent: {self.agent_id}")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to connect: {e}")
            return False

    async def heartbeat(
        self,
        status: str = "running",
        message: Optional[str] = None,
    ) -> dict:
        """
        Send a heartbeat to MUTX.

        Args:
            status: Agent status (running, idle, error, stopped)
            message: Optional status message

        Returns:
            Response from MUTX
        """
        if not self.agent_id:
            raise ValueError("Agent not registered. Call register() or connect() first.")

        client = await self._get_client()

        payload = {
            "agent_id": self.agent_id,
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": platform.system(),
            "hostname": platform.node(),
        }

        try:
            response = await client.post("agents/heartbeat", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Heartbeat failed: {e}")
            raise

    async def report_metrics(
        self,
        metrics: AgentMetrics,
    ) -> dict:
        """
        Report metrics to MUTX.

        Args:
            metrics: AgentMetrics object with current metrics

        Returns:
            Response from MUTX
        """
        if not self.agent_id:
            raise ValueError("Agent not registered. Call register() or connect() first.")

        client = await self._get_client()

        payload = {
            "agent_id": self.agent_id,
            "cpu_usage": metrics.cpu_usage,
            "memory_usage": metrics.memory_usage,
            "uptime_seconds": metrics.uptime_seconds or (time.time() - self._start_time),
            "requests_processed": metrics.requests_processed or self._requests_processed,
            "errors_count": metrics.errors_count or self._errors_count,
            "custom": metrics.custom,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            response = await client.post("agents/metrics", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Metrics report failed: {e}")
            raise

    async def poll_commands(
        self,
        since: Optional[datetime] = None,
    ) -> list[Command]:
        """
        Poll for pending commands from MUTX.

        Args:
            since: Only return commands received after this time

        Returns:
            List of Command objects
        """
        if not self.agent_id:
            raise ValueError("Agent not registered. Call register() or connect() first.")

        client = await self._get_client()

        params = {"agent_id": self.agent_id}
        if since:
            params["since"] = since.isoformat()

        try:
            response = await client.get("agents/commands", params=params)
            response.raise_for_status()
            data = response.json()

            commands = []
            for cmd in data.get("commands", []):
                commands.append(
                    Command(
                        command_id=cmd["command_id"],
                        action=cmd["action"],
                        parameters=cmd.get("parameters", {}),
                        received_at=datetime.fromisoformat(cmd["received_at"]),
                    )
                )

            return commands
        except httpx.HTTPError as e:
            logger.error(f"Command poll failed: {e}")
            return []

    async def acknowledge_command(
        self,
        command_id: str,
        success: bool = True,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> dict:
        """
        Acknowledge a command execution.

        Args:
            command_id: The command ID
            success: Whether execution was successful
            result: Result data
            error: Error message if failed

        Returns:
            Response from MUTX
        """
        if not self.agent_id:
            raise ValueError("Agent not registered.")

        client = await self._get_client()

        payload = {
            "command_id": command_id,
            "agent_id": self.agent_id,
            "success": success,
            "result": result,
            "error": error,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            response = await client.post("agents/commands/acknowledge", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Command acknowledgment failed: {e}")
            raise

    async def log(
        self,
        level: str,
        message: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Send a log entry to MUTX.

        Args:
            level: Log level (debug, info, warning, error)
            message: Log message
            metadata: Additional metadata

        Returns:
            Response from MUTX
        """
        if not self.agent_id:
            raise ValueError("Agent not registered.")

        client = await self._get_client()

        payload = {
            "agent_id": self.agent_id,
            "level": level,
            "message": message,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            response = await client.post("agents/logs", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Log failed: {e}")
            raise

    def start_heartbeat(
        self,
        interval: int = 30,
        status: str = "running",
    ):
        """
        Start automatic heartbeat loop in background thread.

        Args:
            interval: Heartbeat interval in seconds
            status: Status to send with heartbeat
        """
        self._heartbeat_interval = interval
        self._heartbeat_running = True

        def heartbeat_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            while self._heartbeat_running:
                try:
                    loop.run_until_complete(self.heartbeat(status=status))
                except Exception as e:
                    logger.error(f"Auto-heartbeat error: {e}")
                time.sleep(self._heartbeat_interval)
            loop.close()

        self._heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        logger.info(f"Started heartbeat loop (interval={interval}s)")

    def stop_heartbeat(self):
        """Stop the automatic heartbeat loop."""
        self._heartbeat_running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
            self._heartbeat_thread = None
        logger.info("Stopped heartbeat loop")

    def set_command_callback(self, callback: Callable[[Command], Any]):
        """
        Set callback for handling commands.

        Args:
            callback: Async function that receives Command and returns result
        """
        self._command_callback = callback

    async def run_command_loop(
        self,
        poll_interval: int = 5,
        callback: Optional[Callable[[Command], Any]] = None,
    ):
        """
        Run the command polling loop.

        Args:
            poll_interval: How often to poll for commands (seconds)
            callback: Function to handle commands
        """
        callback = callback or self._command_callback
        if not callback:
            raise ValueError(
                "No command callback set. Use set_command_callback() or pass callback parameter."
            )

        last_poll = datetime.now(timezone.utc)

        while True:
            try:
                commands = await self.poll_commands(since=last_poll)

                for command in commands:
                    try:
                        result = await callback(command)
                        await self.acknowledge_command(
                            command.command_id,
                            success=True,
                            result=result if isinstance(result, dict) else {"result": str(result)},
                        )
                    except Exception as e:
                        logger.error(f"Command execution failed: {e}")
                        await self.acknowledge_command(
                            command.command_id,
                            success=False,
                            error=str(e),
                        )

                if commands:
                    last_poll = datetime.now(timezone.utc)

            except Exception as e:
                logger.error(f"Command loop error: {e}")

            await asyncio.sleep(poll_interval)

    @property
    def is_registered(self) -> bool:
        return self._registered

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time

    def increment_requests(self):
        self._requests_processed += 1

    def increment_errors(self):
        self._errors_count += 1

    def check_input(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Check input text against guardrails before LLM processing.

        Args:
            text: The input text to check.
            context: Additional context for guardrail evaluation.

        Raises:
            GuardrailViolationError: If any guardrail blocks the text.
        """
        if self._guardrail_middleware is None:
            return

        self._guardrail_middleware.check_input_text(text, context)

    def check_output(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Check output text against guardrails before returning.

        Args:
            text: The output text to check.
            context: Additional context for guardrail evaluation.

        Raises:
            GuardrailViolationError: If any guardrail blocks the text.
        """
        if self._guardrail_middleware is None:
            return

        self._guardrail_middleware.check_output_text(text, context)


class MutxAgentSyncClient:
    """
    Synchronous version of MutxAgentClient for simpler use cases.
    """

    def __init__(
        self,
        mutx_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout: float = 30.0,
        guardrail_middleware: Optional[GuardrailMiddleware] = None,
        policy_client: Optional[MutxPolicyClient] = None,
    ):
        self.mutx_url = mutx_url.rstrip("/")
        self.api_base_url = normalize_api_base_url(mutx_url)
        self.api_key = api_key
        self.agent_id = agent_id
        self.timeout = timeout
        self._registered = False
        self._start_time = time.time()
        self._requests_processed = 0
        self._errors_count = 0
        self._guardrail_middleware = guardrail_middleware
        self._policy_client = policy_client

    def _get_client(self) -> httpx.Client:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return httpx.Client(
            base_url=self.api_base_url,
            timeout=self.timeout,
            headers=headers,
        )

    def register(
        self,
        name: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AgentInfo:
        """Synchronous register."""
        with self._get_client() as client:
            payload = {
                "name": name,
                "description": description or "",
                "metadata": metadata or {},
            }
            response = client.post("agents/register", json=payload)
            response.raise_for_status()
            data = response.json()

            self.agent_id = data["agent_id"]
            self.api_key = data["api_key"]
            self._registered = True

            return AgentInfo(
                agent_id=self.agent_id,
                name=name,
                api_key=self.api_key,
                status=data.get("status", "registered"),
                registered_at=datetime.now(timezone.utc),
            )

    def heartbeat(
        self,
        status: str = "running",
        message: Optional[str] = None,
    ) -> dict:
        """Synchronous heartbeat."""
        if not self.agent_id:
            raise ValueError("Agent not registered.")

        with self._get_client() as client:
            payload = {
                "agent_id": self.agent_id,
                "status": status,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            response = client.post("agents/heartbeat", json=payload)
            response.raise_for_status()
            return response.json()

    def report_metrics(
        self,
        cpu_usage: float = 0.0,
        memory_usage: float = 0.0,
        custom: Optional[dict] = None,
    ) -> dict:
        """Synchronous metrics reporting."""
        if not self.agent_id:
            raise ValueError("Agent not registered.")

        with self._get_client() as client:
            payload = {
                "agent_id": self.agent_id,
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "uptime_seconds": time.time() - self._start_time,
                "requests_processed": self._requests_processed,
                "errors_count": self._errors_count,
                "custom": custom or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            response = client.post("agents/metrics", json=payload)
            response.raise_for_status()
            return response.json()

    def log(
        self,
        level: str,
        message: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Synchronous logging."""
        if not self.agent_id:
            raise ValueError("Agent not registered.")

        with self._get_client() as client:
            payload = {
                "agent_id": self.agent_id,
                "level": level,
                "message": message,
                "metadata": metadata or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            response = client.post("agents/logs", json=payload)
            response.raise_for_status()
            return response.json()

    @property
    def is_registered(self) -> bool:
        return self._registered

    def check_input(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Check input text against guardrails before LLM processing.

        Args:
            text: The input text to check.
            context: Additional context for guardrail evaluation.

        Raises:
            GuardrailViolationError: If any guardrail blocks the text.
        """
        if self._guardrail_middleware is None:
            return

        self._guardrail_middleware.check_input_text(text, context)

    def check_output(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Check output text against guardrails before returning.

        Args:
            text: The output text to check.
            context: Additional context for guardrail evaluation.

        Raises:
            GuardrailViolationError: If any guardrail blocks the text.
        """
        if self._guardrail_middleware is None:
            return

        self._guardrail_middleware.check_output_text(text, context)


# Convenience function for quick setup
async def create_agent_client(
    mutx_url: str = DEFAULT_BASE_URL,
    agent_name: str = "default-agent",
    agent_description: str = "",
    api_key: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> MutxAgentClient:
    """
    Create and register an agent client.

    Usage:
        client = await create_agent_client(
            mutx_url="https://api.mutx.dev",
            agent_name="my-agent",
        )
        client.start_heartbeat()
    """
    client = MutxAgentClient(mutx_url=mutx_url, api_key=api_key, agent_id=agent_id)

    if api_key and agent_id:
        await client.connect(agent_id, api_key)
    else:
        await client.register(name=agent_name, description=agent_description)

    return client


__all__ = [
    "MutxAgentClient",
    "MutxAgentSyncClient",
    "AgentInfo",
    "Command",
    "AgentMetrics",
    "create_agent_client",
    "run_with_approval",
    "ApprovalRejectedError",
    "ApprovalTimeoutError",
]


# ------------------------------------------------------------------
# Human-in-the-loop approval context manager
# ------------------------------------------------------------------


class ApprovalRejectedError(Exception):
    """Raised when an approval request is rejected by an approver."""

    def __init__(self, request_id: str, approver: str, comment: Optional[str] = None):
        self.request_id = request_id
        self.approver = approver
        self.comment = comment
        super().__init__(f"Approval request {request_id} was rejected by {approver}")


class ApprovalTimeoutError(Exception):
    """Raised when an approval request times out before being resolved."""

    def __init__(self, request_id: str, timeout_seconds: int):
        self.request_id = request_id
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Approval request {request_id} timed out after {timeout_seconds}s")


class run_with_approval:  # noqa: N801
    """
    Async context manager that submits an approval request and polls until
    the request is resolved (approved, rejected, or expired).

    Usage::

        async with run_with_approval(
            api_key="...",
            base_url="https://api.mutx.dev",
            approval_request={
                "agent_id": "agent-123",
                "session_id": "session-456",
                "action_type": "deploy",
                "payload": {"target": "production"},
            },
            timeout_seconds=1800,  # 30 minutes
        ) as approval:
            # approval.result.status is "APPROVED"
            pass  # proceed with the approved action

    On ``reject`` the context manager raises ``ApprovalRejectedError``.
    On timeout it raises ``ApprovalTimeoutError``.
    """

    DEFAULT_TIMEOUT_SECONDS = 1800  # 30 minutes
    DEFAULT_POLL_INTERVAL_SECONDS = 5

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        approval_request: dict,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.api_base_url = normalize_api_base_url(base_url)
        self.request_payload = approval_request
        self.timeout_seconds = timeout_seconds
        self.poll_interval = poll_interval_seconds
        self._client: Optional[httpx.AsyncClient] = None
        self._request_id: Optional[str] = None
        self._result: Optional[dict] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.api_base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def _submit(self) -> str:
        """POST to /v1/approvals and return the request ID."""
        client = await self._get_client()
        response = await client.post("approvals", json=self.request_payload)
        response.raise_for_status()
        data = response.json()
        return data["id"]

    async def _poll(self) -> dict:
        """GET /v1/approvals/{request_id} and return the full approval record."""
        client = await self._get_client()
        response = await client.get(api_path("approvals/{request_id}", request_id=self._request_id))
        response.raise_for_status()
        return response.json()

    async def __aenter__(self) -> "run_with_approval":
        # 1. Submit the approval request
        self._request_id = await self._submit()
        logger.info(
            "Approval request submitted: id=%s, timeout=%ds",
            self._request_id,
            self.timeout_seconds,
        )

        # 2. Poll until resolved
        start = asyncio.get_event_loop().time()
        while True:
            await asyncio.sleep(self.poll_interval)

            approval = await self._poll()
            status = approval.get("status", "").upper()

            if status == "APPROVED":
                self._result = approval
                logger.info("Approval request %s approved", self._request_id)
                return self

            if status == "REJECTED":
                raise ApprovalRejectedError(
                    request_id=self._request_id,
                    approver=approval.get("approver", "unknown"),
                    comment=approval.get("comment"),
                )

            if status == "EXPIRED":
                raise ApprovalTimeoutError(
                    request_id=self._request_id,
                    timeout_seconds=self.timeout_seconds,
                )

            # Still PENDING — check timeout
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed >= self.timeout_seconds:
                raise ApprovalTimeoutError(
                    request_id=self._request_id,
                    timeout_seconds=self.timeout_seconds,
                )

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def result(self) -> Optional[dict]:
        """The final approval record (only valid after entering the context)."""
        return self._result
