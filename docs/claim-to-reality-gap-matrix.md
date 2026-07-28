# MUTX Claim-to-Reality Gap Matrix
**Audit Date:** 2026-04-11  
**Repo:** `/Users/fortune/MUTX`  
**Scope:** Phase A/B Autonomy Operating Model  
**Previous Audit:** 2026-04-10

---

## 1. Claim vs Reality Table

### 1.1 README Claims

| Claim | Source | Reality | Status |
|-------|--------|---------|--------|
| "FastAPI control plane with public routes mounted under `/v1/*`\" | README.md | TRUE — 29 mounted route prefixes, 181 endpoint-method pairs in OpenAPI | SHIPPED |
| "route groups for auth, agents, deployments, API keys, webhooks, newsletter, health, and readiness" | README.md | Auth ✓, Agents ✓, Deployments ✓, API Keys ✓, Webhooks ✓. Newsletter is UNMOUNTED (code exists but not served). Health probes at `/`, `/health`, `/ready` | PARTIAL |
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
| "FastAPI control plane with route groups: `/v1/auth`, `/v1/agents`, `/v1/deployments`, `/v1/api-keys`, `/v1/webhooks`, `/v1/newsletter`, `/v1/health`, `/v1/ready`" | whitepaper.md §6.1 | All confirmed in OpenAPI EXCEPT `/v1/newsletter` is unmounted (code exists, not served). `/v1/leads` is the active replacement. | PARTIAL |
| "Additional `/v1/*` surfaces: templates, assistant, sessions, runs, monitoring, budgets, rag, and runtime" | whitepaper.md §6.1 | ALL now confirmed in OpenAPI: templates ✓, assistant ✓, sessions ✓, runs ✓, monitoring ✓, budgets ✓, rag ✓, runtime ✓ | SHIPPED |
| "control-plane record model for agents and deployments" | whitepaper.md §8 | Database models confirmed. Routes are live with real DB-backed operations. | SHIPPED |
| "agent status values: creating, running, stopped, failed, deleting" | whitepaper.md §8.1 | Modeled in code; agent lifecycle routes support status transitions | SHIPPED |
| "Observability: /health, /ready, deployment logs and metrics routes, agent logs and metrics routes, webhook ingestion endpoints, monitoring configs" | whitepaper.md §10 | `/health` and `/ready` confirmed. Agent/deployment logs+metrics in OpenAPI. Webhook ingestion exists. Monitoring routes (`/v1/monitoring/*`) now in OpenAPI. Telemetry config at `/v1/telemetry/*` | SHIPPED |
| "Infrastructure: Railway + Docker, Terraform + Ansible, Prometheus + Grafana" | whitepaper.md §11 | Docker Compose confirmed. Terraform/Ansible/Helm in `infrastructure/`. Railway deploy notifications confirmed (Discord on cold start). | PARTIAL |
| "Vault integration" mentioned as infrastructure | whitepaper.md | Still explicitly documented as STUB in roadmap.md | STUB |

### 1.3 project-status.md Claims

| Claim | Source | Reality | Status |
|-------|--------|---------|--------|
| "RAG search and scheduler return 503 with feature flags until runtime is configured" | project-status.md | RAG now has real `/v1/rag/embed`, `/v1/rag/embed/batch`, `/v1/rag/search` endpoints (gated by `enable_rag_api` setting). Scheduler has real asyncio task engine with CRUD (374 lines). No longer 503 stubs. | **CHANGED → SHIPPED** |
| "`MutxAsyncClient` remains limited and must stay explicitly documented as such" | project-status.md | SDK async contract exists; 20+ contract test modules added in v1.4 | PARTIAL |
| "Vault integration is still a stub" | project-status.md | Confirmed — Vault integration remains a stub | STUB |
| "CLI grouped commands: auth, agent, deployment, assistant, runtime, setup, governance, and observability" | project-status.md | Governance CLI (`mutx governance`) confirmed. Other groups exist in `cli/commands/` | SHIPPED |
| "SDK sync client tracks `/v1/*` correctly" | project-status.md | SDK contract tests added for 20+ modules in v1.4 | SHIPPED |
| "route/auth ownership checks" are ongoing work | project-status.md | `get_current_user` dependency on 146+ endpoint-method pairs. RBAC enforcement with role checks on admin routes. Auth enforcement tests added. | SHIPPED |
| "API, CLI, frontend, observability, docs, and serial release smoke tests now exist" | project-status.md | pytest API tests ✓, Playwright e2e ✓, frontend unit tests ✓, scheduler/governance/session tests added since audit | SHIPPED |

