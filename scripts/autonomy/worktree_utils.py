from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable


def run_git(args: list[str], cwd: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True)


def run_gh(args: list[str], cwd: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], cwd=str(cwd), text=True, capture_output=True)


def is_git_worktree(path: str | Path) -> bool:
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_dir():
        return False
    result = run_git(["rev-parse", "--is-inside-work-tree"], candidate)
    return result.returncode == 0 and result.stdout.strip() == "true"


def is_clean_worktree(path: str | Path) -> bool:
    result = run_git(["status", "--short"], path)
    return result.returncode == 0 and not result.stdout.strip()


def list_valid_worktrees(
    candidates: Iterable[str | Path], *, allow_dirty: bool = True
) -> list[str]:
    valid: list[str] = []
    for candidate in candidates:
        candidate_path = Path(candidate)
        if not is_git_worktree(candidate_path):
            continue
        if not allow_dirty and not is_clean_worktree(candidate_path):
            continue
        valid.append(str(candidate_path))
    return valid


def first_valid_worktree(
    candidates: Iterable[str | Path], *, allow_dirty: bool = True
) -> str | None:
    valid = list_valid_worktrees(candidates, allow_dirty=allow_dirty)
    return valid[0] if valid else None


def current_branch(path: str | Path) -> str | None:
    result = run_git(["branch", "--show-current"], path)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def sanitize_branch_name(value: str) -> str:
    cleaned = []
    for char in value.lower():
        if char.isalnum() or char in {"-", "_", "/"}:
            cleaned.append(char)
        else:
            cleaned.append("-")
    branch = "".join(cleaned).strip("-/_")
    while "--" in branch:
        branch = branch.replace("--", "-")
    return branch[:120] or "task"


def default_remote(path: str | Path) -> str | None:
    result = run_git(["remote"], path)
    if result.returncode != 0:
        return None
    remotes = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not remotes:
        return None
    if "origin" in remotes:
        return "origin"
    return remotes[0]


def default_base_branch(path: str | Path, remote: str | None = None) -> str | None:
    selected_remote = remote or default_remote(path)
    if not selected_remote:
        return None
    result = run_git(["symbolic-ref", f"refs/remotes/{selected_remote}/HEAD"], path)
    if result.returncode != 0:
        return "main"
    ref = result.stdout.strip()
    if not ref:
        return "main"
    return ref.rsplit("/", 1)[-1] or "main"


def summarize_handoff_failure(stderr: str, stdout: str = "") -> str:
    text = f"{stdout}\n{stderr}".lower()
    if "could not resolve host" in text or "failed to connect" in text:
        return "network_unavailable"
    if "authentication failed" in text or "could not read username" in text:
        return "auth_failure"
    if "permission denied" in text and "publickey" in text:
        return "auth_failure"
    if "repository not found" in text or "not found" in text:
        return "repo_unavailable"
    if "no such remote" in text:
        return "remote_missing"
    if "not a git repository" in text:
        return "invalid_worktree"
    if "not logged into any github hosts" in text or "authenticate with" in text:
        return "gh_auth_unavailable"
    return "handoff_failed"


def summarize_branch_prepare_failure(stderr: str, stdout: str = "") -> str:
    text = f"{stdout}\n{stderr}".lower()
    if "already checked out at" in text:
        return "branch_in_use"
    if "not a git repository" in text:
        return "invalid_worktree"
    return "branch_prepare_failed"


def local_branch_exists(path: str | Path, branch: str) -> bool:
    result = run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], path)
    return result.returncode == 0


