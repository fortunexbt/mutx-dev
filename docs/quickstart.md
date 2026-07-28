---
title: MUTX Quickstart
description: Fastest path to install MUTX, authenticate an operator, deploy the Personal Assistant starter, and inspect the runtime from the CLI, TUI, or browser control plane.
keywords:
  - MUTX quickstart
  - AI agent quickstart
  - AI agent deployment quickstart
  - AI agent control plane
  - operator onboarding
icon: rocket
---

# MUTX Quickstart

This is the fastest decision guide for getting started with MUTX.

Use this page when you want to answer three questions before you install anything:

1. Which quickstart lane should you use?
2. What does the installer actually set up?
3. Which guide gets you to a working starter assistant fastest?

The full step-by-step instructions live in [Deployment Quickstart](/docs/deployment/quickstart). This page explains the shortest path and what success looks like.

## Quick answer

For most operators, the shortest validated path is:

```bash
curl -fsSL https://mutx.dev/install.sh | bash
```

That installer keeps you inside a MUTX onboarding wizard in the same terminal. It can authenticate your operator session, install or import OpenClaw, deploy the `Personal Assistant` starter, and leave you with a runtime you can inspect from the CLI or TUI.

## Choose your lane

| Lane | Best for | What you get | Read next |
| --- | --- | --- | --- |
| Hosted operator | The fastest path to a working AI agent control plane | Stored auth session, tracked OpenClaw runtime, deployed starter assistant, operator surfaces | [Deployment Quickstart](/docs/deployment/quickstart) |
| Local operator | Private localhost testing on your own machine | Local control plane, local dashboard, tracked runtime, deployed starter assistant | [Deployment Quickstart](/docs/deployment/quickstart#local-operator) |
| Repo contributor | Developers changing MUTX itself | Local repo services plus the same local operator flow | [Local Developer Bootstrap](/docs/deployment/local-developer-bootstrap) |

## What success looks like

Every supported quickstart lane ends with the same operator-first outcome:

1. You have a stored authenticated session in `~/.mutx/config.json`.
2. You have deployed the `Personal Assistant` starter template.
3. MUTX is tracking the bound OpenClaw runtime under `~/.mutx/providers/openclaw`.
4. You can inspect the assistant with `mutx doctor`, `mutx assistant overview`, `mutx runtime inspect openclaw`, and `mutx runtime open openclaw --surface tui`.

## What the installer sets up

The recommended installer handles the practical bootstrapping work most teams would otherwise do by hand:

* authenticate the operator account
* detect or install OpenClaw
* write the tracked runtime manifest and bindings
* deploy the `Personal Assistant` starter
* open an operator surface so you can verify the runtime immediately

If you want to understand the exact commands and branching logic, go straight to [Deployment Quickstart](/docs/deployment/quickstart).

## After the quickstart

Once the starter assistant is live, these pages are the highest-value next reads:

* [Deployment Quickstart](/docs/deployment/quickstart) for the full hosted and local command paths
* [Architecture Overview](/docs/architecture/overview) for the code-accurate system map
* [API Reference](api/reference.md) for the public `/v1/*` contract
* [AI Agent Cost Management](/ai-agent-cost) for spend visibility and budget controls
* [AI Agent Approvals](/ai-agent-approvals) for human-in-the-loop controls
