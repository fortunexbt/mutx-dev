"""
Receipt Generator.

Cryptographically signed records binding action, context, policy decision,
and outcome. Enables forensic reconstruction and compliance audit trails.

AARM alignment: contributes to current R5 tamper-evident receipts. Production
persistence requires platform signing, while the full current R5 receipt schema
is not yet demonstrated.

AARM documentation reference: MIT License, Copyright (c) 2023 Mintlify.
https://github.com/aarm-dev/docs/tree/8eff208b98786b2c9a578b26cb7eaca440ec4020
"""

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from src.security.mediator import NormalizedAction
from src.security.context import SessionContext
from src.security.policy import PolicyDecisionResult


TrustedPublicKeys = Mapping[str, bytes | str]


class ReceiptSigningError(RuntimeError):
    """A required receipt could not be signed by the configured platform key."""


def _validate_key_id(key_id: str) -> str:
    """Validate an immutable, log-safe receipt signer identifier."""
    if not isinstance(key_id, str) or not key_id or len(key_id) > 128:
        raise ValueError("Receipt signing key ID must contain between 1 and 128 characters")
    allowed = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/-")
    if any(character not in allowed for character in key_id):
        raise ValueError(
            "Receipt signing key ID may contain only letters, numbers, '.', '_', ':', '/', or '-'"
        )
    return key_id


def _decode_ed25519_key(value: bytes | str, *, label: str) -> bytes:
    """Decode an exact-length raw Ed25519 key without reflecting key material in errors."""
    if isinstance(value, str):
        try:
            value = bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a hex-encoded Ed25519 key") from exc
    if not isinstance(value, bytes):
        raise ValueError(f"{label} must be raw bytes or a hex-encoded Ed25519 key")
    if len(value) != 32:
        raise ValueError(f"{label} must encode exactly 32 bytes")
    return value


