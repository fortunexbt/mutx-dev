"""CrewAI adapter for MUTX observability and agent runtime.

This module provides:
- MutxCrewAICallbackHandler: Callback handler for tracing CrewAI executions
- run_crew(): Execute a crew with MUTX callback attached

Example:
    >>> from crewai import Crew, Agent, Task
    >>> from mutx.adapters.crewai import MutxCrewAICallbackHandler, run_crew
    >>>
    >>> handler = MutxCrewAICallbackHandler(
    ...     api_url="https://api.mutx.dev",
    ...     api_key="...",
    ...     crew_name="my-crew",
    ... )
    >>> crew = Crew(agents=[...], tasks=[...])
    >>> result = run_crew(crew, {"topic": "AI"})
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from mutx._http import normalize_api_base_url
from mutx.telemetry import get_tracer

if TYPE_CHECKING:
    pass


class MutxCrewAICallbackHandler:
    """Callback handler for tracing CrewAI agent executions via OTel.

    This handler emits spans for:
    - Crew start/end (mutx.crew.start, mutx.crew.end)
    - Agent start/end (logged to MUTX audit store)
    - Task start/end (logged to MUTX audit store)

    Attributes:
        api_url: Base URL for the MUTX API.
        api_key: API key for authentication.
        crew_name: Name of the crew for span attribution.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        crew_name: str = "crewai-crew",
    ):
        """Initialize the callback handler.

        Args:
            api_url: Base URL for the MUTX API.
            api_key: API key for authentication.
            crew_name: Name of the crew for span attribution.
        """
        self.api_url = api_url.rstrip("/")
        self.api_base_url = normalize_api_base_url(api_url)
        self.api_key = api_key
        self.crew_name = crew_name
        self._http = httpx.Client(
            base_url=self.api_base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._tracer = get_tracer("mutx.crewai")

    def on_crew_start(self, crew: Any, **kwargs: Any) -> None:
        """Emit span when crew execution starts.

        Args:
            crew: The Crew instance starting execution.
            **kwargs: Additional callback parameters.
        """
        span_name = "mutx.crew.start"
        attributes = {
            "crew.name": self.crew_name,
            "crew.agent_count": len(getattr(crew, "agents", [])),
            "crew.task_count": len(getattr(crew, "tasks", [])),
        }
        self._tracer.start_span(span_name, attributes=attributes)

    def on_crew_end(self, crew: Any, result: Any = None, **kwargs: Any) -> None:
        """End span when crew execution completes.

        Args:
            crew: The Crew instance that completed.
            result: The result of the crew execution.
            **kwargs: Additional callback parameters.
        """
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span:
                span.set_attribute("crew.success", True)
                span.end()
        except Exception:
            pass  # Best effort telemetry recording

    def on_agent_start(self, agent: Any, **kwargs: Any) -> None:
        """Log agent start to MUTX audit store.

        Args:
            agent: The Agent instance starting.
            **kwargs: Additional callback parameters.
        """
        event = {
            "event_type": "crew_agent_start",
            "crew_name": self.crew_name,
            "agent_role": getattr(agent, "role", "unknown"),
            "agent_goal": getattr(agent, "goal", ""),
            "timestamp": datetime.now().isoformat(),
        }

        try:
            self._http.post("events", json=event)
        except httpx.HTTPError:
            pass  # Fail silently to not interrupt crew execution

    def on_agent_end(self, agent: Any, result: Any = None, **kwargs: Any) -> None:
        """Log agent end to MUTX audit store.

        Args:
            agent: The Agent instance that ended.
            result: The result of the agent execution.
            **kwargs: Additional callback parameters.
        """
        event = {
            "event_type": "crew_agent_end",
            "crew_name": self.crew_name,
            "agent_role": getattr(agent, "role", "unknown"),
            "timestamp": datetime.now().isoformat(),
        }

        try:
            self._http.post("events", json=event)
        except httpx.HTTPError:
            pass  # Fail silently

    def on_task_start(self, task: Any, **kwargs: Any) -> None:
        """Log task start to MUTX audit store.

        Args:
            task: The Task instance starting.
            **kwargs: Additional callback parameters.
        """
        event = {
            "event_type": "crew_task_start",
            "crew_name": self.crew_name,
            "task_description": getattr(task, "description", ""),
            "task_expected_output": getattr(task, "expected_output", ""),
            "timestamp": datetime.now().isoformat(),
        }

        try:
            self._http.post("events", json=event)
        except httpx.HTTPError:
            pass  # Fail silently

    def on_task_end(self, task: Any, result: Any = None, **kwargs: Any) -> None:
        """Log task end to MUTX audit store.

        Args:
            task: The Task instance that completed.
            result: The result of the task execution.
            **kwargs: Additional callback parameters.
        """
        event = {
            "event_type": "crew_task_end",
            "crew_name": self.crew_name,
            "task_description": getattr(task, "description", ""),
            "timestamp": datetime.now().isoformat(),
        }

        try:
            self._http.post("events", json=event)
        except httpx.HTTPError:
            pass  # Fail silently

    def __del__(self) -> None:
        """Clean up HTTP client on deletion."""
        try:
            self._http.close()
        except Exception:
            pass


def run_crew(
    crew: Any, inputs: dict[str, Any], *, api_key: str = "", api_url: str = "https://api.mutx.dev"
) -> Any:
    """Execute a CrewAI crew with MUTX callback attached.

    Args:
        crew: A CrewAI Crew instance.
        inputs: Dictionary of inputs to pass to the crew kickoff.
        api_key: MUTX API key for authentication. Reads from MUTX_API_KEY env var if empty.
        api_url: MUTX API base URL.

    Returns:
        The result of the crew execution.

    Raises:
        ImportError: If crewai is not installed.
        ValueError: If no API key is provided or found in environment.

    Example:
        >>> crew = Crew(agents=[researcher, writer], tasks=[...])
        >>> result = run_crew(crew, {"topic": "AI ethics"}, api_key="mutx_...")
    """
    import os

    # Resolve API key: explicit param > env var > error
    resolved_key = api_key or os.environ.get("MUTX_API_KEY", "")
    if not resolved_key:
        raise ValueError(
            "MUTX API key required. Pass api_key parameter or set MUTX_API_KEY environment variable."
        )

    # Verify crewai is available
    try:
        from crewai import Crew  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "crewai is required for run_crew(). Install with: pip install mutx[crewai]"
        ) from e

    # Access crew attributes safely
    crew_name = getattr(crew, "name", "crewai-crew") or "crewai-crew"

    handler = MutxCrewAICallbackHandler(
        api_url=api_url,
        api_key=resolved_key,
        crew_name=crew_name,
    )

    # Attach callbacks to agents if supported
    try:
        for agent in getattr(crew, "agents", []):
            if hasattr(agent, "callback") and agent.callback is None:
                agent.callback = handler
    except Exception:
        pass  # Best effort callback attachment

    # Execute the crew
    result = crew.kickoff(inputs=inputs)

    return result


__all__ = [
    "MutxCrewAICallbackHandler",
    "run_crew",
]
