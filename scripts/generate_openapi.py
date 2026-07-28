import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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


def build_openapi_document() -> dict[str, Any]:
    from fastapi.openapi.utils import get_openapi

    from src.api.main import app  # noqa: E402

    spec = get_openapi(title=app.title, version=app.version, routes=app.routes)

    # Add Bearer token security scheme so the spec accurately reflects
    # that auth-guarded routes require an Authorization header.
    # Routes using get_current_agent / get_current_user via Depends()
    # are not detected by FastAPI's automatic security inference.
    spec["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT bearer token or API key. Example: 'Bearer eyJ...'",
        }
    }

    # Apply Bearer auth globally — all routes require auth by default.
    # Routes that are genuinely public (health probes, docs, etc.) should
    # declare `security: []` (no auth) explicitly in their route file.
    spec["security"] = [{"BearerAuth": []}]

    # Override global security for genuinely public paths so they show
    # "lock icon = none" in Swagger UI even though they have no explicit
    # security key in the route definition.
    public_paths = {
        "/health",
        "/ready",
        "/metrics",
        # Auth routes — intentionally public (no get_current_user dependency)
        "/v1/auth/login",
        "/v1/auth/register",
        "/v1/auth/forgot-password",
        "/v1/auth/reset-password",
        "/v1/auth/verify-email",
        "/v1/auth/resend-verification",
        "/v1/auth/oauth",
        "/v1/auth/sso",
    }
    for path, path_item in spec.get("paths", {}).items():
        if path in public_paths:
            for method, operation in path_item.items():
                if method in ("get", "post", "put", "patch", "delete"):
                    operation["security"] = []

    return normalize_openapi_document(spec)


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
