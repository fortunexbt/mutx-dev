# Activation Guide

This repository includes an operator-controlled autonomy substrate. Autonomous
execution runs from a trusted local host and hands changes to GitHub through
reviewable pull requests. The former scheduled GitHub-hosted dispatch and
shipping workflows were retired; CI validates code but never authors or pushes
it.

## What Is Already In Repo

- agent definitions under `agents/`
- ownership map in `agents/registry.yml`
- bounded local daemon and lane runners under `scripts/autonomy/`
- scoped intake template in `.github/ISSUE_TEMPLATE/agent-task.yml`
- immutable CI and PR templates for truthful validation

## Smallest Real Deployment

1. Protect `main` and require `CI / Required Validation` in GitHub.
2. Create the labels from `docs/autonomy/OPERATING_MODEL.md`.
3. Provision a trusted operator host with GitHub CLI authentication, Python
   3.11+, and Node 24.15+.
4. Configure the executor variables below on that host. Keep model credentials
   out of repository variables and workflow files.
5. Start the daemon with `scripts/autonomy/daemon-launcher.sh start`.
6. Run `scripts/autonomy/daemon-watchdog.sh` from a local service manager or a
   2–5 minute cron interval.
7. Monitor `.autonomy/daemon-status.json` and `reports/autonomy-status.jsonl`.
8. Require every authored branch to pass CI and review before merge.

## Operator Host Shape

- trusted, access-controlled host
- dedicated repository checkout and bounded worktrees
- GitHub CLI authenticated as the operator or a least-privilege bot
- Python 3.11+ and Node 24.15+

## Executor Variables

- `AUTONOMY_AGENT_CMD_TEMPLATE`: command template invoked after branch prep
- `AUTONOMY_OPEN_PR`: `true` or `false`
- `AUTONOMY_BASE_BRANCH`: optional, defaults to `main`
- `AUTONOMY_BRIEF_DIR`: optional, defaults to `.autonomy/briefs`
- `AUTONOMY_MODEL`: optional, defaults to `gpt-4.1-mini`
- `AUTONOMY_MAX_PATCH_BYTES`: optional, defaults to `50000`
- `AUTONOMY_MAX_CHANGED_FILES`: optional, defaults to `6`
- `AUTONOMY_REVIEWER_MAP`: optional JSON object mapping reviewer-agent ids to GitHub logins

## Executor Credentials

- `GITHUB_MODELS_TOKEN`: preferred by `scripts/autonomy/hosted_llm_executor.py`
- `OPENAI_API_KEY`: alternate provider when GitHub Models is not used

Set credentials only in the trusted host environment or its secret manager.
They are not CI secrets because no checked-in workflow runs the executor.

Example:

```text
AUTONOMY_AGENT_CMD_TEMPLATE=python scripts/autonomy/github_hosted_agent.py --agent {agent} --brief {brief} --work-order {work_order}
AUTONOMY_OPEN_PR=true
```

If `AUTONOMY_AGENT_CMD_TEMPLATE` is unset but `GITHUB_MODELS_TOKEN` or
`OPENAI_API_KEY` is present, the local executor falls back to:

```text
python scripts/autonomy/hosted_llm_executor.py --agent {agent} --brief {brief} --work-order {work_order}
```

If a generated patch exceeds the configured size or file-count guardrails, the executor stops and writes `.autonomy/guardrail-failure.json` for debugging.

If `AUTONOMY_REVIEWER_MAP` is set, the executor also assigns the mapped GitHub login to the PR and leaves a reviewer-routing comment.

When the executor opens or updates a PR, it also posts the required handoff comment: `@codex please review` (idempotent if already present).

The daemon records queue and lane health in `.autonomy/daemon-status.json` and
`reports/autonomy-status.jsonl`. Stale local running items are recovered by the
queue-state contract; GitHub issue labels remain an operator-owned signal and
must not be treated as a distributed lock.

## Dispatch Logic

Use `scripts/autonomy/select_agent.py` to map labels to a specialist and release lane.
Use `scripts/autonomy/build_work_order.py` to pick the highest-priority unclaimed issue and create an executor-ready work order.
Use `scripts/autonomy/execute_work_order.py` to create the branch, write the brief, optionally comment on the issue, invoke the hosted coding command, and optionally open a draft PR.

Example:

```bash
python scripts/autonomy/select_agent.py \
  --issue 123 \
  --labels autonomy:ready autonomy:safe area:cli-sdk risk:low size:s

python scripts/autonomy/build_work_order.py \
  --queue autonomy-queue.json \
  --output autonomy-work-order.json

python scripts/autonomy/execute_work_order.py autonomy-work-order.json
```

## Recommended First Automation

- let the orchestrator open or update a queue summary every 15 minutes
- let only 2 to 4 agents author code at first
- require reviewer assignment before merge
- auto-merge only `safe-auto-merge` lane changes

## Do Not Enable Yet

- unattended infra applies
- unattended auth-breaking changes
- unattended production migrations
- unattended runtime protocol rewrites

## Expansion Path

1. Stabilize CI truthfulness.
2. Let safe lanes auto-merge.
3. Add staging deployment gates.
4. Add a second reviewer agent for backend and runtime changes.
5. Expand the active pool to all 10 agents.
