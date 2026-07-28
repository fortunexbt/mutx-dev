import {
  DESKTOP_RELEASE_MAX_PAGES,
  buildDesktopArtifactName,
  buildReleaseNotesUrl,
  fetchLatestStableDesktopRelease,
  findLatestStableAppRelease,
  isValidDesktopChecksumManifest,
  normalizeDesktopRelease,
  type GitHubRelease,
} from '../../lib/desktopRelease'
import { getPublishedDoc } from '../../lib/docs'

const assetKinds = ['arm64-dmg', 'x64-dmg', 'arm64-zip', 'x64-zip', 'checksums'] as const

function makeCompleteRelease(
  version: string,
  overrides: Partial<GitHubRelease> = {}
): GitHubRelease {
  const tagName = `v${version}`

  return {
    tag_name: tagName,
    draft: false,
    prerelease: false,
    html_url: `https://github.com/mutx-dev/mutx-dev/releases/tag/${tagName}`,
    assets: assetKinds.map((kind) => {
      const name = buildDesktopArtifactName(version, kind)
      return {
        name,
        browser_download_url: `https://github.com/mutx-dev/mutx-dev/releases/download/${tagName}/${name}`,
        size: 1024,
        state: 'uploaded' as const,
      }
    }),
    ...overrides,
  }
}

function makeChecksumManifest(version: string) {
  return (['arm64-dmg', 'x64-dmg', 'arm64-zip', 'x64-zip'] as const)
    .map((kind, index) => `${String(index + 1).repeat(64)}  ${buildDesktopArtifactName(version, kind)}`)
    .join('\n') + '\n'
}

function makeReleaseFetch(
  pages: readonly unknown[][],
  manifestOverrides: Readonly<Record<string, string | null>> = {}
) {
  return jest.fn(async (input: string | URL | Request) => {
    const url = String(input instanceof Request ? input.url : input)
    if (url.startsWith('https://api.github.com/repos/mutx-dev/mutx-dev/releases?')) {
      const page = Number(new URL(url).searchParams.get('page') ?? '1')
      return new Response(JSON.stringify(pages[page - 1] ?? []), { status: 200 })
    }

    const manifestMatch = /\/releases\/download\/v([^/]+)\/MUTX-[^/]+-SHA256SUMS\.txt$/.exec(url)
    if (manifestMatch) {
      const version = manifestMatch[1]
      const override = manifestOverrides[version]
      if (override === null) {
        return new Response('not found', { status: 404 })
      }
      return new Response(override ?? makeChecksumManifest(version), { status: 200 })
    }

    return new Response('unexpected URL', { status: 500 })
  })
}

function makeNonDesktopRelease(tagName: string): GitHubRelease {
  return {
    tag_name: tagName,
    draft: false,
    prerelease: false,
    html_url: `https://github.com/mutx-dev/mutx-dev/releases/tag/${tagName}`,
    assets: [],
  }
}

