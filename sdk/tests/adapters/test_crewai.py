"""Contract tests for sdk/mutx/adapters/crewai.py.

These tests verify the MutxCrewAICallbackHandler and run_crew()
integrate correctly with CrewAI callbacks and emit OTel spans/events.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestMutxCrewAICallbackHandler:
    """Tests for MutxCrewAICallbackHandler."""

    def test_init_sets_attributes(self):
        """Test that handler initializes with correct attributes."""
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )

        assert handler.api_url == "https://api.mutx.dev"
        assert handler.api_key == "test-key"
        assert handler.crew_name == "test-crew"
        assert handler._http is not None

    def test_init_strips_trailing_slash(self):
        """Test that api_url trailing slash is stripped."""
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev/",
            api_key="test-key",
            crew_name="test-crew",
        )

        assert handler.api_url == "https://api.mutx.dev"

    def test_on_crew_start_emits_span(self):
        """Test that on_crew_start creates a span via telemetry."""
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )

        mock_crew = MagicMock()
        mock_crew.agents = [MagicMock(), MagicMock()]
        mock_crew.tasks = [MagicMock(), MagicMock(), MagicMock()]

        with patch.object(handler._tracer, "start_span") as mock_start_span:
            mock_span = MagicMock()
            mock_start_span.return_value = mock_span

            handler.on_crew_start(mock_crew)

            mock_start_span.assert_called_once()
            call_args = mock_start_span.call_args
            assert call_args[0][0] == "mutx.crew.start"
            assert call_args[1]["attributes"]["crew.name"] == "test-crew"
            assert call_args[1]["attributes"]["crew.agent_count"] == 2
            assert call_args[1]["attributes"]["crew.task_count"] == 3

    def test_on_crew_end_ends_span(self):
        """Test that on_crew_end properly ends the span."""
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )

        mock_crew = MagicMock()

        with patch("opentelemetry.trace") as mock_trace:
            mock_span = MagicMock()
            mock_trace.get_current_span.return_value = mock_span

            handler.on_crew_end(mock_crew, result="test-result")

            mock_span.set_attribute.assert_called_with("crew.success", True)
            mock_span.end.assert_called_once()

    def test_on_agent_start_logs_event(self):
        """Test that on_agent_start logs to audit store."""
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )

        mock_agent = MagicMock()
        mock_agent.role = "Researcher"
        mock_agent.goal = "Research things"

        with patch.object(handler._http, "post") as mock_post:
            handler.on_agent_start(mock_agent)

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "events"
            event = call_args[1]["json"]
            assert event["event_type"] == "crew_agent_start"
            assert event["crew_name"] == "test-crew"
            assert event["agent_role"] == "Researcher"

    def test_on_agent_end_logs_event(self):
        """Test that on_agent_end logs to audit store."""
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )

        mock_agent = MagicMock()
        mock_agent.role = "Writer"

        with patch.object(handler._http, "post") as mock_post:
            handler.on_agent_end(mock_agent, result="output")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            event = call_args[1]["json"]
            assert event["event_type"] == "crew_agent_end"
            assert event["agent_role"] == "Writer"

    def test_on_task_start_logs_event(self):
        """Test that on_task_start logs to audit store."""
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )

        mock_task = MagicMock()
        mock_task.description = "Research AI trends"
        mock_task.expected_output = "Summary report"

        with patch.object(handler._http, "post") as mock_post:
            handler.on_task_start(mock_task)

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            event = call_args[1]["json"]
            assert event["event_type"] == "crew_task_start"
            assert event["task_description"] == "Research AI trends"

    def test_on_task_end_logs_event(self):
        """Test that on_task_end logs to audit store."""
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )

        mock_task = MagicMock()
        mock_task.description = "Write article"

        with patch.object(handler._http, "post") as mock_post:
            handler.on_task_end(mock_task, result="article-content")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            event = call_args[1]["json"]
            assert event["event_type"] == "crew_task_end"
            assert event["task_description"] == "Write article"

    def test_audit_log_failure_does_not_raise(self):
        """Test that audit log failures don't raise exceptions."""
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )

        mock_agent = MagicMock()
        mock_agent.role = "Researcher"

        import httpx

        with patch.object(handler._http, "post") as mock_post:
            mock_post.side_effect = httpx.HTTPError("Network error")

            # Should not raise
            handler.on_agent_start(mock_agent)

    def test_http_client_cleanup(self):
        """Test that HTTP client is properly closed on deletion."""
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )

        with patch.object(handler._http, "close") as mock_close:
            handler.__del__()
            mock_close.assert_called_once()


class TestRunCrew:
    """Tests for run_crew function."""

    def test_run_crew_accepts_crew_and_inputs(self):
        """Test that run_crew accepts crew and inputs parameters."""
        import sys
        from unittest.mock import MagicMock

        from mutx.adapters.crewai import run_crew

        # Mock crewai module to avoid ImportError
        mock_crewai_module = MagicMock()
        mock_crewai_module.Crew = MagicMock()
        with patch.dict(sys.modules, {"crewai": mock_crewai_module}):
            mock_crew = MagicMock()
            mock_crew.name = "test-crew"
            mock_crew.agents = []
            mock_crew.tasks = []
            mock_crew.kickoff.return_value = "test-result"

            with patch("mutx.adapters.crewai.MutxCrewAICallbackHandler"):
                result = run_crew(mock_crew, {"topic": "AI"}, api_key="test-key")

            assert result == "test-result"
            mock_crew.kickoff.assert_called_once_with(inputs={"topic": "AI"})
