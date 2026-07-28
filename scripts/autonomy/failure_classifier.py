from __future__ import annotations

import re


_DURATION_TOKEN = re.compile(
    r"(?P<value>\d+)\s*(?P<unit>hours?|hrs?|hr|h|minutes?|mins?|min|m|seconds?|secs?|sec|s)",
    re.IGNORECASE,
)


def extract_retry_after_seconds(text: str) -> int | None:
    hay = text or ""
    lowered = hay.lower()
    if not lowered.strip():
        return None
    matches = list(_DURATION_TOKEN.finditer(lowered))
    if not matches:
        direct = re.search(r"retry[-_ ]after[^\d]*(\d{2,6})", lowered)
        if direct:
            return int(direct.group(1))
        return None
    total = 0
    for match in matches[:3]:
        value = int(match.group("value"))
        unit = match.group("unit").lower()
        if unit.startswith("h"):
            total += value * 3600
        elif unit.startswith("m"):
            total += value * 60
        else:
            total += value
    return total or None


def classify_failure(text: str) -> str | None:
    hay = (text or "").lower()
    if not hay.strip():
        return None
    if (
        "quota exceeded" in hay
        or "billing details" in hay
        or "insufficient_quota" in hay
        or "usage limit" in hay
        or "rate limit" in hay
    ):
        return "quota_exceeded"
    if "http error 404" in hay or "not found" in hay and "api" in hay:
        return "provider_failure"
    if "auth" in hay and ("failed" in hay or "missing" in hay or "invalid" in hay):
        return "auth_failure"
    if "api key" in hay and ("missing" in hay or "invalid" in hay):
        return "auth_failure"
    if "no module named 'openclaw'" in hay:
        return "runtime_bootstrap_failure"
    if "unknown option '--task'" in hay:
        return "stale_cli_contract"
    if "must be run in a work tree" in hay or "not a git repository" in hay:
        return "invalid_worktree"
    return None
