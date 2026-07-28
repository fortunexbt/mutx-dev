from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


def _load_generate_openapi_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_openapi.py"
    spec = importlib.util.spec_from_file_location("generate_openapi", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_openapi_document_flattens_single_ref_allof() -> None:
    module = _load_generate_openapi_module()

    document = {
        "components": {
            "schemas": {
                "AgentConfig": {
                    "properties": {
                        "type": {
                            "allOf": [{"$ref": "#/components/schemas/AgentType"}],
                            "default": "openai",
                        }
                    }
                }
            }
        }
    }

    assert module.normalize_openapi_document(document) == {
        "components": {
            "schemas": {
                "AgentConfig": {
                    "properties": {
                        "type": {
                            "$ref": "#/components/schemas/AgentType",
                            "default": "openai",
                        }
                    }
                }
            }
        }
    }


def test_normalize_openapi_document_keeps_multi_entry_allof() -> None:
    module = _load_generate_openapi_module()

    document = {
        "properties": {
            "value": {
                "allOf": [
                    {"$ref": "#/components/schemas/BaseValue"},
                    {"type": "string"},
                ]
            }
        }
    }

    assert module.normalize_openapi_document(document) == document


def test_normalize_openapi_document_preserves_open_object_contracts() -> None:
    module = _load_generate_openapi_module()
    document = {"type": "object", "additionalProperties": True}

    assert module.normalize_openapi_document(document) == document


def test_main_preserves_existing_snapshot_when_generation_fails(monkeypatch, tmp_path) -> None:
    module = _load_generate_openapi_module()
    openapi_path = tmp_path / "docs" / "api" / "openapi.json"
    openapi_path.parent.mkdir(parents=True)
    openapi_path.write_text('{"openapi":"3.1.0"}')

    def fail_generation() -> dict[str, object]:
        raise RuntimeError("missing dependency")

    monkeypatch.setattr(module, "build_openapi_document", fail_generation)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="missing dependency"):
        module.main()

    assert openapi_path.read_text() == '{"openapi":"3.1.0"}'
    assert not os.path.exists(f"{openapi_path}.tmp")
