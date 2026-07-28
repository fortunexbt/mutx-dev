---
description: Evidence-based mapping of the OWASP Top 10 for Agentic Applications 2026 to MUTX controls and gaps.
---

# OWASP agentic risk matrix

This document maps the **OWASP Top 10 for Agentic Applications 2026** to
MUTX as it exists at commit `95ec55d9a49f68c488dc08c9f6fecabfadb57afe`,
audited on 2026-07-16. It is an engineering gap assessment, not an OWASP
certification, an implementation-level verification, or a “10/10 coverage”
claim.

The risk names and ordering come from OWASP's primary publications:

- [OWASP Top 10 for Agentic Applications for 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
- [OWASP launch article with the ASI01–ASI10 taxonomy](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/)

## How to read this matrix

- **Partial** means source-backed controls are relevant to the risk, but
  material attack paths or verification requirements remain open.
- **Gap** means MUTX has no verified control for the core risk. Adjacent
  inventory, authentication, or observability does not change that status.
- A file's existence is not proof that every deployed agent path uses it.
  Runtime configuration and end-to-end enforcement still need production-path
  evidence.
- **AARM overlap** identifies related requirements in the
  [current MUTX AARM assessment](../legal/aarm-alignment.md). It does not imply
  that AARM or OWASP coverage has been demonstrated.

## Current mapping

| ID | Official risk | Status | Source-backed MUTX capability | Explicit gap | AARM overlap |
| --- | --- | --- | --- | --- | --- |
| ASI01 | Agent Goal Hijack | Partial | [`ContextAccumulator`](../../src/security/context.py) records the original request, stated intent, actions, and heuristic intent signals; [`PolicyEngine`](../../src/security/policy.py) can make a rule depend on a supplied drift signal. | There is no direct or indirect prompt-injection detector, trusted/untrusted content boundary, source labeling, or calibrated semantic goal comparison. Context is process-local, and the policy path only uses it when a caller supplies it. Universal pre-execution enforcement is not demonstrated. | R1, R2, R3, R7, R8 |
| ASI02 | Tool Misuse & Exploitation | Partial | [`ActionMediator`](../../src/security/mediator.py) supports registered tool schemas and parameter constraints; [`PolicyEngine`](../../src/security/policy.py) supports deny/modify/defer rules and limited command-pattern checks; [`FarameshSupervisor`](../../src/api/services/faramesh_supervisor.py) defaults direct launches off and allowlists executables and environment keys. | Unregistered tools pass schema validation, command checks are regex-based, and interception is not proven across every framework/runtime path. There is no general capability-scoped tool token, per-call network/data boundary, or complete fail-closed proof. | R1, R3, R4, R5, R9 |
| ASI03 | Identity & Privilege Abuse | Partial | API users and agents have separate authentication paths in [`middleware/auth.py`](../../src/api/middleware/auth.py); owned-resource lookups are centralized in [`auth/ownership.py`](../../src/api/auth/ownership.py); the repo also contains a [`SPIFFEIdentityProvider`](../../src/api/services/spiffe_identity.py) and a multi-backend [`CredentialBroker`](../../src/api/services/credential_broker.py). | Workload identity is not bound to every normalized action, policy decision, receipt, or delegated call. The SPIFFE provider falls back to environment identity and treats validation as successful when the SPIRE binary is absent. Revocation, freshness, role/privilege propagation, and operation-scoped credentials are not demonstrated end to end. | R5, R6, R9 |
| ASI04 | Agentic Supply Chain Vulnerabilities | Partial | Dependency lockfiles and pinned GitHub Actions constrain part of the software supply chain; CI scans the frontend container with Trivy in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml); the local skill catalog records upstream repository/commit metadata in [`assistant_control_plane.py`](../../src/api/services/assistant_control_plane.py). | MUTX does not verify signed provenance or attestations for agent models, MCP servers, tools, skills, prompts, or runtime updates. The skill install flow changes agent configuration but has no malware/policy scanner, and there is no MCP security scanner. Container scanning covers only one artifact class. | R1, R3, R5, R8 |
| ASI05 | Unexpected Code Execution | Partial | [`PolicyEngine.validate_command_constraints()`](../../src/security/policy.py) rejects a small set of dangerous shell strings; [`FarameshSupervisor`](../../src/api/services/faramesh_supervisor.py) launches argument arrays without a shell and restricts commands, environment overrides, and policy paths when configured. | Pattern matching is bypassable and is not code or AST validation. MUTX does not provide a verified OS sandbox, filesystem boundary, syscall policy, network-egress policy, resource quota, or isolation proof for every code-capable agent/tool path. | R1, R3, R4, R5 |
| ASI06 | Memory & Context Poisoning | Gap | [`ContextAccumulator`](../../src/security/context.py) records session context for policy input. The authenticated RAG surface in [`routes/rag.py`](../../src/api/routes/rag.py) uses durable tenant-owned collections, bounds request and metadata shape/size, enforces tenant storage quotas, validates collection configuration before embedding, and caps exhaustive document scans. These are isolation and resource-bounding controls, not memory-integrity controls. | RAG still accepts arbitrary text and caller-selected collection names without provenance, sanitization, trust scoring, approval, integrity versioning, or deletion review. Context has no poisoned-memory detection or trusted-source separation, and indexed vector search is not yet available. | R2, R3, R5, R7, R8 |
| ASI07 | Insecure Inter-Agent Communication | Gap | [`routes/swarms.py`](../../src/api/routes/swarms.py) enforces ownership for swarm membership and bounds replicas. HMAC-capable outbound webhooks and agent API keys exist elsewhere, but they are not an inter-agent security protocol. | The swarm surface manages membership and scale only. There is no authenticated and authorized agent-to-agent message envelope, sender attestation, payload integrity, replay protection, schema validation, trust-boundary policy, delivery provenance, or per-peer rate limit. | R2, R5, R6, R8 |
| ASI08 | Cascading Failures | Partial | [`monitoring.py`](../../src/api/services/monitoring.py) marks stale agents failed and emits alerts/events; [`self_healer.py`](../../src/api/services/self_healer.py) has bounded retries and rollback hooks; swarm replica limits and [`middleware/rate_limit.py`](../../src/api/middleware/rate_limit.py) provide local bounds. | These controls observe or recover individual components. There is no dependency graph, cascade-aware budget, fan-out/depth limit, circuit breaker for agent/tool chains, global kill switch, failure-domain isolation proof, or test showing one compromised agent cannot propagate harm. | R2, R3, R4, R7, R8 |
| ASI09 | Human-Agent Trust Exploitation | Partial | Canonical [`ApprovalRecord`](../../src/api/models/approval.py) rows persist owner/reviewer assignment and authenticated decisions; [`routes/security.py`](../../src/api/routes/security.py) exposes compatibility endpoints over those records. | The approval record does not prove that reviewers receive trustworthy provenance, uncertainty, alternatives, or a clear rendering of agent-supplied content versus system facts. Phishing-resistant confirmation and tests against persuasive or deceptive output remain incomplete. | R4, R5, R6, R8 |
| ASI10 | Rogue Agents | Partial | Agent heartbeat/status handling, manual stop and rollback routes, [`monitoring.py`](../../src/api/services/monitoring.py), governance telemetry in [`security/telemetry.py`](../../src/security/telemetry.py), and supervised-process stop controls provide pieces of detection and containment. | Health checks detect liveness, not behavioral integrity. MUTX has no calibrated anomaly model for goal drift, collusion, concealment, self-replication, or reward hacking; no cross-agent quarantine; and no demonstrated emergency stop that revokes credentials, network access, pending work, and delegated authority atomically. | R1, R2, R3, R4, R5, R7, R8, R9 |

