"""
Tests for CrewAI adapter (sdk/mutx/adapters/crewai.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestMutxCrewAICallbackHandlerImport:
    def test_handler_instantiates(self):
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )
        assert handler.api_url == "https://api.mutx.dev"
        assert handler.crew_name == "test-crew"
        assert handler._tracer is not None
        handler._http.close()

    def test_handler_url_rstrip(self):
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev///",
            api_key="test-key",
        )
        assert handler.api_url == "https://api.mutx.dev"
        handler._http.close()


class TestMutxCrewAICallbackSpans:
    def test_on_crew_start_creates_span(self):
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )
        mock_tracer = MagicMock()
        handler._tracer = mock_tracer

        mock_crew = MagicMock()
        mock_crew.agents = [MagicMock(), MagicMock()]
        mock_crew.tasks = [MagicMock(), MagicMock(), MagicMock()]

        handler.on_crew_start(mock_crew)

        mock_tracer.start_span.assert_called_once()
        call_args = mock_tracer.start_span.call_args
        assert call_args[0][0] == "mutx.crew.start"
        assert call_args[1]["attributes"]["crew.name"] == "test-crew"
        assert call_args[1]["attributes"]["crew.agent_count"] == 2
        assert call_args[1]["attributes"]["crew.task_count"] == 3
        handler._http.close()

    def test_on_agent_start_posts_audit_event(self):
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )
        mock_tracer = MagicMock()
        handler._tracer = mock_tracer
        # Mock HTTP to avoid network calls
        handler._http.post = MagicMock()

        mock_agent = MagicMock()
        mock_agent.role = "researcher"
        mock_agent.name = "researcher-agent"
        mock_agent.goal = "research goal"

        handler.on_agent_start(mock_agent)

        # on_agent_start logs to audit store, not spans
        handler._http.post.assert_called_once()
        call_args = handler._http.post.call_args
        assert call_args[0][0] == "events"
        event = call_args[1]["json"]
        assert event["event_type"] == "crew_agent_start"
        assert event["crew_name"] == "test-crew"
        assert event["agent_role"] == "researcher"
        handler._http.close()

    def test_on_task_start_posts_audit_event(self):
        from mutx.adapters.crewai import MutxCrewAICallbackHandler

        handler = MutxCrewAICallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            crew_name="test-crew",
        )
        mock_tracer = MagicMock()
        handler._tracer = mock_tracer
        # Mock HTTP to avoid network calls
        handler._http.post = MagicMock()

        mock_task = MagicMock()
        mock_task.description = "Research AI trends"
        mock_task.expected_output = "A research summary"

        handler.on_task_start(mock_task)

        # on_task_start logs to audit store, not spans
        handler._http.post.assert_called_once()
        call_args = handler._http.post.call_args
        assert call_args[0][0] == "events"
        event = call_args[1]["json"]
        assert event["event_type"] == "crew_task_start"
        assert event["crew_name"] == "test-crew"
        assert event["task_description"] == "Research AI trends"
        handler._http.close()


class TestRunCrew:
    def test_run_crew_calls_kickoff(self):
        from mutx.adapters.crewai import run_crew

        mock_crew = MagicMock()
        mock_crew.kickoff = MagicMock(return_value=MagicMock(output="crew result"))
        mock_crew.agents = []

        with patch.dict("sys.modules", {"crewai": MagicMock(), "crewai.Crew": MagicMock()}):
            result = run_crew(mock_crew, {"topic": "AI"}, api_key="test-key")

        mock_crew.kickoff.assert_called_once()
        assert result.output == "crew result"

    def test_run_crew_attaches_callback_to_agents(self):
        from mutx.adapters.crewai import run_crew, MutxCrewAICallbackHandler

        mock_agent = MagicMock()
        mock_agent.callback = None
        mock_crew = MagicMock()
        mock_crew.agents = [mock_agent]
        mock_crew.name = "test-crew"
        mock_crew.kickoff = MagicMock(return_value=MagicMock(output="result"))

        with patch.dict("sys.modules", {"crewai": MagicMock(), "crewai.Crew": MagicMock()}):
            run_crew(mock_crew, {"topic": "AI"}, api_key="test-key")

        # Callback should be attached to agents that don't have one
        assert mock_agent.callback is not None
        assert isinstance(mock_agent.callback, MutxCrewAICallbackHandler)
