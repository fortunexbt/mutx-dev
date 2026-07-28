# API Overview

MUTX public control-plane routes are mounted under `/v1/*`.

Root operational probes remain at `/`, `/health`, `/ready`, and `/metrics`.

## Base URLs

- Local API: `http://localhost:8000`
- Hosted API: `https://api.mutx.dev`
- Browser proxy surface: `http://localhost:3000/api/*` locally and `https://app.mutx.dev/api/*` when hosted

## Source Of Truth

When prose and implementation disagree, use this order:

1. `src/api/main.py` router registration plus `src/api/routes/*.py`
2. [`openapi.json`](./openapi.json)
3. Markdown pages in `docs/api/*.md`

## Authentication Model

- Interactive user flows use `Authorization: Bearer ***
- Managed API keys can authenticate automation through `Authorization: Bearer *** or `X-API-Key: <mutx_live_...>`.
- `POST /v1/auth/local-bootstrap` is for localhost-only, non-production operator setup.

Canonical auth endpoints:

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `GET /v1/auth/me`

See [authentication.md](./authentication.md) and [api-keys.md](./api-keys.md) for details.

## Current Route Groups

| Group | Mounted routes |
| --- | --- |
| Auth | `/v1/auth/*` |
| Assistant | `/v1/assistant/*` |
| Agents | `/v1/agents`, `/v1/agents/{agent_id}/*`, runtime-compatible `/v1/agents/register`, `/v1/agents/heartbeat`, `/v1/agents/metrics`, `/v1/agents/logs`, `/v1/agents/commands*` |
| Approvals | `/v1/approvals/*` — request, approve, reject |
| Audit | `/v1/audit/*` — events and traces (private) |
| Deployments | `/v1/deployments`, `/v1/deployments/{deployment_id}/*` |
| API keys | `/v1/api-keys`, `/v1/api-keys/{key_id}`, `/v1/api-keys/{key_id}/rotate` |
| Webhooks | `/v1/webhooks/*` for outbound webhook management |
| Ingest | `/v1/ingest/agent-status`, `/v1/ingest/deployment`, `/v1/ingest/metrics` |
| Leads | `/v1/leads` plus compatibility-shaped `/v1/leads/contacts` |
| Observability | `/v1/observability/*` — runs, eval, provenance, status, steps |
| Policies | `/v1/policies/*` — CRUD and reload |
| Scheduler | `/v1/scheduler/*` — asyncio task engine with CRUD |
| Security | `/v1/security/*` — actions, approvals, compliance, MCP definition scanning, metrics, receipts, sessions |
| Telemetry | `/v1/telemetry/*` — config and health |
| Other public families | `/v1/analytics`, `/v1/budgets`, `/v1/clawhub`, `/v1/documents/*`, `/v1/governance/*`, `/v1/monitoring/*`, `/v1/onboarding/*`, `/v1/pico/*`, `/v1/rag/*`, `/v1/reasoning/*`, `/v1/runtime/*`, `/v1/sessions`, `/v1/swarms`, `/v1/templates`, `/v1/usage` |

## Browser And App Surface

The Next.js app exposes same-origin route handlers under `app/api/*` for browser-facing flows such as auth, dashboard reads and writes, API keys, webhooks, and leads.

Use the FastAPI routes directly for server-to-server integrations. Use `app/api/*` when you are operating inside the browser app surface.

## Generated Contract Artifacts

- OpenAPI snapshot: [`openapi.json`](./openapi.json)
- Generated TypeScript types: `app/types/api.ts`
- Refresh commands: see [reference.md](./reference.md)

## Related Pages

- [Authentication](./authentication.md)
- [API Keys](./api-keys.md)
- [Agents](./agents.md)
- [Deployments](./deployments.md)
- [MCP Definition Scanning](./mcp-security.md)
- [Webhooks And Ingestion](./webhooks.md)
- [Leads](./leads.md)
