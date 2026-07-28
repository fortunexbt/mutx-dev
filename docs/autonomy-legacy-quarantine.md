# Autonomy Legacy Quarantine

These older autonomy scripts were retired from the working tree after their
replacement contracts became canonical. Their source remains available in Git
history for archaeology, but they are not executable product surface:

- `scripts/autonomy/autonomous-loop.py`
- `scripts/autonomy/autonomous-coder.py`
- `scripts/autonomy/mutx-autonomous-daemon.py`
- `scripts/autonomy/mutx-master-controller.py`
- `scripts/autonomy/mutx-gap-scanner.py`
- `scripts/autonomy/mutx-gap-scanner-v3.py`

## Why quarantined

They encode assumptions that have already drifted or broken:
- stale worktree paths
- stale CLI contracts
- provider/runtime coupling that no longer matches reality
- `.openclaw` log/pid coupling
- overlapping control responsibilities

## Current replacement track

Prefer the new substrate:
- `scripts/autonomy/lane_contract.py`
- `scripts/autonomy/queue_state.py`
- `scripts/autonomy/worktree_utils.py`
- `scripts/autonomy/orchestrator_main.py`
- `scripts/autonomy/daemon_main.py`
- `scripts/autonomy/run_opencode_lane.py`
- `scripts/autonomy/run_codex_lane.py`
- `scripts/autonomy/report_status.py`

## Rule

Do not restore or enable these legacy scripts for 24/7 operation. Migrate any
still-useful behavior into the bounded replacement substrate with tests and an
explicit review.
