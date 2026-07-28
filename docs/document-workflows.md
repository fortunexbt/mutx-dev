---
description: Predict-RLM-backed document workflow engine for the dashboard, API, CLI, and worker.
icon: file-text
---

# Document Workflows

MUTX ships a first-class document workflow engine backed by [`predict-rlm`](https://github.com/Trampoline-AI/predict-rlm) from Trampoline AI.

This surface is for file-heavy, operator-visible jobs that need structured outputs, managed artifacts, and run/trace linkage inside MUTX. It is not a runtime provider and it is not an assistant template.

## What ships

- `GET /v1/documents/templates`
- `POST /v1/documents/jobs`
- `GET /v1/documents/jobs`
- `GET /v1/documents/jobs/{job_id}`
- `POST /v1/documents/jobs/{job_id}/artifacts`
- `POST /v1/documents/jobs/{job_id}/dispatch`
- `POST /v1/documents/jobs/{job_id}/launch-local`
- `POST /v1/documents/jobs/{job_id}/events`
- `GET /v1/documents/jobs/{job_id}/artifacts/{artifact_id}`
- Dashboard route: `app.mutx.dev/dashboard/documents`
- CLI group: `mutx documents ...`
- Dedicated worker loop: `python -m src.api.document_worker`

Every document job creates a linked MUTX run so the existing Runs and Traces surfaces remain the canonical observability layer.

The dedicated worker is part of the full server installation, whose `requirements.txt` supplies
SQLAlchemy and the backend runtime. The `mutx-cli` distribution intentionally does not publish a
`mutx-document-worker` console script; Helm and other split deployments invoke the server module
from the API image.

## Templates

MUTX currently exposes these `predict-rlm` template contracts:

- `document_analysis`: uploaded documents -> markdown report + JSON summary
- `contract_comparison`: baseline document + comparison document -> markdown diff report + JSON summary
- `invoice_extraction`: uploaded invoices -> `.xlsx` workbook + JSON summary
- `document_redaction`: uploaded documents + redaction policy -> redacted outputs + verification report + JSON summary

These template ids and output contracts are intentionally aligned with the upstream `predict-rlm` example surface for document analysis, contract comparison, invoice processing, and document redaction.

## Runtime requirements

Document workflows are a hard `predict-rlm` cutover. MUTX no longer falls back to a builtin executor.

Required prerequisites:

- `MUTX_DOCUMENTS_ENABLED=true`
- Python `>= 3.11`
- `deno` on `PATH`
- `predict-rlm>=0.7.3,<1` in the backend environment
- model credentials for the configured providers

Default model wiring:

- `MUTX_DOCUMENTS_LM=openai/gpt-5.4`
- `MUTX_DOCUMENTS_SUB_LM=openai/gpt-5.1`

With the defaults above, `OPENAI_API_KEY` is required. If you point either model at another provider, MUTX expects that provider's credential environment variable instead:

- `openai/...` -> `OPENAI_API_KEY`
- `openrouter/...` -> `OPENROUTER_API_KEY`
- `anthropic/...` -> `ANTHROPIC_API_KEY`

If prerequisites are missing, the document worker still fails fast when it tries to execute `predict-rlm`; managed dispatch and local launch can still queue and build manifests in split deployments.

## Configuration

Relevant backend settings:

- `MUTX_DOCUMENTS_ENABLED`
- `MUTX_ARTIFACTS_DIR`
- `MUTX_DOCUMENT_MAX_UPLOAD_MB`
- `MUTX_DOCUMENT_WORKER_POLL_SECONDS`
- `MUTX_DOCUMENTS_LM`
- `MUTX_DOCUMENTS_SUB_LM`

Readiness is exposed through:

- `mutx doctor`
- desktop bridge health payloads
- document launch/dispatch errors

## CLI flow

List templates:

```bash
mutx documents templates
```

Run a managed document analysis job:

```bash
mutx documents run \
  --template-id document_analysis \
  --mode managed \
  --file ./brief.pdf \
  --instructions "Summarize risks, dates, and counterparties"
```

Run a local redaction job:

```bash
mutx documents run \
  --template-id document_redaction \
  --mode local \
  --file ./input.pdf \
  --redaction-policy "Remove SSNs and account numbers" \
  --output-dir ./out
```

Inspect results:

```bash
mutx documents list
mutx documents get <job-id>
mutx documents download-artifact <job-id> <artifact-id>
```

## Managed vs local execution

Managed mode:

- input files must be uploaded into MUTX-managed storage
- the document worker claims queued jobs and runs `predict-rlm`
- output artifacts are synced back into managed storage automatically

Local mode:

- raw inputs are registered as `local_reference` artifacts
- MUTX returns an execution manifest to the local launcher
- generated outputs are uploaded back into managed storage so the dashboard can inspect them

## Attribution

MUTX does not claim authorship over `predict-rlm` or its upstream example designs.

- Upstream project: [Trampoline-AI/predict-rlm](https://github.com/Trampoline-AI/predict-rlm)
- License: MIT
- Validated upstream release: `v0.7.3`
  (`e7f1e5df7d0188861b39142094b4b738f456972f`)
- Historical adaptation ref: `5c7387afa1980b62b21a34ad0261256a95d8caa1`

The v0.7.3 core document API remains compatible with MUTX's use of `File`,
`Skill`, and `PredictRLM`. The upstream release adds GPT-5.6 support to the
optional `codex-lm` extra; MUTX's document engine uses the core package, so its
template and artifact contracts do not require a migration.

The integration, template alignment, and legal provenance are tracked in:

- [CREDITS.md](../CREDITS.md)
- [Licensing](./legal/index.md)
- [OSS Attribution Ledger](./legal/oss-attribution-ledger.md)
