"""
Tests for AutoGen adapter (sdk/mutx/adapters/autogen.py).

Verifies:
- MutxAutoGenCallback emits OTel spans on agent message/teardown
- register_with_autogen() attaches callback to an agent
- Audit events are POSTed to /v1/events
- HTTP errors are swallowed gracefully
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestMutxAutoGenCallbackImport:
    """Test handler instantiation."""

    def test_handler_can_be_instantiated(self):
        """Verify callback instantiates with required params."""
        from mutx.adapters.autogen import MutxAutoGenCallback

        callback = MutxAutoGenCallback(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )
        assert callback.api_url == "https://api.mutx.dev"
        assert callback.api_key == "test-key"
        assert callback.agent_name == "test-agent"
        assert callback._tracer is not None
        callback._http.close()

    def test_handler_url_rstrip(self):
        """Verify trailing slash is stripped from api_url."""
        from mutx.adapters.autogen import MutxAutoGenCallback

        callback = MutxAutoGenCallback(
            api_url="https://api.mutx.dev///",
            api_key="test-key",
        )
        assert callback.api_url == "https://api.mutx.dev"
        callback._http.close()


class TestMutxAutoGenCallbackSpans:
    """Test OTel span emission on AutoGen callback methods."""

    def test_on_agent_message_received_uses_span_context_manager(self):
        """on_agent_message_received should use span() context manager."""
        from mutx.adapters.autogen import MutxAutoGenCallback

        callback = MutxAutoGenCallback(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        with patch("mutx.adapters.autogen.span") as mock_span_cm:
            mock_span = MagicMock()
            mock_span_cm.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_span_cm.return_value.__exit__ = MagicMock(return_value=None)

            mock_message = MagicMock()
            mock_message.__class__.__name__ = "ChatMessage"
            mock_sender = MagicMock()
            mock_sender.name = "assistant-agent"

            callback.on_agent_message_received(mock_message, mock_sender)

            mock_span_cm.assert_called_once()
            call_args = mock_span_cm.call_args
            assert call_args[0][0] == "mutx.autogen.message"
            assert call_args[1]["attributes"]["agent.name"] == "test-agent"
            assert call_args[1]["attributes"]["message.type"] == "ChatMessage"
            assert call_args[1]["attributes"]["sender.name"] == "assistant-agent"

        callback._http.close()

    def test_on_agent_message_received_posts_event(self):
        """Should POST audit event to /v1/events."""
        from mutx.adapters.autogen import MutxAutoGenCallback

        callback = MutxAutoGenCallback(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        mock_response = MagicMock()
        callback._http.post = MagicMock(return_value=mock_response)

        with patch("mutx.adapters.autogen.span") as mock_span_cm:
            mock_span = MagicMock()
            mock_span_cm.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_span_cm.return_value.__exit__ = MagicMock(return_value=None)

            mock_message = MagicMock()
            mock_message.__class__.__name__ = "TextMessage"
            mock_sender = MagicMock()
            mock_sender.name = "user"

            callback.on_agent_message_received(mock_message, mock_sender)

            callback._http.post.assert_called_once()
            call_args = callback._http.post.call_args
            assert call_args[0][0] == "events"
            event = call_args[1]["json"]
            assert event["event_type"] == "autogen_message_received"
            assert event["agent_name"] == "test-agent"
            assert event["sender"] == "user"
            assert event["message_type"] == "TextMessage"

        callback._http.close()

    def test_on_agent_message_received_swallows_http_errors(self):
        """Should not raise on HTTP errors."""
        from mutx.adapters.autogen import MutxAutoGenCallback
        import httpx

        callback = MutxAutoGenCallback(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        callback._http.post = MagicMock(side_effect=httpx.HTTPError("network error"))

        with patch("mutx.adapters.autogen.span") as mock_span_cm:
            mock_span = MagicMock()
            mock_span_cm.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_span_cm.return_value.__exit__ = MagicMock(return_value=None)

            mock_message = MagicMock()
            mock_message.__class__.__name__ = "TextMessage"
            mock_sender = MagicMock()
            mock_sender.name = "user"

            # Should not raise
            callback.on_agent_message_received(mock_message, mock_sender)

        callback._http.close()

    def test_on_agent_teardown_uses_span(self):
        """on_agent_teardown should use span() context manager."""
        from mutx.adapters.autogen import MutxAutoGenCallback

        callback = MutxAutoGenCallback(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        mock_response = MagicMock()
        callback._http.post = MagicMock(return_value=mock_response)

        with patch("mutx.adapters.autogen.span") as mock_span_cm:
            mock_span = MagicMock()
            mock_span_cm.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_span_cm.return_value.__exit__ = MagicMock(return_value=None)

            callback.on_agent_teardown(agent=MagicMock())

            mock_span_cm.assert_called_once()
            call_args = mock_span_cm.call_args
            assert call_args[0][0] == "mutx.autogen.teardown"
            assert call_args[1]["attributes"]["agent.name"] == "test-agent"

            callback._http.post.assert_called_once()
            event = callback._http.post.call_args[1]["json"]
            assert event["event_type"] == "autogen_agent_teardown"

        callback._http.close()

    def test_on_agent_teardown_swallows_http_errors(self):
        """Should not raise on HTTP errors during teardown."""
        from mutx.adapters.autogen import MutxAutoGenCallback
        import httpx

        callback = MutxAutoGenCallback(
            api_url="https://api.mutx.dev",
            api_key="test-key",
            agent_name="test-agent",
        )

        callback._http.post = MagicMock(side_effect=httpx.HTTPError("network error"))

        with patch("mutx.adapters.autogen.span") as mock_span_cm:
            mock_span = MagicMock()
            mock_span_cm.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_span_cm.return_value.__exit__ = MagicMock(return_value=None)

            # Should not raise
            callback.on_agent_teardown(agent=MagicMock())

        callback._http.close()


class TestRegisterWithAutoGen:
    """Test register_with_autogen() helper."""

    def test_register_with_autogen_attaches_callback(self):
        """register_with_autogen should attach MutxAutoGenCallback to agent."""
        from mutx.adapters.autogen import MutxAutoGenCallback, register_with_autogen

        mock_agent = MagicMock()
        mock_agent.name = "my-autogen-agent"
        mock_agent.register_message_handler = MagicMock()
        mock_agent.register_teardown_handler = MagicMock()

        with patch.dict("sys.modules", {"autogen": MagicMock()}):
            callback = register_with_autogen(
                agent=mock_agent,
                mutx_api_url="https://api.mutx.dev",
                api_key="test-key",
            )

        assert isinstance(callback, MutxAutoGenCallback)
        assert callback.agent_name == "my-autogen-agent"
        mock_agent.register_message_handler.assert_called_once_with(
            callback.on_agent_message_received
        )
        mock_agent.register_teardown_handler.assert_called_once_with(callback.on_agent_teardown)

    def test_register_with_autogen_skips_missing_handlers(self):
        """register_with_autogen should not fail if agent lacks handler methods."""
        from mutx.adapters.autogen import register_with_autogen

        mock_agent = MagicMock(spec=[])  # no custom methods
        mock_agent.name = "test-agent"

        with patch.dict("sys.modules", {"autogen": MagicMock()}):
            # Should not raise
            callback = register_with_autogen(
                agent=mock_agent,
                mutx_api_url="https://api.mutx.dev",
                api_key="test-key",
            )

        assert callback is not None
        assert callback.agent_name == "test-agent"

    def test_register_with_autogen_uses_agent_name_fallback(self):
        """register_with_autogen should use agent.name or fall back to default."""
        from mutx.adapters.autogen import MutxAutoGenCallback, register_with_autogen

        mock_agent = MagicMock()
        mock_agent.name = "named-agent"
        mock_agent.register_message_handler = MagicMock()
        mock_agent.register_teardown_handler = MagicMock()

        with patch.dict("sys.modules", {"autogen": MagicMock()}):
            callback = register_with_autogen(
                agent=mock_agent,
                mutx_api_url="https://api.mutx.dev",
                api_key="test-key",
            )

        assert isinstance(callback, MutxAutoGenCallback)
        assert callback.agent_name == "named-agent"
