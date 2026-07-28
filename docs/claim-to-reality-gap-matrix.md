# MUTX Claim-to-Reality Gap Matrix
**Audit Date:** 2026-07-28
**Repo:** current checkout
**Scope:** public product, API contract, authorization, and generated artifacts
**Contract snapshot:** 33 top-level `/v1` families, 198 paths, 246 operations

---

## 1. Claim vs Reality Table

### 1.1 README Claims

| Claim | Source | Reality | Status |
|-------|--------|---------|--------|
| "FastAPI control plane with public routes mounted under `/v1/*`\" | README.md | TRUE — 33 top-level `/v1` families, 198 paths, and 246 operations in the generated OpenAPI snapshot | SHIPPED |
| "route groups for auth, agents, deployments, API keys, webhooks, newsletter, health, and readiness" | historical README wording | Auth ✓, Agents ✓, Deployments ✓, API Keys ✓, Webhooks ✓. Newsletter is deliberately unmounted; `/v1/leads` is active. Health probes are root `/`, `/health`, and `/ready`, not `/v1/*`. | CORRECTED |
| "route groups for templates, sessions, runs, usage, api-keys, webhooks, monitoring, budgets, rag, clawhub, runtime, analytics, onboarding, swarms, and leads" | README.md | ALL confirmed in OpenAPI as of v1.4+: templates ✓, sessions ✓, runs ✓, usage ✓, api-keys ✓, webhooks ✓, monitoring ✓, budgets ✓, rag ✓, clawhub ✓, runtime ✓, analytics ✓, onboarding ✓, swarms ✓, leads ✓ | SHIPPED |
| "a Python CLI and first-party Textual TUI" | README.md | `cli/` exists with Click-based commands. `mutx tui` referenced in docs. TUI shell exists. | SHIPPED |
| "local-first setup and bootstrap flows for hosted and localhost operators" | README.md | `mutx setup hosted` and `mutx setup local` confirmed in CLI code | SHIPPED |
| "`~/.mutx/config.json` stores auth state" | README.md | Hardcoded path `~/.mutx/config.json` confirmed in autonomy scripts | SHIPPED |
| "installer at mutx.dev/install.sh" | README.md | Referenced; also `brew tap mutx-dev/homebrew-tap && brew install mutx` | SHIPPED |
| "local dev stack with `make dev-up`" | README.md | `make dev-up` confirmed; `./dev.sh` also available | SHIPPED |
| "Docker, Terraform, Ansible, Railway, and monitoring assets exist" | README.md | Docker Compose confirmed. Terraform/Ansible/Helm exist in `infrastructure/`. Monitoring configs present. | SHIPPED |
| "Helm (k8s)" | README.md | `infrastructure/helm/` confirmed | SHIPPED |

### 1.2 Whitepaper Claims

| Claim | Source | Reality | Status |
|-------|--------|---------|--------|
| "FastAPI control plane with route groups: `/v1/auth`, `/v1/agents`, `/v1/deployments`, `/v1/api-keys`, `/v1/webhooks`, `/v1/newsletter`, `/v1/health`, `/v1/ready`" | historical whitepaper wording | Corrected: newsletter is unmounted, `/v1/leads` is active, and health/readiness remain root probes. | CORRECTED |
| "Additional `/v1/*` surfaces: templates, assistant, sessions, runs, monitoring, budgets, rag, and runtime" | whitepaper.md §6.1 | ALL now confirmed in OpenAPI: templates ✓, assistant ✓, sessions ✓, runs ✓, monitoring ✓, budgets ✓, rag ✓, runtime ✓ | SHIPPED |
| "control-plane record model for agents and deployments" | whitepaper.md §8 | Database models confirmed. Routes are live with real DB-backed operations. | SHIPPED |
| "agent status values: creating, running, stopped, failed, deleting" | whitepaper.md §8.1 | Modeled in code; agent lifecycle routes support status transitions | SHIPPED |
| "Observability: /health, /ready, deployment logs and metrics routes, agent logs and metrics routes, webhook ingestion endpoints, monitoring configs" | whitepaper.md §10 | `/health` and `/ready` confirmed. Agent/deployment logs+metrics in OpenAPI. Webhook ingestion exists. Monitoring routes (`/v1/monitoring/*`) now in OpenAPI. Telemetry config at `/v1/telemetry/*` | SHIPPED |
| "Infrastructure: Railway + Docker, Terraform + Ansible, Prometheus + Grafana" | whitepaper.md §11 | Docker Compose confirmed. Terraform/Ansible/Helm in `infrastructure/`. Railway deploy notifications confirmed (Discord on cold start). | PARTIAL |
| "Vault integration" mentioned as infrastructure | whitepaper.md | The credential broker has a Vault provider for an externally configured service. The Terraform Vault module is still a placeholder and no checked-in config proves a live backend. | PARTIAL |

