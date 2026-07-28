# Platform Overview

MUTX is a source-available control plane for operating AI agents with clearer boundaries than a demo app.

Today the repo exposes a supported marketing site, a supported authenticated dashboard, and a separate simulated control demo. Understanding that split is the fastest way to orient yourself.

For a detailed surface matrix, see [Surface Matrix](surfaces.md).

## The public surfaces

### `mutx.dev`

`mutx.dev` is the public marketing site.

What it does today:

- explains the product thesis
- links people to the docs and GitHub repo
- publishes the desktop download flow
- points operators toward the supported dashboard and CLI install lanes

What it is not:

- not the canonical API reference
- not the authenticated operator dashboard
- not the source of truth for route behavior

The landing page currently lives in `app/page.tsx`.

### `mutx.dev/docs`

`mutx.dev/docs` is the canonical documentation surface.

It should answer three questions clearly:

1. what exists now
2. how to get started
3. how the marketing site, docs, and app relate

In repo terms, the docs source currently lives under `docs/`.

### `app.mutx.dev`

`app.mutx.dev` is the operator-facing app host.

What exists today:

- login and register browser flows via `app/api/auth/*`
- current-user lookup via `app/api/auth/me`
- supported dashboard pages under `app/dashboard/*` for agents, deployments, documents, reasoning, runs, execution history, sessions, observability, approvals, audit, budgets, monitoring, webhooks, security, orchestration, memory, channels, templates, notifications, standup, skills, and local autonomy
- a compatibility redirect from `/dashboard/spawn` to agent creation
- same-origin dashboard and control-plane proxies under `app/api/dashboard/*`, `app/api/agents/*`, `app/api/deployments/*`, `app/api/api-keys/*`, and `app/api/webhooks/*`
- a catch-all control demo rendered from `app/control/[[...slug]]/page.tsx`

Operational boundaries:

- optional providers and machine-local integrations report unavailable or degraded state when they are not configured
- provider-side infrastructure rollout remains separate from mutating a control-plane deployment record
- direct API and CLI usage remain first-class automation paths alongside the dashboard

## Product model right now

MUTX already has real control-plane primitives:

- authentication
- templates and assistant workflows
- agents
- deployments
- runs and traces
- sessions
- budgets and monitoring
- API keys
- ingest routes
- webhook registration and delivery history
- health and readiness routes

The docs should describe those primitives as they exist today, not as a future ideal.

## Source-of-truth map

Use these directories when checking claims:

| Source | Trust it for |
| --- | --- |
| `app/page.tsx` | public landing site content and calls-to-action |
| `app/dashboard/` | current operator dashboard routes and positioning |
| `app/control/[[...slug]]/page.tsx` | current demo shell positioning |
| `app/api/` | browser-facing same-origin proxy routes |
| `src/api/routes/` | backend route contracts |
| `docs/api/openapi.json` | generated API contract snapshot |
| `docs/project-status.md` | current-state maturity framing |

## Canonical rule

If a route, screen, or workflow cannot be traced to code in this repo, do not present it as live product truth.
