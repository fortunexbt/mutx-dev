from copy import deepcopy
import json
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING, get_args, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fastapi import FastAPI
    from fastapi.dependencies.models import Dependant
    from starlette.routing import BaseRoute

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


AUTH_SCHEMES_BY_HEADER = {
    "authorization": "BearerAuth",
    "x-api-key": "ApiKeyAuth",
}
MIDDLEWARE_API_KEY_USER_DEPENDENCIES = {
    ("src.api.middleware.auth", "get_current_user"),
}
OPENAPI_HTTP_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put"})
BEARER_SECURITY_SCHEME = {
    "type": "http",
    "scheme": "bearer",
    "bearerFormat": "JWT",
    "description": "JWT, managed API key, or agent API key sent as a Bearer credential.",
}
API_KEY_SECURITY_SCHEME = {
    "type": "apiKey",
    "in": "header",
    "name": "X-API-Key",
    "description": "Managed MUTX API key sent in the X-API-Key header.",
}


def normalize_openapi_document(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_openapi_document(item) for item in value]

    if not isinstance(value, dict):
        return value

    normalized = {key: normalize_openapi_document(item) for key, item in value.items()}
    all_of = normalized.get("allOf")
    if (
        isinstance(all_of, list)
        and len(all_of) == 1
        and isinstance(all_of[0], dict)
        and set(all_of[0]) == {"$ref"}
    ):
        merged = {"$ref": all_of[0]["$ref"]}
        merged.update((key, item) for key, item in normalized.items() if key != "allOf")
        return merged

    return normalized


def _pydantic_model_by_name(model_name: str) -> type[Any] | None:
    from pydantic import BaseModel

    pending = list(BaseModel.__subclasses__())
    seen: set[type[Any]] = set()
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        pending.extend(model.__subclasses__())
        if model.__name__ == model_name:
            return model
    return None


def _uses_degraded_numeric_response_wrapper(model: type[Any]) -> bool:
    return any(
        base.__module__ == "src.api.models.numeric"
        and base.__name__ == "DegradedNumericResponseModel"
        for base in model.__mro__
    )


def _add_computed_field_schemas(schema: dict[str, Any], model_name: str) -> None:
    from pydantic import TypeAdapter

    model = _pydantic_model_by_name(model_name)
    if model is None:
        return

    properties = schema.setdefault("properties", {})
    required = schema.setdefault("required", [])
    for field_name, field_info in model.model_computed_fields.items():
        property_name = field_info.alias or field_name
        if property_name in properties:
            continue
        field_schema = TypeAdapter(field_info.return_type).json_schema(
            ref_template="#/components/schemas/{model}"
        )
        field_schema["title"] = field_info.title or property_name.replace("_", " ").title()
        if field_info.description:
            field_schema["description"] = field_info.description
        field_schema["readOnly"] = True
        properties[property_name] = field_schema
        if property_name not in required:
            required.append(property_name)


def _repair_empty_model_schemas(schemas: dict[str, Any]) -> None:
    for model_name, schema in list(schemas.items()):
        if schema:
            continue
        model = _pydantic_model_by_name(model_name)
        if model is None or not _uses_degraded_numeric_response_wrapper(model):
            continue
        structured = model.model_json_schema(
            mode="validation",
            ref_template="#/components/schemas/{model}",
        )
        definitions = structured.pop("$defs", {})
        for definition_name, definition in definitions.items():
            schemas.setdefault(definition_name, definition)
        _add_computed_field_schemas(structured, model_name)
        schemas[model_name] = structured


def _replace_schema_refs(value: Any, replacements: dict[str, str]) -> None:
    if isinstance(value, list):
        for item in value:
            _replace_schema_refs(item, replacements)
        return
    if not isinstance(value, dict):
        return

    ref = value.get("$ref")
    prefix = "#/components/schemas/"
    if isinstance(ref, str) and ref.startswith(prefix):
        schema_name = ref[len(prefix) :]
        if schema_name in replacements:
            value["$ref"] = f"{prefix}{replacements[schema_name]}"
    for item in value.values():
        _replace_schema_refs(item, replacements)


def canonicalize_response_schemas(document: dict[str, Any]) -> dict[str, Any]:
    """Collapse FastAPI ``-Input``/``-Output`` response variants.

    Response models are not request bodies in the MUTX contract. Keeping one
    canonical component name avoids breaking existing TypeScript consumers. If
    an ``Any`` wrap serializer erased the output schema, rebuild its computed
    fields on top of the structured input schema.
    """
    schemas = document.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict):
        return document

    replacements: dict[str, str] = {}
    bases = {
        name.removesuffix("-Input").removesuffix("-Output")
        for name in schemas
        if name.endswith(("-Input", "-Output"))
        and name.removesuffix("-Input").removesuffix("-Output").endswith("Response")
    }
    for base in sorted(bases):
        input_name = f"{base}-Input"
        output_name = f"{base}-Output"
        input_schema = schemas.get(input_name)
        output_schema = schemas.get(output_name)
        model = _pydantic_model_by_name(base)
        if isinstance(output_schema, dict) and output_schema:
            selected = output_schema
        elif model is not None and _uses_degraded_numeric_response_wrapper(model):
            selected = input_schema
        else:
            continue
        if not isinstance(selected, dict):
            continue
        selected = deepcopy(selected)
        if not output_schema:
            _add_computed_field_schemas(selected, base)
        schemas[base] = selected
        schemas.pop(input_name, None)
        schemas.pop(output_name, None)
        replacements[input_name] = base
        replacements[output_name] = base

    _repair_empty_model_schemas(schemas)
    _replace_schema_refs(document, replacements)
    return document


