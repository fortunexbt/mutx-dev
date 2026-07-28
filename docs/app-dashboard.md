# App and Dashboard

This page documents the current truth of `app.mutx.dev`.

## Current role

`app.mutx.dev` is the operator-facing app host.

Right now it has two distinct browser roles:

- `/dashboard` is the authenticated operator shell; each panel's maturity depends on its same-origin proxy and upstream `/v1/*` contract
- `/control/*` is the browser demo shell for the control-plane story

## What exists today

### Auth flows

The app exposes browser-facing auth route handlers under `app/api/auth/`:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

Those handlers proxy to the FastAPI control plane and manage browser cookies for the web surface.

### Dashboard and resource proxies

The app exposes current resource routes such as:

- `GET /api/dashboard/agents`
- `GET /api/dashboard/agents/{agentId}`
- `GET /api/dashboard/deployments`
- `GET /api/dashboard/deployments/{id}`
- `GET /api/dashboard/runs`
- `GET /api/dashboard/runs/{runId}`
- `GET /api/dashboard/runs/{runId}/traces`
- `GET /api/dashboard/sessions`
- `GET /api/dashboard/swarms`
- `GET /api/dashboard/budgets`
- `GET /api/dashboard/monitoring/alerts`
- `GET /api/dashboard/assistant/overview`
- `GET /api/dashboard/health`
- `GET /api/api-keys`
- `POST /api/api-keys`
- `DELETE /api/api-keys/{id}`
- `POST /api/api-keys/{id}/rotate`
- `GET /api/webhooks`
- `POST /api/webhooks`
- `GET /api/agents`
- `POST /api/agents`
- `GET /api/deployments`
- `POST /api/deployments`

### Rendered shells

The dashboard shell publishes source-backed operator pages and keeps the simulated `/control/*` story in a separate route tree.

Pages with source-backed control-plane proxy contracts include:

- overview
- auth
- agents
- deployments
- runs and traces
- approvals and audit evidence
- sessions and swarms
- budgets and monitoring
- document and reasoning jobs when their feature flags and workers are configured
- skills and bundles as catalog/configuration records
- orchestration, retained memory, assistant channels, templates, notifications, and standup synthesis
- runtime security, analytics, observability, logs, and machine-local autonomy posture
- execution history backed by the live runs and traces APIs
- API keys
- webhooks

The compatibility entry point `/dashboard/spawn` redirects to agent creation. `/dashboard/history` is a first-class execution-history surface; `/dashboard/audit` remains the governance evidence ledger.

Release-oriented source contracts include:

- a composed `GET /api/dashboard/overview` route for the first-view dashboard contract
- CI gates for lint, typecheck, build, browser smoke, desktop checks, and signing/notarization validation when the required Apple credentials are present
- first-party desktop download routes at `mutx.dev/download/macos/*` that offer a handoff only when the resolver finds the complete expected GitHub artifact set
- explicit desktop lifecycle diagnostics for the UI server, bridge, runtime, control plane, and assistant binding
- grouped Essential and Full Mode navigation backed by one canonical route registry

The control demo is rendered from `app/control/[[...slug]]/page.tsx`.

## Important boundary

The app surface is not the canonical source for route contracts.

When describing behavior:

- trust `src/api/routes/` for backend semantics
- trust `app/api/` for browser proxy behavior
- trust the app shell for UX positioning only

## Domain split summary

| Surface | Main job |
| --- | --- |
| `mutx.dev` | public product narrative and entry point |
| `mutx.dev/releases` | public release summary and conditional artifact availability |
| `mutx.dev/docs` | canonical docs and API explanation |
| `app.mutx.dev/dashboard` | supported operator-facing authenticated shell for stable routes |
| `app.mutx.dev/control/*` | demo surface for the browser control-plane story |

## Operational boundaries

- the CLI and direct API remain the preferred interfaces for automation and bulk workflows
- RAG is implemented but opt-in and disabled by default; search/ingest durability depends on the configured vector store
- the internal scheduler stores tenant-owned tasks and execution outcomes in the database; each API worker may poll, while lease-token claims ensure only one worker executes a due task and expired claims are recoverable
- deployment actions update control-plane lifecycle records; applying and verifying provider state remains operator-owned
- repository tests can validate resolver, Railway manifest, and HTTP contracts, but they do not prove a Railway rollout or a published signed/notarized desktop asset set
- machine-local autonomy and assistant-provider surfaces report unavailable state when their host dependencies are absent
- `/control/*` remains explicitly simulated and never presents its sample records as operator state

These boundaries are exposed in the UI so an unavailable integration cannot look like an empty or successful live result.
