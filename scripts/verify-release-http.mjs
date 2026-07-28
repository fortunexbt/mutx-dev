#!/usr/bin/env node

const [mode, rawUrl] = process.argv.slice(2)

const VALID_MODES = new Set(['frontend', 'health', 'ready', 'release'])
const FRONTEND_MARKER = 'aria-label="Example MUTX governed deployment record"'
const REQUEST_TIMEOUT_MS = 10_000

function usage() {
  console.error(
    'Usage: node scripts/verify-release-http.mjs <frontend|health|ready|release> <url>'
  )
}

function excerpt(value) {
  return value.replace(/\s+/g, ' ').trim().slice(0, 240)
}

async function fetchExact200(url) {
  const response = await fetch(url, {
    cache: 'no-store',
    redirect: 'manual',
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  })

  if (response.status !== 200) {
    const body = await response.text().catch(() => '')
    throw new Error(
      `${url} returned HTTP ${response.status}; expected exactly 200. Body: ${excerpt(body)}`
    )
  }

  return response
}

function findStaticAsset(html, baseUrl) {
  const match = html.match(
    /(?:src|href)=["']([^"']*\/_next\/static\/[^"']+\.(?:css|js)(?:\?[^"']*)?)["']/i
  )

  if (!match) {
    throw new Error('Rendered frontend HTML did not reference a Next.js static CSS/JS asset.')
  }

  return new URL(match[1].replaceAll('&amp;', '&'), baseUrl).toString()
}

async function verifyFrontend(url) {
  const response = await fetchExact200(url)
  const contentType = response.headers.get('content-type') || ''
  const html = await response.text()

  if (!contentType.toLowerCase().includes('text/html')) {
    throw new Error(`${url} returned ${contentType || 'no content type'}; expected HTML.`)
  }
  if (!html.includes(FRONTEND_MARKER)) {
    throw new Error(`${url} returned HTML without the rendered MUTX homepage marker.`)
  }

  const assetUrl = findStaticAsset(html, url)
  const assetResponse = await fetchExact200(assetUrl)
  const assetType = (assetResponse.headers.get('content-type') || '').toLowerCase()
  const asset = await assetResponse.arrayBuffer()

  if (!assetType.includes('javascript') && !assetType.includes('text/css')) {
    throw new Error(
      `${assetUrl} returned ${assetType || 'no content type'}; expected JavaScript or CSS.`
    )
  }
  if (asset.byteLength === 0) {
    throw new Error(`${assetUrl} returned an empty static asset.`)
  }
}

async function readJsonResponse(url) {
  const response = await fetchExact200(url)
  const contentType = response.headers.get('content-type') || ''
  const body = await response.text()

  if (!contentType.toLowerCase().includes('application/json')) {
    throw new Error(`${url} returned ${contentType || 'no content type'}; expected JSON.`)
  }

  try {
    return JSON.parse(body)
  } catch {
    throw new Error(`${url} returned invalid JSON: ${excerpt(body)}`)
  }
}

async function verifyHealth(url) {
  const payload = await readJsonResponse(url)
  if (
    payload.status !== 'healthy' ||
    payload.database !== 'ready' ||
    payload.components?.database?.status !== 'healthy'
  ) {
    throw new Error(
      `${url} did not report a healthy ready database: ${excerpt(JSON.stringify(payload))}`
    )
  }
}

async function verifyReady(url) {
  const payload = await readJsonResponse(url)
  if (payload.status !== 'ready' || payload.database !== 'ready') {
    throw new Error(`${url} did not report ready: ${excerpt(JSON.stringify(payload))}`)
  }
}

async function verifyRelease(url) {
  const expected = {
    tag: process.env.RELEASE_TAG,
    version: process.env.RELEASE_VERSION,
    sha: process.env.RELEASE_SHA,
  }
  for (const [key, value] of Object.entries(expected)) {
    if (!value) throw new Error(`RELEASE_${key.toUpperCase()} is required for release verification.`)
  }

  const payload = await readJsonResponse(url)
  const keys = Object.keys(payload).sort()
  const expectedKeys = Object.keys(expected).sort()
  if (JSON.stringify(keys) !== JSON.stringify(expectedKeys)) {
    throw new Error(`${url} returned an unexpected release identity shape: ${keys.join(', ')}`)
  }

  for (const [key, value] of Object.entries(expected)) {
    if (payload[key] !== value) {
      throw new Error(
        `${url} reported ${key}=${JSON.stringify(payload[key])}; expected ${JSON.stringify(value)}.`
      )
    }
  }
}

async function main() {
  if (!VALID_MODES.has(mode) || !rawUrl) {
    usage()
    process.exitCode = 2
    return
  }

  const url = new URL(rawUrl).toString()
  if (mode === 'frontend') await verifyFrontend(url)
  if (mode === 'health') await verifyHealth(url)
  if (mode === 'ready') await verifyReady(url)
  if (mode === 'release') await verifyRelease(url)
}

main().catch((error) => {
  console.error(`Release HTTP verification failed: ${error.message}`)
  process.exitCode = 1
})