### 1.3 project-status.md Claims

| Claim | Source | Reality | Status |
|-------|--------|---------|--------|
| "RAG search and scheduler return 503 with feature flags until runtime is configured" | project-status.md | RAG now has real `/v1/rag/embed`, `/v1/rag/embed/batch`, `/v1/rag/search` endpoints (gated by `enable_rag_api` setting). Scheduler has a real asyncio task engine with CRUD. No longer 503 stubs. | **CHANGED → SHIPPED** |
| "`MutxAsyncClient` remains limited and must stay explicitly documented as such" | project-status.md | SDK async contract exists; 20+ contract test modules added in v1.4 | PARTIAL |
| "provider credentials and Vault support remain configuration-dependent" | project-status.md | Confirmed — broker adapters exist, but external backend provisioning and end-to-end rollout evidence remain operator-owned | PARTIAL |
| "CLI grouped commands: auth, agent, deployment, assistant, runtime, setup, governance, and observability" | project-status.md | Governance CLI (`mutx governance`) confirmed. Other groups exist in `cli/commands/` | SHIPPED |
| "SDK sync client tracks `/v1/*` correctly" | project-status.md | SDK contract tests added for 20+ modules in v1.4 | SHIPPED |
| "route/auth ownership checks" are ongoing work | project-status.md | Generated OpenAPI now records 223 required-auth, 2 optional-auth, and 21 public operations. Application roles and ownership remain route-specific and are tested in source. | SHIPPED |
| "API, CLI, frontend, observability, docs, and serial release smoke tests now exist" | project-status.md | pytest API tests ✓, Playwright e2e ✓, frontend unit tests ✓, scheduler/governance/session tests added since audit | SHIPPED |

### 1.4 surfaces.md Claims

| Claim | Source | Reality | Status |
|-------|--------|---------|--------|
| "Governance (Faramesh) — CLI commands for governance inspection and approval actions" | surfaces.md | `mutx governance` CLI exists in `cli/commands/governance.py` | SHIPPED |
| "Governance — Prometheus metrics export via `/v1/runtime/governance/metrics`" | surfaces.md | `/v1/runtime/governance/metrics` confirmed in OpenAPI ✓ | SHIPPED |
| "Governance — Policy enforcement (PERMIT/DENY/DEFER) via FPL" | surfaces.md | Code exists in `src/security/` and policies routes `/v1/policies/*` in OpenAPI | SHIPPED |
| "Governance — Credential broker (Vault, AWS, GCP, Azure, 1Password, Infisical)" | surfaces.md | `/v1/governance/credentials/*` routes and all six provider adapters exist. External provisioning, credentials, and live end-to-end proof remain configuration-dependent; the Terraform Vault module is still a placeholder. | PARTIAL |
| "Governance — Supervised agents" | surfaces.md | `/v1/runtime/governance/supervised/*` routes in OpenAPI with start/stop/restart/profiles | SHIPPED |
| "Security — Actions, approvals, compliance, metrics, receipts, sessions" | surfaces.md | All confirmed: `/v1/security/actions/evaluate`, `/v1/security/approvals/*`, `/v1/security/compliance`, `/v1/security/metrics`, `/v1/security/receipts/*`, `/v1/security/sessions/*` | SHIPPED |
| "Dashboard — RAG search and scheduler return 503 with feature flags" | surfaces.md | RAG now has real endpoints (gated by config flag). Scheduler has real implementation. **No longer 503 stubs.** | **CHANGED → SHIPPED** |

