#!/usr/bin/env python3
"""Fail fast on known incompatible pinned dependency combinations."""

from __future__ import annotations

from pathlib import Path
import re
import sys


PIN_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([0-9][A-Za-z0-9_.+-]*)\s*$")
REQUIREMENT_NAME_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?")
LOCK_PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")


def normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pinned_versions(requirements_path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-r "):
            continue
        match = PIN_PATTERN.match(line)
        if not match:
            continue
        package, version = match.groups()
        versions[normalize_package_name(package)] = version
    return versions


def parse_requirement_names(requirements_path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = REQUIREMENT_NAME_PATTERN.match(line)
        if match:
            names.add(normalize_package_name(match.group(1)))
    return names


def parse_lock_versions(lock_path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        match = LOCK_PIN_PATTERN.match(line)
        if match:
            package, version = match.groups()
            versions[normalize_package_name(package)] = version
    return versions


def version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for part in version.split("."):
        if not part.isdigit():
            break
        parts.append(int(part))
    return tuple(parts)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    requirements_path = repo_root / "requirements.txt"
    test_requirements_path = repo_root / "test-requirements.txt"
    runtime_lock_path = repo_root / "requirements-runtime.lock"
    ci_lock_path = repo_root / "requirements-ci.lock"
    versions = parse_pinned_versions(requirements_path)
    test_versions = parse_pinned_versions(test_requirements_path)
    test_requirements_text = test_requirements_path.read_text(encoding="utf-8")

    for lock_path in (runtime_lock_path, ci_lock_path):
        if not lock_path.is_file():
            print(f"ERROR: Missing generated dependency lock: {lock_path.name}")
            return 1
        lock_text = lock_path.read_text(encoding="utf-8")
        if (
            "--generate-hashes" not in lock_text.splitlines()[1]
            or "--hash=sha256:" not in lock_text
        ):
            print(f"ERROR: {lock_path.name} must be generated with SHA-256 hashes.")
            return 1

    runtime_lock_versions = parse_lock_versions(runtime_lock_path)
    ci_lock_versions = parse_lock_versions(ci_lock_path)
    runtime_names = parse_requirement_names(requirements_path)
    test_names = parse_requirement_names(test_requirements_path)

    missing_runtime = sorted(runtime_names - runtime_lock_versions.keys())
    missing_ci = sorted((runtime_names | test_names | {"ruff"}) - ci_lock_versions.keys())
    if missing_runtime or missing_ci:
        print(
            "ERROR: Generated dependency locks are stale.\n"
            f"Missing from requirements-runtime.lock: {missing_runtime}\n"
            f"Missing from requirements-ci.lock: {missing_ci}"
        )
        return 1

    for package, version in versions.items():
        if (
            runtime_lock_versions.get(package) != version
            or ci_lock_versions.get(package) != version
        ):
            print(
                "ERROR: Generated dependency lock pin drift detected.\n"
                f"{package} must resolve to {version} in both generated locks."
            )
            return 1

    if "-r requirements.txt" not in test_requirements_text:
        print(
            "ERROR: test-requirements drift detected.\n"
            "test-requirements.txt must include '-r requirements.txt' so test installs start from runtime pins."
        )
        return 1

    if "passlib[bcrypt]" in test_requirements_text:
        print(
            "ERROR: test-requirements drift detected.\n"
            "passlib[bcrypt] is legacy auth baggage and should not be present in test-requirements.txt."
        )
        return 1

    for package_name in ("httpx", "aiosqlite", "sqlalchemy"):
        runtime_version = versions.get(package_name)
        test_version = test_versions.get(package_name)
        if runtime_version and test_version and runtime_version != test_version:
            print(
                "ERROR: test-requirements drift detected.\n"
                f"{package_name} runtime pin is {runtime_version} but test pin is {test_version}.\n"
                "Keep overlapping runtime/test pins in lockstep."
            )
            return 1

    pydantic = versions.get("pydantic")
    pydantic_settings = versions.get("pydantic-settings")

    if pydantic and pydantic_settings:
        pydantic_version = version_tuple(pydantic)
        pydantic_settings_version = version_tuple(pydantic_settings)
        if pydantic_settings_version >= (2, 7, 0) and pydantic_version < (2, 7, 0):
            print(
                "ERROR: Incompatible requirements pinning detected.\n"
                f"- pydantic=={pydantic}\n"
                f"- pydantic-settings=={pydantic_settings}\n"
                "pydantic-settings>=2.7.0 requires pydantic>=2.7.0.\n"
                "Either lower pydantic-settings below 2.7.0 or upgrade pydantic in lockstep."
            )
            return 1

    print("Dependency compatibility checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
