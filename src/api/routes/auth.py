from datetime import datetime, timezone
from ipaddress import ip_address
import logging
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.database import get_db
from src.api.models.models import User
from src.api.services.user_service import UserService
from src.api.services.analytics import log_analytics_event, AnalyticsEventType
from src.api.auth.dependencies import get_current_user, get_current_user_optional
from src.api.auth.jwt import (
    create_access_token as create_dashboard_access_token,
    issue_token_pair,
    revoke_refresh_token,
    refresh_access_token,
)
from src.api.auth.oauth_state import consume_oauth_state, issue_oauth_state
from src.api.auth.password import validate_password_strength
from src.api.services.auth import (
    OAuthIdentityConflictError,
    authenticate_password_user,
    consume_email_verification_token,
    consume_password_reset_token,
    get_auth_user_by_email,
    resolve_external_auth_user,
    resolve_oauth_user,
)
from src.api.services.email.email_service import (
    EmailActionTokenError,
    decode_email_action_token,
    send_verification_email,
    send_password_reset_email,
)
from src.api.services.social_auth import (
    OAuthProvider,
    SocialAuthError,
    build_authorization_url,
    exchange_code_for_user_profile,
    get_provider_client_id,
    get_provider_client_secret,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
logger = logging.getLogger(__name__)
LOCAL_BOOTSTRAP_EMAIL = "local-operator@mutx.local"


def _get_expires_in_seconds(expires_at: datetime) -> int:
    return max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))


class AuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(AuthRequest):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)
    verification_origin: str | None = None
    return_path: str | None = Field(default=None, max_length=1024)


class LoginRequest(AuthRequest):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(AuthRequest):
    refresh_token: str = Field(min_length=32, max_length=4096)


class LogoutRequest(AuthRequest):
    refresh_token: Optional[str] = Field(default=None, min_length=32, max_length=4096)


class LocalBootstrapRequest(AuthRequest):
    name: str = Field(default="Local Operator", min_length=1, max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RegisterResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    verification_email_sent: bool
    requires_email_verification: bool = False
    return_path: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    plan: str
    roles: list[str]
    created_at: datetime
    is_active: bool
    is_email_verified: bool = False

    model_config = ConfigDict(from_attributes=True)


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False

    normalized = host.strip().lower()
    if normalized in {"localhost", "testclient"}:
        return True

    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _assert_local_bootstrap_allowed(request: Request) -> None:
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local bootstrap is disabled in production.",
        )

    forwarded_for = request.headers.get("x-forwarded-for")
    forwarded = request.headers.get("forwarded")
    if forwarded_for or forwarded:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local bootstrap is only available from localhost.",
        )

    client_host = request.client.host if request.client else None
    if not _is_loopback_host(client_host):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local bootstrap is only available from localhost.",
        )


def _origin_from_url(value: str | None) -> str | None:
    if not value:
        return None

    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None

    return f"{parsed.scheme}://{parsed.netloc}"


def _normalize_origin(value: str | None) -> str | None:
    if not value:
        return None

    parsed = urlsplit(value)
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return None
    return _origin_from_url(value)


def _get_allowed_frontend_origins() -> set[str]:
    origins: set[str] = set()
    default_origin = _normalize_origin(settings.frontend_url)
    if default_origin:
        origins.add(default_origin)
    configured = (
        settings.auth_redirect_origins if isinstance(settings.auth_redirect_origins, list) else []
    )
    for origin in configured:
        normalized = _normalize_origin(origin)
        if normalized:
            origins.add(normalized.rstrip("/"))
    return origins


def _is_allowed_frontend_origin(origin: str) -> bool:
    return origin in _get_allowed_frontend_origins()


def _resolve_frontend_origin(requested_origin: str | None) -> str:
    normalized = _normalize_origin(requested_origin)
    if normalized and _is_allowed_frontend_origin(normalized):
        return normalized
    default_origin = _normalize_origin(settings.frontend_url)
    if default_origin is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Frontend URL configuration is invalid.",
        )
    return default_origin


def _default_return_path_for_origin(origin: str) -> str:
    hostname = (urlsplit(origin).hostname or "").casefold()
    pico_hosts = {"pico.mutx.dev", "pico.localhost"}
    return "/" if hostname in pico_hosts else "/dashboard"


