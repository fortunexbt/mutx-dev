import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { AnchorHTMLAttributes, ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const fetchLatestStableDesktopRelease = jest.fn()

jest.mock('../../lib/desktopRelease', () => ({
  MUTX_GITHUB_RELEASES_URL: 'https://github.com/mutx-dev/mutx-dev/releases',
  MUTX_RELEASE_NOTES_URL: 'https://mutx.dev/docs/releases/v1.4',
  buildDesktopArtifactName: (version: string, kind: string) => `MUTX-${version}-${kind}`,
  buildReleaseNotesUrl: (version: string) => `https://mutx.dev/docs/releases/v${version}`,
  fetchLatestStableDesktopRelease,
}))

type MockLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & {
  href: string
  children?: ReactNode
}

jest.mock('next/link', () => {
  const React = jest.requireActual<typeof import('react')>('react')

  return {
    __esModule: true,
    default: ({ href, children, ...props }: MockLinkProps) =>
      React.createElement('a', { ...props, href }, children),
  }
})

jest.mock('@/components/site/PublicNav', () => ({ PublicNav: () => null }))
jest.mock('@/components/site/PublicFooter', () => ({ PublicFooter: () => null }))
jest.mock('@/components/site/PublicSurface', () => ({
  PublicSurface: ({ children }: { children: ReactNode }) => children,
}))
jest.mock('@/components/site/marketing/OperationalVisual', () => ({
  OperationalVisual: () => null,
}))

const completeRelease = {
  tagName: 'v1.4.0',
  version: '1.4.0',
  htmlUrl: 'https://github.com/mutx-dev/mutx-dev/releases/tag/v1.4.0',
  assets: {
    arm64Dmg: 'https://github.com/mutx-dev/mutx-dev/releases/download/v1.4.0/MUTX-arm64.dmg',
    x64Dmg: 'https://github.com/mutx-dev/mutx-dev/releases/download/v1.4.0/MUTX-x64.dmg',
    arm64Zip: 'https://github.com/mutx-dev/mutx-dev/releases/download/v1.4.0/MUTX-arm64.zip',
    x64Zip: 'https://github.com/mutx-dev/mutx-dev/releases/download/v1.4.0/MUTX-x64.zip',
    checksums: 'https://github.com/mutx-dev/mutx-dev/releases/download/v1.4.0/SHA256SUMS.txt',
  },
}

function source(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

function expectNewTabLinksToBeSafeAndAnnounced(html: string) {
  const links = html.match(/<a\b(?=[^>]*target="_blank")[^>]*>[\s\S]*?<\/a>/g) ?? []

  expect(links.length).toBeGreaterThan(0)
  for (const link of links) {
    expect(link).toContain('rel="noopener noreferrer"')
    expect(link).toContain('(opens in a new tab)')
  }
}

describe('public interaction quality', () => {
  beforeEach(() => {
    fetchLatestStableDesktopRelease.mockReset().mockResolvedValue(completeRelease)
  })

  it('describes a complete release without treating asset presence as signing proof', async () => {
    const { default: MacDownloadPage } = await import('../../app/download/macos/page')
    const { default: ReleasesPage } = await import('../../app/releases/page')
    const downloadHtml = renderToStaticMarkup(await MacDownloadPage())
    const releasesHtml = renderToStaticMarkup(await ReleasesPage())

    expect(downloadHtml).toContain('Complete stable release:')
    expect(releasesHtml).toContain('Complete desktop release.')
    expect(`${downloadHtml}\n${releasesHtml}`).not.toMatch(/\b(?:signed|notarized)\b/i)

    const arm64Link = downloadHtml.match(
      new RegExp(`<a[^>]*href="${completeRelease.assets.arm64Dmg.replaceAll('.', '\\.') }"[^>]*>`),
    )?.[0]
    expect(arm64Link).toBeDefined()
    expect(arm64Link).not.toContain('target="_blank"')

    expectNewTabLinksToBeSafeAndAnnounced(downloadHtml)
    expectNewTabLinksToBeSafeAndAnnounced(releasesHtml)
  })

  it('keeps legal contact actionable and announces external docs navigation', async () => {
    const { default: PrivacyPolicyPage } = await import('../../app/privacy-policy/page')
    const privacyHtml = renderToStaticMarkup(<PrivacyPolicyPage />)
    const docsLayout = source('components/site/docs/DocsLayout.tsx')

    expect(privacyHtml).toContain('href="mailto:hello@mutx.dev"')
    expect(docsLayout.match(/\(opens in a new tab\)/g)).toHaveLength(2)
  })

  it('keeps recovery failures friendly when an endpoint does not return JSON', () => {
    for (const relativePath of [
      'components/pico/PicoForgotPasswordPageClient.tsx',
      'components/pico/PicoResetPasswordPageClient.tsx',
    ]) {
      const recoverySource = source(relativePath)

      expect(recoverySource).toContain('.json().catch(() => null)')
      expect(recoverySource).toContain('aria-busy={loading}')
      expect(recoverySource).not.toContain("err instanceof Error ? err.message")
    }
  })
})
