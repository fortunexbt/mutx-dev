"""Tests for guardrails middleware."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from mutx.guardrails import (
    GuardrailMiddleware,
    GuardrailResult,
    GuardrailViolationError,
    PIIBlocklistGuardrail,
    RegexBlocklistGuardrail,
    ToxicityGuardrail,
)


class MockInputGuardrail:
    """Mock input guardrail for testing."""

    def __init__(self, result: GuardrailResult):
        self._result = result

    def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        return self._result


class MockOutputGuardrail:
    """Mock output guardrail for testing."""

    def __init__(self, result: GuardrailResult):
        self._result = result

    def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        return self._result


class TestGuardrailResult:
    """Tests for GuardrailResult dataclass."""

    def test_passed_result(self):
        result = GuardrailResult(
            passed=True,
            triggered_rule=None,
            action="allow",
            message="Check passed",
        )
        assert result.passed is True
        assert result.triggered_rule is None
        assert result.action == "allow"

    def test_blocked_result(self):
        result = GuardrailResult(
            passed=False,
            triggered_rule="pii_block",
            action="block",
            message="PII detected",
        )
        assert result.passed is False
        assert result.triggered_rule == "pii_block"
        assert result.action == "block"


class TestPIIBlocklistGuardrail:
    """Tests for PIIBlocklistGuardrail."""

    def setup_method(self):
        self.guardrail = PIIBlocklistGuardrail()

    def test_clean_text_passes(self):
        result = self.guardrail.check("Hello, how are you today?", {})
        assert result.passed is True
        assert result.action == "allow"

    def test_ssn_is_blocked(self):
        result = self.guardrail.check("My SSN is 123-45-6789.", {})
        assert result.passed is False
        assert result.triggered_rule == "ssn_block"
        assert result.action == "block"

    def test_credit_card_is_blocked(self):
        result = self.guardrail.check("Card: 1234-5678-9012-3456", {})
        assert result.passed is False
        assert result.triggered_rule == "credit_card_block"
        assert result.action == "block"

    def test_credit_card_no_separator_is_blocked(self):
        result = self.guardrail.check("Card: 1234567890123456", {})
        assert result.passed is False
        assert result.triggered_rule == "credit_card_block"
        assert result.action == "block"

    def test_email_is_blocked(self):
        result = self.guardrail.check("Contact me at john.doe@example.com", {})
        assert result.passed is False
        assert result.triggered_rule == "email_block"
        assert result.action == "block"


class TestRegexBlocklistGuardrail:
    """Tests for RegexBlocklistGuardrail."""

    def test_no_match_passes(self):
        guardrail = RegexBlocklistGuardrail([r"secret", r"password"])
        result = guardrail.check("Hello world", {})
        assert result.passed is True
        assert result.action == "allow"

    def test_single_match_blocks(self):
        guardrail = RegexBlocklistGuardrail([r"secret", r"password"])
        result = guardrail.check("The secret is out", {})
        assert result.passed is False
        assert result.triggered_rule == "regex_block_0"
        assert result.action == "block"

    def test_multiple_patterns(self):
        guardrail = RegexBlocklistGuardrail([r"secret", r"password"])
        result = guardrail.check("My password is 12345", {})
        assert result.passed is False
        assert result.triggered_rule == "regex_block_1"
        assert result.action == "block"


class TestToxicityGuardrail:
    """Tests for ToxicityGuardrail."""

    @staticmethod
    def _response(
        payload: Any = None,
        *,
        status_code: int = 200,
        content: bytes | None = None,
    ) -> httpx.Response:
        request = httpx.Request("POST", "https://toxicity.test/check")
        if content is not None:
            return httpx.Response(status_code, content=content, request=request)
        return httpx.Response(status_code, json=payload, request=request)

    @staticmethod
    def _check(guardrail: ToxicityGuardrail, *, async_mode: bool) -> GuardrailResult:
        if async_mode:
            return asyncio.run(guardrail.acheck("Hello world", {"source": "test"}))
        return guardrail.check("Hello world", {"source": "test"})

    @staticmethod
    def _mock_request(
        guardrail: ToxicityGuardrail,
        monkeypatch: pytest.MonkeyPatch,
        *,
        async_mode: bool,
        response: httpx.Response | None = None,
        error: httpx.HTTPError | None = None,
    ) -> AsyncMock | MagicMock:
        request_mock: AsyncMock | MagicMock
        if async_mode:
            request_mock = AsyncMock(return_value=response, side_effect=error)
            monkeypatch.setattr(guardrail, "_arequest", request_mock)
        else:
            request_mock = MagicMock(return_value=response, side_effect=error)
            monkeypatch.setattr(guardrail, "_request", request_mock)
        return request_mock

    def test_no_api_fails_closed(self):
        guardrail = ToxicityGuardrail()
        result = guardrail.check("Hello world", {})
        assert result.passed is False
        assert result.triggered_rule == "toxicity_unavailable"
        assert result.action == "block"
        assert "not configured" in result.message

    def test_sync_check_calls_configured_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        response = self._response({"toxic": False})
        client = MagicMock()
        client.__enter__.return_value = client
        client.post.return_value = response
        client_factory = MagicMock(return_value=client)
        monkeypatch.setattr(httpx, "Client", client_factory)
        guardrail = ToxicityGuardrail(
            toxicity_api_url="https://toxicity.test/check",
            timeout=2.5,
        )

        result = guardrail.check("Hello world", {"source": "test"})

        assert result.passed is True
        client_factory.assert_called_once_with(timeout=2.5)
        client.post.assert_called_once_with(
            "https://toxicity.test/check",
            json={"text": "Hello world", "context": {"source": "test"}},
        )

    def test_async_check_calls_configured_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        response = self._response({"toxic": False})
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=response)
        client_factory = MagicMock(return_value=client)
        monkeypatch.setattr(httpx, "AsyncClient", client_factory)
        guardrail = ToxicityGuardrail(
            toxicity_api_url="https://toxicity.test/check",
            timeout=3.5,
        )

        result = asyncio.run(guardrail.acheck("Hello world", {"source": "test"}))

        assert result.passed is True
        client_factory.assert_called_once_with(timeout=3.5)
        client.post.assert_awaited_once_with(
            "https://toxicity.test/check",
            json={"text": "Hello world", "context": {"source": "test"}},
        )

    @pytest.mark.parametrize("async_mode", [False, True], ids=["sync", "async"])
    def test_clean_service_response_passes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_mode: bool,
    ) -> None:
        guardrail = ToxicityGuardrail(toxicity_api_url="http://localhost:8000/check")
        request_mock = self._mock_request(
            guardrail,
            monkeypatch,
            async_mode=async_mode,
            response=self._response({"toxic": False}),
        )

        result = self._check(guardrail, async_mode=async_mode)

        assert result.passed is True
        assert result.action == "allow"
        request_mock.assert_called_once_with("Hello world", {"source": "test"})

    @pytest.mark.parametrize("async_mode", [False, True], ids=["sync", "async"])
    def test_toxic_service_response_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_mode: bool,
    ) -> None:
        guardrail = ToxicityGuardrail(toxicity_api_url="https://toxicity.test/check")
        self._mock_request(
            guardrail,
            monkeypatch,
            async_mode=async_mode,
            response=self._response({"toxic": True, "reason": "Threatening language"}),
        )

        result = self._check(guardrail, async_mode=async_mode)

        assert result.passed is False
        assert result.triggered_rule == "toxicity"
        assert result.action == "block"
        assert result.message == "Threatening language"

    @pytest.mark.parametrize("async_mode", [False, True], ids=["sync", "async"])
    def test_service_http_error_fails_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_mode: bool,
    ) -> None:
        guardrail = ToxicityGuardrail(toxicity_api_url="https://toxicity.test/check")
        self._mock_request(
            guardrail,
            monkeypatch,
            async_mode=async_mode,
            response=self._response({"detail": "down"}, status_code=503),
        )

        result = self._check(guardrail, async_mode=async_mode)

        assert result.passed is False
        assert result.triggered_rule == "toxicity_unavailable"
        assert result.action == "block"
        assert "HTTPStatusError" in result.message

    @pytest.mark.parametrize("async_mode", [False, True], ids=["sync", "async"])
    def test_malformed_service_response_fails_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_mode: bool,
    ) -> None:
        guardrail = ToxicityGuardrail(toxicity_api_url="https://toxicity.test/check")
        self._mock_request(
            guardrail,
            monkeypatch,
            async_mode=async_mode,
            response=self._response({"toxic": "no"}),
        )

        result = self._check(guardrail, async_mode=async_mode)

        assert result.passed is False
        assert result.triggered_rule == "toxicity_unavailable"
        assert result.action == "block"
        assert "must be a boolean" in result.message

    @pytest.mark.parametrize("async_mode", [False, True], ids=["sync", "async"])
    def test_timeout_fails_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_mode: bool,
    ) -> None:
        guardrail = ToxicityGuardrail(toxicity_api_url="https://toxicity.test/check")
        timeout = httpx.ReadTimeout(
            "timed out",
            request=httpx.Request("POST", "https://toxicity.test/check"),
        )
        self._mock_request(
            guardrail,
            monkeypatch,
            async_mode=async_mode,
            error=timeout,
        )

        result = self._check(guardrail, async_mode=async_mode)

        assert result.passed is False
        assert result.triggered_rule == "toxicity_unavailable"
        assert result.action == "block"
        assert "ReadTimeout" in result.message

    @pytest.mark.parametrize("async_mode", [False, True], ids=["sync", "async"])
    def test_explicit_fail_open_returns_visible_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_mode: bool,
    ) -> None:
        guardrail = ToxicityGuardrail(
            toxicity_api_url="https://toxicity.test/check",
            fail_open_on_unavailable=True,
        )
        self._mock_request(
            guardrail,
            monkeypatch,
            async_mode=async_mode,
            response=self._response(content=b"not-json"),
        )

        result = self._check(guardrail, async_mode=async_mode)

        assert result.passed is True
        assert result.triggered_rule == "toxicity_unavailable"
        assert result.action == "warn"
        assert "not valid JSON" in result.message
        assert "fail_open_on_unavailable=True" in result.message


class TestGuardrailMiddleware:
    """Tests for GuardrailMiddleware."""

    def test_no_guardrails_allows(self):
        middleware = GuardrailMiddleware()
        # Should not raise
        middleware.check_input_text("Hello world", {})
        middleware.check_output_text("Hello world", {})

    def test_input_guardrail_passes(self):
        guardrail = MockInputGuardrail(
            GuardrailResult(passed=True, triggered_rule=None, action="allow", message="ok")
        )
        middleware = GuardrailMiddleware(input_guardrails=[guardrail])
        # Should not raise
        middleware.check_input_text("Hello world", {})

    def test_input_guardrail_blocks(self):
        guardrail = MockInputGuardrail(
            GuardrailResult(passed=False, triggered_rule="test", action="block", message="blocked")
        )
        middleware = GuardrailMiddleware(input_guardrails=[guardrail])
        with pytest.raises(GuardrailViolationError) as exc_info:
            middleware.check_input_text("Hello world", {})
        assert exc_info.value.result.triggered_rule == "test"

    def test_output_guardrail_blocks(self):
        guardrail = MockOutputGuardrail(
            GuardrailResult(
                passed=False, triggered_rule="output_test", action="block", message="blocked"
            )
        )
        middleware = GuardrailMiddleware(output_guardrails=[guardrail])
        with pytest.raises(GuardrailViolationError) as exc_info:
            middleware.check_output_text("Hello world", {})
        assert exc_info.value.result.triggered_rule == "output_test"

    def test_short_circuits_on_first_block(self):
        call_count = 0

        class CountingGuardrail:
            def __init__(self):
                self.call_count = 0

            def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
                nonlocal call_count
                call_count += 1
                self.call_count += 1
                return GuardrailResult(
                    passed=False, triggered_rule="first", action="block", message="blocked"
                )

        second_guardrail = MockInputGuardrail(
            GuardrailResult(
                passed=False, triggered_rule="second", action="block", message="blocked"
            )
        )

        counting = CountingGuardrail()
        middleware = GuardrailMiddleware(
            input_guardrails=[
                counting,
                second_guardrail,  # Should not be called
            ]
        )

        with pytest.raises(GuardrailViolationError):
            middleware.check_input_text("test", {})
        assert call_count == 1

    def test_check_input_returns_all_results(self):
        result1 = GuardrailResult(passed=True, triggered_rule=None, action="allow", message="ok")
        result2 = GuardrailResult(passed=True, triggered_rule=None, action="allow", message="ok")
        guardrail1 = MockInputGuardrail(result1)
        guardrail2 = MockInputGuardrail(result2)
        middleware = GuardrailMiddleware(input_guardrails=[guardrail1, guardrail2])

        results = middleware.check_input("test", {})
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is True

    def test_check_output_returns_all_results(self):
        result = GuardrailResult(passed=True, triggered_rule=None, action="allow", message="ok")
        guardrail = MockOutputGuardrail(result)
        middleware = GuardrailMiddleware(output_guardrails=[guardrail])

        results = middleware.check_output("test", {})
        assert len(results) == 1
        assert results[0].passed is True


class TestGuardrailViolationError:
    """Tests for GuardrailViolationError."""

    def test_error_contains_result(self):
        result = GuardrailResult(
            passed=False,
            triggered_rule="pii_block",
            action="block",
            message="PII detected in text",
        )
        error = GuardrailViolationError(result)
        assert error.result == result
        assert "pii_block" in str(error)
        assert "PII detected" in str(error)


class TestGuardrailsIntegration:
    """Integration tests for guardrails with agent runtime."""

    def test_guardrail_middleware_with_pii_guardrail(self):
        """Test that PII guardrail blocks SSN in input."""
        pii_guardrail = PIIBlocklistGuardrail()
        middleware = GuardrailMiddleware(input_guardrails=[pii_guardrail])

        with pytest.raises(GuardrailViolationError) as exc_info:
            middleware.check_input_text("My SSN is 123-45-6789", {})
        assert exc_info.value.result.triggered_rule == "ssn_block"

    def test_guardrail_middleware_allows_clean_input(self):
        """Test that clean input passes through."""
        pii_guardrail = PIIBlocklistGuardrail()
        middleware = GuardrailMiddleware(input_guardrails=[pii_guardrail])

        # Should not raise
        middleware.check_input_text("Hello, how can I help you?", {})

    def test_multiple_guardrails_chained(self):
        """Test multiple guardrails applied in sequence."""
        pii_guardrail = PIIBlocklistGuardrail()
        regex_guardrail = RegexBlocklistGuardrail([r"confidential"])
        middleware = GuardrailMiddleware(input_guardrails=[pii_guardrail, regex_guardrail])

        # Clean text should pass
        middleware.check_input_text("Hello world", {})

        # Regex match should block
        with pytest.raises(GuardrailViolationError):
            middleware.check_input_text("This is confidential info", {})

    def test_output_guardrail_with_email(self):
        """Test output guardrail blocks email."""
        pii_guardrail = PIIBlocklistGuardrail()
        middleware = GuardrailMiddleware(output_guardrails=[pii_guardrail])

        with pytest.raises(GuardrailViolationError) as exc_info:
            middleware.check_output_text("My email is user@example.com", {})
        assert exc_info.value.result.triggered_rule == "email_block"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
