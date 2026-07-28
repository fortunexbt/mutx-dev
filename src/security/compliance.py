"""Local capability checks mapped to the current AARM requirements.

This module is retained under its historical public names for API compatibility.
Its output is an engineering gap assessment, not an AARM conformance report.
MUTX has not demonstrated every AARM Core technical test or the organizational
conditions required to use the designation "AARM-conformant."

Specification audit ref: aarm-dev/docs@8eff208b98786b2c9a578b26cb7eaca440ec4020
AARM documentation reference: MIT License, Copyright (c) 2023 Mintlify.
See docs/legal/aarm-alignment.md for evidence and gaps.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.security.approvals import ApprovalService
from src.security.context import ContextAccumulator
from src.security.mediator import ActionMediator
from src.security.policy import PolicyEngine
from src.security.receipts import ReceiptGenerator
from src.security.telemetry import TelemetryExporter


class ConformanceLevel(str, Enum):
    """Normative level assigned by the current AARM specification."""

    MUST = "MUST"
    SHOULD = "SHOULD"


@dataclass
class ConformanceResult:
    """Completeness result for one current AARM requirement."""

    requirement_id: str
    level: ConformanceLevel
    description: str
    satisfied: bool
    details: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_met(self) -> bool:
        return self.satisfied


@dataclass
class AARMComplianceReport:
    """Backward-compatible container for the local AARM alignment assessment."""

    version: str = "2026-03-26"
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    overall_satisfied: bool = True
    results: list[ConformanceResult] = field(default_factory=list)

    def add_result(self, result: ConformanceResult) -> None:
        self.results.append(result)
        if not result.satisfied and result.level == ConformanceLevel.MUST:
            self.overall_satisfied = False

    def get_result(self, requirement_id: str) -> Optional[ConformanceResult]:
        for result in self.results:
            if result.requirement_id == requirement_id:
                return result
        return None

    def summary(self) -> dict[str, Any]:
        must_results = [result for result in self.results if result.level == ConformanceLevel.MUST]
        should_results = [
            result for result in self.results if result.level == ConformanceLevel.SHOULD
        ]

        return {
            "overall_satisfied": self.overall_satisfied,
            "total_requirements": len(self.results),
            "must_requirements": len(must_results),
            "must_satisfied": sum(1 for result in must_results if result.satisfied),
            "should_requirements": len(should_results),
            "should_satisfied": sum(1 for result in should_results if result.satisfied),
            "assessment_scope": "local-capability-gap-check",
            "conformance_claim": "none",
        }


@dataclass(frozen=True)
class _RequirementAssessment:
    level: ConformanceLevel
    description: str
    gap: str
    component_attribute: Optional[str] = None


_REQUIREMENTS: dict[str, _RequirementAssessment] = {
    "R1": _RequirementAssessment(
        ConformanceLevel.MUST,
        "Pre-execution interception with blocking, deferral, and fail-closed behavior",
        "Relevant mediation and policy code exists, but interception across every execution "
        "path, zero effects for denied/deferred actions, fail-closed unavailability, and "
        "decision receipts have not all been demonstrated.",
        "policy_engine",
    ),
    "R2": _RequirementAssessment(
        ConformanceLevel.MUST,
        "Context accumulation across actions, data classifications, and original intent",
        "Session actions, data access, and original requests can be stored, but the "
        "highest-sensitivity classification default and full production policy-path "
        "consumption have not been demonstrated.",
        "context_accumulator",
    ),
    "R3": _RequirementAssessment(
        ConformanceLevel.MUST,
        "Static and contextual policy evaluation with required deferral conditions",
        "MUTX has static rules, a context signal, and parameter constraints, but lacks the "
        "complete classification model and mandatory deferral behavior for missing context, "
        "equal-priority conflicts, and low confidence.",
        "policy_engine",
    ),
    "R4": _RequirementAssessment(
        ConformanceLevel.MUST,
        "Five distinct decisions: ALLOW, DENY, MODIFY, STEP_UP, and DEFER",
        "PolicyDecision has no distinct STEP_UP value and approval is conflated with DEFER. "
        "Dependency propagation, ordering, bounded cascades, and deny-on-timeout behavior "
        "have not been demonstrated.",
        "approval_service",
    ),
    "R5": _RequirementAssessment(
        ConformanceLevel.MUST,
        "Signed, offline-verifiable receipts with the complete required evidence",
        "Receipt generation now requires Ed25519 signing, embeds offline verification data, "
        "and rejects unsigned or non-Ed25519 records. The complete service identity, role, "
        "privilege, policy hash/version, approval-resolution, credential-use, and production "
        "path evidence has not been demonstrated for every decision.",
        "receipt_generator",
    ),
    "R6": _RequirementAssessment(
        ConformanceLevel.MUST,
        "Identity binding for human, service, agent, session, role, and privilege scope",
        "User, agent, and session identifiers exist, but service identity, role/privilege "
        "scope, trusted-source freshness and revocation checks, and identity preservation "
        "through deferral/delegation have not been demonstrated.",
        "mediator",
    ),
    "R7": _RequirementAssessment(
        ConformanceLevel.SHOULD,
        "Calibrated cumulative semantic-distance tracking from stated intent",
        "The current denial/error/repetition heuristic is not the semantic-distance and "
        "calibration model described by R7.",
        "context_accumulator",
    ),
    "R8": _RequirementAssessment(
        ConformanceLevel.SHOULD,
        "Structured near-real-time telemetry with filtering and historical export",
        "Custom events and Prometheus metrics exist, but delivery latency, filtering, "
        "complete DEFER coverage, schema stability, and historical batch export have not "
        "been demonstrated against a security platform.",
        "telemetry_exporter",
    ),
    "R9": _RequirementAssessment(
        ConformanceLevel.SHOULD,
        "Just-in-time, operation-scoped least-privilege credentials",
        "No MUTX production-path test proves short-lived operation-scoped issuance, "
        "read-cannot-write enforcement, and credential-use audit evidence.",
    ),
}


class AARMComplianceChecker:
    """Backward-compatible local AARM alignment checker.

    A result is ``satisfied=True`` only when the complete current upstream
    verification is demonstrated. The presence of one component or passing unit
    test is deliberately insufficient.
    """

    def __init__(
        self,
        mediator: Optional[ActionMediator] = None,
        context_accumulator: Optional[ContextAccumulator] = None,
        policy_engine: Optional[PolicyEngine] = None,
        approval_service: Optional[ApprovalService] = None,
        receipt_generator: Optional[ReceiptGenerator] = None,
        telemetry_exporter: Optional[TelemetryExporter] = None,
    ):
        self.mediator = mediator
        self.context_accumulator = context_accumulator
        self.policy_engine = policy_engine
        self.approval_service = approval_service
        self.receipt_generator = receipt_generator
        self.telemetry_exporter = telemetry_exporter

    def _check(self, requirement_id: str) -> ConformanceResult:
        assessment = _REQUIREMENTS[requirement_id]
        component_state = "not applicable"
        if assessment.component_attribute:
            component_state = (
                "configured"
                if getattr(self, assessment.component_attribute) is not None
                else "not configured"
            )

        return ConformanceResult(
            requirement_id=requirement_id,
            level=assessment.level,
            description=assessment.description,
            satisfied=False,
            details=(
                f"Component signal: {component_state}. Gap: {assessment.gap} "
                "This local result is not an AARM validation report."
            ),
        )

    def check_r1(self) -> ConformanceResult:
        return self._check("R1")

    def check_r2(self) -> ConformanceResult:
        return self._check("R2")

    def check_r3(self) -> ConformanceResult:
        return self._check("R3")

    def check_r4(self) -> ConformanceResult:
        return self._check("R4")

    def check_r5(self) -> ConformanceResult:
        return self._check("R5")

    def check_r6(self) -> ConformanceResult:
        return self._check("R6")

    def check_r7(self) -> ConformanceResult:
        return self._check("R7")

    def check_r8(self) -> ConformanceResult:
        return self._check("R8")

    def check_r9(self) -> ConformanceResult:
        return self._check("R9")

    def full_audit(self) -> AARMComplianceReport:
        """Return the complete local gap assessment for current R1-R9."""

        report = AARMComplianceReport()
        for requirement_id in _REQUIREMENTS:
            report.add_result(self._check(requirement_id))
        return report
