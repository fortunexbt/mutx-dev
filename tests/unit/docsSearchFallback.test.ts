jest.mock('@/lib/docs/searchIndex', () => ({
  createDocsSearchIndex: jest.fn(),
}))

import { GET } from '../../app/docs/search-index.json/route'
import { createDocsSearchIndex } from '../../lib/docs/searchIndex'
import {
  loadDocsSearchEntries,
  type DocsSearchIndex,
} from '../../lib/docs/search'

const searchIndex: DocsSearchIndex = {
  version: 1,
  routes: ['/docs'],
  documents: [
    {
      title: 'MUTX Docs',
      href: '/docs',
      section: 'Docs',
      entries: [
        {
          id: '/docs',
          title: 'MUTX Docs',
          section: 'Docs',
          content: 'Operator manual',
          href: '/docs',
          headings: [],
        },
      ],
    },
  ],
}

const mockCreateDocsSearchIndex = jest.mocked(createDocsSearchIndex)

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

describe('documentation search fallback', () => {
  const originalNodeEnv = process.env.NODE_ENV

  afterEach(() => {
    setNodeEnv(originalNodeEnv)
    mockCreateDocsSearchIndex.mockReset()
  })

  it('loads the canonical dynamic fallback only after a missing static asset', async () => {
    const requests: string[] = []
    const entries = await loadDocsSearchEntries(async (input) => {
      requests.push(input)
      if (input === '/docs-search-index.json') {
        return { ok: false, status: 404, json: async () => ({}) }
      }
      return { ok: true, status: 200, json: async () => searchIndex }
    })

    expect(requests).toEqual(['/docs-search-index.json', '/docs/search-index.json'])
    expect(entries).toEqual(searchIndex.documents[0].entries)
  })

  it('serves a fresh no-store index in development', async () => {
    setNodeEnv('development')
    mockCreateDocsSearchIndex.mockReturnValue(searchIndex)

    const response = GET()

    expect(response.status).toBe(200)
    expect(response.headers.get('cache-control')).toBe('no-store')
    await expect(response.json()).resolves.toEqual(searchIndex)
    expect(mockCreateDocsSearchIndex).toHaveBeenCalledTimes(1)
  })

  it('does not expose the dynamic builder in production', () => {
    setNodeEnv('production')

    const response = GET()

    expect(response.status).toBe(404)
    expect(response.headers.get('cache-control')).toBe('no-store')
    expect(mockCreateDocsSearchIndex).not.toHaveBeenCalled()
  })
})
