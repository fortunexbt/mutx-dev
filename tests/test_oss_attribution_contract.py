"""Regression tests for OSS attribution evidence and AARM claim boundaries."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.security.compliance import AARMComplianceChecker


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "docs/legal/oss-attribution-evidence.json"


def _projects() -> dict[str, dict[str, object]]:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["verified_at"] == "2026-07-15"
    return {project["id"]: project for project in payload["projects"]}


def test_upstream_versions_licenses_and_refs_are_pinned() -> None:
    projects = _projects()

    expected = {
        "agent-run": (
            None,
            "MIT",
            "9c7c3fa68413de878fae2d605c90fb334a0201f6",
        ),
        "aarm-docs": (
            None,
            "MIT",
            "8eff208b98786b2c9a578b26cb7eaca440ec4020",
        ),
        "faramesh-core": (
            None,
            "Apache-2.0",
            "e230a9ac2d12d80ed6f632db42b6e1983ccbce82",
        ),
        "fpl-lang": (
            None,
            "Apache-2.0",
            "b7aa0b7ad56f60428d692278a435c5e6640cec2b",
        ),
        "mission-control": (
            "v2.2.0",
            "MIT",
            "0552b00b3b743ed12949e6deb19597655b02bbcc",
        ),
        "orchestra-research": (
            "v1.7.2",
            "MIT",
            "773a52944ba4747a18bd4ae9ade53fff041adcbc",
        ),
        "predict-rlm": (
            "v0.7.2",
            "MIT",
            "4ff334dea79a2f27e96b7a50a358b0427050899e",
        ),
        "guild-ai": (
            "0.9.0",
            "Apache-2.0",
            "dfbefedb6ca5ce3a1341f9f00a4016420f6fc76d",
        ),
        "lacp": (None, None, None),
    }

    assert set(projects) == set(expected)
    for project_id, (version, license_id, ref) in expected.items():
        project = projects[project_id]
        assert project["current_version"] == version
        assert project["license"] == license_id
        assert project["current_ref"] == ref


def test_every_attributed_local_path_exists() -> None:
    for project in _projects().values():
        for relative_path in project["local_paths"]:
            assert (ROOT / relative_path).exists(), (
                f"{project['id']} evidence points to missing local path {relative_path}"
            )


def test_evidence_uses_immutable_source_and_license_links() -> None:
    projects = _projects()

    for project_id, project in projects.items():
        if project_id == "lacp":
            assert project["repository"] is None
            assert project["license_url"] is None
            continue

        current_ref = str(project["current_ref"])
        assert current_ref in str(project["release_url"])
        assert current_ref in str(project["license_url"])

    agent_run = projects["agent-run"]
    assert agent_run["status"] == "adapted-upstream-quarantined"
    assert agent_run["security_review_url"].endswith(
        "/9c7c3fa68413de878fae2d605c90fb334a0201f6/typescript/src/index.ts"
    )
    assert str(agent_run["security_status"]).startswith("quarantined-do-not-import")

    faramesh = projects["faramesh-core"]
    assert faramesh["latest_semver_tag"] == "v1.2.9"
    assert faramesh["latest_semver_tag_ref"] == ("c85237e4e6b13745169291f60b9c6b985285dbaa")
    assert faramesh["latest_semver_tag_license"] == "MPL-2.0"
    assert faramesh["latest_semver_tag_ref"] in faramesh["latest_semver_tag_url"]
    assert faramesh["latest_semver_tag_ref"] in faramesh["latest_semver_tag_license_url"]
    assert faramesh["installer_ref"] == "ae3ebc9066d65e4e930164881c2f2ce2be554c7f"
    assert faramesh["installer_version"] == "v0.2.0"
    assert faramesh["installer_license"] == "MPL-2.0"
    assert faramesh["installer_ref"] in faramesh["installer_source_url"]
    assert faramesh["installer_ref"] in faramesh["installer_license_url"]

    mission_control = projects["mission-control"]
    assert mission_control["verified_at"] == "2026-07-22"
    assert mission_control["comparison_baseline_version"] == "v2.1.0"
    assert mission_control["comparison_baseline_ref"] == (
        "b4ebc5418bea4fa9288a5c17fbddb9ba99740964"
    )
    assert mission_control["provenance_ref"] == ("eb7c35e950b83f73d6fd61e89f7d4b377db2ad50")
    for source_url in mission_control["reviewed_contract_source_urls"]:
        assert mission_control["current_ref"] in source_url


def test_required_apache_and_mpl_license_texts_are_verbatim() -> None:
    apache = (ROOT / "third_party/licenses/Apache-2.0.txt").read_text(encoding="utf-8")
    sdk_license = (ROOT / "sdk/LICENSE").read_text(encoding="utf-8")
    mpl = (ROOT / "third_party/licenses/MPL-2.0.txt").read_text(encoding="utf-8")

    assert apache.startswith("                                 Apache License\n")
    assert "Version 2.0, January 2004" in apache
    assert "END OF TERMS AND CONDITIONS" in apache
    assert "Faramesh contributors" not in apache
    assert "Copyright (c) 2026 MUTX" in sdk_license
    assert "Faramesh contributors" not in sdk_license
    assert mpl.startswith("Mozilla Public License\nVersion 2.0\n")
    assert "10.4. Distributing Source Code Form that is Incompatible" in mpl
    assert "Exhibit B" in mpl


def test_faramesh_installers_are_immutable_and_version_pinned() -> None:
    from cli import faramesh_runtime
    from src.runtime.gateways import faramesh

    expected_ref = "ae3ebc9066d65e4e930164881c2f2ce2be554c7f"
    for module in (faramesh_runtime, faramesh):
        assert module.FAREMESH_INSTALL_REF == expected_ref
        assert module.FAREMESH_INSTALL_VERSION == "0.2.0"
        assert expected_ref in module.FAREMESH_INSTALL_URL
        assert "/main/" not in module.FAREMESH_INSTALL_URL


def test_faramesh_gateway_passes_pinned_version_to_installer() -> None:
    from src.runtime.gateways.faramesh import FAREMESH_INSTALL_VERSION, FarameshGateway

    gateway = FarameshGateway()
    with (
        patch("subprocess.run") as run,
        patch.object(gateway, "_find_bin", return_value="/usr/local/bin/faramesh"),
    ):
        run.side_effect = [
            MagicMock(returncode=0, stdout="#!/bin/sh\n", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        installed, bin_path = gateway.install()

    assert installed is True
    assert bin_path == "/usr/local/bin/faramesh"
    installer_call = run.call_args_list[1]
    assert installer_call.args[0] == [
        "bash",
        "-s",
        "--",
        "--version",
        FAREMESH_INSTALL_VERSION,
        "--no-interactive",
    ]
    assert installer_call.kwargs["input"] == "#!/bin/sh\n"


def test_direct_port_ledger_has_durable_evidence() -> None:
    ledger = (ROOT / "docs/legal/oss-attribution-ledger.md").read_text(encoding="utf-8")

    for evidence_id in ("agent-run", "mission-control", "predict-rlm"):
        assert f"`{evidence_id}`" in ledger

    assert "UI-PORT-PLAN.md" not in ledger
    assert "Record the exact upstream repo URL" not in ledger
    assert "LACP (`MIT`)" not in ledger


def test_mission_control_refresh_preserves_history_and_pins_v220_contract() -> None:
    current_ref = "0552b00b3b743ed12949e6deb19597655b02bbcc"
    comparison_ref = "b4ebc5418bea4fa9288a5c17fbddb9ba99740964"
    historical_port_ref = "eb7c35e950b83f73d6fd61e89f7d4b377db2ad50"
    report = (ROOT / "docs/upstream-dep-report.md").read_text(encoding="utf-8")
    credits = (ROOT / "CREDITS.md").read_text(encoding="utf-8")
    sandbox = (ROOT / "scripts/autonomy/work_order_sandbox.py").read_text(encoding="utf-8")

    for text in (report, credits):
        assert "v2.2.0" in text
        assert current_ref in text
        assert comparison_ref in text
        assert "2026-07-22" in text

    assert historical_port_ref in report
    assert current_ref in sandbox
    assert "src/lib/task-dispatch.ts" in sandbox
    assert "Copyright (c) 2026 Builderz Labs" in sandbox


def test_public_legal_docs_expose_attribution_and_alignment_pages() -> None:
    summary = (ROOT / "SUMMARY.md").read_text(encoding="utf-8")
    legal = (ROOT / "docs/legal/index.md").read_text(encoding="utf-8")

    assert "docs/legal/oss-attribution-ledger.md" in summary
    assert "docs/legal/aarm-alignment.md" in summary
    assert "oss-attribution-evidence.json" in legal
    assert "no Core or Extended conformance claim" in legal


def test_incorrect_embedded_license_and_conformance_claims_do_not_return() -> None:
    aarm_sources = [
        ROOT / "src/security/__init__.py",
        ROOT / "src/security/mediator.py",
        ROOT / "src/security/context.py",
        ROOT / "src/security/policy.py",
        ROOT / "src/security/approvals.py",
        ROOT / "src/security/receipts.py",
        ROOT / "src/security/telemetry.py",
        ROOT / "src/security/compliance.py",
        ROOT / "src/api/routes/security.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in aarm_sources)

    assert "Copyright (c) 2024 aarm-dev" not in combined
    assert "AARM-Compliant Runtime Security" not in combined
    assert "AARM-compliant runtime security" not in combined

    faramesh = (ROOT / "src/runtime/gateways/faramesh.py").read_text(encoding="utf-8")
    assert "Apache-2.0" in faramesh
    assert "MIT License - Copyright (c) 2024 faramesh" not in faramesh

    observability_sources = [
        ROOT / "src/api/models/observability.py",
        ROOT / "src/api/models/observability_models.py",
        ROOT / "src/api/routes/observability.py",
        ROOT / "sdk/mutx/observability.py",
    ]
    for path in observability_sources:
        text = path.read_text(encoding="utf-8")
        assert "Copyright (c) 2026 Builderz Labs" in text
        assert "Copyright (c) 2024 builderz-labs" not in text


def test_local_aarm_check_is_not_a_conformance_pass() -> None:
    report = AARMComplianceChecker().full_audit()

    assert report.version == "2026-03-26"
    assert report.overall_satisfied is False
    assert [result.requirement_id for result in report.results] == [
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
        "R6",
        "R7",
        "R8",
        "R9",
    ]
    assert not any(result.satisfied for result in report.results)
    assert report.summary()["conformance_claim"] == "none"
