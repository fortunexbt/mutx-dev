from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
AUTONOMY_DIR = ROOT / "scripts" / "autonomy"
SANDBOX_PATH = AUTONOMY_DIR / "work_order_sandbox.py"


def _load_sandbox_module():
    spec = importlib.util.spec_from_file_location("work_order_sandbox", SANDBOX_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SANDBOX = _load_sandbox_module()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


@pytest.fixture
def clean_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "sandbox@example.com")
    _git(repo, "config", "user.name", "Sandbox Test")
    (repo / "docs").mkdir()
    (repo / "docs" / "tracked.md").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", "docs/tracked.md")
    _git(repo, "commit", "-qm", "baseline")
    return repo


def _work_order(repo: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "worktree": str(repo),
        "allowed_paths": ["docs/"],
        "constraints": ["max_changed_files=6"],
    }
    payload.update(overrides)
    return payload


def test_prepare_sandbox_resolves_clean_exact_git_root(clean_repo: Path) -> None:
    sandbox = SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo))

    assert sandbox.worktree == str(clean_repo.resolve())
    assert sandbox.base_commit == _git(clean_repo, "rev-parse", "HEAD").stdout.strip()
    assert sandbox.allowed_paths == ("docs",)
    assert sandbox.max_changed_files == 6


def test_prepare_sandbox_rejects_git_subdirectory(clean_repo: Path) -> None:
    with pytest.raises(SANDBOX.WorkOrderSandboxError) as exc_info:
        SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo / "docs"))

    assert exc_info.value.reason == "worktree_not_root"


@pytest.mark.parametrize(
    "allowed_path",
    ["../outside", "/tmp/outside", ".", ".git/config", "docs/../outside", "docs\\file"],
)
def test_prepare_sandbox_rejects_unsafe_allowed_paths(clean_repo: Path, allowed_path: str) -> None:
    with pytest.raises(SANDBOX.WorkOrderSandboxError) as exc_info:
        SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo, allowed_paths=[allowed_path]))

    assert exc_info.value.reason == "invalid_allowed_path"


def test_prepare_sandbox_rejects_allowed_path_symlink_escape(
    clean_repo: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (clean_repo / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SANDBOX.WorkOrderSandboxError) as exc_info:
        SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo, allowed_paths=["escape"]))

    assert exc_info.value.reason == "allowed_path_escape"


def test_prepare_sandbox_rejects_dirty_worktree(clean_repo: Path) -> None:
    (clean_repo / "docs" / "untracked.md").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(SANDBOX.WorkOrderSandboxError) as exc_info:
        SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo))

    assert exc_info.value.reason == "dirty_worktree"
    assert exc_info.value.context["changed_files"] == ["docs/untracked.md"]


def test_assessment_accepts_changes_inside_declared_paths(clean_repo: Path) -> None:
    sandbox = SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo))
    (clean_repo / "docs" / "tracked.md").write_text("updated\n", encoding="utf-8")

    result = SANDBOX.assess_worktree_changes(sandbox)

    assert result["ok"] is True
    assert result["changed_files"] == ["docs/tracked.md"]


def test_assessment_fails_closed_for_out_of_scope_changes(clean_repo: Path) -> None:
    sandbox = SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo))
    (clean_repo / "app").mkdir()
    (clean_repo / "app" / "page.tsx").write_text("export default null\n", encoding="utf-8")

    result = SANDBOX.assess_worktree_changes(sandbox)

    assert result["ok"] is False
    assert result["reason"] == "changed_path_outside_allowlist"
    assert result["out_of_scope"] == ["app/page.tsx"]


def test_assessment_checks_both_sides_of_cross_boundary_rename(clean_repo: Path) -> None:
    sandbox = SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo))
    (clean_repo / "app").mkdir()
    (clean_repo / "docs" / "tracked.md").rename(clean_repo / "app" / "tracked.md")

    result = SANDBOX.assess_worktree_changes(sandbox)

    assert result["ok"] is False
    assert result["changed_files"] == ["app/tracked.md", "docs/tracked.md"]
    assert result["out_of_scope"] == ["app/tracked.md"]


def test_assessment_catches_out_of_scope_changes_committed_by_worker(clean_repo: Path) -> None:
    sandbox = SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo))
    (clean_repo / "app").mkdir()
    (clean_repo / "app" / "committed.ts").write_text("export const value = 1\n", encoding="utf-8")
    _git(clean_repo, "add", "app/committed.ts")
    _git(clean_repo, "commit", "-qm", "worker tried to hide an out-of-scope change")

    assert SANDBOX.list_changed_files(clean_repo) == []
    result = SANDBOX.assess_worktree_changes(sandbox)

    assert result["ok"] is False
    assert result["reason"] == "worker_mutated_git_history"
    assert result["changed_files"] == []


def test_assessment_reserves_git_history_mutation_for_orchestrator(clean_repo: Path) -> None:
    sandbox = SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo))
    (clean_repo / "docs" / "tracked.md").write_text("worker commit\n", encoding="utf-8")
    _git(clean_repo, "add", "docs/tracked.md")
    _git(clean_repo, "commit", "-qm", "worker bypasses orchestrator")

    result = SANDBOX.assess_worktree_changes(sandbox)

    assert result["ok"] is False
    assert result["reason"] == "worker_mutated_git_history"
    assert result["changed_files"] == []
    assert result["head_commit"] != result["base_commit"]


