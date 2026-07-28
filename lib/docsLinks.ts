import fs from "fs";
import path from "path";

import {
  canonicalizeDocsRoute,
  docsFileToCanonicalRoute,
  getDocsPublicationManifest,
  type DocsPublicationManifest,
} from "@/lib/docs";

const SOURCE_BASE_URL = "https://github.com/mutx-dev/mutx-dev/blob/main";

function splitHref(href: string) {
  const hashIndex = href.indexOf("#");
  const beforeHash = hashIndex >= 0 ? href.slice(0, hashIndex) : href;
  const hash = hashIndex >= 0 ? href.slice(hashIndex) : "";
  const queryIndex = beforeHash.indexOf("?");
  const hrefPath = queryIndex >= 0 ? beforeHash.slice(0, queryIndex) : beforeHash;
  const query = queryIndex >= 0 ? beforeHash.slice(queryIndex) : "";
  return { hrefPath, suffix: `${query}${hash}` };
}

function normalizeRepoSegments(segments: string[]): string[] {
  const normalized: string[] = [];
  for (const segment of segments) {
    if (!segment || segment === ".") continue;
    if (segment === "..") normalized.pop();
    else normalized.push(segment);
  }
  return normalized;
}

export function repoSourceHref(sourcePath: string): string {
  const encodedPath = sourcePath
    .split("/")
    .filter(Boolean)
    .map(encodeURIComponent)
    .join("/");
  return `${SOURCE_BASE_URL}/${encodedPath}`;
}

function publishedRouteForSource(
  sourcePath: string,
  publication: DocsPublicationManifest,
): string | null {
  const normalized = sourcePath.replace(/\\/g, "/");
  const published = publication.bySourcePath.get(normalized);
  if (published) return published.route;

  if (normalized === "support.md") return "/support";
  if (!normalized.startsWith("docs/") || !normalized.toLowerCase().endsWith(".md")) return null;
  return docsFileToCanonicalRoute(
    path.resolve(publication.repoRoot, normalized),
    path.resolve(publication.repoRoot, "docs"),
    publication.repoRoot,
  );
}

function withSuffix(href: string, suffix: string): string {
  return suffix ? `${href}${suffix}` : href;
}

/** Resolve a Markdown source link to a route only when that route is published.
 * Repo files and unpublished Markdown stay honest by linking to canonical source.
 */
export function resolveDocHref(
  href: string,
  currentSlug: string[],
  publication = getDocsPublicationManifest(),
): string {
  if (!href || href.startsWith("#") || /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//")) {
    return href;
  }

  const { hrefPath, suffix } = splitHref(href);
  if (!hrefPath) return href;

  if (hrefPath.startsWith("/")) {
    if (hrefPath === "/docs" || hrefPath.startsWith("/docs/")) {
      const canonical = canonicalizeDocsRoute(hrefPath);
      if (publication.byRoute.has(canonical)) {
        return withSuffix(canonical, suffix);
      }

      let sourcePath = canonical.replace(/^\/docs\/?/, "");
      if (sourcePath === "reference") sourcePath = "api/reference";
      else if (sourcePath.startsWith("reference/")) sourcePath = `api/${sourcePath.slice(10)}`;
      const candidate = `docs/${sourcePath}.md`;
      return fs.existsSync(path.resolve(publication.repoRoot, candidate))
        ? withSuffix(repoSourceHref(candidate), suffix)
        : href;
    }
    return href;
  }

  const base = ["docs", ...currentSlug.slice(0, -1)];
  const sourceSegments = normalizeRepoSegments([...base, ...hrefPath.split("/")]);
  const sourcePath = sourceSegments.join("/");

  if (sourcePath.startsWith("public/")) {
    return withSuffix(`/${sourcePath.slice("public/".length)}`, suffix);
  }

  const candidates = /\.[a-z0-9]+$/i.test(sourcePath)
    ? [sourcePath]
    : [`${sourcePath}.md`, `${sourcePath}/README.md`, `${sourcePath}/index.md`];
  const publishedSource = candidates.find((candidate) => publication.bySourcePath.has(candidate));

  if (publishedSource) {
    const route = publishedRouteForSource(publishedSource, publication);
    if (route) return withSuffix(route, suffix);
  }

  const sourceCandidate = candidates.find((candidate) => {
    return fs.existsSync(path.resolve(publication.repoRoot, candidate));
  });
  if (sourceCandidate) return withSuffix(repoSourceHref(sourceCandidate), suffix);

  // Preserve unresolved web-style links. The renderer sanitizes unsafe schemes,
  // and a missing source must not be invented as a published docs route.
  return href;
}

export function resolveDocAssetHref(href: string, currentSlug: string[]): string {
  if (!href || href.startsWith("/") || /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//")) {
    return href;
  }

  const base = ["docs", ...currentSlug.slice(0, -1)];
  const sourcePath = normalizeRepoSegments([...base, ...href.split("/")]).join("/");
  return sourcePath.startsWith("public/") ? `/${sourcePath.slice("public/".length)}` : href;
}
