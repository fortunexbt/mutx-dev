"""Contract tests for sdk/mutx/adapters/langchain.py.

These tests verify the MutxLangChainCallbackHandler and MutxAgentKit
integrate correctly with LangChain callbacks and emit OTel spans/events.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class CallbackStreamingExecutor:
    """Executor that emits real callback lifecycle events in a known order."""

    async def ainvoke(
        self,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, str]:
        callback = config["callbacks"][0]
        callback.on_llm_start({"name": "test-model"}, ["hello"], run_id="llm-1")
        llm_result = MagicMock()
        llm_result.llm_output = {
            "token_usage": {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
            }
        }
        callback.on_llm_end(llm_result, run_id="llm-1")
        callback.on_tool_start({"name": "search"}, "MUTX", run_id="tool-1")
        callback.on_tool_end("found", run_id="tool-1")

        action = MagicMock(tool="search", tool_input="MUTX", log="Calling search")
        callback.on_agent_action(action, run_id="agent-1")
        finish = MagicMock(log="done", return_values={"output": "done"})
        callback.on_agent_finish(finish, run_id="agent-1")
        return {"output": "done"}


class BlockingStreamingExecutor:
    """Executor used to prove an abandoned stream cancels its background run."""

    def __init__(self) -> None:
        self.cancelled = False

    async def ainvoke(
        self,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, str]:
        callback = config["callbacks"][0]
        callback.on_llm_start({"name": "test-model"}, ["hello"], run_id="llm-1")
        try:
            await asyncio.get_running_loop().create_future()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class TestMutxLangChainCallbackHandler:
    """Tests for MutxLangChainCallbackHandler."""

    def test_init_sets_attributes(self):
        """Test that handler initializes with correct attributes."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        assert handler.api_url == "https://api.mutx.dev"
        assert handler.api_key == "test-key"
        assert handler.agent_name == "test-agent"
        assert handler._http is not None

    def test_init_strips_trailing_slash(self):
        """Test that api_url trailing slash is stripped."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev/",
            api_key="test-key",
            agent_name="test-agent",
        )

        assert handler.api_url == "https://api.mutx.dev"

    def test_on_llm_start_emits_span(self):
        """Test that on_llm_start creates a span via telemetry."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        serialized = {"name": "gpt-4"}
        prompts = ["Hello, world!"]

        with patch.object(handler._tracer, "start_span") as mock_start_span:
            mock_span = MagicMock()
            mock_start_span.return_value = mock_span

            handler.on_llm_start(serialized, prompts)

            mock_start_span.assert_called_once()
            call_args = mock_start_span.call_args
            assert call_args[0][0] == "mutx.llm.call"
            assert call_args[1]["attributes"]["llm.model"] == "gpt-4"
            assert call_args[1]["attributes"]["llm.prompt_count"] == 1

    def test_on_chat_model_start_emits_v1_span(self):
        """LangChain v1 chat callbacks should emit the same LLM span."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        with patch.object(handler._tracer, "start_span") as mock_start_span:
            handler.on_chat_model_start(
                {"id": ["langchain", "chat_models", "ChatOpenAI"]},
                [[MagicMock()]],
            )

        mock_start_span.assert_called_once_with(
            "mutx.llm.call",
            attributes={
                "llm.model": "ChatOpenAI",
                "llm.prompt_count": 1,
                "agent.name": "test-agent",
            },
        )

    def test_on_llm_end_records_token_usage(self):
        """Test that on_llm_end records token usage attributes."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        mock_response = MagicMock()
        mock_response.llm_output = {
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            }
        }

        with patch("opentelemetry.trace") as mock_trace:
            mock_span = MagicMock()
            mock_trace.get_current_span.return_value = mock_span

            handler.on_llm_end(mock_response)

            mock_span.set_attribute.assert_any_call("llm.output_tokens", 20)
            mock_span.set_attribute.assert_any_call("llm.prompt_tokens", 10)
            mock_span.set_attribute.assert_any_call("llm.total_tokens", 30)

    def test_on_llm_end_handles_missing_token_usage(self):
        """Test that on_llm_end handles missing token usage gracefully."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        mock_response = MagicMock()
        mock_response.llm_output = None

        with patch("opentelemetry.trace") as mock_trace:
            mock_span = MagicMock()
            mock_trace.get_current_span.return_value = mock_span

            # Should not raise
            handler.on_llm_end(mock_response)

            # Should have set 0 values
            mock_span.set_attribute.assert_any_call("llm.output_tokens", 0)
            mock_span.set_attribute.assert_any_call("llm.prompt_tokens", 0)
            mock_span.set_attribute.assert_any_call("llm.total_tokens", 0)

    def test_on_tool_start_emits_span_with_tool_name(self):
        """Test that on_tool_start creates a span with tool.name attribute."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        serialized = {"name": "get_weather"}
        input_str = '{"city": "New York"}'

        with patch.object(handler._tracer, "start_span") as mock_start_span:
            mock_span = MagicMock()
            mock_start_span.return_value = mock_span

            handler.on_tool_start(serialized, input_str)

            mock_start_span.assert_called_once()
            call_args = mock_start_span.call_args
            assert call_args[0][0] == "mutx.tool.call"
            assert call_args[1]["attributes"]["tool.name"] == "get_weather"
            assert call_args[1]["attributes"]["tool.input_length"] == len(input_str)

    def test_on_tool_end_sets_success_attribute(self):
        """Test that on_tool_end marks span as successful."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        output = '{"weather": "sunny", "temp": 72}'

        with patch("opentelemetry.trace") as mock_trace:
            mock_span = MagicMock()
            mock_trace.get_current_span.return_value = mock_span

            handler.on_tool_end(output)

            mock_span.set_attribute.assert_any_call("tool.output_length", len(output))
            mock_span.set_attribute.assert_any_call("tool.success", True)
            mock_span.end.assert_called_once()

    def test_on_tool_error_records_exception(self):
        """Test that on_tool_error records error status and exception."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        error = ValueError("Tool execution failed")

        with patch("opentelemetry.trace") as mock_trace:
            mock_span = MagicMock()
            mock_trace.get_current_span.return_value = mock_span
            mock_trace.StatusCode = MagicMock()
            mock_trace.Status = MagicMock()

            handler.on_tool_error(error)

            mock_span.set_status.assert_called_once()
            mock_span.record_exception.assert_called_once_with(error)
            mock_span.end.assert_called_once()

    def test_on_agent_action_logs_to_api(self):
        """Test that on_agent_action posts event to MUTX API."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        # Mock the http client
        mock_response = MagicMock()
        handler._http.post = MagicMock(return_value=mock_response)

        mock_action = MagicMock()
        mock_action.tool = "get_weather"
        mock_action.tool_input = '{"city": "London"}'
        mock_action.log = "Calling get_weather with input: {'city': 'London'}"

        handler.on_agent_action(mock_action)

        handler._http.post.assert_called_once()
        call_args = handler._http.post.call_args
        assert call_args[0][0] == "events"

        event_payload = call_args[1]["json"]
        assert event_payload["event_type"] == "agent_action"
        assert event_payload["agent_name"] == "test-agent"
        assert event_payload["tool"] == "get_weather"
        assert event_payload["tool_input"] == '{"city": "London"}'

    def test_on_agent_finish_logs_to_api(self):
        """Test that on_agent_finish posts finish event to MUTX API."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        mock_response = MagicMock()
        handler._http.post = MagicMock(return_value=mock_response)

        mock_finish = MagicMock()
        mock_finish.log = "Final response: The weather is sunny."
        mock_finish.return_values = {"output": "The weather is sunny."}

        handler.on_agent_finish(mock_finish)

        handler._http.post.assert_called_once()
        call_args = handler._http.post.call_args
        assert call_args[0][0] == "events"

        event_payload = call_args[1]["json"]
        assert event_payload["event_type"] == "agent_finish"
        assert event_payload["agent_name"] == "test-agent"

    def test_audit_logging_fails_silently(self):
        """Test that audit logging failures don't raise exceptions."""
        from mutx.adapters.langchain import MutxLangChainCallbackHandler

        handler = MutxLangChainCallbackHandler(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        import httpx

        handler._http.post = MagicMock(side_effect=httpx.HTTPError("Connection failed"))

        mock_action = MagicMock()
        mock_action.tool = "test_tool"
        mock_action.tool_input = "{}"
        mock_action.log = "test log"

        # Should not raise
        handler.on_agent_action(mock_action)


class TestMutxAgentKit:
    """Tests for MutxAgentKit."""

    def test_init_sets_attributes(self):
        """Test that kit initializes with correct attributes."""
        from mutx.adapters.langchain import MutxAgentKit

        kit = MutxAgentKit(
            mutx_api_url="https://api.mutx.dev",
            agent_name="test-agent",
            api_key="test-key",
            guardrails_enabled=False,
        )

        assert kit.mutx_api_url == "https://api.mutx.dev"
        assert kit.agent_name == "test-agent"
        assert kit.api_key == "test-key"
        assert kit.guardrails_enabled is False
        assert kit._callback_handler is not None
        assert kit._agent_executor is None

    def test_init_with_guardrails_enabled(self):
        """Test that kit initializes guardrail middleware when enabled."""
        from mutx.adapters.langchain import MutxAgentKit

        kit = MutxAgentKit(
            mutx_api_url="https://api.mutx.dev",
            agent_name="test-agent",
            api_key="test-key",
            guardrails_enabled=True,
        )

        assert kit.guardrails_enabled is True
        # Guardrail middleware should be initialized
        # (actual guardrails may not be available if mutx.guardrails not installed)

    def test_set_agent_executor(self):
        """Test setting the agent executor."""
        from mutx.adapters.langchain import MutxAgentKit

        kit = MutxAgentKit(
            mutx_api_url="https://api.mutx.dev",
            agent_name="test-agent",
            api_key="test-key",
        )

        mock_executor = MagicMock()
        kit.set_agent_executor(mock_executor)

        assert kit._agent_executor is mock_executor

    def test_arun_raises_when_no_executor(self):
        """Test that arun raises RuntimeError when no executor is set."""
        from mutx.adapters.langchain import MutxAgentKit

        kit = MutxAgentKit(
            mutx_api_url="https://api.mutx.dev",
            agent_name="test-agent",
            api_key="test-key",
        )

        with pytest.raises(RuntimeError, match="No agent executor set"):
            kit.arun("test input")

    def test_arun_calls_executor_with_callback(self):
        """Test that arun calls the executor with callbacks."""
        from mutx.adapters.langchain import MutxAgentKit

        kit = MutxAgentKit(
            mutx_api_url="https://api.mutx.dev",
            agent_name="test-agent",
            api_key="test-key",
            guardrails_enabled=False,
        )

        mock_executor = MagicMock()
        response_message = MagicMock()
        response_message.text = "test response"
        mock_executor.invoke.return_value = {"messages": [response_message]}
        kit.set_agent_executor(mock_executor)

        result = kit.arun("test input")

        assert result == "test response"
        mock_executor.invoke.assert_called_once()
        # The invoke is called with two positional args: (input_dict, config_dict)
        call_args = mock_executor.invoke.call_args
        assert call_args[0][0] == {"messages": [{"role": "user", "content": "test input"}]}
        # Second positional argument should be the config dict with callbacks
        config_arg = call_args[0][1]
        assert "callbacks" in config_arg
        assert kit._callback_handler in config_arg["callbacks"]

    def test_arun_with_guardrails_checks_input(self):
        """Test that arun checks input with guardrails when enabled."""
        from mutx.adapters.langchain import MutxAgentKit

        kit = MutxAgentKit(
            mutx_api_url="https://api.mutx.dev",
            agent_name="test-agent",
            api_key="test-key",
            guardrails_enabled=True,
        )

        # Mock the guardrail middleware
        mock_middleware = MagicMock()
        kit._guardrail_middleware = mock_middleware

        mock_executor = MagicMock()
        mock_executor.invoke.return_value = {"output": "test response"}
        kit.set_agent_executor(mock_executor)

        kit.arun("test input")

        mock_middleware.check_input_text.assert_called_once_with("test input")

    def test_arun_with_guardrails_checks_output(self):
        """Test that arun checks output with guardrails when enabled."""
        from mutx.adapters.langchain import MutxAgentKit

        kit = MutxAgentKit(
            mutx_api_url="https://api.mutx.dev",
            agent_name="test-agent",
            api_key="test-key",
            guardrails_enabled=True,
        )

        mock_middleware = MagicMock()
        kit._guardrail_middleware = mock_middleware

        mock_executor = MagicMock()
        mock_executor.invoke.return_value = {"output": "test response"}
        kit.set_agent_executor(mock_executor)

        kit.arun("test input")

        mock_middleware.check_output_text.assert_called_once_with("test response")

    def test_stream_events_requires_executor(self):
        """A stream without an executor fails explicitly instead of fabricating events."""
        from mutx.adapters.langchain import MutxAgentKit

        kit = MutxAgentKit(
            mutx_api_url="https://api.mutx.dev",
            agent_name="test-agent",
            api_key="test-key",
        )

        async def collect() -> list[dict[str, Any]]:
            return [event async for event in kit.stream_events("hello")]

        with pytest.raises(RuntimeError, match="No agent executor set"):
            asyncio.run(collect())

        assert kit._callback_handler._event_listeners == []

    def test_stream_events_yields_real_callbacks_in_order(self):
        """The stream forwards observed callback events without synthetic starts."""
        from mutx.adapters.langchain import MutxAgentKit

        kit = MutxAgentKit(
            mutx_api_url="https://api.mutx.dev",
            agent_name="test-agent",
            api_key="test-key",
        )
        kit._callback_handler._http.post = MagicMock()
        kit.set_agent_executor(CallbackStreamingExecutor())

        async def collect() -> list[dict[str, Any]]:
            return [event async for event in kit.stream_events("hello")]

        events = asyncio.run(collect())

        assert [event["event_type"] for event in events] == [
            "llm_start",
            "llm_end",
            "tool_start",
            "tool_end",
            "agent_action",
            "agent_finish",
        ]
        assert all(event["agent_name"] == "test-agent" for event in events)
        assert all("timestamp" in event for event in events)
        assert kit._callback_handler._event_listeners == []
        assert kit._stream_active is False

    def test_stream_events_closes_listener_and_cancels_background_run(self):
        """Closing the consumer cleans up both callback and task lifecycle state."""
        from mutx.adapters.langchain import MutxAgentKit

        kit = MutxAgentKit(
            mutx_api_url="https://api.mutx.dev",
            agent_name="test-agent",
            api_key="test-key",
        )
        executor = BlockingStreamingExecutor()
        kit.set_agent_executor(executor)

        async def consume_one() -> dict[str, Any]:
            stream = kit.stream_events("hello")
            event = await stream.__anext__()
            await stream.aclose()
            return event

        event = asyncio.run(consume_one())

        assert event["event_type"] == "llm_start"
        assert executor.cancelled is True
        assert kit._callback_handler._event_listeners == []
        assert kit._stream_active is False
