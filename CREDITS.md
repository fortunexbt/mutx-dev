# MUTX Credits and Attributions

MUTX is built on the shoulders of open-source projects. This document records
the projects MUTX integrates with, materially adapts, or uses as an
interoperability target. “Current upstream” means the release or commit checked
on 2026-07-15; it is not a claim that MUTX has already migrated every integration
to that revision.

Machine-readable evidence, immutable source links, and local file scopes live in
[`docs/legal/oss-attribution-evidence.json`](docs/legal/oss-attribution-evidence.json).
Direct ports are recorded in
[`docs/legal/oss-attribution-ledger.md`](docs/legal/oss-attribution-ledger.md).

## Integrated and adapted projects

### agent-run

- **Repository:** https://github.com/builderz-labs/agent-run
- **License:** MIT — Copyright (c) 2026 Builderz Labs
- **Current upstream:** no release tags; audited main commit
  `9c7c3fa68413de878fae2d605c90fb334a0201f6`
- **Upstream security status:** quarantined for MUTX dependency/vendor purposes
  pending maintainer review of the current TypeScript entry point; do not import,
  package, execute, or update from current upstream main
- **MUTX use:** the MUTX observability schema materially adapts the agent-run
  schema vocabulary into `MutxRun`, `MutxStep`, `MutxCost`, `MutxProvenance`,
  and `MutxEval`.

Tracked local surfaces include `src/api/models/observability.py`,
`src/api/models/observability_models.py`, `src/api/routes/observability.py`, and
`sdk/mutx/observability.py`.

MUTX carries its own adapted schemas and does not require the upstream
TypeScript package at runtime. The current commit is recorded for audit evidence,
not as a recommended upgrade target.

### AARM documentation and specification

- **Repository:** https://github.com/aarm-dev/docs
- **Repository license:** MIT — Copyright (c) 2023 Mintlify
- **Current upstream:** audited main commit
  `8eff208b98786b2c9a578b26cb7eaca440ec4020`
- **MUTX use:** specification alignment and terminology for the runtime security
  modules under `src/security/`.

The current specification defines **AARM Core** as R1–R6 and **AARM Extended**
as R1–R9. The meanings of R1–R9 changed from the older model previously copied
into MUTX. MUTX has relevant capabilities, but it has not demonstrated all
technical tests or the organizational conditions required to call the product
“AARM-conformant.” The evidence-based mapping is maintained in
[`docs/legal/aarm-alignment.md`](docs/legal/aarm-alignment.md).

The MIT copyright in the AARM repository belongs to Mintlify; the former
“Copyright (c) 2024 aarm-dev” notice was not present in the upstream license and
has been removed.

### Faramesh Core and FPL

- **Verified:** 2026-07-22
- **Core repository:** https://github.com/faramesh/faramesh-core
- **FPL repository:** https://github.com/faramesh/fpl-lang
- **Core current-main license:** Apache-2.0 at
  `01476cfb8bcbce83c199df3497af746a46318f8f`
- **Pinned installer release:** `v0.2.0`
  (`ae3ebc9066d65e4e930164881c2f2ce2be554c7f`), licensed MPL-2.0
- **Latest published Core release:** `v0.2.0`; the installer remains pinned
  because no newer GitHub release exists
- **Core latest semver tag:** `v1.2.9`
  (`c85237e4e6b13745169291f60b9c6b985285dbaa`), licensed MPL-2.0 at that tag
- **FPL current-main license:** Apache-2.0
- **Current FPL audit ref:**
  `c78b5a44215aa810cb86c46fbefa032a8aa10364`
- **FPL releases/tags:** none published; the EBNF grammar is unchanged from the
  previous audited ref and hashes to
  `599f498b2d204e018eb3f0313512f68d17adc80cee2e16c012649fb57d6cb3b2`

MUTX integrates with the Faramesh daemon and FPL policy format through
`cli/faramesh_runtime.py`, `cli/commands/governance.py`, `cli/policies/*.fpl`,
`src/api/services/faramesh_supervisor.py`, and
`src/runtime/gateways/faramesh.py`. Faramesh is listed by AARM as
**Aligned**, not **Conformant**; MUTX therefore does not use the integration as
proof of AARM conformance.

