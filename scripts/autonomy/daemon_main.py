from __future__ import annotations

import argparse
import atexit
import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from lane_contract import (
    LanePaths,
    build_work_order,
    queued_items_in_priority_order,
    worktree_candidates_for_lane,
)
from lane_state import is_lane_paused, lane_reason, load_lane_state
from queue_state import load_queue, recover_stale_running_items, save_queue, set_status
from report_status import append_jsonl, build_report, utc_now_iso
from resume_policy import apply_auto_resume
from worktree_utils import list_valid_worktrees

DEFAULT_SLEEP_SECONDS = 60
DEFAULT_ACTIVE_POLL_SECONDS = 5
DEFAULT_BURST_SIZE = 2
DEFAULT_MAX_ACTIVE_RUNNERS = 2
MAX_IDLE_SECONDS = 900
DEFAULT_IDLE_REPORT_INTERVAL = 900
DEFAULT_FLEET_SCAN_INTERVAL = 900
DEFAULT_ISSUE_SYNC_INTERVAL = 900
DEFAULT_QUEUE_REFILL_THRESHOLD = 2
DEFAULT_FLEET_REQUEUE_COOLDOWN = 1800
DEFAULT_PR_RECONCILE_INTERVAL = 300
DEFAULT_STALE_RUNNING_RECOVERY_SECONDS = 300
LOCK_EXIT_CODE = 75
STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM)

_STOP_REQUESTED = False


class DaemonLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"daemon lock already held: {self.path}") from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"{os.getpid()}\n")
        self.handle.flush()

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            self.handle.truncate()
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


class StatusTracker:
    def __init__(self, path: Path, args: argparse.Namespace) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state: dict[str, Any] = {
            "status": "starting",
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "repo_root": args.repo_root,
            "queue": args.queue,
            "report_log": args.report_log,
            "lock_file": args.lock_file,
            "fleet_config": args.fleet_config,
            "started_at": utc_now_iso(),
            "heartbeat_at": utc_now_iso(),
            "last_cycle_started_at": None,
            "last_cycle_completed_at": None,
            "last_non_idle_at": None,
            "last_idle_report_at": None,
            "last_fleet_scan_at": None,
            "last_fleet_enqueue_at": None,
            "last_issue_sync_at": None,
            "last_issue_enqueue_at": None,
            "last_result": None,
            "last_error": None,
            "queue_depth": 0,
            "consecutive_idle_cycles": 0,
            "cycle_count": 0,
            "fleet_tasks_enqueued": 0,
            "queue_refill_threshold": getattr(
                args, "queue_refill_threshold", DEFAULT_QUEUE_REFILL_THRESHOLD
            ),
            "last_auto_resume_at": None,
            "last_auto_resume_result": None,
            "last_pr_reconcile_at": None,
            "last_pr_reconcile_result": None,
            "stop_requested": False,
            "active_runners": [],
        }
        self.write()

    def update(self, **changes: Any) -> None:
        self.state.update(changes)
        self.state["heartbeat_at"] = utc_now_iso()
        self.write()

    def mark_cycle_start(self, queue_depth: int) -> None:
        self.state["cycle_count"] += 1
        self.update(last_cycle_started_at=utc_now_iso(), queue_depth=queue_depth)

    def mark_cycle_end(
        self,
        *,
        status: str,
        last_result: dict[str, Any] | None = None,
        last_error: str | None = None,
        queue_depth: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "status": status,
            "last_cycle_completed_at": utc_now_iso(),
            "last_result": last_result,
            "last_error": last_error,
        }
        if queue_depth is not None:
            payload["queue_depth"] = queue_depth
        self.update(**payload)

    def write(self) -> None:
        write_json_atomic(self.path, self.state)


