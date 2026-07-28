"""SDK contract tests for governance trust, lifecycle, discovery, and attestations."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from mutx.governance import AttestationBundle, DiscoveryFinding, Governance, GovernedIdentity


def _identity_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "agent_id": "agent-1",
        "display_name": "Agent One",
        "trust_score": 720,
        "trust_tier": "elevated",
        "credential_status": "brokered",
        "lifecycle_status": "active",
    }
    payload.update(overrides)
    return payload


def _attestation_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "summary": {"identities": 1, "discovery_items": 2},
        "coverage": {"policy_coverage": True, "receipt_integrity": True},
        "compliance": {"overall_satisfied": True},
        "owasp_agentic_risk_mapping": [{"risk": "shadow_agents", "status": "covered"}],
    }
    payload.update(overrides)
    return payload


def test_list_trust_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"items": [_identity_payload()]})

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    governance = Governance(client)

    result = governance.list_trust()

    assert captured["path"] == "/v1/governance/trust"
    assert isinstance(result[0], GovernedIdentity)
    assert result[0].trust_tier == "elevated"


def test_update_lifecycle_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["body"] = request.read().decode()
        return httpx.Response(200, json=_identity_payload(lifecycle_status="suspended"))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    governance = Governance(client)

    result = governance.update_lifecycle("agent-1", state="suspended", reason="operator pause")

    assert captured["path"] == "/v1/governance/lifecycle/agent-1"
    assert captured["method"] == "POST"
    assert '"state":"suspended"' in captured["body"]
    assert result.lifecycle_status == "suspended"


def test_scan_discovery_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "count": 1,
                "items": [
                    {
                        "finding_id": "finding-1",
                        "entity_id": "codex:abc",
                        "entity_type": "local_session",
                        "title": "Codex session",
                        "source": "codex",
                        "risk_level": "high",
                        "registration_status": "unregistered",
                        "confidence": 0.95,
                    }
                ],
            },
        )

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    governance = Governance(client)

    result = governance.scan_discovery()

    assert captured["path"] == "/v1/governance/discovery/scan"
    assert result["count"] == 1


def test_list_discovery_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "finding_id": "finding-1",
                        "entity_id": "codex:abc",
                        "entity_type": "local_session",
                        "title": "Codex session",
                        "source": "codex",
                        "risk_level": "high",
                        "registration_status": "unregistered",
                        "confidence": 0.95,
                    }
                ]
            },
        )

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    governance = Governance(client)

    result = governance.list_discovery()

    assert captured["path"] == "/v1/governance/discovery"
    assert isinstance(result[0], DiscoveryFinding)
    assert result[0].registration_status == "unregistered"


def test_verify_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_attestation_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    governance = Governance(client)

    result = governance.verify()

    assert captured["path"] == "/v1/governance/attestations/verify"
    assert isinstance(result, AttestationBundle)
    assert result.coverage["policy_coverage"] is True


def test_get_attestations_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_attestation_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    governance = Governance(client)

    result = governance.get_attestations()

    assert captured["path"] == "/v1/governance/attestations"
    assert result.compliance["overall_satisfied"] is True


@pytest.mark.asyncio
async def test_async_routes_hit_contract_routes() -> None:
    captured: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url.path)
        if request.url.path.endswith("/verify") or request.url.path.endswith("/attestations"):
            return httpx.Response(200, json=_attestation_payload())
        return httpx.Response(200, json={"items": [_identity_payload()]})

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    governance = Governance(client)

    trust = await governance.alist_trust()
    lifecycle = await governance.alist_lifecycle()
    attestation = await governance.averify()

    assert trust[0].agent_id == "agent-1"
    assert lifecycle[0].lifecycle_status == "active"
    assert attestation.coverage["receipt_integrity"] is True
    assert "/v1/governance/trust" in captured
    assert "/v1/governance/lifecycle" in captured
    assert "/v1/governance/attestations/verify" in captured
