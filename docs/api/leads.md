# Leads

Lead capture is intentionally split between:

- a public create path for landing pages and onboarding
- authenticated administrator follow-up routes

The same handlers are mounted on both `/v1/leads` and `/v1/leads/contacts`.

## Access Rules

- `POST /v1/leads` and `POST /v1/leads/contacts` are public
- `GET`, `PATCH`, and `DELETE` routes require persisted `ADMIN`

## Routes

| Route | Purpose |
| --- | --- |
| `POST /v1/leads` | Capture a new lead |
| `GET /v1/leads` | List leads |
| `GET /v1/leads/{lead_id}` | Fetch one lead |
| `PATCH /v1/leads/{lead_id}` | Update one lead |
| `DELETE /v1/leads/{lead_id}` | Delete one lead |
| `POST /v1/leads/contacts` | Compatibility-shaped public capture route |
| `GET /v1/leads/contacts` | Compatibility-shaped list route |
| `GET /v1/leads/contacts/{lead_id}` | Compatibility-shaped detail route |
| `PATCH /v1/leads/contacts/{lead_id}` | Compatibility-shaped update route |
| `DELETE /v1/leads/contacts/{lead_id}` | Compatibility-shaped delete route |

## Capture A Lead

```bash
BASE_URL=http://localhost:8000

curl -X POST "$BASE_URL/v1/leads" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "founder@example.com",
    "name": "Founder",
    "company": "Example Co",
    "message": "Interested in migration support.",
    "source": "homepage"
  }'
```

Example response:

```json
{
  "id": "uuid",
  "email": "founder@example.com",
  "name": "Founder",
  "company": "Example Co",
  "message": "Interested in migration support.",
  "source": "homepage",
  "tier": null,
  "interest": null,
  "locale": null,
  "product_updates_consent": false,
  "notification_scheduled_at": null,
  "created_at": "2026-03-22T12:00:00Z",
  "success": true,
  "status": "accepted",
  "persisted": true,
  "replayed": false,
  "notification_scheduled": false,
  "follow_up": "unavailable",
  "message_to_submitter": "Your request was saved. Automated confirmation and team notification are best-effort and are not guaranteed."
}
```

The create handler normalizes email casing and trims optional text fields.

## List And Fetch Leads

```bash
curl "$BASE_URL/v1/leads?skip=0&limit=50" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl "$BASE_URL/v1/leads/YOUR_LEAD_ID" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Equivalent compatibility routes are also mounted under `/v1/leads/contacts`.

## Update And Delete

```bash
curl -X PATCH "$BASE_URL/v1/leads/YOUR_LEAD_ID" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "company": "Updated Co",
    "message": "Followed up with a live demo."
  }'

curl -X DELETE "$BASE_URL/v1/leads/YOUR_LEAD_ID" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

`PATCH` accepts any subset of:

- `email`
- `name`
- `company`
- `message`
- `source`
- `tier`
- `interest`
- `locale`
- `product_updates_consent`

An empty patch returns `400`.
