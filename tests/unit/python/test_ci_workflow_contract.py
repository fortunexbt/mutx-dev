from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
ACTIVE_WORKFLOWS = (
    "ci-health.yml",
    "ci.yml",
    "infrastructure-drift.yml",
    "railway-production-promotion.yml",
    "release.yml",
)
PINNED_ACTION = re.compile(r"^[^./][^@]*@[0-9a-f]{40}$")


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def load_workflow(name: str) -> dict[str, object]:
    return yaml.safe_load((WORKFLOW_DIR / name).read_text(encoding="utf-8"))


def test_active_workflow_inventory_has_one_authoritative_validation_flow() -> None:
    assert tuple(path.name for path in sorted(WORKFLOW_DIR.glob("*.yml"))) == ACTIVE_WORKFLOWS
    assert not tuple(WORKFLOW_DIR.glob("*.disabled"))
    assert not (WORKFLOW_DIR / "ci-autofix.yml").exists()
    assert not (WORKFLOW_DIR / "infrastructure-ci.yml").exists()
    assert not (WORKFLOW_DIR / "infrastructure-validation.yml").exists()

    ci = load_workflow("ci.yml")
    required = ci["jobs"]["required-validation"]
    assert required["name"] == "Required Validation"
    assert required["if"] == "always()"
    assert set(required["needs"]) == {
        "changes",
        "workflow-contracts",
        "python-validation",
        "frontend-validation",
        "infrastructure-validation",
        "compose-smoke",
        "container-scan",
    }
    gate_script = required["steps"][0]["run"]
    assert "success|skipped" in gate_script
    assert "was selected but finished with" in gate_script
    assert "select_surface" in gate_script
    assert "::error::" in gate_script


def test_ci_changed_surface_and_full_run_semantics_are_fail_closed() -> None:
    ci = load_workflow("ci.yml")
    jobs = ci["jobs"]
    changes = jobs["changes"]
    filters = changes["steps"][1]["with"]["filters"]

    assert set(changes["outputs"]) == {
        "ci",
        "python",
        "frontend",
        "infrastructure",
        "compose",
        "container",
    }
    for checker in (
        "requirements-runtime.lock",
        "requirements-ci.lock",
        "scripts/**",
        "scripts/**/*.py",
        "scripts/check_requirements_compat.py",
        "scripts/verify-release-http.mjs",
        "docs/upstream-tracking.json",
        "docs/legal/oss-attribution-evidence.json",
        "tests/unit/python/test_ci_workflow_contract.py",
        "tests/unit/python/test_ci_compose_release_gate.py",
        ".github/workflows/**",
        ".yamllint.yml",
        "alembic.ini",
    ):
        assert f"- '{checker}'" in filters

    parsed_filters = yaml.safe_load(filters)
    assert {".dockerignore", "alembic.ini", "src/api/**", "src/runtime/**"} <= set(
        parsed_filters["container"]
    )
    assert {"src/api/**", "src/runtime/**", "src/security/**"} <= set(parsed_filters["python"])
    assert {"src/api/**", "src/runtime/**", "src/security/**"} <= set(parsed_filters["compose"])
    assert {"scripts/**", "docs/api/openapi.json", "app/types/api.ts"} <= set(
        parsed_filters["frontend"]
    )
    assert {"infrastructure/helm/**", "scripts/deploy*.sh"} <= set(parsed_filters["infrastructure"])

    for job_name in (
        "python-validation",
        "frontend-validation",
        "infrastructure-validation",
        "compose-smoke",
        "container-scan",
    ):
        condition = jobs[job_name]["if"]
        assert "github.event_name != 'pull_request'" in condition
        assert "needs.changes.outputs.ci == 'true'" in condition

    workflow_text = read_text(".github/workflows/ci.yml")
    assert "merge_group:" in workflow_text
    assert "workflow_dispatch:" in workflow_text
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow_text


