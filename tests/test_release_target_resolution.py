import os
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
RESOLVER = ROOT / "scripts" / "resolve-release-target.sh"
BINDING_VERIFIER = ROOT / "scripts" / "verify-release-tag-binding.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def run_git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def tagged_repository(tmp_path: Path) -> Path:
    run_git(tmp_path, "init", "--quiet")
    run_git(tmp_path, "branch", "-M", "main")
    (tmp_path / "release.txt").write_text("release\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"version":"1.2.3"}\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "mutx-cli"\nversion = "2.0.0-rc.1"\n', encoding="utf-8"
    )
    (tmp_path / "sdk").mkdir()
    (tmp_path / "sdk" / "pyproject.toml").write_text(
        '[project]\nname = "mutx-sdk"\nversion = "3.4.5"\n', encoding="utf-8"
    )
    run_git(tmp_path, "add", "release.txt", "package.json", "pyproject.toml", "sdk/pyproject.toml")
    run_git(
        tmp_path,
        "-c",
        "user.name=Release Test",
        "-c",
        "user.email=release-test@example.com",
        "commit",
        "--quiet",
        "-m",
        "release fixture",
    )
    run_git(tmp_path, "tag", "-a", "v1.2.3", "-m", "desktop release")
    run_git(tmp_path, "tag", "-a", "cli-v2.0.0-rc.1", "-m", "CLI release")
    run_git(tmp_path, "tag", "-a", "sdk-v3.4.5", "-m", "SDK release")

    (tmp_path / "package.json").write_text('{"version":"1.2.4-rc.1"}\n', encoding="utf-8")
    run_git(tmp_path, "add", "package.json")
    run_git(
        tmp_path,
        "-c",
        "user.name=Release Test",
        "-c",
        "user.email=release-test@example.com",
        "commit",
        "--quiet",
        "-m",
        "desktop prerelease fixture",
    )
    run_git(tmp_path, "tag", "-a", "v1.2.4-rc.1", "-m", "desktop prerelease")
    run_git(tmp_path, "tag", "v1.2.5+build.7")
    run_git(tmp_path, "tag", "cli-v2.0.0+build.7")
    run_git(tmp_path, "tag", "sdk-v3.4.5+build.7")
    run_git(tmp_path, "tag", "v1.2.6")
    run_git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return tmp_path


