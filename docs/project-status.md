---
description: Capability matrix, biggest gaps, and highest-leverage next tasks.
icon: chart-line
---

# Project Status

This matrix tracks the current repo state and where contributors can help next.

## Capability Matrix

| Area         | Current state                                                       | Biggest gaps                                                                                                                                     | Contributor-ready work                                                               |
| ------------ | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Web          | public site, authenticated dashboard, PicoMUTX, docs, desktop handoff, and an isolated `/control/*` simulation exist in Next.js | a repository build does not prove hosted availability or configured external providers | browser regression coverage, accessibility checks, keep simulation and live-data boundaries honest |
| API          | `/v1/*` routes cover owned agents, runs, deployment records, usage, governance, and other control-plane resources; route dependencies enforce authentication, ownership, or explicit roles where declared | RAG is optional and disabled by default; the scheduler is internal, tenant-owned, and database-backed with leased execution claims; governed tool policy covers the MUTX runtime dispatch path, not uninstrumented external agents | typed response polish, lifecycle tests, authorization inventory, OpenAPI auth accuracy |
| CLI          | grouped `auth`, `agent`, `deployment`, `assistant`, `runtime`, `setup`, `governance`, and `observability` commands plus compatibility aliases | Faramesh governance depends on an installed, operator-managed local daemon; some aliases still add docs burden | streamline help/docs, keep setup truthful, tighten command coverage |
| SDK          | sync clients, runtime heartbeat/metric reporting, adapters, and opt-in guardrail middleware exist | traces contain only callbacks an integration observes and submits; `MutxAsyncClient` remains limited | async contract coverage, supported-method matrix, instrumentation docs |
| Infra        | Docker, Terraform, Ansible, Railway manifests, Kubernetes/Helm, and monitoring configuration exist | checked-in configuration and validation are not proof of a rollout; provider credentials, secrets, and production reconciliation remain operator-owned | infra docs cleanup, deployment verification boundaries, Vault and secret-backend clarity |
| Tests and CI | API, CLI, frontend, observability, docs, and release-contract checks exist | signing/notarization requires real Apple credentials, and no source-only check proves a complete public desktop asset set or Railway rollout | route/OpenAPI drift checks, link checks, local-first validation, conditional artifact checks |
| Docs         | docs are now structured for GitBook and GitHub together; v1.4 release notes and release checklists through v1.5 exist | drift risk remains high whenever routes, app paths, or CLI groups move                                                                           | doc drift guardrails, GitBook sync rules, API reference upkeep                       |
| Autonomous   | autonomous dev lane shipped for agentic workflows | still early; coverage and reliability need real-world validation | autonomous flow coverage, reliability, docs alignment |

## Highest-Leverage Next Tasks

- keep route, CLI, SDK, and docs truth aligned around the live `/v1/*` contract
- keep live dashboard workflows, optional integration boundaries, and compatibility redirects aligned to the canonical route registry
- keep the desktop resolver conditional: offer downloads only when a complete remote artifact set is discovered; do not infer signing or notarization from filenames
- keep SDK async documentation honest until full async support is real
- keep generated per-operation OpenAPI security metadata aligned with route dependencies
- keep GitBook sync GitHub-first and stop GitBook-only README drift
- deepen role coverage and OIDC provider support without describing authentication as universal role enforcement

## Contribution Lanes

### `area:web`

- dashboard lifecycle and browser regression coverage
- better browser auth/session handling
- keep `/dashboard` and `/control` semantics clear

### `area:api`

- maintain the route-level authentication, ownership, internal-user, and role checks declared in source
- deeper runtime-backed lifecycle semantics
- preserve public, optional-auth, bearer, and `X-API-Key` alternatives in generated OpenAPI
- provider-backed deployment reconciliation and Vault integration completion

### `area:cli`

- keep grouped commands and compatibility aliases documented accurately
- improve auth ergonomics and setup recovery
- keep runtime import/resync flows honest

### `area:sdk`

- keep `/v1/*` behavior aligned to the server
- keep `MutxAsyncClient` deprecation and docs honest until async method coverage is real
- add a supported-method matrix with tests

### `area:testing`

- docs drift tests against real routes and OpenAPI
- backend route tests
- CLI and SDK contract tests

### `area:docs`

* keep examples aligned with real routes
* document supported, conditional, and simulated surfaces clearly (see [Surface Matrix](./surfaces.md))
* keep GitBook sidebar and repo docs in sync

For priority and sequencing, see `roadmap.md`.
