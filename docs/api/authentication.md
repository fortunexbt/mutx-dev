# Authentication

MUTX uses JWT-based user auth for interactive sessions. `login`,
`local-bootstrap`, and `refresh` return a token pair. Registration is always an
account-creation request rather than a login: it returns a uniform accepted
shape with null token fields and queues verification delivery for an unverified
account. When verification is disabled, the user can log in immediately, but
registration still does not issue tokens.

## Endpoints

| Route | Purpose |
| --- | --- |
| `POST /v1/auth/register` | Create or safely acknowledge an unverified account and queue verification delivery |
| `POST /v1/auth/login` | Exchange email and password for a token pair |
| `POST /v1/auth/local-bootstrap` | Localhost-only bootstrap for non-production local setups |
| `POST /v1/auth/refresh` | Exchange a refresh token for a fresh token pair |
| `POST /v1/auth/logout` | Revoke the provided refresh token family or all user refresh sessions |
| `GET /v1/auth/me` | Return the authenticated user profile |
| `POST /v1/auth/forgot-password` | Start password reset flow |
| `POST /v1/auth/reset-password` | Complete password reset and revoke prior refresh sessions |
| `POST /v1/auth/verify-email` | Mark an email as verified |
| `POST /v1/auth/resend-verification` | Re-send verification email |
| `GET /v1/auth/oauth/{provider}/authorize` | Build an OAuth authorization URL for a social provider |
| `POST /v1/auth/oauth/{provider}/exchange` | Exchange an OAuth authorization code for a MUTX token pair |
| `GET /v1/auth/sso/{provider}` | Initiate SSO by redirecting to the provider's authorization endpoint |
| `GET /v1/auth/sso/{provider}/callback` | Handle SSO callback and issue a MUTX access token |

## Password Policy

`register` and `reset-password` enforce the current password validator in `src/api/auth/password.py`:

- at least 8 characters
- at least one uppercase letter
- at least one lowercase letter
- at least one number
- at least one special character

## Register

```bash
BASE_URL=http://localhost:8000

curl -X POST "$BASE_URL/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "operator@example.com",
    "name": "Operator",
    "password": "StrongPass1!"
  }'
```

Example response:

```json
{
  "access_token": null,
  "refresh_token": null,
  "token_type": "bearer",
  "expires_in": null,
  "verification_email_sent": true,
  "requires_email_verification": true,
  "return_path": "/dashboard"
}
```

The response is deliberately uniform to reduce account enumeration. Delivery is
performed in a background task, so `verification_email_sent` means the task was
queued rather than proving provider acceptance. If mail delivery is unavailable,
configure Resend or SMTP and use `POST /v1/auth/resend-verification`. When
verification is explicitly disabled, `requires_email_verification` is `false`,
but the token fields remain null; use `POST /v1/auth/login` to authenticate.

## Login

```bash
curl -X POST "$BASE_URL/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "operator@example.com",
    "password": "StrongPass1!"
  }'
```

`login` returns the standard non-null token-pair payload. With verification enabled,
password login remains blocked until `POST /v1/auth/verify-email` succeeds.

## Local Bootstrap

`POST /v1/auth/local-bootstrap` exists for localhost operator setup.

It is rejected in production and rejected for non-loopback callers.

```bash
curl -X POST "$BASE_URL/v1/auth/local-bootstrap" \
  -H "Content-Type: application/json" \
  -d '{"name":"Local Operator"}'
```

## Refresh

```bash
curl -X POST "$BASE_URL/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"YOUR_REFRESH_TOKEN"}'
```

The response is another access + refresh token pair. The refresh token family is rotated.

## Logout

`logout` supports two patterns:

- send `Authorization: Bearer <access_token>` to revoke all refresh sessions for the current user
- send a `refresh_token` body to revoke that refresh token family directly

```bash
curl -X POST "$BASE_URL/v1/auth/logout" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Example response:

```json
{
  "message": "Successfully logged out"
}
```

## Current User

```bash
curl "$BASE_URL/v1/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Example response:

```json
{
  "id": "uuid",
  "email": "operator@example.com",
  "name": "Operator",
  "plan": "free",
  "roles": ["VIEWER"],
  "created_at": "2026-03-22T12:00:00Z",
  "is_active": true,
  "is_email_verified": false
}
```

## Password Reset And Email Verification

All four endpoints use small request bodies and message responses:

- `POST /v1/auth/forgot-password`
- `POST /v1/auth/reset-password`
- `POST /v1/auth/verify-email`
- `POST /v1/auth/resend-verification`

Examples:

```bash
curl -X POST "$BASE_URL/v1/auth/forgot-password" \
  -H "Content-Type: application/json" \
  -d '{"email":"operator@example.com"}'

curl -X POST "$BASE_URL/v1/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d '{"token":"RESET_TOKEN","new_password":"NewStrongPass1!"}'
```

