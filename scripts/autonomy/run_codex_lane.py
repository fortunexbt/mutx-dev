from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from failure_classifier import classify_failure, extract_retry_after_seconds
from work_order_sandbox import (
    SANDBOX_BLOCKER_CLASS,
    WorkOrderSandboxError,
    assess_worktree_changes,
    list_changed_files,
    prepare_work_order_sandbox,
)


DEFAULT_MODEL = "gpt-5.4"


def load_work_order(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def build_prompt(work_order: dict[str, Any]) -> str:
    allowed_paths = "\n".join(f"- {path}" for path in work_order.get("allowed_paths", []))
    verification = "\n".join(f"- {cmd}" for cmd in work_order.get("verification", []))
    constraints = "\n".join(f"- {item}" for item in work_order.get("constraints", []))
    return f"""You are the Codex backend worker for MUTX.

Task ID: {work_order["id"]}
Title: {work_order["title"]}
Lane: {work_order["lane"]}
Worktree: {work_order["worktree"]}

Description:
{work_order["description"]}

Allowed paths:
{allowed_paths or "- (none declared)"}

Verification commands:
{verification or "- (none declared)"}

Constraints:
{constraints or "- keep the change small and focused"}

Execution rules:
- Stay strictly inside the allowed paths; the runner enforces this boundary after execution.
- Prefer the smallest correct backend change.
- Do not mutate queue state.
- Do not edit scheduling or orchestration policy.
- Return a concise summary of what changed and what verification should run.
"""


def build_command(work_order: dict[str, Any], model: str) -> list[str]:
    return [
        "codex",
        "exec",
        "--sandbox",
        "workspace-write",
        "--model",
        model,
        "--cd",
        work_order["worktree"],
        build_prompt(work_order),
    ]


def run_command(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout)


def changed_files(cwd: str) -> list[str]:
    return list_changed_files(cwd)


def run_verification(commands: list[str], cwd: str) -> list[dict[str, Any]]:
    results = []
    for command in commands:
        argv = shlex.split(command)
        if not argv:
            results.append(
                {"command": command, "exit_code": 2, "stdout": "", "stderr": "empty command"}
            )
            continue
        proc = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, shell=False)
        results.append(
            {
                "command": command,
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or preview the MUTX Codex lane")
    parser.add_argument("work_order", help="Path to normalized work-order JSON")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--execute", action="store_true", help="Actually invoke Codex")
    args = parser.parse_args()

    work_order = load_work_order(args.work_order)
    command = build_command(work_order, args.model)
    preview = {
        "runner": "codex",
        "task_id": work_order.get("id"),
        "lane": work_order.get("lane"),
        "worktree": work_order["worktree"],
        "command": shlex.join(command),
        "allowed_paths": work_order.get("allowed_paths", []),
        "verification_commands": work_order.get("verification", []),
    }

    if not args.execute:
        print(json.dumps(preview, indent=2, sort_keys=True))
        return 0

    try:
        sandbox = prepare_work_order_sandbox(work_order)
    except WorkOrderSandboxError as exc:
        payload = {
            **preview,
            "exit_code": 2,
            "stdout": "",
            "stderr": exc.detail,
            "changed_files": exc.context.get("changed_files", []),
            "verification": [],
            "verification_passed": False,
            "blocker_class": SANDBOX_BLOCKER_CLASS,
            "retry_after_seconds": None,
            "sandbox": exc.to_dict(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2

    work_order["worktree"] = sandbox.worktree
    command = build_command(work_order, args.model)
    preview["worktree"] = sandbox.worktree
    preview["command"] = shlex.join(command)
    result = run_command(command, timeout=args.timeout)
    sandbox_result = assess_worktree_changes(sandbox)
    verification = (
        run_verification(work_order.get("verification", []), sandbox.worktree)
        if sandbox_result["ok"]
        else []
    )
    if sandbox_result["ok"]:
        sandbox_result = assess_worktree_changes(sandbox)
    sandbox_passed = bool(sandbox_result["ok"])
    combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
    blocker_class = classify_failure(combined_output) if sandbox_passed else SANDBOX_BLOCKER_CLASS
    retry_after_seconds = extract_retry_after_seconds(combined_output)
    verification_passed = sandbox_passed and (
        all(item["exit_code"] == 0 for item in verification) if verification else True
    )
    payload = {
        **preview,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "changed_files": sandbox_result["changed_files"],
        "verification": verification,
        "verification_passed": verification_passed,
        "blocker_class": blocker_class,
        "retry_after_seconds": retry_after_seconds,
        "sandbox": sandbox_result,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return (
        result.returncode
        if result.returncode != 0
        else (0 if payload["verification_passed"] else 2)
    )


if __name__ == "__main__":
    raise SystemExit(main())