def _sanitize_return_path(value: str | None, *, fallback: str = "/dashboard") -> str:
    if not value:
        return fallback

    candidate = value.strip()
    decoded = unquote(candidate)
    if (
        not candidate
        or len(candidate) > 1024
        or not candidate.startswith("/")
        or candidate.startswith("//")
        or not decoded.startswith("/")
        or decoded.startswith("//")
        or "\\" in candidate
        or "\\" in decoded
        or any(ord(character) < 32 for character in candidate)
    ):
        return fallback

    parsed = urlsplit(candidate)
    decoded_parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc or decoded_parsed.scheme or decoded_parsed.netloc:
        return fallback

    path = decoded_parsed.path.casefold()
    blocked_paths = (
        "/login",
        "/register",
        "/forgot-password",
        "/reset-password",
        "/verify-email",
        "/api/auth/",
    )
    if any(path == blocked.rstrip("/") or path.startswith(blocked) for blocked in blocked_paths):
        return fallback
    return candidate


def _validate_oauth_redirect_uri(provider: OAuthProvider, redirect_uri: str) -> str:
    parsed = urlsplit(redirect_uri)
    origin = _origin_from_url(redirect_uri)

    if origin is None or not _is_allowed_frontend_origin(origin) or parsed.query or parsed.fragment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth redirect URI must target an allowed frontend origin.",
        )

    expected_suffix = f"/api/auth/oauth/{provider.value}/callback"
    if parsed.path != expected_suffix:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth redirect URI path is invalid.",
        )

    return f"{origin}{parsed.path}"


def _assert_social_provider_configured(provider: OAuthProvider) -> str:
    client_id = get_provider_client_id(provider)
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{provider.value.title()} OAuth is not configured.",
        )

    if provider == OAuthProvider.APPLE:
        required = (
            settings.apple_team_id,
            settings.apple_key_id,
            settings.apple_private_key,
        )
        has_credentials = all(required)
    else:
        has_credentials = bool(get_provider_client_secret(provider))

    if not has_credentials:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{provider.value.title()} OAuth is not configured.",
        )
    return client_id


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    user_service = UserService(session)
    normalized_email = str(request.email).strip().casefold()
    normalized_name = request.name.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name must not be empty",
        )

    is_valid, error_message = validate_password_strength(request.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    verification_origin = _resolve_frontend_origin(request.verification_origin)
    return_path = _sanitize_return_path(
        request.return_path,
        fallback=_default_return_path_for_origin(verification_origin),
    )

    user: User | None = None
    try:
        user = await user_service.create_user(
            email=normalized_email,
            name=normalized_name,
            password=request.password,
        )
    except IntegrityError as exc:
        await session.rollback()
        existing_user = await get_auth_user_by_email(session, normalized_email)
        if existing_user is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Account registration is temporarily unavailable",
            ) from exc
        if not existing_user.is_email_verified:
            user = existing_user

    if user is not None and not user.is_email_verified:
        token = await user_service.create_email_verification_token(user.id)
        background_tasks.add_task(
            _deliver_auth_email_safely,
            send_verification_email,
            user.email,
            user.name,
            token,
            frontend_url=verification_origin,
            return_path=return_path,
        )

    # Registration is an account-creation request, not a login. Returning the
    # same accepted shape for new and existing addresses avoids enumeration;
    # users authenticate separately when verification policy is disabled.
    return RegisterResponse(
        access_token=None,
        refresh_token=None,
        expires_in=None,
        verification_email_sent=True,
        requires_email_verification=settings.require_email_verification,
        return_path=return_path,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, session: AsyncSession = Depends(get_db)):
    user = await authenticate_password_user(
        session,
        email=str(request.email),
        password=request.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    if settings.require_email_verification and not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification is required before login",
        )

    access_token, access_token_expires_at, refresh_token = await issue_token_pair(session, user.id)

    # Track analytics event
    await log_analytics_event(
        session,
        event_name="User logged in",
        event_type=AnalyticsEventType.USER_LOGIN,
        user_id=user.id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=_get_expires_in_seconds(access_token_expires_at),
    )


