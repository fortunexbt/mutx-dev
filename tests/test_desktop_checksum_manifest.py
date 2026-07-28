import hashlib
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "desktop" / "scripts" / "verify-checksum-manifest.js"
VERSION = "1.4.0"


def artifacts_for(version: str) -> tuple[str, ...]:
    return (
        f"MUTX-{version}-macos-arm64.dmg",
        f"MUTX-{version}-macos-x64.dmg",
        f"MUTX-{version}-macos-arm64.zip",
        f"MUTX-{version}-macos-x64.zip",
    )


def write_valid_release(directory: Path, version: str = VERSION) -> list[str]:
    entries = []
    for index, name in enumerate(artifacts_for(version)):
        body = f"artifact-{index}".encode()
        (directory / name).write_bytes(body)
        entries.append(f"{hashlib.sha256(body).hexdigest()}  {name}")
    (directory / f"MUTX-{version}-SHA256SUMS.txt").write_text(
        "\n".join(entries) + "\n", encoding="utf-8"
    )
    return entries


def run_verifier(directory: Path, version: str = VERSION) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "node",
            str(VERIFIER),
            "--dir",
            str(directory),
            "--version",
            version,
        ],
        capture_output=True,
        text=True,
    )


def test_checksum_verifier_streams_and_accepts_the_exact_four_artifacts(tmp_path: Path) -> None:
    write_valid_release(tmp_path)

    result = run_verifier(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("OK   MUTX-") == 4


@pytest.mark.parametrize("version", ("1.4.0-rc.1", "2.0.0-beta.2.hotfix-7"))
def test_checksum_verifier_accepts_valid_semver_prerelease_artifacts(
    tmp_path: Path,
    version: str,
) -> None:
    write_valid_release(tmp_path, version)

    result = run_verifier(tmp_path, version)

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("OK   MUTX-") == 4


@pytest.mark.parametrize(
    "mutate",
    (
        lambda entries: entries[:-1],
        lambda entries: [entries[0], entries[0], entries[2], entries[3]],
        lambda entries: [*entries, f"{'0' * 64}  unexpected.zip"],
        lambda entries: [entries[0].upper(), *entries[1:]],
    ),
    ids=("missing-entry", "duplicate-entry", "extra-entry", "malformed-entry"),
)
def test_checksum_verifier_rejects_non_exact_manifests(tmp_path: Path, mutate) -> None:
    entries = write_valid_release(tmp_path)
    (tmp_path / f"MUTX-{VERSION}-SHA256SUMS.txt").write_text(
        "\n".join(mutate(entries)) + "\n", encoding="utf-8"
    )

    assert run_verifier(tmp_path).returncode != 0


def test_checksum_verifier_rejects_an_actual_digest_mismatch(tmp_path: Path) -> None:
    write_valid_release(tmp_path)
    (tmp_path / artifacts_for(VERSION)[0]).write_bytes(b"tampered")

    result = run_verifier(tmp_path)

    assert result.returncode != 0
    assert "SHA-256 mismatch" in result.stderr


@pytest.mark.parametrize("version", ("1.4.0-01", "1.4.0+build.1", "1.4.0-rc..1"))
def test_checksum_verifier_rejects_invalid_release_versions(
    tmp_path: Path,
    version: str,
) -> None:
    result = run_verifier(tmp_path, version)

    assert result.returncode != 0
    assert "<release-semver>" in result.stderr