### 1.5 roadmap.md Claims

| Claim | Source | Reality | Status |
|-------|--------|---------|--------|
| "keep Vault and provider credential support configuration-dependent until an end-to-end deployment proves the integration" | roadmap.md | Confirmed — the adapter is implemented, while deployment proof remains external | PARTIAL |
| "Replace scheduler stub with real implementation or keep unmounted and documented" | historical roadmap wording | **DONE** — Scheduler is mounted with database-backed CRUD, execution claims, leases, and recovery | **CHANGED → SHIPPED** |
| "Turn RAG search into real vector-backed behavior" | roadmap.md | **DONE** — `/v1/rag/embed`, `/v1/rag/embed/batch`, `/v1/rag/search` are real endpoints with OpenAI embedding support | **CHANGED → SHIPPED** |

---

## 2. OpenAPI `/v1/*` Route Inventory

**Audit Date:** 2026-07-28
**Total top-level `/v1` families:** 33
**Total OpenAPI paths:** 198
**Total endpoint-method pairs:** 246

Security counts below are generated operation contracts. They do not replace the
persisted-role, ownership, plan, or internal-user checks declared in route source.

| Route family | Methods | Security-mode operations |
| --- | --- | --- |
| `/v1/agents` | DELETE, GET, PATCH, POST | 21 required |
| `/v1/analytics` | GET | 8 required |
| `/v1/api-keys` | DELETE, GET, POST | 5 required |
| `/v1/approvals` | GET, POST | 5 required |
| `/v1/assistant` | DELETE, GET, POST | 8 required |
| `/v1/audit` | GET | 3 required |
| `/v1/auth` | GET, POST | 1 required / 1 optional / 12 public |
| `/v1/budgets` | GET | 2 required |
| `/v1/clawhub` | GET, POST | 3 required / 2 public |
| `/v1/deployments` | DELETE, GET, POST | 11 required |
| `/v1/documents` | GET, POST | 11 required |
| `/v1/events` | POST | 1 required |
| `/v1/governance` | DELETE, GET, POST | 14 required |
| `/v1/ingest` | POST | 4 required |
| `/v1/leads` | DELETE, GET, PATCH, POST | 8 required / 2 public |
| `/v1/monitoring` | GET, PATCH | 3 required |
| `/v1/observability` | GET, PATCH, POST | 8 required |
| `/v1/onboarding` | GET, POST | 2 required |
| `/v1/payments` | GET, POST | 4 required / 1 public |
| `/v1/pico` | DELETE, GET, POST, PUT | 10 required / 1 optional |
| `/v1/policies` | DELETE, GET, POST, PUT | 7 required |
| `/v1/rag` | GET, POST | 5 required |
| `/v1/reasoning` | GET, POST | 9 required |
| `/v1/runs` | GET, POST | 5 required |
| `/v1/runtime` | GET, POST, PUT | 10 required |
| `/v1/scheduler` | DELETE, GET, PATCH, POST | 6 required |
| `/v1/security` | DELETE, GET, POST | 14 required |
| `/v1/sessions` | DELETE, GET, POST | 5 required |
| `/v1/swarms` | DELETE, GET, PATCH, POST | 7 required |
| `/v1/telemetry` | GET, POST | 3 required |
| `/v1/templates` | DELETE, GET, POST, PUT | 8 required |
| `/v1/usage` | GET, POST | 3 required |
| `/v1/webhooks` | DELETE, GET, PATCH, POST | 9 required |
| `/`, `/health`, `/metrics`, `/ready` | GET | 4 public total |

