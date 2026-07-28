"""Contract tests for sdk/mutx/onboarding.py."""

from datetime import datetime
from unittest.mock import MagicMock

import httpx
import pytest

from sdk.mutx.onboarding import Onboarding, OnboardingState, OnboardingStep
from tests.sdk_contract_utils import assert_v1_request


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def step_data() -> dict:
    return {
        "id": "step-1",
        "name": "Connect Wallet",
        "status": "completed",
        "completed_at": "2026-04-01T10:00:00",
    }


@pytest.fixture
def minimal_step_data() -> dict:
    return {
        "id": "step-2",
        "name": "Enable MFA",
    }


@pytest.fixture
def state_data(step_data: dict) -> dict:
    return {
        "user_id": "user-123",
        "provider": "openclaw",
        "current_step": "step-2",
        "status": "active",
        "steps": [step_data],
        "created_at": "2026-04-01T09:00:00",
        "updated_at": "2026-04-01T10:00:00",
    }


@pytest.fixture
def minimal_state_data(minimal_step_data: dict) -> dict:
    return {
        "user_id": "user-456",
        "provider": "test",
    }


@pytest.fixture
def sync_mock_client(step_data: dict) -> MagicMock:
    """httpx.Client mock that returns state_data."""
    response = MagicMock()
    response.json.return_value = {
        "user_id": "user-123",
        "provider": "openclaw",
        "current_step": "step-1",
        "status": "active",
        "steps": [step_data],
        "created_at": "2026-04-01T09:00:00",
        "updated_at": "2026-04-01T10:00:00",
    }
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = response
    client.post.return_value = response
    return client


@pytest.fixture
def async_mock_client(step_data: dict) -> MagicMock:
    """httpx.AsyncClient mock that returns state_data."""
    response = MagicMock()
    response.json.return_value = {
        "user_id": "user-123",
        "provider": "openclaw",
        "current_step": "step-1",
        "status": "active",
        "steps": [step_data],
        "created_at": "2026-04-01T09:00:00",
        "updated_at": "2026-04-01T10:00:00",
    }
    client = MagicMock(spec=httpx.AsyncClient)
    client.get.return_value = response
    client.post.return_value = response
    return client


# ---------------------------------------------------------------------------
# OnboardingStep — data class parsing
# ---------------------------------------------------------------------------


class TestOnboardingStepParsing:
    def test_required_fields(self, step_data: dict) -> None:
        step = OnboardingStep(step_data)
        assert step.id == "step-1"
        assert step.name == "Connect Wallet"
        assert step.status == "completed"
        assert step.completed_at == datetime.fromisoformat("2026-04-01T10:00:00")

    def test_optional_status_defaults_to_pending(self, minimal_step_data: dict) -> None:
        step = OnboardingStep(minimal_step_data)
        assert step.status == "pending"

    def test_optional_completed_at_defaults_to_none(self, minimal_step_data: dict) -> None:
        step = OnboardingStep(minimal_step_data)
        assert step.completed_at is None

    def test_raw_data_preserved(self, step_data: dict) -> None:
        step = OnboardingStep(step_data)
        assert step._data == step_data


# ---------------------------------------------------------------------------
# OnboardingState — data class parsing + repr
# ---------------------------------------------------------------------------


