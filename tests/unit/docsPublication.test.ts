import fs from 'fs'
import { execFileSync } from 'node:child_process'
import path from 'path'
import { pathToFileURL } from 'node:url'

import { getPublishedDocs, resolvePublishedDocRequest } from '../../lib/docs'
import { preprocessGitBookMarkdown } from '../../lib/docs/hints'
import { resolveDocAssetHref, resolveDocHref } from '../../lib/docsLinks'
import {
  type DocsSearchEntry,
  type DocsSearchIndex,
  loadDocsSearchEntries,
  parseDocsSearchIndex,
} from '../../lib/docs/search'

const searchIndexModuleUrl = pathToFileURL(
  path.join(process.cwd(), 'lib/docs/searchIndex.ts')
).href

function runSearchIndexModule<T>(body: string): T {
  const output = execFileSync(process.execPath, [
    '--experimental-strip-types',
    '--input-type=module',
    '--eval',
    `import { createDocsSearchHeadingEntries, createDocsSearchIndex } from ${JSON.stringify(searchIndexModuleUrl)}; ${body}`,
  ], {
    cwd: process.cwd(),
    encoding: 'utf-8',
  })

  return JSON.parse(output) as T
}

function createSearchIndexes(): { first: DocsSearchIndex; second: DocsSearchIndex } {
  return runSearchIndexModule(
    'const first = createDocsSearchIndex(); const second = createDocsSearchIndex(); process.stdout.write(JSON.stringify({ first, second }));'
  )
}

function createSearchHeadingEntries(markdown: string): DocsSearchEntry[] {
  return runSearchIndexModule(
    `process.stdout.write(JSON.stringify(createDocsSearchHeadingEntries(${JSON.stringify(markdown)}, '/docs/example', 'Example')));`
  )
}

