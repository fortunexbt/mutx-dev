from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from queue_state import load_queue

ROOT = Path(__file__).resolve().parents[2]
PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "p4": 4}
STATUS_SCORE = {
    "MISLEADING": 45,
    "STUB": 34,
    "PLACEHOLDER": 30,
    "PARTIAL": 20,
    "UNCONFIRMED": 18,
    "SHIPPED": 0,
}
SOURCE_SCORE = {
    "fleet:claim-matrix": 35,
    "fleet:route-claim-scan": 40,
    "fleet:todo-scan": 24,
    "fleet:ux-scan": 26,
    "fleet:docs-language-scan": 18,
}
ROLE_HINTS = {
    "fleet:claim-matrix": ["cio", "research", "cto"],
    "fleet:route-claim-scan": ["research", "cio", "cto"],
    "fleet:docs-language-scan": ["research", "cto", "cio"],
    "fleet:ux-scan": ["ux", "frontend"],
}
AREA_DEFAULT_ROLE = {
    "area:api": ["backend"],
    "area:auth": ["backend"],
    "area:runtime": ["backend"],
    "area:ops": ["backend"],
    "area:infra": ["backend"],
    "area:web": ["frontend", "ux"],
    "area:docs": ["research", "cio", "cto"],
}
EXECUTION_LANE_BY_AREA = {
    "area:docs": "main",
    "area:api": "codex",
    "area:auth": "codex",
    "area:runtime": "codex",
    "area:ops": "codex",
    "area:infra": "codex",
    "area:web": "opencode",
}
TEXT_FILE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".md"}
ROUTE_PATTERN = re.compile(r"/v1(?:/[a-z0-9][a-z0-9_\-/]*)", re.IGNORECASE)
LANGUAGE_DRIFT_PATTERN = re.compile(
    r"\b(?:TODO|TBD|coming soon|planned|placeholder|skeletal|stub)\b",
    re.IGNORECASE,
)
RISK_PATTERN = re.compile(
    r"\b(auth|security|deploy|runtime|infra|observability|billing)\b", re.IGNORECASE
)


@dataclass(slots=True)
class RoleProfile:
    id: str
    lane: str
    purpose: str
    scan_targets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskCandidate:
    id: str
    title: str
    description: str
    area: str
    source: str
    allowed_paths: list[str]
    verification: list[str]
    constraints: list[str]
    evidence_paths: list[str] = field(default_factory=list)
    evidence_fingerprint: str = ""
    evidence: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    priority: str = "p3"
    score: int = 0
    owner_role: str = "backend"
    role_lane: str = "codex"
    lane: str = "codex"
    runner: str = "codex"
    scheduling_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_paths"] = sorted(dict.fromkeys(self.evidence_paths))
        payload["allowed_paths"] = sorted(dict.fromkeys(self.allowed_paths))
        payload["labels"] = sorted(dict.fromkeys(self.labels))
        payload["verification"] = list(dict.fromkeys(self.verification))
        payload["constraints"] = list(dict.fromkeys(self.constraints))
        payload["evidence"] = self.evidence[:4]
        return payload


