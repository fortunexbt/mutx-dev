---
description: Short answers to the most common repo and product questions.
icon: question
---

# FAQ

## What is in this repo today?

A Next.js marketing and app surface, a FastAPI backend, a Python CLI, a Python SDK, Docker workflows, and Terraform plus Ansible infrastructure code.

## Is PicoMUTX live?

Yes. `pico.mutx.dev` ships the PicoMUTX landing page, onboarding-first workspace, Academy, grounded Tutor, Support, and Autopilot routes.

## Is there a `/v1` API prefix?

Yes. The current FastAPI app mounts versioned routes such as `/v1/auth`, `/v1/agents`, `/v1/deployments`, and `/v1/webhooks`.

## Can I use the CLI for everything?

Use the CLI for the operator workflows it exposes and the SDK or direct API for the rest of the control-plane contract. The CLI is intentionally not a one-to-one command wrapper for every HTTP endpoint.

Current examples:

- `mutx deploy create` now targets the canonical `POST /v1/deployments` route
- `mutx tui` provides the current operator-focused agents and deployments shell
- `mutx agents create` now relies on authenticated ownership instead of a client-supplied `user_id`

## Is the SDK fully aligned with the API?

The exported `MutxClient` is the supported general-purpose client and its resources use the canonical `/v1/*` base. Resource classes also expose `a*` methods when constructed with an async `httpx` client; the package does not export a separate general-purpose `MutxAsyncClient`.

## Does the contact form persist submissions?

Yes. Public contact and lead requests are validated, persisted before acknowledgement, and protected with idempotency keys. Follow-up notification is best-effort and is reported separately from durable acceptance.

## Do the Playwright tests run against localhost?

Yes. The checked-in Playwright config starts the local standalone app server and targets localhost. Build first when `.next/standalone` is missing, then use `npx playwright test --list` or `./scripts/test.sh` for the repo validation path. In short: build first when `.next/standalone` is missing.

## Are the architecture docs purely current-state?

No. Some architecture docs describe the direction of the platform as well as implemented pieces. For current route and workflow behavior, prefer the README, `docs/README.md`, and the code under `src/api/`, `cli/`, and `sdk/`.

## What license does this repo use?

MUTX core is source-available under BUSL-1.1. The Python SDK is Apache-2.0. See `LICENSE` and `LICENSE-FAQ.md` for details.

Commercial hosted, managed, white-labeled, OEM, and embedded offerings require a separate license from MUTX.
