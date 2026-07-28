from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
NODE_BASE = (
    "node:24-alpine3.23@sha256:595398b0081eacda8e1c4c5b97b76cd1020e4d58a8ebcb4843b9bca1e79e7436"
)


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_production_frontend_image_copies_only_runtime_artifacts() -> None:
    root_dockerfile = read_text("Dockerfile")
    root_runner = root_dockerfile.split("FROM base AS runner", 1)[1]
    dockerfile = read_text("infrastructure/docker/Dockerfile.frontend")
    production = dockerfile.split("FROM base AS production", 1)[1].split(
        "FROM production AS runner", 1
    )[0]

    assert "COPY --from=builder /app /app" not in root_runner
    assert "/app/.next/standalone" in root_runner
    assert "/app/.next/static" in root_runner
    assert "/app/public" in root_runner
    assert "COPY --from=builder /app /app" not in production
    for source, destination in (
        ("/app/.next/standalone", "/app/.next/standalone"),
        ("/app/public", "/app/.next/standalone/public"),
        ("/app/.next/static", "/app/.next/standalone/.next/static"),
        ("/app/docs", "/app/docs"),
        ("/app/app/fonts", "/app/app/fonts"),
    ):
        assert source in production
        assert destination in production
    for runtime_document in ("SUMMARY.md", "security.md", "support.md"):
        assert runtime_document in production

    assert f"FROM {NODE_BASE} AS base" in root_dockerfile
    assert f"FROM {NODE_BASE} AS base" in dockerfile
    assert "apk upgrade" not in root_dockerfile
    assert "apk upgrade" not in dockerfile


def test_docker_context_excludes_local_and_sensitive_inputs() -> None:
    dockerignore = read_text(".dockerignore").splitlines()

    for pattern in (
        ".git",
        ".worktrees",
        "**/.worktrees",
        ".venv",
        "**/.venv",
        "infrastructure/terraform",
        "**/.terraform",
        "*.tfstate",
        ".cache",
        ".env*",
        ".secrets",
        "*.pem",
        "playwright-report",
        "test-results",
    ):
        assert pattern in dockerignore

    for required_input in ("!.env.example", "!.env.production.example", "!SUMMARY.md"):
        assert required_input in dockerignore

    for build_input in (
        "package.json",
        "package-lock.json",
        "next.config.mjs",
        "app",
        "components",
        "lib",
        "public",
        "docs",
    ):
        assert build_input not in dockerignore


def test_ci_smokes_the_same_frontend_image_that_it_scans() -> None:
    workflow = yaml.safe_load(read_text(".github/workflows/ci.yml"))
    steps = workflow["jobs"]["container-scan"]["steps"]
    commands = [step.get("run", "") for step in steps]
    filters = workflow["jobs"]["changes"]["steps"][1]["with"]["filters"]

    assert (
        "bash scripts/smoke-frontend-container.sh 'mutx-ci-frontend:${{ github.sha }}'" in commands
    )
    workflow_source = read_text(".github/workflows/ci.yml")
    assert "dockerfile: infrastructure/docker/Dockerfile.frontend" in workflow_source
    assert "--tag 'mutx-ci-${{ matrix.image }}:${{ github.sha }}'" in workflow_source
    assert "scan-ref: mutx-ci-${{ matrix.image }}:${{ github.sha }}" in workflow_source
    assert filters.count("- '.dockerignore'") == 4