class ActiveRunner:
    def __init__(
        self,
        *,
        task_id: str,
        lane: str,
        runner: str,
        worktree: str,
        process: subprocess.Popen[str],
    ) -> None:
        self.task_id = task_id
        self.lane = lane
        self.runner = runner
        self.worktree = worktree
        self.process = process
        self.started_at = utc_now_iso()

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "lane": self.lane,
            "runner": self.runner,
            "worktree": self.worktree,
            "pid": self.process.pid,
            "started_at": self.started_at,
        }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def next_idle_delay(current: int) -> int:
    if current <= 0:
        return DEFAULT_SLEEP_SECONDS
    return min(current * 2, MAX_IDLE_SECONDS)


def should_emit_idle_report(last_idle_report_at: str | None, idle_report_interval: int) -> bool:
    if not last_idle_report_at:
        return True
    try:
        previous = parse_epoch(last_idle_report_at)
    except ValueError:
        return True
    return (time.time() - previous) >= idle_report_interval


def parse_epoch(value: str) -> float:
    normalized = value.replace("Z", "+00:00")
    return __import__("datetime").datetime.fromisoformat(normalized).timestamp()


def install_signal_handlers() -> None:
    for sig in STOP_SIGNALS:
        signal.signal(sig, request_stop)


def request_stop(signum: int, _frame: Any) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True
    sys.stderr.write(f"autonomy daemon received signal {signum}; shutting down\n")
    sys.stderr.flush()


def split_candidates(raw: str) -> list[str]:
    return [item for item in (part.strip() for part in raw.split(":")) if item]


def build_lane_paths(args: argparse.Namespace) -> LanePaths:
    return LanePaths(
        repo_root=args.repo_root,
        backend_worktree=args.backend_worktree,
        frontend_worktree=args.frontend_worktree,
        backend_candidates=split_candidates(args.backend_candidates),
        frontend_candidates=split_candidates(args.frontend_candidates),
    )


def execution_lane_for(runner: str, lane: str) -> str:
    return runner if runner in {"codex", "opencode", "main"} else lane


def runner_command(
    orchestrator_args: argparse.Namespace,
    *,
    task_id: str,
    worktree_override: str | None = None,
) -> list[str]:
    command = [
        "python3",
        "scripts/autonomy/orchestrator_main.py",
        "--queue",
        orchestrator_args.queue,
        "--repo-root",
        orchestrator_args.repo_root,
        "--backend-worktree",
        orchestrator_args.backend_worktree,
        "--frontend-worktree",
        orchestrator_args.frontend_worktree,
        "--backend-candidates",
        orchestrator_args.backend_candidates,
        "--frontend-candidates",
        orchestrator_args.frontend_candidates,
        "--output-dir",
        orchestrator_args.output_dir,
        "--lane-state",
        orchestrator_args.lane_state,
        "--report-log",
        orchestrator_args.report_log,
        "--task-id",
        task_id,
        "--execute",
    ]
    if worktree_override:
        command.extend(["--worktree-override", worktree_override])
    return command


TERMINAL_QUEUE_STATUSES = {"completed", "failed", "blocked", "merged", "cancelled"}

PR_HANDOFF_NOTE_MARKERS = (
    "draft PR ready",
    "ready PR updated",
    "published",
    "pushed autonomy/",
    "wait_for_auto_merge",
    "review_pull_request",
)


def _item_has_pr_handoff(item: dict[str, Any]) -> bool:
    if item.get("pr_ref") or item.get("pull_request"):
        return True
    notes = item.get("notes") or []
    if not isinstance(notes, list):
        return False
    for note in notes:
        message = str((note or {}).get("message") or "")
        if any(marker in message for marker in PR_HANDOFF_NOTE_MARKERS):
            return True
    return False