### 1.4 surfaces.md Claims

| Claim | Source | Reality | Status |
|-------|--------|---------|--------|
| "Governance (Faramesh) — CLI commands for governance inspection and approval actions" | surfaces.md | `mutx governance` CLI exists in `cli/commands/governance.py` | SHIPPED |
| "Governance — Prometheus metrics export via `/v1/runtime/governance/metrics`" | surfaces.md | `/v1/runtime/governance/metrics` confirmed in OpenAPI ✓ | SHIPPED |
| "Governance — Policy enforcement (PERMIT/DENY/DEFER) via FPL" | surfaces.md | Code exists in `src/security/` and policies routes `/v1/policies/*` in OpenAPI | SHIPPED |
| "Governance — Credential broker (Vault, AWS, GCP, Azure, 1Password, Infisical)" | surfaces.md | `/v1/governance/credentials/*` routes in OpenAPI. Vault backend is stub; other backends have real implementations | PARTIAL |
| "Governance — Supervised agents" | surfaces.md | `/v1/runtime/governance/supervised/*` routes in OpenAPI with start/stop/restart/profiles | SHIPPED |
| "Security — Actions, approvals, compliance, MCP definition scanning, metrics, receipts, sessions" | surfaces.md | Confirmed routes include `/v1/security/actions/evaluate`, `/v1/security/approvals/*`, `/v1/security/compliance`, `/v1/security/mcp/scan`, `/v1/security/metrics`, `/v1/security/receipts/*`, and `/v1/security/sessions/*`; MCP registration/runtime sandboxing is not claimed | SHIPPED |
| "Dashboard — RAG search and scheduler return 503 with feature flags" | surfaces.md | RAG now has real endpoints (gated by config flag). Scheduler has real implementation. **No longer 503 stubs.** | **CHANGED → SHIPPED** |

### 1.5 roadmap.md Claims

| Claim | Source | Reality | Status |
|-------|--------|---------|--------|
| "Vault integration explicitly documented as infrastructure stub until it is real" | roadmap.md | Confirmed — Vault is still documented as stub | STUB |
| "Replace scheduler stub with real implementation or keep unmounted and documented" | roadmap.md | **DONE** — Scheduler is now a real 374-line asyncio task engine with CRUD, mounted in main.py | **CHANGED → SHIPPED** |
| "Turn RAG search into real vector-backed behavior" | roadmap.md | **DONE** — `/v1/rag/embed`, `/v1/rag/embed/batch`, `/v1/rag/search` are real endpoints with OpenAI embedding support | **CHANGED → SHIPPED** |

---

## 2. OpenAPI `/v1/*` Route Inventory

**Audit Date:** 2026-04-11  
**Total unique route prefixes in OpenAPI:** 29
**Total endpoint-method pairs:** 181

| Route Prefix | Auth (Depends) | Methods | Notes |
|---|---|---|---|
| `/v1/agents` | `get_current_user` | POST, GET | create, list, register, heartbeat, logs, metrics, commands |
| `/v1/agents/{agent_id}` | `get_current_user` | GET, DELETE, PATCH, POST | get, delete, config, deploy, stop, logs, metrics, resource-usage, rollback, status, versions |
| `/v1/analytics` | `get_current_user` | GET | summary, timeseries, costs, budget, agent summaries |
| `/v1/api-keys` | `get_current_user` | GET, POST, DELETE | CRUD + rotate |
| `/v1/approvals` | `get_current_user` | POST, GET | request, approve, reject |
| `/v1/assistant` | `get_current_user` | GET | overview, skills, channels, wakeups, health, sessions |
| `/v1/audit` | `get_current_user` (private) | GET | events, traces |
| `/v1/auth` | mixed | POST, GET | register, login, logout, refresh, me, forgot/reset password, verify email, SSO, local-bootstrap |
| `/v1/budgets` | `get_current_user` | GET | credits, usage |
| `/v1/clawhub` | `get_current_user` | GET, POST | skills, install, uninstall |
| `/v1/deployments` | `get_current_user` | POST, GET | CRUD + events, scale, restart, logs, metrics, versions, rollback |
| `/v1/governance/credentials` | `get_current_user` | GET, POST, DELETE | backends, health, get secret |
| `/v1/ingest` | `get_current_user` | POST | agent-status, deployment, metrics |
| `/v1/leads` | `get_current_user` | POST, GET, PATCH, DELETE | contacts + leads CRUD |
| `/v1/monitoring` | `get_current_user` | GET, PATCH | alerts, health |
| `/v1/observability` | `get_current_user` | POST, GET | runs, eval, provenance, status, steps |
| `/v1/onboarding` | `get_current_user` | GET, POST | state management |
| `/v1/pico` | `get_current_user` | GET, POST | progress read/write persistence |
| `/v1/policies` | `get_current_user` | GET, POST, DELETE | CRUD + reload |
| `/v1/rag` | `get_current_user` | POST, GET | embed, embed/batch, search, health, **ingest** |
| `/v1/runs` | `get_current_user` | POST, GET | runs, traces |
| `/v1/runtime` | `get_current_user` | GET, PUT | providers, governance metrics/status/supervised |
| `/v1/scheduler` | `get_current_user` + admin | GET, POST, DELETE, PATCH | real asyncio task engine with CRUD |
| `/v1/security` | `get_current_user` | POST, GET, DELETE | actions, approvals, compliance, MCP definition scanning, metrics, prometheus, receipts, sessions |
| `/v1/sessions` | `get_current_user` | POST, GET, DELETE | wired to OpenClaw gateway HTTP API; **local session discovery for Claude/Codex/Hermes** |
| `/v1/swarms` | `get_current_user` | GET, POST, PATCH, DELETE | list, create, get, update, delete, scale; **real DB persistence** |
| `/v1/telemetry` | `get_current_user` | GET, POST | config, health |
| `/v1/templates` | `get_current_user` | GET, POST | list, deploy |
| `/v1/usage` | `get_current_user` | POST, GET | events |
| `/v1/webhooks` | `get_current_user` | POST, GET, PATCH, DELETE | CRUD + test + deliveries |
| `/metrics` | none | GET | Prometheus |
| `/`, `/health`, `/ready` | none | GET | Root probes |