def load_fleet(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_roles(fleet: dict[str, Any]) -> list[RoleProfile]:
    roles: list[RoleProfile] = []
    for raw in fleet.get("roles", []):
        roles.append(
            RoleProfile(
                id=str(raw.get("id") or "unknown"),
                lane=str(raw.get("lane") or "main"),
                purpose=str(raw.get("purpose") or ""),
                scan_targets=[
                    str(item) for item in raw.get("scan_targets", []) if str(item).strip()
                ],
            )
        )
    return roles


ACTIVE_QUEUE_STATUSES = {"queued", "running", "parked"}


def existing_ids(queue_path: str | Path) -> set[str]:
    queue = load_queue(queue_path)
    seen: set[str] = set()
    for item in queue.get("items", []):
        status = str(item.get("status") or "queued")
        if status not in ACTIVE_QUEUE_STATUSES:
            continue
        seen.add(str(item.get("id")))
    return seen


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def build_evidence_fingerprint(base: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for rel in sorted(dict.fromkeys(paths)):
        candidate = base / rel
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        if not candidate.exists() or not candidate.is_file():
            digest.update(b"MISSING\0")
            continue
        digest.update(candidate.read_text(encoding="utf-8", errors="replace").encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _slug(value: str, *, limit: int = 56) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:limit]


def _trim(value: str, *, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", value.strip())
    return compact[:limit]


def _priority_for_score(score: int) -> str:
    if score >= 90:
        return "p0"
    if score >= 72:
        return "p1"
    if score >= 52:
        return "p2"
    if score >= 32:
        return "p3"
    return "p4"


def _execution_lane(area: str, role_lane: str) -> str:
    if role_lane in {"codex", "opencode"}:
        return role_lane
    return EXECUTION_LANE_BY_AREA.get(area, "codex")


def _candidate_role_names(candidate: TaskCandidate) -> list[str]:
    names: list[str] = []
    names.extend(ROLE_HINTS.get(candidate.source, []))
    names.extend(AREA_DEFAULT_ROLE.get(candidate.area, []))
    return names


def _match_score(target: str, candidate_paths: list[str]) -> int:
    target_norm = target.strip("/")
    if not target_norm:
        return 0
    score = 0
    for raw_path in candidate_paths:
        path = raw_path.strip("/")
        if not path:
            continue
        if path == target_norm:
            score += 7
        elif path.startswith(f"{target_norm}/"):
            score += 5
        elif target_norm.startswith(f"{path}/"):
            score += 2
        elif Path(path).name == Path(target_norm).name:
            score += 1
    return score


def assign_role(candidate: TaskCandidate, roles: list[RoleProfile]) -> tuple[str, str, str]:
    candidate_paths = list(dict.fromkeys(candidate.allowed_paths + candidate.evidence_paths))
    hints = _candidate_role_names(candidate)
    best_score = -1
    chosen: RoleProfile | None = None
    for role in roles:
        score = 0
        if role.id in hints:
            score += max(8 - hints.index(role.id), 1)
        for target in role.scan_targets:
            score += _match_score(target, candidate_paths)
        if candidate.area == "area:docs" and role.id in {"research", "cio", "cto"}:
            score += 2
        if candidate.area == "area:web" and role.id in {"frontend", "ux"}:
            score += 2
        if candidate.area != "area:web" and role.id == "backend":
            score += 2
        if score > best_score:
            best_score = score
            chosen = role
    if chosen is None:
        return ("backend", "codex", "default backend fallback")
    reason_bits = []
    if chosen.id in hints:
        reason_bits.append(f"source/area matched {chosen.id}")
    matched_targets = [
        target for target in chosen.scan_targets if _match_score(target, candidate_paths) > 0
    ]
    if matched_targets:
        reason_bits.append(f"scan_targets={','.join(matched_targets[:3])}")
    if not reason_bits:
        reason_bits.append("best available role fit")
    return (chosen.id, chosen.lane, "; ".join(reason_bits))


def finalize_candidate(
    base: Path, candidate: TaskCandidate, roles: list[RoleProfile]
) -> TaskCandidate:
    owner_role, role_lane, reason = assign_role(candidate, roles)
    candidate.owner_role = owner_role
    candidate.role_lane = role_lane
    candidate.lane = _execution_lane(candidate.area, role_lane)
    if candidate.lane == "main":
        candidate.runner = "main"
    elif candidate.lane == "opencode":
        candidate.runner = "opencode"
    else:
        candidate.runner = "codex"
    score = SOURCE_SCORE.get(candidate.source, 12)
    score += 6 if len(candidate.allowed_paths) <= 2 else 0
    score += 5 if len(candidate.constraints) <= 3 else 0
    score += (
        6 if any(path.endswith("docs/whitepaper.md") for path in candidate.evidence_paths) else 0
    )
    score += 6 if any(path.endswith("README.md") for path in candidate.evidence_paths) else 0
    score += 7 if any(RISK_PATTERN.search(line) for line in candidate.evidence) else 0
    score += 4 if candidate.area == "area:docs" else 0
    score += 4 if candidate.area == "area:web" and candidate.owner_role == "ux" else 0
    score += 3 if candidate.lane == "main" else 0
    for label in candidate.labels:
        if label.startswith("status:"):
            score += STATUS_SCORE.get(label.split(":", 1)[1].upper(), 0)
        if label == "risk:high":
            score += 10
        if label == "size:xs":
            score += 6
        if label == "size:s":
            score += 4
    candidate.score = score
    candidate.priority = _priority_for_score(score)
    candidate.labels.extend(
        [
            candidate.area,
            f"role:{candidate.owner_role}",
            f"lane:{candidate.lane}",
            f"role-lane:{candidate.role_lane}",
            f"priority:{candidate.priority}",
        ]
    )
    if candidate.area == "area:web" and len(candidate.allowed_paths) <= 2:
        candidate.labels.extend(["risk:low", "size:s", "autonomy:safe"])
    if candidate.area == "area:docs" and len(candidate.allowed_paths) <= 4:
        candidate.labels.extend(["risk:low", "size:s", "autonomy:safe"])
    candidate.evidence_fingerprint = build_evidence_fingerprint(
        base, candidate.evidence_paths or candidate.allowed_paths
    )
    candidate.scheduling_reason = reason
    return candidate


def _route_doc_paths_for_route(route: str) -> list[str]:
    last = route.strip("/").split("/")[-1]
    return [
        "docs/api/reference.md",
        f"docs/api/{last}.md",
        "docs/surfaces.md",
        "docs/whitepaper.md",
        "README.md",
    ]


def claim_matrix_tasks(base: Path, roles: list[RoleProfile]) -> list[TaskCandidate]:
    path = base / "docs" / "claim-to-reality-gap-matrix.md"
    if not path.exists():
        return []
    tasks: list[TaskCandidate] = []
    for line in read_lines(path):
        if "|" not in line or any(marker in line for marker in ["|-------", "| Claim"]):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) < 4:
            continue
        claim, source_ref, reality, status = cells[:4]
        if status not in STATUS_SCORE or status == "SHIPPED":
            continue
        title_root = _trim(claim, limit=76)
        slug = _slug(title_root)
        evidence_paths = ["docs/claim-to-reality-gap-matrix.md"]
        allowed_paths = ["docs/claim-to-reality-gap-matrix.md"]
        if (
            "whitepaper" in source_ref.lower()
            or "whitepaper" in claim.lower()
            or "whitepaper" in reality.lower()
        ):
            evidence_paths.append("docs/whitepaper.md")
            allowed_paths.append("docs/whitepaper.md")
        if "roadmap" in source_ref.lower() or "roadmap" in reality.lower():
            evidence_paths.append("docs/roadmap.md")
            allowed_paths.append("docs/roadmap.md")
        if "project-status" in source_ref.lower() or "project-status" in reality.lower():
            evidence_paths.append("docs/project-status.md")
            allowed_paths.append("docs/project-status.md")
        if "surfaces" in source_ref.lower() or "surfaces" in reality.lower():
            evidence_paths.append("docs/surfaces.md")
            allowed_paths.append("docs/surfaces.md")
        candidate = TaskCandidate(
            id=f"fleet-docs-{slug}",
            title=f"docs: tighten drift around {title_root}",
            description=(
                f"Resolve the {status.lower()} claim in docs/claim-to-reality-gap-matrix.md for '{title_root}'. "
                f"Compare the source reference ({source_ref}) against current repo reality and make the smallest truthful docs update."
            ),
            area="area:docs",
            source="fleet:claim-matrix",
            allowed_paths=allowed_paths[:3],
            verification=[
                "python3 -m compileall scripts/autonomy",
                "git diff --check -- docs/claim-to-reality-gap-matrix.md",
            ],
            constraints=[
                "max_changed_files=3",
                "docs-and-truth only",
                "keep claim bounded to cited files",
            ],
            evidence_paths=evidence_paths,
            evidence=[claim, reality, f"status={status}"],
            labels=[f"status:{status.lower()}", "size:s"],
        )
        tasks.append(finalize_candidate(base, candidate, roles))
    return tasks


def repo_todo_tasks(base: Path, roles: list[RoleProfile]) -> list[TaskCandidate]:
    patterns = ("TODO", "FIXME", "HACK", "XXX")
    targets = [
        base / "src",
        base / "app",
        base / "components",
        base / "sdk",
        base / "cli",
        base / "scripts",
        base / "docs",
    ]
    tasks: list[TaskCandidate] = []
    for target in targets:
        if not target.exists():
            continue
        for path in target.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_FILE_SUFFIXES:
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            for lineno, line in enumerate(lines, start=1):
                upper = line.upper()
                if not any(pattern in upper for pattern in patterns):
                    continue
                rel = path.relative_to(base).as_posix()
                snippet = _trim(line, limit=100)
                area = (
                    "area:web"
                    if rel.startswith(("app/", "components/", "lib/"))
                    else "area:docs"
                    if rel.startswith("docs/")
                    else "area:api"
                )
                risk_label = "risk:high" if RISK_PATTERN.search(snippet) else "risk:low"
                size_label = "size:xs" if len(snippet) < 72 else "size:s"
                candidate = TaskCandidate(
                    id=f"fleet-todo-{_slug(f'{rel}-{lineno}')}",
                    title=f"cleanup: resolve {snippet.split(':', 1)[0].lower()} in {rel}:{lineno}",
                    description=f"Address the inline note at {rel}:{lineno}: {snippet}",
                    area=area,
                    source="fleet:todo-scan",
                    allowed_paths=[rel],
                    verification=[f"git diff --check -- {rel}"],
                    constraints=["max_changed_files=2", "small bounded cleanup"],
                    evidence_paths=[rel],
                    evidence=[f"{rel}:{lineno}: {snippet}"],
                    labels=[size_label, risk_label],
                )
                tasks.append(finalize_candidate(base, candidate, roles))
                break
    return tasks


def ux_accessibility_tasks(base: Path, roles: list[RoleProfile]) -> list[TaskCandidate]:
    targets = [
        base / "app" / "dashboard",
        base / "components" / "dashboard",
        base / "components" / "site",
    ]
    tasks: list[TaskCandidate] = []
    for target in targets:
        if not target.exists():
            continue
        for path in target.rglob("*.tsx"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "placeholder=" not in text or "aria-label=" in text:
                continue
            rel = path.relative_to(base).as_posix()
            candidate = TaskCandidate(
                id=f"fleet-ux-{_slug(rel)}",
                title=f"ux: label placeholder-only inputs in {rel}",
                description=(
                    f"Audit {rel} for placeholder-only inputs without explicit labels or aria-labels and "
                    "make the smallest safe accessibility improvement."
                ),
                area="area:web",
                source="fleet:ux-scan",
                allowed_paths=[rel],
                verification=[f"git diff --check -- {rel}"],
                constraints=["max_changed_files=2", "frontend-only change"],
                evidence_paths=[rel],
                evidence=[f"placeholder-only inputs detected in {rel}"],
                labels=["size:s", "risk:low"],
            )
            tasks.append(finalize_candidate(base, candidate, roles))
    return tasks


def load_openapi_routes(base: Path) -> set[str]:
    path = base / "docs" / "api" / "openapi.json"
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    paths = payload.get("paths", {})
    if not isinstance(paths, dict):
        return set()
    return {str(key) for key in paths.keys()}


def route_claim_tasks(base: Path, roles: list[RoleProfile]) -> list[TaskCandidate]:
    openapi_routes = load_openapi_routes(base)
    if not openapi_routes:
        return []
    doc_candidates = [
        base / "docs/whitepaper.md",
        base / "README.md",
        base / "docs" / "surfaces.md",
    ]
    tasks: list[TaskCandidate] = []
    seen: set[tuple[str, str]] = set()
    for doc in doc_candidates:
        if not doc.exists():
            continue
        rel = doc.relative_to(base).as_posix()
        for lineno, line in enumerate(read_lines(doc), start=1):
            routes = {match.group(0) for match in ROUTE_PATTERN.finditer(line)}
            for route in sorted(routes):
                if route in openapi_routes:
                    continue
                key = (rel, route)
                if key in seen:
                    continue
                seen.add(key)
                allowed_paths = [rel, "docs/api/reference.md"]
                allowed_paths.extend(
                    path for path in _route_doc_paths_for_route(route) if path != rel
                )
                candidate = TaskCandidate(
                    id=f"fleet-route-{_slug(f'{rel}-{route}')}",
                    title=f"docs: reconcile undocumented route claim {route}",
                    description=(
                        f"{rel}:{lineno} claims the route {route}, but it is absent from docs/api/openapi.json. "
                        "Tighten the claim or document the real implementation status without expanding scope."
                    ),
                    area="area:docs",
                    source="fleet:route-claim-scan",
                    allowed_paths=allowed_paths[:3],
                    verification=[
                        "git diff --check -- docs/whitepaper.md docs/surfaces.md README.md docs/api/reference.md"
                    ],
                    constraints=[
                        "max_changed_files=3",
                        "docs-and-truth only",
                        "do not invent missing endpoints",
                    ],
                    evidence_paths=[rel, "docs/api/openapi.json"],
                    evidence=[f"{rel}:{lineno}: {line.strip()}", f"missing route: {route}"],
                    labels=[
                        "status:misleading",
                        "size:s" if rel == "docs/whitepaper.md" else "size:xs",
                    ],
                )
                tasks.append(finalize_candidate(base, candidate, roles))
    return tasks


def docs_language_tasks(base: Path, roles: list[RoleProfile]) -> list[TaskCandidate]:
    targets = [
        base / "docs/whitepaper.md",
        base / "README.md",
        base / "docs" / "project-status.md",
        base / "docs" / "docs/roadmap.md",
    ]
    tasks: list[TaskCandidate] = []
    for path in targets:
        if not path.exists():
            continue
        rel = path.relative_to(base).as_posix()
        for lineno, line in enumerate(read_lines(path), start=1):
            if not LANGUAGE_DRIFT_PATTERN.search(line):
                continue
            snippet = _trim(line, limit=110)
            candidate = TaskCandidate(
                id=f"fleet-language-{_slug(f'{rel}-{lineno}')}",
                title=f"docs: tighten speculative language in {rel}:{lineno}",
                description=f"Review speculative or drift-prone language in {rel}:{lineno}: {snippet}",
                area="area:docs",
                source="fleet:docs-language-scan",
                allowed_paths=[rel],
                verification=[f"git diff --check -- {rel}"],
                constraints=["max_changed_files=1", "docs wording only"],
                evidence_paths=[rel],
                evidence=[f"{rel}:{lineno}: {snippet}"],
                labels=["size:xs", "risk:low"],
            )
            tasks.append(finalize_candidate(base, candidate, roles))
            break
    return tasks


def source_enabled(policy: dict[str, Any], source: str) -> bool:
    disabled = policy.get("disabled_sources", [])
    if not isinstance(disabled, list):
        return True
    return source not in {str(item) for item in disabled}


def collect_candidates(
    base: Path, roles: list[RoleProfile], fleet: dict[str, Any]
) -> list[TaskCandidate]:
    policy = fleet.get("scanner_policies", {})
    tasks: list[TaskCandidate] = []
    if source_enabled(policy, "fleet:claim-matrix"):
        tasks.extend(claim_matrix_tasks(base, roles))
    if source_enabled(policy, "fleet:route-claim-scan"):
        tasks.extend(route_claim_tasks(base, roles))
    if source_enabled(policy, "fleet:todo-scan"):
        tasks.extend(repo_todo_tasks(base, roles))
    if source_enabled(policy, "fleet:ux-scan"):
        tasks.extend(ux_accessibility_tasks(base, roles))
    if source_enabled(policy, "fleet:docs-language-scan"):
        tasks.extend(docs_language_tasks(base, roles))
    return tasks


def _lane_caps(policy: dict[str, Any]) -> dict[str, int]:
    raw = policy.get("max_tasks_per_lane_per_cycle", {})
    if isinstance(raw, dict):
        return {str(key): int(value) for key, value in raw.items()}
    return {}


def schedule_tasks(tasks: list[TaskCandidate], fleet: dict[str, Any]) -> list[TaskCandidate]:
    policy = fleet.get("scanner_policies", {})
    limit = int(policy.get("max_new_tasks_per_cycle", 12))
    per_role_cap = int(policy.get("max_tasks_per_role_per_cycle", limit))
    lane_caps = _lane_caps(policy)
    min_score = int(policy.get("min_score", 0))
    scheduled: list[TaskCandidate] = []
    role_count: dict[str, int] = {}
    lane_count: dict[str, int] = {}
    for candidate in sorted(
        tasks,
        key=lambda item: (
            PRIORITY_ORDER.get(item.priority, 99),
            -item.score,
            item.owner_role,
            item.id,
        ),
    ):
        if candidate.score < min_score:
            continue
        if len(scheduled) >= limit:
            break
        if role_count.get(candidate.owner_role, 0) >= per_role_cap:
            continue
        if lane_caps and lane_count.get(candidate.lane, 0) >= lane_caps.get(candidate.lane, limit):
            continue
        scheduled.append(candidate)
        role_count[candidate.owner_role] = role_count.get(candidate.owner_role, 0) + 1
        lane_count[candidate.lane] = lane_count.get(candidate.lane, 0) + 1
    return scheduled


def generate_tasks(base: Path, fleet: dict[str, Any]) -> list[dict[str, Any]]:
    roles = load_roles(fleet)
    candidates = collect_candidates(base, roles, fleet)
    scheduled = schedule_tasks(candidates, fleet)
    return [task.to_dict() for task in scheduled]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate bounded fleet tasks from repo/docs/whitepaper signals"
    )
    parser.add_argument("--fleet", default=str(ROOT / ".autonomy" / "fleet.json"))
    parser.add_argument(
        "--queue", default=str(ROOT / "mutx-engineering-agents" / "dispatch" / "action-queue.json")
    )
    parser.add_argument("--output", default=str(ROOT / ".autonomy" / "generated-tasks.json"))
    parser.add_argument("--repo-root", default=str(ROOT))
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    fleet = load_fleet(args.fleet)
    seen = existing_ids(args.queue)
    tasks = [task for task in generate_tasks(repo_root, fleet) if str(task.get("id")) not in seen]
    Path(args.output).write_text(
        json.dumps(tasks, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"count": len(tasks), "output": args.output}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