`forgot-password` and some verification flows intentionally return generic success messages to reduce account enumeration.

## OAuth Social Login

MUTX supports social login via external OAuth providers (e.g. GitHub, Google).

### Authorize

```bash
curl "$BASE_URL/v1/auth/oauth/github/authorize?redirect_uri=http://localhost:3000/api/auth/oauth/github/callback"
```

Returns an `authorization_url` to redirect the user to:

```json
{
  "authorization_url": "https://github.com/login/oauth/authorize?...",
  "state": "SERVER_ISSUED_STATE"
}
```

The server creates and stores the state value. Return that exact value in the
exchange request.

### Exchange

```bash
curl -X POST "$BASE_URL/v1/auth/oauth/github/exchange" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "OAUTH_CODE",
    "redirect_uri": "http://localhost:3000/api/auth/oauth/github/callback",
    "state": "SERVER_ISSUED_STATE"
  }'
```

Returns the standard token-pair payload (`access_token`, `refresh_token`, `token_type`, `expires_in`).

If the OAuth user does not yet exist in MUTX, it is created automatically.

## SSO Provider Login

SSO login supports Okta, Auth0, Keycloak, and Google.

### Initiate SSO

```bash
curl "$BASE_URL/v1/auth/sso/okta"
```

Returns a `302` redirect to the provider's authorization URL.

### SSO Callback

The provider redirects back to `GET /v1/auth/sso/{provider}/callback?code=...&state=...`.

On success, the callback returns a MUTX access token:

```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

`expires_in` is calculated from the server's configured access-token lifetime;
the value above reflects the default 30-minute setting.

## OIDC Token Validation

The mounted SSO callback validates a provider identity, binds it to a local user,
and issues a MUTX dashboard JWT. Protected control-plane routes consume that
internal JWT; they do not directly accept an arbitrary provider bearer token.

### Configuration

The generic validation utility in `src/api/auth/oidc.py` is configured with:

| Variable | Description | Example |
| --- | --- | --- |
| `OIDC_ISSUER` | Token issuer URL (your IdP domain) | `https://your-org.okta.com` |
| `OIDC_CLIENT_ID` | Expected `aud` claim for your MUTX client | `0oa1abc2def3ghi4jkl5` |
| `OIDC_JWKS_URI` | JWKS endpoint for public key retrieval | `https://your-org.okta.com/oauth2/v1/keys` |

Set all three values together when calling the generic
`validate_oidc_token(...)` utility. No mounted route currently invokes that
generic validator automatically. The mounted SSO routes instead use
provider-specific domain/client credentials (`OKTA_*`, `AUTH0_*`,
`KEYCLOAK_*`, or `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`) and the following
well-known/JWKS templates:

```python
PROVIDER_OIDC_CONFIG = {
    SSOProvider.OKTA:      "{domain}/.well-known/openid-configuration",
    SSOProvider.AUTH0:     "{domain}/.well-known/openid-configuration",
    SSOProvider.KEYCLOAK:  "{domain}/realms/{realm}/.well-known/openid-configuration",
    SSOProvider.GOOGLE:    "https://accounts.google.com/.well-known/openid-configuration",
}
```

### Validation Flow

1. **JWKS fetch** -- The validator fetches the provider's JWKS and caches the document for one hour per URI.
2. **Signature check** -- The token's RS256/ES256 signature is verified against the matching JWKS key (by `kid`).
3. **Claims validation** -- The `iss` (issuer), `aud` (audience), and `exp` (expiry) claims are validated.

The configured OIDC path fails closed when signature or claim validation fails.
The legacy provider-specific callback can still use `/userinfo` for opaque
access tokens when the canonical `OIDC_*` settings are not enabled.

### OIDC-to-dashboard principal mapping

After verification, the callback resolves the provider and `sub` pair through
`external_auth_identities`, creates a local user when needed, and returns the
same UUID-backed access token used by password and social OAuth login. Provider
role claims are normalized for legacy compatibility but are not authorization
input. Audit authorization always reloads `users.roles` from the database.

New users, including SSO and localhost-bootstrap users, receive only `VIEWER`.
MUTX has no automatic admin promotion or self-service role assignment; a
privileged role must be assigned explicitly through a controlled database
administration process. A database role update or revocation applies on the
next request, without waiting for the access token to expire.

The compatibility OIDC normalizer can extract claims from these locations:

- `roles`
- `groups`
- `custom:roles`
- `realm_access.roles` (Keycloak)
- `resource_access.roles` (Keycloak)

See `src/api/auth/oidc.py` for validation and claim normalization,
`src/api/services/auth.py` for external identity resolution, and
`src/api/auth/dependencies.py` for the database-backed role dependency.

## Token Lifetimes

Access and refresh token lifetimes are server-configured in `src/api/auth/jwt.py` and settings.

Use the returned `expires_in` value instead of hardcoding assumptions in clients or docs.
