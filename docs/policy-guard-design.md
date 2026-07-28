# MUTX Policy Guard: Current Runtime Boundary

This document describes the policy behavior implemented in this repository. It is an implementation note, not a claim that MUTX intercepts actions taken by every agent framework or deployment.

## The boundary

MUTX has three related controls with different scope:

1. **Control-plane authorization.** FastAPI route dependencies authenticate users and API keys, enforce resource ownership, or require privileged roles where the route declares them.
2. **Governed MUTX runtime dispatch.** `ToolExecutionHandler.execute_tool()` normalizes and evaluates a tool call before invoking a handler registered with the MUTX `AgentRuntime`.
3. **Optional SDK text guardrails.** SDK middleware can check input and output text for PII patterns, custom regexes, or toxicity. These checks run only when the caller enables and invokes the middleware.

The first two are server-side source paths. The SDK layer is integration-owned. An external agent that neither uses the MUTX runtime dispatcher nor calls the guardrail middleware is outside these policy boundaries.

## Governed runtime flow

```text
tool call submitted to MUTX AgentRuntime
    |
    v
normalize action and evaluate policy
    |
    +-- DENY  --> record blocked receipt and audit event; handler is not called
    |
    +-- DEFER --> record fail-closed non-resumable evidence; handler is not called
    |
    +-- ALLOW or MODIFY
            |
            v
    persist authorization evidence
            |
            +-- persistence fails --> handler is not called
            |
            v
    invoke registered handler
            |
            v
    append observed outcome evidence
```

Source: `src/api/services/agent_runtime.py` and `src/api/services/governance_runtime.py`.

### Decisions

The in-process policy engine supports `ALLOW`, `DENY`, `MODIFY`, and `DEFER`.

- Rules are ordered by priority; the first matching rule returns a decision.
- A policy set has an explicit default decision.
- No configured policy, or a disabled selected policy, returns `DENY`.
- The default MUTX runtime policy allows the known low-risk built-in tool names and denies unconfigured custom tools.
- Built-in command constraints reject known dangerous shell patterns before ordinary rule matching.

The current rule matcher supports tool, agent, and session patterns. It does not implement the YAML policy format or Hermes file layout described by older versions of this document.

### DEFER and approvals

A `DEFER` verdict stops the current `execute_tool()` call before its registered
handler. The runtime cannot currently serialize an arbitrary handler and bind
it to an idempotent durable continuation, so it fails closed with
`resumable: false` and records `blocked_no_resume_binding`. It does not create
an in-process or durable approval that would misleadingly appear resumable.

The REST approvals API is the durable contract. It stores owner-scoped requests
and authenticated resolutions, supports explicit reviewer assignment, and can
send a configured creation webhook. A runtime integration that needs resume
must explicitly bind a canonical approval to a durable job continuation and
re-authorize before executing it.

Source: `src/api/routes/approvals.py`, `src/api/services/approval_persistence.py`,
and `src/api/services/governance_runtime.py`.

## Fail behavior

The governed MUTX runtime is fail-closed before handler invocation in these cases:

- no policy is configured;
- the selected policy is disabled;
- a decision is `DENY` or `DEFER`;
- an allowed or modified decision cannot be persisted before execution; or
- policy evaluation raises before the handler call.

There is one important temporal boundary: once a handler has executed, a later outcome-recording failure cannot undo the external side effect. The runtime returns the handler result with an evidence error so the caller can reconcile it. This is not equivalent to an atomic transaction with an external tool.

The SDK toxicity guardrail also blocks on an unavailable or invalid service by default. A caller may explicitly opt into `fail_open_on_unavailable=True`; that exception applies only to the SDK toxicity check, not to governed runtime tool policy.

## Evidence

For governed tool calls, MUTX can record:

- the normalized action and action hash;
- actor, agent, session, and run identifiers supplied by the caller;
- policy and rule references;
- decision, reason, receipt identifier, and receipt hash;
- approval identifier for workflows that explicitly bind canonical approvals; and
- the handler outcome or error that the runtime observes.

Authorization evidence is written before an allowed handler runs. Audit exports verify the SHA-256 event chain and return an explicit `verified` result. Audit queries and exports require the privileged roles declared by the audit routes.

This evidence covers governed MUTX runtime operations. General run traces and SDK adapter events contain only the events an authenticated caller or instrumented adapter submits.

Source: `src/api/services/audit_log.py`, `src/api/routes/audit.py`, `src/api/routes/runs.py`, and `src/api/services/event_ingestion.py`.

## SDK guardrails

`sdk/mutx/guardrails.py` provides:

- PII-pattern blocking for SSNs, card-number shapes, and email addresses;
- custom regular-expression blocklists;
- optional synchronous or asynchronous toxicity checks; and
- input/output middleware that raises on a blocking result.

The generic agent clients apply these checks only when given guardrail middleware. `MutxAgentKit` enables its default input/output guardrails only when `guardrails_enabled=True`; the default is `False`.

SDK guardrail results are local unless the integration reports them to a MUTX event, run, or audit path.

## Faramesh preview path

The CLI also integrates with Faramesh. That path depends on a Faramesh binary and an operator-managed local daemon/socket. CLI commands can inspect health, submit decisions, manage deferred items, and expose runtime status when that daemon is installed and reachable.

Faramesh is not embedded into every MUTX runtime action, and a successful local daemon check is not evidence that a hosted agent or deployment is governed. Credential-provider support likewise depends on the operator configuring and proving the external provider.

Source: `cli/faramesh_runtime.py`, `cli/commands/governance.py`, and `src/api/routes/runtime.py`.

## Non-goals and operator-owned integration

Current source does not establish these broader claims:

- automatic interception of uninstrumented LangChain, CrewAI, AutoGen, OpenClaw, or arbitrary external tool calls;
- automatic resumption after a REST approval;
- budget enforcement before every model or provider call;
- policy attachment to every deployment version;
- provider deployment, rollback, traffic failover, or network isolation from a control-plane record mutation; or
- complete traces for operations that were not instrumented and submitted.

Deployment providers, runtime adapters, secret backends, telemetry exporters, and retention controls remain operator-owned integration points.

## Verification map

Focused behavior is covered by:

- `tests/api/test_governed_runtime.py`
- `tests/api/test_guardrails.py`
- `tests/api/test_approvals.py`
- `tests/api/test_audit.py`
- `tests/api/test_runs.py`
- `tests/test_faramesh_runtime.py`

When this boundary changes, update this document and the public operational stories in the same change.
