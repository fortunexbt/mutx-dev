"""Governance contract routes for trust, lifecycle, discovery, and attestations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import get_current_internal_user, require_roles
from src.api.database import get_db
from src.api.models import Agent, User, UserSetting
from src.api.models.numeric import DegradedNumericResponseModel

router = APIRouter(prefix="/governance", tags=["governance"])
logger = logging.getLogger(__name__)

TrustTier = Literal["unknown", "low", "trusted", "elevated", "critical"]
CredentialStatus = Literal["unknown", "missing", "brokered", "expired"]
LifecycleStatus = Literal["unknown", "active", "suspended", "retired"]
RiskLevel = Literal["unknown", "low", "medium", "high", "critical"]
RegistrationStatus = Literal["unknown", "registered", "unregistered", "ignored"]


class GovernedIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    display_name: str | None = None
    trust_score: int = Field(default=500, ge=0, le=1000)
    trust_tier: TrustTier = "trusted"
    credential_status: CredentialStatus = "unknown"
    lifecycle_status: LifecycleStatus = "active"
    launch_profile: str | None = None
    faramesh_policy: str | None = None
    capability_scope: list[str] = Field(default_factory=list)
    resource_scope: list[str] = Field(default_factory=list)
    updated_at: str


class GovernanceIdentityList(BaseModel):
    items: list[GovernedIdentity]


class GovernanceTrustUpdate(BaseModel):
    score: int | None = Field(default=None, ge=0, le=1000)
    delta: int | None = None
    reason: str = ""
    capability_scope: list[str] | None = None
    resource_scope: list[str] | None = None
    credential_status: CredentialStatus | None = None
    display_name: str | None = None


class GovernanceLifecycleUpdate(BaseModel):
    state: LifecycleStatus
    reason: str = ""
    apply_runtime_action: bool = True


class DiscoveryFinding(DegradedNumericResponseModel):
    finding_id: str
    entity_id: str
    entity_type: str
    title: str
    source: str
    risk_level: RiskLevel = "unknown"
    registration_status: RegistrationStatus = "unknown"
    confidence: float | None = Field(default=0.0, ge=0.0, le=1.0)
    discovered_at: str


class DiscoveryList(BaseModel):
    items: list[DiscoveryFinding]


class DiscoveryScanResponse(BaseModel):
    count: int
    scanned_at: str
    items: list[DiscoveryFinding]


class AttestationBundle(BaseModel):
    summary: dict[str, int | str]
    coverage: dict[str, bool]
    compliance: dict[str, bool | str | int]
    discovery: dict[str, int]
    runtime: dict[str, int | str | bool | None]
    owasp_agentic_risk_mapping: list[dict[str, str]]
    generated_at: str
    verified: bool = False


_IDENTITY_SETTING_PREFIX = "governance.identity:"
_DISCOVERY_SETTING_PREFIX = "governance.discovery:"


async def require_governance_reader(
    current_user: User = Depends(require_roles("VIEWER", "DEVELOPER")),
    _internal_user: User = Depends(get_current_internal_user),
) -> User:
    """Require an internal persisted principal with a read-capable role."""
    return current_user


async def require_governance_developer(
    current_user: User = Depends(require_roles("DEVELOPER")),
    _internal_user: User = Depends(get_current_internal_user),
) -> User:
    """Require an internal persisted principal with mutation privileges."""
    return current_user


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tier_for_score(score: int) -> TrustTier:
    if score >= 900:
        return "critical"
    if score >= 700:
        return "elevated"
    if score >= 500:
        return "trusted"
    return "low"


def _identity_setting_key(agent_id: str) -> str:
    return f"{_IDENTITY_SETTING_PREFIX}{agent_id}"


def _discovery_setting_key(finding_id: str) -> str:
    return f"{_DISCOVERY_SETTING_PREFIX}{finding_id}"


def _parse_identity(value: Any) -> GovernedIdentity | None:
    try:
        return GovernedIdentity.model_validate(value)
    except (TypeError, ValidationError):
        return None


def _parse_finding(value: Any) -> DiscoveryFinding | None:
    try:
        return DiscoveryFinding.model_validate(value)
    except (TypeError, ValidationError):
        return None


async def _owned_agent_ids(db: AsyncSession, current_user: User) -> set[str]:
    result = await db.execute(select(Agent.id).where(Agent.user_id == current_user.id))
    return {str(agent_id) for agent_id in result.scalars()}


async def _identity_records(
    db: AsyncSession,
    current_user: User,
    *,
    owned_agent_ids: set[str] | None = None,
) -> tuple[list[GovernedIdentity], bool]:
    if owned_agent_ids is None:
        owned_agent_ids = await _owned_agent_ids(db, current_user)

    result = await db.execute(
        select(UserSetting)
        .where(
            UserSetting.user_id == current_user.id,
            UserSetting.key.like(f"{_IDENTITY_SETTING_PREFIX}%"),
        )
        .order_by(UserSetting.key)
    )
    identities: list[GovernedIdentity] = []
    valid = True
    for setting in result.scalars().all():
        identity = _parse_identity(setting.value)
        if (
            identity is None
            or setting.key != _identity_setting_key(identity.agent_id)
            or identity.agent_id not in owned_agent_ids
        ):
            logger.warning(
                "Ignoring invalid governance identity setting user_id=%s key=%s",
                current_user.id,
                setting.key,
            )
            valid = False
            continue
        identities.append(identity)
    return identities, valid


async def _discovery_records(
    db: AsyncSession,
    current_user: User,
    *,
    owned_agent_ids: set[str] | None = None,
) -> tuple[list[DiscoveryFinding], bool]:
    if owned_agent_ids is None:
        owned_agent_ids = await _owned_agent_ids(db, current_user)

    result = await db.execute(
        select(UserSetting)
        .where(
            UserSetting.user_id == current_user.id,
            UserSetting.key.like(f"{_DISCOVERY_SETTING_PREFIX}%"),
        )
        .order_by(UserSetting.key)
    )
    findings: list[DiscoveryFinding] = []
    valid = True
    for setting in result.scalars().all():
        finding = _parse_finding(setting.value)
        supervised_agent_is_owned = finding is not None and (
            finding.entity_type != "supervised_agent" or finding.entity_id in owned_agent_ids
        )
        if (
            finding is None
            or setting.key != _discovery_setting_key(finding.finding_id)
            or not supervised_agent_is_owned
        ):
            logger.warning(
                "Ignoring invalid governance discovery setting user_id=%s key=%s",
                current_user.id,
                setting.key,
            )
            valid = False
            continue
        findings.append(finding)
    return findings, valid


async def _require_owned_agent(
    *,
    agent_id: str,
    current_user: User,
    db: AsyncSession,
) -> str:
    try:
        parsed_agent_id = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(
        select(Agent).where(Agent.id == parsed_agent_id, Agent.user_id == current_user.id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return str(agent.id)


def _default_identity(agent_id: str) -> GovernedIdentity:
    return GovernedIdentity(
        agent_id=agent_id,
        display_name=agent_id,
        trust_score=500,
        trust_tier="trusted",
        lifecycle_status="active",
        updated_at=_now(),
    )


async def _mutate_identity(
    db: AsyncSession,
    current_user: User,
    agent_id: str,
    mutate: Callable[[GovernedIdentity], GovernedIdentity],
) -> GovernedIdentity:
    key = _identity_setting_key(agent_id)
    for attempt in range(2):
        result = await db.execute(
            select(UserSetting)
            .where(UserSetting.user_id == current_user.id, UserSetting.key == key)
            .with_for_update()
        )
        setting = result.scalar_one_or_none()
        if setting is None:
            identity = _default_identity(agent_id)
        else:
            identity = _parse_identity(setting.value)
            if identity is None or identity.agent_id != agent_id:
                raise HTTPException(
                    status_code=500,
                    detail="Stored governance identity is invalid",
                )

        updated = mutate(identity)
        if setting is None:
            db.add(
                UserSetting(
                    user_id=current_user.id,
                    key=key,
                    value=updated.model_dump(mode="json"),
                )
            )
        else:
            setting.value = updated.model_dump(mode="json")

        try:
            await db.commit()
            return updated
        except IntegrityError:
            await db.rollback()
            if attempt == 1:
                raise

    raise RuntimeError("Governance identity update retry exhausted")


async def _replace_discovery_records(
    db: AsyncSession,
    current_user: User,
    findings: dict[str, DiscoveryFinding],
) -> None:
    for attempt in range(2):
        # Serialize full-snapshot replacement per tenant, including the empty-inventory case.
        await db.execute(select(User).where(User.id == current_user.id).with_for_update())
        result = await db.execute(
            select(UserSetting)
            .where(
                UserSetting.user_id == current_user.id,
                UserSetting.key.like(f"{_DISCOVERY_SETTING_PREFIX}%"),
            )
            .order_by(UserSetting.key)
            .with_for_update()
        )
        existing = {setting.key: setting for setting in result.scalars().all()}

        for finding_id, finding in findings.items():
            key = _discovery_setting_key(finding_id)
            setting = existing.pop(key, None)
            value = finding.model_dump(mode="json")
            if setting is None:
                db.add(UserSetting(user_id=current_user.id, key=key, value=value))
            else:
                setting.value = value

        for stale_setting in existing.values():
            await db.delete(stale_setting)

        try:
            await db.commit()
            return
        except IntegrityError:
            await db.rollback()
            if attempt == 1:
                raise


def _restricted_runtime_summary() -> dict[str, int | str | bool | None]:
    return {
        "daemon_reachable": False,
        "socket_reachable": False,
        "policy_loaded": False,
        "version": None,
        "policy_name": None,
        "decisions_total": 0,
        "pending_approvals": 0,
        "status": "restricted",
    }


def _runtime_summary(*, include_global: bool) -> dict[str, int | str | bool | None]:
    if not include_global:
        return _restricted_runtime_summary()

    try:
        from cli.faramesh_runtime import collect_faramesh_snapshot, get_faramesh_health

        health = get_faramesh_health()
        snapshot = collect_faramesh_snapshot()
        return {
            "daemon_reachable": health.daemon_reachable,
            "socket_reachable": health.socket_reachable,
            "policy_loaded": health.policy_loaded,
            "version": health.version,
            "policy_name": health.policy_name,
            "decisions_total": snapshot.decisions_total,
            "pending_approvals": snapshot.pending_approvals,
            "status": snapshot.status,
        }
    except Exception:
        summary = _restricted_runtime_summary()
        summary["status"] = "unavailable"
        return summary


async def _credential_backend_count(current_user: User) -> int:
    try:
        from src.api.services.credential_broker import get_credential_broker

        broker = get_credential_broker(namespace=str(current_user.id))
        return len(await broker.list_backends())
    except Exception:
        return 0


def _supervised_agent_count(owned_agent_ids: set[str]) -> int:
    try:
        from src.api.services.faramesh_supervisor import get_faramesh_supervisor

        return sum(
            1
            for agent in get_faramesh_supervisor().list_agents()
            if str(agent.get("agent_id") or agent.get("id") or "") in owned_agent_ids
        )
    except Exception:
        return 0


def _build_attestation(
    *,
    current_user: User,
    credential_backend_count: int,
    identities: list[GovernedIdentity],
    findings: list[DiscoveryFinding],
    owned_agent_ids: set[str],
    stored_records_valid: bool,
    verification_requested: bool,
) -> AttestationBundle:
    is_admin = any(
        isinstance(role, str) and role.strip().upper() == "ADMIN"
        for role in (current_user.roles or [])
    )
    runtime = _runtime_summary(include_global=is_admin)
    supervised_agents = _supervised_agent_count(owned_agent_ids)
    discovery_count = len(findings)
    identities_count = len(identities)
    generated_at = _now()
    verified = verification_requested and stored_records_valid

    runtime_guardrail_presence = bool(
        runtime.get("daemon_reachable") or runtime.get("socket_reachable") or supervised_agents
    )
    credential_broker_presence = credential_backend_count > 0
    discovery_coverage = discovery_count > 0

    return AttestationBundle(
        summary={
            "identities": identities_count,
            "discovery_items": discovery_count,
            "credential_backends": credential_backend_count,
            "supervised_agents": supervised_agents,
            "pending_approvals": int(runtime.get("pending_approvals") or 0),
            "generated_for": str(current_user.id),
        },
        coverage={
            "runtime_guardrail_presence": runtime_guardrail_presence,
            "credential_broker_presence": credential_broker_presence,
            "discovery_coverage": discovery_coverage,
            "receipt_integrity": stored_records_valid,
            "policy_coverage": bool(runtime.get("policy_loaded")),
        },
        compliance={
            "overall_satisfied": (
                runtime_guardrail_presence and credential_broker_presence and stored_records_valid
            ),
            "verified": verified,
        },
        discovery={
            "total": discovery_count,
            "unregistered": sum(
                1 for finding in findings if finding.registration_status == "unregistered"
            ),
        },
        runtime=runtime,
        owasp_agentic_risk_mapping=[
            {
                "risk": "agent_identity_and_permissions",
                "status": "covered" if identities_count else "needs_inventory",
            },
            {
                "risk": "tool_and_secret_exposure",
                "status": "covered" if credential_broker_presence else "needs_broker",
            },
            {
                "risk": "runtime_oversight",
                "status": "covered" if runtime_guardrail_presence else "needs_guardrail",
            },
        ],
        generated_at=generated_at,
        verified=verified,
    )


@router.get("/trust", response_model=GovernanceIdentityList)
async def list_governance_trust(
    current_user: User = Depends(require_governance_reader),
    db: AsyncSession = Depends(get_db),
):
    """List governance trust records."""
    identities, _ = await _identity_records(db, current_user)
    return GovernanceIdentityList(items=identities)


@router.post("/trust/{agent_id}", response_model=GovernedIdentity)
async def update_governance_trust(
    agent_id: str,
    request: GovernanceTrustUpdate,
    current_user: User = Depends(require_governance_developer),
    db: AsyncSession = Depends(get_db),
):
    """Update governance trust metadata for an agent."""
    owned_agent_id = await _require_owned_agent(agent_id=agent_id, current_user=current_user, db=db)

    def mutate(identity: GovernedIdentity) -> GovernedIdentity:
        score = request.score if request.score is not None else identity.trust_score
        if request.delta is not None:
            score += request.delta
        score = max(0, min(1000, score))
        return identity.model_copy(
            update={
                "agent_id": owned_agent_id,
                "trust_score": score,
                "trust_tier": _tier_for_score(score),
                "credential_status": request.credential_status or identity.credential_status,
                "display_name": request.display_name or identity.display_name,
                "capability_scope": (
                    request.capability_scope
                    if request.capability_scope is not None
                    else identity.capability_scope
                ),
                "resource_scope": (
                    request.resource_scope
                    if request.resource_scope is not None
                    else identity.resource_scope
                ),
                "updated_at": _now(),
            }
        )

    return await _mutate_identity(db, current_user, owned_agent_id, mutate)


@router.get("/lifecycle", response_model=GovernanceIdentityList)
async def list_governance_lifecycle(
    current_user: User = Depends(require_governance_reader),
    db: AsyncSession = Depends(get_db),
):
    """List governance lifecycle records."""
    identities, _ = await _identity_records(db, current_user)
    return GovernanceIdentityList(items=identities)


@router.post("/lifecycle/{agent_id}", response_model=GovernedIdentity)
async def update_governance_lifecycle(
    agent_id: str,
    request: GovernanceLifecycleUpdate,
    current_user: User = Depends(require_governance_developer),
    db: AsyncSession = Depends(get_db),
):
    """Update an agent governance lifecycle state."""
    owned_agent_id = await _require_owned_agent(agent_id=agent_id, current_user=current_user, db=db)

    def mutate(identity: GovernedIdentity) -> GovernedIdentity:
        return identity.model_copy(
            update={
                "agent_id": owned_agent_id,
                "lifecycle_status": request.state,
                "updated_at": _now(),
            }
        )

    return await _mutate_identity(db, current_user, owned_agent_id, mutate)


@router.get("/discovery", response_model=DiscoveryList)
async def list_governance_discovery(
    current_user: User = Depends(require_governance_reader),
    db: AsyncSession = Depends(get_db),
):
    """List governance discovery findings."""
    findings, _ = await _discovery_records(db, current_user)
    return DiscoveryList(items=findings)


@router.post("/discovery/scan", response_model=DiscoveryScanResponse)
async def scan_governance_discovery(
    current_user: User = Depends(require_governance_developer),
    db: AsyncSession = Depends(get_db),
):
    """Run a lightweight governance discovery scan of known local runtime state."""
    scanned_at = _now()
    findings: dict[str, DiscoveryFinding] = {}
    owned_agent_ids = await _owned_agent_ids(db, current_user)
    identities, _ = await _identity_records(
        db,
        current_user,
        owned_agent_ids=owned_agent_ids,
    )
    registered_agent_ids = {identity.agent_id for identity in identities}

    try:
        from src.api.services.faramesh_supervisor import get_faramesh_supervisor

        for agent in get_faramesh_supervisor().list_agents():
            agent_id = str(agent.get("agent_id") or agent.get("id") or "")
            if not agent_id or agent_id not in owned_agent_ids:
                continue
            findings[f"supervised:{agent_id}"] = DiscoveryFinding(
                finding_id=f"supervised:{agent_id}",
                entity_id=agent_id,
                entity_type="supervised_agent",
                title=f"Supervised agent {agent_id}",
                source="faramesh_supervisor",
                risk_level="low",
                registration_status=(
                    "registered" if agent_id in registered_agent_ids else "unregistered"
                ),
                confidence=0.9,
                discovered_at=scanned_at,
            )
    except Exception:
        logger.exception("Failed to scan Faramesh supervisor for governance discovery")

    await _replace_discovery_records(db, current_user, findings)
    return DiscoveryScanResponse(
        count=len(findings),
        scanned_at=scanned_at,
        items=list(findings.values()),
    )


@router.get("/attestations", response_model=AttestationBundle)
async def get_governance_attestations(
    current_user: User = Depends(require_governance_reader),
    db: AsyncSession = Depends(get_db),
):
    """Return a governance attestation bundle for the current operator."""
    owned_agent_ids = await _owned_agent_ids(db, current_user)
    identities, identities_valid = await _identity_records(
        db,
        current_user,
        owned_agent_ids=owned_agent_ids,
    )
    findings, findings_valid = await _discovery_records(
        db,
        current_user,
        owned_agent_ids=owned_agent_ids,
    )
    return _build_attestation(
        current_user=current_user,
        credential_backend_count=await _credential_backend_count(current_user),
        identities=identities,
        findings=findings,
        owned_agent_ids=owned_agent_ids,
        stored_records_valid=identities_valid and findings_valid,
        verification_requested=False,
    )


@router.post("/attestations/verify", response_model=AttestationBundle)
async def verify_governance_attestations(
    current_user: User = Depends(require_governance_developer),
    db: AsyncSession = Depends(get_db),
):
    """Verify and return the current governance attestation bundle."""
    owned_agent_ids = await _owned_agent_ids(db, current_user)
    identities, identities_valid = await _identity_records(
        db,
        current_user,
        owned_agent_ids=owned_agent_ids,
    )
    findings, findings_valid = await _discovery_records(
        db,
        current_user,
        owned_agent_ids=owned_agent_ids,
    )
    bundle = _build_attestation(
        current_user=current_user,
        credential_backend_count=await _credential_backend_count(current_user),
        identities=identities,
        findings=findings,
        owned_agent_ids=owned_agent_ids,
        stored_records_valid=identities_valid and findings_valid,
        verification_requested=True,
    )
    return bundle
