# Continuous Integration

MUTX has one authoritative pull-request and `main` validation workflow:
`.github/workflows/ci.yml`. Its stable branch-protection result is
`CI / Required Validation`.

## Validation architecture

`CI` always runs workflow contract checks. On pull requests, changed-surface
filters select the relevant Python, frontend, infrastructure, production
Compose, and container gates. Changes to workflow or checker code select every
gate. Pushes to `main`, merge-queue runs, and manual dispatches run the complete
monorepo suite regardless of the diff.

The required result runs with `if: always()` and accepts only successful or
intentionally skipped dependencies. A failed or cancelled selected job, or a
failed changed-surface detector, therefore cannot become a green required check.

The full gates are:

- Python tests and compile checks on 3.10, 3.11, and 3.12, with the reviewed
  Ruff 0.15.22 toolchain pinned on 3.11
- Node 24.15.0 unit, generated-contract, lint, typecheck, build, and browser checks
- Terraform, Ansible, Dockerfile, Compose, monitoring, and Helm validation
- isolated production Compose smoke testing
- production frontend and API image builds with fail-closed critical Trivy scans

All Linux jobs use the explicit Ubuntu 24.04 image, and all third-party GitHub
Actions are pinned to full commit SHAs. Dependency caches are scoped by their
lockfiles or dependency manifests. Superseded pull-request runs are cancelled,
while `main`, merge-queue, release, deployment, and drift runs are retained as
immutable evidence.

Python validation installs `requirements-ci.lock`; API images install the
smaller `requirements-runtime.lock`. Both files are universal, fully resolved,
SHA-256-pinned outputs from uv 0.11.33, and installs run with both
`--require-hashes` and `--only-binary=:all:`. This prevents a repeated commit
from silently selecting new transitive dependencies or unreviewed source-build
toolchains. Regenerate both locks after changing `requirements.txt`,
`test-requirements.txt`, or Python project metadata:

```bash
uv pip compile requirements.txt --universal --generate-hashes --no-annotate \
  --exclude-newer 2026-07-28 --output-file requirements-runtime.lock
uv pip compile test-requirements.txt pyproject.toml --extra dev --universal \
  --generate-hashes --no-annotate --exclude-newer 2026-07-28 \
  --output-file requirements-ci.lock
```

Production Node and Python base images are pinned to reviewed multi-platform
image digests. Container builds do not run blanket OS upgrades.

Infrastructure validation also pins Ansible Core 2.21.2, ansible-lint 26.6.0,
and every Galaxy collection in `infrastructure/ansible/requirements.yml` so a
new upstream release cannot change lint or playbook behavior mid-run. Terraform
1.15.8, Helm 3.21.3, and Trivy 0.72.0 are likewise explicit reviewed versions;
Helm remains on its supported v3 line until a separate v4 compatibility change.

## Supporting workflows

- `ci-health.yml` maintains one open issue for a current `main` CI incident. It
  updates that issue in place and resolves it after the newest successful run;
  it also retires duplicate incidents left by the removed autofix workflow. It
  never edits code, pushes commits, or comments on pull requests.
- `infrastructure-drift.yml` retains the opt-in, fail-closed Terraform drift
  check and runs a metadata-only upstream dependency audit on the same existing
  daily/manual cadence. Terraform inputs come from protected environment-specific
  `TF_VARS_STAGING` and `TF_VARS_PRODUCTION` secrets. Saved plans are never
  uploaded because Terraform plan files can contain cleartext sensitive values.
  Upstream JSON reports remain short-lived artifacts; upstream drift is reported
  for review while registry, API, and immutable-pin errors fail the job. The
  workflow never updates pins or source.
- `release.yml` and `railway-production-promotion.yml` retain non-cancelling
  release concurrency, immutable target checks, environment protections, and
  post-promotion verification. Python publication uses the reviewed uv 0.11.33,
  build 1.5.0, and Twine 6.2.0 toolchain. Railway promotion downloads the
  reviewed 5.30.1 Linux binary from its upstream GitHub release and verifies
  the published SHA-256 digest before execution. Its two reusable-workflow call
  sites explicitly inherit the repository Railway secrets.

## Branch-protection migration

Require only `CI / Required Validation` for new changes. Remove the retired
`Infrastructure CI`, `Infrastructure Validation`, and their individual job
contexts after confirming the new result has completed at least once on the
default branch. Do not weaken release environments or tag protections as part
of this migration.

GitHub's public run history shows two GitHub-managed workflows named `CodeQL`
for each `main` push. They are intentional, distinct products: organization-
managed CodeQL default setup reports security findings, while repository Code
Quality reports maintainability findings. Keep both enabled. No advanced CodeQL
analysis workflow is checked into this repository; checked-in CI contains only
the Trivy SARIF uploader, preventing a redundant third CodeQL analysis lane.

## Local validation

Run the focused workflow contracts with:

```bash
python -m pytest tests/unit/python/test_ci_workflow_contract.py \
  tests/unit/python/test_ci_compose_release_gate.py \
  tests/unit/python/test_upstream_drift.py -q
```

When installed, run `actionlint` across `.github/workflows/*.yml` and
`yamllint .github/workflows`. YAML parsing is also covered by the Python
workflow contract tests.
