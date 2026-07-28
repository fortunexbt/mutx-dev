from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_lane_state(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.exists():
        return {"lanes": {}}
    return json.loads(candidate.read_text())


def save_lane_state(path: str | Path, payload: dict[str, Any]) -> None:
    candidate = Path(path)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


DEFAULT_QUOTA_RESUME_SECONDS = 1800
MAX_QUOTA_RESUME_SECONDS = 86400


def pause_lane(
    payload: dict[str, Any],
    lane: str,
    *,
    reason: str,
    source: str | None = None,
    retry_after_seconds: int | None = None,
) -> dict[str, Any]:
    lanes = payload.setdefault("lanes", {})
    lane_state = lanes.setdefault(lane, {})
    pause_count = int(lane_state.get("pause_count") or 0) + 1
    paused_at = utc_now_iso()
    auto_resume_after_seconds = None
    if reason == "quota_exceeded":
        requested_resume_seconds = retry_after_seconds or int(
            lane_state.get("auto_resume_after_seconds") or DEFAULT_QUOTA_RESUME_SECONDS
        )
        auto_resume_after_seconds = max(1, min(requested_resume_seconds, MAX_QUOTA_RESUME_SECONDS))
    resume_at = None
    if auto_resume_after_seconds:
        try:
            resume_at_ts = datetime.now(timezone.utc).timestamp() + auto_resume_after_seconds
            resume_at = (
                datetime.fromtimestamp(resume_at_ts, timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
        except (OverflowError, OSError, ValueError):
            resume_at = None
    lane_state.update(
        {
            "paused": True,
            "reason": reason,
            "source": source,
            "paused_at": paused_at,
            "updated_at": paused_at,
            "pause_count": pause_count,
            "last_pause_reason": reason,
            "last_pause_source": source,
            "auto_resume_after_seconds": auto_resume_after_seconds,
            "resume_at": resume_at,
        }
    )
    return payload


def resume_lane(
    payload: dict[str, Any], lane: str, *, resumed_by: str | None = None
) -> dict[str, Any]:
    lanes = payload.setdefault("lanes", {})
    lane_state = lanes.setdefault(lane, {})
    previous_reason = lane_state.get("reason")
    lane_state.update(
        {
            "paused": False,
            "reason": None,
            "updated_at": utc_now_iso(),
            "source": None,
            "last_resume_at": utc_now_iso(),
            "last_resume_reason": previous_reason,
            "resumed_by": resumed_by or "manual",
            "resume_at": None,
        }
    )
    if previous_reason == "quota_exceeded":
        lane_state["auto_resume_count"] = int(lane_state.get("auto_resume_count") or 0) + (
            1 if (resumed_by or "manual") == "auto" else 0
        )
    return payload


def is_lane_paused(payload: dict[str, Any], lane: str) -> bool:
    return bool(payload.get("lanes", {}).get(lane, {}).get("paused"))


def lane_reason(payload: dict[str, Any], lane: str) -> str | None:
    return payload.get("lanes", {}).get(lane, {}).get("reason")