def test_assessment_rejects_git_hook_tampering(clean_repo: Path) -> None:
    sandbox = SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo))
    hook = clean_repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    result = SANDBOX.assess_worktree_changes(sandbox)

    assert result["ok"] is False
    assert result["reason"] == "repository_metadata_changed"
    assert result["changed_files"] == []


def test_assessment_rejects_git_config_tampering(clean_repo: Path) -> None:
    sandbox = SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo))
    _git(clean_repo, "config", "core.hooksPath", "../hooks")

    result = SANDBOX.assess_worktree_changes(sandbox)

    assert result["ok"] is False
    assert result["reason"] == "repository_metadata_changed"
    assert result["changed_files"] == []


def test_assessment_rejects_changed_symlink_paths(clean_repo: Path, tmp_path: Path) -> None:
    sandbox = SANDBOX.prepare_work_order_sandbox(_work_order(clean_repo))
    outside = tmp_path / "outside"
    outside.mkdir()
    escape = clean_repo / "docs" / "escape"
    escape.symlink_to(outside, target_is_directory=True)
    (escape / "pwned.txt").write_text("outside\n", encoding="utf-8")

    result = SANDBOX.assess_worktree_changes(sandbox)

    assert result["ok"] is False
    assert result["reason"] == "changed_symlink_path"
    assert result["changed_files"] == ["docs/escape"]
    assert result["changed_symlinks"] == ["docs/escape"]


def test_assessment_enforces_clamped_changed_file_limit(clean_repo: Path) -> None:
    sandbox = SANDBOX.prepare_work_order_sandbox(
        _work_order(clean_repo, constraints=["max_changed_files=1"])
    )
    (clean_repo / "docs" / "one.md").write_text("one\n", encoding="utf-8")
    (clean_repo / "docs" / "two.md").write_text("two\n", encoding="utf-8")

    result = SANDBOX.assess_worktree_changes(sandbox)

    assert result["ok"] is False
    assert result["reason"] == "changed_file_limit_exceeded"
    assert result["changed_file_count"] == 2
    assert SANDBOX.max_changed_files_from_constraints(["max_changed_files=1000"]) == 25


@pytest.mark.parametrize(
    "runner_script",
    ["run_codex_lane.py", "run_opencode_lane.py", "run_main_lane.py"],
)
def test_every_lane_runner_blocks_dirty_worktree_before_dispatch(
    clean_repo: Path, tmp_path: Path, runner_script: str
) -> None:
    (clean_repo / "docs" / "untracked.md").write_text("dirty\n", encoding="utf-8")
    work_order_path = tmp_path / f"{runner_script}.json"
    work_order_path.write_text(
        json.dumps(
            {
                "id": "sandbox-contract",
                "title": "Sandbox contract",
                "description": "Must fail before invoking a worker",
                "lane": "main",
                "worktree": str(clean_repo),
                "allowed_paths": ["docs/"],
                "constraints": ["max_changed_files=6"],
                "verification": [],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(AUTONOMY_DIR / runner_script), str(work_order_path), "--execute"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["blocker_class"] == "sandbox_violation"
    assert payload["sandbox"]["reason"] == "dirty_worktree"
    assert payload["verification_passed"] is False


@pytest.mark.parametrize(
    "runner_script",
    ["run_codex_lane.py", "run_opencode_lane.py", "run_main_lane.py"],
)
def test_every_lane_runner_rechecks_boundary_after_verification(
    clean_repo: Path, tmp_path: Path, runner_script: str
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for worker_name in ("codex", "opencode"):
        worker = fake_bin / worker_name
        worker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        worker.chmod(0o755)

    verifier = tmp_path / "write_outside_scope.py"
    verifier.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "target = Path(sys.argv[1]) / 'app' / 'generated.ts'\n"
        "target.parent.mkdir()\n"
        "target.write_text('export const generated = true\\n')\n",
        encoding="utf-8",
    )
    work_order_path = tmp_path / f"verify-{runner_script}.json"
    work_order_path.write_text(
        json.dumps(
            {
                "id": "sandbox-verification-contract",
                "title": "Sandbox verification contract",
                "description": "Verification cannot cross the work-order boundary",
                "lane": "main",
                "worktree": str(clean_repo),
                "allowed_paths": ["docs/"],
                "constraints": ["max_changed_files=6"],
                "verification": [f"{sys.executable} {verifier} {clean_repo}"],
            }
        ),
        encoding="utf-8",
    )
    env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}

    result = subprocess.run(
        [sys.executable, str(AUTONOMY_DIR / runner_script), str(work_order_path), "--execute"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["verification"][0]["exit_code"] == 0
    assert payload["blocker_class"] == "sandbox_violation"
    assert payload["sandbox"]["reason"] == "changed_path_outside_allowlist"
    assert payload["sandbox"]["out_of_scope"] == ["app/generated.ts"]
    assert payload["verification_passed"] is False