describe('desktop release resolver', () => {
  beforeEach(() => {
    jest.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('normalizes a complete coherent desktop artifact set', () => {
    const release = normalizeDesktopRelease(makeCompleteRelease('1.3.0'))

    expect(release).toEqual({
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
    })
  })

  it('rejects a partial newer release and selects the newest complete stable release', () => {
    const partialRelease = makeCompleteRelease('1.4.0')
    partialRelease.assets = partialRelease.assets.filter(
      (asset) => asset.name !== buildDesktopArtifactName('1.4.0', 'x64-dmg')
    )

    expect(normalizeDesktopRelease(partialRelease)).toBeNull()
    expect(
      findLatestStableAppRelease([partialRelease, makeCompleteRelease('1.3.0')])?.tag_name
    ).toBe('v1.3.0')
  })

  it('rejects empty, processing, duplicate, and extra uploaded asset sets', () => {
    const emptyAssetRelease = makeCompleteRelease('1.3.0')
    emptyAssetRelease.assets[0].size = 0

    const completeProcessingRelease = makeCompleteRelease('1.3.0')
    const processingAssetRelease = {
      ...completeProcessingRelease,
      assets: completeProcessingRelease.assets.map((asset) => ({
        ...asset,
        state: String(asset.state),
      })),
    }
    processingAssetRelease.assets[0].state = 'new'

    const duplicateAssetRelease = makeCompleteRelease('1.3.0')
    duplicateAssetRelease.assets[1] = { ...duplicateAssetRelease.assets[0] }

    const extraAssetRelease = makeCompleteRelease('1.3.0')
    extraAssetRelease.assets.push({
      name: 'unexpected.txt',
      browser_download_url:
        'https://github.com/mutx-dev/mutx-dev/releases/download/v1.3.0/unexpected.txt',
      size: 1,
      state: 'uploaded',
    })

    expect(normalizeDesktopRelease(emptyAssetRelease)).toBeNull()
    expect(normalizeDesktopRelease(processingAssetRelease as unknown as GitHubRelease)).toBeNull()
    expect(normalizeDesktopRelease(duplicateAssetRelease)).toBeNull()
    expect(normalizeDesktopRelease(extraAssetRelease)).toBeNull()
  })

  it('does not select a draft release even when its artifact set is complete', () => {
    expect(
      findLatestStableAppRelease([
        makeCompleteRelease('1.4.0', { draft: true }),
        makeCompleteRelease('1.3.0'),
      ])?.tag_name
    ).toBe('v1.3.0')
  })

  it('does not select a prerelease even when its artifact set is complete', () => {
    expect(
      findLatestStableAppRelease([
        makeCompleteRelease('1.4.0', { prerelease: true }),
        makeCompleteRelease('1.3.0'),
      ])?.tag_name
    ).toBe('v1.3.0')
  })

  it('ignores malformed releases and unsafe asset URLs', () => {
    const unsafeRelease = makeCompleteRelease('1.5.0')
    unsafeRelease.assets[0].browser_download_url =
      'https://downloads.example.com/MUTX-1.5.0-macos-arm64.dmg'

    expect(normalizeDesktopRelease(unsafeRelease)).toBeNull()
    expect(
      findLatestStableAppRelease([
        null,
        { tag_name: 'v1.6.0' },
        unsafeRelease,
        makeCompleteRelease('1.3.0'),
      ])?.tag_name
    ).toBe('v1.3.0')
  })

  it('fetches and returns a complete stable desktop release', async () => {
    const fetchImpl = makeReleaseFetch([[makeCompleteRelease('1.3.0')]])

    await expect(fetchLatestStableDesktopRelease(fetchImpl)).resolves.toMatchObject({
      tagName: 'v1.3.0',
      version: '1.3.0',
    })
  })

  it('paginates beyond 20 mixed CLI and SDK releases to find a desktop release', async () => {
    const firstPage = Array.from({ length: 20 }, (_, index) =>
      makeNonDesktopRelease(`${index % 2 === 0 ? 'cli' : 'sdk'}-v9.0.${index}`)
    )
    const fetchImpl = makeReleaseFetch([firstPage, [makeCompleteRelease('1.3.0')]])

    await expect(fetchLatestStableDesktopRelease(fetchImpl)).resolves.toMatchObject({
      tagName: 'v1.3.0',
    })
    expect(fetchImpl).toHaveBeenNthCalledWith(
      1,
      'https://api.github.com/repos/mutx-dev/mutx-dev/releases?per_page=20',
      expect.any(Object)
    )
    expect(fetchImpl).toHaveBeenNthCalledWith(
      2,
      'https://api.github.com/repos/mutx-dev/mutx-dev/releases?per_page=20&page=2',
      expect.any(Object)
    )
  })

  it('selects the global semver maximum after fetching inverse-ordered release pages', async () => {
    const firstPage = [
      makeCompleteRelease('1.3.0'),
      ...Array.from({ length: 19 }, (_, index) =>
        makeNonDesktopRelease(`cli-v9.1.${index}`)
      ),
    ]
    const fetchImpl = makeReleaseFetch([firstPage, [makeCompleteRelease('2.0.0')]])

    await expect(fetchLatestStableDesktopRelease(fetchImpl)).resolves.toMatchObject({
      tagName: 'v2.0.0',
      version: '2.0.0',
    })
    expect(fetchImpl).toHaveBeenCalledTimes(3)
  })

  it('requires an exact four-entry checksum manifest before advertising a release', async () => {
    const version = '1.3.0'
    const validManifest = makeChecksumManifest(version)

    expect(isValidDesktopChecksumManifest(validManifest, version)).toBe(true)
    expect(isValidDesktopChecksumManifest(validManifest.replace('  MUTX', ' MUTX'), version)).toBe(false)
    expect(isValidDesktopChecksumManifest(validManifest.replace(/^[^\n]+\n/, ''), version)).toBe(false)
    expect(isValidDesktopChecksumManifest(validManifest.replaceAll('\n', '\r\n'), version)).toBe(false)

    const fetchImpl = makeReleaseFetch(
      [[makeCompleteRelease(version)]],
      { [version]: 'not a checksum manifest\n' }
    )
    await expect(fetchLatestStableDesktopRelease(fetchImpl)).resolves.toBeNull()
  })

  it('falls back to the newest older release with a valid manifest', async () => {
    const fetchImpl = makeReleaseFetch(
      [[makeCompleteRelease('2.0.0'), makeCompleteRelease('1.3.0')]],
      { '2.0.0': null }
    )

    await expect(fetchLatestStableDesktopRelease(fetchImpl)).resolves.toMatchObject({
      tagName: 'v1.3.0',
      version: '1.3.0',
    })
  })

  it('fails closed when the bounded page scan contains no desktop release', async () => {
    const fullMixedPage = Array.from({ length: 20 }, (_, index) =>
      makeNonDesktopRelease(`cli-v8.0.${index}`)
    )
    const fetchImpl = jest.fn().mockImplementation(async () =>
      new Response(JSON.stringify(fullMixedPage), { status: 200 })
    )

    await expect(fetchLatestStableDesktopRelease(fetchImpl)).resolves.toBeNull()
    expect(fetchImpl).toHaveBeenCalledTimes(DESKTOP_RELEASE_MAX_PAGES)
    expect(fetchImpl.mock.calls.at(-1)?.[0]).toBe(
      `https://api.github.com/repos/mutx-dev/mutx-dev/releases?per_page=20&page=${DESKTOP_RELEASE_MAX_PAGES}`
    )
    expect(console.error).toHaveBeenCalledWith(
      expect.stringContaining(`within ${DESKTOP_RELEASE_MAX_PAGES} pages`)
    )
  })

  it('fails closed when a later GitHub releases page fails', async () => {
    const firstPage = Array.from({ length: 20 }, (_, index) =>
      makeNonDesktopRelease(`sdk-v7.0.${index}`)
    )
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(firstPage), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ message: 'rate limited' }), { status: 429 })
      )

    await expect(fetchLatestStableDesktopRelease(fetchImpl)).resolves.toBeNull()
    expect(fetchImpl).toHaveBeenCalledTimes(2)
  })

  it('fails closed instead of selecting around malformed release records', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      new Response(JSON.stringify([null, makeCompleteRelease('1.3.0')]), { status: 200 })
    )

    await expect(fetchLatestStableDesktopRelease(fetchImpl)).resolves.toBeNull()
  })

  it('returns null for a malformed GitHub releases payload', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      new Response(JSON.stringify({ tag_name: 'v1.3.0' }), { status: 200 })
    )

    await expect(fetchLatestStableDesktopRelease(fetchImpl)).resolves.toBeNull()
  })

  it('maps stable app releases to the repo-backed published release notes route', () => {
    expect(buildReleaseNotesUrl('1.3.0')).toBe('https://mutx.dev/docs/releases/v1.3')
  })

  it('targets a published route backed by the matching repository release notes source', () => {
    const releaseNotesUrl = new URL(buildReleaseNotesUrl('1.4.0'))

    expect(releaseNotesUrl.origin).toBe('https://mutx.dev')
    expect(getPublishedDoc(releaseNotesUrl.pathname)?.sourcePath).toBe('docs/releases/v1.4.md')
  })

  it('returns null when the GitHub releases lookup fails', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'upstream unavailable' }), { status: 503 })
    )

    await expect(fetchLatestStableDesktopRelease(fetchImpl)).resolves.toBeNull()
    expect(fetchImpl).toHaveBeenCalled()
  })
})
