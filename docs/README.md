---
description: Best entry point for setup, platform references, and operator docs.
title: MUTX Documentation Hub
keywords:
  - MUTX docs
  - AI agent documentation
  - AI agent quickstart
  - AI agent approvals
  - AI agent cost management
icon: book
---

# MUTX Docs

Use this section when you want the code-accurate view of setup, runtime surfaces, and current gaps.

<table data-view="cards">
  <thead>
    <tr>
      <th>Title</th>
      <th>Description</th>
      <th data-hidden data-card-target data-type="content-ref">Target</th>
      <th data-hidden data-card-cover data-type="files">Cover</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Setup and local flow</strong></td>
      <td>Get from clone to a working stack with the shortest validated path.</td>
      <td><a href="deployment/quickstart.md">quickstart.md</a></td>
      <td><a href="../public/landing/victory-core.png">victory-core.png</a></td>
    </tr>
    <tr>
      <td><strong>API and integration reference</strong></td>
      <td>Read the live `/v1/*` contract, auth model, and public resource docs.</td>
      <td><a href="api/">api</a></td>
      <td><a href="../public/landing/wiring-bay.png">wiring-bay.png</a></td>
    </tr>
    <tr>
      <td><strong>Platform architecture</strong></td>
      <td>Understand the shape behind the app, backend, CLI, SDK, and infrastructure.</td>
      <td><a href="architecture/overview.md">overview.md</a></td>
      <td><a href="../public/landing/running-agent.png">running-agent.png</a></td>
    </tr>
    <tr>
      <td><strong>Autonomous agent team</strong></td>
      <td>See the specialist roles, ownership boundaries, and review-safe autonomous shipping model.</td>
      <td><a href="https://github.com/mutx-dev/mutx-dev/blob/main/agents/README.md">agents/README.md</a></td>
      <td><a href="../public/landing/docs-surface.png">docs-surface.png</a></td>
    </tr>
    <tr>
      <td><strong>AI agent cost management</strong></td>
      <td>Read the MUTX page on LLM spend tracking, attribution, and budget enforcement.</td>
      <td><a href="https://mutx.dev/ai-agent-cost">mutx.dev/ai-agent-cost</a></td>
      <td><a href="../public/landing/docs-surface.png">docs-surface.png</a></td>
    </tr>
    <tr>
      <td><strong>AI agent approvals</strong></td>
      <td>Read the MUTX page on human-in-the-loop approval workflows and authorization gates.</td>
      <td><a href="https://mutx.dev/ai-agent-approvals">mutx.dev/ai-agent-approvals</a></td>
      <td><a href="../public/landing/docs-surface.png">docs-surface.png</a></td>
    </tr>
  </tbody>
</table>

- `mutx.dev` = public marketing site and product narrative
- `mutx.dev/releases` = public release summary and conditional desktop artifact handoff
- `mutx.dev/docs` = canonical documentation and API truth surface
- `app.mutx.dev/dashboard` = operator-facing dashboard surface
- `app.mutx.dev/control/*` = operator demo surface

## Start Here

- [Overview](https://github.com/mutx-dev/mutx-dev/blob/main/README.md)
- [MUTX Quickstart](./quickstart.md)
- [Quickstart](./deployment/quickstart.md)
- [Architecture Overview](./architecture/overview.md)
- [Autonomous Agent Team](https://github.com/mutx-dev/mutx-dev/blob/main/agents/README.md)
- [AI Agent Cost Management](https://mutx.dev/ai-agent-cost)
- [AI Agent Approvals](https://mutx.dev/ai-agent-approvals)
- [v1.4 Release Notes](./releases/v1.4.md)
- [v1.5 Release Checklist](./releases/v1.5-checklist.md)
- [Project Status](./project-status.md)
- [Roadmap](https://github.com/mutx-dev/mutx-dev/blob/main/roadmap.md)

## By Area

### Setup And Workflow

- [CLI Guide](./cli.md)
- [Document Workflows](./document-workflows.md)
- [Deployment](./deployment/README.md)
- [Local Developer Bootstrap](./deployment/local-developer-bootstrap.md)

### Platform References

- [API Reference](./api/reference.md)
- [API Overview](./api/index.md)
- [Architecture](./architecture/README.md)
- [Autonomy](./autonomy/README.md)
- [MUTX Infrastructure](https://github.com/mutx-dev/mutx-dev/blob/main/infrastructure.md)
- [Python SDK](https://github.com/mutx-dev/mutx-dev/blob/main/sdk.md)

### Troubleshooting

- [Troubleshooting](./troubleshooting/README.md)
- [Common Issues](./troubleshooting/common-issues.md)
- [Debugging](./troubleshooting/debugging.md)
- [FAQ](./troubleshooting/faq.md)

### Supporting Context

- [Platform Overview](./overview.md)
- [Surface Matrix](./surfaces.md)
- [App and Dashboard](./app-dashboard.md)
- [v1.3 Release Notes](./releases/v1.3.md)
- [v1.3 Release Checklist](./releases/v1.3-checklist.md)
- [Manifesto](https://github.com/mutx-dev/mutx-dev/blob/main/manifesto.md)
- [Technical Whitepaper](https://github.com/mutx-dev/mutx-dev/blob/main/whitepaper.md)

## Truth rules

When docs and code disagree, trust the code:

- `src/api/routes/` for backend behavior
- `app/api/` for browser-facing proxy behavior
- `app/` for site and app surfaces
- `cli/` for terminal workflows
- `sdk/mutx/` for SDK behavior

Current hosted/documented split:

- `mutx.dev` is the public landing site
- `mutx.dev/releases` is the public release summary for the current desktop build
- `mutx.dev/docs` should explain the product and link to the current truth
- `app.mutx.dev/dashboard` is the current operator shell
- `app.mutx.dev/control/*` is the demo shell
- `app/api/` contains the browser-facing same-origin proxies and dashboard fetch layer

## GitBook sync rules

The published docs site is synced from this repository.

- GitHub is the canonical source for synced docs content.
- `.gitbook.yaml` pins GitBook to the repo root and uses `README.md` plus `SUMMARY.md`.
- Do not create or rename README pages from the GitBook UI.
- Keep sidebar changes in `SUMMARY.md`, not in ad hoc GitBook-only content.

If a doc drifts, update the doc or remove the claim.
