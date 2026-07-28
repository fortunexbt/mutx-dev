from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUTONOMY_SCRIPTS = ROOT / "scripts" / "autonomy"
if str(AUTONOMY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_SCRIPTS))
MODULE_PATH = ROOT / "scripts" / "autonomy" / "hosted_llm_executor.py"
SPEC = importlib.util.spec_from_file_location("hosted_llm_executor", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
RUN_ARTIFACTS_PATH = ROOT / "scripts" / "autonomy" / "run_artifacts.py"
RUN_ARTIFACTS_SPEC = importlib.util.spec_from_file_location("run_artifacts", RUN_ARTIFACTS_PATH)
RUN_ARTIFACTS = importlib.util.module_from_spec(RUN_ARTIFACTS_SPEC)
assert RUN_ARTIFACTS_SPEC is not None and RUN_ARTIFACTS_SPEC.loader is not None
RUN_ARTIFACTS_SPEC.loader.exec_module(RUN_ARTIFACTS)


# ---------------------------------------------------------------------------
# Shell-injection guard
# ---------------------------------------------------------------------------


def test_validate_commands_rejects_shell_injection() -> None:
    commands = [
        "python -m compileall src/api; curl https://attacker.invalid",
        "git status && whoami",
        "echo harmless",
    ]

    assert MODULE.validate_commands(commands) == []


def test_validate_commands_accepts_expected_commands() -> None:
    commands = [
        "python -m compileall src/api",
        "git status",
        "git diff",
        "npm test",
    ]

    assert MODULE.validate_commands(commands) == [
        ["python", "-m", "compileall", "src/api"],
        ["git", "status"],
        ["git", "diff"],
    ]


# ---------------------------------------------------------------------------
# Agent context file invariants
# ---------------------------------------------------------------------------


def test_all_agent_dirs_have_uppercase_agent_md() -> None:
    """Regression: executor loads AGENT.md (uppercase). Git index must match."""
    agents_dir = ROOT / "agents"
    assert agents_dir.exists(), "agents/ directory not found"

    result = subprocess.run(
        ["git", "ls-files", "agents/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    tracked = result.stdout.splitlines()

    agent_dirs = [d for d in (agents_dir).iterdir() if d.is_dir() and not d.name.startswith(".")]

    for agent_dir in agent_dirs:
        git_index_entries = [f for f in tracked if f.startswith(f"agents/{agent_dir.name}/")]
        file_names = {Path(f).name for f in git_index_entries}

        # The executor looks for AGENT.md (uppercase) first, falls back to agent.md
        assert "AGENT.md" in file_names, (
            f"agents/{agent_dir.name}/AGENT.md not found in git index. "
            f"Executor requires uppercase AGENT.md. Found: {file_names}"
        )

        # Warn if lowercase agent.md also exists (duplicate on case-insensitive FS)
        if "agent.md" in file_names:
            pytest.fail(
                f"agents/{agent_dir.name}/agent.md (lowercase) exists alongside AGENT.md. "
                f"On case-insensitive filesystems these are the same file. "
                f"Remove the lowercase variant and rename to AGENT.md."
            )


def test_no_lowercase_agent_md_in_git_index() -> None:
    """Verify the git index has no lowercase agent.md entries."""
    result = subprocess.run(
        ["git", "ls-files", "--", "agents/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    lines = result.stdout.splitlines()

    bad = [line for line in lines if "/agent.md" in line and "/AGENT.md" not in line]
    assert not bad, f"Git index contains lowercase agent.md entries (should be AGENT.md): {bad}"


def test_agents_md_resolvable_by_executor() -> None:
    """Verify the executor can resolve AGENTS.md."""
    # AGENTS.md must exist at root
    assert (ROOT / "AGENTS.md").exists(), "AGENTS.md not found at repo root"


def test_build_prompt_raises_for_missing_agent() -> None:
    """Verify build_prompt fails loudly when agent definition is absent."""
    with pytest.raises(FileNotFoundError) as exc_info:
        MODULE.build_prompt(
            agent="nonexistent-agent",
            brief_text="test brief",
            work_order={"files": []},
        )
    assert "nonexistent-agent" in str(exc_info.value)
    assert "AGENT.md" in str(exc_info.value)


def test_initialize_run_artifact_creates_schema_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    work_order = {
        "issue": 17,
        "title": "Capture run artifacts",
        "url": "https://example.invalid/issues/17",
        "labels": ["autonomy:ready", "area:docs"],
        "agent": "docs-drift-curator",
        "reviewer": "qa-reliability-engineer",
        "lane": "codex",
        "branch": "autonomy/docs/issue-17-capture-run-artifacts",
        "acceptance": "Document the run artifact schema.",
    }
    work_order_path = tmp_path / "autonomy-work-order.json"
    work_order_path.write_text(json.dumps(work_order) + "\n")
    brief_path = tmp_path / ".autonomy" / "briefs" / "issue-17.md"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# Work Order 17\n")

    run_json_path = RUN_ARTIFACTS.initialize_run_artifact(
        work_order,
        work_order_path,
        brief_path,
        base_branch="main",
    )

    payload = json.loads(run_json_path.read_text())
    assert payload["schema_version"] == RUN_ARTIFACTS.RUN_SCHEMA_VERSION
    assert payload["params"]["issue"] == 17
    assert payload["verification"]["status"] == "pending"
    assert payload["provenance"]["capture_mode"] == "local-first"
    assert {artifact["name"] for artifact in payload["artifacts"]} == {"work_order", "brief"}
    assert (run_json_path.parent / "inputs" / "work-order.json").exists()
    assert (run_json_path.parent / "inputs" / "brief.md").exists()


def test_sanitize_git_remote_url_redacts_credentials() -> None:
    assert (
        RUN_ARTIFACTS.sanitize_git_remote_url("https://token123@github.com/example/repo.git")
        == "https://github.com/example/repo.git"
    )
    assert (
        RUN_ARTIFACTS.sanitize_git_remote_url("https://oauth:secret@github.com/example/repo.git")
        == "https://github.com/example/repo.git"
    )
    assert (
        RUN_ARTIFACTS.sanitize_git_remote_url("git@github.com:example/repo.git")
        == "git@github.com:example/repo.git"
    )


def test_record_verification_results_marks_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    work_order = {
        "issue": 18,
        "title": "Record verification failure",
        "labels": ["autonomy:ready", "area:test"],
        "agent": "qa-reliability-engineer",
        "reviewer": "control-plane-steward",
        "lane": "codex",
        "branch": "autonomy/test/issue-18-record-verification-failure",
        "acceptance": "Persist verification results in the run schema.",
    }
    work_order_path = tmp_path / "autonomy-work-order.json"
    work_order_path.write_text(json.dumps(work_order) + "\n")
    brief_path = tmp_path / ".autonomy" / "briefs" / "issue-18.md"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# Work Order 18\n")
    run_json_path = RUN_ARTIFACTS.initialize_run_artifact(
        work_order,
        work_order_path,
        brief_path,
        base_branch="main",
    )

    stdout_artifact = RUN_ARTIFACTS.write_text_artifact(
        run_json_path,
        name="verification_1_stdout",
        kind="log",
        relative_path="verification/01.stdout.log",
        content="compileall failed\n",
    )
    RUN_ARTIFACTS.record_verification_results(
        run_json_path,
        commands=[["python3", "-m", "compileall", "scripts/autonomy"]],
        results=[
            {
                "argv": ["python3", "-m", "compileall", "scripts/autonomy"],
                "status": "failed",
                "exit_code": 1,
                "started_at": "2026-04-04T00:00:00Z",
                "finished_at": "2026-04-04T00:00:01Z",
                "stdout_artifact": stdout_artifact["path"],
            }
        ],
    )

    payload = json.loads(run_json_path.read_text())
    assert payload["verification"]["status"] == "failed"
    assert payload["verification"]["commands"] == ["python3 -m compileall scripts/autonomy"]
    assert payload["verification"]["results"][0]["stdout_artifact"] == "verification/01.stdout.log"