def _is_stale_terminal_fleet_item(
    item: dict[str, Any], task: dict[str, Any], *, cooldown_seconds: int
) -> bool:
    status = str(item.get("status") or "queued")
    if status not in TERMINAL_QUEUE_STATUSES:
        return False
    source = str(item.get("source") or "")
    if not source.startswith("fleet"):
        return False
    if _item_has_pr_handoff(item):
        return False
    existing_fingerprint = str(item.get("evidence_fingerprint") or "")
    incoming_fingerprint = str(task.get("evidence_fingerprint") or "")
    if (
        existing_fingerprint
        and incoming_fingerprint
        and existing_fingerprint == incoming_fingerprint
    ):
        return False
    ts = item.get("completed_at") or item.get("updated_at")
    if not ts:
        return True
    try:
        age_seconds = time.time() - parse_epoch(str(ts))
    except ValueError:
        return True
    return age_seconds >= cooldown_seconds


def recover_orphaned_running_items(
    queue_path: str | Path,
    *,
    stale_after_seconds: int = DEFAULT_STALE_RUNNING_RECOVERY_SECONDS,
    note: str = "daemon restart recovered orphaned running task",
) -> list[str]:
    queue = load_queue(queue_path)
    recovered = recover_stale_running_items(
        queue,
        stale_after_seconds=stale_after_seconds,
        note=note,
    )
    if recovered:
        save_queue(queue_path, queue)
    return recovered


def enqueue_generated_tasks(
    queue_path: str | Path,
    tasks: list[dict[str, Any]],
    *,
    cooldown_seconds: int = DEFAULT_FLEET_REQUEUE_COOLDOWN,
) -> int:
    if not tasks:
        return 0
    queue = load_queue(queue_path)
    items = queue.setdefault("items", [])
    item_index = {str(item.get("id")): index for index, item in enumerate(items)}
    appended = 0
    for task in tasks:
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        payload = dict(task)
        payload.setdefault("status", "queued")
        payload.setdefault("priority", "p2")
        payload.setdefault("source", "fleet")
        payload.setdefault("labels", [])
        existing_index = item_index.get(task_id)
        if existing_index is not None:
            existing = items[existing_index]
            if not _is_stale_terminal_fleet_item(
                existing, payload, cooldown_seconds=cooldown_seconds
            ):
                continue
            notes = list(existing.get("notes") or [])
            notes.append({"ts": utc_now_iso(), "message": "fleet task refreshed after cooldown"})
            payload["notes"] = notes
            items[existing_index] = payload
            appended += 1
            continue
        items.append(payload)
        item_index[task_id] = len(items) - 1
        appended += 1
    if appended:
        save_queue(queue_path, queue)
    return appended


def run_fleet_scan(args: argparse.Namespace) -> list[dict[str, Any]]:
    fleet_path = Path(args.fleet_config)
    if not fleet_path.exists():
        return []
    output_path = Path(args.generated_task_output)
    command = [
        "python3",
        "scripts/autonomy/generate_fleet_tasks.py",
        "--fleet",
        args.fleet_config,
        "--queue",
        args.queue,
        "--output",
        args.generated_task_output,
    ]
    result = subprocess.run(command, cwd=args.repo_root, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "fleet generation failed"
        )
    if not output_path.exists():
        return []
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("generated fleet task payload was not a list")
    return payload


def run_issue_sync(args: argparse.Namespace) -> list[dict[str, Any]]:
    output_path = Path(args.github_issue_output)
    command = [
        "python3",
        "scripts/autonomy/sync_github_issues.py",
        "--repo",
        args.github_issue_repo,
        "--limit",
        str(args.github_issue_limit),
        "--output",
        args.github_issue_output,
    ]
    result = subprocess.run(command, cwd=args.repo_root, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "github issue sync failed"
        )
    if not output_path.exists():
        return []
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("github issue sync payload was not a list")
    return payload