**Unmounted routes (code exists, not served):**
- `/v1/newsletter` — waitlist signup code exists but router is in `UNMOUNTED_ROUTER_NAMES`

**Current generated-contract truth:**
- every operation has explicit public, optional-auth, or required-auth security metadata
- 217 required user-principal operations advertise Bearer or `X-API-Key`; the 6
  agent-runtime reporting/command operations advertise Bearer only
- both optional-auth operations advertise anonymous, Bearer, or `X-API-Key`
- raw optional auth-header parameters are removed when generated security metadata owns the contract
- sanitizer-wrapped response models retain structured fields and read-only computed properties instead of degrading to empty schemas
- the snapshot and `app/types/api.ts` are generated together and verified byte-for-byte

---

## 3. Legacy Automation / Redundancy Findings

This section preserves the April autonomy audit as a cleanup record, not as a
current public-product contract. Six superseded Python controllers and scanners
have been removed. The supported substrate is the repo-local orchestrator,
daemon, bounded lane runners, queue and lane state, resume policy, and run
artifacts. The two older shell loops remain quarantined for provenance and are
not canonical entry points.

### 3.1 Autonomy Scripts Inventory

All scripts are located in `scripts/autonomy/` unless otherwise noted.

| Script | Purpose | Classification | Redundancy |
|--------|---------|----------------|-------------|
| `autonomous-coder.py` | Historical queue consumer coupled to a local gateway | RETIRED | Removed after the bounded local lane substrate replaced it |
| `autonomous-loop.py` | Historical `sessions_spawn` supervisor | RETIRED | Removed after the bounded local lane substrate replaced it |
| `autonomous-loop.sh` | Historical Bash loop that calls Codex for implementation | QUARANTINED | Retained for provenance; replaced by the bounded lane substrate |
| `autonomous-loop-v3.sh` | Historical Bash loop that calls `openclaw sessions spawn` | QUARANTINED | Retained for provenance; replaced by the bounded lane substrate |
| `mutx-autonomous-daemon.py` | Historical self-supervising daemon coupled to stale local paths | RETIRED | Removed in favor of `daemon_main.py` and bounded lane runners |
| `mutx-master-controller.py` | Historical gap-scanner and daemon supervisor | RETIRED | Removed in favor of `orchestrator_main.py` and `daemon_main.py` |
| `mutx-gap-scanner-v3.py` | Historical GitHub queue scanner | RETIRED | Removed in favor of the canonical orchestrator queue contract |
| `mutx-gap-scanner.py` | Historical source-code gap scanner | RETIRED | Removed with the legacy autonomy stack |
| `build_work_order.py` | Scores GitHub issues by labels, picks top work order, routes to agent/lane | SHIPPED | Queue infrastructure |
| `execute_work_order.py` | Prepares git branch, writes brief, optionally runs agent command and opens PR | SHIPPED | Queue executor |
| `select_agent.py` | Maps issue labels to agent names and lane strategy | SHIPPED | Shared utility |
| `hosted_llm_executor.py` | Calls hosted LLM (GitHub Models or OpenAI) with work order prompt, applies patch | SHIPPED | Agent execution via hosted models |
| `github_hosted_agent.py` | Builds prompt bundle for a GitHub-hosted coding agent | SHIPPED | Prompt builder wrapper |
| `queue-feeder.sh` | Cron script: adds `autonomy:ready` GitHub issues to action queue | SHIPPED | Queue maintenance |
| `mutx-heartbeat.sh` | Runs `make dev`, reports health, opens GitHub issue if broken | SHIPPED | Repo health monitor |
| `mutx-daemon-watchdog.sh` | Checks if daemon is alive, restarts if dead, resets stuck queue items | SHIPPED | Daemon health watchdog |
| `daemon-launcher.sh` | Repo-local daemon launcher with configurable repo root | SHIPPED | Canonical daemon entry point |

