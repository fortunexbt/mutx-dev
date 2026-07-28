"""Adversarial coverage for the public authentication contract."""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
import uuid

from fastapi import BackgroundTasks
from httpx import AsyncClient
from pydantic import ValidationError
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from src.api.auth.jwt import issue_token_pair
from src.api.auth.password import hash_password
from src.api.config import Settings
from src.api.models.models import (
    ExternalAuthIdentity,
    OAuthAuthorizationState,
    RefreshTokenSession,
    User,
)
from src.api.routes import auth as auth_routes
from src.api.services.email.email_service import encode_email_action_token
from src.api.services.social_auth import (
    OAuthProvider,
    OAuthUserProfile,
    SocialAuthError,
)
from src.api.services.user_service import UserService


GOOGLE_CALLBACK = "https://app.mutx.dev/api/auth/oauth/google/callback"
GITHUB_CALLBACK = "https://app.mutx.dev/api/auth/oauth/github/callback"


@pytest.fixture(autouse=True)
def configured_oauth_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep OAuth security tests hermetic instead of reading developer credentials."""
    monkeypatch.setattr(auth_routes.settings, "google_client_id", "google-client-id")
    monkeypatch.setattr(auth_routes.settings, "google_client_secret", "google-client-secret")
    monkeypatch.setattr(auth_routes.settings, "github_client_id", "github-client-id")
    monkeypatch.setattr(auth_routes.settings, "github_client_secret", "github-client-secret")


async def _authorize(client: AsyncClient, provider: str, redirect_uri: str) -> str:
    response = await client.get(
        f"/v1/auth/oauth/{provider}/authorize",
        params={"redirect_uri": redirect_uri},
    )
    assert response.status_code == 200
    return response.json()["state"]


def _profile(
    *,
    provider: OAuthProvider = OAuthProvider.GOOGLE,
    provider_user_id: str = "provider-user-1",
    email: str = "oauth-security@example.com",
    verified: bool = True,
) -> OAuthUserProfile:
    return OAuthUserProfile(
        provider=provider,
        provider_user_id=provider_user_id,
        email=email,
        email_verified=verified,
        display_name="OAuth Security",
        username="oauth-security",
        avatar_url=None,
        profile={"sub": provider_user_id},
    )


@pytest.mark.asyncio
async def test_oauth_state_is_single_use_and_revokes_replay(
    client_no_auth: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_exchange(*_args, **_kwargs) -> OAuthUserProfile:
        nonlocal calls
        calls += 1
        return _profile()

    monkeypatch.setattr(auth_routes, "exchange_code_for_user_profile", fake_exchange)
    state = await _authorize(client_no_auth, "google", GOOGLE_CALLBACK)
    payload = {"code": "provider-code", "redirect_uri": GOOGLE_CALLBACK, "state": state}

    first = await client_no_auth.post("/v1/auth/oauth/google/exchange", json=payload)
    replay = await client_no_auth.post("/v1/auth/oauth/google/exchange", json=payload)

    assert first.status_code == 200
    assert replay.status_code == 400
    assert replay.json()["detail"] == "Invalid or expired OAuth state."
    assert calls == 1


@pytest.mark.asyncio
async def test_oauth_state_rejects_wrong_expired_and_provider_mismatched_values(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
) -> None:
    wrong = await client_no_auth.post(
        "/v1/auth/oauth/google/exchange",
        json={
            "code": "provider-code",
            "redirect_uri": GOOGLE_CALLBACK,
            "state": "x" * 43,
        },
    )
    assert wrong.status_code == 400

    google_state = await _authorize(client_no_auth, "google", GOOGLE_CALLBACK)
    mismatch = await client_no_auth.post(
        "/v1/auth/oauth/github/exchange",
        json={
            "code": "provider-code",
            "redirect_uri": GITHUB_CALLBACK,
            "state": google_state,
        },
    )
    assert mismatch.status_code == 400

    expired_state = await _authorize(client_no_auth, "google", GOOGLE_CALLBACK)
    await db_session.execute(
        update(OAuthAuthorizationState)
        .where(OAuthAuthorizationState.consumed_at.is_(None))
        .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    expired = await client_no_auth.post(
        "/v1/auth/oauth/google/exchange",
        json={
            "code": "provider-code",
            "redirect_uri": GOOGLE_CALLBACK,
            "state": expired_state,
        },
    )
    assert expired.status_code == 400


@pytest.mark.asyncio
async def test_oauth_redirect_allowlist_is_exact(client_no_auth: AsyncClient) -> None:
    for redirect_uri in (
        "https://evil.example/api/auth/oauth/google/callback",
        "https://tenant.mutx.dev/api/auth/oauth/google/callback",
        f"{GOOGLE_CALLBACK}?next=https://evil.example",
        "https://app.mutx.dev/api/auth/oauth/github/callback",
    ):
        response = await client_no_auth.get(
            "/v1/auth/oauth/google/authorize",
            params={"redirect_uri": redirect_uri},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_oauth_fails_closed_when_client_secret_is_missing(
    client_no_auth: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_routes.settings, "google_client_id", "google-client")
    monkeypatch.setattr(auth_routes.settings, "google_client_secret", None)

    response = await client_no_auth.get(
        "/v1/auth/oauth/google/authorize",
        params={"redirect_uri": GOOGLE_CALLBACK},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Google OAuth is not configured."


@pytest.mark.asyncio
async def test_oauth_callback_rejects_provider_confusion_and_maps_upstream_5xx(
    client_no_auth: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _authorize(client_no_auth, "google", GOOGLE_CALLBACK)

    async def mismatched_profile(*_args, **_kwargs) -> OAuthUserProfile:
        return _profile(provider=OAuthProvider.GITHUB)

    monkeypatch.setattr(auth_routes, "exchange_code_for_user_profile", mismatched_profile)
    mismatch = await client_no_auth.post(
        "/v1/auth/oauth/google/exchange",
        json={"code": "provider-code", "redirect_uri": GOOGLE_CALLBACK, "state": state},
    )
    assert mismatch.status_code == 502

    state = await _authorize(client_no_auth, "google", GOOGLE_CALLBACK)

    async def unavailable(*_args, **_kwargs) -> OAuthUserProfile:
        raise SocialAuthError("provider detail must not leak", status_code=503)

    monkeypatch.setattr(auth_routes, "exchange_code_for_user_profile", unavailable)
    failure = await client_no_auth.post(
        "/v1/auth/oauth/google/exchange",
        json={"code": "provider-code", "redirect_uri": GOOGLE_CALLBACK, "state": state},
    )
    assert failure.status_code == 502
    assert failure.json()["detail"] == "OAuth provider is temporarily unavailable."


@pytest.mark.asyncio
async def test_oauth_subject_mapping_is_stable_when_provider_email_changes(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profiles = iter(
        [
            _profile(email="first@example.com"),
            _profile(email="changed@example.com"),
        ]
    )

    async def fake_exchange(*_args, **_kwargs) -> OAuthUserProfile:
        return next(profiles)

    monkeypatch.setattr(auth_routes, "exchange_code_for_user_profile", fake_exchange)
    for _ in range(2):
        state = await _authorize(client_no_auth, "google", GOOGLE_CALLBACK)
        response = await client_no_auth.post(
            "/v1/auth/oauth/google/exchange",
            json={"code": "provider-code", "redirect_uri": GOOGLE_CALLBACK, "state": state},
        )
        assert response.status_code == 200

    users = (await db_session.execute(select(User))).scalars().all()
    identities = (await db_session.execute(select(ExternalAuthIdentity))).scalars().all()
    assert len(users) == 1
    assert users[0].email == "changed@example.com"
    assert users[0].password_hash is None
    assert len(identities) == 1
    assert identities[0].provider_email == "changed@example.com"


@pytest.mark.asyncio
async def test_provider_email_conflict_never_reassigns_owner_or_enables_password_recovery(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profiles = iter(
        [
            _profile(provider_user_id="provider-email-conflict", email="provider-old@example.com"),
            _profile(provider_user_id="provider-email-conflict", email="owned@example.com"),
        ]
    )

    async def fake_exchange(*_args, **_kwargs) -> OAuthUserProfile:
        return next(profiles)

    monkeypatch.setattr(auth_routes, "exchange_code_for_user_profile", fake_exchange)
    first_state = await _authorize(client_no_auth, "google", GOOGLE_CALLBACK)
    first_login = await client_no_auth.post(
        "/v1/auth/oauth/google/exchange",
        json={"code": "provider-code", "redirect_uri": GOOGLE_CALLBACK, "state": first_state},
    )
    assert first_login.status_code == 200

    provider_identity = (
        await db_session.execute(
            select(ExternalAuthIdentity).where(
                ExternalAuthIdentity.provider_user_id == "provider-email-conflict"
            )
        )
    ).scalar_one()
    provider_user = await db_session.get(User, provider_identity.user_id)
    assert provider_user is not None
    email_owner = User(
        id=uuid.uuid4(),
        email="owned@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Existing Owner",
        is_active=True,
        is_email_verified=True,
    )
    db_session.add(email_owner)
    await db_session.commit()

    second_state = await _authorize(client_no_auth, "google", GOOGLE_CALLBACK)
    second_login = await client_no_auth.post(
        "/v1/auth/oauth/google/exchange",
        json={"code": "provider-code", "redirect_uri": GOOGLE_CALLBACK, "state": second_state},
    )
    assert second_login.status_code == 200

    await db_session.refresh(provider_user)
    await db_session.refresh(provider_identity)
    await db_session.refresh(email_owner)
    assert provider_user.email == "provider-old@example.com"
    assert provider_user.password_hash is None
    assert provider_identity.provider_email == "owned@example.com"
    assert email_owner.email == "owned@example.com"

    deliveries: list[str] = []

    async def capture_delivery(to_email: str, *_args, **_kwargs) -> bool:
        deliveries.append(to_email)
        return True

    monkeypatch.setattr(auth_routes, "send_password_reset_email", capture_delivery)
    stale_recovery = await client_no_auth.post(
        "/v1/auth/forgot-password",
        json={"email": "provider-old@example.com"},
    )
    missing_recovery = await client_no_auth.post(
        "/v1/auth/forgot-password",
        json={"email": "missing-provider@example.com"},
    )
    assert stale_recovery.status_code == missing_recovery.status_code == 200
    assert stale_recovery.json() == missing_recovery.json()
    assert deliveries == []

    raw_token = await UserService(db_session).create_password_reset_token(provider_user.id)
    action_token = encode_email_action_token(
        raw_token,
        purpose="reset-password",
        return_path="/dashboard",
        expires_in=timedelta(hours=1),
    )
    reset = await client_no_auth.post(
        "/v1/auth/reset-password",
        json={"token": action_token, "new_password": "TakeoverPassword123!"},
    )
    assert reset.status_code == 400
    await db_session.refresh(provider_user)
    assert provider_user.password_hash is None


@pytest.mark.asyncio
async def test_sso_callback_ignores_host_and_forwarded_headers(
    client_no_auth: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_routes.settings, "public_api_url", "https://api.mutx.dev")
    monkeypatch.setattr(auth_routes.settings, "okta_domain", "https://id.example.com")
    monkeypatch.setattr(auth_routes.settings, "okta_client_id", "mutx-client")
    monkeypatch.setattr(auth_routes.settings, "okta_client_secret", "client-secret")

    response = await client_no_auth.get(
        "/v1/auth/sso/okta",
        headers={
            "X-Forwarded-Host": "evil.example",
            "X-Forwarded-Proto": "http",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    provider_query = parse_qs(urlsplit(response.headers["location"]).query)
    assert provider_query["redirect_uri"] == ["https://api.mutx.dev/v1/auth/sso/okta/callback"]


@pytest.mark.asyncio
async def test_sso_fails_closed_without_public_url_or_client_secret(
    client_no_auth: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_routes.settings, "public_api_url", None)
    monkeypatch.setattr(auth_routes.settings, "okta_domain", "https://id.example.com")
    monkeypatch.setattr(auth_routes.settings, "okta_client_id", "mutx-client")
    monkeypatch.setattr(auth_routes.settings, "okta_client_secret", None)

    missing_secret = await client_no_auth.get("/v1/auth/sso/okta", follow_redirects=False)
    assert missing_secret.status_code == 500

    monkeypatch.setattr(auth_routes.settings, "okta_client_secret", "client-secret")
    missing_url = await client_no_auth.get("/v1/auth/sso/okta", follow_redirects=False)
    assert missing_url.status_code == 500


@pytest.mark.asyncio
async def test_sso_state_is_single_use_and_persists_provider_subject(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.api.services import auth as auth_service

    monkeypatch.setattr(auth_routes.settings, "public_api_url", "https://api.mutx.dev")
    monkeypatch.setattr(auth_routes.settings, "okta_domain", "https://id.example.com")
    monkeypatch.setattr(auth_routes.settings, "okta_client_id", "mutx-client")
    monkeypatch.setattr(auth_routes.settings, "okta_client_secret", "client-secret")

    start = await client_no_auth.get("/v1/auth/sso/okta", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]

    async def fake_exchange(**_kwargs):
        return {"id_token": "signed-id-token", "access_token": "opaque-token"}

    async def fake_verify(**_kwargs):
        return auth_service.TokenPayload(
            sub="subject-123",
            email="sso@example.com",
            email_verified=True,
            roles=["VIEWER"],
            exp=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    monkeypatch.setattr(auth_routes, "_exchange_code_for_token", fake_exchange)
    monkeypatch.setattr(auth_service, "verify_oauth_token", fake_verify)

    callback_params = {"code": "provider-code", "state": state}
    success = await client_no_auth.get(
        "/v1/auth/sso/okta/callback",
        params=callback_params,
    )
    replay = await client_no_auth.get(
        "/v1/auth/sso/okta/callback",
        params=callback_params,
    )

    assert success.status_code == 200
    assert replay.status_code == 400

    identity_result = await db_session.execute(
        select(ExternalAuthIdentity).where(
            ExternalAuthIdentity.provider == "okta",
            ExternalAuthIdentity.provider_user_id == "subject-123",
        )
    )
    identity = identity_result.scalar_one()
    user = await db_session.get(User, identity.user_id)
    assert user is not None
    assert user.roles == ["VIEWER"]

    me = await client_no_auth.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {success.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["id"] == str(user.id)


def test_auth_configuration_rejects_malformed_urls_and_partial_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_names = (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "DISCORD_CLIENT_ID",
        "DISCORD_CLIENT_SECRET",
        "APPLE_CLIENT_ID",
        "APPLE_TEAM_ID",
        "APPLE_KEY_ID",
        "APPLE_PRIVATE_KEY",
        "OKTA_DOMAIN",
        "OKTA_CLIENT_ID",
        "OKTA_CLIENT_SECRET",
        "AUTH0_DOMAIN",
        "AUTH0_CLIENT_ID",
        "AUTH0_CLIENT_SECRET",
        "KEYCLOAK_DOMAIN",
        "KEYCLOAK_REALM",
        "KEYCLOAK_CLIENT_ID",
        "KEYCLOAK_CLIENT_SECRET",
        "PUBLIC_API_URL",
    )
    for name in provider_names:
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("PUBLIC_API_URL", "https://user@api.mutx.dev/callback")
    with pytest.raises(ValidationError, match="Auth origins"):
        Settings(_env_file=None)

    monkeypatch.delenv("PUBLIC_API_URL")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-only")
    with pytest.raises(ValidationError, match="Google OAuth configuration is incomplete"):
        Settings(_env_file=None)


@pytest.mark.asyncio
async def test_password_contract_rejects_bcrypt_truncation_boundary(
    client_no_auth: AsyncClient,
) -> None:
    too_long = "Aa1!" + ("x" * 69)
    response = await client_no_auth.post(
        "/v1/auth/register",
        json={
            "email": "long-password@example.com",
            "name": "Long Password",
            "password": too_long,
        },
    )

    assert len(too_long.encode("utf-8")) > 72
    assert response.status_code == 400
    assert "72 bytes" in response.json()["detail"]


@pytest.mark.asyncio
async def test_verification_tokens_are_one_time_and_expiry_safe(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="verify-once@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Verify Once",
        is_active=True,
        is_email_verified=False,
    )
    db_session.add(user)
    await db_session.commit()
    service = UserService(db_session)

    token = await service.create_email_verification_token(user.id)
    success = await client_no_auth.post("/v1/auth/verify-email", json={"token": token})
    replay = await client_no_auth.post("/v1/auth/verify-email", json={"token": token})
    assert success.status_code == 200
    assert replay.status_code == 400

    user.is_email_verified = False
    user.email_verified_at = None
    await db_session.commit()
    expired_token = await service.create_email_verification_token(user.id)
    user.email_verification_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    expired = await client_no_auth.post(
        "/v1/auth/verify-email",
        json={"token": expired_token},
    )
    assert expired.status_code == 400


@pytest.mark.asyncio
async def test_signed_email_action_preserves_trusted_return_path_and_rejects_tampering(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="signed-return@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Signed Return",
        is_active=True,
        is_email_verified=False,
    )
    db_session.add(user)
    await db_session.commit()
    raw_token = await UserService(db_session).create_email_verification_token(user.id)
    action_token = encode_email_action_token(
        raw_token,
        purpose="verify-email",
        return_path="/dashboard/agents?view=active",
        expires_in=timedelta(hours=1),
    )
    header, payload, signature = action_token.split(".")
    payload_index = len(payload) // 2
    replacement = "a" if payload[payload_index] != "a" else "b"
    tampered_payload = f"{payload[:payload_index]}{replacement}{payload[payload_index + 1 :]}"
    tampered = ".".join((header, tampered_payload, signature))

    rejected = await client_no_auth.post(
        "/v1/auth/verify-email",
        json={"token": tampered},
    )
    success = await client_no_auth.post(
        "/v1/auth/verify-email",
        json={"token": action_token},
    )

    assert rejected.status_code == 400
    assert success.status_code == 200
    assert success.json()["return_path"] == "/dashboard/agents?view=active"


@pytest.mark.asyncio
async def test_password_email_flows_sanitize_and_carry_same_product_return_paths(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, str | None]] = []

    async def capture_delivery(*_args, **kwargs) -> bool:
        captured.append((kwargs["frontend_url"], kwargs["return_path"]))
        return True

    monkeypatch.setattr(auth_routes, "send_verification_email", capture_delivery)
    monkeypatch.setattr(auth_routes, "send_password_reset_email", capture_delivery)

    register = await client_no_auth.post(
        "/v1/auth/register",
        json={
            "email": "return-register@example.com",
            "name": "Return Register",
            "password": "StrongPassword123!",
            "verification_origin": "https://pico.mutx.dev",
            "return_path": "/onboarding?step=runtime",
        },
    )
    resend = await client_no_auth.post(
        "/v1/auth/resend-verification",
        json={
            "email": "return-register@example.com",
            "verification_origin": "https://pico.mutx.dev",
            "return_path": "https://evil.example/steal",
        },
    )
    forgot = await client_no_auth.post(
        "/v1/auth/forgot-password",
        json={
            "email": "return-register@example.com",
            "email_link_origin": "https://app.mutx.dev",
            "return_path": "/dashboard/security?tab=sessions",
        },
    )

    assert (register.status_code, resend.status_code, forgot.status_code) == (201, 200, 200)
    assert register.json()["return_path"] == "/onboarding?step=runtime"
    assert resend.json()["return_path"] == "/"
    assert forgot.json()["return_path"] == "/dashboard/security?tab=sessions"
    assert captured == [
        ("https://pico.mutx.dev", "/onboarding?step=runtime"),
        ("https://pico.mutx.dev", "/"),
        ("https://app.mutx.dev", "/dashboard/security?tab=sessions"),
    ]


@pytest.mark.asyncio
async def test_reset_tokens_are_one_time_expiry_safe_and_revoke_sessions(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="reset-once@example.com",
        password_hash=hash_password("OldPassword123!"),
        name="Reset Once",
        is_active=True,
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    _, _, refresh_token = await issue_token_pair(db_session, user.id)
    await db_session.commit()
    service = UserService(db_session)

    raw_token = await service.create_password_reset_token(user.id)
    token = encode_email_action_token(
        raw_token,
        purpose="reset-password",
        return_path="/dashboard/security?tab=sessions",
        expires_in=timedelta(hours=1),
    )
    success = await client_no_auth.post(
        "/v1/auth/reset-password",
        json={"token": token, "new_password": "NewPassword123!"},
    )
    replay = await client_no_auth.post(
        "/v1/auth/reset-password",
        json={"token": token, "new_password": "AnotherPassword123!"},
    )
    revoked_refresh = await client_no_auth.post(
        "/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert success.status_code == 200
    assert success.json()["return_path"] == "/dashboard/security?tab=sessions"
    assert replay.status_code == 400
    assert revoked_refresh.status_code == 401

    expired_token = await service.create_password_reset_token(user.id)
    user.password_reset_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    expired = await client_no_auth.post(
        "/v1/auth/reset-password",
        json={"token": expired_token, "new_password": "AnotherPassword123!"},
    )
    assert expired.status_code == 400


@pytest.mark.asyncio
async def test_recovery_responses_do_not_disclose_account_existence(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="recovery-present@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Recovery",
        is_active=True,
        is_email_verified=False,
    )
    db_session.add(user)
    await db_session.commit()

    async def failed_delivery(*_args, **_kwargs) -> bool:
        raise RuntimeError("simulated provider failure")

    monkeypatch.setattr(auth_routes, "send_password_reset_email", failed_delivery)
    monkeypatch.setattr(auth_routes, "send_verification_email", failed_delivery)

    existing_reset = await client_no_auth.post(
        "/v1/auth/forgot-password", json={"email": user.email}
    )
    missing_reset = await client_no_auth.post(
        "/v1/auth/forgot-password", json={"email": "recovery-missing@example.com"}
    )
    existing_verify = await client_no_auth.post(
        "/v1/auth/resend-verification", json={"email": user.email}
    )
    missing_verify = await client_no_auth.post(
        "/v1/auth/resend-verification", json={"email": "recovery-missing@example.com"}
    )

    assert existing_reset.status_code == missing_reset.status_code == 200
    assert existing_reset.json() == missing_reset.json()
    assert existing_verify.status_code == missing_verify.status_code == 200
    assert existing_verify.json() == missing_verify.json()
    assert "provider accepted" in existing_reset.json()["message"]
    assert "provider accepted" in existing_verify.json()["message"]
    assert "has been sent" not in existing_reset.json()["message"]
    assert "has been sent" not in existing_verify.json()["message"]


@pytest.mark.asyncio
async def test_registration_and_recovery_queue_email_without_awaiting_provider_io(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def must_not_run_in_route(*_args, **_kwargs) -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(auth_routes, "send_verification_email", must_not_run_in_route)
    monkeypatch.setattr(auth_routes, "send_password_reset_email", must_not_run_in_route)

    registration_tasks = BackgroundTasks()
    registration = await auth_routes.register(
        auth_routes.RegisterRequest(
            email="queued-registration@example.com",
            name="Queued Registration",
            password="StrongPassword123!",
        ),
        registration_tasks,
        db_session,
    )
    recovery_tasks = BackgroundTasks()
    recovery = await auth_routes.forgot_password(
        auth_routes.ForgotPasswordRequest(email="queued-registration@example.com"),
        recovery_tasks,
        db_session,
    )

    assert registration.verification_email_sent is True
    assert recovery.message == auth_routes.PASSWORD_RESET_EMAIL_RESPONSE_MESSAGE
    assert len(registration_tasks.tasks) == 1
    assert len(recovery_tasks.tasks) == 1
    assert calls == 0


@pytest.mark.asyncio
async def test_refresh_rotation_reuses_one_successor_for_delayed_overlap_then_revokes_replay(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.api.auth import jwt as auth_jwt
    from src.api.database import get_db

    clock = [datetime.now(timezone.utc)]
    monkeypatch.setattr(auth_jwt, "_utc_now", lambda: clock[0])
    monkeypatch.setattr(auth_jwt.settings, "refresh_token_rotation_grace_seconds", 10)
    user = User(
        id=uuid.uuid4(),
        email="rotate@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Rotate",
        is_active=True,
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    user_id = user.id
    login = await client_no_auth.post(
        "/v1/auth/login",
        json={"email": user.email, "password": "StrongPassword123!"},
    )
    original = login.json()["refresh_token"]
    rotated = await client_no_auth.post("/v1/auth/refresh", json={"refresh_token": original})
    replacement = rotated.json()["refresh_token"]

    default_db_override = client_no_auth.app.dependency_overrides[get_db]
    fresh_session_factory = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def refresh_from_another_worker(token: str):
        async with fresh_session_factory() as worker_session:

            async def override_get_db():
                yield worker_session

            client_no_auth.app.dependency_overrides[get_db] = override_get_db
            try:
                return await client_no_auth.post("/v1/auth/refresh", json={"refresh_token": token})
            finally:
                client_no_auth.app.dependency_overrides[get_db] = default_db_override

    clock[0] += timedelta(seconds=4)
    delayed_overlap = await refresh_from_another_worker(original)
    clock[0] += timedelta(seconds=4)
    second_delayed_overlap = await refresh_from_another_worker(original)

    assert rotated.status_code == 200
    assert delayed_overlap.status_code == 200
    assert second_delayed_overlap.status_code == 200
    assert delayed_overlap.json()["refresh_token"] == replacement
    assert second_delayed_overlap.json()["refresh_token"] == replacement
    db_session.expire_all()
    overlap_sessions = (
        (
            await db_session.execute(
                select(RefreshTokenSession).where(RefreshTokenSession.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(overlap_sessions) == 2
    assert sum(item.revoked_at is None for item in overlap_sessions) == 1

    clock[0] += timedelta(seconds=3)
    replay = await client_no_auth.post("/v1/auth/refresh", json={"refresh_token": original})
    family_revoked = await client_no_auth.post(
        "/v1/auth/refresh", json={"refresh_token": replacement}
    )

    assert replay.status_code == 401
    assert family_revoked.status_code == 401
    sessions = (
        (
            await db_session.execute(
                select(RefreshTokenSession).where(RefreshTokenSession.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    assert sessions
    assert all(item.revoked_at is not None for item in sessions)


@pytest.mark.asyncio
async def test_refresh_overlap_rejects_replay_after_successor_is_spent(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="rotate-chain@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Rotate Chain",
        is_active=True,
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    login = await client_no_auth.post(
        "/v1/auth/login",
        json={"email": user.email, "password": "StrongPassword123!"},
    )
    original = login.json()["refresh_token"]
    first_rotation = await client_no_auth.post("/v1/auth/refresh", json={"refresh_token": original})
    first_successor = first_rotation.json()["refresh_token"]
    second_rotation = await client_no_auth.post(
        "/v1/auth/refresh", json={"refresh_token": first_successor}
    )
    active_successor = second_rotation.json()["refresh_token"]

    replay = await client_no_auth.post("/v1/auth/refresh", json={"refresh_token": original})
    family_revoked = await client_no_auth.post(
        "/v1/auth/refresh", json={"refresh_token": active_successor}
    )

    assert first_rotation.status_code == 200
    assert second_rotation.status_code == 200
    assert replay.status_code == 401
    assert family_revoked.status_code == 401


@pytest.mark.asyncio
async def test_unverified_user_cannot_refresh(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="unverified-refresh@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Unverified Refresh",
        is_active=True,
        is_email_verified=False,
    )
    db_session.add(user)
    await db_session.commit()
    _, _, refresh_token = await issue_token_pair(db_session, user.id)
    await db_session.commit()

    response = await client_no_auth.post("/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unverified_user_access_token_cannot_authenticate(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="unverified-access@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Unverified Access",
        is_active=True,
        is_email_verified=False,
    )
    db_session.add(user)
    await db_session.commit()
    access_token, _, _ = await issue_token_pair(db_session, user.id)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {access_token}"}

    me_response = await client_no_auth.get("/v1/auth/me", headers=headers)
    protected_response = await client_no_auth.get("/v1/agents", headers=headers)

    assert me_response.status_code == 403
    assert protected_response.status_code == 403
    assert "verification is required" in me_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unverified_user_api_key_cannot_authenticate(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="unverified-api-key@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Unverified API Key",
        is_active=True,
        is_email_verified=False,
    )
    db_session.add(user)
    await db_session.commit()
    _, api_key = await UserService(db_session).create_api_key(user.id, "legacy key")

    response = await client_no_auth.get(
        "/v1/webhooks/",
        headers={"X-API-Key": api_key},
    )

    assert response.status_code == 403
    assert "verification is required" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_logout_rejects_invalid_refresh_and_revokes_valid_session(
    client_no_auth: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email="logout-refresh@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Logout",
        is_active=True,
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    _, _, refresh_token = await issue_token_pair(db_session, user.id)
    await db_session.commit()

    invalid = await client_no_auth.post("/v1/auth/logout", json={"refresh_token": "x" * 64})
    valid = await client_no_auth.post("/v1/auth/logout", json={"refresh_token": refresh_token})
    after_logout = await client_no_auth.post(
        "/v1/auth/refresh", json={"refresh_token": refresh_token}
    )

    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert after_logout.status_code == 401
