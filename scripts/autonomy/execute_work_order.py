from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_artifacts import (  # noqa: E402 - direct script execution needs the sibling path.
    copy_artifact_to_run,
    finalize_run,
    initialize_run_artifact,
    record_command_finish,
    record_command_skipped,
    record_command_start,
    write_text_artifact,
)


DEFAULT_MAX_CHANGED_FILES = 6
CODEX_REVIEW_COMMENT = "@codex please review"


def run(
    command: list[str], *, cwd: str | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=check, text=True, capture_output=True)


def git_output(args: list[str]) -> str:
    return run(["git", *args]).stdout.strip()


def resolve_reviewer_login(reviewer_agent: str) -> str | None:
    raw_map = os.environ.get("AUTONOMY_REVIEWER_MAP", "").strip()
    if not raw_map:
        return None
    try:
        reviewer_map = json.loads(raw_map)
    except json.JSONDecodeError:
        return None
    if not isinstance(reviewer_map, dict):
        return None
    login = reviewer_map.get(reviewer_agent)
    return login if isinstance(login, str) and login.strip() else None


def resolve_open_pr_ref(branch: str) -> str:
    # If branch is already a PR ref, keep it. Otherwise try to map to an open PR by head branch.
    result = run(
        ["gh", "pr", "list", "--state", "open", "--json", "number,headRefName", "--limit", "100"],
        check=False,
    )
    if result.returncode != 0:
        return branch

    try:
        pull_requests = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return branch

    for pull_request in pull_requests:
        if pull_request.get("headRefName") == branch:
            pr_number = pull_request.get("number")
            if isinstance(pr_number, int):
                return str(pr_number)
            if isinstance(pr_number, str) and pr_number:
                return pr_number

    return branch


def count_changed_files() -> int:
    status = git_output(["status", "--short"])
    return len([line for line in status.splitlines() if line.strip()])


def write_guardrail_failure(reason: str, details: dict) -> None:
    failure_path = Path(".autonomy/guardrail-failure.json")
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({"reason": reason, "details": details}, indent=2) + "\n")


def enforce_repo_guardrails() -> None:
    max_changed_files = int(
        os.environ.get("AUTONOMY_MAX_CHANGED_FILES", str(DEFAULT_MAX_CHANGED_FILES))
    )
    changed_files = count_changed_files()
    if changed_files > max_changed_files:
        write_guardrail_failure(
            "too_many_worktree_files",
            {
                "changed_files": changed_files,
                "max_changed_files": max_changed_files,
            },
        )
        raise RuntimeError(
            f"Autonomous worktree touches {changed_files} files, exceeding AUTONOMY_MAX_CHANGED_FILES={max_changed_files}"
        )


def ensure_branch(branch: str, base_branch: str) -> None:
    run(["git", "fetch", "origin", base_branch], check=False)
    run(["git", "checkout", base_branch])
    run(["git", "pull", "--ff-only", "origin", base_branch], check=False)
    existing = run(["git", "branch", "--list", branch], check=False).stdout.strip()
    if existing:
        run(["git", "checkout", branch])
        return
    run(["git", "checkout", "-b", branch])