@dataclass
class ActionReceipt:
    """
    Tamper-evident receipt for an action.

    The ActionReceipt binds together:
    - The action that was evaluated
    - The session context at evaluation time
    - The policy decision
    - The actual outcome (executed, blocked, error, etc.)

    New receipts identify an Ed25519 signer by key ID. Public verification key
    material is deliberately not carried by or trusted from the receipt.
    """

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
    signer_key_id: Optional[str] = None

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_signed(self) -> bool:
        """Return whether the receipt has complete signature metadata."""
        return bool(self.signature and (self.signer_key_id or self.signed_by))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)

    def to_signing_json(self) -> str:
        """Serialize the fields bound by a receipt signature."""
        payload = self.to_dict()
        payload.pop("signature")
        return json.dumps(payload, sort_keys=True)

    def _to_unbound_signer_signing_json(self) -> str:
        """Serialize the earlier Ed25519 payload that did not bind signer metadata."""
        payload = self.to_dict()
        payload.pop("signature")
        payload.pop("signed_by")
        payload.pop("signer_key_id")
        return json.dumps(payload, sort_keys=True)

    def _to_legacy_signing_json(self) -> str:
        """Serialize the pre-exclusion Ed25519 payload for verification compatibility."""
        payload = self.to_dict()
        payload.pop("signer_key_id")
        payload["signature"] = None
        payload["signed_by"] = None
        return json.dumps(payload, sort_keys=True)

    def compute_hash(self) -> str:
        """
        Compute SHA-256 hash of receipt content.

        This hash can be used to verify the receipt hasn't been tampered with.
        """
        canonical = self.to_json()
        return hashlib.sha256(canonical.encode()).hexdigest()


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

        # Sign receipt
        generator.sign(receipt, private_key, "platform-key-2026-01")

        # Store for audit
        storage.store(receipt)
    """

    def __init__(
        self,
        *,
        signing_private_key: bytes | str | None = None,
        signing_key_id: str | None = None,
        trusted_public_keys: TrustedPublicKeys | None = None,
        signing_required: bool = False,
    ) -> None:
        self._chains: dict[str, ReceiptChain] = {}
        self._receipts: dict[str, ActionReceipt] = {}
        self._signing_required = signing_required
        self._signing_private_key = (
            _decode_ed25519_key(signing_private_key, label="Receipt signing private key")
            if signing_private_key is not None
            else None
        )
        self._signing_key_id = (
            _validate_key_id(signing_key_id) if signing_key_id is not None else None
        )
        if (self._signing_private_key is None) != (self._signing_key_id is None):
            raise ValueError("Receipt signing private key and key ID must be configured together")

        self._trusted_public_keys = {
            _validate_key_id(key_id): _decode_ed25519_key(
                public_key,
                label=f"Trusted public key for receipt signer {key_id!r}",
            )
            for key_id, public_key in (trusted_public_keys or {}).items()
        }
        if self._signing_private_key is not None and self._signing_key_id is not None:
            trusted_public_key = self._trusted_public_keys.get(self._signing_key_id)
            if trusted_public_key is None:
                raise ValueError(
                    "Configured receipt signing key ID must exist in the trusted public key registry"
                )
            if trusted_public_key != self.public_key_bytes(self._signing_private_key):
                raise ValueError(
                    "Configured receipt signing key does not match its trusted public key"
                )

    @property
    def signing_required(self) -> bool:
        """Return whether persistence must fail closed without a platform signature."""
        return self._signing_required

    @staticmethod
    def public_key_bytes(private_key: bytes | str) -> bytes:
        """Derive raw Ed25519 public key bytes for configuration validation."""
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError as exc:
            raise RuntimeError(
                "Ed25519 signing unavailable: the cryptography package is required"
            ) from exc

        private_key_bytes = _decode_ed25519_key(
            private_key,
            label="Receipt signing private key",
        )
        key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        return key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

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
        private_key: bytes | str,
        key_id: str | None = None,
        *,
        public_key_id: str | None = None,
    ) -> str:
        """
        Sign a receipt with Ed25519.

        Args:
            receipt: Receipt to sign
            private_key: Ed25519 private key bytes
            key_id: Identifier resolved through a verifier-controlled trusted key registry
            public_key_id: Legacy public-key identifier alias; retained only as a bound key ID

        Returns:
            The signature as a hex string

        Raises:
            RuntimeError: If Ed25519 support is unavailable
            ValueError: If the signing key metadata is invalid or does not match
        """
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError as exc:
            raise RuntimeError(
                "Ed25519 signing unavailable: the cryptography package is required"
            ) from exc

        private_key_bytes = _decode_ed25519_key(
            private_key,
            label="Receipt signing private key",
        )
        derived_public_key = self.public_key_bytes(private_key_bytes)
        if key_id is not None and public_key_id:
            raise ValueError("Specify either key_id or legacy public_key_id, not both")
        if key_id is None:
            if public_key_id:
                supplied_public_key = _decode_ed25519_key(
                    public_key_id,
                    label="Legacy receipt public key ID",
                )
                if supplied_public_key != derived_public_key:
                    raise ValueError(
                        "Legacy receipt public key ID does not match the supplied private key"
                    )
            signer = derived_public_key.hex()
        else:
            signer = _validate_key_id(key_id)
        trusted_public_key = self._trusted_public_keys.get(signer)
        if trusted_public_key is not None and trusted_public_key != derived_public_key:
            raise ValueError("Receipt signing key does not match its trusted public key")

        key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        original_signature = receipt.signature
        original_signed_by = receipt.signed_by
        original_signer_key_id = receipt.signer_key_id
        receipt.signature = None
        receipt.signed_by = signer
        receipt.signer_key_id = signer
        try:
            signature = key.sign(receipt.to_signing_json().encode())
        except Exception:
            receipt.signature = original_signature
            receipt.signed_by = original_signed_by
            receipt.signer_key_id = original_signer_key_id
            raise
        encoded_signature = signature.hex()
        receipt.signature = encoded_signature

        return encoded_signature

    def sign_for_persistence(self, receipt: ActionReceipt) -> str | None:
        """Sign with the configured platform key, failing closed when required."""
        if self._signing_private_key is None or self._signing_key_id is None:
            if self._signing_required:
                raise ReceiptSigningError(
                    "A platform Ed25519 receipt signing key is required before persistence"
                )
            return None
        try:
            return self.sign(receipt, self._signing_private_key, self._signing_key_id)
        except (RuntimeError, ValueError) as exc:
            raise ReceiptSigningError("The platform receipt could not be signed") from exc

    def verify(self, receipt: ActionReceipt) -> tuple[bool, str]:
        """
        Verify a receipt's integrity.

        Args:
            receipt: Receipt to verify

        Returns:
            Tuple of (is_valid, error_message)
        """
        if (
            receipt.signature is None
            and receipt.signed_by is None
            and receipt.signer_key_id is None
        ):
            return False, "Receipt is unsigned and cannot be cryptographically verified"
        if not receipt.signature:
            return False, "Receipt signature is missing"
        key_id = receipt.signer_key_id or receipt.signed_by
        if not key_id:
            return False, "Receipt signer key ID is missing"
        if receipt.signer_key_id and receipt.signed_by != receipt.signer_key_id:
            return False, "Receipt signer key identifiers do not match"
        if key_id == "hmac-fallback":
            return False, "Legacy HMAC fallback receipts are insecure and unverifiable"

        try:
            key_id = _validate_key_id(key_id)
        except ValueError:
            return False, "Receipt signer key ID is malformed"
        public_key_bytes = self._trusted_public_keys.get(key_id)
        if public_key_bytes is None:
            return False, "Receipt signer key is not trusted"

        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError:
            return False, "Ed25519 verification unavailable: the cryptography package is required"

        try:
            signature = bytes.fromhex(receipt.signature)
        except (TypeError, ValueError):
            return False, "Receipt signature is malformed"

        if len(signature) != 64:
            return False, "Receipt signature must encode exactly 64 bytes"

        try:
            key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            key.verify(signature, receipt.to_signing_json().encode())
        except InvalidSignature:
            if receipt.signer_key_id is not None:
                return False, "Receipt signature mismatch"
            for legacy_payload in (
                receipt._to_unbound_signer_signing_json(),
                receipt._to_legacy_signing_json(),
            ):
                try:
                    key.verify(signature, legacy_payload.encode())
                    return True, ""
                except InvalidSignature:
                    continue
            return False, "Receipt signature mismatch"
        except (TypeError, ValueError):
            return False, "Receipt signature or signing key is malformed"

        return True, ""

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
