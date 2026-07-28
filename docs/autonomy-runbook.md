# Autonomy Runbook

## Adding a New Lane / Specialist Agent

1. Add the agent definition in `agents/registry.yml`:

```yaml
agents:
  - id: my-new-specialist
    name: My New Specialist
    description: Handles my-new-area work items
    owner: team@mutx.dev
    lane: my-new-lane
    capabilities:
      - code
      - pr
    labels:
      - area:my-new-area
```

2. Add the area label to GitHub (if not already present):
   - `area:my-new-area`

3. Add lane routing in `scripts/autonomy/select_agent.py` under `LANE_ROUTING`:

```python
LANE_ROUTING = {
    "area:my-new-area": ("my-new-specialist", "lane-b"),
    # ...existing routes
}
```

4. Add file ownership bounds in `scripts/autonomy/validate_lane_bounds.py` or the equivalent guard if one exists. If no bounds check exists for your lane, this step is optional but recommended.

5. Verify the agent can be selected:

```bash
python scripts/autonomy/select_agent.py \
  --issue 999 \
  --labels area:my-new-area autonomy:ready risk:low size:s
```

Expected output: agent ID `my-new-specialist` and lane assignment.

6. Open a test issue labeled `area:my-new-area` and `autonomy:ready` and confirm the dispatch workflow picks it up within 15 minutes.

## Creating a Backlog Item That Triggers a Specialist

1. Create a GitHub issue in the `mutx-dev` repository.

2. Apply required labels:
   - `autonomy:ready` -- signals the item is claimable
   - `area:<area>` -- routes to the correct specialist (e.g., `area:backend`, `area:cli-sdk`)
   - `risk:<level>` -- `risk:low`, `risk:medium`, or `risk:high`
   - `size:<size>` -- `size:xs`, `size:s`, `size:m`, or `size:l`

3. The issue title and body are the work order source. Include:
   - What to change (specific file(s) or path(s))
   - What the expected behavior is
   - How to verify the change works

Example:

```markdown
## Area
area:backend

## What
Fix N+1 query in `src/api/services/usage.py` on the /api/usage endpoint.

## Verification
Run `pytest tests/api/test_usage.py -v` and confirm no more than 2 queries fire
for a request with 10 line items.
```

4. Once labeled, the dispatch workflow (`.github/workflows/autonomous-dispatch.yml`) will pick up the issue within the next poll cycle.

## Verifying a Lane Completed Its Work

Successful autonomy substrate runs now attempt the full handoff automatically:
- commit tracked worktree changes
- push the active worktree branch to the default remote
- create a draft PR by default when GitHub CLI is installed and authenticated
- promote the PR to ready-for-review only when the task is explicitly low-risk (`autonomy:safe` or `risk:low` plus `size:xs|size:s`) and the changed files stay inside low-risk `opencode` or docs-only paths
- enable GitHub auto-merge only for the same explicitly safe tasks when verification passed and the change is very small (3 files or fewer)

If `gh` is missing or not authenticated, the run still completes locally and records a partial handoff in `reports/autonomy-status.jsonl` so an operator can push or open the PR manually. Any task outside those low-risk guards stays on a draft PR for human review.

1. Check for an open PR linked to the issue:
   - The PR title should include the issue number (e.g., `fix: resolve N+1 in usage #123`).
   - The PR body should reference the issue.

2. Confirm CI is green:
   - `scripts/test.sh` passes (API truth contract)
   - Frontend build passes if the lane is `frontend-dashboard`
   - No new lint errors introduced

3. For backend and runtime lanes, additionally verify:
   - No regression in `pytest tests/api/`
   - Any new routes have corresponding route tests

4. For `runtime-openclaw` lane specifically:
   - Verify the OpenClaw health endpoint responds: `curl http://localhost:8080/health`
   - Confirm Node version requirement in `package.json` or runtime config matches the declared runtime (Node 24.15+ recommended)

5. Merge if all checks pass. The dispatch workflow will close the issue automatically when the PR is merged.

## Local Always-On Autonomy Daemon Operations

The new autonomy daemon is managed by:
- `scripts/autonomy/daemon-launcher.sh`
- `scripts/autonomy/daemon-watchdog.sh`
- `scripts/autonomy/daemon_main.py`

