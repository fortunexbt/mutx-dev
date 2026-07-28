const PICO_HOSTS = new Set(["pico.mutx.dev", "pico.localhost"]);
const REDIRECT_BASE_URL = "https://redirect.invalid";

function hasUnsafeRedirectCharacters(value: string) {
  return (
    value.includes("\\") ||
    Array.from(value).some((character) => {
      const codePoint = character.codePointAt(0) ?? 0;
      return codePoint <= 0x1f || codePoint === 0x7f;
    })
  );
}

function decodeRedirectPath(value: string) {
  let decoded = value;

  for (let pass = 0; pass < 2; pass += 1) {
    const next = decodeURIComponent(decoded);
    if (next === decoded) break;
    decoded = next;
  }

  return decoded;
}

export function isPicoHost(hostname?: string | null) {
  if (!hostname) {
    return false;
  }

  return PICO_HOSTS.has(hostname.toLowerCase());
}

export function getDefaultRedirectPathForHost(
  hostname?: string | null,
  fallback = "/dashboard",
) {
  return isPicoHost(hostname) ? "/" : fallback;
}

export function mergeRedirectPathWithSearch(
  nextPath?: string | null,
  search?: string | null,
) {
  if (!nextPath || !search || nextPath.includes("?")) {
    return nextPath;
  }

  const normalizedSearch = search.startsWith("?") ? search : `?${search}`;
  if (normalizedSearch === "?") {
    return nextPath;
  }

  const hashIndex = nextPath.indexOf("#");
  if (hashIndex === -1) {
    return `${nextPath}${normalizedSearch}`;
  }

  return `${nextPath.slice(0, hashIndex)}${normalizedSearch}${nextPath.slice(hashIndex)}`;
}

export function resolveRedirectPath(
  nextPath?: string | null,
  fallback = "/dashboard",
) {
  if (!nextPath) {
    return fallback;
  }

  if (hasUnsafeRedirectCharacters(nextPath)) {
    return fallback;
  }

  let decodedPath: string;
  let resolvedUrl: URL;
  try {
    decodedPath = decodeRedirectPath(nextPath);
    resolvedUrl = new URL(nextPath, REDIRECT_BASE_URL);
  } catch {
    return fallback;
  }

  if (
    !nextPath.startsWith("/") ||
    nextPath.startsWith("//") ||
    hasUnsafeRedirectCharacters(decodedPath) ||
    !decodedPath.startsWith("/") ||
    decodedPath.startsWith("//") ||
    resolvedUrl.origin !== REDIRECT_BASE_URL
  ) {
    return fallback;
  }

  if (
    decodedPath.startsWith("/login") ||
    decodedPath.startsWith("/register") ||
    decodedPath.startsWith("/api/auth/oauth/")
  ) {
    return fallback;
  }

  return nextPath;
}
