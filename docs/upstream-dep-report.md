# MUTX upstream dependency report

Last verified: 2026-07-15

This report separates three facts that older revisions conflated:

1. the current upstream release or head;
2. the historical ref from which MUTX adapted or generated local material; and
3. whether MUTX has actually validated compatibility with the current upstream.

Immutable license and source evidence is maintained in
[`docs/legal/oss-attribution-evidence.json`](legal/oss-attribution-evidence.json).

## Current upstream truth

| Project | Current audited upstream | License at audited ref | MUTX state | Required action |
| --- | --- | --- | --- | --- |
| agent-run | No release tags; main `9c7c3fa68413de878fae2d605c90fb334a0201f6` | MIT, Copyright (c) 2026 Builderz Labs | Local schemas are adapted; upstream package is not a runtime dependency | **QUARANTINE** current upstream package; do not import, vendor, execute, or update pending maintainer review |
| AARM docs | Main `8eff208b98786b2c9a578b26cb7eaca440ec4020` | MIT, Copyright (c) 2023 Mintlify | MUTX’s old R1–R9 numbering drifted from the current model | Use the current mapping; close technical and organizational gaps before any conformance claim |
| Faramesh Core | Main `e230a9ac2d12d80ed6f632db42b6e1983ccbce82`; pinned published release `v0.2.0` / `ae3ebc9066d65e4e930164881c2f2ce2be554c7f`; historical semver tag `v1.2.9` / `c85237e4e6b13745169291f60b9c6b985285dbaa` | Main: Apache-2.0; `v0.2.0` and `v1.2.9`: MPL-2.0 | CLI and gateway fetch an immutable installer and request `v0.2.0` explicitly | Run the pinned compatibility lane before changing either installer ref or release |
| FPL | Main `b7aa0b7ad56f60428d692278a435c5e6640cec2b` | Apache-2.0 | MUTX ships FPL policy files and CLI integration | Validate parser/daemon compatibility; retain Apache-2.0 text and any future `NOTICE` |
| Mission Control | `v2.1.0` / `b4ebc5418bea4fa9288a5c17fbddb9ba99740964` | MIT, Copyright (c) 2026 Builderz Labs | Direct dashboard pattern provenance predates the current release | Treat `v2.1.0` as the comparison baseline, not proof of compatibility |
| Orchestra Research AI-Research-SKILLs | `v1.7.2` / `773a52944ba4747a18bd4ae9ade53fff041adcbc` | MIT, Copyright (c) 2025 Claude AI Research Skills Contributors | Catalog is pinned to `05f1958727bfc2bc22240f41d060504473c4f236` | Regenerate and validate the catalog against `v1.7.2` in a dedicated migration |
| predict-rlm | `v0.7.2` / `4ff334dea79a2f27e96b7a50a358b0427050899e` | MIT, Copyright (c) 2026 Trampoline AI | Workflow provenance is pinned to `5c7387afa1980b62b21a34ad0261256a95d8caa1` | Validate templates, runtime prerequisites, and output contracts against `v0.7.2` |
| Guild AI | Tag `0.9.0`; audited main `dfbefedb6ca5ce3a1341f9f00a4016420f6fc76d` | Apache-2.0 | Candidate only; no direct reuse recorded | Keep out of the distribution unless a scoped adoption decision records exact provenance |
| LACP | Unresolved identity | Unknown | No direct reuse recorded | Do not port or make a license claim until owner, canonical repo, ref, and license are established |

## Security hold: agent-run

