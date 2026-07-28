from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from lane_state import load_lane_state, resume_lane, save_lane_state
from queue_state import utc_now_iso

AUTO_RESUME_REASONS = {"quota_exceeded"}
TERMINAL_STATUSES = {"completed", "failed", "blocked", "merged"}


def _parse_epoch(value: str | None) -> float | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return __import__("datetime").datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def inspect_lane_resume(
    payload: dict[str, Any],
    lane: str,
    *,
    min_pause_seconds: int,
    max_auto_resumes: int,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    lanes = payload.get("lanes", {})
    lane_state = lanes.get(lane, {})
    paused = bool(lane_state.get("paused"))
    reason = lane_state.get("reason")
    paused_at = lane_state.get("paused_at") or lane_state.get("updated_at")
    paused_epoch = _parse_epoch(str(paused_at)) if paused_at else None
    effective_pause_seconds = int(lane_state.get("auto_resume_after_seconds") or min_pause_seconds)
    resume_count = int(lane_state.get("auto_resume_count") or 0)
    age_seconds = (
        None if paused_epoch is None else max(int((now_epoch or time.time()) - paused_epoch), 0)
    )
    eligible = bool(
        paused
        and reason in AUTO_RESUME_REASONS
        and age_seconds is not None
        and age_seconds >= effective_pause_seconds
        and resume_count < max_auto_resumes
    )
    blocked_by = None
    if not paused:
        blocked_by = "lane_not_paused"
    elif reason not in AUTO_RESUME_REASONS:
        blocked_by = f"reason_not_auto_resume:{reason}"
    elif age_seconds is None:
        blocked_by = "missing_pause_timestamp"
    elif age_seconds < effective_pause_seconds:
        blocked_by = "backoff_not_elapsed"
    elif resume_count >= max_auto_resumes:
        blocked_by = "max_auto_resumes_reached"
    remaining_seconds = (
        None if age_seconds is None else max(effective_pause_seconds - age_seconds, 0)
    )
    return {
        "lane": lane,
        "paused": paused,
        "reason": reason,
        "paused_at": paused_at,
        "resume_at": lane_state.get("resume_at"),
        "age_seconds": age_seconds,
        "remaining_seconds": remaining_seconds,
        "effective_pause_seconds": effective_pause_seconds,
        "auto_resume_count": resume_count,
        "max_auto_resumes": max_auto_resumes,
        "eligible": eligible,
        "blocked_by": blocked_by,
    }


def requeue_parked_items(queue: dict[str, Any], lane: str) -> int:
    resumed = 0
    for item in queue.get("items", []):
        item_lane = str(item.get("runner") or item.get("lane") or "")
        if item.get("status") != "parked" or item_lane != lane:
            continue
        notes = item.get("notes") if isinstance(item.get("notes"), list) else []
        if notes and not any(
            "lane paused" in str(note.get("message") or "")
            for note in notes
            if isinstance(note, dict)
        ):
            continue
        item["status"] = "queued"
        item["updated_at"] = utc_now_iso()
        item.pop("completed_at", None)
        notes.append({"ts": utc_now_iso(), "message": f"lane auto-resumed: requeued for {lane}"})
        item["notes"] = notes
        resumed += 1
    return resumed


def apply_auto_resume(
    lane_state_path: str | Path,
    queue_path: str | Path,
    lane: str,
    *,
    min_pause_seconds: int,
    max_auto_resumes: int,
) -> dict[str, Any]:
    payload = load_lane_state(lane_state_path)
    inspection = inspect_lane_resume(
        payload,
        lane,
        min_pause_seconds=min_pause_seconds,
        max_auto_resumes=max_auto_resumes,
    )
    if not inspection["eligible"]:
        return {"changed": False, **inspection, "requeued_items": 0}

    updated = resume_lane(payload, lane, resumed_by="auto")
    save_lane_state(lane_state_path, updated)

    queue_file = Path(queue_path)
    requeued = 0
    if queue_file.exists():
        queue = json.loads(queue_file.read_text(encoding="utf-8"))
        requeued = requeue_parked_items(queue, lane)
        queue_file.write_text(json.dumps(queue, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    return {
        "changed": True,
        **inspection,
        "eligible": True,
        "requeued_items": requeued,
        "resumed_by": "auto",
    }
