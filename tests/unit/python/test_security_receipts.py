"""Focused cryptographic trust-boundary tests for action receipts."""

import builtins
from copy import deepcopy
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import hmac
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from src.security.receipts import ActionReceipt, ReceiptGenerator, ReceiptSigningError


PLATFORM_KEY_ID = "mutx-platform-2026-01"
BOUND_FIELD_TAMPERS = {
    "receipt_id": "receipt-tampered",
    "action_id": "action-tampered",
    "action_hash": "hash-tampered",
    "session_id": "session-tampered",
    "tool_name": "shell.exec",
    "tool_args": {"path": "/tampered"},
    "agent_id": "agent-tampered",
    "user_id": "user-tampered",
    "policy_decision": "deny",
    "policy_rule_id": "rule-tampered",
    "policy_rule_name": "Tampered rule",
    "decision_reason": "tampered reason",
    "outcome": "blocked",
    "outcome_detail": "tampered detail",
    "timestamp": datetime(2025, 2, 3, 4, 5, 7, tzinfo=timezone.utc),
    "duration_ms": 43,
    "session_snapshot": {"risk": "tampered"},
    "prior_action_hashes": ["prior-tampered"],
    "metadata": {"source": "tampered"},
}


@pytest.fixture
def receipt() -> ActionReceipt:
    return ActionReceipt(
        receipt_id="receipt-1",
        action_id="action-1",
        action_hash="hash-1",
        session_id="session-1",
        tool_name="file.read",
        tool_args={"path": "/safe", "options": {"limit": 10}},
        agent_id="agent-1",
        user_id="user-1",
        policy_decision="allow",
        policy_rule_id="rule-1",
        policy_rule_name="Allow safe reads",
        decision_reason="read is within policy",
        outcome="executed",
        outcome_detail="read completed",
        timestamp=datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc),
        duration_ms=42,
        session_snapshot={"risk": "low", "tool_call_count": 1},
        prior_action_hashes=["prior-1"],
        metadata={"source": "unit-test", "nested": {"bound": True}},
    )


@pytest.fixture
def private_key_bytes() -> bytes:
    return Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _public_key_bytes(private_key_bytes: bytes) -> bytes:
    return ReceiptGenerator.public_key_bytes(private_key_bytes)


def _trusted_generator(
    private_key_bytes: bytes,
    *key_ids: str,
) -> ReceiptGenerator:
    public_key = _public_key_bytes(private_key_bytes)
    return ReceiptGenerator(
        trusted_public_keys={key_id: public_key for key_id in key_ids or (PLATFORM_KEY_ID,)}
    )


def _block_cryptography_import(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "cryptography" or name.startswith("cryptography."):
            raise ImportError("simulated missing cryptography")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)


def test_valid_ed25519_receipt_binds_key_id_and_verifies_from_registry(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
) -> None:
    generator = _trusted_generator(private_key_bytes)

    signature = generator.sign(receipt, private_key_bytes, PLATFORM_KEY_ID)

    assert receipt.signature == signature
    assert receipt.signer_key_id == PLATFORM_KEY_ID
    assert receipt.signed_by == PLATFORM_KEY_ID
    assert receipt.signed_by != _public_key_bytes(private_key_bytes).hex()
    assert receipt.is_signed is True
    assert generator.verify(receipt) == (True, "")


@pytest.mark.parametrize("provide_legacy_public_key", [False, True])
def test_legacy_sign_call_derives_a_bound_key_id_but_still_requires_registry(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
    provide_legacy_public_key: bool,
) -> None:
    legacy_key_id = _public_key_bytes(private_key_bytes).hex()
    verifier = _trusted_generator(private_key_bytes, legacy_key_id)

    verifier.sign(
        receipt,
        private_key_bytes,
        public_key_id=legacy_key_id if provide_legacy_public_key else None,
    )

    assert receipt.signer_key_id == legacy_key_id
    assert verifier.verify(receipt) == (True, "")


