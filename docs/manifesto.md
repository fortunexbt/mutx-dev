---
description: Why MUTX focuses on control planes, operational trust, and systems over demos.
icon: bullseye
---

# MUTX Manifesto

## We Do Not Think The Hard Part Is The Model

The hardest part of agentic software is not generating tokens.
It is turning token generation into something a team can trust, operate, budget, debug, and ship.

That is the problem MUTX exists to solve.

We believe the next wave of software will be built around agents that can reason, call tools, write state, react to events, and operate continuously. But we also believe most of the market is still focused on the easiest layer to demo and the least important layer to own: prompts, wrappers, and orchestrated screenshots.

The real bottleneck is everything that happens after the demo works once.

## The Real Failure Mode

Agent projects usually do not die because the model is too weak.
They die because the surrounding system is too weak.

They die when:

- identity is unclear
- ownership is not enforced
- deployments are implicit instead of modeled
- secrets and API keys are bolted on late
- webhooks have no real governance layer
- logs and metrics exist, but nobody can trust them
- the website, API, CLI, SDK, and infra all drift apart
- local success cannot survive production reality

This is not a prompt engineering problem.
It is a systems problem.

## Our Thesis

Infrastructure is the constraint.
Control planes are the wedge.
Operational trust is the product.

If agents are going to do real work, they need to be treated like production systems, not novelty interfaces.
That means:

- explicit control planes
- durable state
- reproducible deployments
- real authentication and ownership
- observable execution
- cost visibility
- open interfaces
- honest contracts between code, docs, and product surfaces

## What MUTX Is

MUTX is a source-available control plane for AI agents.

It is not just an API.
It is not just a dashboard.
It is not just a CLI.
It is not just an SDK.

It is the layer that ties all of those together so agent systems become operable.

In practical terms, that means MUTX is being built to handle the surfaces around agents that teams actually need:

- auth and user identity
- agent records and lifecycle actions
- deployment records and lifecycle actions
- API key management
- webhook ingestion and outbound automation hooks
- health, readiness, logs, and metrics surfaces
- website and app experiences that reflect the real platform
- infrastructure automation that does not live outside the product story

## What MUTX Is Not

We are not building a closed model lab.
We are not building a token resale business.
We are not pretending a demo runtime is a platform.
We are not interested in fake enterprise theater.

We care more about a system that is honest, operable, and extensible than a product that looks finished while hiding brittle assumptions underneath.

## Our Principles

### 1. Current-State Honesty
The repo should say what exists, what works, what is rough, and what is still aspirational.

### 2. Control Over Magic
A boring, explicit control plane is more valuable than clever hidden behavior.

### 3. Open Interfaces
The website, API, CLI, SDK, docs, and infrastructure should reinforce each other instead of drifting into parallel realities.

### 4. Cost Transparency
The platform should make model and infrastructure cost easier to reason about, not harder.

### 5. Operational Trust
If an operator cannot answer who owns a resource, what changed, what failed, and what to do next, the platform is unfinished.

### 6. Small Surfaces, Strong Guarantees
We would rather have a smaller system with real semantics than a larger one full of implied behavior.

## Why Source Availability

Agent infrastructure should be inspectable.
The control layer around deployment, auth, API keys, and operational workflows should not be magic.

MUTX core is source-available under the Business Source License (BUSL-1.1), with each release converting to Apache-2.0 after 36 months.
Source availability forces clarity.
It sharpens interfaces.
It reveals drift.
It invites the right contributors.
And it creates the conditions for a real platform, not just a proprietary wrapper around the same problems.

## Where We Are Going

The destination is not "an AI app."
The destination is an operating layer for agent systems.

Near term, that means tightening contracts, hardening auth and ownership, improving the app surface, and making the CLI, SDK, and API tell the same story.
Long term, that means turning agent execution, deployment, observability, and governance into a coherent product surface teams can actually build on.

## The Invitation

If you care about:

- agent systems that survive contact with reality
- infrastructure that is more than marketing copy
- honest product architecture
- source-available platforms with real operational depth

then MUTX is for you.

Build with us.
Break the edges.
Tighten the contracts.
Help turn the control plane into the product.

**Deploy agents like you deploy services. Operate them like systems.**
