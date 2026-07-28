import type { AnchorHTMLAttributes, ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const fetchLatestStableDesktopRelease = jest.fn()

jest.mock('../../lib/desktopRelease', () => ({
  MUTX_GITHUB_RELEASES_URL: 'https://github.com/mutx-dev/mutx-dev/releases',
  MUTX_RELEASE_NOTES_URL: 'https://mutx.dev/docs/releases/v1.4',
  buildDesktopArtifactName: (version: string, kind: string) =>
    `unexpected-placeholder-${version}-${kind}`,
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

jest.mock('@/components/site/PublicNav', () => ({
  PublicNav: () => null,
}))

jest.mock('@/components/site/PublicFooter', () => ({
  PublicFooter: () => null,
}))

jest.mock('@/components/site/PublicSurface', () => ({
  PublicSurface: ({ children }: { children: ReactNode }) => children,
}))

jest.mock('@/components/site/marketing/OperationalVisual', () => ({
  OperationalVisual: () => null,
}))

describe('unavailable desktop release pages', () => {
  beforeEach(() => {
    fetchLatestStableDesktopRelease.mockReset()
    fetchLatestStableDesktopRelease.mockResolvedValue(null)
  })

  it('renders the public download page without fake artifacts or notarization claims', async () => {
    const { default: MacDownloadPage } = await import('../../app/download/macos/page')
    const html = renderToStaticMarkup(await MacDownloadPage())

    expect(html).toContain('data-testid="desktop-release-unavailable"')
    expect(html).toContain('MUTX desktop for macOS is currently unavailable.')
    expect(html).toContain('Artifact set incomplete.')
    expect(html).toContain('https://github.com/mutx-dev/mutx-dev/releases')
    expect(html).not.toContain('unexpected-placeholder')
    expect(html).not.toContain('Signed and notarized release')
    expect(html).not.toContain('View checksums')
    expect(html).not.toContain('/download/macos/arm64')
    expect(html).not.toContain('/download/macos/intel')
  })

  it('renders the release summary as unavailable while preserving release notes access', async () => {
    const { default: ReleasesPage } = await import('../../app/releases/page')
    const html = renderToStaticMarkup(await ReleasesPage())

    expect(html).toContain('data-testid="desktop-release-unavailable"')
    expect(html).toContain('No desktop download is offered.')
    expect(html).toContain('No release files advertised')
    expect(html).toContain('GitHub release notes')
    expect(html).toContain('https://mutx.dev/docs/releases/v1.4')
    expect(html).not.toContain('unexpected-placeholder')
    expect(html).not.toContain('Signed desktop release')
  })
})

describe('manifest-verified desktop release pages', () => {
  const release = {
    tagName: 'v1.3.0',
    version: '1.3.0',
    htmlUrl: 'https://github.com/mutx-dev/mutx-dev/releases/tag/v1.3.0',
    assets: {
      arm64Dmg:
        'https://github.com/mutx-dev/mutx-dev/releases/download/v1.3.0/MUTX-1.3.0-macos-arm64.dmg',
      x64Dmg:
        'https://github.com/mutx-dev/mutx-dev/releases/download/v1.3.0/MUTX-1.3.0-macos-x64.dmg',
      arm64Zip:
        'https://github.com/mutx-dev/mutx-dev/releases/download/v1.3.0/MUTX-1.3.0-macos-arm64.zip',
      x64Zip:
        'https://github.com/mutx-dev/mutx-dev/releases/download/v1.3.0/MUTX-1.3.0-macos-x64.zip',
      checksums:
        'https://github.com/mutx-dev/mutx-dev/releases/download/v1.3.0/MUTX-1.3.0-SHA256SUMS.txt',
    },
  }

  beforeEach(() => {
    fetchLatestStableDesktopRelease.mockReset().mockResolvedValue(release)
  })

  it('exposes provenance and verification without claiming signing or notarization', async () => {
    const { default: MacDownloadPage } = await import('../../app/download/macos/page')
    const { default: ReleasesPage } = await import('../../app/releases/page')
    const html = `${renderToStaticMarkup(await MacDownloadPage())}\n${renderToStaticMarkup(await ReleasesPage())}`

    expect(html).toContain('data-testid="desktop-release-manifest"')
    expect(html).toContain('checksum manifest names exactly both DMGs and both ZIPs')
    expect(html).toContain('exact assets from v1.3.0')
    expect(html).toContain(release.assets.arm64Zip)
    expect(html).toContain(release.assets.x64Zip)
    expect(html).not.toMatch(/\b(?:signed|notarized)\b/i)
  })
})
