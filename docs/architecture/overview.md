---
title: AI Agent Control Plane Architecture Overview
description: Code-accurate map of the MUTX architecture across the Next.js operator surface, FastAPI control plane, CLI, SDK, docs, and deployment tooling.
keywords:
  - AI agent architecture
  - AI agent control plane architecture
  - MUTX architecture
  - FastAPI control plane
  - Next.js operator dashboard
icon: sitemap
---

# AI Agent Control Plane Architecture Overview

This page describes the architecture that is visible in the MUTX repo today.

When docs and code disagree, trust the executable system:

* `app/` for the Next.js website, docs, and operator surfaces
* `app/api/` for browser-facing route handlers and proxies
* `src/api/` for the FastAPI control plane, services, middleware, and integrations
* `cli/` for terminal workflows
* `sdk/mutx/` for the Python SDK
* `infrastructure/` for Terraform, Ansible, monitoring, and Helm

## High-level architecture

| Layer | Entry point | Code location | What it owns |
| --- | --- | --- | --- |
| Public web surface | Browser and docs users | `app/`, `components/`, `lib/` | marketing pages, docs rendering, download flows, and dashboard shells |
| Same-origin browser API | Web UI requests that need server-side handling | `app/api/` | browser-facing route handlers and proxy behavior |
| Public control plane | Browser proxies, CLI, and SDK clients | `src/api/` | `/v1/*` routes, auth, RBAC, OIDC, tracing, and service orchestration |
| Operator tooling | Terminal users and Python integrations | `cli/`, `sdk/mutx/` | command workflows and typed access to the public API contract |
| Runtime dependencies | Control-plane services | Postgres, Redis, telemetry, and external runtimes | state, queues or cache support, traces, and downstream execution |

The shortest accurate flow is:

* Browser or docs user -> Next.js surface -> `app/api/` when same-origin behavior is needed -> FastAPI control plane -> Postgres, Redis, telemetry, and external runtimes
* CLI or SDK client -> public `/v1/*` API -> FastAPI control plane -> the same service and data layers

## Current shipped surfaces

MUTX is split into a small number of visible surfaces:

| Surface | Code location | Responsibility |
| --- | --- | --- |
| Website and docs | `app/`, `components/`, `lib/` | Marketing pages, docs rendering, metadata, public download and narrative surfaces |
| Browser-facing route handlers | `app/api/` | Same-origin request handling and proxy behavior for the web app |
| Control plane API | `src/api/` | FastAPI routes, services, models, middleware, integrations, auth, and policy enforcement |
| CLI | `cli/` | Click-based operator commands for setup, inspection, and workflow automation |
| Python SDK | `sdk/mutx/` | Thin typed wrappers around the public API contract |
| Infrastructure | `infrastructure/` | Terraform, Ansible, monitoring validation, and Helm deployment assets |

## Public API shape

The public control-plane contract is mounted under `/v1/*`.

Root probes stay at:

* `/`
* `/health`
* `/ready`
* `/metrics`

Route registration is centralized in `src/api/main.py`. Route-level access control is enforced through dependencies under `src/api/routes/`, with the security layer implemented in `src/api/security.py`.

## Request flow

The highest-level request paths look like this:

### Browser path

1. A user lands on a Next.js surface in `app/`.
2. The page renders marketing, docs, or operator UI.
3. When browser-specific proxy behavior is needed, the request goes through `app/api/`.
4. Control-plane state ultimately resolves through the FastAPI backend or other configured integrations.

### CLI and SDK path

1. A CLI command or SDK method issues a request against the public `/v1/*` API.
2. FastAPI route handlers validate input, check auth and role boundaries, and dispatch into service code.
3. Services talk to the database, runtime integrations, monitoring systems, or approval and policy layers.
4. Responses are wrapped back into CLI output or SDK objects.

## Control plane layers

The backend is organized so route handlers stay relatively thin and most behavior lives in services, middleware, and models.

### Identity and access

MUTX enforces authentication and persisted-role checks on protected routes; public
probes, account-entry flows, and lead capture remain anonymous by design. The
generic OIDC validation utility lives in `src/api/auth/oidc.py` and is configured
through:

* `OIDC_ISSUER`
* `OIDC_CLIENT_ID`
* `OIDC_JWKS_URI`

Mounted SSO callbacks use provider-specific domain/client settings, bind the
verified external identity to a local user, and issue a MUTX JWT. Canonical
protected routes do not directly accept arbitrary provider bearer tokens.

This matters architecturally because authorization is not an afterthought at the edge. It is part of the route and dependency layer.

### Routing and services

The route registry in `src/api/main.py` exposes the main control-plane modules, including:

* agents
* deployments
* templates
* approvals
* budgets
* sessions
* observability
* telemetry
* monitoring
* runtime
* security

### Data and state

The repo uses Postgres-backed application state and Redis-backed runtime or queue support where configured. The exact data model lives in `src/api/models/` and the async database patterns live under `src/api/database.py` and the service layer.

## Observability and trace propagation

Distributed tracing is a first-class concern in the codebase.

Current observability touchpoints include:

* OpenTelemetry span naming under the `mutx.*` namespace
* trace propagation through middleware in `src/api/middleware/tracing.py`
* an internal-admin, tenant-scoped telemetry config route at `GET /v1/telemetry/config`
* dashboard and docs surfaces that explain runtime history, traces, and monitoring

That gives the architecture a useful property: web UI, API clients, and runtime operators can speak about the same run, session, and trace identifiers.

## Deployment shapes

Deployment tooling exists in several layers:

* Terraform targets under `infrastructure/terraform`
* Ansible targets under `infrastructure/ansible`
* monitoring validation targets under `infrastructure/`
* a Helm chart for Kubernetes deployment under `infrastructure/helm/`

This is why the architecture spans more than the FastAPI app. MUTX includes the operator surface, the public API, client tooling, and the deployment assets that move the control plane into real environments.

## Related control surfaces

Some architecture questions are easier to answer from adjacent pages:

* [Deployment Quickstart](/docs/deployment/quickstart) for the shortest supported install and setup path
* [API Reference](../api/reference.md) for the public `/v1/*` contract
* [AI Agent Approvals](/ai-agent-approvals) for human approval gates in the control plane
* [AI Agent Cost Management](/ai-agent-cost) for spend visibility and budget controls
* [Autonomous Agent Team](https://github.com/mutx-dev/mutx-dev/blob/main/agents/README.md) for the specialist roles used in autonomous shipping workflows

## Summary

The simplest accurate mental model is:

* Next.js serves the public and operator-facing web surfaces.
* FastAPI owns the public control-plane contract under `/v1/*`.
* CLI and SDK clients ride that same contract.
* Auth, RBAC, tracing, approvals, budgets, and runtime services live in the backend.
* Terraform, Ansible, and Helm carry the system into real environments.
