#!/usr/bin/env python3
"""Build the MUTX Orchestra Research catalog from an immutable checkout."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "src/api/data/orchestra_research_catalog.json"
DEFAULT_REPO_URL = "https://github.com/Orchestra-Research/AI-Research-SKILLs"
DEFAULT_RELEASE = "v1.7.2"
DEFAULT_COMMIT = "773a52944ba4747a18bd4ae9ade53fff041adcbc"
SKIP_ROOTS = {
    ".git",
    ".github",
    "anthropic_official_docs",
    "demos",
    "dev_data",
    "docs",
    "packages",
}

CATEGORY_NAMES = {
    "0-autoresearch-skill": "Autoresearch",
    "03-fine-tuning": "Fine-Tuning",
    "06-post-training": "Post-Training",
    "07-safety-alignment": "Safety & Alignment",
    "12-inference-serving": "Inference & Serving",
    "13-mlops": "MLOps",
    "15-rag": "RAG",
    "20-ml-paper-writing": "ML Paper Writing",
}


def _git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=source,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _category_name(category_id: str) -> str:
    if category_id in CATEGORY_NAMES:
        return CATEGORY_NAMES[category_id]
    label = re.sub(r"^\d+-", "", category_id).replace("-", " ")
    return label.title()


def _frontmatter(markdown: str, path: Path) -> dict[str, Any]:
    if not markdown.startswith("---\n"):
        raise ValueError(f"{path} has no YAML frontmatter")
    try:
        raw_frontmatter, _body = markdown[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError(f"{path} has unterminated YAML frontmatter") from exc
    payload = yaml.safe_load(raw_frontmatter)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} frontmatter must be an object")
    return payload


def _display_name(markdown: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def discover_skills(source: Path) -> list[dict[str, Any]]:
    """Normalize every upstream SKILL.md into MUTX catalog metadata."""
    skills: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()

    for skill_md in sorted(source.rglob("SKILL.md")):
        relative_file = skill_md.relative_to(source)
        if any(part in SKIP_ROOTS for part in relative_file.parts):
            continue

        skill_dir = skill_md.parent
        upstream_path = skill_dir.relative_to(source)
        markdown = skill_md.read_text(encoding="utf-8")
        metadata = _frontmatter(markdown, skill_md)
        skill_id = skill_dir.name
        canonical_name = str(metadata.get("name") or "").strip()
        description = str(metadata.get("description") or "").strip()
        author = str(metadata.get("author") or "Orchestra Research").strip()
        raw_tags = metadata.get("tags") or []

        if not canonical_name or not description:
            raise ValueError(f"{skill_md} must define name and description")
        if not isinstance(raw_tags, list) or not all(isinstance(tag, str) for tag in raw_tags):
            raise ValueError(f"{skill_md} tags must be a string list")
        if skill_id in seen_ids:
            raise ValueError(f"duplicate skill id: {skill_id}")
        if canonical_name in seen_names:
            raise ValueError(f"duplicate canonical skill name: {canonical_name}")
        seen_ids.add(skill_id)
        seen_names.add(canonical_name)

        category_id = upstream_path.parts[0]
        skills.append(
            {
                "id": skill_id,
                "canonical_name": canonical_name,
                "name": _display_name(markdown, canonical_name),
                "description": description,
                "author": author,
                "category_id": category_id,
                "category_name": _category_name(category_id),
                "upstream_path": upstream_path.as_posix(),
                "tags": raw_tags,
                "has_references": (skill_dir / "references").is_dir(),
                "has_templates": (skill_dir / "templates").is_dir(),
                "has_scripts": (skill_dir / "scripts").is_dir(),
            }
        )

    return skills


def source_metadata(source: Path, *, expected_commit: str, release: str) -> dict[str, Any]:
    commit = _git(source, "rev-parse", "HEAD")
    if commit != expected_commit:
        raise ValueError(f"source checkout is {commit}; expected {expected_commit}")
    commit_date = _git(source, "show", "-s", "--format=%cI", "HEAD")
    return {
        "name": "Orchestra Research AI-Research-SKILLs",
        "repo_url": DEFAULT_REPO_URL,
        "version": release,
        "commit": commit,
        "commit_date": commit_date,
        "commit_subject": _git(source, "show", "-s", "--format=%s", "HEAD"),
        "release_url": f"{DEFAULT_REPO_URL}/releases/tag/{release}",
        "license": "MIT",
        "attribution": (
            "Catalog metadata derived from Orchestra Research upstream repository. "
            "Skill content remains credited to Orchestra Research and upstream project authors."
        ),
    }


def validate_catalog(catalog: dict[str, Any]) -> None:
    skill_ids = {str(item["id"]) for item in catalog["skills"]}
    bundles = {str(item["id"]): item for item in catalog["bundles"]}
    template_ids = {str(item["id"]) for item in catalog["templates"]}
    blueprint_ids = {str(item["id"]) for item in catalog["swarm_blueprints"]}

    for bundle_id, bundle in bundles.items():
        missing = set(bundle.get("skill_ids") or []) - skill_ids
        if missing:
            raise ValueError(f"bundle {bundle_id} references missing skills: {sorted(missing)}")
        if bundle.get("recommended_template_id") not in template_ids:
            raise ValueError(f"bundle {bundle_id} references a missing template")
        if bundle.get("recommended_swarm_blueprint_id") not in blueprint_ids:
            raise ValueError(f"bundle {bundle_id} references a missing swarm blueprint")

    for template in catalog["templates"]:
        missing_bundles = set(template.get("bundle_ids") or []) - bundles.keys()
        missing_skills = set(template.get("default_config", {}).get("skills") or []) - skill_ids
        if missing_bundles or missing_skills:
            raise ValueError(
                f"template {template['id']} has missing references: "
                f"bundles={sorted(missing_bundles)}, skills={sorted(missing_skills)}"
            )

    for blueprint in catalog["swarm_blueprints"]:
        for role in blueprint.get("roles") or []:
            if role.get("bundle_id") not in bundles:
                raise ValueError(f"blueprint {blueprint['id']} references a missing bundle")


def build_catalog(
    existing: dict[str, Any],
    *,
    source: dict[str, Any],
    skills: list[dict[str, Any]],
) -> dict[str, Any]:
    catalog = {
        "source": source,
        "skills": skills,
        "bundles": deepcopy(existing.get("bundles") or []),
        "swarm_blueprints": deepcopy(existing.get("swarm_blueprints") or []),
        "templates": deepcopy(existing.get("templates") or []),
    }
    version_date = str(source["commit_date"])[:10].replace("-", ".")
    pin_message = f"Pinned to Orchestra Research {source['version']} at commit {source['commit']}."
    for template in catalog["templates"]:
        template["version"] = version_date
        template["validation_message"] = pin_message
    validate_catalog(catalog)
    return catalog


def _render(catalog: dict[str, Any]) -> str:
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate the Orchestra Research catalog from a pinned checkout."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    parser.add_argument("--release", default=DEFAULT_RELEASE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    existing = json.loads(args.catalog.read_text(encoding="utf-8"))
    catalog = build_catalog(
        existing,
        source=source_metadata(
            args.source.resolve(), expected_commit=args.commit, release=args.release
        ),
        skills=discover_skills(args.source.resolve()),
    )
    rendered = _render(catalog)
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Orchestra Research catalog is stale")
        return
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
