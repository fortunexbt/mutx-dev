"""Tests for pico_coach service — prompt construction, state extraction, and chat handling."""

import pytest

from src.api.models.pico_onboarding import CoachMessage, OnboardingState, PicoChatRequest
from src.api.services.pico_coach import (
    build_coach_messages,
    extract_onboarding_state,
    handle_coach_chat,
    load_builder_knowledge,
    load_builder_system_prompt,
)


# ---------------------------------------------------------------------------
# load_builder_system_prompt
# ---------------------------------------------------------------------------


class TestLoadBuilderSystemPrompt:
    """Tests for the system prompt loader."""

    def test_returns_non_empty_string(self):
        prompt = load_builder_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_contains_pico_mutx_builder(self):
        prompt = load_builder_system_prompt()
        assert "PicoMUTX Builder" in prompt

    def test_is_cached(self):
        """Two calls should return the same object (lru_cache)."""
        a = load_builder_system_prompt()
        b = load_builder_system_prompt()
        assert a is b


# ---------------------------------------------------------------------------
# load_builder_knowledge
# ---------------------------------------------------------------------------


class TestLoadBuilderKnowledge:
    """Tests for the knowledge file concatenation."""

    def test_returns_non_empty_string(self):
        knowledge = load_builder_knowledge()
        assert isinstance(knowledge, str)
        assert len(knowledge) > 0

    def test_contains_section_headers(self):
        """Knowledge should contain ## headers derived from the .md file stems."""
        knowledge = load_builder_knowledge()
        # The loader converts file stems like HERMES -> "Hermes", OPENCLAW -> "Openclaw"
        # At minimum the core stack docs should be present
        assert "## Hermes" in knowledge
        assert "## Openclaw" in knowledge
        assert "## Nanoclaw" in knowledge
        assert "## Picoclaw" in knowledge

    def test_does_not_contain_system_prompt_title(self):
        """SYSTEM_PROMPT.md is excluded from knowledge; its stem would be 'System Prompt'."""
        knowledge = load_builder_knowledge()
        assert "## System Prompt" not in knowledge

    def test_is_cached(self):
        a = load_builder_knowledge()
        b = load_builder_knowledge()
        assert a is b


# ---------------------------------------------------------------------------
# build_coach_messages
# ---------------------------------------------------------------------------


class TestBuildCoachMessages:
    """Tests for the OpenAI messages array constructor."""

    def test_empty_history(self):
        messages = build_coach_messages([], "Hello!")

        assert isinstance(messages, list)
        assert len(messages) == 2  # system + user

        assert messages[0]["role"] == "system"
        assert "PicoMUTX Builder" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello!"

    def test_populated_history(self):
        history = [
            CoachMessage(role="user", content="I want to set up an agent"),
            CoachMessage(role="assistant", content="Great! What OS are you on?"),
        ]
        messages = build_coach_messages(history, "macOS")

        assert len(messages) == 4  # system + 2 history + user

        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "I want to set up an agent"}
        assert messages[2] == {"role": "assistant", "content": "Great! What OS are you on?"}
        assert messages[3] == {"role": "user", "content": "macOS"}

    def test_system_message_contains_knowledge_reference(self):
        messages = build_coach_messages([], "test")
        system_content = messages[0]["content"]
        assert "Reference Knowledge" in system_content

    def test_long_history_preserved(self):
        history = [CoachMessage(role="user", content=f"turn {i}") for i in range(10)]
        messages = build_coach_messages(history, "final")
        # system + 10 history + 1 user
        assert len(messages) == 12
        assert messages[-1]["content"] == "final"


# ---------------------------------------------------------------------------
# extract_onboarding_state
# ---------------------------------------------------------------------------


class TestExtractOnboardingState:
    """Tests for the JSON state block parser."""

    def test_valid_json_block_extracts_state(self):
        reply = (
            "Great choice! Let me set up Hermes for you.\n\n"
            "```json\n"
            '{"onboarding_state": {"stack": "hermes", "os": "macos", '
            '"provider": "openai", "goal": "install", "ready": true}}\n'
            "```"
        )
        clean, state = extract_onboarding_state(reply)

        assert isinstance(state, OnboardingState)
        assert state.stack == "hermes"
        assert state.os == "macos"
        assert state.provider == "openai"
        assert state.goal == "install"
        assert state.ready is True
        # The JSON block should be stripped from the clean reply
        assert "```json" not in clean
        assert "Great choice!" in clean

    def test_no_json_block_returns_default_state(self):
        reply = "I'd love to help! What OS are you running?"
        clean, state = extract_onboarding_state(reply)

        assert clean == reply
        assert state == OnboardingState()
        assert state.ready is False

    def test_malformed_json_returns_default_state(self):
        reply = "Sure!\n\n```json\n{this is not valid json!!!}\n```"
        clean, state = extract_onboarding_state(reply)

        assert clean == reply
        assert state == OnboardingState()

    def test_missing_onboarding_state_key(self):
        reply = 'Hello!\n\n```json\n{"wrong_key": {"stack": "hermes"}}\n```'
        clean, state = extract_onboarding_state(reply)

        assert clean == reply
        assert state == OnboardingState()

    def test_valid_json_ready_true_all_required_fields(self):
        reply = (
            "Your package is ready!\n\n"
            "```json\n"
            '{"onboarding_state": {"stack": "hermes", "os": "linux", '
            '"provider": "anthropic", "goal": "migrate"}}\n'
            "```"
        )
        clean, state = extract_onboarding_state(reply)

        assert state.stack == "hermes"
        assert state.os == "linux"
        assert state.provider == "anthropic"
        assert state.goal == "migrate"
        # The model_validator sets ready=True when all 4 required fields are set
        assert state.ready is True

    def test_partial_state_not_ready(self):
        reply = 'Got it.\n\n```json\n{"onboarding_state": {"stack": "hermes", "os": "macos"}}\n```'
        clean, state = extract_onboarding_state(reply)

        assert state.stack == "hermes"
        assert state.os == "macos"
        assert state.provider is None
        assert state.goal is None
        assert state.ready is False

    def test_multiple_json_blocks_uses_last(self):
        """If there are multiple JSON blocks, the last one should be used."""
        reply = (
            "First answer.\n\n"
            "```json\n"
            '{"onboarding_state": {"stack": "openclaw"}}\n'
            "```"
            "\n\nSecond answer.\n\n"
            "```json\n"
            '{"onboarding_state": {"stack": "hermes", "os": "linux", '
            '"provider": "openai", "goal": "install"}}\n'
            "```"
        )
        clean, state = extract_onboarding_state(reply)

        # Should extract the last block's state
        assert state.stack == "hermes"
        # Clean reply should contain everything before the last block
        assert "First answer." in clean
        assert "Second answer." in clean


