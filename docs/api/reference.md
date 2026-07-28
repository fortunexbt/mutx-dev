# API Reference

This directory is the public API reference for MUTX.

It should always match the mounted FastAPI application, not older GitBook prose.

## Source Of Truth Order

When docs and implementation disagree, use this order:

1. `src/api/main.py` plus `src/api/routes/*.py`
2. `docs/api/openapi.json`
3. Prose docs in `docs/api/*.md`

## Refresh Generated Artifacts

Regenerate the OpenAPI snapshot from the live FastAPI app:

```bash
python scripts/generate_openapi.py
```

Regenerate the TypeScript types that power the app surface:

```bash
npm run generate-types
```

Quick route inventory check:

```bash
jq -r '.paths | keys[]' docs/api/openapi.json | sort
```

## Hosted Surfaces

- Marketing site: `https://mutx.dev`
- Docs site: `https://docs.mutx.dev`
- Operator app: `https://app.mutx.dev`
- Direct API base: `https://api.mutx.dev`

## Route Inventory

All public routes mount under `/v1/*` via `PUBLIC_ROUTE_REGISTRATIONS` in `src/api/main.py`.
The private `audit` route also mounts at `/v1/audit` but requires internal credentials.

| Route Group | Prefix | Has Docs? |
| --- | --- | --- |
| `agents` | `/v1/agents` | [agents.md](./agents.md) |
| `agent_runtime` | `/v1/agents` (runtime sub-paths) | — |
| `assistant` | `/v1/assistant` | — |
| `deployments` | `/v1/deployments` | [deployments.md](./deployments.md) |
| `templates` | `/v1/templates` | — |
| `webhooks` | `/v1/webhooks` | [webhooks.md](./webhooks.md) |
| `ingest` | `/v1/ingest` | (see webhooks.md) |
| `auth` | `/v1/auth` | [authentication.md](./authentication.md) |
| `clawhub` | `/v1/clawhub` | — |
| `api_keys` | `/v1/api-keys` | [api-keys.md](./api-keys.md) |
| `leads` | `/v1/leads` | [leads.md](./leads.md) |
| `runs` | `/v1/runs` | — |
| `documents` | `/v1/documents` | — |
| `reasoning` | `/v1/reasoning` | — |
| `observability` | `/v1/observability` | — |
| `security` | `/v1/security` | [mcp-security.md](./mcp-security.md) |
| `rag` | `/v1/rag` | — |
| `usage` | `/v1/usage` | — |
| `analytics` | `/v1/analytics` | [analytics.md](./analytics.md) |
| `monitoring` | `/v1/monitoring` | — |
| `onboarding` | `/v1/onboarding` | — |
| `pico` | `/v1/pico` | — |
| `runtime` | `/v1/runtime` | — |
| `scheduler` | `/v1/scheduler` | — |
| `sessions` | `/v1/sessions` | — |
| `swarms` | `/v1/swarms` | — |
| `telemetry` | `/v1/telemetry` | — |
| `budgets` | `/v1/budgets` | — |
| `governance_credentials` | `/v1/governance/credentials` | — |
| `governance_supervision` | `/v1/governance/supervision` | — |
| `policies` | `/v1/policies` | — |
| `approvals` | `/v1/approvals` | — |
| `audit` (private) | `/v1/audit` | — |

## Reference Artifacts

- API overview: [index.md](./index.md)
- OpenAPI JSON: [`openapi.json`](./openapi.json)
- Authentication: [authentication.md](./authentication.md)
- API keys: [api-keys.md](./api-keys.md)
- MCP definition scanning: [mcp-security.md](./mcp-security.md)
- Agents: [agents.md](./agents.md)
- Analytics: [analytics.md](./analytics.md)
- Deployments: [deployments.md](./deployments.md)
- Webhooks and ingestion: [webhooks.md](./webhooks.md)
- Leads: [leads.md](./leads.md)

## Publication Rules

- GitHub is the canonical source for `README.md`, `SUMMARY.md`, and `docs/api/*`.
- GitBook should import from GitHub first when sync is reconnected.
- Do not create replacement README pages from the GitBook UI.