def test_ci_versions_and_monorepo_gates_match_supported_runtimes() -> None:
    ci = load_workflow("ci.yml")
    jobs = ci["jobs"]
    workflow_contract_commands = "\n".join(
        step.get("run", "") for step in jobs["workflow-contracts"]["steps"]
    )
    assert "python -m pip install 'pytest==9.0.3' 'PyYAML==6.0.3'" in (workflow_contract_commands)
    assert jobs["python-validation"]["strategy"]["matrix"]["python-version"] == [
        "3.11",
        "3.12",
    ]
    python_commands = "\n".join(step.get("run", "") for step in jobs["python-validation"]["steps"])
    assert "--require-hashes" in python_commands
    assert "--only-binary=:all:" in python_commands
    assert "--requirement requirements-ci.lock" in python_commands
    assert "pip install --upgrade pip" not in python_commands
    assert "ruff check ." in python_commands
    assert "ruff format --check ." in python_commands
    assert "python -m compileall -q src cli sdk/mutx scripts examples" in python_commands

    frontend_steps = jobs["frontend-validation"]["steps"]
    node_step = next(step for step in frontend_steps if step["name"] == "Set up Node.js")
    assert node_step["with"]["node-version"] == "24.15.0"
    frontend_commands = "\n".join(step.get("run", "") for step in frontend_steps)
    for command in (
        "npm run test:app",
        "scripts/verify-generated-artifacts.sh",
        "npm run lint",
        "npm run typecheck",
        "scripts/test-release-browser-contract.sh all",
    ):
        assert command in frontend_commands

    infrastructure_commands = "\n".join(
        step.get("run", "") for step in jobs["infrastructure-validation"]["steps"]
    )
    infrastructure_steps = jobs["infrastructure-validation"]["steps"]
    terraform_setup = next(
        step for step in infrastructure_steps if step["name"] == "Set up Terraform"
    )
    helm_setup = next(step for step in infrastructure_steps if step["name"] == "Set up Helm")
    assert terraform_setup["with"]["terraform_version"] == "1.15.8"
    assert helm_setup["with"]["version"] == "v3.21.3"
    assert jobs["infrastructure-validation"]["env"]["COMPOSE_DISABLE_ENV_FILE"] == "1"
    assert jobs["infrastructure-validation"]["env"]["RECEIPT_SIGNING_PRIVATE_KEY"] == (
        "0101010101010101010101010101010101010101010101010101010101010101"
    )
    for command in (
        "make -C infrastructure tf-fmt",
        "make -C infrastructure tf-validate",
        "python -m pip install 'ansible-core==2.21.2' 'ansible-lint==26.6.0'",
        "make -C infrastructure ansible-lint",
        "docker build --check",
        "docker compose -f infrastructure/docker/docker-compose.prod.yml config --quiet",
        "make -C infrastructure monitor-validate",
        "infrastructure/helm/mutx/tests/test_chart.py",
    ):
        assert command in infrastructure_commands

    images = jobs["container-scan"]["strategy"]["matrix"]["include"]
    assert {image["image"] for image in images} == {"api", "frontend"}
    trivy_scan = next(
        step
        for step in jobs["container-scan"]["steps"]
        if step["name"] == "Run Trivy vulnerability scanner"
    )
    assert trivy_scan["with"]["version"] == "v0.72.0"
    assert "exit-code: '1'" in read_text(".github/workflows/ci.yml")

    ansible_requirements = yaml.safe_load(read_text("infrastructure/ansible/requirements.yml"))
    assert ansible_requirements == {
        "collections": [
            {"name": "community.docker", "version": "5.2.1"},
            {
                "name": "community.library_inventory_filtering_v1",
                "version": "1.1.5",
            },
            {"name": "community.general", "version": "13.2.0"},
            {"name": "community.postgresql", "version": "4.2.0"},
        ]
    }
    provision_playbook = read_text("infrastructure/ansible/playbooks/provision.yml")
    assert "\n            db: agent_db" not in provision_playbook
    assert provision_playbook.count("login_db: agent_db") == 2

    root_project = tomllib.loads(read_text("pyproject.toml"))
    sdk_project = tomllib.loads(read_text("sdk/pyproject.toml"))
    assert "pyyaml==6.0.3" in read_text("requirements.txt").lower().splitlines()
    assert "ruff==0.15.22" in root_project["project"]["optional-dependencies"]["dev"]
    assert "ruff==0.15.22" in sdk_project["project"]["optional-dependencies"]["dev"]


def test_external_actions_are_immutable_node24_compatible_pins() -> None:
    for workflow_name in ACTIVE_WORKFLOWS:
        text = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
        assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in text
        assert "ubuntu-latest" not in text
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("uses: "):
                continue
            action = stripped.removeprefix("uses: ").split(" #", 1)[0]
            if action.startswith("./"):
                continue
            assert PINNED_ACTION.fullmatch(action), f"mutable action in {workflow_name}: {action}"


