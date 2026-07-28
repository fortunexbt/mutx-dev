"""
Receipt Generator.

Cryptographically signed records binding action, context, policy decision,
and outcome. Enables forensic reconstruction and compliance audit trails.

AARM alignment: contributes to current R5 tamper-evident receipts. Every
generated receipt is signed with Ed25519 and can be verified offline from the
embedded public key. The full current R5 receipt schema is not yet demonstrated.

AARM documentation reference: MIT License, Copyright (c) 2023 Mintlify.
https://github.com/aarm-dev/docs/tree/8eff208b98786b2c9a578b26cb7eaca440ec4020
"""

import hashlib
import json
import secrets
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Optional

from src.security.mediator import NormalizedAction
from src.security.context import SessionContext
from src.security.policy import PolicyDecisionResult


@dataclass
class ActionReceipt:
    """
    Tamper-evident receipt for an action.

    The ActionReceipt binds together:
    - The action that was evaluated
    - The session context at evaluation time
    - The policy decision
    - The actual outcome (executed, blocked, error, etc.)

    Receipts are signed with Ed25519 for tamper detection and offline verification.
    """

    receipt_version: str = "1.0"
    receipt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_id: str = ""
    action_hash: str = ""
    session_id: str = ""

    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)

    agent_id: str = ""
    user_id: str = ""

    policy_decision: str = ""
    policy_rule_id: Optional[str] = None
    policy_rule_name: Optional[str] = None
    decision_reason: str = ""

    outcome: str = ""
    outcome_detail: str = ""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: Optional[int] = None

    session_snapshot: Optional[dict[str, Any]] = None
    prior_action_hashes: list[str] = field(default_factory=list)

    signature: Optional[str] = None
    signed_by: Optional[str] = None
    signature_algorithm: Optional[str] = None
    signing_key_id: Optional[str] = None

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_signed(self) -> bool:
        return self.signature is not None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ActionReceipt":
        """Rebuild an exported receipt for offline verification."""
        payload = dict(value)
        unknown_fields = set(payload) - {item.name for item in fields(cls)}
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unknown receipt fields: {names}")
        timestamp = payload.get("timestamp")
        if isinstance(timestamp, str):
            try:
                payload["timestamp"] = datetime.fromisoformat(timestamp)
            except ValueError as exc:
                raise ValueError("Receipt timestamp must be ISO 8601") from exc
        elif timestamp is not None and not isinstance(timestamp, datetime):
            raise ValueError("Receipt timestamp must be ISO 8601")
        return cls(**payload)

    def signing_payload(self) -> bytes:
        """Return the canonical receipt content covered by the signature."""
        payload = self.to_dict()
        payload.pop("signature", None)
        canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return canonical.encode()

    def compute_hash(self) -> str:
        """
        Compute SHA-256 hash of receipt content.

        This hash can be used to verify the receipt hasn't been tampered with.
        """
        return hashlib.sha256(self.signing_payload()).hexdigest()


