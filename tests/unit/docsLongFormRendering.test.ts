import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import ManifestoPage, { generateMetadata as generateManifestoMetadata } from '../../app/manifesto/page'
import RoadmapPage, { generateMetadata as generateRoadmapMetadata } from '../../app/roadmap/page'
import WhitepaperPage, { generateMetadata as generateWhitepaperMetadata } from '../../app/whitepaper/page'

jest.mock('fs', () => ({
  readFileSync: jest.fn((filePath: string) => filePath),
}))

jest.mock('path', () => ({
  join: jest.fn((...parts: string[]) => parts.join('/')),
}))

jest.mock('gray-matter', () =>
  jest.fn((source: string) => {
    const slug = source.match(/(manifesto|roadmap|whitepaper)\.md$/)?.[1] ?? 'document'
    const title = slug.charAt(0).toUpperCase() + slug.slice(1)

    return {
      data: {
        title,
        description: `${title} evidence record.`,
      },
      content: `# ${title}\n\n**Rendered through the safe docs pipeline.**`,
    }
  })
)

jest.mock('@/components/site/docs/DocsLayout', () => {
  const React = jest.requireActual<typeof import('react')>('react')

  return {
    DocsLayout: ({ children }: { children: ReactNode }) =>
      React.createElement('div', { 'data-docs-layout': 'true' }, children),
  }
})

jest.mock('@/components/site/docs/DocsRenderer', () => {
  const React = jest.requireActual<typeof import('react')>('react')

  return {
    DocsRenderer: ({ source, currentSlug }: { source: string; currentSlug: string[] }) =>
      React.createElement(
        'article',
        { 'data-safe-docs-renderer': currentSlug.join('/') },
        source
      ),
  }
})

const longFormPages = [
  {
    slug: 'manifesto',
    Page: ManifestoPage,
    generateMetadata: generateManifestoMetadata,
  },
  {
    slug: 'roadmap',
    Page: RoadmapPage,
    generateMetadata: generateRoadmapMetadata,
  },
  {
    slug: 'whitepaper',
    Page: WhitepaperPage,
    generateMetadata: generateWhitepaperMetadata,
  },
]

describe('public long-form rendering', () => {
  it.each(longFormPages)('renders /$slug through DocsRenderer', async ({ slug, Page }) => {
    const html = renderToStaticMarkup(await Page())

    expect(html).toContain(`data-safe-docs-renderer="${slug}"`)
    expect(html).toContain('Rendered through the safe docs pipeline.')
    expect(html).toContain('type="application/ld+json"')
  })

  it.each(longFormPages)(
    'preserves canonical metadata for /$slug',
    async ({ slug, generateMetadata }) => {
      const metadata = await generateMetadata()

      expect(metadata.title).toBe(`${slug.charAt(0).toUpperCase() + slug.slice(1)} — MUTX`)
      expect(metadata.alternates?.canonical).toBe(`https://mutx.dev/${slug}`)
    }
  )
})
