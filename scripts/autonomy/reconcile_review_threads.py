from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

BOT_LOGINS = {
    "chatgpt-codex-connector",
    "copilot-pull-request-reviewer[bot]",
}


def gh(args: list[str], cwd: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], cwd=str(cwd), text=True, capture_output=True)


def gh_graphql(query: str, variables: dict[str, Any], cwd: str | Path) -> dict[str, Any]:
    command = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        flag = "-F" if isinstance(value, int) else "-f"
        command.extend([flag, f"{key}={value}"])
    result = gh(command, cwd)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def thread_last_comment_at(thread: dict[str, Any]) -> datetime | None:
    comments = (thread.get("comments") or {}).get("nodes") or []
    timestamps = [parse_iso(comment.get("createdAt")) for comment in comments]
    timestamps = [ts for ts in timestamps if ts is not None]
    return max(timestamps) if timestamps else None


def is_bot_only_thread(thread: dict[str, Any]) -> bool:
    comments = (thread.get("comments") or {}).get("nodes") or []
    if not comments:
        return False
    logins = {str(((comment.get("author") or {}).get("login")) or "") for comment in comments}
    return bool(logins) and logins.issubset(BOT_LOGINS)


def should_auto_resolve_thread(
    thread: dict[str, Any], *, pr_updated_at: str | None, changed_files: list[str]
) -> bool:
    if thread.get("isResolved") or thread.get("isOutdated"):
        return False
    if not is_bot_only_thread(thread):
        return False
    path = str(thread.get("path") or "")
    if not path or path not in changed_files:
        return False
    thread_at = thread_last_comment_at(thread)
    pr_at = parse_iso(pr_updated_at)
    if thread_at is None or pr_at is None:
        return False
    return pr_at > thread_at


def load_open_autonomy_prs(repo_root: str | Path) -> list[dict[str, Any]]:
    result = gh(
        [
            "pr",
            "list",
            "--limit",
            "100",
            "--json",
            "number,title,headRefName,updatedAt,isDraft,state",
        ],
        repo_root,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    prs = json.loads(result.stdout)
    return [
        pr
        for pr in prs
        if str(pr.get("headRefName", "")).startswith("autonomy/") and pr.get("state") == "OPEN"
    ]


def pr_changed_files(pr_number: int, repo_root: str | Path) -> list[str]:
    result = gh(["pr", "diff", str(pr_number), "--name-only"], repo_root)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def load_review_threads(repo_root: str | Path, pr_number: int) -> list[dict[str, Any]]:
    query = """
query($owner:String!,$repo:String!,$number:Int!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$number){
      reviewThreads(first:100){
        nodes{
          id
          isResolved
          isOutdated
          path
          line
          comments(first:20){
            nodes{
              author{login}
              body
              createdAt
              url
            }
          }
        }
      }
    }
  }
}
"""
    payload = gh_graphql(
        query, {"owner": "mutx-dev", "repo": "mutx-dev", "number": pr_number}, repo_root
    )
    return payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]


def resolve_thread(repo_root: str | Path, thread_id: str) -> dict[str, Any]:
    mutation = "mutation($threadId:ID!){resolveReviewThread(input:{threadId:$threadId}){thread{id isResolved}}}"
    payload = gh_graphql(mutation, {"threadId": thread_id}, repo_root)
    return payload["data"]["resolveReviewThread"]["thread"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve addressed bot review threads on autonomy PRs"
    )
    parser.add_argument(
        "--repo-root", default=os.environ.get("MUTX_REPO_ROOT", "/Users/fortune/MUTX")
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    actions: list[dict[str, Any]] = []
    for pr in load_open_autonomy_prs(repo_root):
        number = int(pr["number"])
        changed_files = pr_changed_files(number, repo_root)
        threads = load_review_threads(repo_root, number)
        for thread in threads:
            should_resolve = should_auto_resolve_thread(
                thread,
                pr_updated_at=pr.get("updatedAt"),
                changed_files=changed_files,
            )
            entry: dict[str, Any] = {
                "number": number,
                "title": pr.get("title"),
                "thread_id": thread.get("id"),
                "path": thread.get("path"),
                "should_resolve": should_resolve,
                "url": (((thread.get("comments") or {}).get("nodes") or [{}])[0]).get("url"),
            }
            if should_resolve and args.execute:
                entry["resolved"] = resolve_thread(repo_root, str(thread.get("id")))
            actions.append(entry)
    print(json.dumps(actions, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
