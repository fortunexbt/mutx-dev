---
description: How to choose work, stay truthful, and submit clean MUTX contributions.
icon: handshake
---

# Contributing

Thanks for helping improve `mutx.dev`.

## Before You Start

* Read `README.md`, `docs/README.md`, `roadmap.md`, and `docs/project-status.md`.
* Trust the code over older docs when they disagree.
* Keep changes scoped. This repo spans web, API, CLI, SDK, Docker, Terraform, and Ansible.

## Local Setup

Use the canonical quickstart in `docs/deployment/quickstart.md`.

## What To Work On

The best starting points live in:

* `roadmap.md`
* `docs/project-status.md`
* open issues created from those docs

Good contribution shapes:

* API contract fixes
* CLI and SDK alignment
* dashboard/product surface improvements
* docs drift cleanup
* backend tests and CI improvements

## GitBook Sync Guardrails

GitBook should render repo truth, not compete with it.

* GitHub stays canonical for synced docs content.
* `.gitbook.yaml` pins GitBook to the repo root.
* `README.md` and `SUMMARY.md` are repo-owned and control the published homepage and sidebar.
* Do not create README pages from the GitBook UI.
* Prefer GitHub -> GitBook for the first sync after structural cleanup.

## Pull Requests

* Prefer small PRs by area.
* Link an issue when there is one.
* Explain what changed and why.
* Include the validation commands you ran.
* Update the closest docs when behavior changes.
* Do not bundle unrelated cleanup with the main change.

## Validation

Use the smallest relevant validation set for your change.

### Frontend

```bash
npm run lint
npm run build
```

### Python API, CLI, and SDK

```bash
ruff check src/api cli sdk
ruff format --check src/api cli sdk src/security
python3 -m compileall src/api cli sdk/mutx
```

### Playwright

```bash
npm run build
npx playwright test --list
```

Important: Playwright targets the local standalone app server from `playwright.config.ts`, so build first when `.next/standalone` is missing.

## Source Of Truth

When behavior is unclear, inspect:

* `src/api/routes/`
* `cli/commands/`
* `sdk/mutx/`
* `docker-compose.yml`
* `infrastructure/docker/docker-compose.prod.yml`
* `infrastructure/helm/mutx/` (Kubernetes Helm chart and K8s manifests)

## Questions And Support

See `support.md`.