Lane execution helpers:
- `scripts/autonomy/run_main_lane.py` — bounded docs/truth work on the `main` lane
- `scripts/autonomy/run_codex_lane.py` — backend/API/runtime work on the `codex` lane
- `scripts/autonomy/run_opencode_lane.py` — frontend/product-surface work on the `opencode` lane

Default operational files:
- pid: `.autonomy/daemon.pid`
- lock: `.autonomy/daemon.lock`
- heartbeat/status: `.autonomy/daemon-status.json`
- daemon log: `reports/autonomy-daemon.log`
- watchdog log: `reports/autonomy-watchdog.log`
- status event stream: `reports/autonomy-status.jsonl`

Basic control:

```bash
scripts/autonomy/daemon-launcher.sh start
scripts/autonomy/daemon-launcher.sh status
scripts/autonomy/daemon-launcher.sh restart
scripts/autonomy/daemon-launcher.sh stop
```

Watchdog usage:

```bash
scripts/autonomy/daemon-watchdog.sh
```

Recommended cron cadence for the watchdog is every 2-5 minutes. The watchdog only restarts the daemon when the process is gone or the heartbeat in `.autonomy/daemon-status.json` is stale.

Operational notes:
- The daemon now takes an exclusive lock via `.autonomy/daemon.lock`, so a second launcher invocation will not create a duplicate worker.
- The daemon can drain a small burst of queued work per cycle with bounded concurrency: by default it launches up to 2 active runners total and never more than 1 active runner per execution lane (`codex`, `opencode`, or `main`).
- Burst and concurrency are configurable with `--burst-size`, `--max-active-runners`, and `--active-poll-seconds` on `scripts/autonomy/daemon_main.py`.
- Codex/opencode/main pause semantics remain intact: paused lanes are parked instead of being dispatched, and active lanes are not double-booked.
- Idle status reports are rate-limited to reduce `reports/autonomy-status.jsonl` noise while the queue is empty.
- If `.autonomy/fleet.json` exists, the daemon opportunistically runs `generate_fleet_tasks.py` on idle intervals and enqueues bounded generated work.
- Launcher start rotates oversized daemon logs before boot to keep always-on use low-waste.

Useful checks:

```bash
python3 -m json.tool .autonomy/daemon-status.json
python3 - <<'PY'
import json
from pathlib import Path
path = Path('reports/autonomy-status.jsonl')
print(path.read_text().splitlines()[-5:])
PY
```

## Disable / Enable Always-On Processes

Each always-on process is controlled by a GitHub Actions secret or repo variable.

| Process | Config Variable | Values |
|---------|-----------------|--------|
| executive scheduler | `AUTONOMY_SCHEDULER_ENABLED` | `true` / `false` |
| backlog sync | `AUTONOMY_BACKLOG_SYNC_ENABLED` | `true` / `false` |
| release watchdog | `AUTONOMY_RELEASE_WATCHDOG_ENABLED` | `true` / `false` |
| runtime health watchdog | `AUTONOMY_HEALTH_WATCHDOG_ENABLED` | `true` / `false` |

To disable:

```bash
# Via GitHub CLI
gh variable set AUTONOMY_SCHEDULER_ENABLED --body false
```

To enable:

```bash
gh variable set AUTONOMY_SCHEDULER_ENABLED --body true
```

To list current state:

```bash
gh variable list
```

## Diagnosing Why a Specialist Agent Failed

1. Check the dispatch workflow run for the claimed issue:
   - Navigate to the issue -> Actions -> workflow run linked in the comment
   - Look for `autonomy-dispatch.yml` runs with the issue number in the title

2. Common failure modes:

   **Agent timed out**: Increase `AUTONOMY_MAX_RUNTIME_MINUTES` (default 30) or simplify the work item scope.

   **Guardrail exceeded**: The agent generated a patch larger than `AUTONOMY_MAX_PATCH_BYTES` or changed more than `AUTONOMY_MAX_CHANGED_FILES`. Split the work into smaller issues.

   **No valid action possible**: The issue had insufficient context. The agent should have closed the issue with `needs-investigation`. If it did not, the agent prompt needs adjustment in `agents/registry.yml`.

   **CI failing unrelated to the change**: Check if `scripts/test.sh` is truthful. CI failures on `main` that are not caused by the PR indicate fixture drift -- fix the fixture, not the PR.