@router.post("/local-bootstrap", response_model=TokenResponse)
async def local_bootstrap(
    request: LocalBootstrapRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_db),
):
    _assert_local_bootstrap_allowed(http_request)

    user_service = UserService(session)
    user = await user_service.get_or_create_local_bootstrap_user(
        email=LOCAL_BOOTSTRAP_EMAIL,
        name=request.name,
    )

    access_token, access_token_expires_at, refresh_token = await issue_token_pair(session, user.id)

    await log_analytics_event(
        session,
        event_name="Local operator bootstrapped",
        event_type=AnalyticsEventType.USER_LOGIN,
        user_id=user.id,
        properties={"mode": "local_bootstrap"},
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=_get_expires_in_seconds(access_token_expires_at),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest, session: AsyncSession = Depends(get_db)):
    result = await refresh_access_token(request.refresh_token, session)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    access_token, access_token_expires_at, new_refresh_token = result
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=_get_expires_in_seconds(access_token_expires_at),
    )


@router.post("/logout")
async def logout(
    request: Optional[LogoutRequest] = None,
    session: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    refresh_token = request.refresh_token if request is not None else None

    if not current_user and not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    if refresh_token:
        revoked = await revoke_refresh_token(
            session,
            refresh_token,
            user_id=current_user.id if current_user else None,
        )
        if not revoked:
            if current_user:
                await UserService(session).revoke_all_refresh_tokens(current_user.id)
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token",
                )
    elif current_user:
        await UserService(session).revoke_all_refresh_tokens(current_user.id)

    if current_user:
        await log_analytics_event(
            session,
            event_name="User logged out",
            event_type=AnalyticsEventType.USER_LOGOUT,
            user_id=current_user.id,
        )

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        plan=current_user.plan,
        roles=current_user.roles,
        created_at=current_user.created_at,
        is_active=current_user.is_active,
        is_email_verified=current_user.is_email_verified,
    )


# New request models for password reset and email verification
class ForgotPasswordRequest(AuthRequest):
    email: EmailStr
    email_link_origin: str | None = None
    return_path: str | None = Field(default=None, max_length=1024)


class ResetPasswordRequest(AuthRequest):
    token: str = Field(min_length=32, max_length=4096)
    new_password: str = Field(min_length=8, max_length=1024)


class VerifyEmailRequest(AuthRequest):
    token: str = Field(min_length=32, max_length=4096)


class ResendVerificationRequest(AuthRequest):
    email: EmailStr
    verification_origin: str | None = None
    return_path: str | None = Field(default=None, max_length=1024)


class MessageResponse(BaseModel):
    message: str
    return_path: str | None = None


class OAuthAuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


class OAuthExchangeRequest(AuthRequest):
    code: str = Field(min_length=1, max_length=4096)
    redirect_uri: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=32, max_length=512)


VERIFICATION_EMAIL_RESPONSE_MESSAGE = (
    "If an unverified account exists, the delivery request was processed. "
    "Check the inbox if the configured provider accepted it."
)
PASSWORD_RESET_EMAIL_RESPONSE_MESSAGE = (
    "If an eligible account exists, the reset request was processed. "
    "Check the inbox if the configured provider accepted it."
)