class TestOnboardingStateParsing:
    def test_required_fields(self, state_data: dict) -> None:
        state = OnboardingState(state_data)
        assert state.user_id == "user-123"
        assert state.provider == "openclaw"
        assert state.current_step == "step-2"
        assert state.status == "active"
        assert state.created_at == datetime.fromisoformat("2026-04-01T09:00:00")
        assert state.updated_at == datetime.fromisoformat("2026-04-01T10:00:00")
        assert len(state.steps) == 1

    def test_optional_current_step_defaults_to_empty(self, minimal_state_data: dict) -> None:
        state = OnboardingState(minimal_state_data)
        assert state.current_step == ""

    def test_optional_status_defaults_to_active(self, minimal_state_data: dict) -> None:
        state = OnboardingState(minimal_state_data)
        assert state.status == "active"

    def test_optional_steps_defaults_to_empty_list(self, minimal_state_data: dict) -> None:
        state = OnboardingState(minimal_state_data)
        assert state.steps == []

    def test_optional_created_at_defaults_to_none(self, minimal_state_data: dict) -> None:
        state = OnboardingState(minimal_state_data)
        assert state.created_at is None

    def test_optional_updated_at_defaults_to_none(self, minimal_state_data: dict) -> None:
        state = OnboardingState(minimal_state_data)
        assert state.updated_at is None

    def test_steps_parsed_as_onboardingstep_instances(self, state_data: dict) -> None:
        state = OnboardingState(state_data)
        assert isinstance(state.steps[0], OnboardingStep)
        assert state.steps[0].id == "step-1"

    def test_repr(self, state_data: dict) -> None:
        state = OnboardingState(state_data)
        assert repr(state) == "OnboardingState(provider=openclaw, step=step-2)"

    def test_raw_data_preserved(self, state_data: dict) -> None:
        state = OnboardingState(state_data)
        assert state._data == state_data


# ---------------------------------------------------------------------------
# Type guards
# ---------------------------------------------------------------------------


class TestSyncClientTypeGuard:
    def test_sync_method_raises_on_async_client(self) -> None:
        async_client = httpx.AsyncClient()
        onboarding = Onboarding(async_client)
        with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
            onboarding.get_state()


class TestAsyncClientTypeGuard:
    @pytest.mark.asyncio
    async def test_async_method_raises_on_sync_client(self) -> None:
        sync_client = httpx.Client()
        onboarding = Onboarding(sync_client)
        with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
            await onboarding.aget_state()


# ---------------------------------------------------------------------------
# Sync methods — mocked httpx.Client
# ---------------------------------------------------------------------------


class TestGetStateSync:
    def test_get_state_calls_get_with_params(self, sync_mock_client: MagicMock) -> None:
        onboarding = Onboarding(sync_mock_client)
        result = onboarding.get_state(provider="openclaw")
        request = assert_v1_request(sync_mock_client.get, "GET", "/v1/onboarding")
        assert dict(request.url.params) == {"provider": "openclaw"}
        assert isinstance(result, OnboardingState)

    def test_get_state_default_provider(self, sync_mock_client: MagicMock) -> None:
        onboarding = Onboarding(sync_mock_client)
        onboarding.get_state()
        request = assert_v1_request(sync_mock_client.get, "GET", "/v1/onboarding")
        assert dict(request.url.params) == {"provider": "openclaw"}


class TestUpdateSync:
    def test_update_calls_post_with_action_only(self, sync_mock_client: MagicMock) -> None:
        onboarding = Onboarding(sync_mock_client)
        onboarding.update(action="complete_step")
        sync_mock_client.post.assert_called_once()
        call_kwargs = sync_mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["action"] == "complete_step"
        assert call_kwargs["json"]["provider"] == "openclaw"
        assert "step" not in call_kwargs["json"]
        assert "payload" not in call_kwargs["json"]

    def test_update_includes_step_when_provided(self, sync_mock_client: MagicMock) -> None:
        onboarding = Onboarding(sync_mock_client)
        onboarding.update(action="skip_step", step="step-1")
        call_kwargs = sync_mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["step"] == "step-1"

    def test_update_includes_payload_when_provided(self, sync_mock_client: MagicMock) -> None:
        onboarding = Onboarding(sync_mock_client)
        onboarding.update(action="complete_step", payload={"foo": "bar"})
        call_kwargs = sync_mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["payload"] == {"foo": "bar"}

    def test_update_returns_onboarding_state(self, sync_mock_client: MagicMock) -> None:
        onboarding = Onboarding(sync_mock_client)
        result = onboarding.update(action="complete_step")
        assert isinstance(result, OnboardingState)


