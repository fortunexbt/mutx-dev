import { execFileSync } from 'node:child_process'
import path from 'path'
import { pathToFileURL } from 'node:url'
import { renderToStaticMarkup } from 'react-dom/server'

const notFound = jest.fn(() => {
  throw new Error('NEXT_NOT_FOUND')
})
const redirect = jest.fn((href: string) => {
  throw new Error(`NEXT_REDIRECT:${href}`)
})

jest.mock('next/navigation', () => ({ notFound, redirect }))
jest.mock('@/components/site/docs/DocsRenderer', () => ({
  DocsRenderer: jest.fn(),
  extractHeadings: jest.fn(() => []),
}))

import DocPage, { generateMetadata } from '../../app/docs/[[...slug]]/page'

function getDocsHomeSearchAnchors(): string[] {
  const moduleUrl = pathToFileURL(
    path.join(process.cwd(), 'lib/docs/searchIndex.ts')
  ).href
  const output = execFileSync(process.execPath, [
    '--experimental-strip-types',
    '--input-type=module',
    '--eval',
    `import { createDocsSearchIndex } from ${JSON.stringify(moduleUrl)}; const home = createDocsSearchIndex().documents.find((document) => document.href === '/docs'); process.stdout.write(JSON.stringify(home.entries.filter((entry) => entry.href.includes('#')).map((entry) => entry.href.split('#', 2)[1])));`,
  ], {
    cwd: process.cwd(),
    encoding: 'utf-8',
  })

  return JSON.parse(output) as string[]
}

describe('docs page publication boundary', () => {
  beforeEach(() => {
    notFound.mockClear()
    redirect.mockClear()
  })

  it('returns an honest not-found result for invalid and unpublished slugs', async () => {
    await expect(DocPage({
      params: Promise.resolve({ slug: ['agents', 'qa-reliability-engineer'] }),
    })).rejects.toThrow('NEXT_NOT_FOUND')

    expect(notFound).toHaveBeenCalledTimes(1)
    expect(redirect).not.toHaveBeenCalled()
    await expect(generateMetadata({
      params: Promise.resolve({ slug: ['not-a-real-page'] }),
    })).resolves.toEqual({ title: 'Not Found' })
  })

  it('redirects duplicate and legacy aliases to their canonical published route', async () => {
    await expect(DocPage({
      params: Promise.resolve({ slug: ['README'] }),
    })).rejects.toThrow('NEXT_REDIRECT:/docs')
    await expect(DocPage({
      params: Promise.resolve({ slug: ['api', 'authentication'] }),
    })).rejects.toThrow('NEXT_REDIRECT:/docs/reference/authentication')

    expect(notFound).not.toHaveBeenCalled()
  })

  it('renders the public agents reference without inventing a modification date', async () => {
    const params = Promise.resolve({ slug: ['reference', 'agents'] })
    const html = renderToStaticMarkup(await DocPage({ params }))
    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: ['reference', 'agents'] }),
    })

    expect(html).toContain('application/ld+json')
    expect(html).not.toContain('dateModified')
    expect(metadata.alternates?.canonical).toBe('https://mutx.dev/docs/reference/agents')
    expect(notFound).not.toHaveBeenCalled()
    expect(redirect).not.toHaveBeenCalled()
  })

  it('renders every anchor emitted by the docs home search model', async () => {
    const html = renderToStaticMarkup(await DocPage({
      params: Promise.resolve({ slug: [] }),
    }))
    const searchAnchors = getDocsHomeSearchAnchors()

    expect(searchAnchors.length).toBeGreaterThan(0)
    for (const anchor of searchAnchors) {
      expect(html).toContain(`id="${anchor}"`)
    }
  })
})
