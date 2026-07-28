from __future__ import annotations

import argparse
import json

from lane_state import load_lane_state
from resume_policy import apply_auto_resume, inspect_lane_resume


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or auto-resume the Codex lane after quota pauses"
    )
    parser.add_argument("--lane", default="codex", choices=["codex", "opencode", "main"])
    parser.add_argument("--lane-state", default=".autonomy/lane-state.json")
    parser.add_argument("--queue", default="mutx-engineering-agents/dispatch/action-queue.json")
    parser.add_argument("--min-pause-seconds", type=int, default=1800)
    parser.add_argument("--max-auto-resumes", type=int, default=3)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually resume the lane and requeue parked items when eligible",
    )
    args = parser.parse_args()

    if args.apply:
        payload = apply_auto_resume(
            args.lane_state,
            args.queue,
            args.lane,
            min_pause_seconds=args.min_pause_seconds,
            max_auto_resumes=args.max_auto_resumes,
        )
    else:
        payload = inspect_lane_resume(
            load_lane_state(args.lane_state),
            args.lane,
            min_pause_seconds=args.min_pause_seconds,
            max_auto_resumes=args.max_auto_resumes,
        )
        payload["changed"] = False
        payload["requeued_items"] = 0
        payload["mode"] = "dry-run"
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
