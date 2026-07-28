from __future__ import annotations

from copy import deepcopy
import importlib.util
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, Security
from fastapi.security import APIKeyHeader
from pydantic import computed_field
import pytest

from src.api.models.numeric import DegradedNumericResponseModel

from scripts.generate_openapi import (
    build_openapi_document,
    get_application_openapi,
    normalize_openapi_document,
)


BEARER_REQUIRED = [{"BearerAuth": []}]
BEARER_OPTIONAL = [{}, {"BearerAuth": []}]
BEARER_OR_API_KEY_REQUIRED = [{"BearerAuth": []}, {"ApiKeyAuth": []}]
BEARER_OR_API_KEY_OPTIONAL = [{}, {"BearerAuth": []}, {"ApiKeyAuth": []}]
OPENAPI_METHODS = {"delete", "get", "head", "options", "patch", "post", "put"}


def _load_generate_openapi_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_openapi.py"
    spec = importlib.util.spec_from_file_location("generate_openapi", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _without_security_metadata(document: dict[str, Any]) -> dict[str, Any]:
    comparable = deepcopy(document)
    comparable.pop("security", None)

    components = comparable.get("components", {})
    components.pop("securitySchemes", None)

    for path_item in comparable.get("paths", {}).values():
        for method, operation in path_item.items():
            if method in OPENAPI_METHODS:
                operation.pop("security", None)
                parameters = operation.get("parameters", [])
                filtered = [
                    parameter
                    for parameter in parameters
                    if not (
                        parameter.get("in") == "header"
                        and str(parameter.get("name", "")).lower() in {"authorization", "x-api-key"}
                    )
                ]
                if filtered:
                    operation["parameters"] = filtered
                else:
                    operation.pop("parameters", None)

    return normalize_openapi_document(comparable)


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


def test_generation_keeps_fields_for_wrapped_response_serializers() -> None:
    test_app = FastAPI()

    class WrappedResponse(DegradedNumericResponseModel):
        value: float

        @computed_field
        @property
        def doubled(self) -> float:
            return self.value * 2

    @test_app.get("/wrapped", response_model=WrappedResponse)
    async def wrapped_operation() -> WrappedResponse:
        return WrappedResponse(value=1.0)

    native_schemas = test_app.openapi()["components"]["schemas"]
    native_name = next(name for name in native_schemas if name.startswith("WrappedResponse"))
    assert native_schemas[native_name] == {}

    document = build_openapi_document(test_app)

    wrapped_schema = document["components"]["schemas"]["WrappedResponse"]
    assert wrapped_schema["properties"] == {
        "degraded": {"type": "boolean", "title": "Degraded", "default": False},
        "value": {"type": "number", "title": "Value"},
        "doubled": {"type": "number", "title": "Doubled", "readOnly": True},
    }
    assert wrapped_schema["required"] == ["value", "doubled"]
    assert "WrappedResponse-Input" not in document["components"]["schemas"]
    assert "WrappedResponse-Output" not in document["components"]["schemas"]


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


def test_security_is_derived_from_nested_route_dependencies() -> None:
    test_app = FastAPI()

    async def required_principal(
        authorization: str | None = Header(default=None),
    ) -> str:
        return authorization or "anonymous"

    async def optional_principal(
        authorization: str | None = Header(default=None),
    ) -> str | None:
        return authorization

    async def role_guard(principal: str = Depends(required_principal)) -> str:
        return principal

    @test_app.get("/public")
    async def public_operation() -> dict[str, bool]:
        return {"ok": True}

    @test_app.get("/protected")
    async def protected_operation(principal: str = Depends(required_principal)) -> str:
        return principal

    @test_app.get("/role-gated", dependencies=[Depends(role_guard)])
    async def role_gated_operation() -> dict[str, bool]:
        return {"ok": True}

    @test_app.get("/optional")
    async def optional_operation(
        principal: str | None = Depends(optional_principal),
    ) -> str | None:
        return principal

    document = build_openapi_document(test_app)

    assert "security" not in document
    assert document["paths"]["/public"]["get"]["security"] == []
    assert document["paths"]["/protected"]["get"]["security"] == BEARER_REQUIRED
    assert document["paths"]["/role-gated"]["get"]["security"] == BEARER_REQUIRED
    assert document["paths"]["/optional"]["get"]["security"] == BEARER_OPTIONAL
    assert "parameters" not in document["paths"]["/protected"]["get"]


def test_alternative_auth_headers_become_security_schemes() -> None:
    test_app = FastAPI()

    async def bearer_or_api_key(
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> str:
        return authorization or x_api_key or "anonymous"

    @test_app.get("/protected")
    async def protected_operation(
        principal: str = Depends(bearer_or_api_key),
    ) -> str:
        return principal

    document = build_openapi_document(test_app)
    operation = document["paths"]["/protected"]["get"]

    assert operation["security"] == BEARER_OR_API_KEY_REQUIRED
    assert "parameters" not in operation
    assert document["components"]["securitySchemes"]["ApiKeyAuth"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Managed MUTX API key sent in the X-API-Key header.",
    }


def test_existing_security_schemes_and_operation_overrides_are_preserved() -> None:
    test_app = FastAPI()
    existing_key = APIKeyHeader(name="X-Existing-Key", scheme_name="ExistingKey")

    async def required_principal(
        authorization: str | None = Header(default=None),
    ) -> str:
        return authorization or "anonymous"

    @test_app.get("/native-security")
    async def native_security_operation(
        credential: str = Security(existing_key),
    ) -> str:
        return credential

    @test_app.get(
        "/route-override",
        dependencies=[Depends(required_principal)],
        openapi_extra={"security": []},
    )
    async def route_override_operation() -> dict[str, bool]:
        return {"ok": True}

    document = build_openapi_document(test_app)

    schemes = document["components"]["securitySchemes"]
    assert schemes["ExistingKey"] == {"type": "apiKey", "in": "header", "name": "X-Existing-Key"}
    assert schemes["BearerAuth"]["scheme"] == "bearer"
    assert document["paths"]["/native-security"]["get"]["security"] == [{"ExistingKey": []}]
    assert document["paths"]["/route-override"]["get"]["security"] == []


def test_live_app_has_truthful_representative_operation_security() -> None:
    document = build_openapi_document()

    assert "security" not in document
    assert document["paths"]["/health"]["get"]["security"] == []
    assert document["paths"]["/v1/auth/login"]["post"]["security"] == []
    assert document["paths"]["/v1/leads/contacts"]["post"]["security"] == []
    assert document["paths"]["/v1/agents"]["post"]["security"] == BEARER_OR_API_KEY_REQUIRED
    assert document["paths"]["/v1/audit/events"]["get"]["security"] == BEARER_OR_API_KEY_REQUIRED
    assert (
        document["paths"]["/v1/analytics/summary"]["get"]["security"] == BEARER_OR_API_KEY_REQUIRED
    )
    assert document["paths"]["/v1/agents/heartbeat"]["post"]["security"] == BEARER_REQUIRED
    assert (
        document["paths"]["/v1/ingest/agent-status"]["post"]["security"]
        == BEARER_OR_API_KEY_REQUIRED
    )
    assert document["paths"]["/v1/webhooks/"]["post"]["security"] == BEARER_OR_API_KEY_REQUIRED
    assert document["paths"]["/v1/auth/logout"]["post"]["security"] == BEARER_OR_API_KEY_OPTIONAL
    assert document["paths"]["/v1/pico/chat"]["post"]["security"] == BEARER_OR_API_KEY_OPTIONAL
    assert "parameters" not in document["paths"]["/v1/ingest/agent-status"]["post"]

    for path_item in document["paths"].values():
        for method, operation in path_item.items():
            if method in OPENAPI_METHODS:
                assert "security" in operation


def test_live_generated_response_schemas_remain_structured() -> None:
    document = build_openapi_document()
    schemas = document["components"]["schemas"]

    assert "properties" in schemas["AgentResponse"]
    assert "properties" in schemas["AnalyticsSummaryResponse"]
    assert schemas["DeploymentResponse"]["properties"]["allowed_actions"]["readOnly"]
    assert schemas["UsageEventResponse"]["properties"]["metadata"]["readOnly"]
    assert not any(name.endswith(("-Input", "-Output")) for name in schemas)


def test_generated_document_matches_shared_app_schema_outside_security_metadata() -> None:
    from src.api.main import app

    generated = build_openapi_document()
    shared_schema = get_application_openapi(app)

    assert _without_security_metadata(generated) == _without_security_metadata(shared_schema)
