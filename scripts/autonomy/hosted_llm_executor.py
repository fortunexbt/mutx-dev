from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_artifacts import (  # noqa: E402
    copy_artifact_to_run,
    record_verification_results,
    utc_now,
    write_text_artifact,
)


AREA_CONTEXT = {
    "area:api": [
        "src/api/main.py",
        "src/api/routes/agents.py",
        "src/api/routes/deployments.py",
        "src/api/routes/auth.py",
    ],
    "area:web": [
        "app/api/_lib/controlPlane.ts",
        "components/app/AppDashboardClient.tsx",
        "app/page.tsx",
    ],
    "area:auth": [
        "src/api/routes/auth.py",
        "app/api/auth/login/route.ts",
        "app/api/auth/register/route.ts",
    ],
    "area:cli-sdk": [
        "cli/main.py",
        "cli/commands/deploy.py",
        "sdk/mutx/__init__.py",
        "sdk/mutx/agents.py",
    ],
    "area:runtime": [
        "src/api/routes/agent_runtime.py",
        "sdk/mutx/agent_runtime.py",
        "src/api/models/models.py",
    ],
    "area:test": [
        "tests/conftest.py",
        "tests/api/test_agents.py",
        ".github/workflows/ci.yml",
    ],
    "area:infra": [
        "infrastructure/Makefile",
        "infrastructure/docker/docker-compose.prod.yml",
        ".github/workflows/infrastructure-drift.yml",
    ],
    "area:ops": [
        "src/api/services/monitor.py",
        "src/api/main.py",
        "infrastructure/monitoring/prometheus/alerts.yml",
    ],
    "area:docs": [
        "README.md",
        "docs/autonomy/OPERATING_MODEL.md",
        "AGENTS.md",
    ],
}

ALLOWED_EXECUTABLES = {
    "python",
    "python3",
    "npm",
    "npx",
    "ruff",
    "./.venv/bin/python",
}

ALLOWED_GIT_COMMANDS = {
    ("git", "status"),
    ("git", "diff"),
}

DEFAULT_MAX_PATCH_BYTES = 50000
DEFAULT_MAX_CHANGED_FILES = 6
SHELL_METACHAR_PATTERN = re.compile(r"[;&|`<>$\n\r]")


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def git_ls_files() -> list[str]:
    result = run(["git", "ls-files"])
    return [line for line in result.stdout.splitlines() if line]


def extract_issue_paths(text: str, repo_files: set[str]) -> list[str]:
    matches = re.findall(r"`([^`]+)`", text)
    found = []
    for match in matches:
        cleaned = match.strip()
        if cleaned in repo_files:
            found.append(cleaned)
    return found


def collect_files(work_order: dict[str, object]) -> list[str]:
    raw_labels = work_order.get("labels", [])
    labels = (
        [label for label in raw_labels if isinstance(label, str)]
        if isinstance(raw_labels, list)
        else []
    )
    repo_files = set(git_ls_files())
    files: list[str] = []
    for label in labels:
        files.extend(AREA_CONTEXT.get(label, []))
    files.extend(extract_issue_paths(str(work_order.get("acceptance", "")), repo_files))
    unique = []
    seen = set()
    for file_path in files:
        if file_path in repo_files and file_path not in seen:
            seen.add(file_path)
            unique.append(file_path)
    return unique[:8]


def read_snippet(path: str, limit: int = 220) -> str:
    content = Path(path).read_text()
    lines = content.splitlines()
    snippet = "\n".join(lines[:limit])
    return f"FILE: {path}\n```\n{snippet}\n```"


