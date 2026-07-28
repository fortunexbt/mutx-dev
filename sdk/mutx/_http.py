from __future__ import annotations

import string
from collections.abc import Collection
from typing import Any
from urllib.parse import quote

import httpx

API_VERSION = "v1"
DEFAULT_BASE_URL = "https://api.mutx.dev"


def normalize_api_base_url(base_url: str) -> str:
    """Return an absolute API base URL ending in exactly one ``/v1`` segment."""

    candidate = base_url.strip()
    if not candidate:
        raise ValueError("base_url must not be empty")

    url = httpx.URL(candidate)
    if not url.is_absolute_url:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if url.scheme not in {"http", "https"}:
        raise ValueError("base_url must use the http or https scheme")
    if url.query or url.fragment:
        raise ValueError("base_url must not include a query string or fragment")

    path = url.path.rstrip("/")
    if path.rsplit("/", 1)[-1] != API_VERSION:
        path = f"{path}/{API_VERSION}"

    return str(url.copy_with(path=path))


def api_path(
    template: str,
    /,
    *,
    path_parameters: Collection[str] = (),
    **parameters: Any,
) -> str:
    """Render a relative API route while safely encoding dynamic path segments.

    Values are encoded as one path segment by default. Parameters named in
    ``path_parameters`` may contain slashes for FastAPI ``:path`` converters.
    """

    if (
        template.startswith("/")
        or template == API_VERSION
        or template.startswith(f"{API_VERSION}/")
    ):
        raise ValueError("API paths must be relative to the canonical /v1 base URL")

    field_names = {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name is not None
    }
    parameter_names = set(parameters)
    if field_names != parameter_names:
        missing = field_names - parameter_names
        unexpected = parameter_names - field_names
        details = []
        if missing:
            details.append(f"missing parameters: {', '.join(sorted(missing))}")
        if unexpected:
            details.append(f"unexpected parameters: {', '.join(sorted(unexpected))}")
        raise ValueError("Invalid API path parameters (" + "; ".join(details) + ")")

    unknown_path_parameters = set(path_parameters) - field_names
    if unknown_path_parameters:
        names = ", ".join(sorted(unknown_path_parameters))
        raise ValueError(f"Unknown path parameters: {names}")

    encoded = {
        name: quote(str(value), safe="/" if name in path_parameters else "")
        for name, value in parameters.items()
    }
    return template.format_map(encoded)