Neither audited current-main upstream contains a `NOTICE` file. The verbatim
third-party Apache-2.0 text is retained at
[`third_party/licenses/Apache-2.0.txt`](third_party/licenses/Apache-2.0.txt),
and the verbatim MPL-2.0 text applying to the pinned Core `v0.2.0` release and
historical `v1.2.9` tag is retained at
[`third_party/licenses/MPL-2.0.txt`](third_party/licenses/MPL-2.0.txt). A
Faramesh installation must be evaluated under the license at the exact ref being
distributed; the main-branch relicense does not retroactively change either tag.

### Mission Control

- **Repository:** https://github.com/builderz-labs/mission-control
- **License:** MIT — Copyright (c) 2026 Builderz Labs
- **Current upstream release:** `v2.1.0`
  (`b4ebc5418bea4fa9288a5c17fbddb9ba99740964`)
- **MUTX use:** dashboard briefing and signal-display patterns.

The direct adaptation is pinned to immutable upstream paths and the local port
commit in the attribution ledger. The current upstream release is newer than
that provenance pin; the two are intentionally reported separately.

### Orchestra Research AI-Research-SKILLs

- **Repository:** https://github.com/Orchestra-Research/AI-Research-SKILLs
- **License:** MIT — Copyright (c) 2025 Claude AI Research Skills Contributors
- **Current upstream release:** `v1.7.2`
  (`773a52944ba4747a18bd4ae9ade53fff041adcbc`)
- **MUTX integration pin:**
  `05f1958727bfc2bc22240f41d060504473c4f236`

MUTX imports catalog metadata, curates install bundles and swarm blueprints, and
provides `scripts/sync_orchestra_research_skills.py`. The upstream skill content
remains attributed to Orchestra Research and to the upstream authors documented
in that repository. The difference between the current release and the MUTX pin
is an explicit upgrade gap, not hidden drift.

### predict-rlm

- **Repository:** https://github.com/Trampoline-AI/predict-rlm
- **License:** MIT — Copyright (c) 2026 Trampoline AI
- **Current upstream release:** `v0.7.2`
  (`4ff334dea79a2f27e96b7a50a358b0427050899e`)
- **MUTX provenance pin:**
  `5c7387afa1980b62b21a34ad0261256a95d8caa1`

MUTX uses predict-rlm as the document workflow engine and adapts its workflow
families into MUTX job, artifact, worker, CLI, dashboard, and observability
surfaces. The current upstream release and the historical adaptation pin are
reported separately until compatibility with `v0.7.2` is validated.

## Candidate projects with no direct reuse recorded

### Guild AI

- **Repository:** https://github.com/guildai/guildai
- **License:** Apache-2.0
- **Direct reuse:** none recorded

Guild AI remains a candidate source. If code or documentation is ported later,
the exact upstream commit, local scope, Apache-2.0 license, and any upstream
`NOTICE` material must be recorded in the ledger in the same change.

### LACP

“LACP” is not a sufficient project identity: the repository owner, canonical URL,
and license have not been established. MUTX records no direct reuse from LACP and
makes **no license claim** for it. No LACP port may land until those facts are
resolved and pinned.

## License texts and immutable evidence

The exact upstream license files audited for this record are pinned in the
machine-readable evidence file. MIT-licensed adaptations retain the following
permission text together with each project’s copyright notice above:

```text
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Third-party Apache-2.0 text:
[`third_party/licenses/Apache-2.0.txt`](third_party/licenses/Apache-2.0.txt).
MPL-2.0 text:
[`third_party/licenses/MPL-2.0.txt`](third_party/licenses/MPL-2.0.txt).

## Independence and trademarks

MUTX, agent-run, AARM, Faramesh, Mission Control, Orchestra Research,
predict-rlm, and Guild AI are separate projects. MUTX is not affiliated with or
endorsed by these projects beyond the license grants and integrations described
above. Project names and marks remain the property of their respective owners.
