import asyncio
from datetime import datetime, timedelta, timezone
import secrets
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from html import escape
from typing import Optional
from urllib.parse import urlencode

import aiohttp
from jose import JWTError, jwt

from src.api.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

PASSWORD_RESET_TOKEN_EXPIRE_HOURS = 1
EMAIL_ACTION_ALGORITHM = "HS256"
EMAIL_ACTION_AUDIENCE = "mutx-auth"
EMAIL_ACTION_ISSUER = "mutx-email-action"


class EmailActionTokenError(ValueError):
    """Raised when a signed email action token is invalid or has expired."""


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


def encode_email_action_token(
    token: str,
    *,
    purpose: str,
    return_path: str,
    expires_in: timedelta,
) -> str:
    """Bind an email token to its sanitized return path and purpose."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": EMAIL_ACTION_ISSUER,
            "aud": EMAIL_ACTION_AUDIENCE,
            "purpose": purpose,
            "token": token,
            "return_path": return_path,
            "iat": now,
            "exp": now + expires_in,
        },
        settings.jwt_secret,
        algorithm=EMAIL_ACTION_ALGORITHM,
    )


def decode_email_action_token(
    action_token: str,
    *,
    purpose: str,
) -> tuple[str, str | None]:
    """Validate an email action envelope, accepting legacy raw tokens."""
    if action_token.count(".") != 2:
        return action_token, None

    try:
        payload = jwt.decode(
            action_token,
            settings.jwt_secret,
            algorithms=[EMAIL_ACTION_ALGORITHM],
            audience=EMAIL_ACTION_AUDIENCE,
            issuer=EMAIL_ACTION_ISSUER,
            options={"require_exp": True},
        )
    except JWTError as exc:
        raise EmailActionTokenError("Invalid or expired email action token") from exc

    token = payload.get("token")
    return_path = payload.get("return_path")
    if (
        payload.get("purpose") != purpose
        or not isinstance(token, str)
        or not token
        or not isinstance(return_path, str)
        or not return_path
    ):
        raise EmailActionTokenError("Invalid email action token")
    return token, return_path


def _send_smtp_email(
    to_email: str, subject: str, html_body: str, text_body: Optional[str] = None
) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        # Attach plain text and HTML versions
        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Connect to SMTP server and send
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

        logger.info("Transactional email accepted by SMTP")
        return True
    except Exception:
        logger.exception("SMTP transactional email failed")
        return False


async def send_email(
    to_email: str, subject: str, html_body: str, text_body: Optional[str] = None
) -> bool:
    """Send transactional auth email through Resend or configured SMTP.

    Delivery is fail-closed: an unconfigured provider returns ``False`` instead
    of pretending a message was sent.
    """
    if settings.resend_api_key:
        from_email = (
            settings.resend_from_email or f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": from_email,
                        "to": [to_email],
                        "subject": subject,
                        "html": html_body,
                        "text": text_body or "",
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if 200 <= response.status < 300:
                        logger.info("Transactional email accepted by Resend")
                        return True
                    logger.warning(
                        "Resend transactional email failed with status %s",
                        response.status,
                    )
        except Exception:
            logger.exception("Resend transactional email failed")

    if settings.smtp_user and settings.smtp_password:
        return await asyncio.to_thread(
            _send_smtp_email,
            to_email,
            subject,
            html_body,
            text_body,
        )

    logger.warning("Transactional email provider is not configured")
    return False


async def send_verification_email(
    to_email: str,
    name: str,
    token: str,
    *,
    frontend_url: str | None = None,
    return_path: str | None = None,
) -> bool:
    """Send email verification email."""
    base_url = (frontend_url or settings.frontend_url).rstrip("/")
    action_token = (
        encode_email_action_token(
            token,
            purpose="verify-email",
            return_path=return_path,
            expires_in=timedelta(hours=settings.email_verification_token_expire_hours),
        )
        if return_path
        else token
    )
    verify_url = f"{base_url}/verify-email?{urlencode({'token': action_token})}"
    safe_name = escape(name)
    safe_verify_url = escape(verify_url, quote=True)

    subject = "Verify your MUTX account"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #1a1a2e;">Welcome to MUTX, {safe_name}!</h1>
        <p style="color: #333; font-size: 16px; line-height: 1.6;">
            Thanks for signing up! Please verify your email address by clicking the button below:
        </p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{safe_verify_url}" style="background-color: #4f46e5; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block;">
                Verify Email
            </a>
        </div>
        <p style="color: #666; font-size: 14px; line-height: 1.6;">
            Or copy and paste this link into your browser:<br>
            <a href="{safe_verify_url}" style="color: #4f46e5;">{safe_verify_url}</a>
        </p>
        <p style="color: #999; font-size: 12px; margin-top: 30px;">
            This link will expire in {settings.email_verification_token_expire_hours} hours.<br>
            If you didn't create an account with MUTX, you can safely ignore this email.
        </p>
    </body>
    </html>
    """
    text_body = f"""
    Welcome to MUTX, {name}!

    Thanks for signing up! Please verify your email address by visiting this link:
    {verify_url}

    This link will expire in {settings.email_verification_token_expire_hours} hours.

    If you didn't create an account with MUTX, you can safely ignore this email.
    """

    return await send_email(to_email, subject, html_body, text_body)


async def send_password_reset_email(
    to_email: str,
    name: str,
    token: str,
    *,
    frontend_url: str | None = None,
    return_path: str | None = None,
) -> bool:
    """Send password reset email."""
    base_url = (frontend_url or settings.frontend_url).rstrip("/")
    action_token = (
        encode_email_action_token(
            token,
            purpose="reset-password",
            return_path=return_path,
            expires_in=timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS),
        )
        if return_path
        else token
    )
    reset_url = f"{base_url}/reset-password?{urlencode({'token': action_token})}"
    safe_name = escape(name)
    safe_reset_url = escape(reset_url, quote=True)

    subject = "Reset your MUTX password"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #1a1a2e;">Reset your password</h1>
        <p style="color: #333; font-size: 16px; line-height: 1.6;">
            Hi {safe_name},<br><br>
            We received a request to reset your password. Click the button below to create a new password:
        </p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{safe_reset_url}" style="background-color: #4f46e5; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block;">
                Reset Password
            </a>
        </div>
        <p style="color: #666; font-size: 14px; line-height: 1.6;">
            Or copy and paste this link into your browser:<br>
            <a href="{safe_reset_url}" style="color: #4f46e5;">{safe_reset_url}</a>
        </p>
        <p style="color: #999; font-size: 12px; margin-top: 30px;">
            This link will expire in {PASSWORD_RESET_TOKEN_EXPIRE_HOURS} hour.<br>
            If you didn't request a password reset, you can safely ignore this email. Your password will remain unchanged.
        </p>
    </body>
    </html>
    """
    text_body = f"""
    Reset your password

    Hi {name},

    We received a request to reset your password. Visit this link to create a new password:
    {reset_url}

    This link will expire in {PASSWORD_RESET_TOKEN_EXPIRE_HOURS} hour.

    If you didn't request a password reset, you can safely ignore this email.
    """

    return await send_email(to_email, subject, html_body, text_body)
