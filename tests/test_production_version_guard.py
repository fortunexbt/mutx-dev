import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check-production-version.cjs"


def run_guard(
    target: str,
    identities: list[dict[str, str]],
    *,
    target_sha: str = "a" * 40,
    ancestor_pairs: tuple[tuple[str, str], ...] = (),
) -> subprocess.CompletedProcess[str]:
    script = f"""
const guard = require({json.dumps(str(GUARD))})
const identities = {json.dumps(identities)}
const ancestorPairs = new Set({json.dumps([f"{left}:{right}" for left, right in ancestor_pairs])})
let index = 0
global.fetch = async () => new Response(JSON.stringify(identities[index++]), {{
  status: 200,
  headers: {{ 'content-type': 'application/json' }},
}})
guard.assertProductionIsNotDowngraded(
  {json.dumps(target)},
  {json.dumps(target_sha)},
  'https://api.mutx.dev/release',
  'https://app.mutx.dev/mutx-release.json',
  {{ isAncestor: (left, right) => ancestorPairs.has(`${{left}}:${{right}}`) }},
).catch((error) => {{ console.error(error.message); process.exitCode = 1 }})
"""
    return subprocess.run(["node", "-e", script], capture_output=True, text=True)


def identity(version: str, marker: str) -> dict[str, str]:
    return {"tag": f"v{version}", "version": version, "sha": marker * 40}


@pytest.mark.parametrize("target", ("1.4.1", "1.4.0"), ids=("upgrade", "same-recovery"))
def test_production_version_guard_allows_upgrade_and_exact_same_commit_recovery(
    target: str,
) -> None:
    result = run_guard(target, [identity("1.4.0", "a"), identity("1.3.9", "b")])

    assert result.returncode == 0, result.stderr


def test_production_version_guard_allows_same_version_forward_ancestry() -> None:
    current_sha = "b" * 40
    target_sha = "c" * 40

    result = run_guard(
        "1.4.0",
        [identity("1.4.0", "b"), identity("1.4.0", "b")],
        target_sha=target_sha,
        ancestor_pairs=((current_sha, target_sha),),
    )

    assert result.returncode == 0, result.stderr
    assert "commit-bound and forward-only" in result.stdout


def test_production_version_guard_rejects_same_version_divergent_commit() -> None:
    result = run_guard(
        "1.4.0",
        [identity("1.4.0", "b"), identity("1.4.0", "b")],
        target_sha="c" * 40,
    )

    assert result.returncode != 0
    assert "neither" in result.stderr
    assert "nor its ancestor" in result.stderr


def test_production_version_guard_rejects_downgrade_against_either_surface() -> None:
    result = run_guard("1.4.0", [identity("1.4.0", "a"), identity("1.5.0", "b")])

    assert result.returncode != 0
    assert "Refusing production downgrade from 1.5.0 to 1.4.0" in result.stderr


def test_production_version_guard_fails_closed_on_malformed_current_identity() -> None:
    malformed = {**identity("1.4.0", "a"), "extra": "ambiguous"}
    result = run_guard("1.4.0", [malformed, identity("1.4.0", "b")])

    assert result.returncode != 0
    assert "unexpected release identity shape" in result.stderr
