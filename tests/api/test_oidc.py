from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from src.api.auth import oidc
from src.api.auth.dependencies import SSOTokenUser, require_roles
from src.api.config import Settings
from src.api.services.auth import Role


def _clear_oidc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_JWKS_URI"):
        monkeypatch.delenv(name, raising=False)


def test_settings_load_complete_oidc_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_oidc_env(monkeypatch)
    monkeypatch.setenv("OIDC_ISSUER", "https://id.example.com/")
    monkeypatch.setenv("OIDC_CLIENT_ID", "mutx-api")
    monkeypatch.setenv("OIDC_JWKS_URI", "https://id.example.com/keys")

    settings = Settings(_env_file=None)
    resolved = oidc.get_oidc_settings(settings)

    assert resolved == oidc.OIDCSettings(
        issuer="https://id.example.com/",
        client_id="mutx-api",
        jwks_uri="https://id.example.com/keys",
    )


def test_settings_reject_partial_oidc_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_oidc_env(monkeypatch)
    monkeypatch.setenv("OIDC_ISSUER", "https://id.example.com")

    with pytest.raises(ValidationError, match="OIDC configuration must be provided"):
        Settings(_env_file=None)


def test_settings_allow_separate_complete_generic_and_provider_oidc_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_oidc_env(monkeypatch)
    configuration = {
        "OIDC_ISSUER": "https://generic.example.com",
        "OIDC_CLIENT_ID": "generic-client",
        "OIDC_JWKS_URI": "https://generic.example.com/keys",
        "OKTA_DOMAIN": "https://provider.example.com",
        "OKTA_CLIENT_ID": "provider-client",
        "OKTA_CLIENT_SECRET": "provider-secret",
        "PUBLIC_API_URL": "https://api.example.com",
    }
    for name, value in configuration.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    assert oidc.get_oidc_settings(settings) == oidc.OIDCSettings(
        issuer="https://generic.example.com",
        client_id="generic-client",
        jwks_uri="https://generic.example.com/keys",
    )
    assert settings.okta_client_id == "provider-client"


@pytest.mark.asyncio
async def test_fetch_jwks_caches_each_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"keys": [{"kid": "key-1"}]}

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, uri: str) -> FakeResponse:
            requests.append(uri)
            return FakeResponse()

    monkeypatch.setattr(oidc.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    oidc.clear_jwks_cache()

    first = await oidc.fetch_jwks("https://id.example.com/keys")
    second = await oidc.fetch_jwks("https://id.example.com/keys")
    await oidc.fetch_jwks("https://other.example.com/keys")

    assert first is second
    assert requests == [
        "https://id.example.com/keys",
        "https://other.example.com/keys",
    ]


@pytest.mark.asyncio
async def test_validate_oidc_token_checks_key_issuer_and_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = oidc.OIDCSettings(
        issuer="https://id.example.com",
        client_id="mutx-api",
        jwks_uri="https://id.example.com/keys",
    )
    signing_key = {"kid": "key-1", "kty": "RSA"}
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        oidc.jwt,
        "get_unverified_header",
        lambda _token: {"kid": "key-1", "alg": "RS256"},
    )

    async def fake_fetch_jwks(uri: str) -> dict[str, object]:
        assert uri == settings.jwks_uri
        return {"keys": [signing_key]}

    def fake_decode(token: str, key: dict[str, str], **kwargs: object) -> dict[str, object]:
        captured.update({"token": token, "key": key, **kwargs})
        return {
            "sub": "oidc-user",
            "email": "oidc@example.com",
            "roles": ["AUDIT_ADMIN"],
            "exp": 4_102_444_800,
        }

    monkeypatch.setattr(oidc, "fetch_jwks", fake_fetch_jwks)
    monkeypatch.setattr(oidc.jwt, "decode", fake_decode)

    payload = await oidc.validate_oidc_token("signed-token", settings=settings)

    assert payload["sub"] == "oidc-user"
    assert captured == {
        "token": "signed-token",
        "key": signing_key,
        "algorithms": ["RS256"],
        "audience": "mutx-api",
        "issuer": "https://id.example.com",
        "options": {"require_exp": True},
    }


