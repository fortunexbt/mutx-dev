---
description: Current implementation priorities grounded in code, OpenAPI, and tests.
icon: road
---

# Roadmap

This roadmap is intentionally short and grounded in the code that exists today.

It is a guide for contributors, not a promise of exact delivery order.

## Principles

- Prefer current-state honesty over target-state marketing.
- Fix contracts before adding more surface area.
- Land small, reviewable slices.
- Update docs when behavior changes.
- Keep GitBook rendering downstream from repo truth, not beside it.

## Now

- Runtime and dependency modernization (`#3688`)
  - align React 19.2 with the Next.js 16 runtime and keep the dependency tree peer-valid
  - migrate Tailwind 3 to 4 and Electron 39 to 43 as separate, fully tested compatibility waves
  - move the supported Python baseline forward deliberately, then replace abandoned auth/cloud clients
  - refresh OpenTelemetry exporters and remove the retired Jaeger exporter without breaking trace contracts
- API, CLI, SDK, and docs contract alignment
  - keep every public example aligned with the mounted `/v1/*` contract
  - keep grouped CLI commands and compatibility aliases documented accurately
  - keep SDK async support honest while `MutxAsyncClient` remains limited
- Dashboard product integrity
  - keep `/dashboard` as the canonical operator surface
  - keep `/control/*` clearly marked as the demo shell
  - keep every published panel tied to a live proxy, explicit capability boundary, and browser regression contract
- Docs drift and GitBook stability
  - keep `README.md` and `SUMMARY.md` repo-owned
  - preserve the current GitBook sidebar feel while removing sync-poisoning pages
  - make docs drift tests catch broken links, dead paths, and stale route claims
- Backend hardening
  - continue tightening ownership and auth enforcement across user-scoped resources
  - keep deployment lifecycle history, versions, and rollback semantics honest and tested
- Optional and operator-integrated subsystems
  - replace the internal scheduler's process-local store before treating it as durable or multi-instance scheduling
  - keep RAG explicitly opt-in (`ENABLE_RAG_API=false` by default); document OpenAI and deterministic local embedding modes plus vector-store persistence requirements
  - keep Vault and provider credential support configuration-dependent until an end-to-end deployment proves the integration
  - connect deployment desired-state records to provider rollouts without treating record mutation as deployment completion

## Next

- Pico product contract follow-through
  - keep `/pico` as the onboarding-first landing and preserve direct paths into onboarding, Academy, Tutor, Support, Autopilot, and live pricing
  - keep Jest and Playwright contracts honest as the premium Pico surface evolves
- Local operator ergonomics
  - keep the hosted and local setup lanes recoverable when installs, migrations, or stale local state drift
  - reduce false local verification signals from worktree server reuse and stale standalone builds

## Later

- Quotas and plan enforcement beyond the current foundations
- Deeper run and trace workflows
- Expanded runtime support beyond the current OpenClaw-first path
- Broader tenant and secret-management hardening once Vault and deeper infra automation are real

## Implementation Milestones

- `2026-07-16` Unified site redesign now covers the public site, docs, dashboard, auth, desktop, and Pico surfaces
- `2026-07-16` Node 24 and the safe JavaScript dependency baseline are enforced across local, CI, and container builds
- `2026-07-16` LangChain is migrated to the v1 graph-backed agent runtime with current provider packages and no legacy compatibility layer
- `2026-07-16` OSS attribution and AARM claims are backed by immutable upstream source and license evidence
- `2026-04-14` Deployment lifecycle events, version records, and record-level rollback became available across API-facing operator surfaces; provider rollout remains separate
- `2026-04-14` Pico now uses the premium studio surface across onboarding, academy, tutor, autopilot, and support
- `2026-04-14` Dashboard observability aggregates telemetry config, traces, and session health into `/dashboard/observability`
- `2026-04-14` Webhook and API-key lifecycle status is unified across dashboard and CLI operator surfaces
- `2026-04-11` Pico progress API mounted at `/v1/pico/progress` with GET/POST progress persistence
- `2026-04-10` Swarms real DB persistence with PATCH/DELETE endpoints
- `2026-04-10` Opt-in RAG `/v1/rag/ingest` added for configured vector-store ingestion
- `2026-04-10` Sessions local discovery (Claude/Codex/Hermes auto-detection)
- `2026-04-10` Internal scheduler gained asyncio CRUD and log, webhook, and agent-heartbeat execution; state remains process-local
- `2026-04-10` Opt-in RAG gained embed/search paths with OpenAI or deterministic local embeddings
- `2026-04-11` OpenAPI spec: 29 route prefixes, 181 endpoint-method pairs
- `2026-04-09` Route-level authentication, ownership, internal-user, and explicit role dependencies were expanded
- `2026-04-09` OIDC token validation at `src/api/auth/oidc.py`
- `2026-04-09` Kubernetes/Helm chart in `infrastructure/helm/`
- `2026-04-09` Self-hosted docs platform at `mutx.dev/docs`
- `2026-04-09` Autonomous dev lane for agentic workflows
- `2026-04-09` Adapter hardening across SDK adapters
- `2026-04-09` Security hardening across auth and API layers
- `2026-03-22` Prepare `v1.1` and CLI `0.2.1` release
- `2026-03-22` Fix local demo bootstrap and migration flow
- `2026-03-21` Simplify quickstart and bootstrap the localhost lane from docs truth
- `2026-03-21` Stabilize control and live route surfaces for the dashboard
- `2026-03-21` Add OpenClaw import flow, provider wizard, runtime tracking, and suspended handoff
- `2026-03-20` Build the public browser control-plane demo and rename stale internal app routes
- `2026-03-20` Simplify installer handoff and bootstrap local operator auth
- `2026-03-19` Add one-command TUI bootstrap and operator packaging work
- `2026-03-19` Enforce ownership on all agent endpoints
- `2026-03-19` Make `/dashboard` the canonical operator surface and collapse stale app routes

## Contributor-Ready Lanes

- `area:docs`
  - keep commands and route examples aligned with the code
  - keep GitBook sync GitHub-first and repo-owned
- `area:api`
  - route auth, ownership, typed schemas, placeholder reduction, and tests
- `area:cli`
  - setup ergonomics, grouped command docs, config overrides, and auth ergonomics
- `area:sdk`
  - align defaults and supported methods to the real server contract
  - keep async support and docs honest
- `area:web`
  - deepen the dashboard without blurring the line between live UI and demo UI
- `area:testing`
  - backend tests, docs drift checks, local-first Playwright, and CI sanity checks

## Where To Look Next

- Current capability matrix: `project-status.md`
- Setup and workflows: `README.md`
- Contribution process: `CONTRIBUTING.md`