async def _deliver_auth_email_safely(
    delivery: Callable[..., Awaitable[bool]],
    *args: Any,
    **kwargs: Any,
) -> None:
    """Run post-response auth email I/O without changing the public response."""
    try:
        await delivery(*args, **kwargs)
    except Exception:
        logger.exception("Background transactional authentication email failed")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    """Request a password reset email."""
    user_service = UserService(session)
    frontend_origin = _resolve_frontend_origin(request.email_link_origin)
    return_path = _sanitize_return_path(
        request.return_path,
        fallback=_default_return_path_for_origin(frontend_origin),
    )

    user = await get_auth_user_by_email(session, str(request.email))
    if user is not None and user.password_hash is not None:
        token = await user_service.create_password_reset_token(user.id)
        background_tasks.add_task(
            _deliver_auth_email_safely,
            send_password_reset_email,
            user.email,
            user.name,
            token,
            frontend_url=frontend_origin,
            return_path=return_path,
        )

    # Always return success to prevent email enumeration
    return MessageResponse(
        message=PASSWORD_RESET_EMAIL_RESPONSE_MESSAGE,
        return_path=return_path,
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(request: ResetPasswordRequest, session: AsyncSession = Depends(get_db)):
    """Reset password using token."""
    try:
        reset_token, return_path = decode_email_action_token(
            request.token,
            purpose="reset-password",
        )
    except EmailActionTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        ) from exc

    # Validate password strength
    is_valid, error_message = validate_password_strength(request.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    # Reset password
    user = await consume_password_reset_token(
        session,
        token=reset_token,
        new_password=request.new_password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    return MessageResponse(
        message="Password has been reset successfully",
        return_path=_sanitize_return_path(return_path),
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(request: VerifyEmailRequest, session: AsyncSession = Depends(get_db)):
    """Verify email with token."""
    try:
        verification_token, return_path = decode_email_action_token(
            request.token,
            purpose="verify-email",
        )
    except EmailActionTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        ) from exc

    user = await consume_email_verification_token(session, verification_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    return MessageResponse(
        message="Email has been verified successfully",
        return_path=_sanitize_return_path(return_path),
    )


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    request: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    """Resend verification email."""
    user_service = UserService(session)
    verification_origin = _resolve_frontend_origin(request.verification_origin)
    return_path = _sanitize_return_path(
        request.return_path,
        fallback=_default_return_path_for_origin(verification_origin),
    )

    user = await get_auth_user_by_email(session, str(request.email))
    if not user:
        # Don't reveal if email exists
        return MessageResponse(
            message=VERIFICATION_EMAIL_RESPONSE_MESSAGE,
            return_path=return_path,
        )

    if user.is_email_verified:
        return MessageResponse(
            message=VERIFICATION_EMAIL_RESPONSE_MESSAGE,
            return_path=return_path,
        )

    # Create new verification token
    token = await user_service.create_email_verification_token(user.id)
    background_tasks.add_task(
        _deliver_auth_email_safely,
        send_verification_email,
        user.email,
        user.name,
        token,
        frontend_url=verification_origin,
        return_path=return_path,
    )

    return MessageResponse(
        message=VERIFICATION_EMAIL_RESPONSE_MESSAGE,
        return_path=return_path,
    )


@router.get("/oauth/{provider}/authorize", response_model=OAuthAuthorizeResponse)
async def authorize_oauth(
    provider: OAuthProvider,
    redirect_uri: str,
    state: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    validated_redirect_uri = _validate_oauth_redirect_uri(provider, redirect_uri)
    client_id = _assert_social_provider_configured(provider)
    bound_state = await issue_oauth_state(
        session,
        flow="oauth",
        provider=provider.value,
        redirect_uri=validated_redirect_uri,
        ttl_seconds=settings.oauth_state_ttl_seconds,
    )

    return OAuthAuthorizeResponse(
        authorization_url=build_authorization_url(
            provider,
            client_id=client_id,
            redirect_uri=validated_redirect_uri,
            state=bound_state,
        ),
        state=bound_state,
    )


@router.post("/oauth/{provider}/exchange", response_model=TokenResponse)
async def exchange_oauth_code(
    provider: OAuthProvider,
    request: OAuthExchangeRequest,
    session: AsyncSession = Depends(get_db),
):
    validated_redirect_uri = _validate_oauth_redirect_uri(provider, request.redirect_uri)
    _assert_social_provider_configured(provider)
    state_is_valid = await consume_oauth_state(
        session,
        state=request.state,
        flow="oauth",
        provider=provider.value,
        redirect_uri=validated_redirect_uri,
    )
    if not state_is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state.",
        )

    try:
        profile = await exchange_code_for_user_profile(
            provider,
            code=request.code,
            redirect_uri=validated_redirect_uri,
        )
    except SocialAuthError as exc:
        upstream_status = (
            status.HTTP_502_BAD_GATEWAY
            if exc.status_code == 429 or exc.status_code >= 500
            else status.HTTP_400_BAD_REQUEST
        )
        detail = (
            "OAuth provider is temporarily unavailable."
            if upstream_status == status.HTTP_502_BAD_GATEWAY
            else "OAuth authorization code was rejected."
        )
        raise HTTPException(status_code=upstream_status, detail=detail) from exc

    if profile.provider != provider:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OAuth provider returned an inconsistent identity.",
        )
    if not profile.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OAuth account email must be verified.",
        )
    try:
        user = await resolve_oauth_user(session, profile)
    except OAuthIdentityConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="OAuth account cannot be linked automatically.",
        ) from exc
    except ValueError as exc:
        logger.warning("OAuth provider returned an unusable identity: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OAuth provider returned an incomplete identity.",
        ) from exc
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token, access_token_expires_at, refresh_token = await issue_token_pair(session, user.id)

    await log_analytics_event(
        session,
        event_name="User logged in",
        event_type=AnalyticsEventType.USER_LOGIN,
        user_id=user.id,
        properties={"provider": provider.value},
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=_get_expires_in_seconds(access_token_expires_at),
    )


# SSO OAuth Routes


