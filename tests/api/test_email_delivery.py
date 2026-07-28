"""Transactional authentication email delivery contracts."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from src.api.services.email import email_service


@pytest.mark.asyncio
async def test_unconfigured_transactional_email_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(email_service.settings, "resend_api_key", None)
    monkeypatch.setattr(email_service.settings, "smtp_user", "")
    monkeypatch.setattr(email_service.settings, "smtp_password", "")

    delivered = await email_service.send_email(
        "operator@example.com",
        "Verify",
        "<p>Verify</p>",
        "Verify",
    )

    assert delivered is False


@pytest.mark.asyncio
async def test_verification_email_escapes_user_supplied_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_send_email(
        _to_email: str,
        _subject: str,
        html_body: str,
        _text_body: str | None = None,
    ) -> bool:
        captured["html"] = html_body
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send_email)

    delivered = await email_service.send_verification_email(
        "operator@example.com",
        '<img src=x onerror="alert(1)">',
        "safe-token",
        frontend_url="https://app.mutx.dev",
    )

    assert delivered is True
    assert "<img src=x" not in captured["html"]
    assert "&lt;img src=x" in captured["html"]
    assert "https://app.mutx.dev/verify-email?token=safe-token" in captured["html"]


@pytest.mark.asyncio
async def test_verification_email_binds_return_path_in_signed_action_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_send_email(
        _to_email: str,
        _subject: str,
        _html_body: str,
        text_body: str | None = None,
    ) -> bool:
        captured["text"] = text_body or ""
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send_email)

    delivered = await email_service.send_verification_email(
        "operator@example.com",
        "Operator",
        "raw-verification-token",
        frontend_url="https://pico.mutx.dev",
        return_path="/onboarding?step=runtime",
    )

    assert delivered is True
    link = next(
        line.strip()
        for line in captured["text"].splitlines()
        if line.strip().startswith("https://")
    )
    query = parse_qs(urlsplit(link).query)
    raw_token, return_path = email_service.decode_email_action_token(
        query["token"][0],
        purpose="verify-email",
    )
    assert set(query) == {"token"}
    assert raw_token == "raw-verification-token"
    assert return_path == "/onboarding?step=runtime"


def test_email_action_token_rejects_tampering_and_cross_purpose_use() -> None:
    action_token = email_service.encode_email_action_token(
        "raw-reset-token",
        purpose="reset-password",
        return_path="/dashboard/security",
        expires_in=timedelta(hours=1),
    )
    header, payload, signature = action_token.split(".")
    payload_index = len(payload) // 2
    replacement = "a" if payload[payload_index] != "a" else "b"
    tampered_payload = f"{payload[:payload_index]}{replacement}{payload[payload_index + 1 :]}"
    tampered = ".".join((header, tampered_payload, signature))

    with pytest.raises(email_service.EmailActionTokenError):
        email_service.decode_email_action_token(tampered, purpose="reset-password")
    with pytest.raises(email_service.EmailActionTokenError):
        email_service.decode_email_action_token(action_token, purpose="verify-email")
