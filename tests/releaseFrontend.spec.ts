import { expect, test } from '@playwright/test'

test('production frontend renders the release route and serves a hashed asset', async ({
  page,
  request,
}) => {
  const response = await page.goto('/', { waitUntil: 'domcontentloaded' })

  expect(response?.status()).toBe(200)
  await expect(
    page.getByRole('heading', { name: /read the governed path\. hold the line\./i })
  ).toBeVisible()
  await expect(
    page.getByLabel(/example mutx governed deployment record/i)
  ).toBeVisible()

  const assetPath = await page
    .locator('script[src*="/_next/static/"], link[href*="/_next/static/"]')
    .first()
    .evaluate((element) => element.getAttribute('src') ?? element.getAttribute('href'))

  expect(assetPath).toBeTruthy()

  const assetResponse = await request.get(new URL(assetPath!, response!.url()).toString())
  expect(assetResponse.status()).toBe(200)
  expect(assetResponse.headers()['content-type']).toMatch(/javascript|text\/css/i)
  expect((await assetResponse.body()).byteLength).toBeGreaterThan(0)
})

test('release and architecture routes fail closed when desktop artifacts are unavailable @release-fixture-unavailable', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.MUTX_DESKTOP_RELEASE_FIXTURE !== 'unavailable',
    'requires the deterministic unavailable release fixture'
  )

  const releaseResponse = await page.goto('/releases', { waitUntil: 'domcontentloaded' })

  expect(releaseResponse?.status()).toBe(200)
  await expect(page.getByTestId('desktop-release-unavailable')).toContainText(/unavailable/i)
  await expect(page.getByRole('heading', { name: /no desktop download is offered/i })).toBeVisible()

  const architectureResponse = await request.get('/download/macos/arm64', {
    maxRedirects: 0,
  })
  expect(architectureResponse.status()).toBe(307)
  expect(new URL(architectureResponse.headers().location).pathname).toBe('/download/macos')

  const releaseNotesResponse = await request.get('/download/macos/release-notes')
  expect(releaseNotesResponse.status()).toBe(200)
  expect(new URL(releaseNotesResponse.url()).pathname).toBe('/docs/releases/v1.4')
  expect(await releaseNotesResponse.text()).toContain('MUTX v1.4.0')

  await page.goto('/download/macos', { waitUntil: 'domcontentloaded' })
  await expect(page.getByTestId('desktop-release-unavailable')).toContainText(/unavailable/i)
  await expect(page.getByRole('heading', { name: /currently unavailable/i })).toBeVisible()
  await expect(page.getByRole('link', { name: /download for apple silicon/i })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /download for intel mac/i })).toHaveCount(0)
})

test('release and architecture routes expose one complete artifact set @release-fixture-available', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.MUTX_DESKTOP_RELEASE_FIXTURE !== 'available',
    'requires the deterministic available release fixture'
  )

  const releaseResponse = await page.goto('/releases', { waitUntil: 'domcontentloaded' })

  expect(releaseResponse?.status()).toBe(200)
  await expect(page.getByRole('heading', { name: /complete desktop release/i })).toBeVisible()
  await expect(page.getByText(/current stable desktop release:/i)).toContainText('v9.8.7')
  await expect(page.getByRole('link', { name: /download arm64/i })).toHaveAttribute(
    'href',
    'https://github.com/mutx-dev/mutx-dev/releases/download/v9.8.7/MUTX-9.8.7-macos-arm64.dmg'
  )

  const architectureResponse = await request.get('/download/macos/arm64', {
    maxRedirects: 0,
  })
  expect(architectureResponse.status()).toBe(307)
  expect(architectureResponse.headers().location).toBe(
    'https://github.com/mutx-dev/mutx-dev/releases/download/v9.8.7/MUTX-9.8.7-macos-arm64.dmg'
  )

  await page.goto('/download/macos', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('link', { name: /download for apple silicon/i })).toBeVisible()
  await expect(page.getByRole('link', { name: /download for intel mac/i })).toBeVisible()
  await expect(page.getByTestId('desktop-release-unavailable')).toHaveCount(0)
})

test('standalone docs publish a working client search index', async ({ page }) => {
  const response = await page.goto('/docs', { waitUntil: 'domcontentloaded' })

  expect(response?.status()).toBe(200)
  await page.getByRole('button', { name: /search docs/i }).click()
  const search = page.getByRole('combobox', { name: /search documentation/i })
  await search.fill('agent')
  await expect(page.getByRole('listbox', { name: /search results/i })).toBeVisible()
  await expect(page.getByRole('option').first()).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: /search documentation/i })).toHaveCount(0)
})

test('standalone dashboard preserves its route boundary without a live session', async ({ page }) => {
  const response = await page.goto('/dashboard/release-smoke-unknown', {
    waitUntil: 'domcontentloaded',
  })

  expect(response?.status()).toBe(404)
  const boundary = page.locator(
    '[data-boundary-surface="dashboard"][data-boundary-kind="not-found"]'
  )
  await expect(boundary).toBeVisible()
  await expect(boundary.getByRole('heading', { name: /no dashboard record matches/i })).toBeVisible()
  await expect(boundary.getByRole('link', { name: /dashboard home/i })).toBeVisible()
})
