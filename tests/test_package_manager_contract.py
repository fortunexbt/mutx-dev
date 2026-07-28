from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_repo_declares_npm_as_the_canonical_package_manager() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    assert package_json["packageManager"] == "npm@11.18.0"
    assert package_json["engines"] == {
        "node": ">=24.15.0",
        "npm": ">=11.18.0 <12",
    }


def test_setup_and_frontend_docker_use_the_same_npm_install_lane() -> None:
    setup_script = read_text("scripts/setup.sh")
    frontend_dockerfile = read_text("infrastructure/docker/Dockerfile.frontend")

    assert "npm ci --legacy-peer-deps" in setup_script
    assert "RUN npm install -g npm@11.18.0" in frontend_dockerfile
    assert "RUN npm ci --legacy-peer-deps" in frontend_dockerfile
    assert "RUN npm install --force" not in frontend_dockerfile


def test_production_dockerfiles_share_the_supported_node_baseline() -> None:
    root_dockerfile = read_text("Dockerfile")
    frontend_dockerfile = read_text("infrastructure/docker/Dockerfile.frontend")

    root_base = root_dockerfile.splitlines()[1]
    frontend_base = frontend_dockerfile.splitlines()[0]
    assert root_base == frontend_base
    assert root_base.startswith("FROM node:24-alpine3.23@sha256:")
    assert len(root_base.removeprefix("FROM node:24-alpine3.23@sha256:").split()[0]) == 64
    assert "RUN npm install -g npm@11.18.0" in root_dockerfile
    assert "FROM node:20" not in root_dockerfile
    assert "FROM node:20" not in frontend_dockerfile
