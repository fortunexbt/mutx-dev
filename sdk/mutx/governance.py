"""Governance API SDK for trust, lifecycle, discovery, and attestations."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from mutx._http import api_path


class GovernedIdentity:
    def __init__(self, data: dict[str, Any]):
        self.agent_id: str = data.get("agent_id", "")
        self.display_name: Optional[str] = data.get("display_name")
        self.trust_score: int = data.get("trust_score", 0)
        self.trust_tier: str = data.get("trust_tier", "unknown")
        self.credential_status: str = data.get("credential_status", "unknown")
        self.lifecycle_status: str = data.get("lifecycle_status", "unknown")
        self.launch_profile: Optional[str] = data.get("launch_profile")
        self.faramesh_policy: Optional[str] = data.get("faramesh_policy")
        self.capability_scope: list[str] = data.get("capability_scope", [])
        self.resource_scope: list[str] = data.get("resource_scope", [])
        self._data = data

    def __repr__(self) -> str:
        return f"GovernedIdentity(agent_id={self.agent_id}, trust_tier={self.trust_tier})"


class DiscoveryFinding:
    def __init__(self, data: dict[str, Any]):
        self.finding_id: str = data.get("finding_id", "")
        self.entity_id: str = data.get("entity_id", "")
        self.entity_type: str = data.get("entity_type", "unknown")
        self.title: str = data.get("title", "")
        self.source: str = data.get("source", "")
        self.risk_level: str = data.get("risk_level", "unknown")
        self.registration_status: str = data.get("registration_status", "unknown")
        self.confidence: float = float(data.get("confidence", 0.0))
        self._data = data

    def __repr__(self) -> str:
        return f"DiscoveryFinding(entity_id={self.entity_id}, risk_level={self.risk_level})"


class AttestationBundle:
    def __init__(self, data: dict[str, Any]):
        self.summary: dict[str, Any] = data.get("summary", {})
        self.coverage: dict[str, bool] = data.get("coverage", {})
        self.compliance: dict[str, Any] = data.get("compliance", {})
        self.discovery: dict[str, Any] = data.get("discovery", {})
        self.runtime: dict[str, Any] = data.get("runtime", {})
        self.owasp_agentic_risk_mapping: list[dict[str, Any]] = data.get(
            "owasp_agentic_risk_mapping", []
        )
        self._data = data

    def __repr__(self) -> str:
        return (
            "AttestationBundle("
            f"identities={self.summary.get('identities', 0)}, "
            f"discovery_items={self.summary.get('discovery_items', 0)})"
        )


class Governance:
    """SDK resource for governance trust, lifecycle, discovery, and attestations."""

    def __init__(self, client: httpx.Client | httpx.AsyncClient):
        self._client = client

    def _require_sync_client(self) -> None:
        if isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError(
                "This resource requires a sync httpx.Client. For async clients, use the `a*` methods."
            )

    def _require_async_client(self) -> None:
        if not isinstance(self._client, httpx.AsyncClient):
            raise RuntimeError(
                "This async resource helper requires an async httpx.AsyncClient and an `a*` method call."
            )

    def list_trust(self) -> list[GovernedIdentity]:
        self._require_sync_client()
        response = self._client.get("governance/trust")
        response.raise_for_status()
        payload = response.json()
        return [GovernedIdentity(item) for item in payload.get("items", [])]

    async def alist_trust(self) -> list[GovernedIdentity]:
        self._require_async_client()
        response = await self._client.get("governance/trust")
        response.raise_for_status()
        payload = response.json()
        return [GovernedIdentity(item) for item in payload.get("items", [])]

    def update_trust(
        self,
        agent_id: str,
        *,
        score: Optional[int] = None,
        delta: Optional[int] = None,
        reason: str = "",
        capability_scope: Optional[list[str]] = None,
        resource_scope: Optional[list[str]] = None,
        credential_status: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> GovernedIdentity:
        self._require_sync_client()
        payload: dict[str, Any] = {"reason": reason}
        if score is not None:
            payload["score"] = score
        if delta is not None:
            payload["delta"] = delta
        if capability_scope is not None:
            payload["capability_scope"] = capability_scope
        if resource_scope is not None:
            payload["resource_scope"] = resource_scope
        if credential_status is not None:
            payload["credential_status"] = credential_status
        if display_name is not None:
            payload["display_name"] = display_name

        response = self._client.post(
            api_path("governance/trust/{agent_id}", agent_id=agent_id), json=payload
        )
        response.raise_for_status()
        return GovernedIdentity(response.json())

    async def aupdate_trust(self, agent_id: str, **kwargs: Any) -> GovernedIdentity:
        self._require_async_client()
        response = await self._client.post(
            api_path("governance/trust/{agent_id}", agent_id=agent_id), json=kwargs
        )
        response.raise_for_status()
        return GovernedIdentity(response.json())

    def list_lifecycle(self) -> list[GovernedIdentity]:
        self._require_sync_client()
        response = self._client.get("governance/lifecycle")
        response.raise_for_status()
        payload = response.json()
        return [GovernedIdentity(item) for item in payload.get("items", [])]

    async def alist_lifecycle(self) -> list[GovernedIdentity]:
        self._require_async_client()
        response = await self._client.get("governance/lifecycle")
        response.raise_for_status()
        payload = response.json()
        return [GovernedIdentity(item) for item in payload.get("items", [])]

    def update_lifecycle(
        self,
        agent_id: str,
        *,
        state: str,
        reason: str = "",
        apply_runtime_action: bool = True,
    ) -> GovernedIdentity:
        self._require_sync_client()
        response = self._client.post(
            api_path("governance/lifecycle/{agent_id}", agent_id=agent_id),
            json={
                "state": state,
                "reason": reason,
                "apply_runtime_action": apply_runtime_action,
            },
        )
        response.raise_for_status()
        return GovernedIdentity(response.json())

    async def aupdate_lifecycle(
        self,
        agent_id: str,
        *,
        state: str,
        reason: str = "",
        apply_runtime_action: bool = True,
    ) -> GovernedIdentity:
        self._require_async_client()
        response = await self._client.post(
            api_path("governance/lifecycle/{agent_id}", agent_id=agent_id),
            json={
                "state": state,
                "reason": reason,
                "apply_runtime_action": apply_runtime_action,
            },
        )
        response.raise_for_status()
        return GovernedIdentity(response.json())

    def list_discovery(self) -> list[DiscoveryFinding]:
        self._require_sync_client()
        response = self._client.get("governance/discovery")
        response.raise_for_status()
        payload = response.json()
        return [DiscoveryFinding(item) for item in payload.get("items", [])]

    async def alist_discovery(self) -> list[DiscoveryFinding]:
        self._require_async_client()
        response = await self._client.get("governance/discovery")
        response.raise_for_status()
        payload = response.json()
        return [DiscoveryFinding(item) for item in payload.get("items", [])]

    def scan_discovery(self) -> dict[str, Any]:
        self._require_sync_client()
        response = self._client.post("governance/discovery/scan")
        response.raise_for_status()
        return response.json()

    async def ascan_discovery(self) -> dict[str, Any]:
        self._require_async_client()
        response = await self._client.post("governance/discovery/scan")
        response.raise_for_status()
        return response.json()

    def get_attestations(self) -> AttestationBundle:
        self._require_sync_client()
        response = self._client.get("governance/attestations")
        response.raise_for_status()
        return AttestationBundle(response.json())

    async def aget_attestations(self) -> AttestationBundle:
        self._require_async_client()
        response = await self._client.get("governance/attestations")
        response.raise_for_status()
        return AttestationBundle(response.json())

    def verify(self) -> AttestationBundle:
        self._require_sync_client()
        response = self._client.post("governance/attestations/verify")
        response.raise_for_status()
        return AttestationBundle(response.json())

    async def averify(self) -> AttestationBundle:
        self._require_async_client()
        response = await self._client.post("governance/attestations/verify")
        response.raise_for_status()
        return AttestationBundle(response.json())
