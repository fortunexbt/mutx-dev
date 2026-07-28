---
description: Legacy contract notes retained so old links do not hard-break.
icon: scale-balanced
---

# Legacy Contract Notes

This `docs/contracts/` tree is no longer the public API source of truth.

Use the repo-owned API docs in [`../api/reference.md`](../api/reference.md) instead.

## Canonical Contract Order

1. `src/api/main.py` and `src/api/routes/*.py`
2. [`docs/api/openapi.json`](https://github.com/mutx-dev/mutx-dev/blob/main/docs/api/openapi.json)
3. `docs/api/*.md`

## Generated Artifacts

```bash
python scripts/generate_openapi.py
npm run generate-types
```

## Why This Directory Still Exists

- preserve old GitBook and GitHub links
- avoid breaking existing references immediately
- redirect readers to the repo-owned `docs/api/*` pages

## Use These Pages Instead

- [API Overview](../api/index.md)
- [API Reference](../api/reference.md)
- [Authentication](../api/authentication.md)
- [API Keys](../api/api-keys.md)
- [Agents](../api/agents.md)
- [Deployments](../api/deployments.md)
- [Webhooks And Ingestion](../api/webhooks.md)
- [Leads](../api/leads.md)