class SSOCallbackResponse(BaseModel):
    """Response model for SSO callback."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400


class SSOUserInfo(BaseModel):
    """SSO user information from token."""

    sub: str
    email: str
    roles: list[str]
    exp: datetime

    model_config = ConfigDict(from_attributes=True)


def _get_public_api_origin() -> str:
    public_api_url = getattr(settings, "public_api_url", None)
    origin = _normalize_origin(public_api_url)
    if origin is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Public API URL is not configured for SSO.",
        )
    return origin


def _get_sso_client_credentials(provider: str) -> tuple[str, str]:
    client_id = getattr(settings, f"{provider.lower()}_client_id", None)
    client_secret = getattr(settings, f"{provider.lower()}_client_secret", None)
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{provider.title()} SSO is not configured.",
        )
    return client_id, client_secret


def _build_sso_authorization_url(
    provider: str,
    client_id: str,
    redirect_uri: str,
    state: str,
) -> tuple[str, str]:
    """
    Build the SSO provider authorization URL.

    Returns tuple of (authorization_url, state)
    """
    from src.api.services.auth import SSOProvider

    # Provider-specific authorization endpoints
    auth_urls = {
        SSOProvider.OKTA.value: "{domain}/oauth2/v1/authorize",
        SSOProvider.AUTH0.value: "{domain}/authorize",
        SSOProvider.KEYCLOAK.value: "{domain}/realms/{realm}/protocol/openid-connect/auth",
        SSOProvider.GOOGLE.value: "https://accounts.google.com/o/oauth2/v2/auth",
    }

    # Build scopes per provider
    scopes = {
        SSOProvider.OKTA.value: "openid email profile groups",
        SSOProvider.AUTH0.value: "openid email profile",
        SSOProvider.KEYCLOAK.value: "openid email profile roles",
        SSOProvider.GOOGLE.value: "openid email profile",
    }

    provider_lower = provider.lower()

    if provider_lower not in auth_urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported SSO provider: {provider}",
        )

    # Get domain config
    domain_attr = f"{provider_lower}_domain"
    domain = getattr(settings, domain_attr, None)
    realm = (
        getattr(settings, f"{provider_lower}_realm", None) if provider_lower == "keycloak" else None
    )

    if provider_lower != SSOProvider.GOOGLE.value and _normalize_origin(domain) is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{provider.title()} SSO domain is not configured.",
        )
    if provider_lower == SSOProvider.KEYCLOAK.value and not realm:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Keycloak SSO realm is not configured.",
        )

    auth_url_template = auth_urls[provider_lower]
    scope = scopes[provider_lower]

    if provider_lower == SSOProvider.KEYCLOAK.value:
        auth_url = auth_url_template.format(domain=domain, realm=realm)
    elif provider_lower == SSOProvider.GOOGLE.value:
        auth_url = auth_url_template
    else:
        auth_url = auth_url_template.format(domain=domain)

    # Build authorization URL with query parameters
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }

    if provider_lower == SSOProvider.GOOGLE.value:
        params["redirect_uri"] = redirect_uri
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    auth_url = f"{auth_url}?{urlencode(params)}"

    return auth_url, state


async def _exchange_code_for_token(
    provider: str,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> dict:
    """
    Exchange authorization code for access token.

    Returns the token response from the SSO provider.
    """
    import httpx
    from src.api.services.auth import SSOProvider

    # Provider token endpoints
    token_urls = {
        SSOProvider.OKTA.value: "{domain}/oauth2/v1/token",
        SSOProvider.AUTH0.value: "{domain}/oauth/token",
        SSOProvider.KEYCLOAK.value: "{domain}/realms/{realm}/protocol/openid-connect/token",
        SSOProvider.GOOGLE.value: "https://oauth2.googleapis.com/token",
    }

    provider_lower = provider.lower()
    domain_attr = f"{provider_lower}_domain"
    domain = getattr(settings, domain_attr, None)
    realm = (
        getattr(settings, f"{provider_lower}_realm", None) if provider_lower == "keycloak" else None
    )

    if provider_lower != SSOProvider.GOOGLE.value and _normalize_origin(domain) is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{provider.title()} SSO domain is not configured.",
        )
    if provider_lower == SSOProvider.KEYCLOAK.value and not realm:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Keycloak SSO realm is not configured.",
        )

    token_url_template = token_urls[provider_lower]
    if provider_lower == SSOProvider.KEYCLOAK.value:
        token_url = token_url_template.format(domain=domain, realm=realm)
    elif provider_lower == SSOProvider.GOOGLE.value:
        token_url = token_url_template
    else:
        token_url = token_url_template.format(domain=domain)

    # Build token request
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }

    data["client_secret"] = client_secret

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SSO provider is temporarily unavailable.",
        ) from exc

    if response.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SSO provider is temporarily unavailable.",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO authorization code was rejected.",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SSO provider returned an invalid response.",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SSO provider returned an invalid response.",
        )
    return payload


@router.get("/sso/{provider}", tags=["auth"])
async def sso_redirect(
    provider: str,
    session: AsyncSession = Depends(get_db),
):
    """
    Initiate SSO authentication by redirecting to the provider's authorization endpoint.

    Returns a redirect to the SSO provider's authorization URL with appropriate
    client_id, redirect_uri, scope, and state parameters.
    """
    # Validate provider
    from src.api.services.auth import SSOProvider

    try:
        SSOProvider(provider.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported SSO provider: {provider}",
        )

    client_id, _ = _get_sso_client_credentials(provider)

    redirect_uri = f"{_get_public_api_origin()}/v1/auth/sso/{provider.lower()}/callback"

    state = await issue_oauth_state(
        session,
        flow="sso",
        provider=provider.lower(),
        redirect_uri=redirect_uri,
        ttl_seconds=settings.oauth_state_ttl_seconds,
    )

    # Build authorization URL
    auth_url, _ = _build_sso_authorization_url(
        provider=provider,
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
    )

    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/sso/{provider}/callback", response_model=SSOCallbackResponse, tags=["auth"])
async def sso_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    """
    Handle SSO callback from the identity provider.

    Exchanges the authorization code for an access token from the SSO provider,
    verifies the token, and issues a MUTX JWT access token.
    """
    from src.api.services.auth import SSOProvider, verify_oauth_token

    # Validate provider
    try:
        sso_provider = SSOProvider(provider.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported SSO provider: {provider}",
        )

    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO callback is missing required parameters.",
        )

    client_id, client_secret = _get_sso_client_credentials(provider)
    redirect_uri = f"{_get_public_api_origin()}/v1/auth/sso/{provider.lower()}/callback"
    state_is_valid = await consume_oauth_state(
        session,
        state=state,
        flow="sso",
        provider=provider.lower(),
        redirect_uri=redirect_uri,
    )
    if not state_is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired SSO state.",
        )

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO provider rejected authorization.",
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO callback is missing required parameters.",
        )

    try:
        # Exchange code for token with SSO provider
        token_response = await _exchange_code_for_token(
            provider=provider,
            code=code,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
        )

        # Prefer the OIDC ID token for local signature/issuer/audience validation.
        # When a provider omits it, the access token may be opaque or scoped to a
        # resource server, so allow the verifier to resolve identity via userinfo.
        access_token = token_response.get("access_token")
        id_token = token_response.get("id_token")
        verification_token = id_token or access_token
        if not verification_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No identity token returned from SSO provider",
            )

        # Verify the OAuth token and extract user info
        token_payload = await verify_oauth_token(
            token=verification_token,
            provider=sso_provider,
            domain=(
                getattr(settings, f"{provider.lower()}_domain", None)
                or ("https://accounts.google.com" if sso_provider.value == "google" else None)
            ),
            client_id=client_id,
            allow_userinfo_fallback=id_token is None,
        )
        if not token_payload.sub or not token_payload.email or not token_payload.email_verified:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="SSO identity is incomplete.",
            )
        user = await resolve_external_auth_user(
            session,
            provider=sso_provider.value,
            provider_user_id=token_payload.sub,
            email=token_payload.email,
            email_verified=token_payload.email_verified,
            display_name=token_payload.email.split("@", 1)[0],
            profile={"source": "sso"},
        )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        # SSO uses the same UUID-backed token as dashboard login. Persisted
        # database roles, not provider claims, are authoritative at request time.
        mutx_access_token, access_token_expires_at = create_dashboard_access_token(user.id)

        return SSOCallbackResponse(
            access_token=mutx_access_token,
            token_type="bearer",
            expires_in=_get_expires_in_seconds(access_token_expires_at),
        )

    except OAuthIdentityConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SSO account cannot be linked automatically.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected SSO callback failure", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SSO authentication failed.",
        ) from exc