def run_resolver(
    repository: Path,
    *,
    event_name: str,
    ref_name: str = "",
    requested_version: str = "",
    event_ref: str | None = None,
    event_sha: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    output_path = repository / "github-output.txt"
    env = {
        **os.environ,
        "GITHUB_EVENT_NAME": event_name,
        "GITHUB_REF_NAME": ref_name,
        "GITHUB_REF": event_ref
        if event_ref is not None
        else (f"refs/tags/{ref_name}" if event_name == "push" else "refs/heads/main"),
        "GITHUB_SHA": event_sha
        if event_sha is not None
        else (
            run_git(repository, "rev-parse", f"{ref_name}^{{commit}}")
            if event_name == "push"
            and ref_name in run_git(repository, "tag", "--list").splitlines()
            else "0" * 40
        ),
        "REQUESTED_VERSION": requested_version,
        "GITHUB_OUTPUT": str(output_path),
    }
    result = subprocess.run(
        ["bash", str(RESOLVER)],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
    )
    outputs = {}
    if output_path.exists():
        outputs = dict(
            line.split("=", 1) for line in output_path.read_text(encoding="utf-8").splitlines()
        )
    return result, outputs


def run_binding_verifier(
    repository: Path,
    tmp_path: Path,
    *,
    tag: str = "v1.2.3",
    remote_target: str | None = None,
) -> subprocess.CompletedProcess[str]:
    tag_object = run_git(repository, "rev-parse", f"refs/tags/{tag}")
    target = run_git(repository, "rev-parse", f"refs/tags/{tag}^{{commit}}")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(exist_ok=True)
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        """#!/usr/bin/env python3
import os
import sys

args = " ".join(sys.argv[1:])
if "immutable-releases" in args:
    print("true")
elif "/git/ref/tags/" in args:
    print(f"refs/tags/{os.environ['FAKE_TAG']}\\ttag\\t{os.environ['FAKE_TAG_OBJECT']}")
elif "/git/tags/" in args:
    print(f"commit\\t{os.environ['FAKE_REMOTE_TARGET']}\\ttrue\\tvalid")
else:
    raise SystemExit(f"unexpected gh invocation: {args}")
""",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    env = {
        **os.environ,
        "FAKE_REMOTE_TARGET": remote_target or target,
        "FAKE_TAG": tag,
        "FAKE_TAG_OBJECT": tag_object,
        "GITHUB_REPOSITORY": "mutx-dev/mutx-dev",
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "RELEASE_SHA": target,
        "RELEASE_TAG": tag,
    }
    return subprocess.run(
        ["bash", str(BINDING_VERIFIER)],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("requested_version", ["v1.2.3"])
def test_manual_dispatch_normalizes_and_resolves_exact_existing_desktop_tag(
    tagged_repository: Path,
    requested_version: str,
) -> None:
    result, outputs = run_resolver(
        tagged_repository,
        event_name="workflow_dispatch",
        requested_version=requested_version,
    )

    assert result.returncode == 0, result.stderr
    assert outputs == {
        "target_tag": "v1.2.3",
        "target_commit": run_git(tagged_repository, "rev-parse", "v1.2.3^{commit}"),
        "target_version": "1.2.3",
        "release_lane": "desktop",
        "promote_production": "true",
    }


@pytest.mark.parametrize(
    ("ref_name", "expected_lane", "expected_version", "expected_promotion"),
    [
        ("v1.2.3", "desktop", "1.2.3", "true"),
        ("v1.2.4-rc.1", "desktop", "1.2.4-rc.1", "false"),
        ("cli-v2.0.0-rc.1", "cli", "2.0.0-rc.1", "false"),
        ("sdk-v3.4.5", "sdk", "3.4.5", "false"),
    ],
)
def test_tag_pushes_resolve_the_matching_release_lane(
    tagged_repository: Path,
    ref_name: str,
    expected_lane: str,
    expected_version: str,
    expected_promotion: str,
) -> None:
    result, outputs = run_resolver(
        tagged_repository,
        event_name="push",
        ref_name=ref_name,
    )

    assert result.returncode == 0, result.stderr
    assert outputs["target_tag"] == ref_name
    assert outputs["release_lane"] == expected_lane
    assert outputs["target_version"] == expected_version
    assert outputs["promote_production"] == expected_promotion
    assert outputs["target_commit"] == run_git(
        tagged_repository,
        "rev-parse",
        f"{ref_name}^{{commit}}",
    )


@pytest.mark.parametrize(
    "requested_version",
    [
        "",
        "1.2.3",
        "v1.2",
        "v01.2.3",
        "v1.2.3-01",
        "cli-v2.0.0",
        "v1.2.3+build.7",
        "v1.2.3;touch-pwned",
    ],
)
def test_manual_dispatch_rejects_invalid_or_non_desktop_targets_without_creating_tags(
    tagged_repository: Path,
    requested_version: str,
) -> None:
    tags_before = run_git(tagged_repository, "tag", "--list")

    result, outputs = run_resolver(
        tagged_repository,
        event_name="workflow_dispatch",
        requested_version=requested_version,
    )

    assert result.returncode != 0
    assert outputs == {}
    assert run_git(tagged_repository, "tag", "--list") == tags_before
    assert not (tagged_repository / "pwned").exists()


def test_manual_dispatch_rejects_a_valid_version_without_an_existing_tag(
    tagged_repository: Path,
) -> None:
    result, outputs = run_resolver(
        tagged_repository,
        event_name="workflow_dispatch",
        requested_version="v9.9.9",
    )

    assert result.returncode != 0
    assert "Release tag does not exist: v9.9.9" in result.stderr
    assert outputs == {}
    assert "v9.9.9" not in run_git(tagged_repository, "tag", "--list").splitlines()


def test_resolver_rejects_a_lightweight_release_tag(tagged_repository: Path) -> None:
    result, outputs = run_resolver(
        tagged_repository,
        event_name="push",
        ref_name="v1.2.6",
    )

    assert result.returncode != 0
    assert "must be an annotated tag object" in result.stderr
    assert outputs == {}


def test_resolver_rejects_a_tag_event_sha_mismatch(tagged_repository: Path) -> None:
    result, outputs = run_resolver(
        tagged_repository,
        event_name="push",
        ref_name="v1.2.4-rc.1",
        event_sha="f" * 40,
    )

    assert result.returncode != 0
    assert "event SHA must exactly match" in result.stderr
    assert outputs == {}


def test_resolver_rejects_a_target_outside_origin_main(tagged_repository: Path) -> None:
    stable_commit = run_git(tagged_repository, "rev-parse", "v1.2.3^{commit}")
    run_git(tagged_repository, "update-ref", "refs/remotes/origin/main", stable_commit)

    result, outputs = run_resolver(
        tagged_repository,
        event_name="push",
        ref_name="v1.2.4-rc.1",
    )

    assert result.returncode != 0
    assert "not an ancestor of origin/main" in result.stderr
    assert outputs == {}


def test_resolver_rejects_tag_and_source_version_drift(tagged_repository: Path) -> None:
    run_git(tagged_repository, "tag", "-a", "v9.9.8", "-m", "drifted release")

    result, outputs = run_resolver(
        tagged_repository,
        event_name="workflow_dispatch",
        requested_version="v9.9.8",
    )

    assert result.returncode != 0
    assert "does not match expected version 1.2.4-rc.1" in result.stderr
    assert outputs == {}


def test_binding_verifier_accepts_the_original_signed_tag_object(
    tagged_repository: Path,
    tmp_path: Path,
) -> None:
    result = run_binding_verifier(tagged_repository, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Verified immutable signed tag binding" in result.stdout


def test_binding_verifier_rejects_a_remote_tag_target_change(
    tagged_repository: Path,
    tmp_path: Path,
) -> None:
    result = run_binding_verifier(
        tagged_repository,
        tmp_path,
        remote_target="f" * 40,
    )

    assert result.returncode != 0
    assert "cryptographically signed" in result.stderr


@pytest.mark.parametrize(
    ("event_name", "ref_name"),
    [
        ("push", "v1.2.3-01"),
        ("push", "release-v1.2.3"),
        ("push", "v1.2.5+build.7"),
        ("push", "cli-v2.0.0+build.7"),
        ("push", "sdk-v3.4.5+build.7"),
        ("schedule", "v1.2.3"),
    ],
)
def test_resolver_rejects_malformed_push_tags_and_unsupported_events(
    tagged_repository: Path,
    event_name: str,
    ref_name: str,
) -> None:
    result, outputs = run_resolver(
        tagged_repository,
        event_name=event_name,
        ref_name=ref_name,
    )

    assert result.returncode != 0
    assert outputs == {}


def test_release_workflow_consumes_one_resolved_target_and_preserves_desktop_gates() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow["jobs"]

    resolver = jobs["resolve_target"]
    assert resolver["outputs"] == {
        "target_tag": "${{ steps.target.outputs.target_tag }}",
        "target_commit": "${{ steps.target.outputs.target_commit }}",
        "target_version": "${{ steps.target.outputs.target_version }}",
        "release_lane": "${{ steps.target.outputs.release_lane }}",
        "promote_production": "${{ steps.target.outputs.promote_production }}",
    }
    assert resolver["steps"][0]["with"]["fetch-depth"] == 0
    assert resolver["steps"][1]["run"] == "bash scripts/resolve-release-target.sh"
    assert resolver["steps"][2]["run"] == "bash scripts/verify-release-tag-binding.sh"
    binding_gate = (ROOT / "scripts" / "verify-release-tag-binding.sh").read_text(encoding="utf-8")
    assert "git/ref/tags/${release_tag}" in binding_gate
    assert 'local_tag_object_sha="$(git rev-parse "refs/tags/${release_tag}")"' in binding_gate
    assert ".verification.verified" in binding_gate
    assert "immutable-releases" in binding_gate

    assert jobs["validate"]["needs"] == "resolve_target"
    assert jobs["validate"]["if"] == (
        "github.event_name == 'push' || inputs.operation == 'publish'"
    )
    assert jobs["validate"]["steps"][0]["with"]["ref"] == (
        "${{ needs.resolve_target.outputs.target_commit }}"
    )

    for job_name in ("release-app-desktop", "release-cli", "release-sdk"):
        job = jobs[job_name]
        assert job["needs"] == ["resolve_target", "validate"]
        assert job["environment"] == "release-publishing"
        assert job["env"]["RELEASE_TAG"] == "${{ needs.resolve_target.outputs.target_tag }}"
        assert job["env"]["RELEASE_VERSION"] == (
            "${{ needs.resolve_target.outputs.target_version }}"
        )
        assert job["steps"][0]["with"]["ref"] == (
            "${{ needs.resolve_target.outputs.target_commit }}"
        )

    assert jobs["release-app-desktop"]["if"] == (
        "needs.resolve_target.outputs.release_lane == 'desktop' && "
        "(github.event_name == 'push' || inputs.operation == 'publish')"
    )
    assert jobs["release-cli"]["if"] == ("needs.resolve_target.outputs.release_lane == 'cli'")
    assert jobs["release-sdk"]["if"] == ("needs.resolve_target.outputs.release_lane == 'sdk'")

    for job_name, package_name in (("release-cli", "CLI"), ("release-sdk", "SDK")):
        extract_version = next(
            step for step in jobs[job_name]["steps"] if step["name"] == "Extract version"
        )
        assert 'tomllib.load(open("pyproject.toml", "rb"))' in extract_version["run"]
        assert f"does not match {package_name} package version" in extract_version["run"]

    desktop_steps = [step["name"] for step in jobs["release-app-desktop"]["steps"]]
    gates = [
        "Require complete local desktop artifact set",
        "Require exact versioned release notes",
        "Create or update draft GitHub release",
        "Upload signed desktop assets",
        "Verify uploaded desktop artifact set",
    ]
    assert [desktop_steps.index(gate) for gate in gates] == sorted(
        desktop_steps.index(gate) for gate in gates
    )
    assert "startsWith(github.ref" not in workflow_text
    assert "${GITHUB_REF" not in workflow_text
    publisher = jobs["publish-desktop-release"]
    assert publisher["needs"] == [
        "resolve_target",
        "release-app-desktop",
        "desktop-launch-smoke",
    ]
    publisher_steps = [step["name"] for step in publisher["steps"]]
    assert publisher_steps == [
        "Checkout exact originally resolved release commit",
        "Re-resolve tag binding and publish the native-gated draft",
        "Reconfirm original tag binding and require immutable attestation",
    ]
    publish_run = publisher["steps"][1]["run"]
    assert publish_run.index("verify-release-tag-binding.sh") < publish_run.index(
        'gh release edit "${RELEASE_TAG}"'
    )
    assert publisher["steps"][2]["run"].index("verify-release-tag-binding.sh") < publisher["steps"][
        2
    ]["run"].index('gh release verify "${RELEASE_TAG}"')
    promotion = jobs["promote-production"]
    assert promotion["if"] == (
        "needs.resolve_target.outputs.promote_production == 'true' && "
        "needs.publish-desktop-release.result == 'success' && "
        "(github.event_name == 'push' || "
        "inputs.confirm_production == format('PROMOTE {0}', "
        "needs.resolve_target.outputs.target_tag))"
    )
    assert 'expected_confirmation="PROMOTE ${RELEASE_TAG}"' in workflow_text
    assert promotion["with"]["target_commit"] == (
        "${{ needs.resolve_target.outputs.target_commit }}"
    )
    railway_secrets = {
        "RAILWAY_TOKEN": "${{ secrets.RAILWAY_TOKEN }}",
        "RAILWAY_PROJECT_ID": "${{ secrets.RAILWAY_PROJECT_ID }}",
        "RAILWAY_FRONTEND_SERVICE_ID": "${{ secrets.RAILWAY_FRONTEND_SERVICE_ID }}",
        "RAILWAY_API_SERVICE_ID": "${{ secrets.RAILWAY_API_SERVICE_ID }}",
        "RAILWAY_ENVIRONMENT_ID": "${{ secrets.RAILWAY_ENVIRONMENT_ID }}",
    }
    assert promotion["permissions"] == {"contents": "read"}
    assert promotion["secrets"] == railway_secrets
    assert jobs["desktop-launch-smoke"]["strategy"]["matrix"]["include"] == [
        {"arch": "arm64", "runner": "macos-26", "app_dir": "mac-arm64"},
        {"arch": "x64", "runner": "macos-26-intel", "app_dir": "mac"},
    ]
    assert jobs["desktop-launch-smoke"]["needs"] == [
        "resolve_target",
        "release-app-desktop",
        "verify-published-desktop-recovery",
    ]
    assert "inputs.operation == 'promote_existing'" in jobs["desktop-launch-smoke"]["if"]
    recovery = jobs["verify-published-desktop-recovery"]
    assert recovery["environment"] == "release-publishing"
    assert 'gh release verify "${RELEASE_TAG}"' in workflow_text
    assert "gh release verify-asset" in workflow_text
    assert "MUTX_REQUIRE_SIGNATURE_IDENTITY" in workflow_text
    assert jobs["promote-production-recovery"]["needs"] == [
        "resolve_target",
        "desktop-launch-smoke",
    ]
    assert jobs["promote-production-recovery"]["permissions"] == {"contents": "read"}
    assert jobs["promote-production-recovery"]["secrets"] == railway_secrets
    assert jobs["promote-production-recovery"]["if"].endswith(
        "inputs.confirm_production == format('PROMOTE {0}', "
        "needs.resolve_target.outputs.target_tag)"
    )
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert "inputs.version" in workflow["concurrency"]["group"]
    assert "validate-release-version.sh" in RESOLVER.read_text(encoding="utf-8")
    assert "Build metadata is not published" in (
        ROOT / "scripts" / "validate-release-version.sh"
    ).read_text(encoding="utf-8")
