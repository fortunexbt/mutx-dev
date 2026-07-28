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

After backend routes settle, refresh both committed contract artifacts in one pass:

```bash
PYTHON_BIN=.venv/bin/python npm run generate:contracts
```

The generator derives security per operation from FastAPI route dependencies and
the application-level managed-key middleware contract. It keeps public
operations anonymous, distinguishes Bearer from `X-API-Key` alternatives, and
preserves explicit operation-level security overrides. It also uses FastAPI's
shared validation shape for response wrappers whose Pydantic serializer only
sanitizes values; this prevents those structured models from degrading to `{}`
and `unknown` in generated clients. Computed response fields remain read-only.

Quick route inventory check:

```bash
jq -r '.paths | keys[]' docs/api/openapi.json | sort
```

## Hosted Surfaces

- Marketing site: `https://mutx.dev`
- Docs site: `https://mutx.dev/docs`
- Operator app: `https://app.mutx.dev`
- Direct API base: `https://api.mutx.dev`

## Route Inventory

All registered control-plane routers mount under `/v1/*` via the route registries
in `src/api/main.py`; operational probes remain at the root. The separately
registered `audit` router mounts at `/v1/audit` and requires persisted `ADMIN` or
`AUDIT_ADMIN`.

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
| `security` | `/v1/security` | — |
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
| `governance_supervision` | `/v1/runtime/governance/supervised` | — |
| `policies` | `/v1/policies` | — |
| `approvals` | `/v1/approvals` | [approvals.md](./approvals.md) |
| `audit` (private) | `/v1/audit` | — |

## Reference Artifacts

- API overview: [index.md](./index.md)
- OpenAPI JSON: [`openapi.json`](https://github.com/mutx-dev/mutx-dev/blob/main/docs/api/openapi.json)
- Authentication: [authentication.md](./authentication.md)
- API keys: [api-keys.md](./api-keys.md)
- Agents: [agents.md](./agents.md)
- Analytics: [analytics.md](./analytics.md)
- Approvals: [approvals.md](./approvals.md)
- Deployments: [deployments.md](./deployments.md)
- Webhooks and ingestion: [webhooks.md](./webhooks.md)
- Leads: [leads.md](./leads.md)

## Publication Rules

- GitHub is the canonical source for `README.md`, `SUMMARY.md`, and `docs/api/*`.
- GitBook should import from GitHub first when sync is reconnected.
- Do not create replacement README pages from the GitBook UI.
