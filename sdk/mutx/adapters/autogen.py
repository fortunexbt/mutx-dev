"""AutoGen adapter for MUTX observability and agent runtime.

This module provides:
- MutxAutoGenCallback: Callback for tracing AutoGen agent executions
- register_with_autogen(): Attach MUTX callback to an AutoGen agent

Example:
    >>> from autogen import ConversableAgent
    >>> from mutx.adapters.autogen import MutxAutoGenCallback, register_with_autogen
    >>>
    >>> callback = MutxAutoGenCallback(
    ...     api_url="https://api.mutx.dev",
    ...     api_key="...",
    ...     agent_name="my-agent",
    ... )
    >>> agent = ConversableAgent("assistant", llm_config={...})
    >>> register_with_autogen(agent, "https://api.mutx.dev", "...")
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from mutx._http import normalize_api_base_url
from mutx.telemetry import get_tracer, span

if TYPE_CHECKING:
    pass


class MutxAutoGenCallback:
    """Callback handler for tracing AutoGen agent executions via OTel.

    This handler emits spans for:
    - Agent message received (mutx.autogen.message)
    - Agent teardown (mutx.autogen.teardown)
    - Tool calls (mutx.tool.call)
    - LLM calls (mutx.llm.call)
    - Audit events via POST /v1/events

    Attributes:
        api_url: Base URL for the MUTX API.
        api_key: API key for authentication.
        agent_name: Name of the agent for span attribution.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        agent_name: str = "autogen-agent",
    ):
        """Initialize the callback handler.

        Args:
            api_url: Base URL for the MUTX API.
            api_key: API key for authentication.
            agent_name: Name of the agent for span attribution.
        """
        self.api_url = api_url.rstrip("/")
        self.api_base_url = normalize_api_base_url(api_url)
        self.api_key = api_key
        self.agent_name = agent_name
        self._http = httpx.Client(
            base_url=self.api_base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._tracer = get_tracer("mutx.autogen")

    def on_agent_message_received(self, message: Any, sender: Any, **kwargs: Any) -> None:
        """Handle incoming agent message with OTel span wrapping.

        Args:
            message: The message received by the agent.
            sender: The sender of the message.
            **kwargs: Additional callback parameters.
        """
        with span(
            "mutx.autogen.message",
            attributes={
                "agent.name": self.agent_name,
                "message.type": type(message).__name__,
                "sender.name": getattr(sender, "name", str(sender)),
            },
        ):
            event = {
                "event_type": "autogen_message_received",
                "agent_name": self.agent_name,
                "sender": getattr(sender, "name", str(sender)),
                "message_type": type(message).__name__,
                "timestamp": datetime.now().isoformat(),
            }

            try:
                self._http.post("events", json=event)
            except httpx.HTTPError:
                pass  # Best effort audit logging

    def on_agent_teardown(self, agent: Any, **kwargs: Any) -> None:
        """Handle agent teardown with OTel span.

        Args:
            agent: The agent being torn down.
            **kwargs: Additional callback parameters.
        """
        with span(
            "mutx.autogen.teardown",
            attributes={
                "agent.name": self.agent_name,
            },
        ):
            event = {
                "event_type": "autogen_agent_teardown",
                "agent_name": self.agent_name,
                "timestamp": datetime.now().isoformat(),
            }

            try:
                self._http.post("events", json=event)
            except httpx.HTTPError:
                pass  # Best effort audit logging

    def wrap_tool_call(self, tool_name: str, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Wrap a tool call with OTel span.

        Args:
            tool_name: Name of the tool being called.
            func: The tool function to wrap.
            *args: Positional arguments to pass to the tool.
            **kwargs: Keyword arguments to pass to the tool.

        Returns:
            The result of the tool call.
        """
        with span(
            "mutx.tool.call",
            attributes={
                "tool.name": tool_name,
                "agent.name": self.agent_name,
            },
        ):
            try:
                result = func(*args, **kwargs)
                return result
            except Exception:
                # Record exception in span
                with span("mutx.tool.error", {"tool.name": tool_name}):
                    pass
                raise

    def wrap_llm_call(self, model: str, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Wrap an LLM call with OTel span.

        Args:
            model: The model name being used.
            func: The LLM call function to wrap.
            *args: Positional arguments to pass to the LLM call.
            **kwargs: Keyword arguments to pass to the LLM call.

        Returns:
            The result of the LLM call.
        """
        with span(
            "mutx.llm.call",
            attributes={
                "llm.model": model,
                "agent.name": self.agent_name,
            },
        ):
            result = func(*args, **kwargs)

            event = {
                "event_type": "autogen_llm_call",
                "agent_name": self.agent_name,
                "model": model,
                "timestamp": datetime.now().isoformat(),
            }

            try:
                self._http.post("events", json=event)
            except httpx.HTTPError:
                pass  # Best effort audit logging

            return result

    def __del__(self) -> None:
        """Clean up HTTP client on deletion."""
        try:
            self._http.close()
        except Exception:
            pass


def register_with_autogen(agent: Any, mutx_api_url: str, api_key: str) -> MutxAutoGenCallback:
    """Register a MUTX callback with an AutoGen agent.

    This function creates and attaches a MutxAutoGenCallback to an AutoGen agent,
    enabling OTel tracing and audit logging for the agent's executions.

    Args:
        agent: An AutoGen agent instance (e.g., ConversableAgent).
        mutx_api_url: Base URL for the MUTX API.
        api_key: API key for authentication.

    Returns:
        The MutxAutoGenCallback instance attached to the agent.

    Raises:
        ImportError: If autogen is not installed.

    Example:
        >>> from autogen import ConversableAgent
        >>> agent = ConversableAgent("assistant", llm_config={...})
        >>> callback = register_with_autogen(
        ...     agent,
        ...     "https://api.mutx.dev",
        ...     "mk-..."
        ... )
    """
    # Verify autogen is available
    try:
        import autogen  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "autogen is required for register_with_autogen(). Install with: pip install mutx[autogen]"
        ) from e

    callback = MutxAutoGenCallback(
        api_url=mutx_api_url,
        api_key=api_key,
        agent_name=getattr(agent, "name", "autogen-agent") or "autogen-agent",
    )

    # Register callback with the agent
    if hasattr(agent, "register_message_handler"):
        agent.register_message_handler(callback.on_agent_message_received)

    if hasattr(agent, "register_teardown_handler"):
        agent.register_teardown_handler(callback.on_agent_teardown)

    return callback


__all__ = [
    "MutxAutoGenCallback",
    "register_with_autogen",
]
