from __future__ import annotations

import argparse
import json

from lane_state import load_lane_state, resume_lane, save_lane_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Resume a paused MUTX autonomy lane")
    parser.add_argument("lane", choices=["codex", "opencode", "main"])
    parser.add_argument("--lane-state", default=".autonomy/lane-state.json")
    parser.add_argument(
        "--by", default="manual", help="Resume source recorded in lane-state metadata"
    )
    args = parser.parse_args()

    payload = load_lane_state(args.lane_state)
    updated = resume_lane(payload, args.lane, resumed_by=args.by)
    save_lane_state(args.lane_state, updated)
    print(json.dumps(updated, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