The current upstream TypeScript entry point at
[`agent-run@9c7c3fa/typescript/src/index.ts`](https://github.com/builderz-labs/agent-run/blob/9c7c3fa68413de878fae2d605c90fb334a0201f6/typescript/src/index.ts)
contains behavior that requires coordinated security review before the package
can be trusted as a schema/types dependency. MUTX must not recommend, install,
import, vendor, execute, or update that package until the upstream maintainer has
resolved the review.

MUTX’s existing observability implementation consists of local adapted schemas
and does not need the upstream TypeScript package at runtime. The commit is
recorded as audit evidence, not as an upgrade target. Coordinate any disclosure
through the repository’s security process; do not publish secret material.

## Current AARM model

The authoritative requirements are pinned at
[`aarm-dev/docs@8eff208b/conformance/requirements.mdx`](https://github.com/aarm-dev/docs/blob/8eff208b98786b2c9a578b26cb7eaca440ec4020/conformance/requirements.mdx).

| ID | Level | Current meaning | MUTX status |
| --- | --- | --- | --- |
| R1 | MUST | Pre-execution interception, blocking/deferral, no target effects, fail closed | Partial; not demonstrated |
| R2 | MUST | Context accumulation including data classification and original request | Partial; not demonstrated |
| R3 | MUST | Static and contextual policy evaluation with mandatory deferral conditions | Partial; not demonstrated |
| R4 | MUST | Distinct ALLOW, DENY, MODIFY, STEP_UP, and DEFER decisions | Partial; STEP_UP is not distinct |
| R5 | MUST | Complete signed and offline-verifiable receipts for every action | Partial; not demonstrated |
| R6 | MUST | Human, service, agent, session, role, and privilege identity binding | Partial; not demonstrated |
| R7 | SHOULD | Calibrated cumulative semantic-distance tracking | Gap; current heuristic is insufficient |
| R8 | SHOULD | Structured near-real-time telemetry, filtering, and historical export | Partial; not demonstrated |
| R9 | SHOULD | Just-in-time operation-scoped credentials | Gap; not demonstrated |

**AARM Core** requires all R1–R6 MUST requirements. **AARM Extended** adds
R7–R9. The upstream process also evaluates organizational conditions including
community engagement, an active production deployment, a relevant recognized
security certification, and benchmarking participation. MUTX has not published
evidence satisfying those conditions. See
[`docs/legal/aarm-alignment.md`](legal/aarm-alignment.md).

## Mission Control comparison baseline

Mission Control `v2.1.0` supersedes the `v2.0.1` baseline used by the previous
report. MUTX should compare behavior rather than copy its API breadth wholesale.
The durable direct-port evidence is intentionally pinned to the upstream source
commit that introduced the briefing pattern and to MUTX port commit
`972ab49b0af83d15042b2301679246103cbdbab6`.

High-value comparison areas remain:

- framework and gateway adapters;
- session lifecycle and transcript controls;
- webhook delivery history and retry behavior;
- skill registry synchronization and security scanning;
- agent evaluation and quality-review surfaces.

Each adoption should be its own issue/PR with compatibility tests and attribution.

## Faramesh and FPL license obligations

Faramesh Core current main and FPL current main are Apache-2.0, not MIT. The
pinned Core `v0.2.0` release and historical `v1.2.9` tag are MPL-2.0. The
audited refs contain no root `NOTICE` file. MUTX retains the verbatim
third-party Apache-2.0 text at `third_party/licenses/Apache-2.0.txt` and the
verbatim MPL-2.0 text at `third_party/licenses/MPL-2.0.txt`. A later relicense
on main does not retroactively relicense an earlier tag. If a future upstream ref adds
`NOTICE`, that material must be carried into the distribution when applicable.
“AARM-aligned” is the accurate upstream status for Faramesh and does not prove
MUTX conformance.

## Integration migration order

1. Keep agent-run quarantined and use only MUTX’s local adapted schema.
2. Close the AARM naming and claim drift before adding new conformance features.
3. Validate the pinned Faramesh Core `v0.2.0` release and current FPL in an isolated compatibility lane.
4. Regenerate Orchestra metadata against `v1.7.2` and review the resulting content.
5. Exercise predict-rlm `v0.7.2` through every managed/local workflow contract.
6. Re-audit Mission Control `v2.1.0` only for roadmap-backed capabilities.

## Automated drift reporting

[`docs/upstream-tracking.json`](upstream-tracking.json) maps this attribution
evidence and the Pico engine release pins to explicit GitHub metadata checks.
Run `python scripts/check_upstream_drift.py` for a live report. The checker only
reads repository, commit, tag, and release metadata; it never clones, imports,
vendors, or executes upstream code.

The `Upstream Drift` workflow runs weekly and on manual dispatch. Live mutable
network checks are deliberately isolated from ordinary pull-request CI, while
offline unit tests enforce the registry and report contracts. A drift result is
a review signal, not authorization to update or import an upstream. Triage and
compatibility work is tracked in [SOTA modernization epic #3688](https://github.com/mutx-dev/mutx-dev/issues/3688).

## Changelog

### 2026-07-15

- Replaced mutable and broken evidence with immutable commit/tag links.
- Corrected agent-run and Mission Control copyright years to 2026.
- Quarantined the current agent-run package pending upstream security review.
- Corrected AARM’s repository license notice to Copyright (c) 2023 Mintlify.
- Replaced the obsolete AARM requirement numbering with the current Core/Extended model.
- Corrected Faramesh/FPL from MIT and recorded the ref-specific split: Core main
  and FPL main are Apache-2.0, while the pinned Core `v0.2.0` release and
  historical `v1.2.9` tag are MPL-2.0.
- Updated Mission Control to `v2.1.0`, Orchestra to `v1.7.2`, and predict-rlm to `v0.7.2`.
- Marked LACP identity/license as unresolved and removed the unsupported MIT claim.

### 2026-04-16

- Initial upstream dependency report (now superseded by the verified record above).