def get_application_openapi(application: "FastAPI") -> dict[str, Any]:
    """Build FastAPI's shared schema without lossy output-schema splitting.

    Pydantic wrap serializers that return ``Any`` can make FastAPI's default
    serialization-schema mode replace a structured response model with ``{}``.
    MUTX's response wrappers sanitize values without changing their fields, so
    the shared validation schema is the truthful client contract.
    """
    from fastapi.openapi.utils import get_openapi

    document = get_openapi(
        title=application.title,
        version=application.version,
        openapi_version=application.openapi_version,
        summary=application.summary,
        description=application.description,
        terms_of_service=application.terms_of_service,
        contact=application.contact,
        license_info=application.license_info,
        routes=application.routes,
        webhooks=application.webhooks.routes,
        tags=application.openapi_tags,
        servers=application.servers,
        separate_input_output_schemas=False,
        external_docs=application.openapi_external_docs,
    )
    return canonicalize_response_schemas(document)


def _allows_anonymous_principal(dependant: "Dependant") -> bool:
    if dependant.call is None:
        return False

    try:
        return_annotation = get_type_hints(dependant.call).get("return")
    except (NameError, TypeError):
        return False

    return type(None) in get_args(return_annotation)


def _declared_auth_schemes(dependant: "Dependant") -> set[str]:
    schemes = {
        AUTH_SCHEMES_BY_HEADER[str(parameter.alias).lower()]
        for parameter in dependant.header_params
        if str(parameter.alias).lower() in AUTH_SCHEMES_BY_HEADER
    }
    call = dependant.call
    call_identity = (
        getattr(call, "__module__", ""),
        getattr(call, "__name__", ""),
    )
    if call_identity in MIDDLEWARE_API_KEY_USER_DEPENDENCIES:
        # AuthenticationMiddleware resolves X-API-Key before get_current_user
        # reloads request.state.auth_user_id. The dependency's own signature
        # only declares Authorization, so preserve the application-level
        # alternative explicitly in the generated contract.
        schemes.add("ApiKeyAuth")
    return schemes


def _dependency_security_contract(dependant: "Dependant") -> tuple[str, set[str]]:
    """Return auth optionality and schemes declared by a route dependency tree."""
    optional_auth = False
    required_auth = False
    schemes: set[str] = set()
    pending = list(dependant.dependencies)

    while pending:
        dependency = pending.pop()
        pending.extend(dependency.dependencies)

        declared_schemes = _declared_auth_schemes(dependency)
        if not declared_schemes:
            continue
        schemes.update(declared_schemes)
        if _allows_anonymous_principal(dependency):
            optional_auth = True
        else:
            required_auth = True

    if required_auth:
        return "required", schemes
    if optional_auth:
        return "optional", schemes
    return "public", schemes


def _security_requirement(mode: str, schemes: set[str]) -> list[dict[str, list[str]]]:
    ordered_schemes = sorted(schemes, key=lambda scheme: (scheme != "BearerAuth", scheme))
    requirements = [{scheme: []} for scheme in ordered_schemes]
    if mode == "required":
        return requirements
    if mode == "optional":
        return [{}, *requirements]
    return []


def _remove_inferred_auth_header_parameters(operation: dict[str, Any]) -> None:
    parameters = operation.get("parameters")
    if not isinstance(parameters, list):
        return

    filtered = [
        parameter
        for parameter in parameters
        if not (
            isinstance(parameter, dict)
            and str(parameter.get("in", "")).lower() == "header"
            and str(parameter.get("name", "")).lower() in AUTH_SCHEMES_BY_HEADER
        )
    ]
    if filtered:
        operation["parameters"] = filtered
    else:
        operation.pop("parameters", None)


def apply_operation_security(spec: dict[str, Any], routes: "Iterable[BaseRoute]") -> dict[str, Any]:
    """Annotate OpenAPI operations from their FastAPI dependency contracts."""
    from fastapi.routing import APIRoute

    components = spec.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes.setdefault("BearerAuth", BEARER_SECURITY_SCHEME)
    security_schemes.setdefault("ApiKeyAuth", API_KEY_SECURITY_SCHEME)

    # Authentication is operation-specific. A top-level requirement would also
    # protect anonymous and optional-auth routes, including the framework docs.
    spec.pop("security", None)

    paths = spec.get("paths", {})
    for route in routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue

        path_item = paths.get(route.path_format)
        if not isinstance(path_item, dict):
            continue

        mode, schemes = _dependency_security_contract(route.dependant)
        security = _security_requirement(mode, schemes)
        for route_method in route.methods or ():
            method = route_method.lower()
            operation = path_item.get(method)
            if method not in OPENAPI_HTTP_METHODS or not isinstance(operation, dict):
                continue

            # FastAPI Security dependencies and route openapi_extra values are
            # authoritative operation-level overrides.
            if "security" in operation:
                continue
            operation["security"] = deepcopy(security)
            if schemes:
                _remove_inferred_auth_header_parameters(operation)

    return spec


def build_openapi_document(application: "FastAPI | None" = None) -> dict[str, Any]:
    if application is None:
        from src.api.main import app as application  # noqa: E402

    spec = deepcopy(get_application_openapi(application))
    return normalize_openapi_document(apply_operation_security(spec, application.routes))


def main() -> None:
    output_path = Path("docs/api/openapi.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = build_openapi_document()
    temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with temp_path.open("w") as file_handle:
        json.dump(document, file_handle, indent=2)
    temp_path.replace(output_path)
    print(f"OpenAPI spec generated at {output_path}.")


if __name__ == "__main__":
    main()
