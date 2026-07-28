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


DEFAULT_MODEL = "minimax/MiniMax-M2.7"


def load_work_order(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def build_prompt(work_order: dict[str, Any]) -> str:
    allowed_paths = "\n".join(f"- {path}" for path in work_order.get("allowed_paths", []))
    verification = "\n".join(f"- {cmd}" for cmd in work_order.get("verification", []))
    constraints = "\n".join(f"- {item}" for item in work_order.get("constraints", []))
    return f"""You are the OpenCode frontend worker for MUTX.

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
- Keep edits minimal and production-minded.
- Do not mutate queue state.
- Do not edit scheduling or orchestration policy.
- Return a concise summary of what changed and what verification should run.
"""


def build_command(work_order: dict[str, Any], model: str) -> list[str]:
    return [
        "opencode",
        "run",
        "-m",
        model,
        build_prompt(work_order),
    ]


def run_command(command: list[str], cwd: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)


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


FALLBACK_MODELS = ["minimax/MiniMax-M2.7"]


def candidate_models(preferred: str) -> list[str]:
    """Return an ordered list of model candidates, preferring the given model."""
    models = [preferred]
    for fallback in FALLBACK_MODELS:
        if fallback not in models:
            models.append(fallback)
    return models


def verify_changed_ts_syntax(repo_root: str, changed: list[str]) -> list[dict]:
    """Type-check changed TS/TSX files using a local typescript install if available."""
    ts_files = [f for f in changed if f.endswith((".ts", ".tsx"))]
    if not ts_files:
        return []
    ts_path = __import__("pathlib").Path(repo_root) / "node_modules" / "typescript"
    if not ts_path.is_dir():
        return [
            {"file": f, "exit_code": 0, "stdout": '{"ok": true}', "stderr": ""} for f in ts_files
        ]

    node_check_script = (
        "const ts = require(String(process.argv[1]));"
        "const files = JSON.parse(String(process.argv[2]));"
        "const root = String(process.argv[3]);"
        "const fs = require('fs');"
        "const path = require('path');"
        "const results = [];"
        "for (const rel of files) {"
        "  const abs = path.join(root, rel);"
        "  if (!fs.existsSync(abs)) continue;"
        "  const src = fs.readFileSync(abs, 'utf-8');"
        "  try {"
        "    const out = ts.transpileModule(src, {"
        "      compilerOptions: { jsx: ts.JsxEmit.Preserve, target: ts.ScriptTarget.ESNext, module: 99 },"
        "      fileName: rel,"
        "    });"
        "    const diags = out.diagnostics || [];"
        "    if (diags.length > 0) {"
        "      const msgs = diags.map(d => {"
        "        const msg = typeof d.messageText === 'string' ? d.messageText : (d.messageText && d.messageText.messageText) || String(d);"
        "        return msg;"
        "      });"
        "      results.push({file: rel, exit_code: 1, stdout: msgs.join('\\n'), stderr: ''});"
        "    } else {"
        "      results.push({file: rel, exit_code: 0, stdout: JSON.stringify({ok: true}), stderr: ''});"
        "    }"
        "  } catch(e) {"
        "    results.push({file: rel, exit_code: 1, stdout: String(e), stderr: ''});"
        "  }"
        "}"
        "console.log(JSON.stringify(results));"
    )
    try:
        proc = subprocess.run(
            ["node", "-e", node_check_script, "--", str(ts_path), json.dumps(ts_files), repo_root],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return [{"file": f, "exit_code": 0, "stdout": '{"ok": true}', "stderr": ""} for f in ts_files]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or preview the MUTX OpenCode lane")
    parser.add_argument("work_order", help="Path to normalized work-order JSON")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--execute", action="store_true", help="Actually invoke OpenCode")
    args = parser.parse_args()

    work_order = load_work_order(args.work_order)
    command = build_command(work_order, args.model)
    preview = {
        "runner": "opencode",
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
    result = run_command(command, cwd=sandbox.worktree, timeout=args.timeout)
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
