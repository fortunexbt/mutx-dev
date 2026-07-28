from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_orchestra_research_catalog import (
    DEFAULT_COMMIT,
    DEFAULT_RELEASE,
    build_catalog,
    discover_skills,
    validate_catalog,
)
from scripts.sync_orchestra_research_skills import DEFAULT_COMMIT as SYNC_COMMIT
from scripts.sync_orchestra_research_skills import DEFAULT_RELEASE as SYNC_RELEASE


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "src/api/data/orchestra_research_catalog.json"


def test_discover_skills_normalizes_upstream_frontmatter(tmp_path: Path) -> None:
    skill_dir = tmp_path / "22-agent-native-research-artifact" / "compiler"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: ara-compiler
description: Compile research into an agent-native artifact.
author: Orchestra Research
tags: [ARA, Provenance]
---

# Universal ARA Compiler
""",
        encoding="utf-8",
    )

    assert discover_skills(tmp_path) == [
        {
            "id": "compiler",
            "canonical_name": "ara-compiler",
            "name": "Universal ARA Compiler",
            "description": "Compile research into an agent-native artifact.",
            "author": "Orchestra Research",
            "category_id": "22-agent-native-research-artifact",
            "category_name": "Agent Native Research Artifact",
            "upstream_path": "22-agent-native-research-artifact/compiler",
            "tags": ["ARA", "Provenance"],
            "has_references": True,
            "has_templates": False,
            "has_scripts": False,
        }
    ]


def test_build_catalog_preserves_curated_layers_and_updates_template_pin() -> None:
    existing = {
        "bundles": [
            {
                "id": "foundation",
                "skill_ids": ["compiler"],
                "recommended_template_id": "template",
                "recommended_swarm_blueprint_id": "blueprint",
            }
        ],
        "swarm_blueprints": [{"id": "blueprint", "roles": [{"bundle_id": "foundation"}]}],
        "templates": [
            {
                "id": "template",
                "bundle_ids": ["foundation"],
                "default_config": {"skills": ["compiler"]},
                "version": "old",
                "validation_message": "old",
            }
        ],
    }
    source = {
        "version": DEFAULT_RELEASE,
        "commit": DEFAULT_COMMIT,
        "commit_date": "2026-06-15T21:36:40-04:00",
    }
    skills = [{"id": "compiler"}]

    catalog = build_catalog(existing, source=source, skills=skills)

    assert catalog["templates"][0]["version"] == "2026.06.15"
    assert DEFAULT_RELEASE in catalog["templates"][0]["validation_message"]
    assert DEFAULT_COMMIT in catalog["templates"][0]["validation_message"]
    assert catalog["bundles"] == existing["bundles"]


def test_validate_catalog_rejects_dangling_skill_reference() -> None:
    with pytest.raises(ValueError, match="missing skills"):
        validate_catalog(
            {
                "skills": [],
                "bundles": [
                    {
                        "id": "broken",
                        "skill_ids": ["missing"],
                        "recommended_template_id": "template",
                        "recommended_swarm_blueprint_id": "blueprint",
                    }
                ],
                "templates": [{"id": "template", "bundle_ids": [], "default_config": {}}],
                "swarm_blueprints": [{"id": "blueprint", "roles": []}],
            }
        )


def test_checked_in_catalog_matches_v172_contract() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    source = catalog["source"]
    skill_ids = {skill["id"] for skill in catalog["skills"]}

    assert source["version"] == DEFAULT_RELEASE == SYNC_RELEASE
    assert source["commit"] == DEFAULT_COMMIT == SYNC_COMMIT
    assert len(catalog["skills"]) == 98
    assert {"compiler", "research-manager", "rigor-reviewer"} <= skill_ids
    validate_catalog(catalog)