**Unmounted routes (code exists, not served):**
- `/v1/newsletter` — waitlist signup code exists but router is in `UNMOUNTED_ROUTER_NAMES`

**Key Changes Since April 10 Audit:**
- **NEW:** `/v1/pico/progress` — GET/POST progress persistence for Pico
- **NEW:** `POST /v1/rag/ingest` — document ingestion into vector store
- **NEW:** Swarms PATCH/DELETE on `/{swarm_id}` with real DB persistence
- **NEW:** Sessions local discovery — auto-discovers Claude, Codex, and Hermes sessions from local filesystem
- Route prefix count: 28 → 29; endpoint-method pairs: 179 → 181

---

## 3. Automation / Redundancy Findings

### 3.1 Autonomy Scripts Inventory

All scripts are located in `scripts/autonomy/` unless otherwise noted.

| Script | Purpose | Classification | Redundancy |
|--------|---------|----------------|-------------|
| `autonomous-coder.py` | Reads action queue, calls MiniMax-M2.7 via local gateway, generates code changes, commits and opens PRs | SHIPPED (active) | Overlaps with `autonomous-loop.py` and `autonomous-loop-v3.sh` |
| `autonomous-loop.py` | Supervisor using `sessions_spawn` via subprocess WS connection to OpenClaw gateway | LEGACY | Replaced by `autonomous-loop-v3.sh` and `mutx-autonomous-daemon.py` |
| `autonomous-loop.sh` | Bash loop that calls Codex for implementation | LEGACY/STUB | Replaced by `autonomous-loop-v3.sh` |
| `autonomous-loop-v3.sh` | Bash loop that calls `openclaw sessions spawn` for implementation | SHIPPED | Evolved from `autonomous-loop.sh` |
| `mutx-autonomous-daemon.py` | Self-supervising Python daemon with heartbeat, worktree sync, and area-specific implementation stubs | SHIPPED (most mature) | Consolidates watchdog and heartbeat logic |
| `mutx-master-controller.py` | Runs gap scanner + daemon watchdog in one supervised double-forked process | SHIPPED | Parent supervisor for gap scan + daemon health |
| `mutx-gap-scanner-v3.py` | Scans GitHub issues, stale PRs, SDK coverage gaps; adds to queue | SHIPPED (active version) | Replaces `mutx-gap-scanner.py` |
| `mutx-gap-scanner.py` | Code-analysis-based gap scanner (TODOs, error handling, deps, API docs) | LEGACY | Replaced by `mutx-gap-scanner-v3.py` |
| `build_work_order.py` | Scores GitHub issues by labels, picks top work order, routes to agent/lane | SHIPPED | Queue infrastructure |
| `execute_work_order.py` | Prepares git branch, writes brief, optionally runs agent command and opens PR | SHIPPED | Queue executor |
| `select_agent.py` | Maps issue labels to agent names and lane strategy | SHIPPED | Shared utility |
| `hosted_llm_executor.py` | Calls hosted LLM (GitHub Models or OpenAI) with work order prompt, applies patch | SHIPPED | Agent execution via hosted models |
| `github_hosted_agent.py` | Builds prompt bundle for a GitHub-hosted coding agent | SHIPPED | Prompt builder wrapper |
| `queue-feeder.sh` | Cron script: adds `autonomy:ready` GitHub issues to action queue | SHIPPED | Queue maintenance |
| `mutx-heartbeat.sh` | Runs `make dev`, reports health, opens GitHub issue if broken | SHIPPED | Repo health monitor |
| `mutx-daemon-watchdog.sh` | Checks if daemon is alive, restarts if dead, resets stuck queue items | SHIPPED | Daemon health watchdog |
| `daemon-launcher.py` | Launchd wrapper — prevents fork when launched by launchd | SHIPPED (in ~/MUTX only) | Only exists in ~/MUTX, NOT in mutx-dev clone |