def maybe_resume_codex_lane(args: argparse.Namespace, tracker: StatusTracker) -> dict[str, Any]:
    if args.codex_auto_resume_max_attempts <= 0:
        return {
            "changed": False,
            "eligible": False,
            "blocked_by": "auto_resume_disabled",
            "requeued_items": 0,
        }
    result = apply_auto_resume(
        args.lane_state,
        args.queue,
        "codex",
        min_pause_seconds=args.codex_auto_resume_pause_seconds,
        max_auto_resumes=args.codex_auto_resume_max_attempts,
    )
    if result.get("changed"):
        tracker.update(last_auto_resume_at=utc_now_iso(), last_auto_resume_result=result)
    return result


def maybe_reconcile_prs(
    args: argparse.Namespace, tracker: StatusTracker, *, force: bool = False
) -> dict[str, Any]:
    interval = max(0, int(getattr(args, "pr_reconcile_interval", DEFAULT_PR_RECONCILE_INTERVAL)))
    last_run = tracker.state.get("last_pr_reconcile_at")
    if not force and interval and last_run:
        try:
            elapsed = time.time() - float(last_run)
        except (TypeError, ValueError):
            elapsed = interval
        if elapsed < interval:
            return {"ran": False, "reason": "cooldown"}
    command = ["python3", "scripts/autonomy/reconcile_prs.py"]
    result = subprocess.run(command, cwd=args.repo_root, text=True, capture_output=True)
    tracker.update(
        last_pr_reconcile_at=str(time.time()),
        last_pr_reconcile_result={
            "exit_code": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        },
    )
    return {"ran": True, "exit_code": result.returncode}


def maybe_run_issue_sync(
    args: argparse.Namespace, tracker: StatusTracker, *, queued_items: int, force: bool = False
) -> int:
    if not args.github_issue_sync_enabled:
        return 0
    if not force and queued_items > args.queue_refill_threshold:
        return 0
    last_sync_at = tracker.state.get("last_issue_sync_at")
    if (
        not force
        and last_sync_at
        and (time.time() - parse_epoch(last_sync_at)) < args.github_issue_sync_interval
    ):
        return 0
    tracker.update(last_issue_sync_at=utc_now_iso())
    tasks = run_issue_sync(args)
    appended = enqueue_generated_tasks(args.queue, tasks, cooldown_seconds=0)
    if appended:
        tracker.update(last_issue_enqueue_at=utc_now_iso())
    return appended


def maybe_run_fleet_scan(
    args: argparse.Namespace, tracker: StatusTracker, *, queued_items: int, force: bool = False
) -> int:
    if not args.fleet_scan_interval or args.fleet_scan_interval < 0:
        return 0
    if not force and queued_items > args.queue_refill_threshold:
        return 0
    last_scan_at = tracker.state.get("last_fleet_scan_at")
    if (
        not force
        and last_scan_at
        and (time.time() - parse_epoch(last_scan_at)) < args.fleet_scan_interval
    ):
        return 0
    tracker.update(last_fleet_scan_at=utc_now_iso())
    tasks = run_fleet_scan(args)
    appended = enqueue_generated_tasks(args.queue, tasks)
    if appended:
        tracker.update(
            last_fleet_enqueue_at=utc_now_iso(),
            fleet_tasks_enqueued=int(tracker.state.get("fleet_tasks_enqueued", 0)) + appended,
        )
    return appended


def build_idle_report(
    args: argparse.Namespace, idle_delay: int, queued_items: int, appended: int = 0
) -> dict[str, Any]:
    summary = f"Queue empty ({queued_items} queued items); sleeping for {idle_delay}s"
    next_action = "wait_for_queue_items"
    if appended:
        summary = f"Queue empty; enqueued {appended} fleet task(s) and continuing"
        next_action = "dispatch_generated_tasks"
    return build_report(
        task_id="daemon",
        lane="main",
        status="parked",
        summary=summary,
        worktree=args.repo_root,
        verification=[],
        next_action=next_action,
    )


def refresh_active_runner_state(tracker: StatusTracker, active_runners: list[ActiveRunner]) -> None:
    tracker.update(active_runners=[runner.snapshot() for runner in active_runners])