## Evidence boundaries

The following distinctions prevent this matrix from becoming a marketing
claim:

1. Authentication is not authorization for an agent action. A valid user,
   agent key, or SVID does not prove least privilege for a specific tool call.
2. Logging is not prevention. Receipts, traces, and alerts help investigation,
   but do not stop a hijacked goal, poisoned memory, or cascading action.
3. Approval is not automatically informed consent. The reviewer needs trusted
   context, bound action parameters, authoritative identity, expiry, and replay
   protection.
4. Process supervision is not sandboxing. An allowlisted executable can still
   access excessive files, credentials, or network destinations.
5. Dependency scanning is not agentic supply-chain verification. Models,
   prompts, skills, tools, MCP servers, registries, and runtime configuration
   require provenance and policy of their own.

## Closure priorities

1. Isolate RAG data by tenant and agent; add source provenance, integrity
   versioning, trust policy, and poison-screening before retrieval or memory
   writes (ASI06).
2. Define an authenticated inter-agent envelope with workload identity,
   authorization, schema validation, nonce/expiry, replay protection, and
   per-peer limits before adding swarm messaging (ASI07).
3. Prove one fail-closed mediation path for every supported runtime, then add
   OS-level isolation and outbound data/network policy for code-capable tools
   (ASI01, ASI02, ASI05).
4. Bind human, service, agent, session, role, privilege, credential scope, and
   delegation chain to decisions and receipts (ASI03, ASI09).
5. Require signed provenance and security policy for skills, MCP servers,
   tools, models, prompts, and release artifacts; keep unverified upstreams out
   of execution paths (ASI04).
6. Add cascade budgets, dependency-aware circuit breaking, behavioral anomaly
   detection, quarantine, and an atomic emergency stop with credential
   revocation (ASI08, ASI10).

Reassess every row after those controls are integrated and production-path
tests exist. Until then, the truthful summary is **eight partial mappings and
two gaps**, not comprehensive coverage.
