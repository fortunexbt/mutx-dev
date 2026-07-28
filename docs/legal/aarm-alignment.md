---
description: Evidence-based mapping from the current AARM requirements to MUTX capabilities and gaps.
---

# AARM alignment status

MUTX is **not claiming AARM Core or AARM Extended conformance**. This page is a
local engineering gap assessment against the AARM requirements audited at
`aarm-dev/docs@8eff208b98786b2c9a578b26cb7eaca440ec4020` on 2026-07-15.

The authoritative requirements are
[`conformance/requirements.mdx`](https://github.com/aarm-dev/docs/blob/8eff208b98786b2c9a578b26cb7eaca440ec4020/conformance/requirements.mdx)
and the authoritative testing protocol is
[`conformance/testing.mdx`](https://github.com/aarm-dev/docs/blob/8eff208b98786b2c9a578b26cb7eaca440ec4020/conformance/testing.mdx).
AARM Core requires every MUST requirement, R1–R6. AARM Extended adds R7–R9.

## Technical mapping

“Partial” means relevant code exists, not that the upstream verification has
passed. Every row remains **not demonstrated** until its full upstream test set
has reproducible evidence for the production execution path.

| ID | Current AARM requirement | Relevant MUTX evidence | Gap to close | Status |
| --- | --- | --- | --- | --- |
| R1 | Pre-execution interception that blocks or defers, has no target effects, and fails closed | `src/security/mediator.py`, `src/security/policy.py`, `src/runtime/gateways/faramesh.py` | Prove every supported execution path is intercepted, denied/deferred actions have no effects, unavailability cannot fail open, and both decisions generate receipts | Partial; not demonstrated |
| R2 | Accumulate prior actions, data classifications, original request, and make context available to policy evaluation | `src/security/context.py` tracks actions, data access, and original request | Add classification rules with a highest-sensitivity default; prove the production policy path consumes the full context; add tamper-evident context storage if claiming the SHOULD | Partial; not demonstrated |
| R3 | Static and contextual policy evaluation with four action classifications, parameter validation, and mandatory deferral conditions | `src/security/mediator.py` validates registered tool schemas; `src/security/policy.py` supports static rules and an intent signal | Add `context-dependent defer`; defer on missing context, equal-priority conflicts, and low confidence; document/audit those conditions; prove all parameter constraint classes | Partial; not demonstrated |
| R4 | Five distinct decisions: ALLOW, DENY, MODIFY, STEP_UP, and DEFER, including safe timeout and dependency behavior | `PolicyDecision` supports ALLOW, DENY, MODIFY, DEFER; `ApprovalService` provides a human decision flow | Add a distinct STEP_UP decision; keep DEFER separate from human approval; enforce deny-on-timeout, dependency propagation, ordering, and bounded cascading deferrals | Partial; not demonstrated |
| R5 | Signed, offline-verifiable receipts for every decision with full action, context, identity, decision, approval/deferral, outcome, and policy evidence | `src/security/receipts.py` automatically signs every generated receipt with Ed25519, embeds the public key and stable key ID, rejects unsigned/non-Ed25519 records, and has tamper tests across every current decision; production requires a persistent signing seed | Include every required service identity, role, privilege, policy hash/version, deferral, approval-resolution, and credential-use field; prove complete receipt generation and trusted-key verification across every production execution path | Partial; not demonstrated |
| R6 | Bind human, service, agent, session, role, and privilege scope to trusted, fresh, revocation-aware identity | `NormalizedAction` carries user, agent, and session identifiers; API auth validates a caller | Add service identity and role/privilege scope to actions and receipts; prove trusted-source validation, freshness, revocation, rejection/flagging of unverifiable identity, and preservation across deferral/delegation | Partial; not demonstrated |
| R7 | Semantic-distance tracking from stated intent with calibrated cumulative drift and escalation | `ContextAccumulator.evaluate_intent()` computes a denial/error/repetition heuristic | Implement and calibrate semantic distance against the original request, track cumulative drift, document aggregation and thresholds, and prove alert/deferral/escalation behavior | Gap; not demonstrated |
| R8 | Structured near-real-time telemetry with filtering, DEFER coverage, and historical batch export | `src/security/telemetry.py` emits custom structured events and Prometheus metrics | Prove seconds-level delivery, decision/identity/action filtering, complete DEFER events, documented schema stability, and historical batch export to a security platform | Partial; not demonstrated |
| R9 | Just-in-time, operation-scoped credentials with audit logging | Faramesh exposes a credential-broker integration surface; MUTX has no equivalent native credential issuance proof | Integrate and test short-lived operation-scoped credentials, including a read credential that cannot write, and record usage in receipts/telemetry | Gap; not demonstrated |

## Organizational conditions

The AARM documentation also asks an organization using the “AARM-conformant”
designation to demonstrate community engagement, an actively used production
deployment, a relevant recognized security certification, and participation in
future benchmarking. This repository does not contain sufficient public evidence
for those conditions. They are therefore **not demonstrated** and cannot be
inferred from unit tests or from this mapping.

## What the API self-check means

`GET /v1/security/compliance` and `AARMComplianceChecker` are retained for
backward compatibility. They are local capability checks, not an AARM validation
report. A true conformance statement requires the current upstream technical
tests plus the organizational evidence described above.

## Updating this assessment

1. Pin the new AARM commit in
   `docs/legal/oss-attribution-evidence.json` before changing requirement names.
2. Update every source header that references a requirement number.
3. Add production-path tests matching the upstream verification language.
4. Keep a row “not demonstrated” until the complete test and evidence set exists.
5. Do not use “AARM-conformant” in product or marketing copy without an approved,
   current conformance record.