3. Check the executor logs:
   - The dispatch workflow uploads `autonomy-work-order.json` as an artifact
   - Look for `autonomy/briefs/{issue-number}/` for the brief written to disk
   - The executor stdout/stderr is in the workflow run log

4. If the agent left a stale claim (issue is `autonomy:claimed` but no PR exists):
   - Wait for `AUTONOMY_STALE_CLAIM_MINUTES` (default 120) for automatic release
   - Or manually release: remove `autonomy:claimed` label, re-add `autonomy:ready`

## Emergency Rollback Procedures

### Revert a Merged PR

```bash
# Find the merge commit SHA
gh pr view <pr-number> --json mergeCommitSHA

# Revert via GitHub
gh pr create --revert <pr-number>

# Or manually
git revert -m 1 <merge-commit-sha>
git push origin main
```

### Disable All Autonomous Shipping Immediately

Set all four always-on process flags to `false`:

```bash
gh variable set AUTONOMY_SCHEDULER_ENABLED --body false
gh variable set AUTONOMY_BACKLOG_SYNC_ENABLED --body false
gh variable set AUTONOMY_RELEASE_WATCHDOG_ENABLED --body false
gh variable set AUTONOMY_HEALTH_WATCHDOG_ENABLED --body false
```

Then manually triage the queue:
- Remove `autonomy:claimed` from any stuck issues
- Set `autonomy:blocked` on any issues that should not be actioned

### Kill a Running Dispatch Workflow

```bash
# Find the run
gh run list --workflow=autonomous-dispatch.yml --status=in_progress

# Cancel it
gh run cancel <run-id>
```

### Restore OpenClaw Runtime If Health Watchdog Detects Failure

```bash
# SSH to the runtime host
ssh openclaw-host

# Check service status
systemctl status openclaw
# or
pm2 status openclaw

# Restart if needed
systemctl restart openclaw
# or
pm2 restart openclaw

# Verify
curl http://localhost:8080/health
```

### Reset the Backlog Queue State

If queue state is corrupted (e.g., `autonomy-queue.json` is out of sync):

```bash
# Force a full resync from GitHub issues
python scripts/autonomy/build_work_order.py \
  --queue /dev/null \
  --output autonomy-queue.json \
  --force-refresh
```

This rebuilds the queue from live GitHub issue data.

---

## Node Runtime Alignment

MUTX and OpenClaw share Node 24.15+ as their recommended runtime lane. Use that lane for both unless you are deliberately testing one of OpenClaw's other supported majors.

### Requirements

| Component | Node Version |
|-----------|-------------|
| MUTX (CLI, SDK, dashboard build) | Node 24.15+ |
| OpenClaw (runtime substrate) | Node 24.15+ recommended; 22.22.3+ and 25.9+ supported |

Node 24.15+ is the shared supported intersection and the repo's CI baseline.

### Default Shared Toolchain

Keep `node` and `npm` on the same installation prefix:

```bash
/node24/bin/node --version   # 24.15+ recommended
/node24/bin/npm --version    # 11.12.1+ for this repo
```

With `nvm`:

```bash
export NVM_DIR="$HOME/.nvm"
nvm install 24.15
nvm use 24.15
node --version  # 24.15.x or newer 24.x
npm --version
```

### Optional Isolation

If you test OpenClaw on Node 22.22.3+ or 25.9+, isolate that runtime with `nvm`, `mise`, or a container. Do not mix a `node` executable from one prefix with `npm` from another.

### Verification

```bash
node --version  # 24.15+ for the shared lane
npm --version   # 11.12.1+ and lower than 12 for MUTX
npm run typecheck
```

### CI Note

Repository workflows provision Node 24 explicitly with `actions/setup-node`; do not rely on the runner's preinstalled version. Jobs that exercise a different OpenClaw major must select that version explicitly and remain isolated from the MUTX build job.
