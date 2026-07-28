# API Keys

Managed API keys provide user-scoped automation auth without an interactive login flow.

New keys are issued with the `mutx_live_` prefix.

## Routes

| Route | Purpose |
| --- | --- |
| `GET /v1/api-keys` | List API keys, including revoked keys for audit history |
| `GET /v1/api-keys/{key_id}` | Fetch one API key record |
| `POST /v1/api-keys` | Create a new key |
| `POST /v1/api-keys/{key_id}/rotate` | Revoke the old key and issue a replacement |
| `DELETE /v1/api-keys/{key_id}` | Revoke a key while keeping its record |

## Authentication

Management calls use user auth.
Listing and detail reads accept `VIEWER` or `DEVELOPER`; create, rotate, and revoke
require `DEVELOPER`. `ADMIN` implicitly satisfies either role check.

For interactive docs examples, use a bearer access token:

```bash
-H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Issued managed keys can then be used against protected user-principal routes in
either of these forms:

```bash
curl -H "Authorization: Bearer mutx_live_your_key_here" \
  https://api.mutx.dev/v1/deployments

curl -H "X-API-Key: mutx_live_your_key_here" \
  https://api.mutx.dev/v1/webhooks/
```

Agent-runtime endpoints such as heartbeat and command polling use separately
issued `mutx_agent_...` credentials through the Bearer header.

## List API Keys

```bash
BASE_URL=http://localhost:8000

curl "$BASE_URL/v1/api-keys?skip=0&limit=50" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Example response:

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Dashboard automation",
      "last_used": null,
      "created_at": "2026-03-22T12:00:00Z",
      "expires_at": null,
      "is_active": true
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 50,
  "has_more": false
}
```

## Create A Key

```bash
curl -X POST "$BASE_URL/v1/api-keys" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CI deployer",
    "expires_in_days": 30
  }'
```

Example response:

```json
{
  "id": "uuid",
  "name": "CI deployer",
  "key": "mutx_live_abc123...",
  "created_at": "2026-03-22T12:00:00Z",
  "expires_at": "2026-04-21T12:00:00Z"
}
```

The plaintext `key` value is only returned once.

If the current plan has reached its active API key quota, create returns `409 Conflict`.

## Rotate A Key

```bash
curl -X POST "$BASE_URL/v1/api-keys/YOUR_KEY_ID/rotate" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Rotation revokes the current active key and returns a newly issued plaintext key once.

Rotating a revoked key returns `409 Conflict`.

## Revoke A Key

```bash
curl -X DELETE "$BASE_URL/v1/api-keys/YOUR_KEY_ID" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Successful revoke returns `204 No Content`.

The record remains visible in list responses for auditability.

## Operational Notes

- API key records currently expose `last_used`, `created_at`, `expires_at`, and `is_active`.
- Expiration is optional.
- The dashboard uses the same backend contract through its same-origin proxy routes under `app/api/api-keys/*`.