def build_prompt(agent: str, brief_text: str, work_order: dict[str, object]) -> str:
    files = collect_files(work_order)
    file_sections = [read_snippet(file_path) for file_path in files]
    general_context = []

    # Resolve AGENTS.md
    agents_resolved = "AGENTS.md" if Path("AGENTS.md").exists() else None
    if agents_resolved and agents_resolved not in files:
        general_context.append(read_snippet(agents_resolved, limit=180))

    # Resolve agent definition — prefer uppercase AGENT.md, fall back to lowercase agent.md
    agent_def_paths = [f"agents/{agent}/AGENT.md", f"agents/{agent}/agent.md"]
    agent_def_resolved = next((p for p in agent_def_paths if Path(p).exists()), None)
    if not agent_def_resolved:
        raise FileNotFoundError(
            f"No agent definition found for '{agent}'. Looked in: {agent_def_paths}. "
            f"Ensure agents/{agent}/AGENT.md exists and is named correctly."
        )
    if agent_def_resolved not in files:
        general_context.append(read_snippet(agent_def_resolved, limit=180))

    for fixed in ["package.json", "pyproject.toml"]:
        if Path(fixed).exists() and fixed not in files:
            general_context.append(read_snippet(fixed, limit=180))

    prompt = f"""
You are the MUTX specialist agent `{agent}` working inside the repository.

Your job is to implement the assigned work order with the smallest safe patch.

Return JSON only with this exact shape:
{{
  "summary": "one short sentence",
  "patch": "```diff\n<unified diff patch>\n```",
  "validation_commands": ["cmd1", "cmd2"]
}}

Rules:
- Output JSON only, no prose before or after.
- The patch must be a valid unified diff against the current repository checkout.
- Keep changes minimal and directly tied to the task.
- Do not modify unrelated files.
- Do not add fake tests or fake passing logic.
- If no safe code change can be made from the provided context, return an empty diff block.
- Validation commands must be drawn from repo-native commands only.

WORK ORDER:
{json.dumps(work_order, indent=2, sort_keys=True)}

BRIEF:
{brief_text}

REPO CONTEXT:
{os.linesep.join(general_context + file_sections)}
"""
    return textwrap.dedent(prompt).strip()


def get_provider_config(model: str) -> tuple[str, str, dict[str, str]]:
    github_models_token = os.environ.get("GITHUB_MODELS_TOKEN", "").strip()
    if github_models_token:
        return (
            "github-models",
            os.environ.get(
                "GITHUB_MODELS_ENDPOINT",
                "https://models.inference.ai.azure.com/chat/completions",
            ),
            {
                "Authorization": f"Bearer {github_models_token}",
                "Content-Type": "application/json",
            },
        )

    openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_api_key:
        return (
            "openai",
            os.environ.get(
                "OPENAI_CHAT_COMPLETIONS_URL", "https://api.openai.com/v1/chat/completions"
            ),
            {
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json",
            },
        )

    raise RuntimeError("Set GITHUB_MODELS_TOKEN or OPENAI_API_KEY for hosted autonomous execution")


def chat_completion(prompt: str, model: str) -> str:
    _, endpoint, headers = get_provider_config(model)
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a careful coding agent that returns strict JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")

    request = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Hosted model request failed: {detail}") from exc

    return body["choices"][0]["message"]["content"]


def parse_json_response(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Hosted model response must be a JSON object")
    return payload


def extract_patch(raw_patch: str) -> str:
    text = raw_patch.strip()
    if text.startswith("```"):
        text = re.sub(r"^```diff\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def count_changed_files_from_patch(patch_text: str) -> int:
    return sum(1 for line in patch_text.splitlines() if line.startswith("diff --git "))


def write_guardrail_failure(reason: str, details: dict[str, object]) -> None:
    failure_path = Path(".autonomy/guardrail-failure.json")
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"reason": reason, "details": details}
    failure_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def enforce_patch_guardrails(patch_text: str) -> None:
    if not patch_text:
        return

    max_patch_bytes = int(os.environ.get("AUTONOMY_MAX_PATCH_BYTES", str(DEFAULT_MAX_PATCH_BYTES)))
    max_changed_files = int(
        os.environ.get("AUTONOMY_MAX_CHANGED_FILES", str(DEFAULT_MAX_CHANGED_FILES))
    )
    patch_size = len(patch_text.encode("utf-8"))
    changed_files = count_changed_files_from_patch(patch_text)

    if patch_size > max_patch_bytes:
        write_guardrail_failure(
            "patch_too_large",
            {
                "patch_size_bytes": patch_size,
                "max_patch_bytes": max_patch_bytes,
                "changed_files": changed_files,
            },
        )
        raise RuntimeError(
            f"Generated patch is {patch_size} bytes, exceeding AUTONOMY_MAX_PATCH_BYTES={max_patch_bytes}"
        )

    if changed_files > max_changed_files:
        write_guardrail_failure(
            "too_many_files",
            {
                "changed_files": changed_files,
                "max_changed_files": max_changed_files,
                "patch_size_bytes": patch_size,
            },
        )
        raise RuntimeError(
            f"Generated patch touches {changed_files} files, exceeding AUTONOMY_MAX_CHANGED_FILES={max_changed_files}"
        )


def apply_patch_text(patch_text: str) -> Path | None:
    if not patch_text:
        return None
    patch_path = Path(".autonomy/generated.patch")
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch_text + "\n")
    run(["git", "apply", str(patch_path)])
    return patch_path


