from __future__ import annotations

import time
from enum import Enum
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt
from pydantic import BaseModel

from src.api.config import get_settings

settings = get_settings()

APPLE_ID_TOKEN_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ID_TOKEN_ALGORITHMS = ["RS256"]


class OAuthProvider(str, Enum):
    GOOGLE = "google"
    GITHUB = "github"
    DISCORD = "discord"
    APPLE = "apple"


class SocialAuthError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class OAuthUserProfile(BaseModel):
    provider: OAuthProvider
    provider_user_id: str
    email: str
    email_verified: bool
    display_name: str
    username: str | None = None
    avatar_url: str | None = None
    profile: dict[str, Any]


def get_provider_client_id(provider: OAuthProvider) -> str | None:
    return getattr(settings, f"{provider.value}_client_id", None)


def get_provider_client_secret(provider: OAuthProvider) -> str | None:
    return getattr(settings, f"{provider.value}_client_secret", None)


def build_authorization_url(
    provider: OAuthProvider,
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }

    if provider == OAuthProvider.GOOGLE:
        params.update(
            {
                "response_type": "code",
                "scope": "openid email profile",
                "access_type": "offline",
                "prompt": "select_account",
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    if provider == OAuthProvider.GITHUB:
        params.update(
            {
                "scope": "read:user user:email",
                "allow_signup": "true",
            }
        )
        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    if provider == OAuthProvider.DISCORD:
        params.update(
            {
                "response_type": "code",
                "scope": "identify email",
                "prompt": "consent",
            }
        )
        return f"https://discord.com/oauth2/authorize?{urlencode(params)}"

    if provider == OAuthProvider.APPLE:
        params.update(
            {
                "response_type": "code",
                "scope": "name email",
                "response_mode": "form_post",
            }
        )
        return f"https://appleid.apple.com/auth/authorize?{urlencode(params)}"

    raise SocialAuthError(f"Unsupported OAuth provider: {provider.value}")


async def exchange_code_for_user_profile(
    provider: OAuthProvider,
    *,
    code: str,
    redirect_uri: str,
) -> OAuthUserProfile:
    client_id = get_provider_client_id(provider)
    client_secret = get_provider_client_secret(provider)

    if not client_id:
        raise SocialAuthError(
            f"{provider.value.title()} OAuth is not configured on the backend.",
            status_code=500,
        )

    if provider == OAuthProvider.APPLE:
        client_secret = _generate_apple_client_secret()
    elif not client_secret:
        raise SocialAuthError(
            f"{provider.value.title()} OAuth is not configured on the backend.",
            status_code=500,
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if provider == OAuthProvider.GOOGLE:
                return await _exchange_google_code(
                    client,
                    code=code,
                    redirect_uri=redirect_uri,
                    client_id=client_id,
                    client_secret=client_secret,
                )

            if provider == OAuthProvider.GITHUB:
                return await _exchange_github_code(
                    client,
                    code=code,
                    redirect_uri=redirect_uri,
                    client_id=client_id,
                    client_secret=client_secret,
                )

            if provider == OAuthProvider.DISCORD:
                return await _exchange_discord_code(
                    client,
                    code=code,
                    redirect_uri=redirect_uri,
                    client_id=client_id,
                    client_secret=client_secret,
                )

            if provider == OAuthProvider.APPLE:
                return await _exchange_apple_code(
                    client,
                    code=code,
                    redirect_uri=redirect_uri,
                    client_id=client_id,
                    client_secret=client_secret,
                )
    except httpx.RequestError as exc:
        raise SocialAuthError(
            f"Could not reach {provider.value.title()} during OAuth exchange.",
            status_code=502,
        ) from exc

    raise SocialAuthError(f"Unsupported OAuth provider: {provider.value}")


async def _exchange_google_code(
    client: httpx.AsyncClient,
    *,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> OAuthUserProfile:
    token_response = await client.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    _raise_for_provider_error(token_response, "Google token exchange failed")

    token_payload = token_response.json()
    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise SocialAuthError("Google did not return an access token.")

    profile_response = await client.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    _raise_for_provider_error(profile_response, "Google profile lookup failed")

    profile = profile_response.json()
    email = profile.get("email")
    if not isinstance(email, str) or not email:
        raise SocialAuthError("Google did not return an email address.")
    if not profile.get("email_verified"):
        raise SocialAuthError("Google account email must be verified before continuing.")
    provider_user_id = str(profile.get("sub", "")).strip()
    if not provider_user_id:
        raise SocialAuthError("Google did not return a stable account identifier.", status_code=502)

    return OAuthUserProfile(
        provider=OAuthProvider.GOOGLE,
        provider_user_id=provider_user_id,
        email=email.lower(),
        email_verified=bool(profile.get("email_verified")),
        display_name=str(profile.get("name") or profile.get("given_name") or email.split("@")[0]),
        username=None,
        avatar_url=profile.get("picture"),
        profile=profile,
    )


async def _exchange_github_code(
    client: httpx.AsyncClient,
    *,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> OAuthUserProfile:
    token_response = await client.post(
        "https://github.com/login/oauth/access_token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    _raise_for_provider_error(token_response, "GitHub token exchange failed")

    token_payload = token_response.json()
    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise SocialAuthError("GitHub did not return an access token.")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    profile_response = await client.get("https://api.github.com/user", headers=headers)
    _raise_for_provider_error(profile_response, "GitHub profile lookup failed")
    profile = profile_response.json()

    emails_response = await client.get("https://api.github.com/user/emails", headers=headers)
    _raise_for_provider_error(emails_response, "GitHub email lookup failed")
    email = _pick_github_email(emails_response.json())
    if email is None:
        raise SocialAuthError("GitHub account must expose at least one verified email address.")

    login = profile.get("login")
    display_name = profile.get("name") or login or email["email"].split("@")[0]
    provider_user_id = str(profile.get("id", "")).strip()
    if not provider_user_id:
        raise SocialAuthError("GitHub did not return a stable account identifier.", status_code=502)

    return OAuthUserProfile(
        provider=OAuthProvider.GITHUB,
        provider_user_id=provider_user_id,
        email=email["email"].lower(),
        email_verified=True,
        display_name=str(display_name),
        username=str(login) if isinstance(login, str) else None,
        avatar_url=profile.get("avatar_url"),
        profile={
            "user": profile,
            "emails": emails_response.json(),
        },
    )


async def _exchange_discord_code(
    client: httpx.AsyncClient,
    *,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> OAuthUserProfile:
    token_response = await client.post(
        "https://discord.com/api/oauth2/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    _raise_for_provider_error(token_response, "Discord token exchange failed")

    token_payload = token_response.json()
    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise SocialAuthError("Discord did not return an access token.")

    profile_response = await client.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    _raise_for_provider_error(profile_response, "Discord profile lookup failed")

    profile = profile_response.json()
    email = profile.get("email")
    if not isinstance(email, str) or not email:
        raise SocialAuthError("Discord did not return an email address.")
    if not profile.get("verified"):
        raise SocialAuthError("Discord account email must be verified before continuing.")

    user_id = str(profile.get("id", ""))
    if not user_id:
        raise SocialAuthError(
            "Discord did not return a stable account identifier.", status_code=502
        )
    avatar_hash = profile.get("avatar")
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=256"
        if isinstance(avatar_hash, str) and avatar_hash
        else None
    )

    return OAuthUserProfile(
        provider=OAuthProvider.DISCORD,
        provider_user_id=user_id,
        email=email.lower(),
        email_verified=True,
        display_name=str(
            profile.get("global_name") or profile.get("username") or email.split("@")[0]
        ),
        username=str(profile.get("username")) if isinstance(profile.get("username"), str) else None,
        avatar_url=avatar_url,
        profile=profile,
    )


def _generate_apple_client_secret() -> str:
    """Generate a JWT client secret for Apple Sign In.

    Apple requires the client secret to be a JWT signed with the ES256
    algorithm using the .p8 private key provisioned from the Apple
    Developer portal.  The JWT is short-lived (5 minutes) and generated
    fresh on every exchange request.
    """
    _settings = get_settings()

    team_id = _settings.apple_team_id
    key_id = _settings.apple_key_id
    client_id = _settings.apple_client_id
    private_key = _settings.apple_private_key

    if not all([team_id, key_id, client_id, private_key]):
        raise SocialAuthError(
            "Apple Sign In is not fully configured. "
            "APPLE_CLIENT_ID, APPLE_TEAM_ID, APPLE_KEY_ID, and APPLE_PRIVATE_KEY are all required.",
            status_code=500,
        )

    now = int(time.time())
    claims = {
        "iss": team_id,
        "iat": now,
        "exp": now + 300,  # 5-minute expiry
        "aud": "https://appleid.apple.com",
        "sub": client_id,
    }

    return jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": key_id})


async def _exchange_apple_code(
    client: httpx.AsyncClient,
    *,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> OAuthUserProfile:
    """Exchange an Apple authorization code for a user profile.

    Apple returns user info inside the ``id_token`` JWT from the token
    endpoint.  The ``user`` JSON (with name) is only sent on the very
    first authorization and is not available here — we fall back to the
    email prefix as a display name when the name is absent.
    """
    token_response = await client.post(
        "https://appleid.apple.com/auth/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    _raise_for_provider_error(token_response, "Apple token exchange failed")

    token_payload = token_response.json()
    id_token_raw = token_payload.get("id_token")
    if not isinstance(id_token_raw, str) or not id_token_raw:
        raise SocialAuthError("Apple did not return an id_token.")

    claims = await _decode_apple_id_token(client, id_token_raw, client_id)

    apple_user_id = claims.get("sub")
    if not isinstance(apple_user_id, str) or not apple_user_id:
        raise SocialAuthError("Apple id_token did not contain a subject (sub).")

    email = claims.get("email")
    if not isinstance(email, str) or not email:
        raise SocialAuthError("Apple did not return an email address.")

    email_verified = claims.get("email_verified")
    if isinstance(email_verified, str):
        email_verified = email_verified.lower() == "true"
    email_verified = bool(email_verified)
    if not email_verified:
        raise SocialAuthError("Apple account email must be verified before continuing.")

    display_name = str(email.split("@")[0])

    return OAuthUserProfile(
        provider=OAuthProvider.APPLE,
        provider_user_id=apple_user_id,
        email=email.lower(),
        email_verified=email_verified,
        display_name=display_name,
        username=None,
        avatar_url=None,
        profile={
            "id_token_claims": claims,
        },
    )


async def _decode_apple_id_token(
    client: httpx.AsyncClient,
    id_token_raw: str,
    client_id: str,
) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(id_token_raw)
    except JWTError as exc:
        raise SocialAuthError("Could not read Apple id_token header.") from exc

    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise SocialAuthError("Apple id_token did not include a key identifier.")

    jwks_response = await client.get(APPLE_JWKS_URL)
    _raise_for_provider_error(jwks_response, "Apple key lookup failed")

    jwks_payload = jwks_response.json()
    keys = jwks_payload.get("keys") if isinstance(jwks_payload, dict) else None
    if not isinstance(keys, list) or not keys:
        raise SocialAuthError("Apple key lookup did not return signing keys.", status_code=502)

    signing_key = next(
        (key for key in keys if isinstance(key, dict) and key.get("kid") == kid), None
    )
    if signing_key is None:
        raise SocialAuthError("Apple id_token signing key was not found.", status_code=401)

    try:
        return jwt.decode(
            id_token_raw,
            signing_key,
            algorithms=APPLE_ID_TOKEN_ALGORITHMS,
            audience=client_id,
            issuer=APPLE_ID_TOKEN_ISSUER,
        )
    except JWTError as exc:
        raise SocialAuthError("Apple id_token verification failed.", status_code=401) from exc


def _pick_github_email(items: Any) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None

    verified_items = [
        item
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("email"), str)
        and item.get("verified") is True
    ]
    if not verified_items:
        return None

    primary = next((item for item in verified_items if item.get("primary") is True), None)
    return primary or verified_items[0]


def _raise_for_provider_error(response: httpx.Response, fallback_message: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        payload: dict[str, Any] | None = None
        try:
            maybe_payload = response.json()
            if isinstance(maybe_payload, dict):
                payload = maybe_payload
        except ValueError:
            payload = None

        detail = None
        if payload is not None:
            detail = (
                payload.get("error_description") or payload.get("error") or payload.get("message")
            )

        raise SocialAuthError(
            str(detail or fallback_message),
            status_code=exc.response.status_code,
        ) from exc
