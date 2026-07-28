from unittest.mock import AsyncMock

import pytest

from src.api.services import leads_service


def test_resend_notification_html_escapes_untrusted_values() -> None:
    payload = leads_service._build_resend_lead_payload(
        "attacker@example.com",
        '<img src=x onerror="alert(1)">',
        name='<script>alert("name")</script>',
        message="<b>not trusted</b>",
    )

    html_body = str(payload["html"])
    assert "<script>" not in html_body
    assert "<img" not in html_body
    assert "<b>not trusted</b>" not in html_body
    assert "&lt;script&gt;" in html_body
    assert "&lt;img" in html_body
    assert "&lt;b&gt;not trusted&lt;/b&gt;" in html_body


def test_discord_notification_values_are_bounded() -> None:
    payload = leads_service._build_discord_lead_payload(
        "person@example.com",
        "s" * 5_000,
        name="n" * 5_000,
        company="c" * 5_000,
        message="m" * 5_000,
        tier="t" * 5_000,
        interest="i" * 5_000,
    )

    embed = payload["embeds"][0]
    assert len(embed["description"]) <= 4_096
    assert len(embed["fields"]) <= 25
    assert all(len(field["name"]) <= 256 for field in embed["fields"])
    assert all(len(field["value"]) <= 1_024 for field in embed["fields"])


@pytest.mark.asyncio
@pytest.mark.parametrize("consent", [False, True])
async def test_follow_up_enrolls_audience_only_for_explicit_consent(
    monkeypatch: pytest.MonkeyPatch,
    consent: bool,
) -> None:
    monkeypatch.setattr(leads_service.settings, "resend_api_key", "test-key")
    monkeypatch.setattr(leads_service.settings, "resend_audience_id", "audience-1")
    notify_team = AsyncMock(return_value=True)
    confirm = AsyncMock(return_value=False)
    sync_audience = AsyncMock(return_value=False)
    monkeypatch.setattr(leads_service, "_notify_resend_lead", notify_team)
    monkeypatch.setattr(leads_service, "_send_confirmation", confirm)
    monkeypatch.setattr(leads_service, "_sync_resend_audience", sync_audience)

    await leads_service.notify_new_lead(
        lead_id="11111111-1111-1111-1111-111111111111",
        email="person@example.com",
        source="pico-landing",
        product_updates_consent=consent,
    )

    notify_team.assert_awaited_once()
    confirm.assert_awaited_once()
    assert sync_audience.await_count == (1 if consent else 0)


@pytest.mark.asyncio
async def test_no_notification_channel_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(leads_service.settings, "resend_api_key", None)
    monkeypatch.setattr(leads_service.settings, "lead_discord_webhook_url", None)

    await leads_service.notify_new_lead(
        lead_id="11111111-1111-1111-1111-111111111111",
        email="person@example.com",
        source="contact-page",
        product_updates_consent=False,
    )
