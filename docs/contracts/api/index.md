---
description: Compatibility page pointing to the canonical API overview.
icon: circle-nodes
---

# Legacy API Overview Link

This page is retained so old links keep working.

Use the canonical overview in [`../../api/index.md`](../../api/index.md).

## Current Truth

- public control-plane routes are mounted under `/v1/*`
- root health routes remain at `/`, `/health`, `/ready`, and `/metrics`
- the generated OpenAPI snapshot lives at [`docs/api/openapi.json`](https://github.com/mutx-dev/mutx-dev/blob/main/docs/api/openapi.json)
- canonical auth endpoints include `POST /v1/auth/register`, `POST /v1/auth/login`, and `GET /v1/auth/me`

```bash
BASE_URL=http://localhost:8000

curl -X POST "$BASE_URL/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"operator@example.com","name":"Operator","password":"***"}'
```

## Canonical Pages

- [Overview](../../api/index.md)
- [Reference](../../api/reference.md)
- [Authentication](../../api/authentication.md)
- [Agents](../../api/agents.md)
- [Deployments](../../api/deployments.md)
- [Webhooks And Ingestion](../../api/webhooks.md)
- [Leads](../../api/leads.md)