def write_brief(work_order: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    brief_path = output_dir / f"issue-{work_order['issue']}.md"
    lines = [
        f"# Work Order #{work_order['issue']}",
        "",
        f"- title: {work_order['title']}",
        f"- agent: {work_order['agent']}",
        f"- reviewer: {work_order['reviewer']}",
        f"- lane: {work_order['lane']}",
        f"- branch: {work_order['branch']}",
        f"- url: {work_order.get('url', '')}",
        f"- labels: {', '.join(work_order.get('labels', []))}",
        "",
        "## Acceptance / Context",
        "",
        work_order.get("acceptance", "").strip() or "No issue body provided.",
        "",
        "## Constraints",
        "",
        "- Make the smallest correct change.",
        "- Stay inside the owned file area unless the task clearly requires a linked dependency update.",
        "- Open a PR instead of pushing to main.",
    ]
    brief_path.write_text("\n".join(lines) + "\n")
    return brief_path


def maybe_comment_issue(work_order: dict, brief_path: Path) -> None:
    if not os.environ.get("GH_TOKEN"):
        return
    body = (
        f"Executor prepared branch `{work_order['branch']}` for `{work_order['agent']}`.\n\n"
        f"- reviewer: `{work_order['reviewer']}`\n"
        f"- lane: `{work_order['lane']}`\n"
        f"- brief artifact: `{brief_path}`\n"
    )
    run(["gh", "issue", "comment", str(work_order["issue"]), "--body", body], check=False)


def pr_has_codex_review_comment(pr_ref: str) -> bool:
    resolved_pr = resolve_open_pr_ref(pr_ref)
    result = run(
        ["gh", "pr", "view", resolved_pr, "--json", "comments", "--jq", ".comments[].body"],
        check=False,
    )
    if result.returncode != 0:
        return False
    return CODEX_REVIEW_COMMENT.lower() in result.stdout.lower()


def maybe_comment_codex_review(pr_ref: str) -> None:
    if not os.environ.get("GH_TOKEN"):
        return
    resolved_pr = resolve_open_pr_ref(pr_ref)
    if pr_has_codex_review_comment(resolved_pr):
        print("Codex review handoff already present.")
        return
    result = run(["gh", "pr", "comment", resolved_pr, "--body", CODEX_REVIEW_COMMENT], check=False)
    if result.returncode != 0:
        print("Failed to post Codex review handoff comment.")


def run_agent_command(
    work_order: dict,
    brief_path: Path,
    run_json_path: Path,
) -> subprocess.CompletedProcess[str]:
    template = os.environ.get("AUTONOMY_AGENT_CMD_TEMPLATE", "").strip()
    if not template:
        if os.environ.get("GITHUB_MODELS_TOKEN") or os.environ.get("OPENAI_API_KEY"):
            template = (
                "python scripts/autonomy/hosted_llm_executor.py --agent {agent} "
                "--brief {brief} --work-order {work_order}"
            )
        else:
            note = "AUTONOMY_AGENT_CMD_TEMPLATE is not set; branch and brief are prepared."
            print(note)
            record_command_skipped(run_json_path, note=note)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    command = template.format(
        issue=work_order["issue"],
        agent=work_order["agent"],
        reviewer=work_order["reviewer"],
        lane=work_order["lane"],
        branch=work_order["branch"],
        title=work_order["title"],
        brief=str(brief_path),
        work_order=os.environ.get("AUTONOMY_WORK_ORDER_PATH", "autonomy-work-order.json"),
    )
    print(f"Running agent command: {command}")
    argv = shlex.split(command)
    record_command_start(run_json_path, template=template, argv=argv, cwd=str(Path.cwd()))
    result = subprocess.run(argv, text=True, capture_output=True)

    stdout_artifact = None
    stderr_artifact = None

    if result.stdout:
        stdout_artifact = write_text_artifact(
            run_json_path,
            name="agent_command_stdout",
            kind="log",
            relative_path="logs/agent-command.stdout.log",
            content=result.stdout,
        )["path"]
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")

    if result.stderr:
        stderr_artifact = write_text_artifact(
            run_json_path,
            name="agent_command_stderr",
            kind="log",
            relative_path="logs/agent-command.stderr.log",
            content=result.stderr,
        )["path"]
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)

    record_command_finish(
        run_json_path,
        exit_code=result.returncode,
        stdout_artifact=stdout_artifact,
        stderr_artifact=stderr_artifact,
    )
    return result


def sync_optional_run_artifacts(run_json_path: Path, *, since_epoch: float) -> None:
    guardrail_path = Path(".autonomy/guardrail-failure.json")
    if not guardrail_path.exists():
        return
    if guardrail_path.stat().st_mtime < since_epoch:
        return
    copy_artifact_to_run(
        run_json_path,
        guardrail_path,
        name="guardrail_failure",
        kind="metadata",
        relative_path="artifacts/guardrail-failure.json",
    )


