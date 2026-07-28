from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"completed", "failed", "blocked", "parked", "merged", "cancelled"}
RUNNING_STATUS = "running"
DEFAULT_LOAD_RETRIES = 5
DEFAULT_LOAD_RETRY_DELAY = 0.1
STALE_RUNNING_STATUSES = {RUNNING_STATUS}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    normalized = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def load_queue(
    path: str | Path,
    *,
    retries: int = DEFAULT_LOAD_RETRIES,
    retry_delay: float = DEFAULT_LOAD_RETRY_DELAY,
) -> dict[str, Any]:
    queue_path = Path(path)
    last_error: Exception | None = None
    attempts = max(1, retries)
    for attempt in range(attempts):
        try:
            text = queue_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"items": []}
        if text.strip():
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                last_error = exc
            else:
                if isinstance(payload, dict):
                    payload.setdefault("items", [])
                    return payload
                raise ValueError(f"queue payload must be a JSON object: {queue_path}")
        else:
            last_error = json.JSONDecodeError("empty queue file", text, 0)
        if attempt < attempts - 1:
            time.sleep(max(0.0, retry_delay))
    if last_error is not None:
        raise last_error
    return {"items": []}


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temp_name = handle.name
    Path(temp_name).replace(path)


def save_queue(path: str | Path, queue: dict[str, Any]) -> None:
    _write_text_atomic(Path(path), json.dumps(queue, indent=2, sort_keys=False) + "\n")


def find_item(queue: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for item in queue.get("items", []):
        if str(item.get("id")) == str(task_id):
            return item
    return None


def set_status(
    queue: dict[str, Any],
    task_id: str,
    status: str,
    *,
    lane: str | None = None,
    runner: str | None = None,
    note: str | None = None,
    work_order_path: str | None = None,
) -> dict[str, Any]:
    item = find_item(queue, task_id)
    if item is None:
        raise KeyError(f"Task not found: {task_id}")
    item["status"] = status
    item["updated_at"] = utc_now_iso()
    if lane:
        item["lane"] = lane
    if runner:
        item["runner"] = runner
    if work_order_path:
        item["work_order_path"] = work_order_path
    if note:
        notes = item.setdefault("notes", [])
        if isinstance(notes, list):
            notes.append({"ts": utc_now_iso(), "message": note})
    if status in TERMINAL_STATUSES:
        item["completed_at"] = utc_now_iso()
    elif status == "queued":
        item.pop("completed_at", None)
    return item


def recover_stale_running_items(
    queue: dict[str, Any],
    *,
    stale_after_seconds: int,
    note: str = "daemon restart recovered orphaned running task",
    status: str = "queued",
    now: float | None = None,
) -> list[str]:
    current_ts = time.time() if now is None else now
    recovered: list[str] = []
    for item in queue.get("items", []):
        if str(item.get("status") or "") not in STALE_RUNNING_STATUSES:
            continue
        timestamp = parse_iso_timestamp(
            str(item.get("updated_at") or item.get("claimed_at") or item.get("started_at") or "")
        )
        if timestamp is None:
            timestamp = 0.0
        if stale_after_seconds > 0 and (current_ts - timestamp) < stale_after_seconds:
            continue
        task_id = str(item.get("id") or "")
        if not task_id:
            continue
        set_status(
            queue,
            task_id,
            status,
            lane=str(item.get("lane") or "") or None,
            runner=str(item.get("runner") or "") or None,
            note=note,
            work_order_path=str(item.get("work_order_path") or "") or None,
        )
        recovered.append(task_id)
    return recovered