def validate_commands(commands: list[str]) -> list[list[str]]:
    allowed: list[list[str]] = []
    for command in commands[:3]:
        if SHELL_METACHAR_PATTERN.search(command):
            continue
        try:
            argv = shlex.split(command)
        except ValueError:
            continue
        if not argv:
            continue

        if argv[0] in ALLOWED_EXECUTABLES:
            allowed.append(argv)
            continue

        if tuple(argv[:2]) in ALLOWED_GIT_COMMANDS and len(argv) == 2:
            allowed.append(argv)
    return allowed


def run_validation(commands: list[list[str]], run_json_path: Path | None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for index, command in enumerate(commands, start=1):
        started_at = utc_now()
        completed = subprocess.run(command, text=True, capture_output=True)

        if completed.stdout:
            print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
        if completed.stderr:
            print(
                completed.stderr,
                end="" if completed.stderr.endswith("\n") else "\n",
                file=sys.stderr,
            )

        stdout_artifact = None
        stderr_artifact = None
        if run_json_path and completed.stdout:
            stdout_artifact = write_text_artifact(
                run_json_path,
                name=f"verification_{index}_stdout",
                kind="log",
                relative_path=f"verification/{index:02d}.stdout.log",
                content=completed.stdout,
            )["path"]
        if run_json_path and completed.stderr:
            stderr_artifact = write_text_artifact(
                run_json_path,
                name=f"verification_{index}_stderr",
                kind="log",
                relative_path=f"verification/{index:02d}.stderr.log",
                content=completed.stderr,
            )["path"]

        result = {
            "argv": command,
            "status": "passed" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "started_at": started_at,
            "finished_at": utc_now(),
        }
        if stdout_artifact:
            result["stdout_artifact"] = stdout_artifact
        if stderr_artifact:
            result["stderr_artifact"] = stderr_artifact
        results.append(result)

        if completed.returncode != 0:
            break

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a GitHub-hosted LLM coding pass for a MUTX work order"
    )
    parser.add_argument("--agent", required=True)
    parser.add_argument("--brief", required=True)
    parser.add_argument("--work-order", required=True)
    parser.add_argument("--model", default=os.environ.get("AUTONOMY_MODEL", "gpt-4.1-mini"))
    parser.add_argument(
        "--prompt-output",
        default=".autonomy/prompts/latest.md",
        help="Optional prompt artifact path",
    )
    args = parser.parse_args()
    run_json_path = None
    raw_run_json_path = os.environ.get("AUTONOMY_RUN_JSON", "").strip()
    if raw_run_json_path:
        candidate = Path(raw_run_json_path)
        if candidate.exists():
            run_json_path = candidate

    brief_text = Path(args.brief).read_text()
    work_order = json.loads(Path(args.work_order).read_text())
    prompt = build_prompt(args.agent, brief_text, work_order)

    prompt_output = Path(args.prompt_output)
    prompt_output.parent.mkdir(parents=True, exist_ok=True)
    prompt_output.write_text(prompt)
    if run_json_path:
        copy_artifact_to_run(
            run_json_path,
            prompt_output,
            name="prompt",
            kind="generated",
            relative_path="artifacts/prompt.md",
        )

    response_text = chat_completion(prompt, args.model)
    payload = parse_json_response(response_text)

    patch_text = extract_patch(str(payload.get("patch", "")))
    enforce_patch_guardrails(patch_text)
    patch_path = apply_patch_text(patch_text)
    if run_json_path and patch_path:
        copy_artifact_to_run(
            run_json_path,
            patch_path,
            name="generated_patch",
            kind="generated",
            relative_path="artifacts/generated.patch",
        )

    raw_validation_commands: Any = payload.get("validation_commands", [])
    validation_commands = validate_commands(
        raw_validation_commands if isinstance(raw_validation_commands, list) else []
    )
    validation_results = run_validation(validation_commands, run_json_path)
    if run_json_path:
        record_verification_results(
            run_json_path,
            commands=validation_commands,
            results=validation_results,
        )

    summary_path = Path(".autonomy/last-response.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if run_json_path:
        copy_artifact_to_run(
            run_json_path,
            summary_path,
            name="model_response",
            kind="generated",
            relative_path="artifacts/last-response.json",
        )
    if any(result["exit_code"] != 0 for result in validation_results):
        print("Validation failed.")
        return 1
    print(payload.get("summary", "Applied autonomous patch."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
