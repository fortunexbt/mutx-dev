from __future__ import annotations

import json
import time
from pathlib import Path

from queue_state import load_queue, parse_iso_timestamp

ROOT = Path("/Users/fortune/MUTX")
AUTONOMY = ROOT / ".autonomy"
QUEUE = ROOT / "mutx-engineering-agents" / "dispatch" / "action-queue.json"
REPORTS = ROOT / "reports" / "autonomy-status.jsonl"
STALE_HEARTBEAT_SECONDS = 300
STALE_RUNNING_SECONDS = 300


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def load_jsonl_tail(path: Path, limit: int):
    try:
        lines = path.read_text().splitlines()
    except Exception:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"status": "error", "summary": line})
    return out


def heartbeat_age_seconds(daemon: dict) -> float | None:
    ts = parse_iso_timestamp(daemon.get("heartbeat_at"))
    if ts is None:
        return None
    return max(0.0, time.time() - ts)


def classify_item(item: dict, daemon: dict) -> str:
    status = str(item.get("status") or "unknown")
    if status != "running":
        return status
    daemon_alive = str(daemon.get("status") or "") == "active"
    active_runners = daemon.get("active_runners") or []
    active_task_ids = {str(runner.get("task_id") or "") for runner in active_runners}
    if daemon_alive and str(item.get("id") or "") in active_task_ids:
        return "running"
    age = None
    ts = parse_iso_timestamp(
        item.get("updated_at") or item.get("claimed_at") or item.get("started_at")
    )
    if ts is not None:
        age = max(0.0, time.time() - ts)
    if not daemon_alive or not active_runners or (age is not None and age >= STALE_RUNNING_SECONDS):
        return "orphaned_running"
    return "running"


def main() -> int:
    daemon = load_json(AUTONOMY / "daemon-status.json", {})
    lanes = load_json(AUTONOMY / "lane-state.json", {"lanes": {}})
    queue = load_queue(QUEUE)
    reports = load_jsonl_tail(REPORTS, 8)

    items = queue.get("items", [])
    counts = {}
    for item in items:
        key = classify_item(item, daemon)
        counts[key] = counts.get(key, 0) + 1

    heartbeat_age = heartbeat_age_seconds(daemon)
    heartbeat_state = "fresh"
    if heartbeat_age is None:
        heartbeat_state = "missing"
    elif heartbeat_age > STALE_HEARTBEAT_SECONDS:
        heartbeat_state = "stale"

    print("AUTONOMY STATUS")
    print("daemon_status:", daemon.get("status", "unknown"))
    print("heartbeat_at:", daemon.get("heartbeat_at", "n/a"))
    print("heartbeat_state:", heartbeat_state)
    if heartbeat_age is not None:
        print("heartbeat_age_seconds:", int(heartbeat_age))
    print("queue_counts:", counts)
    print("active_runners:", len(daemon.get("active_runners", []) or []))

    print("\nLANES")
    for lane, state in (lanes.get("lanes") or {}).items():
        print(
            f"- {lane}:",
            "paused" if state.get("paused") else "active",
            "|",
            state.get("reason") or "healthy",
        )

    print("\nRUNNING/QUEUED")
    for item in items:
        effective_status = classify_item(item, daemon)
        if effective_status in {"running", "queued", "parked", "orphaned_running"}:
            print(
                "-",
                item.get("id"),
                "|",
                effective_status,
                "|",
                item.get("lane") or item.get("runner"),
                "|",
                item.get("priority"),
            )

    print("\nRECENT REPORTS")
    for report in reports:
        print("-", report.get("task_id"), "|", report.get("status"), "|", report.get("summary"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
