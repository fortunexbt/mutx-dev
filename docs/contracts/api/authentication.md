---
description: Compatibility page pointing to the canonical auth docs.
icon: lock
---

# Legacy Authentication Link

Use the canonical page in [`../../api/authentication.md`](../../api/authentication.md).

## Current Truth

- auth routes live under `/v1/auth/*`
- `login`, `refresh`, and `local-bootstrap` return token pairs
- `register` returns a token pair only when email verification is disabled; the secure default returns no tokens until the address is verified
- token lifetimes are server-configured, so clients should trust `expires_in`

Canonical auth endpoints:

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `GET /v1/auth/me`

```bash
BASE_URL=http://localhost:8000

curl "$BASE_URL/v1/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Canonical Page

- [Authentication](../../api/authentication.md)