@dataclass
class ReceiptChain:
    """
    Chain of receipts for a session.

    Provides full audit trail by linking receipts via action hashes.
    """

    chain_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    root_action_hash: Optional[str] = None
    receipts: list[ActionReceipt] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_receipt(self, receipt: ActionReceipt) -> None:
        """Add a receipt to the chain."""
        self.receipts.append(receipt)
        self.updated_at = datetime.now(timezone.utc)

        if self.root_action_hash is None:
            self.root_action_hash = receipt.action_hash

    def verify_chain(self) -> tuple[bool, list[str]]:
        """
        Verify the integrity of the receipt chain.

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        if not self.receipts:
            return True, []

        for i, receipt in enumerate(self.receipts):
            if i > 0:
                prev_receipt = self.receipts[i - 1]
                if receipt.prior_action_hashes:
                    if prev_receipt.action_hash not in receipt.prior_action_hashes:
                        errors.append(
                            f"Receipt {i}: prior action hash mismatch "
                            f"(expected {prev_receipt.action_hash})"
                        )

        return len(errors) == 0, errors

    def get_receipt(self, receipt_id: str) -> Optional[ActionReceipt]:
        """Get a receipt by ID."""
        for receipt in self.receipts:
            if receipt.receipt_id == receipt_id:
                return receipt
        return None


class ReceiptGenerator:
    """
    Generates tamper-evident receipts for actions.

    The ReceiptGenerator creates signed receipts that prove:
    - What action was evaluated
    - What the policy decision was
    - What the outcome was
    - The state of the session at evaluation time

    Usage:
        generator = ReceiptGenerator()

        # Generate receipt after decision
        receipt = generator.generate(
            action=normalized_action,
            context=session_context,
            decision=policy_result,
            outcome="executed",
        )

        # Store for audit
        storage.store(receipt)
    """

    def __init__(
        self,
        signing_private_key: bytes | str | None = None,
        signing_key_id: str = "mutx-runtime",
    ):
        self._signing_private_key = self._load_private_key(signing_private_key)
        self._signing_key_id = signing_key_id
        self._chains: dict[str, ReceiptChain] = {}
        self._receipts: dict[str, ActionReceipt] = {}

    def generate(
        self,
        action: NormalizedAction,
        context: Optional[SessionContext],
        decision: PolicyDecisionResult,
        outcome: str,
        outcome_detail: str = "",
        duration_ms: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ActionReceipt:
        """
        Generate a receipt for an action.

        Args:
            action: The normalized action
            context: Session context at time of decision
            decision: Policy decision result
            outcome: What actually happened (executed, blocked, error, etc.)
            outcome_detail: Additional outcome details
            duration_ms: Execution duration
            metadata: Additional metadata

        Returns:
            The generated ActionReceipt
        """
        session_snapshot = None
        prior_hashes = []

        if context:
            session_snapshot = {
                "session_id": context.session_id,
                "agent_id": context.agent_id,
                "user_id": context.user_id,
                "tool_call_count": context.tool_call_count,
                "denied_count": context.denied_count,
                "intent_signals": [s.value for s in context.intent_signals],
                "original_request": context.original_request[:500]
                if context.original_request
                else None,
            }
            prior_hashes = context.action_hashes[-10:]

        receipt = ActionReceipt(
            action_id=action.id,
            action_hash=action.action_hash,
            session_id=action.session_id,
            tool_name=action.tool_name,
            tool_args=self._truncate_args(action.tool_args),
            agent_id=action.agent_id,
            user_id=action.user_id,
            policy_decision=decision.decision.value,
            policy_rule_id=decision.rule_id,
            policy_rule_name=decision.rule_name,
            decision_reason=decision.reason,
            outcome=outcome,
            outcome_detail=outcome_detail,
            timestamp=decision.timestamp,
            duration_ms=duration_ms,
            session_snapshot=session_snapshot,
            prior_action_hashes=prior_hashes,
            metadata=metadata or {},
        )

        self.sign(receipt)

        self._receipts[receipt.receipt_id] = receipt

        chain = self._chains.get(action.session_id)
        if not chain:
            chain = ReceiptChain(session_id=action.session_id)
            self._chains[action.session_id] = chain
        chain.add_receipt(receipt)

        return receipt

    def sign(
        self,
        receipt: ActionReceipt,
        private_key: bytes | str | None = None,
        public_key_id: str = "",
    ) -> str:
        """
        Sign a receipt with Ed25519.

        Args:
            receipt: Receipt to sign
            private_key: Optional 32-byte Ed25519 private key seed. The generator's
                configured key is used when omitted.
            public_key_id: Optional stable identifier for the signing key

        Returns:
            The signature as a hex string
        """
        from cryptography.hazmat.primitives import serialization

        key = (
            self._load_private_key(private_key)
            if private_key is not None
            else self._signing_private_key
        )
        public_key = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        receipt.signed_by = public_key.hex()
        receipt.signature_algorithm = "Ed25519"
        receipt.signing_key_id = public_key_id or self._signing_key_id
        signature = key.sign(receipt.signing_payload())
        receipt.signature = signature.hex()
        return signature.hex()

    def verify(
        self,
        receipt: ActionReceipt,
        *,
        trusted_public_key: bytes | str | None = None,
        trusted_key_id: str | None = None,
    ) -> tuple[bool, str]:
        """
        Verify a receipt's integrity.

        Args:
            receipt: Receipt to verify

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not receipt.signature or not receipt.signed_by:
            return False, "Receipt is unsigned"
        if receipt.signature_algorithm != "Ed25519":
            return False, "Receipt does not use Ed25519"
        if trusted_key_id is not None and receipt.signing_key_id != trusted_key_id:
            return False, "Receipt signing key ID is not trusted"

        if trusted_public_key is not None:
            if isinstance(trusted_public_key, bytes):
                trusted_public_key = trusted_public_key.hex()
            try:
                trusted_public_key_bytes = bytes.fromhex(trusted_public_key)
            except ValueError:
                return False, "Trusted Ed25519 public key must be hex-encoded"
            if len(trusted_public_key_bytes) != 32:
                return False, "Trusted Ed25519 public key must contain exactly 32 bytes"
            if not secrets.compare_digest(receipt.signed_by, trusted_public_key.lower()):
                return False, "Receipt signer does not match the trusted public key"

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            public_key_bytes = bytes.fromhex(receipt.signed_by)
            key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            key.verify(bytes.fromhex(receipt.signature), receipt.signing_payload())
            return True, ""
        except Exception as exc:
            return False, f"Signature verification failed: {exc}"

    @staticmethod
    def _load_private_key(private_key: bytes | str | None):
        """Load a 32-byte Ed25519 seed or generate a new signing key."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError as exc:
            raise RuntimeError("Ed25519 receipt signing requires cryptography") from exc

        if private_key is None:
            return Ed25519PrivateKey.generate()
        if isinstance(private_key, str):
            try:
                private_key = bytes.fromhex(private_key)
            except ValueError as exc:
                raise ValueError("Ed25519 private key must be hex-encoded") from exc
        if len(private_key) != 32:
            raise ValueError("Ed25519 private key must contain exactly 32 bytes")
        return Ed25519PrivateKey.from_private_bytes(private_key)

    def get_receipt(self, receipt_id: str) -> Optional[ActionReceipt]:
        """Get a receipt by ID."""
        return self._receipts.get(receipt_id)

    def get_session_chain(self, session_id: str) -> Optional[ReceiptChain]:
        """Get the receipt chain for a session."""
        return self._chains.get(session_id)

    def get_receipts_for_session(self, session_id: str, limit: int = 100) -> list[ActionReceipt]:
        """Get receipts for a session."""
        chain = self._chains.get(session_id)
        if not chain:
            return []
        return chain.receipts[-limit:]

    def _truncate_args(self, args: dict[str, Any], max_length: int = 200) -> dict[str, Any]:
        """Truncate args to prevent oversized receipts."""
        truncated = {}
        for k, v in args.items():
            if isinstance(v, str) and len(v) > max_length:
                truncated[k] = v[:max_length] + "...[truncated]"
            elif isinstance(v, dict):
                truncated[k] = self._truncate_args(v, max_length)
            elif isinstance(v, list):
                truncated[k] = [
                    item[:max_length] + "...[truncated]"
                    if isinstance(item, str) and len(item) > max_length
                    else item
                    for item in v[:10]
                ]
                if len(v) > 10:
                    truncated[k].append(f"...[{len(v) - 10} more items]")
            else:
                truncated[k] = v
        return truncated

    def export_chain(self, session_id: str) -> Optional[dict[str, Any]]:
        """Export a session's receipt chain as JSON-serializable dict."""
        chain = self._chains.get(session_id)
        if not chain:
            return None

        return {
            "chain_id": chain.chain_id,
            "session_id": chain.session_id,
            "root_action_hash": chain.root_action_hash,
            "created_at": chain.created_at.isoformat(),
            "updated_at": chain.updated_at.isoformat(),
            "receipt_count": len(chain.receipts),
            "receipts": [r.to_dict() for r in chain.receipts],
        }