def prepare_task_branch(path: str | Path, branch: str) -> dict[str, Any]:
    if not branch:
        return {"status": "blocked", "reason": "missing_branch"}
    if not is_git_worktree(path):
        return {"status": "blocked", "reason": "invalid_worktree", "branch": branch}
    if not is_clean_worktree(path):
        return {"status": "blocked", "reason": "dirty_worktree", "branch": branch}

    previous_branch = current_branch(path)
    if previous_branch == branch:
        return {
            "status": "ready",
            "branch": branch,
            "previous_branch": previous_branch,
            "created": False,
        }

    if local_branch_exists(path, branch):
        result = run_git(["checkout", branch], path)
        created = False
    else:
        result = run_git(["checkout", "-b", branch], path)
        created = True

    if result.returncode != 0:
        return {
            "status": "blocked",
            "reason": summarize_branch_prepare_failure(result.stderr, result.stdout),
            "branch": branch,
            "previous_branch": previous_branch,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
    return {
        "status": "ready",
        "branch": branch,
        "previous_branch": previous_branch,
        "created": created,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def push_branch(path: str | Path, branch: str, *, remote: str | None = None) -> dict[str, Any]:
    selected_remote = remote or default_remote(path)
    if not branch:
        return {"status": "skipped", "reason": "missing_branch"}
    if not selected_remote:
        return {"status": "skipped", "reason": "remote_missing"}
    result = run_git(["push", "--set-upstream", selected_remote, branch], path)
    payload = {
        "status": "success" if result.returncode == 0 else "failed",
        "remote": selected_remote,
        "branch": branch,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }
    if result.returncode != 0:
        payload["reason"] = summarize_handoff_failure(result.stderr, result.stdout)
    return payload


def gh_cli_available() -> bool:
    return shutil.which("gh") is not None


def gh_authenticated(path: str | Path) -> bool:
    if not gh_cli_available():
        return False
    result = run_gh(["auth", "status"], path)
    return result.returncode == 0


def find_existing_pr(path: str | Path, branch: str) -> dict[str, Any] | None:
    result = run_gh(
        ["pr", "list", "--head", branch, "--json", "number,url,isDraft,state", "--limit", "1"], path
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list) or not payload:
        return None
    pr = payload[0]
    return {
        "status": "existing",
        "number": pr.get("number"),
        "url": pr.get("url"),
        "is_draft": bool(pr.get("isDraft", False)),
        "state": pr.get("state"),
    }


def create_pr(
    path: str | Path,
    branch: str,
    *,
    title: str,
    body: str,
    base_branch: str | None = None,
    draft: bool = True,
) -> dict[str, Any]:
    if not branch:
        return {"status": "skipped", "reason": "missing_branch"}
    if not gh_cli_available():
        return {"status": "skipped", "reason": "gh_unavailable"}
    if not gh_authenticated(path):
        return {"status": "skipped", "reason": "gh_auth_unavailable"}
    existing = find_existing_pr(path, branch)
    if existing:
        return existing
    target_base = base_branch or default_base_branch(path) or "main"
    command = [
        "pr",
        "create",
        "--base",
        target_base,
        "--head",
        branch,
        "--title",
        title,
        "--body",
        body,
    ]
    if draft:
        command.insert(2, "--draft")
    result = run_gh(command, path)
    if result.returncode != 0:
        return {
            "status": "failed",
            "reason": summarize_handoff_failure(result.stderr, result.stdout),
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
            "base_branch": target_base,
        }
    url = result.stdout.strip().splitlines()[-1].strip() if result.stdout.strip() else None
    created = {
        "status": "created",
        "base_branch": target_base,
        "url": url,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "is_draft": draft,
    }
    existing = find_existing_pr(path, branch)
    if existing:
        created["number"] = existing.get("number")
        created["url"] = existing.get("url") or url
    return created


def promote_pr_ready(path: str | Path, pr_number: int | str | None) -> dict[str, Any]:
    if not pr_number:
        return {"status": "skipped", "reason": "missing_pr_number"}
    if not gh_cli_available():
        return {"status": "skipped", "reason": "gh_unavailable"}
    if not gh_authenticated(path):
        return {"status": "skipped", "reason": "gh_auth_unavailable"}
    result = run_gh(["pr", "ready", str(pr_number)], path)
    if result.returncode != 0:
        return {
            "status": "failed",
            "reason": summarize_handoff_failure(result.stderr, result.stdout),
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
    return {
        "status": "ready",
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def enable_pr_auto_merge(
    path: str | Path, pr_number: int | str | None, *, merge_method: str = "squash"
) -> dict[str, Any]:
    if not pr_number:
        return {"status": "skipped", "reason": "missing_pr_number"}
    if not gh_cli_available():
        return {"status": "skipped", "reason": "gh_unavailable"}
    if not gh_authenticated(path):
        return {"status": "skipped", "reason": "gh_auth_unavailable"}
    result = run_gh(["pr", "merge", str(pr_number), "--auto", f"--{merge_method}"], path)
    if result.returncode != 0:
        return {
            "status": "failed",
            "reason": summarize_handoff_failure(result.stderr, result.stdout),
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
            "merge_method": merge_method,
        }
    return {
        "status": "enabled",
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "merge_method": merge_method,
    }


def publish_branch_with_pr(
    path: str | Path,
    branch: str,
    *,
    title: str,
    body: str,
    remote: str | None = None,
    base_branch: str | None = None,
    draft: bool = True,
    enable_auto_merge: bool = False,
) -> dict[str, Any]:
    push_result = push_branch(path, branch, remote=remote)
    effective_base = base_branch or default_base_branch(path, push_result.get("remote")) or "main"
    if push_result.get("status") != "success":
        reason = push_result.get("reason") or "handoff_failed"
        return {
            "status": "partial",
            "branch": branch,
            "remote": push_result.get("remote"),
            "base_branch": effective_base,
            "push": push_result,
            "pr": {"status": "skipped", "reason": f"push_{reason}"},
            "note": f"branch push unavailable ({reason})",
        }
    pr_result = create_pr(
        path, branch, title=title, body=body, base_branch=effective_base, draft=draft
    )
    ready_result: dict[str, Any] | None = None
    auto_merge_result: dict[str, Any] | None = None
    note = f"pushed {branch}"
    status = "partial"
    pr_number = pr_result.get("number")
    if pr_result.get("status") in {"created", "existing"}:
        status = "published"
        draft_state = pr_result.get("is_draft", draft)
        note = f"pushed {branch}; {'draft' if draft_state else 'ready'} PR ready"
        if pr_result.get("status") == "existing" and pr_result.get("is_draft") and not draft:
            ready_result = promote_pr_ready(path, pr_result.get("number"))
            if ready_result.get("status") == "ready":
                pr_result["is_draft"] = False
                note = f"pushed {branch}; ready PR updated"
            else:
                note = f"pushed {branch}; PR ready promotion failed ({ready_result.get('reason', 'handoff_failed')})"
        if enable_auto_merge and not pr_result.get("is_draft", draft):
            auto_merge_result = enable_pr_auto_merge(path, pr_number)
            if auto_merge_result.get("status") == "enabled":
                note += "; auto-merge enabled"
            else:
                note += (
                    f"; auto-merge skipped ({auto_merge_result.get('reason', 'handoff_failed')})"
                )
    elif pr_result.get("status") == "skipped":
        note = f"pushed {branch}; {'draft' if draft else 'ready'} PR skipped ({pr_result.get('reason')})"
    else:
        note = f"pushed {branch}; {'draft' if draft else 'ready'} PR failed ({pr_result.get('reason', 'handoff_failed')})"
    payload = {
        "status": status,
        "branch": branch,
        "remote": push_result.get("remote"),
        "base_branch": effective_base,
        "push": push_result,
        "pr": pr_result,
        "note": note,
    }
    if ready_result is not None:
        payload["ready"] = ready_result
    if auto_merge_result is not None:
        payload["auto_merge"] = auto_merge_result
    return payload


def commit_tracked_files(path: str | Path, files: list[str], message: str) -> str | None:
    if not files:
        return None
    add_result = run_git(["add", "--", *files], path)
    if add_result.returncode != 0:
        return None
    commit_result = run_git(["commit", "-m", message], path)
    if commit_result.returncode != 0:
        return None
    sha_result = run_git(["rev-parse", "HEAD"], path)
    if sha_result.returncode != 0:
        return None
    return sha_result.stdout.strip() or None
