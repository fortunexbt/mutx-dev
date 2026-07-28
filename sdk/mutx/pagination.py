"""Typed pagination results shared by SDK list resources."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Generic, TypeVar, overload

T = TypeVar("T")


class PageEnvelopeError(ValueError):
    """Raised when a paginated API response does not match the public contract."""


class Page(Sequence[T], Generic[T]):
    """A page of SDK models that retains list-style read access.

    Iteration, indexing, ``len(page)``, and equality with a list remain supported
    for callers written against the SDK's former bare-list return values.
    """

    def __init__(
        self,
        items: list[T],
        *,
        total: int | None,
        skip: int,
        limit: int,
        has_more: bool | None,
        is_legacy: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.items = items
        self.total = total
        self.skip = skip
        self.limit = limit
        self.has_more = has_more
        self.is_legacy = is_legacy
        self.metadata = MappingProxyType(dict(metadata or {}))

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> list[T]: ...

    def __getitem__(self, index: int | slice) -> T | list[T]:
        return self.items[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Page):
            return (
                self.items == other.items
                and self.total == other.total
                and self.skip == other.skip
                and self.limit == other.limit
                and self.has_more == other.has_more
                and self.is_legacy == other.is_legacy
                and self.metadata == other.metadata
            )
        if isinstance(other, (list, tuple)):
            return self.items == list(other)
        return NotImplemented

    def __repr__(self) -> str:
        return (
            f"Page(items={self.items!r}, total={self.total!r}, skip={self.skip}, "
            f"limit={self.limit}, has_more={self.has_more!r})"
        )


def _require_int(
    payload: Mapping[str, Any],
    field: str,
    *,
    minimum: int,
) -> int:
    value = payload[field]
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive" if minimum == 1 else "non-negative"
        raise PageEnvelopeError(f"pagination field '{field}' must be a {qualifier} integer")
    return value


def _convert_items(raw_items: list[Any], item_factory: Callable[[dict[str, Any]], T]) -> list[T]:
    converted: list[T] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise PageEnvelopeError(f"pagination item at index {index} must be an object")
        try:
            converted.append(item_factory(raw_item))
        except (KeyError, TypeError, ValueError) as exc:
            raise PageEnvelopeError(f"invalid pagination item at index {index}: {exc}") from exc
    return converted


def parse_page(
    payload: object,
    item_factory: Callable[[dict[str, Any]], T],
    *,
    requested_skip: int,
    requested_limit: int,
    require_has_more: bool = False,
) -> Page[T]:
    """Parse a canonical envelope, with an explicit fallback for legacy lists.

    Legacy list responses do not contain reliable totals or continuation data,
    so ``total`` and ``has_more`` are ``None`` on those results.
    """

    if isinstance(payload, list):
        return Page(
            _convert_items(payload, item_factory),
            total=None,
            skip=requested_skip,
            limit=requested_limit,
            has_more=None,
            is_legacy=True,
        )

    if not isinstance(payload, dict):
        raise PageEnvelopeError("paginated response must be an object or a legacy list")

    required_fields = {"items", "total", "skip", "limit"}
    missing = sorted(required_fields.difference(payload))
    if missing:
        raise PageEnvelopeError(
            f"paginated response is missing required field(s): {', '.join(missing)}"
        )

    raw_items = payload["items"]
    if not isinstance(raw_items, list):
        raise PageEnvelopeError("pagination field 'items' must be a list")

    total = _require_int(payload, "total", minimum=0)
    skip = _require_int(payload, "skip", minimum=0)
    limit = _require_int(payload, "limit", minimum=1)
    if len(raw_items) > limit:
        raise PageEnvelopeError("pagination field 'items' contains more entries than 'limit'")
    if raw_items and skip + len(raw_items) > total:
        raise PageEnvelopeError("pagination fields 'items', 'skip', and 'total' are inconsistent")

    if require_has_more and "has_more" not in payload:
        raise PageEnvelopeError("paginated response is missing required field(s): has_more")

    if "has_more" in payload:
        has_more = payload["has_more"]
        if not isinstance(has_more, bool):
            raise PageEnvelopeError("pagination field 'has_more' must be a boolean")
    else:
        has_more = skip + len(raw_items) < total

    metadata = {
        key: value
        for key, value in payload.items()
        if key not in {"items", "total", "skip", "limit", "has_more"}
    }
    return Page(
        _convert_items(raw_items, item_factory),
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
        metadata=metadata,
    )