def reap_finished_runners(active_runners: list[ActiveRunner]) -> list[dict[str, Any]]:
    finished: list[dict[str, Any]] = []
    still_running: list[ActiveRunner] = []
    for runner in active_runners:
        exit_code = runner.process.poll()
        if exit_code is None:
            still_running.append(runner)
            continue
        stdout, stderr = runner.process.communicate()
        payload = {"status": "unknown"}
        if stdout.strip():
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = {"status": "invalid_json", "stdout_excerpt": stdout.strip()[:400]}
        finished.append(
            {
                "task_id": runner.task_id,
                "lane": runner.lane,
                "runner": runner.runner,
                "exit_code": exit_code,
                "payload": payload,
                "stderr_excerpt": stderr.strip()[:400],
            }
        )
    active_runners[:] = still_running
    return finished


def park_paused_item(
    args: argparse.Namespace,
    queue: dict[str, Any],
    *,
    task_id: str,
    lane: str,
    runner: str,
    worktree: str,
    reason: str,
) -> None:
    set_status(queue, task_id, "parked", lane=lane, runner=runner, note=f"lane paused: {reason}")
    append_jsonl(
        Path(args.report_log),
        build_report(
            task_id=task_id,
            lane=lane,
            status="parked",
            summary=f"lane paused: {reason}",
            worktree=worktree,
            blocker_class=reason,
            next_action="wait_for_lane_resume",
        ),
    )


def select_dispatch_worktree(
    lane: str, paths: LanePaths, reserved_worktrees: set[str]
) -> str | None:
    candidates = worktree_candidates_for_lane(lane, paths)
    for allow_dirty in (False, True):
        for worktree in list_valid_worktrees(candidates, allow_dirty=allow_dirty):
            if worktree not in reserved_worktrees:
                return worktree
    return None


def select_dispatch_candidates(
    queue: dict[str, Any],
    lane_state: dict[str, Any],
    paths: LanePaths,
    *,
    busy_worktrees: set[str],
    limit: int,
) -> tuple[list[dict[str, str]], int]:
    selected: list[dict[str, str]] = []
    parked = 0
    dispatch_count = 0
    reserved_worktrees = set(busy_worktrees)
    for item in queued_items_in_priority_order(queue):
        work_order = build_work_order(item, paths)
        active_lane = execution_lane_for(work_order.runner, work_order.lane)
        reason = lane_reason(lane_state, active_lane)
        if is_lane_paused(lane_state, active_lane):
            selected.append(
                {
                    "action": "park",
                    "task_id": work_order.id,
                    "lane": work_order.lane,
                    "runner": work_order.runner,
                    "worktree": work_order.worktree,
                    "reason": reason or "lane_paused",
                    "active_lane": active_lane,
                }
            )
            parked += 1
            continue
        selected_worktree = select_dispatch_worktree(work_order.lane, paths, reserved_worktrees)
        if not selected_worktree:
            continue
        reserved_worktrees.add(selected_worktree)
        selected.append(
            {
                "action": "dispatch",
                "task_id": work_order.id,
                "lane": work_order.lane,
                "runner": work_order.runner,
                "worktree": selected_worktree,
                "active_lane": active_lane,
            }
        )
        dispatch_count += 1
        if dispatch_count >= limit:
            break
    return selected, parked


