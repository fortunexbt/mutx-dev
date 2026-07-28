# Contributing

Thanks for helping improve `mutx.dev`.

## Before You Start

- Read `README.md`, `docs/README.md`, `roadmap.md`, and `docs/project-status.md`.
- Trust the code over older docs when they disagree.
- Keep changes scoped. This repo spans web, API, CLI, SDK, Docker, Terraform, and Ansible.

## Local Setup

Use the canonical quickstart in `docs/deployment/quickstart.md`.

### Quick Start (Makefile)

For rapid local development, use the Makefile targets:

```bash
make help              # Show available targets
make dev               # Start local dev stack (Docker Compose)
make test-auth         # Register test user, login, get token (one-command)
make test-api          # Run API health tests
make test              # Run full test suite
make lint              # Run linters
```

This starts the FastAPI backend on http://localhost:8000 with API docs at http://localhost:8000/docs.

## What To Work On

The best starting points live in:

- `roadmap.md`
- `docs/project-status.md`
- open issues created from those docs

Good contribution shapes:

- API contract fixes
- CLI and SDK alignment
- dashboard/product surface improvements
- docs drift cleanup
- backend tests and CI improvements

## GitBook Sync Guardrails

GitBook is a presentation layer over repo content, not a second source of truth.

- GitHub stays canonical for synced docs content.
- `.gitbook.yaml` pins GitBook to the repo root.
- `README.md` and `SUMMARY.md` are repo-owned and control the published homepage and sidebar.
- Do not create README pages from the GitBook UI.
- Prefer GitHub -> GitBook for the first sync after structural cleanup.

## Pull Requests

- Prefer small PRs by area.
- Link an issue when there is one.
- Explain what changed and why.
- Include the validation commands you ran.
- Update the closest docs when behavior changes.
- Do not bundle unrelated cleanup with the main change.

Recommended split for CLI/TUI distribution work:

- PR 1: release/docs truth plus shared CLI service extraction
- PR 2: `mutx tui` shell and operator flows
- PR 3: Homebrew tap/formula and install docs

### Updating the Changelog

When your change affects users, update [CHANGELOG.md](CHANGELOG.md):

1. Add your change under the `[Unreleased]` section
2. Use the appropriate type:
   - **Added**: New features
   - **Changed**: Changes to existing functionality
   - **Fixed**: Bug fixes
   - **Security**: Security-related changes
3. Be descriptive but concise

Example:
```markdown
### Added
- New `/agents/list` endpoint for bulk agent retrieval
```

## Validation

Use the smallest relevant validation set for your change.

### Frontend

```bash
npm run lint
npm run typecheck
npm run build
```

### Python API, CLI, and SDK

```bash
ruff check src/api cli sdk
ruff format --check src/api cli sdk src/security
python3 -m compileall src/api cli sdk/mutx
```

### CLI/TUI

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,tui]"
mutx --help
mutx status
python -m pytest tests/test_cli_auth_and_tui.py tests/test_cli_agents_contract.py tests/test_cli_deploy_contract.py
```

### Playwright

```bash
npm run build
npx playwright test --list
```

Important: Playwright targets the local standalone app server from `playwright.config.ts`, so build first when `.next/standalone` is missing.

### Helm Chart / Kubernetes

```bash
helm lint infrastructure/helm/mutx
helm template mutx infrastructure/helm/mutx
```

## Release Process

For maintainers releasing new versions:

1. **Update versions** in:
   - `package.json` (frontend/app)
   - root `pyproject.toml` (CLI distribution)
   - `sdk/pyproject.toml` (SDK, when needed)

2. **Update CHANGELOG.md**:
   - Move `[Unreleased]` items to a new version section
   - Add release date
   - Create GitHub Release with the notes

3. **Run validation**:
   ```bash
   npm run release:check
   ```

4. **Tag and publish**:
   - Frontend: `git tag v1.4.0 && git push origin v1.4.0`
   - CLI: `git tag cli-v0.2.1 && git push origin cli-v0.2.1`

5. **Publish the third-party tap**:
   - Push the matching `cli-vX.Y.Z` tag
   - The release workflow regenerates and pushes `mutx-dev/homebrew-tap`
   - If automation fails, run `python scripts/generate_homebrew_formula.py --tag cli-vX.Y.Z --output homebrew-tap/Formula/mutx.rb`
   - Validate with `brew tap mutx-dev/homebrew-tap && brew install mutx && mutx status`

See [docs/changelog-status.md](docs/changelog-status.md) for full release documentation.

## Source Of Truth

When behavior is unclear, inspect:

- `src/api/routes/`
- `cli/commands/`
- `sdk/mutx/`
- `docker-compose.yml`
- `infrastructure/docker/docker-compose.prod.yml`
- `infrastructure/helm/mutx/` (Kubernetes/Helm chart and K8s manifests)

## Questions And Support

See `support.md`.

## Licensing

MUTX core is source-available under [BUSL-1.1](LICENSE). The Python SDK is licensed under [Apache-2.0](sdk/LICENSE).

By contributing to this repository, you confirm that your contributions do not conflict with these license terms. If you are contributing significant new code, ensure your employer or legal counsel is aware of the licensing terms.

For commercial licensing questions, contact hello@mutx.dev.