def test_validation_and_drift_checkouts_do_not_persist_tokens() -> None:
    for workflow_name in ("ci.yml", "infrastructure-drift.yml"):
        workflow = load_workflow(workflow_name)
        checkout_steps = [
            step
            for job in workflow["jobs"].values()
            for step in job.get("steps", [])
            if step.get("uses", "").startswith("actions/checkout@")
        ]
        assert checkout_steps
        assert all(
            step.get("with", {}).get("persist-credentials") is False for step in checkout_steps
        )


def test_yamllint_configuration_is_compatible_with_ansible_lint() -> None:
    config = yaml.safe_load(read_text(".yamllint.yml"))
    rules = config["rules"]
    assert rules["comments-indentation"] == "disable"
    assert rules["braces"]["max-spaces-inside"] == 1
    assert rules["octal-values"] == {
        "forbid-explicit-octal": True,
        "forbid-implicit-octal": True,
    }


def test_codeql_and_main_failure_reporting_are_not_duplicated_or_noisy() -> None:
    all_workflows = "\n".join(
        (WORKFLOW_DIR / name).read_text(encoding="utf-8") for name in ACTIVE_WORKFLOWS
    )
    assert all_workflows.count("github/codeql-action/upload-sarif@") == 1
    assert "github/codeql-action/init@" not in all_workflows
    assert "github/codeql-action/analyze@" not in all_workflows

    health = read_text(".github/workflows/ci-health.yml")
    assert "schedule:" not in health
    assert "contents: write" not in health
    assert "pull-requests: write" not in health
    assert "gh pr comment" not in health
    assert "git push" not in health
    assert "<!-- mutx-ci-main-incident -->" in health
    assert "github.rest.issues.create" in health
    assert "github.rest.issues.update" in health
    assert "state: 'closed'" in health
    assert "state_reason: 'not_planned'" in health
    assert "❓ Unrecognized CI failure on `main`" in health
    assert "_Tagged by the CI autofix workflow for human review._" in health
    assert "closeLegacyIncidents" in health
    assert "candidate.run_number > run.run_number" in health
    assert "!['success', 'skipped'].includes(job.conclusion)" in health
    assert "github.event.workflow_run.conclusion == 'failure'" not in health


def test_release_deployment_and_drift_workflows_remain_fail_safe() -> None:
    release = load_workflow("release.yml")
    promotion = load_workflow("railway-production-promotion.yml")
    drift = load_workflow("infrastructure-drift.yml")

    assert release["concurrency"]["cancel-in-progress"] is False
    assert promotion["concurrency"] == {
        "group": "railway-production-promotion",
        "cancel-in-progress": False,
    }
    assert drift["concurrency"] == {
        "group": "infrastructure-drift",
        "cancel-in-progress": False,
    }
    drift_text = read_text(".github/workflows/infrastructure-drift.yml")
    assert "ENABLE_TERRAFORM_DRIFT" in drift_text
    assert "-detailed-exitcode" in drift_text
    assert "TF_VARS_STAGING" in drift_text
    assert "TF_VARS_PRODUCTION" in drift_text
    assert "terraform_version: '1.15.8'" in drift_text
    assert "printf '%s\\n' \"${TF_VARS}\"" in drift_text
    assert 'var-file="${RUNNER_TEMP}/terraform-${{ matrix.environment }}.tfvars"' in drift_text
    assert "environments/${{ matrix.environment }}/terraform.tfvars" not in drift_text
    assert "tfplan-${{ matrix.environment }}.bin" not in drift_text
    assert "terraform-plan-${{ matrix.environment }}" not in drift_text

    upstream = drift["jobs"]["upstream-drift"]
    assert upstream["runs-on"] == "ubuntu-24.04"
    assert upstream["timeout-minutes"] == 10
    upstream_commands = "\n".join(step.get("run", "") for step in upstream["steps"])
    assert "scripts/check_upstream_drift.py" in upstream_commands
    assert "--allow-drift" in upstream_commands
    assert '--markdown-output "$GITHUB_STEP_SUMMARY"' in upstream_commands
    assert "--json-output upstream-drift-report.json" in upstream_commands
    artifact = next(
        step for step in upstream["steps"] if step["name"] == "Upload machine-readable report"
    )
    assert artifact["if"] == "always()"
    assert artifact["with"] == {
        "name": "upstream-drift-report",
        "path": "upstream-drift-report.json",
        "if-no-files-found": "warn",
        "retention-days": 30,
    }
    assert drift["permissions"] == {"contents": "read"}
    assert "git push" not in drift_text
