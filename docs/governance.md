---
description: Faramesh governance engine integration for MUTX agents.
---

# Governance Engine

MUTX integrates [Faramesh](https://faramesh.dev) by [Faramesh Technologies](https://github.com/faramesh/faramesh-core) to provide deterministic AI agent governance. Governance decisions are enforced at runtime through FPL (Faramesh Policy Language) policies.

## Overview

Faramesh runs as a daemon alongside MUTX, communicating via Unix socket. The socket path is configured by `FAREMESH_SOCKET_PATH`; when it is unset, MUTX uses `$XDG_RUNTIME_DIR/faramesh.sock` or `~/.mutx/run/faramesh.sock`. When an agent attempts a tool call, Faramesh evaluates it against the active policy and returns PERMIT, DENY, or DEFER.

## CLI Commands

### Daemon Management

```bash
# Start the governance daemon (auto-installed during `mutx setup hosted`)
mutx governance start

# Check daemon health
mutx governance status

# Stream live decisions
mutx governance tail
```

### Inspect Decisions

```bash
# View recent decisions
mutx governance decisions --limit 50

# View pending approvals (DEFER queue)
mutx governance pending

# View metrics
mutx governance metrics

# Export metrics (Prometheus format)
mutx governance export-metrics --format prometheus
```

### Approval Actions

```bash
# Approve a deferred action
mutx governance approve <defer_token>

# Deny a deferred action
mutx governance deny <defer_token>

# Emergency kill an agent
mutx governance kill <agent_id>
```

### Policy Management

```bash
# List bundled policy packs
mutx governance policy list

# Validate a policy file
mutx governance policy validate ./my-policy.fpl

# Hot-reload the running policy (no daemon restart)
mutx governance policy reload

# Edit policy in $EDITOR
mutx governance policy edit
mutx governance policy edit --policy ./custom-policy.fpl
```

### Credential Broker

```bash
# List registered credential backends
mutx governance credential list

# Register a credential backend
mutx governance credential register vault my-vault --path secret/data/stripe --ttl 15m
```

**Supported backends:** `vault`, `awssecrets`, `gcpsm`, `azurekv`, `onepassword`, `infisical`

## Bundled Policy Packs

MUTX ships with several policy packs in `cli/policies/`:

| Pack | Description |
|------|-------------|
| `starter.fpl` | General purpose — blocks destructive commands |
| `payment-bot.fpl` | Session budgets, defer high-value refunds |
| `infra-bot.fpl` | Strict sandbox, defer infrastructure changes |
| `customer-support.fpl` | Phase-based intake/resolve workflow |

## FPL Policy Language

Policies are written in [FPL](https://github.com/faramesh/fpl-lang), a purpose-built language for agent governance:

```fpl
agent payment-bot {
  default deny
  model "gpt-4o"
  framework "langgraph"

  budget session {
    max $500
    daily $2000
    max_calls 100
    on_exceed deny
  }

  rules {
    deny! shell/* reason: "never shell"

    defer stripe/refund when amount > 500
      notify: "finance"
      reason: "high value refund"

    permit stripe/* when amount <= 500
  }
}
```

### Rule Effects

| Effect | Description |
|--------|-------------|
| `permit` | Allow the tool call |
| `deny` | Block the tool call |
| `deny!` | **Mandatory deny** — cannot be overridden |
| `defer` | Pause and route to human for approval |
| `block` | Alias for `deny` |
| `approve` | Alias for `permit` |

### Key FPL Concepts

- **Phase blocks** — Scope tool visibility by workflow stage
- **Budget blocks** — Session/daily spend limits
- **Ambient blocks** — Cross-session rate limiting
- **Selector blocks** — External data fetching at evaluation time
- **Credential blocks** — Credential broker configuration

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      MUTX CLI / TUI                      │
└────────────────────────┬────────────────────────────────┘
                         │ Unix socket
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Faramesh Governance Daemon                  │
│  - Evaluates tool calls against FPL policy              │
│  - Issues PERMIT / DENY / DEFER decisions                │
│  - Manages credential broker                            │
└─────────────────────────────────────────────────────────┘
```

## Prometheus Metrics

The `/v1/runtime/governance/metrics` endpoint returns the current governance
metrics payload. Prometheus scraping remains available at the root `/metrics`
probe when metrics are enabled:

```
# HELP mutx_governance_decisions_total Total governance decisions by effect
# TYPE mutx_governance_decisions_total counter
mutx_governance_decisions_total{effect="permit"} 42
mutx_governance_decisions_total{effect="deny"} 3
mutx_governance_decisions_total{effect="defer"} 5

# HELP mutx_governance_pending_approvals Pending approval count
# TYPE mutx_governance_pending_approvals gauge
mutx_governance_pending_approvals 2

# HELP mutx_governance_daemon_up Daemon availability
# TYPE mutx_governance_daemon_up gauge
mutx_governance_daemon_up 1
```

## Further Reference

- [Faramesh Documentation](https://faramesh.dev/docs)
- [FPL Language Reference](https://github.com/faramesh/fpl-lang)
- [Faramesh Core on GitHub](https://github.com/faramesh/faramesh-core)