### 3.2 Historical Redundancy Retired

The duplicate Python controller, daemon, master controller, and both gap
scanners listed as `RETIRED` above have been deleted. The remaining historical
shell loops are quarantined and are not invoked by the canonical daemon or CI.

The supported flow is:

1. `orchestrator_main.py` builds and enqueues bounded work.
2. `daemon_main.py` supervises queue execution and recovery.
3. `run_codex_lane.py`, `run_opencode_lane.py`, and `run_main_lane.py` execute
   explicit lane contracts.
4. `queue_state.py`, `lane_state.py`, and `run_artifacts.py` preserve durable
   state and evidence.

### 3.3 Remaining Portability Debt

The canonical Python entry points accept command-line or environment overrides,
but some developer-local defaults and quarantined scripts still assume Fortune's
workstation layout:

| Surface | Current behavior | Status |
|---------|------------------|--------|
| `orchestrator_main.py`, `daemon_main.py`, `lane_contract.py` | User-specific repo and worktree defaults; callers can override them with CLI arguments | PORTABLE WITH OVERRIDES |
| `daemon-launcher.sh`, `daemon-watchdog.sh`, `mutx-daemon-watchdog.sh` | Repo root can be overridden with `MUTX_REPO_ROOT` | PORTABLE WITH OVERRIDES |
| `reconcile_review_threads.py` | Repo root can be overridden with `MUTX_REPO_ROOT` | PORTABLE WITH OVERRIDES |
| `autonomous-loop.sh`, `autonomous-loop-v3.sh` | Hardcoded queue, repo, log, and worktree paths | QUARANTINED |
| `queue-feeder.sh`, `mutx-heartbeat.sh` | Hardcoded queue, repo, or log paths | LEGACY OPERATIONS DEBT |
| `print_status.py`, `reconcile_prs.py` | User-specific repo-root defaults without a shared config layer | INTERNAL TOOLING DEBT |
| `hosted_llm_executor.py` | Resolves agent definitions from repo-relative `agents/` paths | PORTABLE REPO CONTRACT |

### 3.4 Runtime Prerequisites

| Contract | Status |
|----------|--------|
| Repo and lane worktrees | Supplied through CLI options or developer-local defaults; not required by product or CI runtime |
| `mutx-engineering-agents/dispatch/action-queue.json` | Runtime queue state created and managed by autonomy tooling; not a public-product dependency |
| `agents/{agent}/AGENT.md` | Repo-relative hosted-executor input; the executor reports a configuration error when a selected definition is absent |
| Hosted model credentials | Required only when the optional hosted executor is selected |

---

## 4. Classification Summary

### 4.1 By Surface

