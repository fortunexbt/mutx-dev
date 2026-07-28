import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from src.security.context import SessionContext
from src.security.mediator import NormalizedAction
from src.security.policy import PolicyDecision, PolicyDecisionResult
from src.security.receipts import ActionReceipt, ReceiptGenerator


SIGNING_SEED = bytes(range(32))


def _generate_receipt(decision: PolicyDecision = PolicyDecision.ALLOW) -> ActionReceipt:
    generator = ReceiptGenerator(SIGNING_SEED, signing_key_id="test-key-2026-07")
    action = NormalizedAction(
        id="action-1",
        tool_name="deploy",
        tool_args={"environment": "production"},
        agent_id="agent-1",
        session_id="session-1",
        user_id="user-1",
        timestamp=datetime(2026, 7, 22, tzinfo=timezone.utc),
    )
    context = SessionContext(
        session_id="session-1",
        agent_id="agent-1",
        user_id="user-1",
        original_request="Deploy the reviewed production release",
    )
    result = PolicyDecisionResult(
        decision=decision,
        rule_id="release-policy",
        rule_name="Reviewed production release",
        reason="Release policy matched",
        timestamp=datetime(2026, 7, 22, 0, 0, 1, tzinfo=timezone.utc),
    )
    return generator.generate(
        action=action,
        context=context,
        decision=result,
        outcome="authorized" if decision != PolicyDecision.DENY else "blocked",
        metadata={
            "approval_id": "approval-1" if decision == PolicyDecision.DEFER else None,
            "policy_decision_id": "decision-1",
            "run_id": "run-1",
        },
    )


@pytest.mark.parametrize("decision", list(PolicyDecision))
def test_every_policy_decision_receipt_is_ed25519_signed(decision: PolicyDecision) -> None:
    receipt = _generate_receipt(decision)

    assert receipt.is_signed is True
    assert receipt.signature_algorithm == "Ed25519"
    assert receipt.signing_key_id == "test-key-2026-07"
    assert len(receipt.signature or "") == 128
    assert len(receipt.signed_by or "") == 64

    offline_verifier = ReceiptGenerator(bytes(reversed(range(32))))
    assert offline_verifier.verify(receipt) == (True, "")


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("tool_args", {"environment": "unreviewed"}),
        ("user_id", "user-2"),
        ("policy_decision", "allow"),
        ("policy_rule_id", "different-policy"),
        ("outcome", "executed"),
        ("metadata", {"approval_id": "forged-approval"}),
        ("signed_by", "00" * 32),
        ("signing_key_id", "forged-key"),
    ],
)
def test_receipt_verification_rejects_tampering(field: str, tampered_value: object) -> None:
    receipt = deepcopy(_generate_receipt(PolicyDecision.DEFER))
    setattr(receipt, field, tampered_value)

    valid, error = ReceiptGenerator(bytes([42]) * 32).verify(receipt)

    assert valid is False
    assert error.startswith("Signature verification failed:")


def test_receipt_verification_rejects_unsigned_and_non_ed25519_records() -> None:
    generator = ReceiptGenerator(SIGNING_SEED)
    unsigned = ActionReceipt(action_id="action-1")
    assert generator.verify(unsigned) == (False, "Receipt is unsigned")

    receipt = _generate_receipt()
    receipt.signature_algorithm = "HMAC-SHA256"
    assert generator.verify(receipt) == (False, "Receipt does not use Ed25519")


def test_offline_verification_can_pin_the_expected_signer() -> None:
    exported = json.loads(_generate_receipt().to_json())
    receipt = ActionReceipt.from_dict(exported)
    generator = ReceiptGenerator(bytes([42]) * 32)

    assert receipt.receipt_version == "1.0"
    assert generator.verify(
        receipt,
        trusted_public_key=receipt.signed_by,
        trusted_key_id="test-key-2026-07",
    ) == (True, "")
    assert generator.verify(receipt, trusted_public_key="00" * 32) == (
        False,
        "Receipt signer does not match the trusted public key",
    )
    assert generator.verify(receipt, trusted_key_id="retired-key") == (
        False,
        "Receipt signing key ID is not trusted",
    )


def test_offline_receipt_parser_rejects_unknown_fields_and_invalid_timestamps() -> None:
    exported = _generate_receipt().to_dict()
    exported["unexpected"] = True
    with pytest.raises(ValueError, match="Unknown receipt fields: unexpected"):
        ActionReceipt.from_dict(exported)

    exported = _generate_receipt().to_dict()
    exported["timestamp"] = "not-a-timestamp"
    with pytest.raises(ValueError, match="Receipt timestamp must be ISO 8601"):
        ActionReceipt.from_dict(exported)


def test_receipt_signing_key_must_be_an_exact_ed25519_seed() -> None:
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        ReceiptGenerator(b"too-short")
    with pytest.raises(ValueError, match="hex-encoded"):
        ReceiptGenerator("not-hex")


def test_receipt_hash_is_stable_when_only_signature_bytes_change() -> None:
    receipt = _generate_receipt()
    original_hash = receipt.compute_hash()

    receipt.signature = "00" * 64

    assert receipt.compute_hash() == original_hash
    assert ReceiptGenerator(bytes([7]) * 32).verify(receipt)[0] is False