### 3.2 Redundancy Map

**3 parallel autonomous coding loops:**
1. `autonomous-coder.py` — MiniMax via gateway, Python
2. `autonomous-loop-v3.sh` — OpenClaw `sessions spawn`, Bash
3. `mutx-autonomous-daemon.py` — Self-supervising Python daemon with implementation stubs

All three read from the same queue (`/Users/fortune/MUTX/mutx-engineering-agents/dispatch/action-queue.json`).

**2 parallel gap scanners:**
1. `mutx-gap-scanner-v3.py` — GitHub API + coverage gap focused
2. `mutx-gap-scanner.py` — Code analysis focused (TODOs, error handling)

### 3.3 Hardcoded Path Dependencies (Portable Audit Blockers)

These scripts have hardcoded absolute paths that will break if the repo moves:

| Script | Hardcoded Paths |
|--------|-----------------|
| `autonomous-coder.py` | `REPO = "/Users/fortune/MUTX"`, `WT_BACKEND`, `WT_FRONTEND`, `QUEUE`, `LOG`, `GW = "http://localhost:18789"` |
| `autonomous-loop.py` | `QUEUE = "/Users/fortune/MUTX/..."`, `LOG`, `WT_BACKEND`, `sock_path = "/var/run/openclaw/gateway.sock"` |
| `autonomous-loop.sh` | `QUEUE_FILE="/Users/fortune/MUTX/..."`, `REPO="/Users/fortune/MUTX"`, worktree paths |
| `autonomous-loop-v3.sh` | Same hardcoded paths |
| `mutx-autonomous-daemon.py` | `REPO`, `QUEUE`, `LOG`, `PID_FILE`, `WT_BACK`, `WT_FRONT`, `GH_REPO="mutx-dev/mutx-dev"` |
| `mutx-master-controller.py` | `REPO="/Users/fortune/MUTX"`, `DAEMON`, `GAPSCAN`, `QUEUE`, `LOG`, `PIDFILE` |
| `mutx-gap-scanner-v3.py` | `GH="/opt/homebrew/bin/gh"`, `QUEUE`, `LOG`, `REPO`, `WT`, `GH_REPO` |
| `mutx-gap-scanner.py` | `REPO="/Users/fortune/MUTX"` |
| `hosted_llm_executor.py` | Hardcodes `agents/{agent}/AGENT.md` paths, area context files |
| `queue-feeder.sh` | `QUEUE_FILE="/Users/fortune/MUTX/..."`, `cd /Users/fortune/MUTX` |
| `mutx-heartbeat.sh` | `REPO="/Users/fortune/MUTX"`, `LOG`, `GITHUB_REPO` |
| `mutx-daemon-watchdog.sh` | `LOG`, `QUEUE`, `DAEMON`, `cd /Users/fortune/MUTX` |

### 3.4 Missing External Dependencies

| Path | Status |
|------|--------|
| `/Users/fortune/mutx-worktrees/factory/backend` | Does not exist — referenced by all loop scripts |
| `/Users/fortune/mutx-worktrees/factory/frontend` | Does not exist — referenced by all loop scripts |
| `/Users/fortune/MUTX/mutx-engineering-agents/dispatch/action-queue.json` | Queue file location — external to both clones |
| `/var/run/openclaw/gateway.sock` | OpenClaw Unix socket — gateway may not be running |
| `agents/{agent}/AGENT.md` | Agent definitions referenced by `hosted_llm_executor.py` — may not exist |

---

## 4. Classification Summary

### 4.1 By Surface