| Surface | Previous | Current | Change |
|---------|----------|---------|--------|
| FastAPI `/v1/*` control plane | SHIPPED | SHIPPED | 33 top-level families, 198 paths, 246 operations |
| Agent lifecycle | SHIPPED | SHIPPED | Expanded: commands, heartbeat, status, versions, rollback |
| Assistant routes | SHIPPED | SHIPPED | Expanded: skill install/delete |
| Templates | SHIPPED | SHIPPED | — |
| Webhooks | SHIPPED | SHIPPED | Now includes PATCH |
| Auth | PARTIAL | SHIPPED | operation-level security metadata plus route-specific persisted roles, ownership, plan, and internal-user checks |
| API Keys | PARTIAL | SHIPPED | Auth enforced |
| Leads | SHIPPED | SHIPPED | Expanded: PATCH support |
| Clawhub | SHIPPED | SHIPPED | — |
| Sessions | PLACEHOLDER | SHIPPED | Wired to OpenClaw gateway HTTP API |
| Runs | PLACEHOLDER | SHIPPED | Real routes with traces |
| Usage/metrics | PLACEHOLDER | SHIPPED | `/v1/usage/events` with CRUD |
| Monitoring | PLACEHOLDER | SHIPPED | `/v1/monitoring/alerts` + health |
| Budgets | PLACEHOLDER | SHIPPED | Credits + usage tracking with plan tiers |
| RAG | PLACEHOLDER | SHIPPED | Real embed/search with OpenAI, gated by config flag |
| Scheduler | STUB | SHIPPED | Database-backed tasks with conditional execution claims, leases, and recovery |
| Runtime | PLACEHOLDER | SHIPPED | Provider snapshots + full governance routes |
| Analytics | PLACEHOLDER | SHIPPED | User summaries/timeseries/costs/budget plus internal revenue, subscription, and payment reads |
| Onboarding | PLACEHOLDER | SHIPPED | State management |
| Swarms | PLACEHOLDER | SHIPPED | List, create, get, update, delete, scale; **real DB persistence** |
| Governance metrics | MISLEADING | SHIPPED | `/v1/runtime/governance/metrics` + status + supervised |
| Governance credentials | PARTIAL | PARTIAL | Route surface and six adapters are real; external provisioning and end-to-end rollout proof remain configuration-dependent |
| Security | — | SHIPPED | NEW: actions, approvals, compliance, metrics, receipts, sessions |
| Observability | — | SHIPPED | NEW: runs, eval, provenance, status, steps |
| Policies | — | SHIPPED | NEW: CRUD + reload |
| Approvals | — | SHIPPED | NEW: request, approve, reject |
| Audit | — | SHIPPED | NEW: events, traces (private route) |
| Ingest | — | SHIPPED | NEW: agent-status, deployment, metrics, events |
| Telemetry | — | SHIPPED | NEW: config, health |
| Pico progress | — | SHIPPED | NEW: `/v1/pico/progress` GET/POST with DB-backed progress persistence |
| Newsletter | MISLEADING | PARTIAL | Code exists but UNMOUNTED — `/v1/leads` is the active replacement |
| Vault integration | STUB | PARTIAL | External Vault adapter exists; Terraform provisioning remains a placeholder and deployment is configuration-dependent |

### 4.2 Current Contract Statistics

| Measure | Current snapshot |
| --- | --- |
| Top-level `/v1` families | 33 |
| OpenAPI paths | 198 |
| OpenAPI operations | 246 |
| Required-auth operations | 223 |
| Optional-auth operations | 2 |
| Public operations | 21 |

---

## 5. Key Gaps Remaining

1. **Vault rollout remains configuration-dependent** — the credential broker
   adapter exists, but the Terraform module is a placeholder and the repository
   does not prove an external Vault deployment.

2. **Newsletter route unmounted** — `/v1/newsletter` code exists but its router
   is explicitly excluded from serving. Public docs now direct lead capture to
   `/v1/leads`; the unused backend module remains cleanup debt.

3. **Authorization remains route-specific** — OpenAPI now represents authentication alternatives accurately, but accepted application roles, ownership, plans, and internal-domain restrictions remain route dependency contracts rather than OpenAPI role metadata.

4. **Legacy hardcoded paths block portability** — the older automation scripts
   catalogued in section 3 hardcode `/Users/fortune/MUTX` and external worktree
   directories; newer repo-local orchestration should remain the preferred path.

5. **3 parallel autonomous loop implementations** — Consolidation opportunity remains unchanged.

6. **Legacy/new autonomy overlap** — the repo-local launcher and orchestrator
   coexist with older hardcoded loop scripts; callers must choose deliberately.

---

*Report checked against whitepaper.md, project-status.md, surfaces.md, roadmap.md,
README.md, docs/api/openapi.json, src/api/routes/*, src/api/main.py, and the
contract-generation scripts in the current checkout.*
