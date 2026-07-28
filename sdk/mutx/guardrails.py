"""Guardrails middleware for MUTX agent runtime.

This module provides guardrail implementations for content filtering,
PII detection, toxicity detection, and custom regex-based blocking.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx


@dataclass
class GuardrailResult:
    """Result of a guardrail check.

    Attributes:
        passed: Whether the check passed.
        triggered_rule: Name of the rule that triggered (if any).
        action: Action taken - "block", "allow", or "warn".
        message: Human-readable message describing the result.
    """

    passed: bool
    triggered_rule: str | None
    action: Literal["block", "allow", "warn"]
    message: str


class InputGuardrail(Protocol):
    """Protocol for input guardrails that check text before LLM processing."""

    def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """Check input text against guardrail rules.

        Args:
            text: The input text to check.
            context: Additional context for the check.

        Returns:
            GuardrailResult with the check outcome.
        """
        ...


class OutputGuardrail(Protocol):
    """Protocol for output guardrails that check text after LLM generation."""

    def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """Check output text against guardrail rules.

        Args:
            text: The output text to check.
            context: Additional context for the check.

        Returns:
            GuardrailResult with the check outcome.
        """
        ...


class PIIBlocklistGuardrail:
    """Guardrail that blocks text containing PII patterns.

    Detects:
    - Social Security Numbers (SSN)
    - Credit card numbers
    - Email addresses
    """

    SSN_PATTERN = r"\b\d{3}-\d{2}-\d{4}\b"
    CREDIT_CARD_PATTERN = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
    EMAIL_PATTERN = r"\b[\w.-]+@[\w.-]+\.\w+\b"

    def __init__(self):
        self.ssn_regex = re.compile(self.SSN_PATTERN)
        self.credit_card_regex = re.compile(self.CREDIT_CARD_PATTERN)
        self.email_regex = re.compile(self.EMAIL_PATTERN)

    def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """Check text for PII patterns.

        Args:
            text: The text to check.
            context: Additional context (unused).

        Returns:
            GuardrailResult with block action if PII found, allow otherwise.
        """
        if self.ssn_regex.search(text):
            return GuardrailResult(
                passed=False,
                triggered_rule="ssn_block",
                action="block",
                message="Social Security Number detected in text",
            )

        if self.credit_card_regex.search(text):
            return GuardrailResult(
                passed=False,
                triggered_rule="credit_card_block",
                action="block",
                message="Credit card number detected in text",
            )

        if self.email_regex.search(text):
            return GuardrailResult(
                passed=False,
                triggered_rule="email_block",
                action="block",
                message="Email address detected in text",
            )

        return GuardrailResult(
            passed=True,
            triggered_rule=None,
            action="allow",
            message="No PII detected",
        )


class RegexBlocklistGuardrail:
    """Guardrail that blocks text matching any of a list of regex patterns."""

    def __init__(self, patterns: list[str]):
        """Initialize with a list of regex patterns.

        Args:
            patterns: List of regex pattern strings to block on match.
        """
        self.patterns = [re.compile(p) for p in patterns]
        self._pattern_names = [f"regex_block_{i}" for i in range(len(patterns))]

    def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """Check text against all configured regex patterns.

        Args:
            text: The text to check.
            context: Additional context (unused).

        Returns:
            GuardrailResult with block action if any pattern matches, allow otherwise.
        """
        for i, pattern in enumerate(self.patterns):
            match = pattern.search(text)
            if match:
                return GuardrailResult(
                    passed=False,
                    triggered_rule=self._pattern_names[i],
                    action="block",
                    message=f"Text matched blocked pattern: {pattern.pattern}",
                )

        return GuardrailResult(
            passed=True,
            triggered_rule=None,
            action="allow",
            message="No blocked patterns detected",
        )


class ToxicityGuardrail:
    """Guardrail for toxicity detection via external API.

    Availability failures block by default. Callers that explicitly accept the
    risk can set ``fail_open_on_unavailable=True`` and receive a warning result
    that includes the availability reason.
    """

    def __init__(
        self,
        toxicity_api_url: str | None = None,
        *,
        timeout: float = 10.0,
        fail_open_on_unavailable: bool = False,
    ):
        """Initialize toxicity guardrail.

        Args:
            toxicity_api_url: Optional URL for toxicity detection API.
            timeout: Request timeout in seconds.
            fail_open_on_unavailable: Allow with a warning when the service is
                unavailable or returns an invalid response. Defaults to False.
        """
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self.toxicity_api_url = toxicity_api_url
        self.timeout = timeout
        self.fail_open_on_unavailable = fail_open_on_unavailable

    def _unavailable_result(self, reason: str) -> GuardrailResult:
        message = f"Toxicity check unavailable: {reason}"
        if self.fail_open_on_unavailable:
            return GuardrailResult(
                passed=True,
                triggered_rule="toxicity_unavailable",
                action="warn",
                message=f"{message}; allowing because fail_open_on_unavailable=True",
            )
        return GuardrailResult(
            passed=False,
            triggered_rule="toxicity_unavailable",
            action="block",
            message=message,
        )

    @staticmethod
    def _result_from_response(response: httpx.Response) -> GuardrailResult:
        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError("response was not valid JSON") from exc

        if not isinstance(data, Mapping):
            raise ValueError("response must be a JSON object")

        toxic = data.get("toxic")
        if not isinstance(toxic, bool):
            raise ValueError("response field 'toxic' must be a boolean")

        reason = data.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("response field 'reason' must be a string")

        if toxic:
            return GuardrailResult(
                passed=False,
                triggered_rule="toxicity",
                action="block",
                message=reason or "Toxic content detected",
            )

        return GuardrailResult(
            passed=True,
            triggered_rule=None,
            action="allow",
            message="Toxicity check passed",
        )

    def _request(self, text: str, context: dict[str, Any]) -> httpx.Response:
        if self.toxicity_api_url is None:
            raise RuntimeError("toxicity API URL is not configured")
        with httpx.Client(timeout=self.timeout) as client:
            return client.post(
                self.toxicity_api_url,
                json={"text": text, "context": context},
            )

    async def _arequest(self, text: str, context: dict[str, Any]) -> httpx.Response:
        if self.toxicity_api_url is None:
            raise RuntimeError("toxicity API URL is not configured")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(
                self.toxicity_api_url,
                json={"text": text, "context": context},
            )

    def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """Check text for toxicity.

        Args:
            text: The text to check.
            context: Additional context (unused).

        Returns:
            GuardrailResult from the configured service, or an availability
            result governed by ``fail_open_on_unavailable``.
        """
        if not self.toxicity_api_url:
            return self._unavailable_result("service URL is not configured")

        try:
            response = self._request(text, context)
            response.raise_for_status()
            return self._result_from_response(response)
        except httpx.HTTPError as exc:
            return self._unavailable_result(f"request failed ({type(exc).__name__})")
        except ValueError as exc:
            return self._unavailable_result(f"invalid service response ({exc})")

    async def acheck(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """Async version of toxicity check.

        Args:
            text: The text to check.
            context: Additional context.

        Returns:
            GuardrailResult with the same validation and availability semantics
            as :meth:`check`.
        """
        if not self.toxicity_api_url:
            return self._unavailable_result("service URL is not configured")

        try:
            response = await self._arequest(text, context)
            response.raise_for_status()
            return self._result_from_response(response)
        except httpx.HTTPError as exc:
            return self._unavailable_result(f"request failed ({type(exc).__name__})")
        except ValueError as exc:
            return self._unavailable_result(f"invalid service response ({exc})")


class GuardrailViolationError(Exception):
    """Exception raised when a guardrail blocks content.

    Attributes:
        result: The GuardrailResult that caused the violation.
    """

    def __init__(self, result: GuardrailResult):
        """Initialize with the guardrail result.

        Args:
            result: The GuardrailResult that triggered the violation.
        """
        self.result = result
        super().__init__(f"Guardrail violation: {result.triggered_rule} - {result.message}")


class GuardrailMiddleware:
    """Middleware that applies a chain of guardrails to input and output text.

    Guardrails are applied in order, short-circuiting on first block.
    """

    def __init__(
        self,
        input_guardrails: list[InputGuardrail] | None = None,
        output_guardrails: list[OutputGuardrail] | None = None,
    ):
        """Initialize guardrail middleware.

        Args:
            input_guardrails: List of guardrails to apply to input.
            output_guardrails: List of guardrails to apply to output.
        """
        self.input_guardrails = input_guardrails or []
        self.output_guardrails = output_guardrails or []

    def check_input_text(self, text: str, context: dict[str, Any] | None = None) -> None:
        """Check input text against all input guardrails.

        Args:
            text: The input text to check.
            context: Additional context for the check.

        Raises:
            GuardrailViolationError: If any input guardrail blocks.
        """
        context = context or {}
        for guardrail in self.input_guardrails:
            result = guardrail.check(text, context)
            if result.action == "block" and not result.passed:
                raise GuardrailViolationError(result)

    def check_output_text(self, text: str, context: dict[str, Any] | None = None) -> None:
        """Check output text against all output guardrails.

        Args:
            text: The output text to check.
            context: Additional context for the check.

        Raises:
            GuardrailViolationError: If any output guardrail blocks.
        """
        context = context or {}
        for guardrail in self.output_guardrails:
            result = guardrail.check(text, context)
            if result.action == "block" and not result.passed:
                raise GuardrailViolationError(result)

    def check_input(
        self, text: str, context: dict[str, Any] | None = None
    ) -> list[GuardrailResult]:
        """Check input text and return all results (no short-circuit).

        Args:
            text: The input text to check.
            context: Additional context for the check.

        Returns:
            List of GuardrailResult from all input guardrails.
        """
        context = context or {}
        return [guardrail.check(text, context) for guardrail in self.input_guardrails]

    def check_output(
        self, text: str, context: dict[str, Any] | None = None
    ) -> list[GuardrailResult]:
        """Check output text and return all results (no short-circuit).

        Args:
            text: The output text to check.
            context: Additional context for the check.

        Returns:
            List of GuardrailResult from all output guardrails.
        """
        context = context or {}
        return [guardrail.check(text, context) for guardrail in self.output_guardrails]


__all__ = [
    "GuardrailResult",
    "InputGuardrail",
    "OutputGuardrail",
    "PIIBlocklistGuardrail",
    "RegexBlocklistGuardrail",
    "ToxicityGuardrail",
    "GuardrailViolationError",
    "GuardrailMiddleware",
]
