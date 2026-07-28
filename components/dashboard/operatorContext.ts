const MAX_CONTEXT_DEPTH = 6;
const MAX_COLLECTION_ITEMS = 60;
const MAX_STRING_LENGTH = 4_000;
const SENSITIVE_KEY_PATTERN =
  /(authorization|cookie|password|passwd|secret|token|api[_-]?key|private[_-]?key|credential)/i;

function truncateString(value: string) {
  if (value.length <= MAX_STRING_LENGTH) return value;
  return `${value.slice(0, MAX_STRING_LENGTH)}… [truncated]`;
}

export function redactOperatorContext(
  value: unknown,
  depth = 0,
  seen = new WeakSet<object>(),
): unknown {
  if (typeof value === "string") return truncateString(value);
  if (
    value === null ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return value;
  }
  if (value === undefined) return "[undefined]";
  if (typeof value !== "object") return `[${typeof value}]`;
  if (depth >= MAX_CONTEXT_DEPTH) return "[depth limit]";
  if (seen.has(value)) return "[circular]";

  seen.add(value);

  if (Array.isArray(value)) {
    const redacted = value
      .slice(0, MAX_COLLECTION_ITEMS)
      .map((item) => redactOperatorContext(item, depth + 1, seen));
    if (value.length > MAX_COLLECTION_ITEMS) {
      redacted.push(`[${value.length - MAX_COLLECTION_ITEMS} more items]`);
    }
    return redacted;
  }

  const entries = Object.entries(value as Record<string, unknown>);
  const redacted: Record<string, unknown> = {};
  entries.slice(0, MAX_COLLECTION_ITEMS).forEach(([key, nestedValue]) => {
    redacted[key] = SENSITIVE_KEY_PATTERN.test(key)
      ? "[redacted]"
      : redactOperatorContext(nestedValue, depth + 1, seen);
  });
  if (entries.length > MAX_COLLECTION_ITEMS) {
    redacted["[truncated]"] = `${entries.length - MAX_COLLECTION_ITEMS} more fields`;
  }
  return redacted;
}

export function formatOperatorContext(value: unknown) {
  try {
    return JSON.stringify(redactOperatorContext(value), null, 2);
  } catch {
    return "[context unavailable]";
  }
}

export function summarizeOperatorContext(value: unknown, maxLength = 180) {
  const summary = formatOperatorContext(value).replace(/\s+/g, " ").trim();
  if (summary.length <= maxLength) return summary;
  return `${summary.slice(0, maxLength)}…`;
}

export function safeOperatorFileSegment(value: string) {
  return (
    value
      .replace(/[^a-zA-Z0-9._-]+/g, "-")
      .replace(/^[.-]+|[.-]+$/g, "")
      .slice(0, 80) || "evidence"
  );
}
