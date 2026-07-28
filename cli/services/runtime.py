from __future__ import annotations

from typing import Any

from cli.services.base import APIService
from cli.services.models import OnboardingStateRecord, RuntimeProviderRecord


class RuntimeStateService(APIService):
    def get_onboarding(self) -> OnboardingStateRecord:
        response = self._request("get", "/v1/onboarding")
        self._expect_status(response, {200})
        return OnboardingStateRecord.from_payload(self._decode_json(response, expected_type=dict))

    def update_onboarding(
        self,
        *,
        action: str,
        step: str | None = None,
        provider: str = "openclaw",
        payload: dict[str, Any] | None = None,
    ) -> OnboardingStateRecord:
        request_payload: dict[str, Any] = {"action": action, "provider": provider}
        if step:
            request_payload["step"] = step
        if payload:
            request_payload["payload"] = payload
        response = self._request("post", "/v1/onboarding", json=request_payload)
        self._expect_status(response, {200})
        return OnboardingStateRecord.from_payload(self._decode_json(response, expected_type=dict))

    def get_provider(self, provider: str) -> RuntimeProviderRecord:
        response = self._request("get", f"/v1/runtime/providers/{provider}")
        self._expect_status(response, {200})
        return RuntimeProviderRecord.from_payload(self._decode_json(response, expected_type=dict))

    def put_provider(self, provider: str, payload: dict[str, Any]) -> RuntimeProviderRecord:
        response = self._request("put", f"/v1/runtime/providers/{provider}", json=payload)
        self._expect_status(response, {200}, invalid_message="Unable to sync provider runtime")
        return RuntimeProviderRecord.from_payload(self._decode_json(response, expected_type=dict))
