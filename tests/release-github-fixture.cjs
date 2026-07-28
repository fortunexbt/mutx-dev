const FIXTURE_MODE = process.env.MUTX_DESKTOP_RELEASE_FIXTURE
const RELEASES_API_URL =
  'https://api.github.com/repos/mutx-dev/mutx-dev/releases?per_page=20'
const FIXTURE_VERSION = '9.8.7'

if (FIXTURE_MODE && !['available', 'unavailable'].includes(FIXTURE_MODE)) {
  throw new Error(`Unsupported MUTX_DESKTOP_RELEASE_FIXTURE: ${FIXTURE_MODE}`)
}

if (FIXTURE_MODE && !globalThis.__mutxReleaseFixtureInstalled) {
  const originalFetch = globalThis.fetch.bind(globalThis)
  const tag = `v${FIXTURE_VERSION}`
  const artifactNames = [
    `MUTX-${FIXTURE_VERSION}-macos-arm64.dmg`,
    `MUTX-${FIXTURE_VERSION}-macos-x64.dmg`,
    `MUTX-${FIXTURE_VERSION}-macos-arm64.zip`,
    `MUTX-${FIXTURE_VERSION}-macos-x64.zip`,
    `MUTX-${FIXTURE_VERSION}-SHA256SUMS.txt`,
  ]
  const availableRelease = {
    tag_name: tag,
    draft: false,
    prerelease: false,
    html_url: `https://github.com/mutx-dev/mutx-dev/releases/tag/${tag}`,
    assets: artifactNames.map((name) => ({
      name,
      browser_download_url:
        `https://github.com/mutx-dev/mutx-dev/releases/download/${tag}/${name}`,
      size: 1024,
      state: 'uploaded',
    })),
  }
  const checksumUrl = availableRelease.assets.at(-1).browser_download_url
  const checksumBody = artifactNames
    .slice(0, -1)
    .map((name, index) => `${String(index + 1).repeat(64)}  ${name}`)
    .join('\n') + '\n'
  const mixedPackageReleases = Array.from({ length: 20 }, (_, index) => {
    const packageTag = `${index % 2 === 0 ? 'cli' : 'sdk'}-v9.7.${index}`
    return {
      tag_name: packageTag,
      draft: false,
      prerelease: false,
      html_url: `https://github.com/mutx-dev/mutx-dev/releases/tag/${packageTag}`,
      assets: [],
    }
  })

  globalThis.fetch = async (input, init) => {
    const url = typeof input === 'string' || input instanceof URL ? String(input) : input.url
    if (url === RELEASES_API_URL || url.startsWith(`${RELEASES_API_URL}&page=`)) {
      const page = new URL(url).searchParams.get('page') ?? '1'
      let payload = []
      if (FIXTURE_MODE === 'available' && page === '1') {
        payload = mixedPackageReleases
      } else if (FIXTURE_MODE === 'available' && page === '2') {
        payload = [availableRelease]
      }
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }
    if (FIXTURE_MODE === 'available' && url === checksumUrl) {
      return new Response(checksumBody, {
        status: 200,
        headers: { 'content-type': 'text/plain' },
      })
    }
    return originalFetch(input, init)
  }

  Object.defineProperty(globalThis, '__mutxReleaseFixtureInstalled', { value: true })
}