def test_signing_serialization_binds_signer_metadata_but_excludes_signature(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
) -> None:
    generator = _trusted_generator(private_key_bytes)

    first_signature = generator.sign(receipt, private_key_bytes, PLATFORM_KEY_ID)
    second_signature = generator.sign(receipt, private_key_bytes, PLATFORM_KEY_ID)
    signing_payload = json.loads(receipt.to_signing_json())

    expected_fields = {item.name for item in fields(ActionReceipt)} - {"signature"}
    assert set(signing_payload) == expected_fields
    assert signing_payload["signer_key_id"] == PLATFORM_KEY_ID
    assert signing_payload["signed_by"] == PLATFORM_KEY_ID
    assert first_signature == second_signature
    assert first_signature not in receipt.to_signing_json()


def test_signer_key_id_tampering_fails_even_when_both_ids_resolve_to_same_key(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
) -> None:
    rotated_key_id = "mutx-platform-alias"
    generator = _trusted_generator(private_key_bytes, PLATFORM_KEY_ID, rotated_key_id)
    generator.sign(receipt, private_key_bytes, PLATFORM_KEY_ID)

    receipt.signer_key_id = rotated_key_id
    receipt.signed_by = rotated_key_id

    assert generator.verify(receipt) == (False, "Receipt signature mismatch")


def test_verifier_does_not_trust_key_material_selected_by_receipt(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
) -> None:
    attacker_private_key = Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    ReceiptGenerator().sign(receipt, attacker_private_key, PLATFORM_KEY_ID)

    trusted_verifier = _trusted_generator(private_key_bytes)

    assert trusted_verifier.verify(receipt) == (False, "Receipt signature mismatch")


def test_verification_requires_an_external_trusted_key_registry(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
) -> None:
    ReceiptGenerator().sign(receipt, private_key_bytes, PLATFORM_KEY_ID)

    assert ReceiptGenerator().verify(receipt) == (
        False,
        "Receipt signer key is not trusted",
    )


def test_legacy_ed25519_receipt_requires_explicitly_trusted_external_key(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
) -> None:
    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    legacy_key_id = _public_key_bytes(private_key_bytes).hex()
    receipt.signature = private_key.sign(receipt._to_legacy_signing_json().encode()).hex()
    receipt.signed_by = legacy_key_id

    assert ReceiptGenerator().verify(receipt) == (False, "Receipt signer key is not trusted")
    trusted_verifier = _trusted_generator(private_key_bytes, legacy_key_id)
    assert trusted_verifier.verify(receipt) == (True, "")

    receipt.outcome = "tampered"
    assert trusted_verifier.verify(receipt) == (False, "Receipt signature mismatch")


def test_previous_unbound_signer_format_is_accepted_only_through_trusted_registry(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
) -> None:
    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    legacy_key_id = _public_key_bytes(private_key_bytes).hex()
    receipt.signature = private_key.sign(receipt._to_unbound_signer_signing_json().encode()).hex()
    receipt.signed_by = legacy_key_id

    assert ReceiptGenerator().verify(receipt) == (False, "Receipt signer key is not trusted")
    assert _trusted_generator(private_key_bytes, legacy_key_id).verify(receipt) == (True, "")


@pytest.mark.parametrize(
    ("field_name", "tampered_value"),
    BOUND_FIELD_TAMPERS.items(),
)
def test_tampering_any_bound_field_is_rejected(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
    field_name: str,
    tampered_value: object,
) -> None:
    generator = _trusted_generator(private_key_bytes)
    generator.sign(receipt, private_key_bytes, PLATFORM_KEY_ID)
    tampered_receipt = deepcopy(receipt)
    setattr(tampered_receipt, field_name, tampered_value)

    assert generator.verify(tampered_receipt) == (False, "Receipt signature mismatch")


def test_signature_tampering_is_rejected(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
) -> None:
    generator = _trusted_generator(private_key_bytes)
    generator.sign(receipt, private_key_bytes, PLATFORM_KEY_ID)
    tampered_signature = bytearray.fromhex(receipt.signature or "")
    tampered_signature[0] ^= 1
    receipt.signature = tampered_signature.hex()

    assert generator.verify(receipt) == (False, "Receipt signature mismatch")


