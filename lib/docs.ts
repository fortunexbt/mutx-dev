import fs from "fs";
import path from "path";
import matter from "gray-matter";

export interface DocNavItem {
  title: string;
  href: string;
  slug: string;
  route: string; // actual Next.js route (e.g. /agents or /docs/api)
  children: DocNavItem[];
  depth: number;
  isPage?: boolean; // true = leaf page, false/undefined = section group
  icon?: string; // GitBook icon name from frontmatter (e.g. "bullseye", "book")
}

function lineDepth(line: string): number {
  // Measure indent of the list-marker (*), not the whole line.
  // "  * [Title]" -> depth 1 (one indent level)
  // "* [Title]"   -> depth 0 (top-level)
  const match = line.match(/^(\s*)\*/);
  if (!match) return 0;
  const indent = match[1].length;
  // Each indent level = 2 spaces (standard markdown convention)
  return Math.floor(indent / 2);
}

function normalizeSummaryHrefToSlug(href: string): string {
  const stripped = href.replace(/^docs\//, "").replace(/\.md$/, "").replace(/^\//, "");
  // Root-level content dirs (agents/) should route to / not /docs
  if (!href.startsWith("docs/")) {
    return stripped.replace(/\/README$/i, "").replace(/\/index$/i, "") || stripped;
  }
  return stripped;
}

/**
 * Read frontmatter from a doc file to extract the `icon` field.
 * Returns undefined if the file doesn't exist or has no icon.
 */
function getDocIcon(
  href: string,
  repoRoot: string,
  watchPaths?: Set<string>,
): string | undefined {
  // Build the file path from the SUMMARY href
  // e.g. "manifesto.md"         → docs/manifesto.md
  // e.g. "whitepaper.md"        → docs/whitepaper.md
  // e.g. "docs/api/reference.md" → docs/api/reference.md
  // e.g. "agents/README.md"     → agents/README.md
  const candidates: string[] = [];
  if (href.startsWith("docs/")) {
    candidates.push(path.join(/* turbopackIgnore: true */ repoRoot, href));
  } else if (href.startsWith("agents/") || href.startsWith("contributing/")) {
    candidates.push(path.join(/* turbopackIgnore: true */ repoRoot, href));
  } else {
    candidates.push(path.join(/* turbopackIgnore: true */ repoRoot, "docs", href));
    candidates.push(path.join(/* turbopackIgnore: true */ repoRoot, href)); // root-level fallback
  }

  for (const filePath of candidates) {
    watchPaths?.add(path.resolve(filePath));
    try {
      const raw = fs.readFileSync(filePath, "utf-8");
      const { data } = matter(raw);
      if (typeof data.icon === "string") return data.icon;
    } catch {
      // try next candidate
    }
  }
  return undefined;
}

function parseLine(line: string): { title: string; href: string; slug: string } | null {
  const match = line.match(/^\s*\*\s*\[([^\]]+)\]\(([^)]+)\)/);
  if (!match) return null;
  const [, title, href] = match;
  return { title, href, slug: normalizeSummaryHrefToSlug(href) };
}

function readSummary(repoRoot: string, watchPaths?: Set<string>): DocNavItem[] {
  const summaryPath = path.join(/* turbopackIgnore: true */ repoRoot, "SUMMARY.md");
  watchPaths?.add(path.resolve(summaryPath));
  const content = fs.readFileSync(summaryPath, "utf-8");
  const lines = content.split("\n");

  const root: DocNavItem[] = [];
  const stack: { item: DocNavItem; depth: number }[] = [];

  for (const line of lines) {
    if (!line.includes("[") || !line.includes("](")) continue;

    const parsed = parseLine(line);
    if (!parsed) continue;

    const depth = lineDepth(line);
    const item: DocNavItem = {
      title: parsed.title,
      href: parsed.href,
      slug: parsed.slug,
      route: summaryHrefToDocsRoute(parsed.href) ?? `/docs/${parsed.slug}`,
      children: [],
      depth,
      icon: getDocIcon(parsed.href, repoRoot, watchPaths),
    };

    // Find where to insert
    while (stack.length > 0 && stack[stack.length - 1].depth >= depth) {
      stack.pop();
    }

    if (stack.length === 0) {
      root.push(item);
    } else {
      stack[stack.length - 1].item.children.push(item);
    }

    stack.push({ item, depth });
  }

  return root;
}

