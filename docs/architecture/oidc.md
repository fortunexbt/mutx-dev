# OIDC Token Validation

> OpenID Connect validation utilities and the mounted SSO exchange boundary.

## Configuration

The generic `validate_oidc_token(...)` utility requires all three values:

- `OIDC_ISSUER`
- `OIDC_CLIENT_ID`
- `OIDC_JWKS_URI`

No mounted route currently feeds arbitrary bearer tokens into this generic
validator. The mounted `/v1/auth/sso/{provider}` flow uses provider-specific
domain/client settings, verifies the callback identity, binds it to a local
user, and returns a MUTX dashboard JWT.

## Mounted SSO Providers

- Okta
- Auth0
- Keycloak
- Google

## Implementation

`src/api/auth/oidc.py` provides the per-URI TTL cache, JWT signature validation,
and `iss`/`aud`/`exp` claim checks. The callback persists an external-identity
binding and issues the same UUID-backed JWT used by password login. Canonical
route auth reloads the local user and its persisted roles through
`src/api/auth/dependencies.py`; provider role claims do not authorize requests.