def maybe_open_pr(work_order: dict, base_branch: str) -> None:
    if os.environ.get("AUTONOMY_OPEN_PR", "false").lower() != "true":
        return
    status = git_output(["status", "--short"])
    if not status:
        print("No changes detected; skipping PR creation.")
        return

    run(["git", "add", "."])
    commit_message = f"autonomy: issue #{work_order['issue']} via {work_order['agent']}"
    run(["git", "commit", "-m", commit_message], check=False)
    run(["git", "push", "-u", "origin", work_order["branch"]], check=False)

    if not os.environ.get("GH_TOKEN"):
        return

    pr_ref = work_order["branch"]
    create_result = run(
        [
            "gh",
            "pr",
            "create",
            "--draft",
            "--base",
            base_branch,
            "--head",
            work_order["branch"],
            "--title",
            f"autonomy: {work_order['title']}",
            "--body",
            "## What changed?\n\n"
            f"- autonomous implementation for #{work_order['issue']}\n\n"
            "## Why?\n\n"
            f"- advance the `{work_order['agent']}` queue\n\n"
            "## Validation\n\n"
            "- executor-supplied validation pending\n",
        ],
        check=False,
    )

    if create_result.returncode != 0:
        print(
            "Could not create PR (possibly already exists). Ensuring handoff is posted on the active PR."
        )

    maybe_comment_codex_review(pr_ref)

    reviewer_login = resolve_reviewer_login(work_order["reviewer"])
    if reviewer_login and os.environ.get("GH_TOKEN"):
        run(
            [
                "gh",
                "pr",
                "edit",
                pr_ref,
                "--add-assignee",
                reviewer_login,
            ],
            check=False,
        )
        run(
            [
                "gh",
                "pr",
                "comment",
                pr_ref,
                "--body",
                f"Reviewer routing: `{work_order['reviewer']}` -> @{reviewer_login}",
            ],
            check=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and execute a MUTX autonomous work order")
    parser.add_argument("work_order", help="Path to work order JSON")
    parser.add_argument("--base-branch", default=os.environ.get("AUTONOMY_BASE_BRANCH", "main"))
    parser.add_argument(
        "--brief-dir", default=os.environ.get("AUTONOMY_BRIEF_DIR", ".autonomy/briefs")
    )
    args = parser.parse_args()

    work_order_path = Path(args.work_order)
    os.environ["AUTONOMY_WORK_ORDER_PATH"] = str(work_order_path)
    work_order = json.loads(work_order_path.read_text())

    if work_order.get("status") == "idle":
        print("No available work order.")
        return 0

    ensure_branch(work_order["branch"], args.base_branch)
    brief_path = write_brief(work_order, Path(args.brief_dir))
    run_json_path = initialize_run_artifact(
        work_order,
        work_order_path,
        brief_path,
        base_branch=args.base_branch,
    )
    os.environ["AUTONOMY_RUN_ID"] = run_json_path.parent.name
    os.environ["AUTONOMY_RUN_DIR"] = str(run_json_path.parent)
    os.environ["AUTONOMY_RUN_JSON"] = str(run_json_path)
    run_started_epoch = time.time()
    maybe_comment_issue(work_order, brief_path)
    try:
        result = run_agent_command(work_order, brief_path, run_json_path)
        sync_optional_run_artifacts(run_json_path, since_epoch=run_started_epoch)
        if result.returncode != 0:
            finalize_run(run_json_path, status="failed")
            return result.returncode
        enforce_repo_guardrails()
        sync_optional_run_artifacts(run_json_path, since_epoch=run_started_epoch)
        maybe_open_pr(work_order, args.base_branch)
    except Exception:
        sync_optional_run_artifacts(run_json_path, since_epoch=run_started_epoch)
        finalize_run(run_json_path, status="failed")
        raise
    finalize_run(run_json_path, status="completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
