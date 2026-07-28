#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

DEFAULT_REPO_URL = "https://github.com/Orchestra-Research/AI-Research-SKILLs.git"
DEFAULT_RELEASE = "v1.7.2"
DEFAULT_COMMIT = "773a52944ba4747a18bd4ae9ade53fff041adcbc"
DEFAULT_DEST = Path.home() / ".mutx" / "skills" / "orchestra-research"
SKIP_ROOTS = {"packages", "docs", "demos", "dev_data", "anthropic_official_docs", ".git", ".github"}


def run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def clone_or_checkout(repo_url: str, commit: str, source: Path | None) -> tuple[Path, bool]:
    if source is not None:
        run("git", "fetch", "--all", "--tags", cwd=source)
        run("git", "checkout", commit, cwd=source)
        return source, False

    temp_dir = Path(tempfile.mkdtemp(prefix="mutx-orchestra-skills-"))
    run("git", "clone", "--depth", "1", repo_url, str(temp_dir))
    run("git", "fetch", "--depth", "1", "origin", commit, cwd=temp_dir)
    run("git", "checkout", commit, cwd=temp_dir)
    return temp_dir, True


def discover_skill_dirs(root: Path) -> list[Path]:
    dirs: list[Path] = []
    for skill_md in root.rglob("SKILL.md"):
        rel = skill_md.relative_to(root)
        if any(part in SKIP_ROOTS for part in rel.parts):
            continue
        dirs.append(skill_md.parent)
    return sorted(dirs)


def sync_skills(source_root: Path, dest_root: Path, *, clean: bool) -> dict[str, object]:
    skill_dirs = discover_skill_dirs(source_root)
    if clean and dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for skill_dir in skill_dirs:
        rel = skill_dir.relative_to(source_root)
        target = dest_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(skill_dir, target)
        copied.append(str(rel))

    manifest = {
        "repo_url": DEFAULT_REPO_URL,
        "version": DEFAULT_RELEASE,
        "commit": run("git", "rev-parse", "HEAD", cwd=source_root),
        "skill_count": len(copied),
        "skills": copied,
    }
    (dest_root / ".mutx-sync.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Orchestra Research skills into the MUTX-managed skill root."
    )
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    parser.add_argument(
        "--source", type=Path, default=None, help="Use an existing local clone instead of cloning."
    )
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument(
        "--no-clean", action="store_true", help="Do not clear the destination before copying."
    )
    args = parser.parse_args()

    source_root, cleanup = clone_or_checkout(
        args.repo_url, args.commit, args.source.expanduser() if args.source else None
    )
    try:
        manifest = sync_skills(source_root, args.dest.expanduser(), clean=not args.no_clean)
        print(json.dumps({"dest": str(args.dest.expanduser()), **manifest}, indent=2))
    finally:
        if cleanup:
            shutil.rmtree(source_root, ignore_errors=True)


if __name__ == "__main__":
    main()
