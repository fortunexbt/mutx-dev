#!/usr/bin/env python3
"""Report drift in MUTX's explicitly tracked GitHub upstreams.

This checker reads metadata only. It never clones, imports, vendors, or executes
upstream code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "docs/upstream-tracking.json"
GITHUB_API_VERSION = "2022-11-28"
STABLE_VERSION = re.compile(r"(?:^|[^0-9])v?(\d+(?:\.\d+){1,3})$")


class RegistryError(ValueError):
    """Raised when the local tracking registry is inconsistent."""


class GitHubError(RuntimeError):
    """Raised when GitHub metadata cannot be read safely."""


@dataclass(frozen=True)
class Project:
    id: str
    repository: str | None
    policy: str | None
    checks: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class Registry:
    sota_epic: str
    projects: tuple[Project, ...]


@dataclass(frozen=True)
class AuditResult:
    project: str
    repository: str | None
    check: str
    status: str
    pinned: str
    observed: str
    detail: str


class GitHubClient:
    """Small GitHub REST client restricted to public repository metadata."""

    def __init__(self, token: str | None = None, api_base: str = "https://api.github.com"):
        self.token = token
        self.api_base = api_base.rstrip("/")

    def _get_json(self, path: str) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "mutx-upstream-drift-checker",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = Request(f"{self.api_base}{path}", headers=headers)
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed API host
                return json.load(response)
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                message = payload.get("message", str(exc.reason))
            except (UnicodeDecodeError, json.JSONDecodeError):
                message = str(exc.reason)
            raise GitHubError(f"GitHub returned {exc.code} for {path}: {message}") from exc
        except URLError as exc:
            raise GitHubError(f"GitHub request failed for {path}: {exc.reason}") from exc

    def commit_sha(self, repository: str, ref: str) -> str:
        payload = self._get_json(f"/repos/{repository}/commits/{quote(ref, safe='')}")
        sha = payload.get("sha") if isinstance(payload, dict) else None
        if not isinstance(sha, str):
            raise GitHubError(f"GitHub returned no commit SHA for {repository}@{ref}")
        return sha

    def latest_release(self, repository: str) -> tuple[str, str]:
        payload = self._get_json(f"/repos/{repository}/releases/latest")
        tag = payload.get("tag_name") if isinstance(payload, dict) else None
        if not isinstance(tag, str):
            raise GitHubError(f"GitHub returned no latest stable release for {repository}")
        return tag, self.commit_sha(repository, tag)

    def latest_stable_tag(self, repository: str) -> tuple[str, str]:
        candidates: list[tuple[tuple[int, ...], str, str]] = []
        for page in range(1, 11):
            payload = self._get_json(f"/repos/{repository}/tags?per_page=100&page={page}")
            if not isinstance(payload, list):
                raise GitHubError(f"GitHub returned an invalid tag list for {repository}")
            for item in payload:
                if not isinstance(item, dict):
                    continue
                tag = item.get("name")
                commit = item.get("commit")
                sha = commit.get("sha") if isinstance(commit, dict) else None
                version = stable_version(tag) if isinstance(tag, str) else None
                if version is not None and isinstance(sha, str):
                    candidates.append((version, tag, sha))
            if len(payload) < 100:
                break
        else:
            raise GitHubError(f"Refusing to infer the latest tag for {repository} beyond 1000 tags")

        if not candidates:
            raise GitHubError(f"GitHub returned no stable semantic version tags for {repository}")
        _, tag, sha = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
        return tag, sha


def stable_version(tag: str) -> tuple[int, ...] | None:
    """Return a comparable version tuple for stable semver/calver-like tags."""

    match = STABLE_VERSION.search(tag)
    if match is None:
        return None
    components = tuple(int(component) for component in match.group(1).split("."))
    return components + (0,) * (4 - len(components))


def repository_slug(repository_url: str) -> str:
    parsed = urlparse(repository_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or parsed.netloc != "github.com" or len(parts) != 2:
        raise RegistryError(f"Expected a canonical GitHub repository URL, got {repository_url!r}")
    return f"{parts[0]}/{parts[1].removesuffix('.git')}"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"Could not read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RegistryError(f"Expected a JSON object in {path}")
    return payload


def load_registry(path: Path = DEFAULT_REGISTRY) -> Registry:
    payload = _read_json(path)
    if payload.get("schema_version") != 1:
        raise RegistryError("Unsupported upstream tracking schema")

    epic = payload.get("sota_epic")
    evidence_file = payload.get("evidence_file")
    raw_projects = payload.get("projects")
    if not isinstance(epic, str) or not isinstance(evidence_file, str):
        raise RegistryError("Registry must declare sota_epic and evidence_file")
    if not isinstance(raw_projects, list):
        raise RegistryError("Registry projects must be a list")

    evidence_path = ROOT / evidence_file
    evidence_payload = _read_json(evidence_path)
    evidence_projects = evidence_payload.get("projects")
    if not isinstance(evidence_projects, list):
        raise RegistryError("Attribution evidence projects must be a list")
    evidence_by_id = {
        project["id"]: project
        for project in evidence_projects
        if isinstance(project, dict) and isinstance(project.get("id"), str)
    }

    projects: list[Project] = []
    seen: set[str] = set()
    for raw_project in raw_projects:
        if not isinstance(raw_project, dict) or not isinstance(raw_project.get("id"), str):
            raise RegistryError("Every tracked project needs a string id")
        project_id = raw_project["id"]
        if project_id in seen:
            raise RegistryError(f"Duplicate tracked project id: {project_id}")
        seen.add(project_id)

        evidence: dict[str, Any] = {}
        evidence_id = raw_project.get("evidence_project")
        if evidence_id is not None:
            if not isinstance(evidence_id, str) or evidence_id not in evidence_by_id:
                raise RegistryError(f"Unknown evidence project for {project_id}: {evidence_id!r}")
            evidence = evidence_by_id[evidence_id]

        repository_url = raw_project.get("repository", evidence.get("repository"))
        if repository_url is not None and not isinstance(repository_url, str):
            raise RegistryError(f"Invalid repository for {project_id}")
        repository = repository_slug(repository_url) if repository_url else None

        raw_checks = raw_project.get("checks")
        if not isinstance(raw_checks, list) or not raw_checks:
            raise RegistryError(f"Tracked project {project_id} has no checks")
        checks: list[dict[str, str]] = []
        for raw_check in raw_checks:
            if not isinstance(raw_check, dict) or raw_check.get("kind") not in {
                "branch",
                "release",
                "tag",
                "unresolved",
            }:
                raise RegistryError(f"Tracked project {project_id} has an invalid check")
            check: dict[str, str] = {}
            for key, value in raw_check.items():
                if key.endswith("_field"):
                    if not isinstance(value, str) or not isinstance(evidence.get(value), str):
                        raise RegistryError(
                            f"{project_id} check references missing evidence field {value!r}"
                        )
                    check[key.removesuffix("_field")] = evidence[value]
                elif isinstance(value, str):
                    check[key] = value
                else:
                    raise RegistryError(f"{project_id} check field {key} must be a string")
            if check["kind"] != "unresolved" and repository is None:
                raise RegistryError(f"Tracked project {project_id} has no repository")
            checks.append(check)

        policy = raw_project.get("policy")
        if policy is not None and not isinstance(policy, str):
            raise RegistryError(f"Invalid policy for {project_id}")
        projects.append(Project(project_id, repository, policy, tuple(checks)))

    missing_evidence = set(evidence_by_id) - {
        project.get("evidence_project") for project in raw_projects if isinstance(project, dict)
    }
    if missing_evidence:
        raise RegistryError(
            "Attribution projects missing from upstream tracking: "
            + ", ".join(sorted(missing_evidence))
        )
    return Registry(epic, tuple(projects))


def _short_sha(sha: str) -> str:
    return sha[:12]


def _result(
    project: Project,
    check: str,
    status: str,
    pinned: str,
    observed: str,
    detail: str,
) -> AuditResult:
    return AuditResult(project.id, project.repository, check, status, pinned, observed, detail)


def audit_project(project: Project, client: GitHubClient) -> list[AuditResult]:
    results: list[AuditResult] = []
    for check in project.checks:
        kind = check["kind"]
        if kind == "unresolved":
            results.append(
                _result(
                    project,
                    "identity",
                    "unresolved",
                    "none",
                    "none",
                    project.policy or "Canonical upstream identity is unresolved",
                )
            )
            continue

        assert project.repository is not None
        try:
            pinned_commit = check.get("pinned_commit")
            if pinned_commit is not None:
                resolved_pin = client.commit_sha(project.repository, pinned_commit)
                if resolved_pin.lower() != pinned_commit.lower():
                    raise GitHubError(
                        f"Pinned commit {pinned_commit} resolved unexpectedly to {resolved_pin}"
                    )

            if kind == "branch":
                branch = check.get("branch")
                if branch is None or pinned_commit is None:
                    raise RegistryError(f"{project.id} branch check is incomplete")
                latest_commit = client.commit_sha(project.repository, branch)
                status = "current" if latest_commit == pinned_commit else "drift"
                detail = project.policy or "Tracked branch head"
                results.append(
                    _result(
                        project,
                        f"branch {branch}",
                        status,
                        _short_sha(pinned_commit),
                        _short_sha(latest_commit),
                        detail,
                    )
                )
                continue

            pinned_tag = check.get("pinned_tag")
            if pinned_tag is None:
                raise RegistryError(f"{project.id} {kind} check has no pinned tag")
            pinned_tag_commit = client.commit_sha(project.repository, pinned_tag)
            if pinned_commit is not None and pinned_tag_commit != pinned_commit:
                raise GitHubError(
                    f"Pinned tag {pinned_tag} resolves to {pinned_tag_commit}, expected {pinned_commit}"
                )

            if kind == "release":
                latest_tag, latest_commit = client.latest_release(project.repository)
                label = "latest stable release"
            else:
                latest_tag, latest_commit = client.latest_stable_tag(project.repository)
                label = "latest stable tag"

            status = (
                "current"
                if latest_tag == pinned_tag
                and (pinned_commit is None or latest_commit == pinned_commit)
                else "drift"
            )
            results.append(
                _result(
                    project,
                    label,
                    status,
                    f"{pinned_tag} @ {_short_sha(pinned_commit or pinned_tag_commit)}",
                    f"{latest_tag} @ {_short_sha(latest_commit)}",
                    project.policy or "Metadata comparison only",
                )
            )
        except (GitHubError, RegistryError) as exc:
            results.append(_result(project, kind, "error", "registry pin", "unavailable", str(exc)))
    return results


def audit_registry(registry: Registry, client: GitHubClient) -> list[AuditResult]:
    return [result for project in registry.projects for result in audit_project(project, client)]


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def markdown_report(
    registry: Registry,
    results: Iterable[AuditResult],
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    result_list = list(results)
    counts = {
        status: sum(result.status == status for result in result_list)
        for status in ("current", "drift", "error", "unresolved")
    }
    lines = [
        "# MUTX upstream drift report",
        "",
        f"Generated: {generated_at.isoformat(timespec='seconds')}",
        f"SOTA tracking epic: [{registry.sota_epic}]({registry.sota_epic})",
        "",
        (
            "This is a metadata-only audit. It does not clone, import, vendor, "
            "or execute upstream code."
        ),
        "",
        (
            f"Summary: {counts['current']} current, {counts['drift']} drifted, "
            f"{counts['error']} errors, {counts['unresolved']} unresolved."
        ),
        "",
        "| Project | Check | Status | Pinned | Observed | Detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in result_list:
        project = result.project
        if result.repository:
            project = f"[{project}](https://github.com/{result.repository})"
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    project,
                    result.check,
                    result.status.upper(),
                    result.pinned,
                    result.observed,
                    result.detail,
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _write_report(path: str | None, content: str) -> None:
    if path:
        Path(path).write_text(content, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--api-base", default="https://api.github.com")
    parser.add_argument("--markdown-output")
    parser.add_argument("--json-output")
    parser.add_argument(
        "--allow-drift",
        action="store_true",
        help="Return success even when drift is detected (metadata errors still fail)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        registry = load_registry(args.registry)
    except RegistryError as exc:
        print(f"registry error: {exc}", file=sys.stderr)
        return 2

    client = GitHubClient(token=os.environ.get("GITHUB_TOKEN"), api_base=args.api_base)
    results = audit_registry(registry, client)
    report = markdown_report(registry, results)
    print(report, end="")
    _write_report(args.markdown_output, report)
    if args.json_output:
        _write_report(
            args.json_output,
            json.dumps(
                {
                    "schema_version": 1,
                    "sota_epic": registry.sota_epic,
                    "results": [asdict(result) for result in results],
                },
                indent=2,
            )
            + "\n",
        )

    has_error = any(result.status == "error" for result in results)
    has_drift = any(result.status == "drift" for result in results)
    return 1 if has_error or (has_drift and not args.allow_drift) else 0


if __name__ == "__main__":
    raise SystemExit(main())
