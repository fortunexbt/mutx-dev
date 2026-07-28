const fetchLatestStableDesktopRelease = jest.fn()

jest.mock('../../lib/desktopRelease', () => ({
  MUTX_RELEASE_NOTES_URL: 'https://mutx.dev/docs/releases/v1.4',
  buildReleaseNotesUrl: (version: string) =>
    `https://mutx.dev/docs/releases/v${version.split('.').slice(0, 2).join('.')}`,
  fetchLatestStableDesktopRelease,
}))

const completeRelease = {
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

describe('download routes', () => {
  beforeEach(() => {
    jest.resetModules()
    fetchLatestStableDesktopRelease.mockReset()
  })

  it('redirects the Apple Silicon route to the coherent stable DMG asset', async () => {
    fetchLatestStableDesktopRelease.mockResolvedValue(completeRelease)

    const { GET } = await import('../../app/download/macos/arm64/route')
    const response = await GET(new Request('https://mutx.dev/download/macos/arm64'))

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe(completeRelease.assets.arm64Dmg)
    expect(response.headers.get('cache-control')).toBe('private, no-store')
  })

  it('redirects the Intel route to the coherent stable DMG asset', async () => {
    fetchLatestStableDesktopRelease.mockResolvedValue(completeRelease)

    const { GET } = await import('../../app/download/macos/intel/route')
    const response = await GET(new Request('https://mutx.dev/download/macos/intel'))

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe(completeRelease.assets.x64Dmg)
    expect(response.headers.get('cache-control')).toBe('private, no-store')
  })

  it.each([
    ['arm64', '../../app/download/macos/arm64/route'],
    ['intel', '../../app/download/macos/intel/route'],
  ])('redirects the unavailable %s route to the public availability page', async (arch, path) => {
    fetchLatestStableDesktopRelease.mockResolvedValue(null)

    const { GET } = await import(path)
    const response = await GET(new Request(`https://mutx.dev/download/macos/${arch}`))

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('https://mutx.dev/download/macos')
    expect(response.headers.get('cache-control')).toBe('private, no-store')
  })

  it('keeps docs release notes available for a complete desktop release', async () => {
    fetchLatestStableDesktopRelease.mockResolvedValue(completeRelease)

    const { GET } = await import('../../app/download/macos/release-notes/route')
    const response = await GET()

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('https://mutx.dev/docs/releases/v1.3')
    expect(response.headers.get('cache-control')).toBe('private, no-store')
  })

  it('keeps the current docs release notes available when desktop downloads are unavailable', async () => {
    fetchLatestStableDesktopRelease.mockResolvedValue(null)

    const { GET } = await import('../../app/download/macos/release-notes/route')
    const response = await GET()

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('https://mutx.dev/docs/releases/v1.4')
    expect(response.headers.get('cache-control')).toBe('private, no-store')
  })
})