def launch_runner(
    args: argparse.Namespace, task_id: str, lane: str, runner: str, worktree: str
) -> ActiveRunner:
    process = subprocess.Popen(
        runner_command(args, task_id=task_id, worktree_override=worktree),
        cwd=args.repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return ActiveRunner(
        task_id=task_id, lane=lane, runner=runner, worktree=worktree, process=process
    )


def stop_active_runners(active_runners: list[ActiveRunner]) -> None:
    for runner in active_runners:
        if runner.process.poll() is None:
            runner.process.terminate()
    deadline = time.time() + 10
    for runner in active_runners:
        if runner.process.poll() is not None:
            continue
        timeout = max(1, int(deadline - time.time()))
        try:
            runner.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            runner.process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the MUTX autonomous orchestrator daemon")
    parser.add_argument("--queue", default="mutx-engineering-agents/dispatch/action-queue.json")
    parser.add_argument("--repo-root", default="/Users/fortune/MUTX")
    parser.add_argument(
        "--backend-worktree", default="/Users/fortune/mutx-worktrees/autonomy/codex-main"
    )
    parser.add_argument(
        "--frontend-worktree", default="/Users/fortune/mutx-worktrees/autonomy/opencode-main"
    )
    parser.add_argument(
        "--backend-candidates",
        default="/Users/fortune/mutx-worktrees/autonomy/codex-main:/Users/fortune/mutx-worktrees/engineering/control-plane-steward:/Users/fortune/mutx-worktrees/factory/backend",
    )
    parser.add_argument(
        "--frontend-candidates",
        default="/Users/fortune/mutx-worktrees/autonomy/opencode-main:/Users/fortune/mutx-worktrees/engineering/operator-surface-builder:/Users/fortune/mutx-worktrees/factory/frontend",
    )
    parser.add_argument("--output-dir", default=".autonomy/work-orders")
    parser.add_argument("--report-log", default="reports/autonomy-status.jsonl")
    parser.add_argument("--lane-state", default=".autonomy/lane-state.json")
    parser.add_argument("--status-file", default=".autonomy/daemon-status.json")
    parser.add_argument("--lock-file", default=".autonomy/daemon.lock")
    parser.add_argument("--generated-task-output", default=".autonomy/generated-tasks.json")
    parser.add_argument("--github-issue-output", default=".autonomy/github-issue-tasks.json")
    parser.add_argument("--fleet-config", default=".autonomy/fleet.json")
    parser.add_argument("--github-issue-repo", default="mutx-dev/mutx-dev")
    parser.add_argument("--github-issue-limit", type=int, default=100)
    parser.add_argument("--github-issue-sync-enabled", action="store_true")
    parser.add_argument("--idle-report-interval", type=int, default=DEFAULT_IDLE_REPORT_INTERVAL)
    parser.add_argument("--fleet-scan-interval", type=int, default=DEFAULT_FLEET_SCAN_INTERVAL)
    parser.add_argument(
        "--github-issue-sync-interval", type=int, default=DEFAULT_ISSUE_SYNC_INTERVAL
    )
    parser.add_argument(
        "--queue-refill-threshold", type=int, default=DEFAULT_QUEUE_REFILL_THRESHOLD
    )
    parser.add_argument("--pr-reconcile-interval", type=int, default=DEFAULT_PR_RECONCILE_INTERVAL)
    parser.add_argument("--codex-auto-resume-pause-seconds", type=int, default=1800)
    parser.add_argument("--codex-auto-resume-max-attempts", type=int, default=3)
    parser.add_argument("--burst-size", type=int, default=DEFAULT_BURST_SIZE)
    parser.add_argument("--max-active-runners", type=int, default=DEFAULT_MAX_ACTIVE_RUNNERS)
    parser.add_argument("--active-poll-seconds", type=int, default=DEFAULT_ACTIVE_POLL_SECONDS)
    parser.add_argument("--once", action="store_true", help="Run a single orchestration cycle")
    args = parser.parse_args()

    args.burst_size = max(1, args.burst_size)
    args.max_active_runners = max(1, args.max_active_runners)
    args.active_poll_seconds = max(1, args.active_poll_seconds)

    install_signal_handlers()
    lock = DaemonLock(Path(args.lock_file))
    try:
        lock.acquire()
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        return LOCK_EXIT_CODE
    atexit.register(lock.release)

    tracker = StatusTracker(Path(args.status_file), args)
    idle_delay = 0
    active_runners: list[ActiveRunner] = []
    paths = build_lane_paths(args)
    recovered_at_start = recover_orphaned_running_items(args.queue)
    if recovered_at_start:
        append_jsonl(
            Path(args.report_log),
            build_report(
                task_id="daemon",
                lane="main",
                status="completed",
                summary=f"Recovered {len(recovered_at_start)} orphaned running task(s) on daemon start",
                worktree=args.repo_root,
                verification=[],
                next_action="continue",
            ),
        )
        tracker.update(
            queue_depth=len(
                [
                    item
                    for item in load_queue(args.queue).get("items", [])
                    if item.get("status") == "queued"
                ]
            )
        )

    try:
        while not _STOP_REQUESTED:
            finished = reap_finished_runners(active_runners)
            refresh_active_runner_state(tracker, active_runners)

            auto_resume = maybe_resume_codex_lane(args, tracker)
            maybe_reconcile_prs(args, tracker)
            queue = load_queue(args.queue)
            queued_items = [
                item for item in queue.get("items", []) if item.get("status") == "queued"
            ]
            tracker.mark_cycle_start(len(queued_items))

            if auto_resume.get("changed"):
                append_jsonl(
                    Path(args.report_log),
                    build_report(
                        task_id="daemon-codex-auto-resume",
                        lane="codex",
                        status="completed",
                        summary=(
                            f"Auto-resumed codex lane after quota pause; requeued {int(auto_resume.get('requeued_items') or 0)} parked item(s)"
                        ),
                        worktree=args.repo_root,
                        verification=[],
                        next_action="continue",
                    ),
                )
                queue = load_queue(args.queue)
                queued_items = [
                    item for item in queue.get("items", []) if item.get("status") == "queued"
                ]
                tracker.update(queue_depth=len(queued_items))

            lane_state = load_lane_state(args.lane_state)
            busy_worktrees = {runner.worktree for runner in active_runners}
            dispatch_capacity = max(0, args.max_active_runners - len(active_runners))

            if not queued_items and not active_runners:
                tracker.update(
                    status="idle",
                    consecutive_idle_cycles=int(tracker.state.get("consecutive_idle_cycles", 0))
                    + 1,
                )
                appended = 0
                issue_appended = 0
                fleet_error = None
                try:
                    issue_appended = maybe_run_issue_sync(args, tracker, queued_items=0, force=True)
                    appended = issue_appended or maybe_run_fleet_scan(
                        args, tracker, queued_items=0, force=True
                    )
                except Exception as exc:
                    fleet_error = str(exc)
                    tracker.update(last_error=fleet_error)

                if appended:
                    queue = load_queue(args.queue)
                    queued_items = [
                        item for item in queue.get("items", []) if item.get("status") == "queued"
                    ]
                    source = "github_issue_sync" if issue_appended else "fleet_enqueued"
                    tracker.mark_cycle_end(
                        status="active",
                        last_result={"status": source, "count": appended},
                        last_error=fleet_error,
                        queue_depth=len(queued_items),
                    )
                    append_jsonl(
                        Path(args.report_log),
                        build_idle_report(args, 0, len(queued_items), appended),
                    )
                    if args.once:
                        return 0
                    continue

                idle_delay = next_idle_delay(idle_delay)
                if should_emit_idle_report(
                    tracker.state.get("last_idle_report_at"), args.idle_report_interval
                ):
                    append_jsonl(
                        Path(args.report_log),
                        build_idle_report(args, idle_delay, len(queued_items)),
                    )
                    tracker.update(last_idle_report_at=utc_now_iso())
                tracker.mark_cycle_end(
                    status="idle",
                    last_result={"status": "idle", "sleep_seconds": idle_delay},
                    last_error=fleet_error,
                    queue_depth=0,
                )
                if args.once:
                    return 0
                time.sleep(idle_delay)
                continue

            idle_delay = 0
            tracker.update(
                status="active", consecutive_idle_cycles=0, last_non_idle_at=utc_now_iso()
            )
            try:
                issue_appended = maybe_run_issue_sync(args, tracker, queued_items=len(queued_items))
                appended = issue_appended or maybe_run_fleet_scan(
                    args, tracker, queued_items=len(queued_items)
                )
            except Exception as exc:
                tracker.update(last_error=str(exc))
            else:
                if appended:
                    queue = load_queue(args.queue)
                    queued_items = [
                        item for item in queue.get("items", []) if item.get("status") == "queued"
                    ]
                    tracker.update(queue_depth=len(queued_items))

            dispatch_limit = min(args.burst_size, dispatch_capacity)
            dispatches = 0
            parked = 0
            dispatch_error = None
            last_result: dict[str, Any]

            if dispatch_limit > 0 and queued_items:
                selections, parked = select_dispatch_candidates(
                    queue,
                    lane_state,
                    paths,
                    busy_worktrees=busy_worktrees,
                    limit=dispatch_limit,
                )
                for selection in selections:
                    if selection["action"] == "park":
                        park_paused_item(
                            args,
                            queue,
                            task_id=selection["task_id"],
                            lane=selection["lane"],
                            runner=selection["runner"],
                            worktree=selection["worktree"],
                            reason=selection["reason"],
                        )
                        continue
                    set_status(
                        queue,
                        selection["task_id"],
                        "running",
                        lane=selection["lane"],
                        runner=selection["runner"],
                        note="daemon dispatched work order",
                    )
                    save_queue(args.queue, queue)
                    try:
                        active_runners.append(
                            launch_runner(
                                args,
                                selection["task_id"],
                                selection["active_lane"],
                                selection["runner"],
                                selection["worktree"],
                            )
                        )
                        dispatches += 1
                    except Exception as exc:
                        dispatch_error = str(exc)
                        set_status(
                            queue,
                            selection["task_id"],
                            "queued",
                            lane=selection["lane"],
                            runner=selection["runner"],
                            note=f"daemon dispatch failed: {dispatch_error}",
                        )
                save_queue(args.queue, queue)

            refresh_active_runner_state(tracker, active_runners)
            queue = load_queue(args.queue)
            queued_items = [
                item for item in queue.get("items", []) if item.get("status") == "queued"
            ]
            if active_runners or dispatches or finished:
                tracker.update(
                    status="active", consecutive_idle_cycles=0, last_non_idle_at=utc_now_iso()
                )
                last_result = {
                    "status": "active",
                    "dispatched": dispatches,
                    "finished": len(finished),
                    "parked": parked,
                    "active_runners": len(active_runners),
                }
                tracker.mark_cycle_end(
                    status="active",
                    last_result=last_result,
                    last_error=dispatch_error,
                    queue_depth=len(queued_items),
                )
            else:
                waiting_status = (
                    "waiting_for_runner_capacity"
                    if dispatch_capacity <= 0
                    else "waiting_for_worktree_capacity"
                )
                last_result = {
                    "status": waiting_status,
                    "parked": parked,
                    "active_runners": len(active_runners),
                }
                tracker.mark_cycle_end(
                    status="active",
                    last_result=last_result,
                    last_error=dispatch_error,
                    queue_depth=len(queued_items),
                )

            if args.once:
                return 0

            if active_runners or queued_items:
                time.sleep(args.active_poll_seconds)
            else:
                time.sleep(DEFAULT_SLEEP_SECONDS)
    finally:
        stop_active_runners(active_runners)
        recovered_on_stop = recover_orphaned_running_items(
            args.queue,
            stale_after_seconds=0,
            note="daemon shutdown recovered in-flight task",
        )
        refresh_active_runner_state(tracker, [])
        tracker.update(
            status="stopped",
            stop_requested=_STOP_REQUESTED,
            last_result={
                "status": "stopped",
                "recovered_on_stop": len(recovered_on_stop),
            },
        )
        lock.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