@pytest.mark.asyncio
async def test_validate_oidc_token_rejects_unknown_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = oidc.OIDCSettings("https://id.example.com", "mutx-api", "https://keys")
    monkeypatch.setattr(
        oidc.jwt,
        "get_unverified_header",
        lambda _token: {"kid": "missing", "alg": "RS256"},
    )

    refreshes: list[bool] = []

    async def fake_fetch_jwks(
        _uri: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        refreshes.append(force_refresh)
        return {"keys": [{"kid": "different"}]}

    monkeypatch.setattr(oidc, "fetch_jwks", fake_fetch_jwks)

    with pytest.raises(oidc.OIDCTokenValidationError, match="matches the token key id"):
        await oidc.validate_oidc_token("signed-token", settings=settings)

    assert refreshes == [False, True]


@pytest.mark.asyncio
async def test_validate_oidc_token_refreshes_rotated_signing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = oidc.OIDCSettings("https://id.example.com/", "mutx-api", "https://keys")
    requests: list[bool] = []

    monkeypatch.setattr(
        oidc.jwt,
        "get_unverified_header",
        lambda _token: {"kid": "rotated", "alg": "RS256"},
    )

    async def fake_fetch_jwks(
        _uri: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        requests.append(force_refresh)
        kid = "rotated" if force_refresh else "previous"
        return {"keys": [{"kid": kid, "kty": "RSA"}]}

    monkeypatch.setattr(oidc, "fetch_jwks", fake_fetch_jwks)
    monkeypatch.setattr(
        oidc.jwt,
        "decode",
        lambda *_args, **_kwargs: {"sub": "rotated-user"},
    )

    payload = await oidc.validate_oidc_token("signed-token", settings=settings)

    assert payload == {"sub": "rotated-user"}
    assert requests == [False, True]


def test_resource_access_roles_are_scoped_to_the_configured_client() -> None:
    payload = oidc._normalize_payload(
        {
            "sub": "oidc-user",
            "email": "oidc@example.com",
            "email_verified": True,
            "exp": 4_102_444_800,
            "realm_access": {"roles": ["USER"]},
            "resource_access": {
                "mutx-api": {"roles": ["AUDIT_ADMIN"]},
                "unrelated-client": {"roles": ["ADMIN"]},
            },
        },
        oidc.SSOProvider.KEYCLOAK,
        client_id="mutx-api",
    )

    assert payload.roles == ["USER", "AUDIT_ADMIN"]


@pytest.mark.parametrize(
    ("provider", "domain", "realm", "expected_issuer"),
    [
        (oidc.SSOProvider.OKTA, "https://okta.example.com/", None, "https://okta.example.com"),
        (oidc.SSOProvider.AUTH0, "https://auth0.example.com", None, "https://auth0.example.com/"),
        (
            oidc.SSOProvider.KEYCLOAK,
            "https://keycloak.example.com/",
            "mutx",
            "https://keycloak.example.com/realms/mutx",
        ),
        (
            oidc.SSOProvider.GOOGLE,
            "https://accounts.google.com",
            None,
            "https://accounts.google.com",
        ),
    ],
)
def test_provider_oidc_issuer_is_selected_per_provider(
    provider: oidc.SSOProvider,
    domain: str,
    realm: str | None,
    expected_issuer: str,
) -> None:
    config = oidc._get_provider_config(provider, domain, realm)

    assert config["issuer"] == expected_issuer
    assert "//." not in config["jwks_uri"]


@pytest.mark.parametrize("email_verified", [None, False, "true"])
def test_oidc_payload_requires_boolean_true_email_verification(
    email_verified: object,
) -> None:
    with pytest.raises(oidc.OIDCTokenValidationError, match="must affirm"):
        oidc._normalize_payload(
            {
                "sub": "oidc-user",
                "email": "oidc@example.com",
                "email_verified": email_verified,
                "exp": 4_102_444_800,
            },
            oidc.SSOProvider.OKTA,
            client_id="mutx-api",
        )


@pytest.mark.asyncio
async def test_provider_sso_ignores_unrelated_generic_oidc_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_settings = SimpleNamespace(
        okta_domain="https://provider.example.com",
        okta_realm=None,
        okta_client_id="provider-client",
        oidc_issuer="https://generic.example.com",
        oidc_client_id="generic-client",
        oidc_jwks_uri="https://generic.example.com/keys",
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(oidc, "get_settings", lambda: provider_settings)
    monkeypatch.setattr(oidc.jwt, "get_unverified_header", lambda _token: {"kid": "key-1"})

    async def fake_signing_key(uri: str, kid: str | None) -> dict[str, str]:
        assert uri == "https://provider.example.com/oauth2/v1/keys"
        assert kid == "key-1"
        return {"kid": "key-1"}

    def fake_decode(*_args: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "sub": "oidc-user",
            "email": "oidc@example.com",
            "email_verified": True,
            "groups": ["AUDIT_ADMIN"],
            "exp": 4_102_444_800,
        }

    monkeypatch.setattr(oidc, "_get_signing_key", fake_signing_key)
    monkeypatch.setattr(oidc.jwt, "decode", fake_decode)
    monkeypatch.setattr(
        oidc,
        "get_oidc_settings",
        lambda: pytest.fail("generic OIDC settings must not participate in provider SSO"),
    )

    payload = await oidc.verify_oauth_token("signed-token", oidc.SSOProvider.OKTA)

    assert payload.sub == "oidc-user"
    assert payload.email_verified is True
    assert payload.roles == ["AUDIT_ADMIN"]
    assert payload.exp == datetime.fromtimestamp(4_102_444_800, tz=timezone.utc)
    assert captured["audience"] == "provider-client"
    assert captured["issuer"] == "https://provider.example.com"


@pytest.mark.asyncio
async def test_verify_oauth_token_uses_userinfo_for_opaque_access_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_settings = SimpleNamespace(
        okta_domain="https://id.example.com",
        okta_realm=None,
        okta_client_id="mutx-api",
    )
    monkeypatch.setattr(oidc, "get_settings", lambda: provider_settings)

    async def fake_userinfo(token: str, uri: str) -> oidc.TokenPayload:
        assert token == "opaque-access-token"
        assert uri == "https://id.example.com/oauth2/v1/userinfo"
        return oidc.TokenPayload(
            sub="oidc-user",
            email="oidc@example.com",
            email_verified=True,
            roles=["USER"],
            exp=datetime.fromtimestamp(4_102_444_800, tz=timezone.utc),
        )

    monkeypatch.setattr(oidc, "_verify_via_userinfo", fake_userinfo)

    payload = await oidc.verify_oauth_token(
        "opaque-access-token",
        oidc.SSOProvider.OKTA,
    )

    assert payload.sub == "oidc-user"


@pytest.mark.asyncio
@pytest.mark.parametrize("email_verified", [None, False, "true"])
async def test_userinfo_requires_boolean_true_email_verification(
    monkeypatch: pytest.MonkeyPatch,
    email_verified: object,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            payload: dict[str, object] = {
                "sub": "userinfo-user",
                "email": "userinfo@example.com",
            }
            if email_verified is not None:
                payload["email_verified"] = email_verified
            return payload

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, *_args: object, **_kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(oidc.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    with pytest.raises(oidc.HTTPException) as exc_info:
        await oidc._verify_via_userinfo("opaque-token", "https://id.example.com/userinfo")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_userinfo_propagates_affirmative_email_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "sub": "userinfo-user",
                "email": "userinfo@example.com",
                "email_verified": True,
            }

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, *_args: object, **_kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(oidc.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    payload = await oidc._verify_via_userinfo(
        "opaque-token",
        "https://id.example.com/userinfo",
    )

    assert payload.email_verified is True


@pytest.mark.asyncio
async def test_verify_oauth_token_rejects_invalid_id_tokens_without_userinfo_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_settings = SimpleNamespace(
        okta_domain="https://id.example.com",
        okta_realm=None,
        okta_client_id="mutx-api",
    )
    monkeypatch.setattr(oidc, "get_settings", lambda: provider_settings)

    async def fail_userinfo(*_args: object) -> oidc.TokenPayload:
        pytest.fail("userinfo must not replace validation of a returned ID token")

    monkeypatch.setattr(oidc, "_verify_via_userinfo", fail_userinfo)

    with pytest.raises(oidc.HTTPException, match="OIDC token validation failed"):
        await oidc.verify_oauth_token(
            "invalid-id-token",
            oidc.SSOProvider.OKTA,
            allow_userinfo_fallback=False,
        )


@pytest.mark.asyncio
async def test_legacy_verifier_honors_disabled_userinfo_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_settings = SimpleNamespace(
        okta_domain="https://id.example.com",
        okta_realm=None,
    )
    monkeypatch.setattr(oidc, "get_oidc_settings", lambda: None)
    monkeypatch.setattr(oidc, "get_settings", lambda: provider_settings)
    monkeypatch.setattr(oidc.jwt, "get_unverified_header", lambda _token: {"kid": "key-1"})

    async def fake_signing_key(*_args: object) -> dict[str, str]:
        return {"kid": "key-1"}

    def reject_invalid_token(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise oidc.JWTError("invalid signature")

    async def fail_userinfo(*_args: object) -> oidc.TokenPayload:
        pytest.fail("legacy ID token validation must not fall back to userinfo")

    monkeypatch.setattr(oidc, "_get_signing_key", fake_signing_key)
    monkeypatch.setattr(oidc.jwt, "decode", reject_invalid_token)
    monkeypatch.setattr(oidc, "_verify_via_userinfo", fail_userinfo)

    with pytest.raises(oidc.HTTPException, match="OIDC token validation failed"):
        await oidc.verify_oauth_token(
            "invalid-id-token",
            oidc.SSOProvider.OKTA,
            client_id="mutx-client",
            allow_userinfo_fallback=False,
        )


@pytest.mark.asyncio
async def test_legacy_verifier_validates_id_token_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_settings = SimpleNamespace(
        okta_domain="https://id.example.com",
        okta_realm=None,
    )
    monkeypatch.setattr(oidc, "get_oidc_settings", lambda: None)
    monkeypatch.setattr(oidc, "get_settings", lambda: provider_settings)
    monkeypatch.setattr(oidc.jwt, "get_unverified_header", lambda _token: {"kid": "key-1"})

    async def fake_signing_key(*_args: object) -> dict[str, str]:
        return {"kid": "key-1"}

    def fake_decode(*_args: object, **kwargs: object) -> dict[str, object]:
        assert kwargs["audience"] == "mutx-client"
        assert kwargs["options"] == {"require_exp": True}
        return {
            "sub": "oidc-user",
            "email": "oidc@example.com",
            "email_verified": True,
            "exp": 4_102_444_800,
        }

    monkeypatch.setattr(oidc, "_get_signing_key", fake_signing_key)
    monkeypatch.setattr(oidc.jwt, "decode", fake_decode)

    payload = await oidc.verify_oauth_token(
        "signed-id-token",
        oidc.SSOProvider.OKTA,
        client_id="mutx-client",
        allow_userinfo_fallback=False,
    )

    assert payload.sub == "oidc-user"


@pytest.mark.asyncio
async def test_require_roles_uses_canonical_sso_principal() -> None:
    principal = SSOTokenUser(
        oidc.TokenPayload(
            sub="admin",
            email="admin@example.com",
            roles=[Role.ADMIN.value],
            exp=datetime.now(timezone.utc),
        )
    )

    checker = require_roles("AUDIT_ADMIN")

    assert await checker(principal) is principal


def test_routes_import_auth_dependencies_only_from_canonical_facade() -> None:
    routes_dir = Path(__file__).resolve().parents[2] / "src" / "api" / "routes"
    legacy_imports = (
        "from src.api.middleware.auth import",
        "from src.api.dependencies import",
    )

    offenders = [
        path.name
        for path in routes_dir.glob("*.py")
        if any(legacy in path.read_text() for legacy in legacy_imports)
    ]

    assert offenders == []


def test_legacy_dependency_module_keeps_sso_compatibility() -> None:
    from src.api import dependencies as legacy
    from src.api.auth import dependencies as canonical

    assert legacy.get_current_user is canonical.get_current_sso_user
    assert legacy.SSOTokenUser is canonical.SSOTokenUser
