from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from queue_state import load_queue, save_queue


def load_task(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    payload = dict(task)
    payload.setdefault("status", "queued")
    payload.setdefault("priority", "p2")
    payload.setdefault("source", "manual")
    payload.setdefault("labels", [])
    if "id" not in payload:
        raise ValueError("Task must include an id")
    if "title" not in payload:
        raise ValueError("Task must include a title")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a clean task into the MUTX autonomy queue")
    parser.add_argument("task", help="Path to task JSON")
    parser.add_argument("--queue", default="mutx-engineering-agents/dispatch/action-queue.json")
    parser.add_argument("--replace", action="store_true", help="Replace existing task with same id")
    args = parser.parse_args()

    queue = load_queue(args.queue)
    task = normalize_task(load_task(args.task))
    items = queue.setdefault("items", [])
    existing_index = next(
        (index for index, item in enumerate(items) if str(item.get("id")) == str(task["id"])), None
    )
    if existing_index is not None:
        if not args.replace:
            raise SystemExit(f"Task already exists: {task['id']}")
        items[existing_index] = task
    else:
        items.append(task)
    save_queue(args.queue, queue)
    print(json.dumps(task, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
