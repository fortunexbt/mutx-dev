# Analytics

The `/v1/analytics/*` surface provides usage summaries, cost tracking, timeseries data, and per-agent metrics.

All endpoints require a persisted user role. Summary, per-agent, timeseries,
cost, and budget reads allow `VIEWER` or `DEVELOPER`; revenue, subscription, and
payment-administration routes require `ADMIN`, a verified email, and an allowed
internal email domain. A user access token or managed API key may authenticate
the request through `Authorization: Bearer ...`; managed API keys also work
through `X-API-Key`. User-facing results are scoped to the authenticated user's
owned resources.

## Routes

| Route | Purpose |
| --- | --- |
| `GET /v1/analytics/summary` | Aggregate dashboard summary |
| `GET /v1/analytics/agents/{agent_id}/summary` | Per-agent metrics summary |
| `GET /v1/analytics/timeseries` | Bucketed timeseries for runs, API calls, or latency |
| `GET /v1/analytics/costs` | Credit usage breakdown by event type and agent |
| `GET /v1/analytics/budget` | Current billing period budget and remaining credits |
| `GET /v1/analytics/revenue` | Internal revenue overview (`ADMIN` plus internal-user check) |
| `GET /v1/analytics/subscriptions` | Internal subscription list (`ADMIN` plus internal-user check) |
| `GET /v1/analytics/payments` | Internal payment list (`ADMIN` plus internal-user check) |

## Period Parameters

Most endpoints accept `period_start` and `period_end` query parameters:

- **Shorthand values**: `24h`, `7d`, `30d` — relative to now
- **ISO 8601 strings**: `2026-04-01T00:00:00Z`
- **Defaults**: `period_start` defaults to 30 days ago; `period_end` defaults to now

## Summary

```bash
BASE_URL=http://localhost:8000

curl "$BASE_URL/v1/analytics/summary?period_start=7d" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Response fields:

- `total_agents` — total owned agents
- `active_agents` — agents in `running` status
- `total_deployments` — total deployments across all agents
- `active_deployments` — deployments in `running`, `ready`, or `deploying`
- `total_runs` — agent runs in the period
- `successful_runs` — runs with `completed` status
- `failed_runs` — runs with `failed` status
- `total_api_calls` — API call usage events in the period
- `avg_latency_ms` — average system latency across owned agents
- `period_start`, `period_end` — resolved period boundaries

## Per-Agent Summary

```bash
curl "$BASE_URL/v1/analytics/agents/YOUR_AGENT_ID/summary?period_start=24h" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Returns:

- `agent_id`, `agent_name`
- `total_runs`, `successful_runs`, `failed_runs`
- `avg_cpu`, `avg_memory` — from runtime metric reports
- `total_requests`, `avg_latency_ms` — from system metrics
- `period_start`, `period_end`

## Timeseries

```bash
curl "$BASE_URL/v1/analytics/timeseries?metric=runs&interval=hour&period_start=24h" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl "$BASE_URL/v1/analytics/timeseries?metric=latency&interval=day&period_start=7d" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

curl "$BASE_URL/v1/analytics/timeseries?metric=api_calls&interval=day&agent_id=YOUR_AGENT_ID" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Required parameters:

- `metric` — one of `runs`, `api_calls`, `latency`

Optional parameters:

- `interval` — `hour` or `day` (default: `hour`)
- `period_start`, `period_end` — standard period parameters
- `agent_id` — scope to a single agent

Response:

- `metric` — the requested metric name
- `interval` — the bucketing interval
- `data` — array of `{timestamp, value}` points
- `period_start`, `period_end`

## Cost Summary

```bash
curl "$BASE_URL/v1/analytics/costs?period_start=30d" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Returns:

- `total_credits_used` — sum of credits consumed in the period
- `credits_remaining` — plan credits minus usage
- `credits_total` — plan credit allowance
- `usage_by_event_type` — credit breakdown keyed by event type
- `usage_by_agent` — credit breakdown keyed by agent ID
- `period_start`, `period_end`

## Budget

```bash
curl "$BASE_URL/v1/analytics/budget" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Returns the current billing period status:

- `user_id`, `plan`
- `credits_total`, `credits_used`, `credits_remaining`
- `reset_date` — when credits reset
- `usage_percentage` — percentage of plan credits consumed
