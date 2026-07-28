export interface DocsSearchEntry {
  id: string;
  title: string;
  section: string;
  content: string;
  href: string;
  headings: string[];
}

export interface DocsSearchDocument {
  title: string;
  href: string;
  section: string;
  entries: DocsSearchEntry[];
}

export interface DocsSearchIndex {
  version: 1;
  routes: string[];
  documents: DocsSearchDocument[];
}

interface SearchIndexResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

export type SearchIndexFetcher = (input: string) => Promise<SearchIndexResponse>;

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isCanonicalSearchRoute(route: string): boolean {
  return route === "/docs" || route.startsWith("/docs/") || route === "/sdk" || route === "/support";
}

export function parseDocsSearchIndex(value: unknown): DocsSearchIndex {
  if (!value || typeof value !== "object") throw new Error("Invalid documentation search index");
  const candidate = value as Partial<DocsSearchIndex>;
  if (candidate.version !== 1 || !Array.isArray(candidate.routes) || !Array.isArray(candidate.documents)) {
    throw new Error("Unsupported documentation search index");
  }

  const routes = candidate.routes;
  if (!routes.every(isString) || new Set(routes).size !== routes.length || !routes.every(isCanonicalSearchRoute)) {
    throw new Error("Invalid documentation search routes");
  }
  if (candidate.documents.length !== routes.length) {
    throw new Error("Documentation search publication mismatch");
  }

  const routeSet = new Set(routes);
  const documentRoutes = new Set<string>();
  for (const document of candidate.documents) {
    if (!document || typeof document !== "object") throw new Error("Invalid documentation search document");
    if (
      !isString(document.title) || !isString(document.href) || !isString(document.section) ||
      !routeSet.has(document.href) || !Array.isArray(document.entries)
    ) {
      throw new Error("Invalid documentation search document");
    }
    if (documentRoutes.has(document.href)) throw new Error("Duplicate documentation search document");
    documentRoutes.add(document.href);

    for (const entry of document.entries) {
      if (
        !entry || typeof entry !== "object" || !isString(entry.id) || !isString(entry.title) ||
        !isString(entry.section) || !isString(entry.content) || !isString(entry.href) ||
        !Array.isArray(entry.headings) || !entry.headings.every(isString) ||
        (entry.href !== document.href && !entry.href.startsWith(`${document.href}#`))
      ) {
        throw new Error("Invalid documentation search entry");
      }
    }
  }
  if (documentRoutes.size !== routeSet.size) throw new Error("Documentation search publication mismatch");

  return candidate as DocsSearchIndex;
}

export function flattenDocsSearchEntries(index: DocsSearchIndex): DocsSearchEntry[] {
  return index.documents.flatMap((document) => (
    document.entries.map((entry) => ({ ...entry, section: document.section }))
  ));
}

export async function loadDocsSearchEntries(
  fetcher: SearchIndexFetcher = fetch,
): Promise<DocsSearchEntry[]> {
  let response = await fetcher("/docs-search-index.json");
  if (!response.ok && response.status === 404) {
    response = await fetcher("/docs/search-index.json");
  }
  if (!response.ok) {
    throw new Error(`Documentation search index request failed (${response.status})`);
  }
  return flattenDocsSearchEntries(parseDocsSearchIndex(await response.json()));
}
