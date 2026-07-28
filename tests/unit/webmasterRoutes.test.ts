const mockHeaders = jest.fn(async () => new Headers({ host: 'mutx.dev' }))

jest.mock('next/headers', () => ({
  headers: mockHeaders,
}))

import manifest from '../../app/manifest'
import robots from '../../app/robots'
import sitemap from '../../app/sitemap'
import { BLOCKED_CRAWL_PREFIXES, PUBLIC_MARKETING_ROUTES } from '../../lib/seo'

describe('webmaster route contracts', () => {
  beforeEach(() => {
    mockHeaders.mockResolvedValue(new Headers({ host: 'mutx.dev' }))
  })

  it('robots.txt blocks intended private prefixes on the marketing host', async () => {
    const result = await robots()
    const firstRule = Array.isArray(result.rules) ? result.rules[0] : result.rules

    expect(firstRule).toBeDefined()
    expect(firstRule?.disallow).toEqual(expect.arrayContaining([...BLOCKED_CRAWL_PREFIXES]))
    expect(result.host).toBe('https://mutx.dev')
    expect(result.sitemap).toBe('https://mutx.dev/sitemap.xml')
  })

  it('robots.txt narrows app crawling to the public control surface', async () => {
    mockHeaders.mockResolvedValue(new Headers({ host: 'app.mutx.dev' }))

    const result = await robots()
    const firstRule = Array.isArray(result.rules) ? result.rules[0] : result.rules

    expect(firstRule).toEqual(
      expect.objectContaining({
        allow: ['/control', '/opengraph-image', '/twitter-image'],
        disallow: ['/'],
      }),
    )
    expect(result.host).toBe('https://app.mutx.dev')
    expect(result.sitemap).toBe('https://app.mutx.dev/sitemap.xml')
  })

  it('robots.txt keeps pico landing-only while excluding the old product lanes', async () => {
    mockHeaders.mockResolvedValue(new Headers({ host: 'pico.mutx.dev' }))

    const result = await robots()
    const firstRule = Array.isArray(result.rules) ? result.rules[0] : result.rules

    expect(firstRule?.allow).toEqual(['/', '/opengraph-image', '/twitter-image'])
    expect(firstRule?.disallow).toEqual(
      expect.arrayContaining([
        ...BLOCKED_CRAWL_PREFIXES.filter((prefix) => prefix !== '/onboarding'),
        '/academy',
        '/autopilot',
        '/build-ledger',
        '/pricing',
        '/support',
        '/tutor',
        '/start',
        '/wip',
        '/pico',
      ]),
    )
    expect(firstRule?.disallow).toContain('/onboarding')
    expect(result.host).toBe('https://pico.mutx.dev')
    expect(result.sitemap).toBe('https://pico.mutx.dev/sitemap.xml')
  })

  it('marketing sitemap includes public routes and excludes private surfaces', async () => {
    const result = await sitemap()
    const urls = result.map((entry) => entry.url)

    for (const route of PUBLIC_MARKETING_ROUTES) {
      expect(urls).toContain(`https://mutx.dev${route === '/' ? '' : route}`)
    }

    expect(urls).toContain('https://mutx.dev/docs')
    expect(urls).toContain('https://mutx.dev/docs/reference')
    expect(urls).not.toContain('https://mutx.dev/dashboard')
    expect(urls).not.toContain('https://mutx.dev/control')
    expect(urls).not.toContain('https://mutx.dev/login')
  })

  it.each([
    ['marketing', 'mutx.dev'],
    ['app', 'app.mutx.dev'],
    ['pico', 'pico.mutx.dev'],
  ])('does not invent request-time freshness for the %s sitemap', async (_surface, host) => {
    mockHeaders.mockResolvedValue(new Headers({ host }))

    const result = await sitemap()

    expect(result.length).toBeGreaterThan(0)
    for (const entry of result) {
      expect(entry).not.toHaveProperty('lastModified')
    }
  })

  it('app sitemap publishes only the control lane', async () => {
    mockHeaders.mockResolvedValue(new Headers({ host: 'app.mutx.dev' }))

    await expect(sitemap()).resolves.toEqual([
      expect.objectContaining({
        url: 'https://app.mutx.dev/control',
      }),
    ])
  })

  it('pico sitemap publishes only the landing page', async () => {
    mockHeaders.mockResolvedValue(new Headers({ host: 'pico.mutx.dev' }))

    const result = await sitemap()
    const urls = result.map((entry) => entry.url)

    expect(urls).toContain('https://pico.mutx.dev')
    expect(urls).toHaveLength(1)
    expect(urls).not.toContain('https://pico.mutx.dev/build-ledger')
    expect(urls).not.toContain('https://pico.mutx.dev/wip')
  })

  it('manifest exposes stable production metadata', () => {
    const result = manifest()

    expect(result.name).toBe('MUTX')
    expect(result.theme_color).toBe('#060810')
    expect(result.background_color).toBe('#060810')
    expect(result.start_url).toBe('/')
    expect(result.icons).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ src: '/android-chrome-192x192.png', sizes: '192x192' }),
        expect.objectContaining({ src: '/android-chrome-512x512.png', sizes: '512x512' }),
      ]),
    )
  })
})
