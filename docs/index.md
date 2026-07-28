---
description: Best entry point for setup, platform references, and operator docs.
icon: book
---

# MUTX Docs

Setup, platform references, and operator docs — code-accurate view of the stack.

<table data-view="cards">
  <thead>
    <tr>
      <th>Title</th>
      <th>Description</th>
      <th data-hidden data-card-target data-type="content-ref">Target</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Setup and local flow</strong></td>
      <td>Get from clone to a working stack with the shortest validated path.</td>
      <td><a href="deployment/quickstart.md">quickstart.md</a></td>
    </tr>
    <tr>
      <td><strong>API and integration reference</strong></td>
      <td>Read the live `/v1/*` contract, auth model, and public resource docs.</td>
      <td><a href="api/">api</a></td>
    </tr>
    <tr>
      <td><strong>Platform architecture</strong></td>
      <td>Understand the shape behind the app, backend, CLI, SDK, and infrastructure.</td>
      <td><a href="architecture/README.md">architecture</a></td>
    </tr>
    <tr>
      <td><strong>v1.3 release notes</strong></td>
      <td>Current public release posture, supported surfaces, and download path.</td>
      <td><a href="releases/v1.3.md">v1.3.md</a></td>
    </tr>
    <tr>
      <td><strong>Troubleshooting and support</strong></td>
      <td>Recover quickly when local setup, auth, or route assumptions drift.</td>
      <td><a href="troubleshooting/README.md">troubleshooting</a></td>
    </tr>
  </tbody>
</table>

## Platform surfaces

- `mutx.dev` — public marketing site and product narrative
- `mutx.dev/releases` — public release summary and conditional desktop artifact handoff
- `mutx.dev/docs` — canonical documentation and API truth surface
- `app.mutx.dev/dashboard` — operator-facing dashboard surface
- `app.mutx.dev/control/*` — operator demo surface

## Quick links

| Area | Pages |
|------|-------|
| **Setup** | [Quickstart](./deployment/quickstart.md) · [CLI Guide](./cli.md) · [Local Developer Bootstrap](./deployment/local-developer-bootstrap.md) |
| **API** | [API Reference](./api/reference.md) · [API Overview](./api/index.md) · [Authentication](./api/authentication.md) |
| **Platform** | [Architecture](./architecture/README.md) · [Autonomy](./autonomy/README.md) · [Infrastructure](https://github.com/mutx-dev/mutx-dev/blob/main/infrastructure.md) · [Python SDK](https://github.com/mutx-dev/mutx-dev/blob/main/sdk.md) |
| **Releases** | [v1.3 Notes](./releases/v1.3.md) · [v1.4 Notes](./releases/v1.4.md) · [v1.3 Checklist](./releases/v1.3-checklist.md) · [v1.4 Checklist](./releases/v1.4-checklist.md) · [v1.5 Checklist](./releases/v1.5-checklist.md) |
| **Troubleshooting** | [Common Issues](./troubleshooting/common-issues.md) · [Debugging](./troubleshooting/debugging.md) · [FAQ](./troubleshooting/faq.md) |
| **Context** | [Surface Matrix](./surfaces.md) · [Project Status](./project-status.md) · [App Dashboard](./app-dashboard.md) |

## Truth rules

When docs and code disagree, trust the code:

- `src/api/routes/` for backend behavior
- `app/api/` for browser-facing proxy behavior
- `app/` for site and app surfaces
- `cli/` for terminal workflows
- `sdk/mutx/` for SDK behavior

## GitBook sync rules

The published docs site is synced from this repository.

- GitHub is the canonical source for synced docs content.
- `.gitbook.yaml` pins GitBook to the repo root and uses `README.md` plus `SUMMARY.md`.
- Do not create or rename README pages from the GitBook UI.
- Keep sidebar changes in `SUMMARY.md`, not in ad hoc GitBook-only content.

If a doc drifts, update the doc or remove the claim.
