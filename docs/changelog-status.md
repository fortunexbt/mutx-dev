# Changelog and Release Notes

This page covers where to track MUTX changes, release processes, and live status for demos and integrations.

## Status Sources

- API health: `GET https://api.mutx.dev/health`
- API readiness: `GET https://api.mutx.dev/ready`
- Website availability: `https://mutx.dev`
- Release summary: `https://mutx.dev/releases`
- App availability: `https://app.mutx.dev/dashboard` (stable operator routes)
- Control demo availability: `https://app.mutx.dev/control`
- Docs availability: `https://mutx.dev/docs`

## Changelog

The canonical changelog lives at [CHANGELOG.md](https://github.com/mutx-dev/mutx-dev/blob/main/CHANGELOG.md) in the repository root.

The canonical public release narrative for the current launch lives at [docs/releases/v1.4.md](./releases/v1.4.md), with the public website summary at `mutx.dev/releases`.

### Changelog Sources

- GitHub releases: `https://github.com/mutx-dev/mutx-dev/releases`
- Merged pull requests: `https://github.com/mutx-dev/mutx-dev/pulls?q=is%3Apr+is%3Amerged`
- OpenAPI contract diff: compare revisions of [`docs/api/openapi.json`](https://github.com/mutx-dev/mutx-dev/blob/main/docs/api/openapi.json)

## Release Process

### Version Bumping

When preparing a release:

1. **Update version numbers** in:
   - `package.json` (frontend/app version, if needed)
   - root `pyproject.toml` (CLI distribution version)
   - `sdk/pyproject.toml` (SDK version, only when shipping the SDK)

2. **Update CHANGELOG.md**:
   - Move items from `[Unreleased]` to the new version section
   - Add the release date
   - Use appropriate version type (Major/Minor/Patch)

3. **Create GitHub Release**:
   - Tag format: `v1.4.0` (web/app/desktop) and `cli-v1.4.0` (CLI distribution)
   - Use the matching `docs/releases/vX.Y.md` page as the release notes body when available
   - Keep the attached desktop assets plus checksums on GitHub Releases

4. **Publish the docs-backed release narrative**:
   - Merge `docs/releases/v1.4.md`
   - Verify the self-hosted docs publish `https://mutx.dev/docs/releases/v1.4`
   - Keep `mutx.dev/releases` aligned with the same version and download contract
   - Keep `mutx.dev/download/macos/release-notes` resolving to that synced page

5. **Promote production on Railway**:
   - Run the Railway production-promotion workflow or `bash scripts/promote-railway-production.sh`
   - Verify `mutx.dev`, `app.mutx.dev/dashboard`, `api.mutx.dev/health`, and `api.mutx.dev/ready`

### Release Validation

Run the release check script before publishing:

```bash
# Fail-closed release validation
npm run release:check
```

Or manually:

```bash
# Lint
npm run lint

# Build
npm run build

# Signed desktop release validation
npm run desktop:release:validate
```

### Python CLI Release

```bash
# Build the CLI distribution from repo root
python -m pip install build
python -m build
```

Then push the matching `cli-vX.Y.Z` tag. The release workflow updates the published Homebrew tap automatically; use the manual formula flow only if that automation fails:

```bash
python scripts/generate_homebrew_formula.py --tag cli-v1.4.0 --output homebrew-tap/Formula/mutx.rb
brew tap mutx-dev/homebrew-tap
brew install mutx
mutx --help
mutx setup --help
mutx doctor --help
```

## Versioning

This project uses [Semantic Versioning](https://semver.org/):

| Component | Version Location |
|-----------|------------------|
| Frontend/App | `package.json` |
| CLI distribution | root `pyproject.toml` |
| Python SDK | `sdk/pyproject.toml` |

See [CHANGELOG.md](https://github.com/mutx-dev/mutx-dev/blob/main/CHANGELOG.md) for details on versioning scheme.

## Contract Notes (Current)

- FastAPI routes are mounted under `/v1/*` in [`src/api/main.py`](https://github.com/mutx-dev/mutx-dev/blob/main/src/api/main.py).
- Ingestion routes are mounted at `/v1/ingest/*`.
- Webhook destination management is mounted at `/v1/webhooks/*`.
- Deployment event history is available at `GET /v1/deployments/{deployment_id}/events`.

## Docs publication notes

- GitHub is the canonical source for synced docs content.
- GitBook publication is rooted at the repo root through `.gitbook.yaml`.
- `README.md` and `SUMMARY.md` are repo-owned docs entrypoints and should not be recreated from the GitBook UI.
- Release notes for the public launch should live in repo-owned docs pages such as `docs/releases/v1.4.md`, not only in GitHub release prose.

## Related Planning Docs

- [v1.3 Release Notes](./releases/v1.3.md)
- [v1.4 Release Notes](./releases/v1.4.md)
- [v1.4 Release Checklist](./releases/v1.4-checklist.md)
- [v1.5 Release Checklist](./releases/v1.5-checklist.md)
- [Project Status](./project-status.md)
- [Roadmap](https://github.com/mutx-dev/mutx-dev/blob/main/roadmap.md)
- [API Reference](./api/reference.md)
- [Contributing](https://github.com/mutx-dev/mutx-dev/blob/main/CONTRIBUTING.md)
- [CLI Reference](./cli.md)
- [CLI Release Runbook](./deployment/cli-release.md)