# ---------------------------------------------------------------------------
# Async methods — mocked httpx.AsyncClient
# ---------------------------------------------------------------------------


class TestGetStateAsync:
    @pytest.mark.asyncio
    async def test_aget_state_calls_get_with_params(self, async_mock_client: MagicMock) -> None:
        onboarding = Onboarding(async_mock_client)
        result = await onboarding.aget_state(provider="openclaw")
        request = assert_v1_request(async_mock_client.get, "GET", "/v1/onboarding")
        assert dict(request.url.params) == {"provider": "openclaw"}
        assert isinstance(result, OnboardingState)

    @pytest.mark.asyncio
    async def test_aget_state_default_provider(self, async_mock_client: MagicMock) -> None:
        onboarding = Onboarding(async_mock_client)
        await onboarding.aget_state()
        request = assert_v1_request(async_mock_client.get, "GET", "/v1/onboarding")
        assert dict(request.url.params) == {"provider": "openclaw"}


class TestUpdateAsync:
    @pytest.mark.asyncio
    async def test_aupdate_calls_post_with_action_only(self, async_mock_client: MagicMock) -> None:
        onboarding = Onboarding(async_mock_client)
        await onboarding.aupdate(action="complete_step")
        async_mock_client.post.assert_called_once()
        call_kwargs = async_mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["action"] == "complete_step"
        assert call_kwargs["json"]["provider"] == "openclaw"
        assert "step" not in call_kwargs["json"]
        assert "payload" not in call_kwargs["json"]

    @pytest.mark.asyncio
    async def test_aupdate_includes_step_when_provided(self, async_mock_client: MagicMock) -> None:
        onboarding = Onboarding(async_mock_client)
        await onboarding.aupdate(action="skip_step", step="step-1")
        call_kwargs = async_mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["step"] == "step-1"

    @pytest.mark.asyncio
    async def test_aupdate_includes_payload_when_provided(
        self, async_mock_client: MagicMock
    ) -> None:
        onboarding = Onboarding(async_mock_client)
        await onboarding.aupdate(action="complete_step", payload={"foo": "bar"})
        call_kwargs = async_mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["payload"] == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_aupdate_returns_onboarding_state(self, async_mock_client: MagicMock) -> None:
        onboarding = Onboarding(async_mock_client)
        result = await onboarding.aupdate(action="complete_step")
        assert isinstance(result, OnboardingState)


# ---------------------------------------------------------------------------
# raise_for_status coverage
# ---------------------------------------------------------------------------


class TestRaiseForStatus:
    def test_get_state_raises_for_status_on_error(self) -> None:
        response = MagicMock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=MagicMock(status_code=404)
        )
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = response
        onboarding = Onboarding(client)
        with pytest.raises(httpx.HTTPStatusError):
            onboarding.get_state()

    def test_update_raises_for_status_on_error(self) -> None:
        response = MagicMock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad request", request=MagicMock(), response=MagicMock(status_code=400)
        )
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = response
        onboarding = Onboarding(client)
        with pytest.raises(httpx.HTTPStatusError):
            onboarding.update(action="complete_step")

    @pytest.mark.asyncio
    async def test_aget_state_raises_for_status_on_error(self) -> None:
        response = MagicMock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=MagicMock(status_code=404)
        )
        client = MagicMock(spec=httpx.AsyncClient)
        client.get.return_value = response
        onboarding = Onboarding(client)
        with pytest.raises(httpx.HTTPStatusError):
            await onboarding.aget_state()

    @pytest.mark.asyncio
    async def test_aupdate_raises_for_status_on_error(self) -> None:
        response = MagicMock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad request", request=MagicMock(), response=MagicMock(status_code=400)
        )
        client = MagicMock(spec=httpx.AsyncClient)
        client.post.return_value = response
        onboarding = Onboarding(client)
        with pytest.raises(httpx.HTTPStatusError):
            await onboarding.aupdate(action="complete_step")