| Surface | Previous | Current | Change |
|---------|----------|---------|--------|
| FastAPI `/v1/*` control plane | SHIPPED | SHIPPED | 29 route prefixes, 181 endpoint-method pairs |
| Agent lifecycle | SHIPPED | SHIPPED | Expanded: commands, heartbeat, status, versions, rollback |
| Assistant routes | SHIPPED | SHIPPED | Expanded: skill install/delete |
| Templates | SHIPPED | SHIPPED | — |
| Webhooks | SHIPPED | SHIPPED | Now includes PATCH |
| Auth | PARTIAL | SHIPPED | `get_current_user` present in 29/32 route modules, RBAC role checks, SSO support |
| API Keys | PARTIAL | SHIPPED | Auth enforced |
| Leads | SHIPPED | SHIPPED | Expanded: PATCH support |
| Clawhub | SHIPPED | SHIPPED | — |
| Sessions | PLACEHOLDER | SHIPPED | Wired to OpenClaw gateway HTTP API |
| Runs | PLACEHOLDER | SHIPPED | Real routes with traces |
| Usage/metrics | PLACEHOLDER | SHIPPED | `/v1/usage/events` with CRUD |
| Monitoring | PLACEHOLDER | SHIPPED | `/v1/monitoring/alerts` + health |
| Budgets | PLACEHOLDER | SHIPPED | Credits + usage tracking with plan tiers |
| RAG | PLACEHOLDER | SHIPPED | Real embed/search with OpenAI, gated by config flag |
| Scheduler | STUB | SHIPPED | Real 374-line asyncio task engine |
| Runtime | PLACEHOLDER | SHIPPED | Provider snapshots + full governance routes |
| Analytics | PLACEHOLDER | SHIPPED | Summary, timeseries, costs, budget |
| Onboarding | PLACEHOLDER | SHIPPED | State management |
| Swarms | PLACEHOLDER | SHIPPED | List, create, get, update, delete, scale; **real DB persistence** |
| Governance metrics | MISLEADING | SHIPPED | `/v1/runtime/governance/metrics` + status + supervised |
| Governance credentials | PARTIAL | PARTIAL | Route surface is real, but Vault remains a documented stub backend |
| Security | — | SHIPPED | NEW: actions, approvals, compliance, metrics, receipts, sessions |
| Observability | — | SHIPPED | NEW: runs, eval, provenance, status, steps |
| Policies | — | SHIPPED | NEW: CRUD + reload |
| Approvals | — | SHIPPED | NEW: request, approve, reject |
| Audit | — | SHIPPED | NEW: events, traces (private route) |
| Ingest | — | SHIPPED | NEW: agent-status, deployment, metrics |
| Telemetry | — | SHIPPED | NEW: config, health |
| Pico progress | — | SHIPPED | NEW: `/v1/pico/progress` GET/POST with DB-backed progress persistence |
| Newsletter | MISLEADING | PARTIAL | Code exists but UNMOUNTED — `/v1/leads` is the active replacement |
| Vault integration | STUB | STUB | No change — still documented as stub |

### 4.2 Summary Statistics

| Classification | Count | Previous |
|---------------|-------|----------|
| SHIPPED | 29 | 30 |
| PARTIAL | 2 | 2 |
| STUB | 1 | 1 |
| PLACEHOLDER | 0 | 0 |
| MISLEADING | 0 | 0 |

---

## 5. Key Gaps Remaining

1. **Vault integration remains a STUB** — the only infrastructure component still explicitly documented as incomplete.

2. **Newsletter route unmounted** — `/v1/newsletter` code exists but router is explicitly excluded from serving. Should either be removed or docs updated to not claim it.

3. **Auth header `required: false` in OpenAPI** — Despite auth enforcement across 29/32 route modules, the OpenAPI spec still marks authorization header as `required: false` on 157 endpoint-method pairs. This is a spec accuracy issue, not a runtime enforcement gap — the code enforces auth via FastAPI dependencies.

4. **Hardcoded paths block portability** — Every autonomy script hardcodes `/Users/fortune/MUTX` and references non-existent worktree directories.

5. **3 parallel autonomous loop implementations** — Consolidation opportunity remains unchanged.

6. **`daemon-launcher.py` drift** — Still exists only in `~/MUTX`, absent from `mutx-dev`.

---

*Report generated from audit of whitepaper.md, project-status.md, surfaces.md, roadmap.md, README.md, docs/api/openapi.json, src/api/routes/*, src/api/main.py, and scripts/autonomy/* in `/Users/fortune/MUTX`.*
