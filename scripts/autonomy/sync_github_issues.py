from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_REPO = "mutx-dev/mutx-dev"
SECTION_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
PATH_TOKEN = re.compile(r"`([^`]+)`")
REPO_PATH_HINT = re.compile(
    r"^(docs/|src/|app/|components/|lib/|sdk/|cli/|scripts/|tests/|infrastructure/|README\.md|roadmap\.md|whitepaper\.md|AGENTS\.md)"
)

AREA_LABELS = {"api", "web", "auth", "cli-sdk", "runtime", "test", "infra", "ops", "docs"}
UNSAFE_VERIFICATION_CHARS = {";", "&", "|", "`", "$", ">", "<"}


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], text=True, capture_output=True)


def load_open_issues(repo: str, limit: int) -> list[dict[str, Any]]:
    result = run_gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--label",
            "autonomy:ready",
            "--limit",
            str(limit),
            "--json",
            "number,title,body,url,labels",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "gh issue list failed")
    payload = json.loads(result.stdout or "[]")
    return payload if isinstance(payload, list) else []


def extract_label_names(issue: dict[str, Any]) -> list[str]:
    labels = []
    for label in issue.get("labels", []):
        if isinstance(label, dict) and label.get("name"):
            labels.append(str(label["name"]))
    return labels


def split_sections(body: str) -> dict[str, str]:
    text = body or ""
    matches = list(SECTION_PATTERN.finditer(text))
    if not matches:
        return {}
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1).strip().lower()] = text[start:end].strip()
    return sections


def infer_area(labels: list[str], sections: dict[str, str], body: str) -> str:
    for label in labels:
        if label.startswith("area:"):
            raw = label.split(":", 1)[1]
            if raw in AREA_LABELS:
                return f"area:{raw}"
    area_text = sections.get("area", "").strip().lower()
    if area_text in AREA_LABELS:
        return f"area:{area_text}"
    lowered = body.lower()
    if any(token in lowered for token in ["dashboard", "frontend", "ui", "react", "tsx"]):
        return "area:web"
    if any(token in lowered for token in ["api", "backend", "route", "fastapi", "sdk", "auth"]):
        return "area:api"
    return "area:docs"


def infer_priority(labels: list[str]) -> str:
    for label in labels:
        if label.startswith("priority:"):
            raw = label.split(":", 1)[1]
            if raw in {"p0", "p1", "p2", "p3", "p4"}:
                return raw
    if "risk:high" in labels:
        return "p1"
    if "size:xs" in labels:
        return "p2"
    return "p2"


def renderable_body(issue: dict[str, Any]) -> bool:
    body = str(issue.get("body") or "").strip()
    return not body.startswith(("file://", "/tmp/"))


def extract_repo_paths(text: str) -> list[str]:
    found = []
    for token in PATH_TOKEN.findall(text or ""):
        token = token.strip()
        if REPO_PATH_HINT.match(token):
            found.append(token)
    return list(dict.fromkeys(found))


def infer_allowed_paths(issue: dict[str, Any], sections: dict[str, str]) -> list[str]:
    body = str(issue.get("body") or "")
    paths = []
    paths.extend(extract_repo_paths(sections.get("likely files or surfaces", "")))
    paths.extend(extract_repo_paths(sections.get("repo context", "")))
    paths.extend(extract_repo_paths(body))
    return list(dict.fromkeys(paths))[:6]


def infer_verification(sections: dict[str, str], area: str) -> list[str]:
    verification = []
    for line in sections.get("acceptance criteria", "").splitlines():
        line = line.strip().lstrip("-*").strip()
        if not line:
            continue
        if any(char in line for char in UNSAFE_VERIFICATION_CHARS):
            continue
        if any(
            cmd in line for cmd in ["pytest", "npm run", "git diff --check", "python3 ", "make "]
        ):
            verification.append(line)
    if verification:
        return verification[:4]
    if area == "area:web":
        return ["npm run lint"]
    if area == "area:docs":
        return ["git diff --check -- README.md docs"]
    return ["pytest tests/api -q"]


def infer_description(issue: dict[str, Any], sections: dict[str, str]) -> str:
    for key in ["task", "summary", "problem statement", "description"]:
        value = sections.get(key, "").strip()
        if value:
            return value[:1200]
    return str(issue.get("body") or "").strip()[:1200]


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any] | None:
    if not renderable_body(issue):
        return None
    labels = extract_label_names(issue)
    body = str(issue.get("body") or "")
    sections = split_sections(body)
    area = infer_area(labels, sections, body)
    return {
        "id": f"gh-issue-{issue['number']}",
        "issue": issue["number"],
        "title": str(issue.get("title") or f"Issue #{issue['number']}").strip(),
        "description": infer_description(issue, sections),
        "area": area,
        "priority": infer_priority(labels),
        "status": "queued",
        "source": "github:issue",
        "labels": labels,
        "allowed_paths": infer_allowed_paths(issue, sections),
        "verification": infer_verification(sections, area),
        "constraints": [
            "issue-driven",
            "keep change bounded",
            "must satisfy acceptance criteria if present",
        ],
        "metadata": {"issue_url": issue.get("url")},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize autonomy-ready GitHub issues into queue tasks"
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    issues = load_open_issues(args.repo, args.limit)
    tasks = []
    for issue in issues:
        normalized = normalize_issue(issue)
        if normalized:
            tasks.append(normalized)
    Path(args.output).write_text(
        json.dumps(tasks, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"count": len(tasks), "output": args.output}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
