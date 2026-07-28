---
description: Source-backed support matrix for MUTX product surfaces.
icon: layered-shapes
---

# Surface Matrix

This document maps MUTX surfaces to their source-backed maturity. These labels describe repository contracts; hosted availability and provider rollout require separate verification.

## The Public Surfaces

| Surface | URL | Role | Status |
| ------- | --- | ---- | ------ |
| Marketing | [mutx.dev](https://mutx.dev) | Public product narrative, release summary, docs, and desktop/download entry point | **Supported** |
| PicoMUTX | [pico.mutx.dev](https://pico.mutx.dev) | Guided onboarding, academy, tutor, support, and runtime-aware operator workflows | **Supported** |
| Release summary | [mutx.dev/releases](https://mutx.dev/releases) | Release notes plus a resolver that exposes desktop assets only when a complete remote set is found | **Conditional** |
| Desktop download lane | [mutx.dev/download/macos](https://mutx.dev/download/macos) | macOS handoff that remains unavailable when the expected remote artifact set is incomplete | **Conditional** |
| Documentation | [mutx.dev/docs](https://mutx.dev/docs) | Canonical self-hosted docs, API reference, and operator guides | **Supported** |
| Operator dashboard | [app.mutx.dev/dashboard](https://app.mutx.dev/dashboard) | Authenticated operator shell for stable dashboard routes | **Supported** |
| Control demo | [app.mutx.dev/control](https://app.mutx.dev/control) | Deliberately isolated browser demonstration of the control-plane story | **Demonstration** |

## Status Definitions

### Supported

Surfaces marked **Supported** have:

- an implemented source path with a maintained repository contract
- focused tests or validation appropriate to that path
- documentation that identifies its source of truth

`Supported` does not, by itself, prove that a public domain is reachable or that a deployment provider applied the current commit.

### Conditional

Surfaces marked **Conditional** have a supported code path but require external evidence before the user action is offered. The desktop lane, for example, requires the resolver to find the complete expected GitHub asset set. Repository source does not prove that such an asset set currently exists, or that its contents are signed and notarized.

### Demonstration

Surfaces marked **Demonstration** are:

- intentionally non-production examples rather than operator state
- isolated from the supported dashboard so sample records cannot look live
- labeled as demonstrations anywhere a user can enter them

## Detailed Breakdown

### mutx.dev (Supported)

**What it does:**
- Explains the product thesis and value proposition
- Links to documentation and GitHub repository
- Publishes the release summary at `/releases`
- Publishes a conditional desktop handoff at `/download/macos`
- Links operators into the dashboard and CLI lanes

**What it is not:**
- The canonical API reference (see mutx.dev/docs)
- The authenticated operator dashboard (see app.mutx.dev/dashboard)
- The source of truth for route behavior

**Source of truth:** `app/page.tsx`

---

### pico.mutx.dev (Supported)

**What it does today:**
- Provides the PicoMUTX landing page and onboarding-first workspace
- Ships the academy, lesson pages, grounded tutor, support lane, and runtime-aware Autopilot bridge
- Reuses existing MUTX dashboard signals for runs, budget, alerts, and approvals when authenticated
- Keeps account recovery, verification, locale, and session continuity on the correct host

**Operational boundaries:**
- Tutor provider validation and generation require a configured provider and model
- Autopilot distinguishes a local operator preference from a server-enforced runtime gate
- Checkout availability depends on configured billing credentials; the UI reports unavailable configuration instead of inventing success

**Source of truth:** `app/pico/`, `components/pico/`, `lib/pico/`

---

### mutx.dev/docs (Supported)

**What it does:**
- Provides canonical API documentation
- Offers quickstart and deployment guides
- Explains platform architecture and security
- Documents troubleshooting and FAQs

**What it is not:**
- A functional app or dashboard
- A replacement for direct API/CLI usage when needed

**Source of truth:** `docs/`

### app.mutx.dev/dashboard (Supported)

**What it does today:**
- Browser-facing auth flows (`/api/auth/*`)
- Authenticated dashboard pages under `/dashboard` for agents, deployments, documents, reasoning, runs, approvals, audit, sessions, budgets, monitoring, observability, security, orchestration, memory, channels, templates, notifications, standup, skills, API keys, webhooks, and local autonomy posture
- Same-origin dashboard proxies for those control-plane resources
- Composed overview contract under `/api/dashboard/overview` for the first viewport
- Onboarding flow for desktop app

**Operational boundaries:**
- Some flows remain CLI-first or API-first
- RAG exposes embed, search, ingest, and health paths only when `ENABLE_RAG_API` is enabled; it is disabled by default. Collections and documents are tenant-owned and database-backed. Ingest enforces 64-collection, 10,000-document, and 256 MiB logical-storage safety ceilings per tenant; exhaustive similarity search refuses collections above 2,000 documents until indexed vector search is available.
- The internal scheduler exposes tenant-scoped CRUD for log, webhook, and agent-heartbeat tasks. Tasks, counters, errors, due times, and execution leases are durable; conditional database claims coordinate multiple workers and recover expired claims.
- Full Mode is an explicit plan/capability boundary; the shell provides an actionable upgrade or configuration path when unavailable
- Deployment actions update control-plane lifecycle records; provider-side rollout verification remains operator-owned

**Source of truth:** `app/dashboard/`, `app/control/`, `app/api/`

### app.mutx.dev/control (Demonstration)

**What it does today:**
- Preserves an isolated sample shell for the control-plane story
- Demonstrates routing, narrative, and sample-specific layout patterns without claiming its records are live

**What it is not:**
- Not the supported dashboard lane
- Not the source of truth for stable operator workflows
- Not an operator state surface

## Quick Reference

| Need | Surface | Status |
|------|---------|--------|
| Learn about MUTX | mutx.dev | Supported |
| Check release notes and desktop asset availability | mutx.dev/releases | Conditional |
| Check whether a Mac download is available | mutx.dev/download/macos | Conditional |
| Understand APIs and integration | mutx.dev/docs | Supported |
| Build on MUTX programmatically | mutx.dev/docs + API | Supported |
| UI-based operator workflows | app.mutx.dev/dashboard | Supported |
| Agent run observability | app.mutx.dev/dashboard/observability | Supported |
| Browser control-plane demo | app.mutx.dev/control/* | Demonstration |
| Agent governance (Faramesh) | `mutx governance` CLI | Conditional on a configured daemon |

### Governance (Faramesh)

MUTX has two governance paths with different scope. The in-process governance runtime evaluates tools dispatched by `src/api/services/agent_runtime.py`. The Faramesh CLI path is conditional on an installed, operator-managed local daemon.

**What it does today:**
- The MUTX runtime evaluates normalized tool calls before invoking registered handlers and records governed decisions
- Authenticated API routes enforce ownership or explicit privileged roles where their dependencies declare them
- Faramesh CLI commands inspect and submit decisions when the local daemon is installed and reachable
- Runtime status and metrics endpoints report the local Faramesh integration state
- Governance, credential, supervision, and approval contracts are available through API and CLI surfaces

**What is not yet:**
- Automatic interception of uninstrumented external agent actions
- Automatic resume of a deferred tool call after a REST approval decision
- Policy editor UI in dashboard
- A hosted credential broker or proof that any external secret provider is configured

**Source of truth:** `src/api/services/agent_runtime.py`, `src/api/services/governance_runtime.py`, `src/security/`, `cli/faramesh_runtime.py`, `cli/commands/governance.py`

## Contributing

When adding features or documenting new capabilities:

1. Identify which surface the work belongs to
2. Document the maturity level honestly
3. Update this matrix if surface status changes
4. Label conditional dependencies and demonstration-only data at every entry point

For current project status and contributor lanes, see [Project Status](./project-status.md).