describe('deterministic docs publication', () => {
  it('keeps the publication manifest and search index in exact route parity', () => {
    const publicationRoutes = getPublishedDocs().map((doc) => doc.route)
    const { first, second } = createSearchIndexes()

    expect(first.routes).toEqual(publicationRoutes)
    expect(first.documents.map((document) => document.href)).toEqual(publicationRoutes)
    expect(JSON.stringify(first)).toBe(JSON.stringify(second))
    expect(first.routes).not.toContain('/docs/MIGRATION_RUNBOOK')
    expect(first.routes).not.toContain('/docs/deployment/cli-release')
    expect(first.routes).not.toContain('/docs/contracts/api/webhooks')
    expect(first.routes).toContain('/docs/reference/agents')
    expect(first.documents.find((document) => document.href === '/docs/reference/agents')).toBeDefined()
    for (const doc of getPublishedDocs().filter((item) => item.route.startsWith('/docs'))) {
      const slug = doc.route === '/docs' ? [] : doc.route.slice('/docs/'.length).split('/')
      expect(resolvePublishedDocRequest(slug)?.doc.sourcePath).toBe(doc.sourcePath)
    }
    expect(first.documents.every((document) => (
      document.entries.every((entry) => (
        entry.href === document.href || entry.href.startsWith(`${document.href}#`)
      ))
    ))).toBe(true)
  })

  it('uses rendered GitHub heading IDs for punctuation, Unicode, and collisions', () => {
    const entries = createSearchHeadingEntries([
      '# Search anchors',
      '## C++ & Rust—naïve_日本語!',
      'First section.',
      '## C++ & Rust—naïve_日本語!',
      'Duplicate section.',
      '## c--rustnaïve_日本語-1',
      'Colliding suffix.',
      '## C++ & Rust—naïve_日本語!',
      'Third duplicate.',
      '##### Hidden depth',
      '#### Hidden depth',
    ].join('\n'))

    expect(entries.map((entry) => entry.href)).toEqual([
      '/docs/example#search-anchors',
      '/docs/example#c--rustnaïve_日本語',
      '/docs/example#c--rustnaïve_日本語-1',
      '/docs/example#c--rustnaïve_日本語-1-1',
      '/docs/example#c--rustnaïve_日本語-2',
      '/docs/example#hidden-depth-1',
    ])
    expect(entries[1].title).toBe('C++ & Rust—naïve_日本語!')
  })

  it('rewrites every published Markdown link away from rejected docs routes', () => {
    const publication = getPublishedDocs()
    const routeSet = new Set(publication.map((doc) => doc.route))

    for (const doc of publication) {
      const source = fs.readFileSync(doc.filePath, 'utf-8')
      const hrefs = [
        ...source.matchAll(/\[[^\]]*\]\(([^)]+)\)/g),
        ...source.matchAll(/href=["']([^"']+)["']/gi),
      ].map((match) => match[1])
      const currentSlug = doc.sourcePath.startsWith('docs/')
        ? doc.sourcePath.slice('docs/'.length).replace(/\.md$/i, '').split('/')
        : [doc.sourcePath.replace(/\.md$/i, '')]

      for (const href of hrefs) {
        const resolved = resolveDocHref(href, currentSlug)
        if (resolved === '/docs' || resolved.startsWith('/docs/')) {
          const route = resolved.split('#', 1)[0].split('?', 1)[0]
          if (!routeSet.has(route)) {
            throw new Error(`${doc.sourcePath}: ${href} resolved to unpublished ${route}`)
          }
        }
        if (!/^[a-z][a-z0-9+.-]*:/i.test(resolved)) {
          expect(resolved).not.toMatch(/\.md(?:$|[?#])/i)
        }
      }
    }
  })

  it('rejects failed requests and index entries outside their published document', async () => {
    await expect(loadDocsSearchEntries(async () => ({
      ok: false,
      status: 503,
      json: async () => ({}),
    }))).rejects.toThrow('request failed (503)')

    const { first: index } = createSearchIndexes()
    const tampered = structuredClone(index)
    tampered.documents[0].entries[0].href = '/docs/not-published'
    expect(() => parseDocsSearchIndex(tampered)).toThrow('Invalid documentation search entry')
  })

  it('preserves allowlisted hint and card semantics while dropping unsafe card HTML', () => {
    const source = [
      '{% hint style="warning" %}',
      'Keep **backups** and read [setup](./quickstart.md).',
      '{% endhint %}',
      '',
      '<table data-view="cards"><thead><tr><th>Title</th><th>Description</th><th data-card-target>Target</th><th data-card-cover>Cover</th></tr></thead><tbody><tr><td><strong>Setup &amp;lt;safe&amp;gt;</strong><script>alert(1)</script></td><td>Safe path</td><td><a href="./quickstart.md" onclick="alert(1)">quickstart.md</a></td><td><img src="../../public/landing/victory-core.png" onerror="alert(1)"></td></tr></tbody></table>',
      '',
      '<script>alert("raw")</script>',
    ].join('\n')

    const preprocessed = preprocessGitBookMarkdown(source)
    const rendererSource = fs.readFileSync(
      path.join(process.cwd(), 'components/site/docs/DocsRenderer.tsx'),
      'utf-8'
    )

    expect(preprocessed).toContain('> [!WARNING]')
    expect(preprocessed).toContain('> Keep **backups** and read [setup](./quickstart.md).')
    expect(preprocessed).toContain('| __MUTX_DOCS_CARD_TABLE__ | Description | Target | Cover |')
    expect(preprocessed).toContain('[quickstart.md](./quickstart.md)')
    expect(preprocessed).toContain('Setup &lt;safe&gt;')
    expect(preprocessed).not.toContain('Setup <safe>')
    expect(preprocessed).not.toContain('<table')
    expect(preprocessed).not.toContain('onclick')
    expect(preprocessed).not.toContain('onerror')
    expect(preprocessed).not.toContain('alert(1)')
    expect(resolveDocHref('./quickstart.md', ['deployment', 'README'])).toBe(
      '/docs/deployment/quickstart'
    )
    expect(resolveDocAssetHref('../../public/landing/victory-core.png', ['deployment', 'README'])).toBe(
      '/landing/victory-core.png'
    )
    expect(rendererSource).toContain('.use(remarkDecorateGitBookBlocks)')
    expect(rendererSource).toContain('allowDangerousHtml: false')
    expect(rendererSource).toContain('.use(rehypeSanitize, docsSchema)')
  })

  it('sequences deterministic search generation before the production compiler', () => {
    const packageJson = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf-8'))
    const build = packageJson.scripts.build as string

    expect(build).toBe('npm run build:docs-search && next build --webpack')
    expect(packageJson.scripts['build:docs-search']).toBe(
      'node --experimental-strip-types scripts/build-docs-search-index.ts'
    )
    expect(build.indexOf('build:docs-search')).toBeLessThan(build.indexOf('next build'))
  })

  it('keeps local bootstrap requirements synchronized with npm and its lockfile', () => {
    const packageJson = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf-8'))
    const packageLock = JSON.parse(
      fs.readFileSync(path.join(process.cwd(), 'package-lock.json'), 'utf-8')
    )
    const bootstrap = fs.readFileSync(
      path.join(process.cwd(), 'docs/deployment/local-developer-bootstrap.md'),
      'utf-8'
    )

    expect(packageLock.lockfileVersion).toBe(3)
    expect(packageLock.packages[''].engines).toEqual(packageJson.engines)
    expect(bootstrap).toContain(`* Node.js \`${packageJson.engines.node}\``)
    expect(bootstrap).toContain(`* npm \`${packageJson.engines.npm}\``)
    expect(bootstrap).toContain(`\`${packageJson.packageManager}\``)
    expect(bootstrap).toContain('package-lock.json')
    expect(bootstrap).toContain('npm ci --legacy-peer-deps')
    expect(bootstrap).not.toMatch(/\bpnpm\b/i)
  })

  it('describes MUTX core as source-available under BUSL', () => {
    const manifesto = fs.readFileSync(
      path.join(process.cwd(), 'docs/manifesto.md'),
      'utf-8'
    )

    expect(manifesto).toContain('source-available under the Business Source License (BUSL-1.1)')
    expect(manifesto).not.toMatch(/\bopen[ -]source\b/i)
  })

  it('keeps search failure visible instead of swallowing it', () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), 'components/site/docs/DocsSearch.tsx'),
      'utf-8'
    )

    expect(source).toContain("setSearchStatus('error')")
    expect(source).toContain("(q || searchStatus === 'error')")
    expect(source).toContain('Documentation search is unavailable.')
    expect(source).not.toContain('.catch(() => {})')
  })
})
