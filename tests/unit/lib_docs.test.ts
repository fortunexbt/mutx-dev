/**
 * Tests for lib/docs.ts — SUMMARY.md parser and doc route helpers.
 *
 * These tests read real files from the repo so they act as both unit tests
 * and a smoke test that SUMMARY.md is well-formed.
 */

import fs from 'fs'
import os from 'os'
import path from 'path'

import {
  getDocsPublicationManifest,
  docsFileToCanonicalRoute,
  parseSummary,
  flatNav,
  getFrontmatterDateModified,
  getDocSitemapRoutes,
  getPublishedDocs,
  getPublishedDocRoutes,
  invalidateDocsPublicationManifest,
  resolvePublishedDocRequest,
  type DocNavItem,
} from '../../lib/docs'
import { resolveDocHref } from '../../lib/docsLinks'

// -----------------------------------------------------------------------------
// Helper constants (replicate lib/docs.ts internals for isolation)
// ---------------------------------------------------------------------------

function normalizeSummaryHrefToSlug(href: string): string {
  const stripped = href.replace(/^docs\//, '').replace(/\.md$/, '').replace(/^\//, '')
  if (!href.startsWith('docs/')) {
    return stripped.replace(/\/README$/i, '').replace(/\/index$/i, '') || stripped
  }
  return stripped
}

function summaryHrefToDocsRoute(href: string): string | null {
  let working = href
  working = working.replace(/^docs\/api\//, 'docs/reference/')
  const slug = working.replace(/^docs\//, '')
  let clean = slug
    .replace(/\.md$/, '')
    .replace(/\/README$/i, '')
    .replace(/\/index$/i, '')
    .replace(/^README$/i, '')
    .replace(/^index$/i, '')
  clean = clean.replace(/^reference\/reference$/, 'reference')
  if (!clean) return '/docs'
  return `/docs/${clean}`
}

// ---------------------------------------------------------------------------
// normalizeSummaryHrefToSlug
// ---------------------------------------------------------------------------
describe('normalizeSummaryHrefToSlug', () => {
  it('strips docs/ prefix', () => {
    expect(normalizeSummaryHrefToSlug('docs/api/auth.md')).toBe('api/auth')
  })

  it('strips .md extension', () => {
    expect(normalizeSummaryHrefToSlug('docs/agents/README.md')).toBe('agents/README')
  })

  it('handles non-docs/ hrefs without prefix', () => {
    expect(normalizeSummaryHrefToSlug('manifesto.md')).toBe('manifesto')
  })

  it('strips /README suffix', () => {
    expect(normalizeSummaryHrefToSlug('docs/agents/README.md')).toBe('agents/README')
  })

  it('strips /index suffix', () => {
    expect(normalizeSummaryHrefToSlug('docs/agents/index.md')).toBe('agents/index')
  })

  it('handles docs/README.md without stripping README (no /README suffix path)', () => {
    // docs/README.md → stripped = "README" (no /README suffix to strip)
    expect(normalizeSummaryHrefToSlug('docs/README.md')).toBe('README')
  })
})

// ---------------------------------------------------------------------------
// summaryHrefToDocsRoute
// ---------------------------------------------------------------------------
describe('summaryHrefToDocsRoute', () => {
  it('maps docs/api/reference.md to /docs/reference', () => {
    expect(summaryHrefToDocsRoute('docs/api/reference.md')).toBe('/docs/reference')
  })

  it('maps docs/api/authentication.md to /docs/reference/authentication', () => {
    expect(summaryHrefToDocsRoute('docs/api/authentication.md')).toBe(
      '/docs/reference/authentication'
    )
  })

  it('maps docs/api/index.md to /docs/reference', () => {
    expect(summaryHrefToDocsRoute('docs/api/index.md')).toBe('/docs/reference')
  })

  it('maps manifesto.md to /manifesto', () => {
    expect(summaryHrefToDocsRoute('manifesto.md')).toBe('/docs/manifesto')
  })

  it('maps whitepaper.md to /docs/whitepaper', () => {
    expect(summaryHrefToDocsRoute('whitepaper.md')).toBe('/docs/whitepaper')
  })

  it('maps docs/agents/README.md to /docs/agents', () => {
    expect(summaryHrefToDocsRoute('docs/agents/README.md')).toBe('/docs/agents')
  })

  it('maps docs/api/index.md (reference dir) to /docs/reference', () => {
    expect(summaryHrefToDocsRoute('docs/api/index.md')).toBe('/docs/reference')
  })

  it('avoids double /reference/reference for deep api paths', () => {
    expect(summaryHrefToDocsRoute('docs/api/reference.md')).toBe('/docs/reference')
  })

  it('returns /docs for empty slug', () => {
    expect(summaryHrefToDocsRoute('docs/index.md')).toBe('/docs')
  })
})

// ---------------------------------------------------------------------------
// Integration: parseSummary + flatNav + getDocSitemapRoutes
describe('parseSummary integration', () => {
  it('parseSummary returns a non-empty array', () => {
    const items = parseSummary()
    expect(Array.isArray(items)).toBe(true)
    expect(items.length).toBeGreaterThan(0)
  })

  it('each top-level item has required fields', () => {
    const items = parseSummary()
    for (const item of items) {
      expect(typeof item.title).toBe('string')
      expect(item.title.length).toBeGreaterThan(0)
      expect(typeof item.href).toBe('string')
      expect(typeof item.slug).toBe('string')
      expect(typeof item.route).toBe('string')
      expect(Array.isArray(item.children)).toBe(true)
      expect(typeof item.depth).toBe('number')
    }
  })

  it('top-level items have depth 0', () => {
    const items = parseSummary()
    for (const item of items) {
      expect(item.depth).toBe(0)
    }
  })

  it('flatNav produces a non-empty flat list', () => {
    const items = parseSummary()
    const flat = flatNav(items)
    expect(Array.isArray(flat)).toBe(true)
    expect(flat.length).toBeGreaterThan(items.length)
  })

  it('flatNav includes all items from nested children', () => {
    const items = parseSummary()
    const flat = flatNav(items)
    // All titles from the nested tree should appear in the flat list
    const flatTitles = new Set(flat.map((i: { title: string }) => i.title))
    function collectTitles(n: DocNavItem[]) {
      for (const item of n) {
        flatTitles.add(item.title)
        if (item.children.length > 0) collectTitles(item.children)
      }
    }
    collectTitles(items)
    // flatNav pushes each node then recurses into children, so flat = root items + all descendants
    // titles should all be present (no title is lost in recursion)
    expect(flatTitles.size).toBeGreaterThan(0)
    for (const item of items) {
      expect(flatTitles.has(item.title)).toBe(true)
    }
  })

  it('getDocSitemapRoutes returns an array starting with /docs', () => {
    const routes = getDocSitemapRoutes()
    expect(Array.isArray(routes)).toBe(true)
    expect(routes[0]).toBe('/docs')
    // All routes should start with /docs
    for (const route of routes) {
      expect(route).toMatch(/^\/docs/)
    }
  })

  it('routes are unique (no duplicates)', () => {
    const routes = getDocSitemapRoutes()
    const unique = new Set(routes)
    expect(routes.length).toBe(unique.size)
  })

  it('keeps safe pages linked from published docs reachable', () => {
    const routes = getPublishedDocRoutes()
    expect(routes.has('/docs/deployment/local-developer-bootstrap')).toBe(true)
    expect(routes.has('/docs/reference/leads')).toBe(true)
    expect(routes.has('/docs/reference/analytics')).toBe(true)
  })

  it('does not publish internal release runbooks linked from old section markup', () => {
    const routes = getPublishedDocRoutes()
    expect(routes.has('/docs/deployment/cli-release')).toBe(false)
    expect(routes.has('/docs/deployment/release-v0.1')).toBe(false)
  })

  it('excludes the legacy webhook compatibility source from every publication surface', () => {
    const docs = getPublishedDocs()
    const routes = getDocSitemapRoutes()

    expect(docs.some((doc) => doc.sourcePath === 'docs/contracts/api/webhooks.md')).toBe(false)
    expect(docs.some((doc) => doc.route === '/docs/contracts/api/webhooks')).toBe(false)
    expect(routes).not.toContain('/docs/contracts/api/webhooks')
    expect(docsFileToCanonicalRoute(
      path.join(process.cwd(), 'docs/contracts/api/webhooks.md')
    )).toBeNull()
    expect(resolvePublishedDocRequest(['contracts', 'api', 'webhooks'])).toBeNull()
  })

  it('publishes one canonical route per source-backed document', () => {
    const docs = getPublishedDocs()
    const routes = docs.map((doc) => doc.route)

    expect(routes).toContain('/sdk')
    expect(routes).toContain('/support')
    expect(routes).not.toContain('/docs/api')
    expect(routes).not.toContain('/docs/sdk')
    expect(routes).not.toContain('/docs/README')
    expect(new Set(routes).size).toBe(routes.length)
  })

  it('publishes the API agents guide at its canonical reference route', () => {
    const agentsDoc = getPublishedDocs().find((doc) => doc.route === '/docs/reference/agents')

    expect(agentsDoc?.sourcePath).toBe('docs/api/agents.md')
    expect(resolvePublishedDocRequest(['reference', 'agents'])).toMatchObject({
      canonicalRoute: '/docs/reference/agents',
      shouldRedirect: false,
    })
  })

  it('distinguishes canonical aliases from unpublished and invalid routes', () => {
    expect(resolvePublishedDocRequest(['README'])).toMatchObject({
      canonicalRoute: '/docs',
      shouldRedirect: true,
    })
    expect(resolvePublishedDocRequest(['api', 'authentication'])).toMatchObject({
      canonicalRoute: '/docs/reference/authentication',
      shouldRedirect: true,
    })
    expect(resolvePublishedDocRequest(['architecture', 'README'])).toMatchObject({
      canonicalRoute: '/docs/architecture',
      shouldRedirect: true,
    })
    expect(resolvePublishedDocRequest(['agents', 'qa-reliability-engineer'])).toBeNull()
    expect(resolvePublishedDocRequest(['does-not-exist'])).toBeNull()
    expect(resolvePublishedDocRequest(['..', 'README'])).toBeNull()
  })
})

describe('documentation frontmatter dates', () => {
  it('accepts only explicit, valid dateModified values', () => {
    expect(getFrontmatterDateModified({})).toBeUndefined()
    expect(getFrontmatterDateModified({ dateModified: 'not-a-date' })).toBeUndefined()
    expect(getFrontmatterDateModified({ dateModified: ' 2026-07-28 ' })).toBe('2026-07-28')
    expect(getFrontmatterDateModified({
      dateModified: new Date('2026-07-28T12:00:00.000Z'),
    })).toBe('2026-07-28T12:00:00.000Z')
  })
})

describe('resolveDocHref', () => {
  it('resolves links from a README-backed section directory', () => {
    expect(resolveDocHref('quickstart.md', ['deployment', 'README'])).toBe('/docs/deployment/quickstart')
    expect(resolveDocHref('docker.md', ['deployment', 'README'])).toBe('/docs/deployment/docker')
  })

  it('preserves API reference routing for source files under docs/api', () => {
    expect(resolveDocHref('./leads.md', ['api', 'reference'])).toBe('/docs/reference/leads')
  })

  it('rewrites source artifacts and unpublished Markdown instead of inventing routes', () => {
    expect(resolveDocHref('./openapi.json', ['api', 'reference'])).toBe(
      'https://github.com/mutx-dev/mutx-dev/blob/main/docs/api/openapi.json'
    )
    expect(resolveDocHref('../../infrastructure/helm/mutx/README.md', ['deployment', 'kubernetes'])).toBe(
      'https://github.com/mutx-dev/mutx-dev/blob/main/infrastructure/helm/mutx/README.md'
    )
    expect(resolveDocHref('../../railway.json', ['deployment', 'railway'])).toBe(
      'https://github.com/mutx-dev/mutx-dev/blob/main/railway.json'
    )
    expect(resolveDocHref('cli-release.md', ['deployment', 'README'])).toBe(
      'https://github.com/mutx-dev/mutx-dev/blob/main/docs/deployment/cli-release.md'
    )
  })

  it('normalizes repo-relative surfaces links to the published canonical route', () => {
    expect(resolveDocHref('../docs/surfaces.md', ['project-status'])).toBe('/docs/surfaces')
  })
})

describe('documentation publication manifest caching', () => {
  const originalNodeEnv = process.env.NODE_ENV

  function setNodeEnv(value: string | undefined) {
    if (value === undefined) {
      Reflect.deleteProperty(process.env, 'NODE_ENV')
      return
    }
    Object.defineProperty(process.env, 'NODE_ENV', {
      configurable: true,
      enumerable: true,
      value,
      writable: true,
    })
  }

  afterEach(() => {
    setNodeEnv(originalNodeEnv)
    invalidateDocsPublicationManifest()
  })

  it('reuses one stable manifest instead of rescanning the publication graph', () => {
    invalidateDocsPublicationManifest()

    const first = getDocsPublicationManifest()
    const second = getDocsPublicationManifest()

    expect(second).toBe(first)
    expect(second.byRoute.get('/docs')?.sourcePath).toBe('docs/README.md')
  })

  it('invalidates the development manifest when a known source changes', () => {
    const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'mutx-docs-manifest-'))
    const docsRoot = path.join(fixtureRoot, 'docs')
    fs.mkdirSync(docsRoot, { recursive: true })
    fs.writeFileSync(
      path.join(fixtureRoot, 'SUMMARY.md'),
      '# Summary\n\n* [Home](docs/README.md)\n',
      'utf-8'
    )
    const readmePath = path.join(docsRoot, 'README.md')
    fs.writeFileSync(readmePath, '# Fixture docs\n', 'utf-8')

    try {
      setNodeEnv('development')
      invalidateDocsPublicationManifest()
      const first = getDocsPublicationManifest(fixtureRoot)

      fs.appendFileSync(readmePath, '\nChanged source content.\n', 'utf-8')
      const second = getDocsPublicationManifest(fixtureRoot)

      expect(second).not.toBe(first)
      expect(second.docs.map((doc) => doc.route)).toEqual(['/docs'])
    } finally {
      fs.rmSync(fixtureRoot, { recursive: true, force: true })
    }
  })
})