export function parseSummary(): DocNavItem[] {
  return getDocsPublicationManifest().nav;
}

export function flatNav(items: DocNavItem[]): DocNavItem[] {
  const result: DocNavItem[] = [];
  for (const item of items) {
    result.push(item);
    result.push(...flatNav(item.children));
  }
  return result;
}

export function summaryHrefToDocsRoute(href: string): string | null {
  if (href === "docs/sdk.md") return "/sdk";
  if (href === "support.md" || href === "docs/support.md") return "/support";

  // GitBook maps docs/api/* → /docs/reference/* (api/ dir → /reference URL path)
  // e.g. docs/api/reference.md → /docs/reference
  // e.g. docs/api/authentication.md → /docs/reference/authentication
  // e.g. docs/api/index.md → /docs/reference

  let working = href;

  // 1. Remap docs/api/ → docs/reference/
  working = working.replace(/^docs\/api\//, "docs/reference/");

  // 2. Strip docs/ prefix to get the slug path
  const slug = working.replace(/^docs\//, "");

  // 3. Strip .md, /README, /index suffixes
  let clean = slug
    .replace(/\.md$/, "")
    .replace(/\/README$/i, "")
    .replace(/\/index$/i, "")
    .replace(/^README$/i, "")
    .replace(/^index$/i, "");

  // 4. docs/api/reference.md → docs/reference/reference → strip redundant segment
  clean = clean.replace(/^reference\/reference$/, "reference");

  if (!clean) return "/docs";
  return `/docs/${clean}`;
}

export function getDocSitemapRoutes(): string[] {
  return Array.from(getPublishedDocRoutes());
}

export interface PublishedDoc {
  route: string;
  filePath: string;
  sourcePath: string;
}

export interface DocsPublicationManifest {
  repoRoot: string;
  nav: DocNavItem[];
  docs: readonly PublishedDoc[];
  byRoute: ReadonlyMap<string, PublishedDoc>;
  bySourcePath: ReadonlyMap<string, PublishedDoc>;
  docRoutes: ReadonlySet<string>;
}

const INTERNAL_PUBLIC_DOC_PATTERNS = [
  /(^|\/)AGENTS?\.md$/i,
  /(^|\/)(?:runbooks?|internal)(\/|$)/i,
  /claim-to-reality-gap-matrix/i,
  /mutation-testing/i,
  /deployment\/(?:cli-release|release-v0\.1)\.md$/i,
  /(^|\/)contracts\/api\/webhooks\.md$/i,
];

const PUBLIC_DOC_PATH_EXCEPTIONS = new Set([
  "api/agents.md",
]);

function isSafePublicDocPath(filePath: string, docsRoot: string): boolean {
  const resolved = path.resolve(filePath);
  const relative = path.relative(docsRoot, resolved).replace(/\\/g, "/");
  const isExplicitPublicDoc = PUBLIC_DOC_PATH_EXCEPTIONS.has(relative.toLowerCase());
  return Boolean(relative) &&
    !relative.startsWith("..") &&
    !path.isAbsolute(relative) &&
    relative.endsWith(".md") &&
    (isExplicitPublicDoc || !INTERNAL_PUBLIC_DOC_PATTERNS.some((pattern) => pattern.test(relative)));
}

export function getFrontmatterDateModified(data: Record<string, unknown>): string | undefined {
  const value = data.dateModified;

  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? undefined : value.toISOString();
  }

  if (typeof value !== "string") return undefined;

  const dateModified = value.trim();
  return dateModified && !Number.isNaN(Date.parse(dateModified)) ? dateModified : undefined;
}

export function docsFileToCanonicalRoute(
  filePath: string,
  docsRoot = path.resolve(process.cwd(), "docs"),
  repoRoot = path.dirname(docsRoot),
): string | null {
  repoRoot = path.resolve(repoRoot);
  const repoRelative = path.relative(repoRoot, filePath).replace(/\\/g, "/");
  if (repoRelative.toLowerCase() === "docs/contracts/api/webhooks.md") return null;
  if (repoRelative === "support.md") return "/support";

  let relative = path.relative(docsRoot, filePath).replace(/\\/g, "/");
  if (relative.startsWith("..") || path.isAbsolute(relative)) return null;
  if (relative.toLowerCase() === "sdk.md") return "/sdk";

  relative = relative.replace(/\.md$/i, "");
  if (relative === "api/reference" || relative === "api/index") return "/docs/reference";
  if (relative.startsWith("api/")) relative = `reference/${relative.slice(4)}`;
  relative = relative.replace(/\/(README|index)$/i, "");
  relative = relative.replace(/^(README|index)$/i, "");
  return relative ? `/docs/${relative}` : "/docs";
}

function linkedMarkdownPaths(source: string): string[] {
  const hrefs = new Set<string>();
  for (const match of source.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) hrefs.add(match[1]);
  for (const match of source.matchAll(/href=["']([^"']+)["']/gi)) hrefs.add(match[1]);
  return Array.from(hrefs);
}

function resolveLinkedDocPath(
  href: string,
  fromFile: string,
  docsRoot: string,
  repoRoot: string,
  watchPaths: Set<string>,
): string | null {
  const clean = href.split("#", 1)[0].split("?", 1)[0].trim();
  if (!clean || /^[a-z][a-z0-9+.-]*:/i.test(clean) || clean.startsWith("//")) return null;

  let candidate: string;
  if (clean === "/support") {
    candidate = path.resolve(repoRoot, "support.md");
  } else if (clean === "/sdk") {
    candidate = path.join(docsRoot, "sdk.md");
  } else if (clean.startsWith("/docs/")) {
    let routePath = clean.slice("/docs/".length);
    if (routePath === "reference") routePath = "api/reference";
    else if (routePath.startsWith("reference/")) routePath = `api/${routePath.slice("reference/".length)}`;
    candidate = path.join(docsRoot, routePath);
  } else if (clean.startsWith("/")) {
    return null;
  } else {
    candidate = path.resolve(path.dirname(fromFile), clean);
  }

  const candidates = /\.md$/i.test(candidate)
    ? [candidate]
    : [`${candidate}.md`, path.join(candidate, "README.md"), path.join(candidate, "index.md")];
  return candidates.find((filePath) => {
    watchPaths.add(path.resolve(filePath));
    if (!fs.existsSync(filePath)) return false;
    if (path.resolve(filePath) === path.resolve(repoRoot, "support.md")) return true;
    return isSafePublicDocPath(filePath, docsRoot);
  }) ?? null;
}

/**
 * Public docs are the curated SUMMARY tree plus safe Markdown pages linked from
 * that tree. The route/source map is the publication contract shared by the
 * renderer and search index; first-party SUMMARY entries win route collisions.
 */
function buildDocsPublicationManifest(repoRoot: string): {
  manifest: DocsPublicationManifest;
  watchPaths: string[];
} {
  repoRoot = path.resolve(repoRoot);
  const docsRoot = path.resolve(repoRoot, "docs");
  const watchPaths = new Set<string>();
  const nav = readSummary(repoRoot, watchPaths);
  const published = new Map<string, PublishedDoc>();
  const queue: string[] = [];
  const visited = new Set<string>();

  function addSource(filePath: string) {
    const resolved = path.resolve(filePath);
    watchPaths.add(resolved);
    const route = docsFileToCanonicalRoute(resolved, docsRoot, repoRoot);
    if (!route) return;

    if (!published.has(route)) {
      published.set(route, {
        route,
        filePath: resolved,
        sourcePath: path.relative(repoRoot, resolved).replace(/\\/g, "/"),
      });
    }
    if (!visited.has(resolved) && !queue.includes(resolved)) queue.push(resolved);
  }

  const rootReadme = path.join(docsRoot, "README.md");
  watchPaths.add(path.resolve(rootReadme));
  if (fs.existsSync(rootReadme)) addSource(rootReadme);

  for (const item of flatNav(nav)) {
    const candidates = item.href.startsWith("docs/")
      ? [path.resolve(repoRoot, item.href)]
      : [path.resolve(docsRoot, item.href), path.resolve(repoRoot, item.href)];
    candidates.forEach((candidate) => watchPaths.add(candidate));
    const filePath = candidates.find((candidate) => fs.existsSync(candidate));
    if (!filePath) continue;
    if (filePath !== path.resolve(repoRoot, "support.md") && !isSafePublicDocPath(filePath, docsRoot)) {
      continue;
    }
    addSource(filePath);
  }

  while (queue.length > 0) {
    const filePath = queue.shift()!;
    if (visited.has(filePath)) continue;
    visited.add(filePath);
    addSource(filePath);

    const source = fs.readFileSync(filePath, "utf-8");
    for (const href of linkedMarkdownPaths(source)) {
      const linkedPath = resolveLinkedDocPath(href, filePath, docsRoot, repoRoot, watchPaths);
      if (linkedPath) addSource(linkedPath);
    }
  }

  const docs = Array.from(published.values()).sort((a, b) => {
    if (a.route === "/docs") return -1;
    if (b.route === "/docs") return 1;
    return a.route.localeCompare(b.route);
  });
  const byRoute = new Map(docs.map((doc) => [doc.route, doc]));
  const bySourcePath = new Map(docs.map((doc) => [doc.sourcePath, doc]));
  const docRoutes = new Set(
    docs
      .map((doc) => doc.route)
      .filter((route) => route === "/docs" || route.startsWith("/docs/")),
  );

  return {
    manifest: {
      repoRoot,
      nav,
      docs,
      byRoute,
      bySourcePath,
      docRoutes,
    },
    watchPaths: Array.from(watchPaths).sort(),
  };
}

interface CachedDocsPublicationManifest {
  manifest: DocsPublicationManifest;
  watchPaths: string[];
  sourceSignature: string;
}

let cachedDocsPublicationManifest: CachedDocsPublicationManifest | null = null;

function getSourceSignature(filePaths: string[]): string {
  return filePaths.map((filePath) => {
    try {
      const stat = fs.statSync(filePath, { bigint: true });
      return `${filePath}:${stat.size}:${stat.mtimeNs}:${stat.ctimeNs}`;
    } catch {
      return `${filePath}:missing`;
    }
  }).join("|");
}

/**
 * Return the canonical route/source manifest. Production keeps one
 * process-lifetime snapshot; development checks only known source metadata and
 * rebuilds the graph when SUMMARY or a linked source changes.
 */
export function getDocsPublicationManifest(
  repoRoot = process.cwd(),
): DocsPublicationManifest {
  const resolvedRoot = path.resolve(repoRoot);
  const cached = cachedDocsPublicationManifest;

  if (cached?.manifest.repoRoot === resolvedRoot) {
    if (process.env.NODE_ENV !== "development") return cached.manifest;
    if (getSourceSignature(cached.watchPaths) === cached.sourceSignature) {
      return cached.manifest;
    }
  }

  const built = buildDocsPublicationManifest(resolvedRoot);
  cachedDocsPublicationManifest = {
    ...built,
    sourceSignature: getSourceSignature(built.watchPaths),
  };
  return built.manifest;
}

export function invalidateDocsPublicationManifest(): void {
  cachedDocsPublicationManifest = null;
}

export function getPublishedDocs(): PublishedDoc[] {
  return [...getDocsPublicationManifest().docs];
}

export function getPublishedDocRoutes(): Set<string> {
  return new Set(getDocsPublicationManifest().docRoutes);
}

export function getPublishedDoc(route: string): PublishedDoc | null {
  return getDocsPublicationManifest().byRoute.get(route) ?? null;
}

export function canonicalizeDocsRoute(route: string): string {
  if (route === "/docs") return route;

  const segments = route.replace(/^\/docs\/?/, "").split("/").filter(Boolean);
  while (segments.length > 0 && /^(README|index)$/i.test(segments[segments.length - 1])) {
    segments.pop();
  }

  if (segments[0]?.toLowerCase() === "api") {
    segments.splice(0, 1, "reference");
  }
  if (segments.join("/").toLowerCase() === "reference/reference") {
    segments.pop();
  }
  if (segments.join("/").toLowerCase() === "sdk") return "/sdk";

  return segments.length > 0 ? `/docs/${segments.join("/")}` : "/docs";
}

export interface PublishedDocRequest {
  requestedRoute: string;
  canonicalRoute: string;
  doc: PublishedDoc;
  shouldRedirect: boolean;
}

export function resolvePublishedDocRequest(slugSegments: string[]): PublishedDocRequest | null {
  if (slugSegments.some((segment) => (
    !segment || segment === "." || segment === ".." || segment.includes("/") ||
    segment.includes("\\") || segment.includes("\0")
  ))) return null;

  const requestedRoute = slugSegments.length > 0
    ? `/docs/${slugSegments.join("/")}`
    : "/docs";
  const canonicalRoute = canonicalizeDocsRoute(requestedRoute);
  const doc = getPublishedDoc(canonicalRoute);
  if (!doc) return null;

  return {
    requestedRoute,
    canonicalRoute,
    doc,
    shouldRedirect: requestedRoute !== canonicalRoute,
  };
}
