from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def test_cli_wheel_installs_without_deps_and_excludes_server_runtime(
    tmp_path: Path,
) -> None:
    wheel_override = os.environ.get("MUTX_CLI_WHEEL")
    if wheel_override:
        wheels = [Path(wheel_override).resolve()]
    else:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        shutil.copytree(ROOT / "cli", source_dir / "cli")
        shutil.copytree(ROOT / "src", source_dir / "src")
        for file_name in ("pyproject.toml", "README.md", "LICENSE", "LICENSE-FAQ.md"):
            source = ROOT / file_name
            if source.is_file():
                shutil.copy2(source, source_dir / file_name)

        wheel_dir = tmp_path / "wheelhouse"
        wheel_dir.mkdir()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheel_dir),
                str(source_dir),
            ],
            check=True,
            cwd=source_dir,
            capture_output=True,
            text=True,
        )
        wheels = list(wheel_dir.glob("mutx_cli-*.whl"))
    assert len(wheels) == 1
    assert wheels[0].is_file()

    with zipfile.ZipFile(wheels[0]) as wheel:
        members = wheel.namelist()
    assert any(member.startswith("cli/") for member in members)
    assert not any(member.startswith("src/") for member in members)

    clean_environment = {
        key: value for key, value in os.environ.items() if key not in {"PYTHONHOME", "PYTHONPATH"}
    }
    venv_dir = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        cwd=ROOT,
        env=clean_environment,
    )

    pip_bin = venv_dir / "bin" / "pip"
    python_bin = venv_dir / "bin" / "python"
    mutx_bin = venv_dir / "bin" / "mutx"

    subprocess.run(
        [str(pip_bin), "install", "--no-deps", str(wheels[0])],
        check=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=clean_environment,
    )

    metadata_result = subprocess.run(
        [
            str(python_bin),
            "-c",
            (
                "import importlib.metadata as m, importlib.util, json; "
                "d=m.distribution('mutx-cli'); "
                "print(json.dumps({'name': d.metadata['Name'], 'requires': d.requires, "
                "'scripts': sorted(e.name for e in d.entry_points "
                "if e.group == 'console_scripts'), "
                "'has_src': importlib.util.find_spec('src') is not None}))"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=clean_environment,
    )

    assert metadata_result.returncode == 0, metadata_result.stderr
    metadata = json.loads(metadata_result.stdout)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert metadata["name"] == "mutx-cli"
    assert metadata["scripts"] == ["mutx"]
    assert metadata["has_src"] is False
    assert set(project["dependencies"]) <= set(metadata["requires"])
    assert mutx_bin.is_file()

    for worker_name in ("mutx-document-worker", "mutx-reasoning-worker"):
        assert not (venv_dir / "bin" / worker_name).exists()
