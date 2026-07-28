"""Canonical composition root for runtime security enforcement and evidence."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import uuid

from src.api.config import get_settings
from src.api.integrations.tool_names import RUNTIME_BUILTIN_TOOL_NAMES
from src.api.services.audit_log import AuditEvent, AuditEventType, AuditLog, get_audit_log
from src.security import (
    ActionMediator,
    ApprovalRequest,
    ApprovalService,
    ContextAccumulator,
    NormalizedAction,
    PolicyDecision,
    PolicyDecisionResult,
    PolicyEngine,
    ReceiptGenerator,
    TelemetryEventType,
    TelemetryExporter,
)
from src.security.context import SessionContext
from src.security.policy import PolicyRule, PolicySet
from src.security.receipts import ActionReceipt

AuditLogFactory = Callable[[], Awaitable[AuditLog]]


@dataclass
class GovernanceEvaluation:
    """A normalized action and its pre-execution policy decision."""

    action: NormalizedAction
    context: SessionContext
    decision: PolicyDecisionResult
    decision_id: str
    run_id: str
    actor_type: str
    actor_id: str
    actor_display: str | None
    policy_refs: list[str]
    approval: ApprovalRequest | None = None


class GovernanceRuntime:
    """Coordinate mediation, policy, approvals, receipts, telemetry, and audit."""

    SAFE_BUILTIN_TOOLS = RUNTIME_BUILTIN_TOOL_NAMES

    def __init__(
        self,
        *,
        mediator: ActionMediator | None = None,
        context_accumulator: ContextAccumulator | None = None,
        policy_engine: PolicyEngine | None = None,
        approval_service: ApprovalService | None = None,
        receipt_generator: ReceiptGenerator | None = None,
        telemetry_exporter: TelemetryExporter | None = None,
        audit_log_factory: AuditLogFactory = get_audit_log,
        install_default_policy: bool = True,
    ) -> None:
        self.mediator = mediator or ActionMediator()
        self.context_accumulator = context_accumulator or ContextAccumulator()
        self.policy_engine = policy_engine or PolicyEngine()
        self.approval_service = approval_service or ApprovalService()
        self.receipt_generator = receipt_generator or ReceiptGenerator()
        self.telemetry_exporter = telemetry_exporter or TelemetryExporter()
        self.audit_log_factory = audit_log_factory
        self._evidence_lock = asyncio.Lock()

        if install_default_policy and not self.policy_engine.list_policies():
            self.policy_engine.add_policy(self._default_policy(), set_default=True)

    @classmethod
    def _default_policy(cls) -> PolicySet:
        policy = PolicySet(
            id="mutx-runtime-default",
            name="MUTX runtime default",
            description="Allow low-risk built-ins and deny unconfigured custom tools.",
            default_decision=PolicyDecision.DENY,
        )
        for priority, tool_name in enumerate(cls.SAFE_BUILTIN_TOOLS, start=10):
            policy.add_rule(
                PolicyRule(
                    id=f"allow-{tool_name}",
                    name=f"Allow {tool_name}",
                    priority=priority,
                    tool_pattern=tool_name,
                    action=PolicyDecision.ALLOW,
                    reason="Low-risk built-in tool",
                )
            )
        return policy

    def authorize(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        agent_id: str,
        session_id: str,
        run_id: str,
        user_id: str = "",
        actor_type: str = "agent",
        actor_id: str | None = None,
        actor_display: str | None = None,
        trigger: str = "agent",
    ) -> GovernanceEvaluation:
        """Normalize and evaluate a tool call before its handler can run."""
        resolved_actor_id = actor_id or agent_id
        context = self.context_accumulator.get_context(session_id)
        if context is None:
            context = self.context_accumulator.create_session(
                session_id=session_id,
                agent_id=agent_id,
                user_id=user_id,
                metadata={"run_id": run_id},
            )

        action = self.mediator.intercept(
            tool_name=tool_name,
            tool_args=tool_args,
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            trigger=trigger,
            runtime="mutx-agent-runtime",
        )
        decision = self.policy_engine.evaluate(action, context)
        policy_refs = self._resolve_policy_refs(decision)
        decision_id = str(uuid.uuid4())
        approval = None
        if decision.is_deferred:
            approval = self.approval_service.request_approval(
                action=action,
                context=context,
                reason=decision.reason,
                metadata={"run_id": run_id, "policy_decision_id": decision_id},
            )

        return GovernanceEvaluation(
            action=action,
            context=context,
            decision=decision,
            decision_id=decision_id,
            run_id=run_id,
            actor_type=actor_type,
            actor_id=resolved_actor_id,
            actor_display=actor_display,
            policy_refs=policy_refs,
            approval=approval,
        )

    def _resolve_policy_refs(self, decision: PolicyDecisionResult) -> list[str]:
        """Identify the policy set and rule that produced a decision."""
        policy_summaries = self.policy_engine.list_policies()
        policy_id = None
        if decision.rule_id:
            for summary in policy_summaries:
                policy = self.policy_engine.get_policy(summary["id"])
                if policy and policy.get_rule(decision.rule_id):
                    policy_id = policy.id
                    break
        elif len(policy_summaries) == 1:
            policy_id = policy_summaries[0]["id"]

        return [ref for ref in (policy_id, decision.rule_id) if ref]

    async def record_outcome(
        self,
        evaluation: GovernanceEvaluation,
        *,
        outcome: str,
        outcome_detail: str = "",
        output_preview: str | None = None,
        error: str | None = None,
        cost_record: dict[str, Any] | None = None,
        redaction_status: str = "none",
        telemetry_type: TelemetryEventType | None = None,
    ) -> tuple[ActionReceipt, AuditEvent]:
        """Generate a receipt and append hash-chained governed-operation evidence."""
        async with self._evidence_lock:
            return await self._record_outcome(
                evaluation,
                outcome=outcome,
                outcome_detail=outcome_detail,
                output_preview=output_preview,
                error=error,
                cost_record=cost_record,
                redaction_status=redaction_status,
                telemetry_type=telemetry_type,
            )

    async def _record_outcome(
        self,
        evaluation: GovernanceEvaluation,
        *,
        outcome: str,
        outcome_detail: str = "",
        output_preview: str | None = None,
        error: str | None = None,
        cost_record: dict[str, Any] | None = None,
        redaction_status: str = "none",
        telemetry_type: TelemetryEventType | None = None,
    ) -> tuple[ActionReceipt, AuditEvent]:
        """Persist evidence while the caller holds the evidence sequencing lock."""
        decision = evaluation.decision
        if decision.is_denied:
            effect = "DENY"
            resolved_telemetry_type = TelemetryEventType.ACTION_DENIED
        elif decision.is_deferred:
            effect = "DEFER"
            resolved_telemetry_type = TelemetryEventType.ACTION_DEFERRED
        else:
            effect = "PERMIT"
            resolved_telemetry_type = (
                TelemetryEventType.ACTION_FAILED if error else TelemetryEventType.ACTION_EXECUTED
            )
        resolved_telemetry_type = telemetry_type or resolved_telemetry_type

        receipt = self.receipt_generator.generate(
            action=evaluation.action,
            context=evaluation.context,
            decision=decision,
            outcome=outcome,
            outcome_detail=outcome_detail,
            metadata={
                "run_id": evaluation.run_id,
                "policy_decision_id": evaluation.decision_id,
                "approval_id": evaluation.approval.id if evaluation.approval else None,
            },
        )
        audit_event = self._build_audit_event(
            evaluation,
            receipt=receipt,
            event_type=AuditEventType.POLICY_CHECK,
            outcome=outcome,
            cost_record=cost_record,
            redaction_status=redaction_status,
        )
        audit_log = await self.audit_log_factory()
        await audit_log.log_with_otel_context(audit_event)

        self.context_accumulator.record_action(
            evaluation.action.session_id,
            evaluation.action,
            effect,
            decision_reason=decision.reason,
            output_preview=output_preview,
            error=error,
        )
        self.telemetry_exporter.export_security_event(
            event_type=resolved_telemetry_type,
            action=evaluation.action,
            decision=decision,
            receipt=receipt,
            error=error,
            metadata={"run_id": evaluation.run_id},
        )
        return receipt, audit_event

    async def record_authorization(
        self,
        evaluation: GovernanceEvaluation,
    ) -> tuple[ActionReceipt, AuditEvent]:
        """Durably record an allow/modify decision before a tool can execute."""
        return await self.record_outcome(
            evaluation,
            outcome="authorized",
            outcome_detail=evaluation.decision.reason,
            telemetry_type=TelemetryEventType.ACTION_ALLOWED,
        )

    async def record_execution_result(
        self,
        evaluation: GovernanceEvaluation,
        *,
        authorization_receipt: ActionReceipt,
        outcome: str,
        output_preview: str | None = None,
        error: str | None = None,
        cost_record: dict[str, Any] | None = None,
        redaction_status: str = "none",
    ) -> AuditEvent:
        """Append the result linked to a previously persisted authorization."""
        audit_event = self._build_audit_event(
            evaluation,
            receipt=authorization_receipt,
            event_type=AuditEventType.TOOL_CALL,
            outcome=outcome,
            cost_record=cost_record,
            redaction_status=redaction_status,
            output_preview=output_preview,
            error=error,
        )
        audit_log = await self.audit_log_factory()
        await audit_log.log_with_otel_context(audit_event)
        self.telemetry_exporter.export_security_event(
            event_type=(
                TelemetryEventType.ACTION_FAILED if error else TelemetryEventType.ACTION_EXECUTED
            ),
            action=evaluation.action,
            decision=evaluation.decision,
            receipt=authorization_receipt,
            error=error,
            metadata={"run_id": evaluation.run_id},
            track_metrics=False,
        )
        return audit_event

    @staticmethod
    def _build_audit_event(
        evaluation: GovernanceEvaluation,
        *,
        receipt: ActionReceipt,
        event_type: AuditEventType,
        outcome: str,
        cost_record: dict[str, Any] | None = None,
        redaction_status: str = "none",
        output_preview: str | None = None,
        error: str | None = None,
    ) -> AuditEvent:
        """Build a governed-operation event linked to its authorization receipt."""
        return AuditEvent(
            event_id=uuid.uuid4(),
            agent_id=evaluation.action.agent_id,
            session_id=evaluation.action.session_id,
            run_id=evaluation.run_id,
            event_type=event_type,
            payload={
                "action_id": evaluation.action.id,
                "action_hash": evaluation.action.action_hash,
                "tool_name": evaluation.action.tool_name,
                "decision": evaluation.decision.decision.value,
                "reason": evaluation.decision.reason,
                "outcome": outcome,
                "receipt_id": receipt.receipt_id,
                "receipt_hash": receipt.compute_hash(),
                "output_preview": output_preview,
                "error": error,
            },
            timestamp=datetime.now(timezone.utc),
            actor_type=evaluation.actor_type,
            actor_id=evaluation.actor_id,
            actor_display=evaluation.actor_display,
            policy_decision_id=evaluation.decision_id,
            policy_refs=evaluation.policy_refs,
            approval_id=evaluation.approval.id if evaluation.approval else None,
            cost_record=cost_record,
            redaction_status=redaction_status,
        )


_governance_runtime: GovernanceRuntime | None = None


def get_governance_runtime() -> GovernanceRuntime:
    """Return the process-wide security composition root."""
    global _governance_runtime
    if _governance_runtime is None:
        settings = get_settings()
        receipt_generator = ReceiptGenerator(
            signing_private_key=settings.receipt_signing_private_key,
            signing_key_id=settings.receipt_signing_key_id,
        )
        _governance_runtime = GovernanceRuntime(receipt_generator=receipt_generator)
    return _governance_runtime