@pytest.mark.parametrize(
    ("signature", "expected_error"),
    [
        ("not-hex", "Receipt signature is malformed"),
        ("00", "Receipt signature must encode exactly 64 bytes"),
    ],
)
def test_malformed_signature_is_rejected(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
    signature: str,
    expected_error: str,
) -> None:
    generator = _trusted_generator(private_key_bytes)
    generator.sign(receipt, private_key_bytes, PLATFORM_KEY_ID)
    receipt.signature = signature

    assert generator.verify(receipt) == (False, expected_error)


def test_mismatched_signer_key_identifiers_are_rejected(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
) -> None:
    generator = _trusted_generator(private_key_bytes)
    generator.sign(receipt, private_key_bytes, PLATFORM_KEY_ID)
    receipt.signed_by = "different-key"

    assert generator.verify(receipt) == (
        False,
        "Receipt signer key identifiers do not match",
    )


def test_signing_fails_closed_when_cryptography_is_unavailable(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = ReceiptGenerator()
    _block_cryptography_import(monkeypatch)

    with pytest.raises(RuntimeError, match="Ed25519 signing unavailable"):
        generator.sign(receipt, private_key_bytes, PLATFORM_KEY_ID)

    assert receipt.signature is None
    assert receipt.signed_by is None
    assert receipt.signer_key_id is None
    assert receipt.is_signed is False


def test_verification_fails_closed_when_cryptography_is_unavailable(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _trusted_generator(private_key_bytes)
    generator.sign(receipt, private_key_bytes, PLATFORM_KEY_ID)
    _block_cryptography_import(monkeypatch)

    assert generator.verify(receipt) == (
        False,
        "Ed25519 verification unavailable: the cryptography package is required",
    )


def test_legacy_public_derived_hmac_fallback_is_rejected(receipt: ActionReceipt) -> None:
    legacy_public_id = "hmac-fallback"
    attacker_key = hashlib.sha256(legacy_public_id.encode()).digest()
    receipt.signature = hmac.new(
        attacker_key,
        receipt._to_legacy_signing_json().encode(),
        hashlib.sha256,
    ).hexdigest()
    receipt.signed_by = legacy_public_id

    assert ReceiptGenerator().verify(receipt) == (
        False,
        "Legacy HMAC fallback receipts are insecure and unverifiable",
    )


@pytest.mark.parametrize(
    ("signature", "signed_by", "signer_key_id", "expected_error"),
    [
        (None, None, None, "Receipt is unsigned and cannot be cryptographically verified"),
        ("00" * 64, None, None, "Receipt signer key ID is missing"),
        (None, PLATFORM_KEY_ID, PLATFORM_KEY_ID, "Receipt signature is missing"),
    ],
)
def test_unsigned_or_partially_signed_receipts_are_explicitly_unverifiable(
    receipt: ActionReceipt,
    signature: str | None,
    signed_by: str | None,
    signer_key_id: str | None,
    expected_error: str,
) -> None:
    receipt.signature = signature
    receipt.signed_by = signed_by
    receipt.signer_key_id = signer_key_id

    assert receipt.is_signed is False
    assert ReceiptGenerator().verify(receipt) == (False, expected_error)


def test_required_platform_signing_fails_before_persistence_without_key(
    receipt: ActionReceipt,
) -> None:
    generator = ReceiptGenerator(signing_required=True)

    with pytest.raises(ReceiptSigningError, match="required before persistence"):
        generator.sign_for_persistence(receipt)


def test_configured_platform_signer_signs_for_persistence(
    receipt: ActionReceipt,
    private_key_bytes: bytes,
) -> None:
    public_key = _public_key_bytes(private_key_bytes)
    generator = ReceiptGenerator(
        signing_private_key=private_key_bytes,
        signing_key_id=PLATFORM_KEY_ID,
        trusted_public_keys={PLATFORM_KEY_ID: public_key},
        signing_required=True,
    )

    generator.sign_for_persistence(receipt)

    assert generator.verify(receipt) == (True, "")


def test_configured_signer_must_match_trusted_registry(private_key_bytes: bytes) -> None:
    other_public_key = (
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )

    with pytest.raises(ValueError, match="does not match its trusted public key"):
        ReceiptGenerator(
            signing_private_key=private_key_bytes,
            signing_key_id=PLATFORM_KEY_ID,
            trusted_public_keys={PLATFORM_KEY_ID: other_public_key},
        )
