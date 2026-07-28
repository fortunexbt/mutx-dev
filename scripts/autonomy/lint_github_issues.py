from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any

BROKEN_PREFIXES = ("file://", "/tmp/")
DEFAULT_REPO = "mutx-dev/mutx-dev"


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], text=True, capture_output=True)


def load_open_issues(repo: str, limit: int) -> list[dict[str, Any]]:
    result = run_gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,title,body,url,labels",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "gh issue list failed")
    payload = json.loads(result.stdout or "[]")
    return payload if isinstance(payload, list) else []


def has_broken_body(issue: dict[str, Any]) -> bool:
    body = str(issue.get("body") or "").strip()
    return bool(body) and body.startswith(BROKEN_PREFIXES)


def fallback_body(issue: dict[str, Any]) -> str:
    body = str(issue.get("body") or "").strip()
    title = str(issue.get("title") or "Untitled issue").strip()
    url = str(issue.get("url") or "").strip()
    return (
        f"## Summary\n"
        f"This issue needs its body rewritten because it currently points at a local non-renderable file reference.\n\n"
        f"- title: {title}\n"
        f"- original body: `{body or '(empty)'}`\n"
        f"- issue url: {url}\n\n"
        "## Required follow-up\n"
        "- replace this placeholder with a proper GitHub-renderable markdown brief\n"
        "- use repo-relative paths in backticks\n"
        "- do not use `file:///tmp/...` or local absolute paths\n"
    )


def fix_issue_body(repo: str, issue_number: int, body: str) -> None:
    result = run_gh(["issue", "edit", str(issue_number), "--repo", repo, "--body", body])
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"gh issue edit failed for {issue_number}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect and optionally rewrite malformed GitHub issue bodies"
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--apply", action="store_true", help="Rewrite malformed bodies with a safe fallback"
    )
    args = parser.parse_args()

    issues = load_open_issues(args.repo, args.limit)
    broken = [issue for issue in issues if has_broken_body(issue)]
    report = []
    for issue in broken:
        entry = {
            "number": issue.get("number"),
            "title": issue.get("title"),
            "url": issue.get("url"),
            "body": issue.get("body"),
        }
        if args.apply:
            fix_issue_body(args.repo, int(issue["number"]), fallback_body(issue))
            entry["fixed"] = True
        report.append(entry)
    print(json.dumps({"repo": args.repo, "broken_count": len(broken), "issues": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
