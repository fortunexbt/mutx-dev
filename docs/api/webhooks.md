# Webhooks And Ingestion

MUTX has two adjacent webhook-related surfaces:

- outbound webhook management under `/v1/webhooks/*`
- runtime ingestion endpoints under `/v1/ingest/*`

## Webhook Management Routes

| Route | Purpose |
| --- | --- |
| `POST /v1/webhooks/` | Create a webhook destination |
| `GET /v1/webhooks/` | List webhook destinations |
| `GET /v1/webhooks/{webhook_id}` | Fetch one webhook |
| `PATCH /v1/webhooks/{webhook_id}` | Update URL, events, or active status |
| `DELETE /v1/webhooks/{webhook_id}` | Delete a webhook |
| `POST /v1/webhooks/{webhook_id}/test` | Send a test event |
| `GET /v1/webhooks/{webhook_id}/deliveries` | List delivery attempts |
| `POST /v1/webhooks/retry` | Retry one delivery by `delivery_id` |
| `GET /v1/webhooks/verify-docs` | Return signature-verification instructions |

## Ingest Routes

| Route | Purpose |
| --- | --- |
| `POST /v1/ingest/agent-status` | Runtime status ingestion |
| `POST /v1/ingest/deployment` | Deployment event ingestion |
| `POST /v1/ingest/metrics` | Metrics ingestion |
| `POST /v1/ingest/events` | Generic runtime event ingestion |

## Authentication

Webhook management and ingest routes accept either:

- `Authorization: Bearer <access_token or mutx_live key>`
- `X-API-Key: <mutx_live key>`

Webhook reads accept the API-key owner's persisted `VIEWER` or `DEVELOPER` role;
mutations, tests, retries, and ingest require `DEVELOPER`. `ADMIN` implicitly
satisfies these role checks.

## Create A Webhook

```bash
BASE_URL=http://localhost:8000

curl -X POST "$BASE_URL/v1/webhooks/" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/webhooks/mutx",
    "events": ["agent.*", "deployment.*"],
    "secret": "optional-secret",
    "is_active": true
  }'
```

Example response:

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "url": "https://example.com/webhooks/mutx",
  "events": ["agent.*", "deployment.*"],
  "secret": null,
  "has_secret": true,
  "is_active": true,
  "circuit_open": false,
  "consecutive_failures": 0,
  "created_at": "2026-03-22T12:00:00Z"
}
```

Webhook secrets are write-only. Responses never return the original secret value.

## List, Update, Delete, And Test

```bash
curl "$BASE_URL/v1/webhooks/?limit=50&skip=0" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl -X PATCH "$BASE_URL/v1/webhooks/YOUR_WEBHOOK_ID" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"events":["deployment.created"],"is_active":false}'

curl -X POST "$BASE_URL/v1/webhooks/YOUR_WEBHOOK_ID/test" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl -X DELETE "$BASE_URL/v1/webhooks/YOUR_WEBHOOK_ID" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

`test` returns a small success payload when delivery succeeds and `502` when the destination is unreachable or rejects the request.

## Delivery History

```bash
curl "$BASE_URL/v1/webhooks/YOUR_WEBHOOK_ID/deliveries?limit=20&success=false" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Delivery records expose:

- `id`
- `webhook_id`
- `event`
- `payload`
- `status_code`
- `success`
- `error_message`
- `attempts`
- `created_at`
- `delivered_at`

## Supported Event Values

Current outbound event values come from `src/api/services/webhook_handler.py`:

- `agent.status`
- `agent.status_update`
- `agent.heartbeat`
- `agent.error`
- `agent.started`
- `agent.stopped`
- `agent.crashed`
- `deployment.created`
- `deployment.updated`
- `deployment.failed`
- `deployment.rolled_back`
- `metrics.report`
- `health.check`

Route validation also accepts:

- `*`
- wildcard families such as `agent.*`, `deployment.*`, and `metrics.*`

## Signature Header

When a webhook has a secret, outbound deliveries include:

```text
X-Webhook-Signature: sha256=<digest>
```

## Retry Behavior

The current delivery service makes at most five attempts for retryable failures.
The four waits are based on 30 seconds, 5 minutes, 30 minutes, and 2 hours, each
with ±20% jitter. Non-retryable responses stop the sequence immediately; five
consecutive failed deliveries open the webhook circuit breaker.

Webhook destinations must use HTTPS on port 443 and resolve to a public address.
Loopback, private, link-local, documentation, multicast, and other non-public
networks are rejected.

## Ingest Notes

The ingest routes are for MUTX runtime updates entering the control plane, not for user-managed outbound webhooks.

Use the source-controlled [`openapi.json`](https://github.com/mutx-dev/mutx-dev/blob/main/docs/api/openapi.json) for the exact ingestion payloads.
