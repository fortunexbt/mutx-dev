"""Best-effort notifications for durably captured public leads."""

import asyncio
import html
import logging
import os
from datetime import datetime, timezone

import aiohttp

from src.api.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

DISCORD_LEAD_COLOR = 0x4B8DFF
DEFAULT_CONTACT_TEMPLATE_ID = "76afba66-9948-419d-9df2-ae9414006859"
RESEND_EMAILS_URL = "https://api.resend.com/emails"


def _bounded(value: str, limit: int) -> str:
    return value.strip()[:limit]


def _discord_field(name: str, value: str, *, inline: bool) -> dict[str, str | bool]:
    return {
        "name": _bounded(name, 256),
        "value": _bounded(value, 1024) or "(empty)",
        "inline": inline,
    }


def _build_discord_lead_payload(
    email: str,
    source: str | None,
    name: str | None = None,
    company: str | None = None,
    message: str | None = None,
    tier: str | None = None,
    interest: str | None = None,
    product_updates_consent: bool = False,
) -> dict[str, object]:
    fields = [_discord_field("Email", email, inline=True)]
    optional_fields = (
        ("Name", name),
        ("Company", company),
        ("Source", source),
        ("Tier", tier),
        ("Interest", interest),
    )
    fields.extend(
        _discord_field(label, value, inline=True) for label, value in optional_fields if value
    )
    fields.append(
        _discord_field(
            "Product updates",
            "Opted in" if product_updates_consent is True else "Not opted in",
            inline=True,
        )
    )
    if message:
        fields.append(_discord_field("Message", message, inline=False))

    return {
        "username": "MUTX Leads",
        "avatar_url": "https://mutx.dev/logo.png",
        "embeds": [
            {
                "title": "New Lead Captured",
                "description": _bounded(f"{email} submitted a contact request.", 4096),
                "color": DISCORD_LEAD_COLOR,
                "fields": fields[:25],
                "footer": {"text": "MUTX Lead Pipeline"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }


def _html_row(label: str, value: str | None) -> str:
    if not value:
        return ""
    safe_label = html.escape(label, quote=True)
    safe_value = html.escape(value, quote=True)
    return (
        '<tr><td style="padding:8px 12px 8px 0;font-size:13px;font-weight:600;'
        f'">{safe_label}</td><td style="padding:8px 0;font-size:15px;white-space:'
        f'pre-wrap;overflow-wrap:anywhere">{safe_value}</td></tr>'
    )


def _build_resend_lead_payload(
    email: str,
    source: str | None,
    name: str | None = None,
    company: str | None = None,
    message: str | None = None,
    tier: str | None = None,
    interest: str | None = None,
    product_updates_consent: bool = False,
) -> dict[str, object]:
    from_email = settings.resend_from_email or "MUTX <hello@mutx.dev>"
    to_email = (
        settings.resend_lead_alert_email
        or os.getenv("CONTACT_NOTIFY_EMAIL", "").strip()
        or "hello@mutx.dev"
    )
    consent = "Opted in" if product_updates_consent is True else "Not opted in"
    rows = "".join(
        (
            _html_row("Email", email),
            _html_row("Name", name),
            _html_row("Company", company),
            _html_row("Source", source),
            _html_row("Tier", tier),
            _html_row("Interest", interest),
            _html_row("Product updates", consent),
            _html_row("Message", message),
        )
    )
    html_body = (
        '<!doctype html><html><body style="font-family:Arial,sans-serif;color:#131a24">'
        '<h2>New lead captured</h2><table style="width:100%;border-collapse:collapse">'
        f"{rows}</table></body></html>"
    )
    text_lines = [
        "New lead captured",
        f"Email: {email}",
        f"Name: {name}" if name else None,
        f"Company: {company}" if company else None,
        f"Source: {source}" if source else None,
        f"Tier: {tier}" if tier else None,
        f"Interest: {interest}" if interest else None,
        f"Product updates: {consent}",
        f"Message: {message}" if message else None,
    ]
    return {
        "from": from_email,
        "to": [to_email],
        "subject": "New MUTX contact request",
        "html": html_body,
        "text": "\n".join(line for line in text_lines if line),
    }


async def _post_json(
    url: str,
    *,
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
    accepted_statuses: set[int] | None = None,
) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                accepted = accepted_statuses or set(range(200, 300))
                return response.status in accepted
    except Exception:
        return False


async def _notify_discord_lead(
    webhook_url: str,
    *,
    email: str,
    source: str | None,
    name: str | None,
    company: str | None,
    message: str | None,
    tier: str | None,
    interest: str | None,
    product_updates_consent: bool,
) -> bool:
    payload = _build_discord_lead_payload(
        email,
        source,
        name,
        company,
        message,
        tier,
        interest,
        product_updates_consent,
    )
    return await _post_json(webhook_url, payload=payload)


def _resend_headers(lead_id: str, operation: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"lead-{lead_id}-{operation}",
    }


async def _notify_resend_lead(
    lead_id: str,
    *,
    email: str,
    source: str | None,
    name: str | None,
    company: str | None,
    message: str | None,
    tier: str | None,
    interest: str | None,
    product_updates_consent: bool,
) -> bool:
    payload = _build_resend_lead_payload(
        email,
        source,
        name,
        company,
        message,
        tier,
        interest,
        product_updates_consent,
    )
    return await _post_json(
        RESEND_EMAILS_URL,
        payload=payload,
        headers=_resend_headers(lead_id, "team-alert"),
    )


def _contact_template_id(locale: str | None) -> str:
    normalized_locale = (locale or "en").strip().lower().split("-", maxsplit=1)[0]
    return (
        os.getenv(f"RESEND_CONTACT_TEMPLATE_ID_{normalized_locale.upper()}", "").strip()
        or os.getenv("RESEND_CONTACT_TEMPLATE_ID_EN", "").strip()
        or os.getenv("RESEND_CONTACT_TEMPLATE_ID", "").strip()
        or DEFAULT_CONTACT_TEMPLATE_ID
    )


async def _send_confirmation(lead_id: str, email: str, locale: str | None) -> bool:
    payload: dict[str, object] = {
        "from": settings.resend_from_email or "MUTX <hello@mutx.dev>",
        "to": [email],
        "template": {"id": _contact_template_id(locale)},
    }
    return await _post_json(
        RESEND_EMAILS_URL,
        payload=payload,
        headers=_resend_headers(lead_id, "confirmation"),
    )


async def _sync_resend_audience(
    lead_id: str,
    *,
    email: str,
    name: str | None,
    company: str | None,
) -> bool:
    if not settings.resend_audience_id:
        return False
    payload: dict[str, object] = {"email": email}
    if name:
        payload["first_name"] = name
    if company:
        payload["last_name"] = company
    return await _post_json(
        f"https://api.resend.com/audiences/{settings.resend_audience_id}/contacts",
        payload=payload,
        headers=_resend_headers(lead_id, "audience"),
        accepted_statuses={200, 201, 409},
    )


async def notify_new_lead(
    *,
    lead_id: str,
    email: str,
    source: str | None,
    name: str | None = None,
    company: str | None = None,
    message: str | None = None,
    tier: str | None = None,
    interest: str | None = None,
    locale: str | None = None,
    product_updates_consent: bool = False,
) -> None:
    """Attempt notification and consent-gated follow-up without affecting persistence."""
    tasks: list[asyncio.Task[bool]] = []
    if settings.lead_discord_webhook_url:
        tasks.append(
            asyncio.create_task(
                _notify_discord_lead(
                    settings.lead_discord_webhook_url,
                    email=email,
                    source=source,
                    name=name,
                    company=company,
                    message=message,
                    tier=tier,
                    interest=interest,
                    product_updates_consent=product_updates_consent,
                )
            )
        )
    if settings.resend_api_key:
        tasks.extend(
            (
                asyncio.create_task(
                    _notify_resend_lead(
                        lead_id,
                        email=email,
                        source=source,
                        name=name,
                        company=company,
                        message=message,
                        tier=tier,
                        interest=interest,
                        product_updates_consent=product_updates_consent,
                    )
                ),
                asyncio.create_task(_send_confirmation(lead_id, email, locale)),
            )
        )
        if product_updates_consent is True and settings.resend_audience_id:
            tasks.append(
                asyncio.create_task(
                    _sync_resend_audience(
                        lead_id,
                        email=email,
                        name=name,
                        company=company,
                    )
                )
            )

    if not tasks:
        logger.info("Lead follow-up unavailable for persisted lead %s", lead_id)
        return

    results = await asyncio.gather(*tasks, return_exceptions=True)
    failures = sum(result is not True for result in results)
    if failures:
        logger.warning(
            "Lead follow-up completed with %d failed channel(s) for lead %s",
            failures,
            lead_id,
        )
