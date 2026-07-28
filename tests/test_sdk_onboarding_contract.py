"""Contract tests for sdk/mutx/onboarding.py."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from sdk.mutx.onboarding import Onboarding, OnboardingState, OnboardingStep
from tests.sdk_contract_utils import assert_v1_request


# ---------------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------------


def _onboarding_step_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "step-001",
        "name": "Connect Wallet",
        "status": "completed",
        "completed_at": "2026-04-03T01:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def _onboarding_state_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "user_id": "user-001",
        "provider": "openclaw",
        "current_step": "step-002",
        "status": "active",
        "steps": [
            _onboarding_step_payload(id="step-001", name="Connect Wallet", status="completed"),
            _onboarding_step_payload(id="step-002", name="Verify Identity", status="pending"),
        ],
        "created_at": "2026-04-03T00:00:00+00:00",
        "updated_at": "2026-04-03T01:30:00+00:00",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Data class tests: OnboardingStep
# ---------------------------------------------------------------------------


class TestOnboardingStep:
    def test_onboarding_step_parsed_fields(self):
        payload = _onboarding_step_payload()
        step = OnboardingStep(payload)

        assert step.id == "step-001"
        assert step.name == "Connect Wallet"
        assert step.status == "completed"
        assert step.completed_at == datetime.fromisoformat("2026-04-03T01:00:00+00:00")
        assert step._data == payload

    def test_onboarding_step_completed_at_none_when_missing(self):
        payload = _onboarding_step_payload(completed_at=None)
        del payload["completed_at"]
        step = OnboardingStep(payload)

        assert step.completed_at is None

    def test_onboarding_step_status_defaults_to_pending(self):
        payload = _onboarding_step_payload(status=None)
        del payload["status"]
        step = OnboardingStep(payload)

        assert step.status == "pending"


# ---------------------------------------------------------------------------
# Data class tests: OnboardingState
# ---------------------------------------------------------------------------


class TestOnboardingState:
    def test_onboarding_state_parsed_fields(self):
        payload = _onboarding_state_payload()
        state = OnboardingState(payload)

        assert state.user_id == "user-001"
        assert state.provider == "openclaw"
        assert state.current_step == "step-002"
        assert state.status == "active"
        assert len(state.steps) == 2
        assert isinstance(state.steps[0], OnboardingStep)
        assert state.steps[0].id == "step-001"
        assert state.steps[1].id == "step-002"
        assert state.created_at == datetime.fromisoformat("2026-04-03T00:00:00+00:00")
        assert state.updated_at == datetime.fromisoformat("2026-04-03T01:30:00+00:00")
        assert state._data == payload

    def test_onboarding_state_current_step_defaults_to_empty(self):
        payload = _onboarding_state_payload()
        del payload["current_step"]
        state = OnboardingState(payload)

        assert state.current_step == ""

    def test_onboarding_state_status_defaults_to_active(self):
        payload = _onboarding_state_payload()
        del payload["status"]
        state = OnboardingState(payload)

        assert state.status == "active"

    def test_onboarding_state_steps_empty_when_missing(self):
        payload = _onboarding_state_payload()
        del payload["steps"]
        state = OnboardingState(payload)

        assert state.steps == []

    def test_onboarding_state_created_at_none_when_missing(self):
        payload = _onboarding_state_payload()
        del payload["created_at"]
        state = OnboardingState(payload)

        assert state.created_at is None

    def test_onboarding_state_repr(self):
        payload = _onboarding_state_payload()
        state = OnboardingState(payload)

        repr_str = repr(state)
        assert "OnboardingState" in repr_str
        assert "openclaw" in repr_str
        assert "step-002" in repr_str


# ---------------------------------------------------------------------------
# Sync method tests: get_state
# ---------------------------------------------------------------------------


class TestOnboardingGetState:
    def test_get_state_returns_onboarding_state(self):
        returned = _onboarding_state_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        onboarding = Onboarding(mock_client)

        result = onboarding.get_state()

        assert isinstance(result, OnboardingState)
        request = assert_v1_request(mock_client.get, "GET", "/v1/onboarding")
        assert dict(request.url.params) == {"provider": "openclaw"}
        mock_response.raise_for_status.assert_called_once()

    def test_get_state_custom_provider(self):
        returned = _onboarding_state_payload(provider="custom")
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        onboarding = Onboarding(mock_client)

        result = onboarding.get_state(provider="custom")

        assert isinstance(result, OnboardingState)
        request = assert_v1_request(mock_client.get, "GET", "/v1/onboarding")
        assert dict(request.url.params) == {"provider": "custom"}

    def test_get_state_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response
        onboarding = Onboarding(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            onboarding.get_state()

    def test_get_state_raises_when_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        onboarding = Onboarding(mock_client)

        with pytest.raises(RuntimeError, match="sync"):
            onboarding.get_state()


# ---------------------------------------------------------------------------
# Sync method tests: update
# ---------------------------------------------------------------------------


class TestOnboardingUpdate:
    def test_update_returns_onboarding_state(self):
        returned = _onboarding_state_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        onboarding = Onboarding(mock_client)

        result = onboarding.update(action="complete_step", step="step-001")

        assert isinstance(result, OnboardingState)
        request = assert_v1_request(mock_client.post, "POST", "/v1/onboarding")
        body = json.loads(request.content)
        assert body["action"] == "complete_step"
        assert body["step"] == "step-001"
        assert body["provider"] == "openclaw"
        mock_response.raise_for_status.assert_called_once()

    def test_update_with_payload(self):
        returned = _onboarding_state_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        onboarding = Onboarding(mock_client)

        onboarding.update(action="skip_step", step="step-002", payload={"reason": "user_requested"})

        call_args = mock_client.post.call_args
        assert call_args.kwargs["json"]["payload"] == {"reason": "user_requested"}

    def test_update_without_step(self):
        returned = _onboarding_state_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        onboarding = Onboarding(mock_client)

        onboarding.update(action="reset")

        call_args = mock_client.post.call_args
        assert "step" not in call_args.kwargs["json"]

    def test_update_raises_for_status(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400", request=MagicMock(), response=MagicMock(status_code=400)
        )
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        onboarding = Onboarding(mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            onboarding.update(action="complete_step", step="step-001")

    def test_update_raises_when_async_client(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        onboarding = Onboarding(mock_client)

        with pytest.raises(RuntimeError, match="sync"):
            onboarding.update(action="complete_step")


# ---------------------------------------------------------------------------
# Async method tests: aget_state
# ---------------------------------------------------------------------------


class TestOnboardingAsyncGetState:
    @pytest.mark.asyncio
    async def test_aget_state_returns_onboarding_state(self):
        returned = _onboarding_state_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        onboarding = Onboarding(mock_client)

        result = await onboarding.aget_state()

        assert isinstance(result, OnboardingState)
        request = assert_v1_request(mock_client.get, "GET", "/v1/onboarding")
        assert dict(request.url.params) == {"provider": "openclaw"}

    @pytest.mark.asyncio
    async def test_aget_state_raises_when_sync_client(self):
        mock_client = MagicMock(spec=httpx.Client)
        onboarding = Onboarding(mock_client)

        with pytest.raises(RuntimeError, match="async"):
            await onboarding.aget_state()


# ---------------------------------------------------------------------------
# Async method tests: aupdate
# ---------------------------------------------------------------------------


class TestOnboardingAsyncUpdate:
    @pytest.mark.asyncio
    async def test_aupdate_returns_onboarding_state(self):
        returned = _onboarding_state_payload()
        mock_response = MagicMock()
        mock_response.json.return_value = returned
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        onboarding = Onboarding(mock_client)

        result = await onboarding.aupdate(action="complete_step", step="step-001")

        assert isinstance(result, OnboardingState)
        request = assert_v1_request(mock_client.post, "POST", "/v1/onboarding")
        body = json.loads(request.content)
        assert body["action"] == "complete_step"
        assert body["step"] == "step-001"

    @pytest.mark.asyncio
    async def test_aupdate_raises_when_sync_client(self):
        mock_client = MagicMock(spec=httpx.Client)
        onboarding = Onboarding(mock_client)

        with pytest.raises(RuntimeError, match="async"):
            await onboarding.aupdate(action="complete_step")
