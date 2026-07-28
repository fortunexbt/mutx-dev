from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_railway_frontend_manifest_keeps_runner_target_and_standalone_start() -> None:
    manifest = read_text("railway-frontend.json")

    assert '"dockerfilePath": "infrastructure/docker/Dockerfile.frontend"' in manifest
    assert '"target": "runner"' in manifest
    assert '"startCommand": "node .next/standalone/server.js"' in manifest


def test_railway_backend_manifest_keeps_healthcheck_contract() -> None:
    manifest = read_text("railway-api.json")

    assert '"dockerfilePath": "infrastructure/docker/Dockerfile.backend"' in manifest
    assert '"healthcheckPath": "/health"' in manifest
    assert '"healthcheckTimeout": 60' in manifest


def test_railway_promotion_script_requires_both_frontend_and_backend_service_ids() -> None:
    script = read_text("scripts/promote-railway-production.sh")

    assert "RAILWAY_FRONTEND_SERVICE_ID" in script
    assert "RAILWAY_API_SERVICE_ID" in script
    assert 'deploy_service "${RAILWAY_FRONTEND_SERVICE_ID}" "frontend"' in script
    assert 'deploy_service "${RAILWAY_API_SERVICE_ID}" "backend"' in script
    assert 'wait_for_release_identity "API" "${API_RELEASE_IDENTITY_URL}"' in script
    assert 'wait_for_release_identity "frontend" "${FRONTEND_RELEASE_IDENTITY_URL}"' in script
    assert "src/api/mutx-release.json" in script
