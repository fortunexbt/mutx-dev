"""Offline contract tests for the upstream drift checker."""

import json
from datetime import datetime, timezone

import pytest

from scripts.check_upstream_drift import (
    GitHubError,
    Project,
    audit_project,
    load_registry,
    markdown_report,
    stable_version,
)


class FakeGitHub:
    def __init__(self):
        self.commits: dict[tuple[str, str], str] = {}
        self.releases: dict[str, tuple[str, str]] = {}
        self.tags: dict[str, tuple[str, str]] = {}

    def commit_sha(self, repository: str, ref: str) -> str:
        try:
            return self.commits[(repository, ref)]
        except KeyError as exc:
            raise GitHubError(f"missing fake commit {repository}@{ref}") from exc

    def latest_release(self, repository: str) -> tuple[str, str]:
        return self.releases[repository]

    def latest_stable_tag(self, repository: str) -> tuple[str, str]:
        return self.tags[repository]


def test_registry_covers_all_attribution_projects_and_pico_pins() -> None:
    registry = load_registry()
    evidence = json.loads(
        (load_registry.__globals__["ROOT"] / "docs/legal/oss-attribution-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    tracked_ids = {project.id for project in registry.projects}
    evidence_ids = {project["id"] for project in evidence["projects"]}

    assert evidence_ids <= tracked_ids
    assert {
        "pico-hermes",
        "pico-openclaw",
        "pico-nanoclaw",
        "pico-picoclaw",
        "pico-picoclaw-android",
    } <= tracked_ids
    assert registry.sota_epic.endswith("/issues/3688")


def test_branch_check_reports_drift_without_fetching_code() -> None:
    pinned = "a" * 40
    latest = "b" * 40
    project = Project(
        "example",
        "owner/repo",
        None,
        ({"kind": "branch", "branch": "main", "pinned_commit": pinned},),
    )
    github = FakeGitHub()
    github.commits = {
        ("owner/repo", pinned): pinned,
        ("owner/repo", "main"): latest,
    }

    [result] = audit_project(project, github)

    assert result.status == "drift"
    assert result.pinned == pinned[:12]
    assert result.observed == latest[:12]


def test_release_check_reports_current_when_tag_and_commit_match() -> None:
    pinned = "c" * 40
    project = Project(
        "example",
        "owner/repo",
        None,
        ({"kind": "release", "pinned_tag": "v1.2.3", "pinned_commit": pinned},),
    )
    github = FakeGitHub()
    github.commits = {
        ("owner/repo", pinned): pinned,
        ("owner/repo", "v1.2.3"): pinned,
    }
    github.releases = {"owner/repo": ("v1.2.3", pinned)}

    [result] = audit_project(project, github)

    assert result.status == "current"
    assert result.check == "latest stable release"


def test_moved_release_tag_is_a_validation_error() -> None:
    pinned = "d" * 40
    moved = "e" * 40
    project = Project(
        "example",
        "owner/repo",
        None,
        ({"kind": "release", "pinned_tag": "v1.2.3", "pinned_commit": pinned},),
    )
    github = FakeGitHub()
    github.commits = {
        ("owner/repo", pinned): pinned,
        ("owner/repo", "v1.2.3"): moved,
    }

    [result] = audit_project(project, github)

    assert result.status == "error"
    assert "expected" in result.detail


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.2.3", (1, 2, 3, 0)),
        ("picoclaw_fui-v0.1.4", (0, 1, 4, 0)),
        ("v2026.7.20", (2026, 7, 20, 0)),
        ("v1.2.3-rc.1", None),
        ("nightly", None),
    ],
)
def test_stable_version_recognizes_only_stable_version_tags(tag, expected) -> None:
    assert stable_version(tag) == expected


def test_markdown_report_is_deterministic_and_links_the_epic() -> None:
    registry = load_registry()
    unresolved = next(project for project in registry.projects if project.id == "lacp")
    results = audit_project(unresolved, FakeGitHub())

    report = markdown_report(
        registry,
        results,
        generated_at=datetime(2026, 7, 22, 0, 0, tzinfo=timezone.utc),
    )

    assert "Generated: 2026-07-22T00:00:00+00:00" in report
    assert "issues/3688" in report
    assert "1 unresolved" in report
    assert "clone, import, vendor, or execute" in report
