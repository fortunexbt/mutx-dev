"""OIDC token validation and provider-specific SSO helpers.

The generic validator is configured through ``OIDC_ISSUER``,
``OIDC_CLIENT_ID``, and ``OIDC_JWKS_URI`` on :class:`src.api.config.Settings`.
Provider SSO callbacks use only their provider-specific issuer, client ID, and
JWKS endpoint so an unrelated generic resource-server configuration cannot
change their trust boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import time
from typing import Any

from fastapi import HTTPException, status
import httpx
from jose import JWTError, jwt
from pydantic import BaseModel

from src.api.config import Settings, get_settings


class SSOProvider(str, Enum):
    """Supported legacy SSO providers."""

    OKTA = "okta"
    AUTH0 = "auth0"
    KEYCLOAK = "keycloak"
    GOOGLE = "google"


class TokenPayload(BaseModel):
    """Normalized claims used by MUTX SSO and RBAC code."""

    sub: str
    email: str
    email_verified: bool = False
    roles: list[str]
    exp: datetime


@dataclass(frozen=True)
class OIDCSettings:
    """Complete external OIDC verification configuration."""

    issuer: str
    client_id: str
    jwks_uri: str


class OIDCTokenValidationError(Exception):
    """Raised when an external OIDC token cannot be validated."""


PROVIDER_OIDC_CONFIG: dict[SSOProvider, str] = {
    SSOProvider.OKTA: "{domain}/.well-known/openid-configuration",
    SSOProvider.AUTH0: "{domain}/.well-known/openid-configuration",
    SSOProvider.KEYCLOAK: "{domain}/realms/{realm}/.well-known/openid-configuration",
    SSOProvider.GOOGLE: "https://accounts.google.com/.well-known/openid-configuration",
}

PROVIDER_JWKS_URLS: dict[SSOProvider, str] = {
    SSOProvider.OKTA: "{domain}/oauth2/v1/keys",
    SSOProvider.AUTH0: "{domain}/.well-known/jwks.json",
    SSOProvider.KEYCLOAK: "{domain}/realms/{realm}/protocol/openid-connect/certs",
    SSOProvider.GOOGLE: "https://www.googleapis.com/oauth2/v3/certs",
}

PROVIDER_USERINFO_URLS: dict[SSOProvider, str] = {
    SSOProvider.OKTA: "{domain}/oauth2/v1/userinfo",
    SSOProvider.AUTH0: "{domain}/userinfo",
    SSOProvider.KEYCLOAK: "{domain}/realms/{realm}/protocol/openid-connect/userinfo",
    SSOProvider.GOOGLE: "https://openidconnect.googleapis.com/v1/userinfo",
}

_JWKS_CACHE_TTL_SECONDS = 3600
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def get_oidc_settings(source: Settings | None = None) -> OIDCSettings | None:
    """Return configured OIDC settings, or ``None`` when OIDC is disabled."""
    source = source or get_settings()
    values = (source.oidc_issuer, source.oidc_client_id, source.oidc_jwks_uri)
    if not any(values):
        return None

    if not all(values):
        raise RuntimeError("OIDC configuration is incomplete")

    return OIDCSettings(
        issuer=source.oidc_issuer,
        client_id=source.oidc_client_id,
        jwks_uri=source.oidc_jwks_uri,
    )


async def fetch_jwks(jwks_uri: str, *, force_refresh: bool = False) -> dict[str, Any]:
    """Fetch and cache a JWKS document by URI for one hour."""
    now = time.monotonic()
    cached = _JWKS_CACHE.get(jwks_uri)
    if not force_refresh and cached and now < cached[0]:
        return cached[1]

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(jwks_uri)
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise OIDCTokenValidationError("OIDC provider returned an invalid JWKS document")

    _JWKS_CACHE[jwks_uri] = (now + _JWKS_CACHE_TTL_SECONDS, data)
    return data


def clear_jwks_cache() -> None:
    """Clear cached provider keys, primarily for tests and key rotation recovery."""
    _JWKS_CACHE.clear()


def _find_key_by_kid(jwks: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
    if not kid:
        return None
    return next((key for key in jwks.get("keys", []) if key.get("kid") == kid), None)


async def _get_signing_key(jwks_uri: str, kid: str | None) -> dict[str, Any] | None:
    """Resolve a signing key, refreshing once when a provider rotates keys."""
    jwks = await fetch_jwks(jwks_uri)
    signing_key = _find_key_by_kid(jwks, kid)
    if signing_key is not None:
        return signing_key

    refreshed_jwks = await fetch_jwks(jwks_uri, force_refresh=True)
    return _find_key_by_kid(refreshed_jwks, kid)


async def validate_oidc_token(
    token: str,
    *,
    settings: OIDCSettings | None = None,
) -> dict[str, Any]:
    """Validate signature, issuer, audience, and expiry for an OIDC JWT."""
    settings = settings or get_oidc_settings()
    if settings is None:
        raise OIDCTokenValidationError("OIDC validation is not configured")

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise OIDCTokenValidationError("Malformed OIDC token header") from exc

    algorithm = header.get("alg")
    allowed_algorithms = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
    if algorithm not in allowed_algorithms:
        raise OIDCTokenValidationError("OIDC token uses an unsupported signing algorithm")

    try:
        signing_key = await _get_signing_key(settings.jwks_uri, header.get("kid"))
    except OIDCTokenValidationError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise OIDCTokenValidationError("Unable to fetch OIDC provider signing keys") from exc

    if signing_key is None:
        raise OIDCTokenValidationError("No OIDC signing key matches the token key id")

    try:
        return jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience=settings.client_id,
            issuer=settings.issuer,
            options={"require_exp": True},
        )
    except jwt.ExpiredSignatureError as exc:
        raise OIDCTokenValidationError("OIDC token has expired") from exc
    except JWTError as exc:
        raise OIDCTokenValidationError("OIDC token validation failed") from exc


def _get_provider_config(provider: SSOProvider, domain: str, realm: str | None = None) -> dict:
    base_domain = domain.rstrip("/")
    if provider == SSOProvider.KEYCLOAK and realm:
        issuer = f"{base_domain}/realms/{realm}"
    elif provider == SSOProvider.AUTH0:
        issuer = f"{base_domain}/"
    else:
        issuer = base_domain
    return {
        "issuer": issuer,
        "userinfo_endpoint": PROVIDER_USERINFO_URLS[provider].format(
            domain=base_domain, realm=realm or ""
        ),
        "jwks_uri": PROVIDER_JWKS_URLS[provider].format(
            domain=base_domain,
            realm=realm or "",
        ),
    }


def _extract_roles_from_payload(
    payload: dict[str, Any],
    provider: SSOProvider,
    *,
    client_id: str | None = None,
) -> list[str]:
    roles: list[str] = []
    for location in ("roles", "groups", "custom:roles", "realm_access.roles"):
        value: Any = payload
        for part in location.split("."):
            value = value.get(part, []) if isinstance(value, dict) else []
        if isinstance(value, list):
            roles.extend(str(role) for role in value)
        elif isinstance(value, str):
            roles.append(value)

    resource_access = payload.get("resource_access", {})
    if isinstance(resource_access, dict) and client_id:
        client_access = resource_access.get(client_id)
        if isinstance(client_access, dict) and isinstance(client_access.get("roles"), list):
            roles.extend(str(role) for role in client_access["roles"])

    if provider == SSOProvider.GOOGLE and isinstance(payload.get("mutable-roles"), list):
        roles.extend(str(role) for role in payload["mutable-roles"])

    return list(dict.fromkeys(roles))


def _normalize_payload(
    payload: dict[str, Any],
    provider: SSOProvider,
    *,
    client_id: str | None = None,
) -> TokenPayload:
    subject = str(payload.get("sub", "")).strip()
    email = str(payload.get("email", payload.get("preferred_username", ""))).strip().casefold()
    if not subject or not email:
        raise OIDCTokenValidationError("OIDC identity is missing a subject or email")
    if payload.get("email_verified") is not True:
        raise OIDCTokenValidationError("OIDC identity must affirm that the email is verified")
    return TokenPayload(
        sub=subject,
        email=email,
        email_verified=True,
        roles=_extract_roles_from_payload(payload, provider, client_id=client_id),
        exp=datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc),
    )


async def verify_oauth_token(
    token: str,
    provider: SSOProvider,
    domain: str | None = None,
    realm: str | None = None,
    *,
    client_id: str | None = None,
    allow_userinfo_fallback: bool = True,
) -> TokenPayload:
    """Verify a provider token against that provider's issuer and audience."""
    source = get_settings()
    domain = domain or getattr(source, f"{provider.value}_domain", None)
    realm = realm or getattr(source, f"{provider.value}_realm", None)
    client_id = client_id or getattr(source, f"{provider.value}_client_id", None)

    if domain is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No domain configured for SSO provider: {provider.value}",
        )
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No client ID configured for SSO provider: {provider.value}",
        )

    config = _get_provider_config(provider, domain, realm)
    try:
        header = jwt.get_unverified_header(token)
        signing_key = await _get_signing_key(config["jwks_uri"], header.get("kid"))
        if signing_key is None:
            if allow_userinfo_fallback:
                return await _verify_via_userinfo(token, config["userinfo_endpoint"])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No OIDC signing key matches the token key id",
            )
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            audience=client_id,
            issuer=config["issuer"],
            options={"require_exp": True},
        )
        return _normalize_payload(payload, provider, client_id=client_id)
    except (JWTError, OIDCTokenValidationError, httpx.HTTPError) as exc:
        if allow_userinfo_fallback:
            return await _verify_via_userinfo(token, config["userinfo_endpoint"])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC token validation failed",
        ) from exc


async def _verify_via_userinfo(token: str, userinfo_uri: str) -> TokenPayload:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                userinfo_uri,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
        userinfo = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed",
        ) from exc

    if not isinstance(userinfo, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed",
        )
    subject = str(userinfo.get("sub", userinfo.get("user_id", ""))).strip()
    email = str(userinfo.get("email", userinfo.get("preferred_username", ""))).strip().casefold()
    if not subject or not email or userinfo.get("email_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC identity is incomplete or unverified",
        )

    roles = userinfo.get("roles", userinfo.get("groups", userinfo.get("custom:roles", [])))
    if isinstance(roles, str):
        roles = [roles]
    return TokenPayload(
        sub=subject,
        email=email,
        email_verified=True,
        roles=roles if isinstance(roles, list) else [],
        exp=datetime.now(timezone.utc) + timedelta(hours=1),
    )