# ---------------------------------------------------------------------------
# handle_coach_chat
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Lightweight stand-in for PicoChatResponse that doesn't require session_id.

    The real PicoChatResponse mandates ``session_id: str`` but
    ``handle_coach_chat`` doesn't supply one — it's expected to be set by
    the route layer.  Tests use this stub to validate the coach logic
    without hitting that field requirement.
    """

    def __init__(self, reply: str, onboarding_state=None, ready_for_package: bool = False, **_kw):
        self.reply = reply
        self.onboarding_state = onboarding_state
        self.ready_for_package = ready_for_package


class TestHandleCoachChat:
    """Tests for the main chat entry point."""

    @pytest.mark.asyncio
    async def test_no_api_key_returns_fallback(self):
        from unittest.mock import patch

        request = PicoChatRequest(message="I want an agent")
        with patch("src.api.services.pico_coach.PicoChatResponse", _FakeResponse):
            response = await handle_coach_chat(request, [], api_key=None)

        assert "PicoMUTX Builder" in response.reply
        assert "API key" in response.reply
        assert response.onboarding_state == OnboardingState()
        assert response.ready_for_package is False

    @pytest.mark.asyncio
    async def test_empty_api_key_returns_fallback(self):
        from unittest.mock import patch

        request = PicoChatRequest(message="Hello")
        with patch("src.api.services.pico_coach.PicoChatResponse", _FakeResponse):
            response = await handle_coach_chat(request, [], api_key="")

        assert "PicoMUTX Builder" in response.reply
        assert response.ready_for_package is False

    @pytest.mark.asyncio
    async def test_with_mocked_openai_client(self):
        """Mock the OpenAI client to test the full happy path without a real API key."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Build a fake OpenAI response with a state block
        fake_message = MagicMock()
        fake_message.content = (
            "I recommend Hermes for your use case!\n\n"
            "```json\n"
            '{"onboarding_state": {"stack": "hermes", "os": "macos", '
            '"provider": "openai", "goal": "install", "channels": ["telegram"]}}\n'
            "```"
        )
        fake_choice = MagicMock()
        fake_choice.message = fake_message
        fake_response = MagicMock()
        fake_response.choices = [fake_choice]

        request = PicoChatRequest(message="I want to set up an agent on my Mac")
        history = []

        with (
            patch("src.api.services.pico_coach.AsyncOpenAI") as MockClient,
            patch("src.api.services.pico_coach.PicoChatResponse", _FakeResponse),
        ):
            mock_instance = MockClient.return_value
            mock_instance.chat = mock_instance
            mock_instance.completions = mock_instance
            mock_instance.create = AsyncMock(return_value=fake_response)

            response = await handle_coach_chat(request, history, api_key="sk-test-key")

        assert "Hermes" in response.reply
        assert response.onboarding_state.stack == "hermes"
        assert response.onboarding_state.os == "macos"
        assert response.onboarding_state.provider == "openai"
        assert response.onboarding_state.goal == "install"
        assert response.onboarding_state.channels == ["telegram"]
        assert response.ready_for_package is True

    @pytest.mark.asyncio
    async def test_with_mocked_openai_error(self):
        """When the LLM call fails, return an error message with empty state."""
        from unittest.mock import AsyncMock, patch

        request = PicoChatRequest(message="Hello")
        history = []

        with (
            patch("src.api.services.pico_coach.AsyncOpenAI") as MockClient,
            patch("src.api.services.pico_coach.PicoChatResponse", _FakeResponse),
        ):
            mock_instance = MockClient.return_value
            mock_instance.chat = mock_instance
            mock_instance.completions = mock_instance
            mock_instance.create = AsyncMock(side_effect=Exception("API error"))

            response = await handle_coach_chat(request, history, api_key="sk-test-key")

        assert "Something went wrong" in response.reply
        assert response.onboarding_state == OnboardingState()
        assert response.ready_for_package is False
