import { expect, test, type Page } from '@playwright/test'

async function useArabic(page: Page) {
  await page.context().addCookies([
    {
      name: 'NEXT_LOCALE',
      value: 'ar',
      domain: '127.0.0.1',
      path: '/',
    },
  ])
}

const arabicSurfaces = [
  { name: 'public', route: '/', selector: '[data-testid="public-nav"]' },
  { name: 'auth', route: '/login', selector: 'main[data-auth-host="default"]' },
  { name: 'docs', route: '/docs', selector: '.docs-shell' },
  { name: 'download', route: '/download', selector: 'main#main-content' },
  { name: 'control', route: '/control', selector: '[data-mutx-demo-root]' },
  { name: 'dashboard', route: '/dashboard', selector: '[data-dashboard-theme="flight-recorder"]' },
] as const

for (const surface of arabicSurfaces) {
  test(`Arabic ${surface.name} surface inherits RTL document direction`, async ({ page }) => {
    await useArabic(page)
    await page.goto(surface.route, { waitUntil: 'domcontentloaded' })

    await expect(page.locator('html')).toHaveAttribute('lang', 'ar')
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
    await expect(page.locator(surface.selector).first()).toHaveCSS('direction', 'rtl')
  })
}

test('Arabic Pico-host auth inherits the root RTL contract', async ({ page }) => {
  await useArabic(page)
  await page.context().setExtraHTTPHeaders({ host: 'pico.mutx.dev' })
  await page.goto('/login', { waitUntil: 'domcontentloaded' })

  await expect(page.locator('html')).toHaveAttribute('lang', 'ar')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.getByRole('heading', { name: 'تسجيل الدخول إلى PicoMUTX' })).toBeVisible()
  await expect(page.locator('main#main-content')).toHaveCSS('direction', 'rtl')
})

test('Arabic docs drawer opens from inline start and retains keyboard focus order', async ({ page }) => {
  await useArabic(page)
  await page.setViewportSize({ width: 800, height: 720 })
  await page.goto('/docs', { waitUntil: 'domcontentloaded' })

  const trigger = page.getByRole('button', { name: 'Open documentation navigation' })
  await trigger.click()

  const drawer = page.getByRole('dialog', { name: 'Documentation navigation' })
  await expect(drawer).toBeVisible()
  const box = await drawer.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.x + box!.width).toBeGreaterThanOrEqual(799)
  await expect(drawer.locator('a, button').first()).toBeFocused()

  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(trigger).toBeFocused()
})

test('technical commands stay LTR inside an Arabic document', async ({ page }) => {
  await useArabic(page)
  await page.goto('/docs', { waitUntil: 'domcontentloaded' })

  const technical = page.locator('code, pre, kbd, samp').first()
  await expect(technical).toBeVisible()
  await expect(technical).toHaveCSS('direction', 'ltr')
  await expect(technical).toHaveCSS('text-align', 'left')
})
