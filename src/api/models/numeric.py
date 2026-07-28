"""Reusable finite-number contracts for API ingestion and serialization."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)


FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
PercentageFloat = Annotated[float, Field(ge=0.0, le=100.0, allow_inf_nan=False)]
UnitIntervalFloat = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class NonFiniteNumberError(ValueError):
    """Raised when a non-finite float crosses a numeric integrity boundary."""


def reject_non_finite_floats(value: Any, *, path: str = "$") -> Any:
    """Reject non-finite floats recursively while preserving the original value.

    The validator intentionally walks the entire arbitrary-JSON value instead of
    relying only on typed leaf fields. The path is included in the validation
    error so callers can identify the poisoned nested value without persisting it.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NonFiniteNumberError(f"non-finite float at {path}")
        return value

    if isinstance(value, Mapping):
        for key, item in value.items():
            reject_non_finite_floats(item, path=f"{path}.{key}")
        return value

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            reject_non_finite_floats(item, path=f"{path}[{index}]")
        return value

    return value


FiniteJsonDict = Annotated[dict[str, Any], AfterValidator(reject_non_finite_floats)]
FiniteJsonList = Annotated[list[Any], AfterValidator(reject_non_finite_floats)]


def nullable_non_finite_numbers(value: Any) -> tuple[Any, bool]:
    """Return a JSON-safe copy with non-finite floats represented as null.

    This helper is for legacy response data only. New externally persisted JSON
    is rejected by :func:`reject_non_finite_floats` instead.
    """
    if isinstance(value, float):
        if math.isfinite(value):
            return value, False
        return None, True

    if isinstance(value, Mapping):
        degraded = False
        output: dict[Any, Any] = {}
        for key, item in value.items():
            sanitized, item_degraded = nullable_non_finite_numbers(item)
            output[key] = sanitized
            degraded = degraded or item_degraded
        return output, degraded

    if isinstance(value, list):
        degraded = False
        output_list: list[Any] = []
        for item in value:
            sanitized, item_degraded = nullable_non_finite_numbers(item)
            output_list.append(sanitized)
            degraded = degraded or item_degraded
        return output_list, degraded

    if isinstance(value, tuple):
        sanitized, degraded = nullable_non_finite_numbers(list(value))
        return tuple(sanitized), degraded

    return value, False


def require_finite_float(value: Any, *, path: str) -> float:
    """Convert a scalar to float and fail if it is not finite."""
    converted = float(value)
    reject_non_finite_floats(converted, path=path)
    return converted


class DegradedNumericResponseModel(BaseModel):
    """Response base that exposes legacy numeric corruption instead of inventing zeroes."""

    degraded: bool = False

    @model_serializer(mode="wrap")
    def _serialize_nullable_numbers(self, handler: SerializerFunctionWrapHandler) -> Any:
        serialized, found_non_finite = nullable_non_finite_numbers(handler(self))
        if isinstance(serialized, dict):
            serialized["degraded"] = bool(serialized.get("degraded")) or found_non_finite
        return serialized
