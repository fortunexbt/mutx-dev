import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_python_release_workflows_pin_publish_tools() -> None:
    release_workflow = read_text(".github/workflows/release.yml")

    assert release_workflow.count("'uv==0.11.33'") == 2
    assert release_workflow.count("--with 'twine==6.2.0' twine upload dist/*") == 2
    assert "uv sync --frozen --all-extras" in release_workflow
    assert "uv run --with twine twine upload dist/*" not in release_workflow
    assert "run: twine upload dist/*" not in release_workflow


def test_release_workflows_pin_every_external_action_to_a_full_commit() -> None:
    for workflow_path in (
        ".github/workflows/release.yml",
        ".github/workflows/railway-production-promotion.yml",
    ):
        for line in read_text(workflow_path).splitlines():
            stripped = line.strip()
            if not stripped.startswith("uses:") or "./.github/" in stripped:
                continue
            reference = stripped.split("#", 1)[0].split("@", 1)[1].strip()
            assert re.fullmatch(r"[0-9a-f]{40}", reference), stripped


def test_railway_promotion_release_notes_path_is_version_derived() -> None:
    workflow = read_text(".github/workflows/railway-production-promotion.yml")

    assert 'release_notes_file="docs/releases/v$(echo "${version}" | cut -d. -f1-2).md"' in workflow
    assert "test -f docs/releases/v1.3.md" not in workflow


def test_railway_cli_and_same_version_guard_are_commit_bound() -> None:
    workflow = read_text(".github/workflows/railway-production-promotion.yml")
    promotion = read_text("scripts/promote-railway-production.sh")
    guard = read_text("scripts/check-production-version.cjs")

    assert 'RAILWAY_CLI_VERSION: "5.30.1"' in workflow
    assert "c6169e27e87d95d73fb7a30ec2c6b6c767c042f8a3ba9aa98c92deccda8db10c" in workflow
    assert "sha256sum --check" in workflow
    assert "npm install --global @railway/cli" not in workflow
    assert 'reviewed_railway_cli_version="5.30.1"' in promotion
    assert '"${RELEASE_SHA}"' in promotion
    assert 'spawnSync("git", ["merge-base", "--is-ancestor"' in guard
    assert "commit-bound and forward-only" in guard


def test_production_promotion_calls_inherit_repository_secrets() -> None:
    workflow = read_text(".github/workflows/release.yml")

    assert workflow.count("secrets: inherit") == 2


def test_container_scan_uses_the_real_frontend_dockerfile() -> None:
    workflow = read_text(".github/workflows/ci.yml")

    assert "dockerfile: infrastructure/docker/Dockerfile.frontend" in workflow
    assert "--tag 'mutx-ci-${{ matrix.image }}:${{ github.sha }}'" in workflow
    assert (
        "bash scripts/smoke-frontend-container.sh 'mutx-ci-frontend:${{ github.sha }}'" in workflow
    )
    assert "scan-ref: mutx-ci-${{ matrix.image }}:${{ github.sha }}" in workflow


def test_cli_release_smokes_the_built_wheel_without_dependency_install() -> None:
    workflow = read_text(".github/workflows/release.yml")

    assert "find dist -maxdepth 1 -name 'mutx_cli-*.whl'" in workflow
    assert 'MUTX_CLI_WHEEL="${wheel_path}"' in workflow
    assert "python -m pytest tests/test_cli_distribution.py -q" in workflow
