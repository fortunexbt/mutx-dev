import { expect, test, type Page } from '@playwright/test'

const PICO_ROUTES = [
  '/pico',
  '/pico/onboarding',
  '/pico/academy',
  '/pico/tutor',
  '/pico/autopilot',
  '/pico/support',
  '/pico/pricing',
  '/pico/build-ledger',
] as const

const LOCALE_ROUTE_SAMPLES = [
  ['en', '/pico'],
  ['es', '/pico/onboarding'],
  ['fr', '/pico/academy'],
  ['de', '/pico/tutor'],
  ['it', '/pico/autopilot'],
  ['pt', '/pico/support'],
  ['ja', '/pico/pricing'],
  ['ko', '/pico/build-ledger'],
  ['zh', '/pico/onboarding'],
  ['ar', '/pico/academy'],
] as const

async function useLocale(page: Page, locale: string) {
  await page.context().addCookies([
    {
      name: 'NEXT_LOCALE',
      value: locale,
      domain: '127.0.0.1',
      path: '/',
    },
  ])
}

async function expectNoRawKeysOrPageOverflow(page: Page) {
  await expect(page.locator('body')).not.toContainText(/\bpico\.[A-Za-z][\w.-]*/)

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth)
}

test.describe('Pico locale and mobile accessibility', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('all ten locale catalogs render a critical mobile route without raw keys or page overflow', async ({ page }) => {
    test.setTimeout(90_000)

    for (const [locale, route] of LOCALE_ROUTE_SAMPLES) {
      await useLocale(page, locale)
      await page.goto(route, { waitUntil: 'domcontentloaded' })

      await expect(page.locator('html')).toHaveAttribute('lang', locale)
      await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr')
      await expectNoRawKeysOrPageOverflow(page)
    }
  })

  test('Arabic mirrors every critical Pico product route at 390px', async ({ page }) => {
    test.setTimeout(90_000)
    await useLocale(page, 'ar')

    for (const route of PICO_ROUTES) {
      await page.goto(route, { waitUntil: 'domcontentloaded' })

      await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
      await expect(page.locator('.pico-root')).toHaveAttribute('dir', 'rtl')
      await expect(page.locator('main#main-content')).toHaveCSS('direction', 'rtl')
      await expectNoRawKeysOrPageOverflow(page)
    }
  })

  test('locale switching refreshes translated content and document direction', async ({ page }) => {
    await useLocale(page, 'en')
    await page.goto('/pico', { waitUntil: 'domcontentloaded' })

    const language = page.getByTestId('pico-language-switcher').first().locator('select')
    await language.selectOption('ar')
    await expect(page.locator('.pico-root')).toHaveAttribute('dir', 'rtl')
    await expect(page.locator('html')).toHaveAttribute('lang', 'ar')
    await expectNoRawKeysOrPageOverflow(page)

    await language.selectOption('ja')
    await expect(page.locator('.pico-root')).toHaveAttribute('dir', 'ltr')
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
    await expectNoRawKeysOrPageOverflow(page)
  })

  test('the mobile welcome tour traps keyboard focus and restores its trigger', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('pico.welcome-tour.dismissed.v2', 'dismissed')
    })
    await page.goto('/pico/onboarding', { waitUntil: 'domcontentloaded' })

    const trigger = page.getByTestId('pico-open-tour-mobile')
    await trigger.click()

    const dialog = page.getByRole('dialog')
    const buttons = dialog.getByRole('button')
    await expect(buttons.first()).toBeFocused()

    await page.keyboard.press('Shift+Tab')
    await expect(buttons.last()).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(buttons.first()).toBeFocused()

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
  })

  test('reduced motion disables Pico CSS animation and transition timing', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/pico', { waitUntil: 'domcontentloaded' })

    const motion = await page.evaluate(() => {
      const rail = document.querySelector<HTMLElement>('[class*="diagnosticRail"]')
      const action = document.querySelector<HTMLElement>('[data-testid="pico-landing"] a')
      if (!rail || !action) return null

      return {
        animationName: window.getComputedStyle(rail, '::after').animationName,
        transitionDuration: window.getComputedStyle(action).transitionDuration,
      }
    })

    expect(motion).not.toBeNull()
    expect(motion?.animationName).toBe('none')
    expect(motion?.transitionDuration).toMatch(/^(?:0\.01ms|0\.00001s|1e-05s)$/)
  })
})
