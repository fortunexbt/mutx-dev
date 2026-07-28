from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional, Tuple

MIN_VERSION = (3, 10)
DEFAULT_PYENV_CANDIDATES = (
    Path.home() / ".pyenv" / "versions" / "3.12.8" / "bin" / "python3",
    Path.home() / ".pyenv" / "versions" / "3.12.7" / "bin" / "python3",
    Path.home() / ".pyenv" / "versions" / "3.11.11" / "bin" / "python3",
)


def _version_of(python_bin: str) -> Optional[Tuple[int, int, int]]:
    try:
        result = subprocess.run(
            [python_bin, "-c", 'import sys; print(".".join(map(str, sys.version_info[:3])))'],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    try:
        major, minor, patch = (int(part) for part in text.split(".")[:3])
    except ValueError:
        return None
    return (major, minor, patch)


def _candidate_bins() -> Iterable[str]:
    env_candidates = [
        os.environ.get("MUTX_AUTONOMY_PYTHON"),
        os.environ.get("PYTHON_BIN"),
    ]
    for candidate in env_candidates:
        if candidate:
            yield candidate
    for candidate in DEFAULT_PYENV_CANDIDATES:
        yield str(candidate)
    if sys.executable:
        yield sys.executable
    for name in ("python3", "python"):
        resolved = shutil.which(name)
        if resolved:
            yield resolved


def resolve_python(min_version: Tuple[int, int] = MIN_VERSION) -> Tuple[str, Tuple[int, int, int]]:
    seen = set()
    for candidate in _candidate_bins():
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        version = _version_of(candidate)
        if version is None:
            continue
        if version[:2] >= min_version:
            return candidate, version
    raise SystemExit(
        "No suitable Python runtime found for MUTX autonomy; "
        f"need >= {min_version[0]}.{min_version[1]}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a repo-safe Python runtime for MUTX autonomy scripts"
    )
    parser.add_argument("--print-version", action="store_true")
    args = parser.parse_args()

    python_bin, version = resolve_python()
    if args.print_version:
        print(".".join(map(str, version)))
    else:
        print(python_bin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
