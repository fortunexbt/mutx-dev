import { expect, test, type Page } from '@playwright/test'

async function expectNoPageOverflow(page: Page) {
  await expect.poll(() => page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  )).toBe(true)
}

for (const viewport of [
  { name: '320px', width: 320, height: 720 },
  { name: '768px', width: 768, height: 900 },
  { name: 'desktop', width: 1440, height: 900 },
]) {
  test(`docs root and nested guide fit at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport)

    await page.goto('/docs')
    await expect(page.getByRole('heading', { level: 1, name: 'Know the system.' })).toBeVisible()
    await expectNoPageOverflow(page)

    await page.goto('/docs/deployment/kubernetes')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expectNoPageOverflow(page)

    for (const selector of ['.docs-prose pre', '.docs-prose table']) {
      const surface = page.locator(selector).first()
      await expect(surface).toBeVisible()
      expect(await surface.evaluate((node) => getComputedStyle(node).overflowX)).toBe('auto')
      expect(await surface.evaluate((node) => node.getBoundingClientRect().right <= innerWidth + 1)).toBe(true)
    }
  })
}

test('mobile navigation and table of contents remain operable', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 })
  await page.goto('/docs/deployment/kubernetes')

  const menuButton = page.getByRole('button', { name: 'Open documentation navigation' })
  await menuButton.click()
  const drawer = page.getByRole('dialog', { name: 'Documentation navigation' })
  await expect(drawer).toBeVisible()
  await expect.poll(() => drawer.evaluate((node) => node.contains(document.activeElement))).toBe(true)
  await expect(page.locator('body')).toHaveCSS('overflow', 'hidden')
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(menuButton).toBeFocused()

  const toc = page.locator('.docs-toc')
  await expect(toc).toBeVisible()
  await expect(toc.locator('nav')).toHaveCSS('overflow-x', 'auto')
  await toc.locator('a').first().click()
  const targetId = (await toc.locator('a').first().getAttribute('href'))?.slice(1)
  expect(targetId).toBeTruthy()
  await expect.poll(() => page.locator(`#${targetId}`).evaluate((node) => {
    const header = document.querySelector('.docs-header')?.getBoundingClientRect().height ?? 0
    return node.getBoundingClientRect().top >= header - 1
  })).toBe(true)
})

test('search and RTL drawer preserve focus and logical alignment', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 })
  await page.goto('/docs')

  const searchButton = page.getByRole('button', { name: 'Search docs (Cmd+K)' })
  await searchButton.click()
  const dialog = page.getByRole('dialog', { name: 'Search documentation' })
  await expect(dialog.getByRole('combobox')).toBeFocused()
  await dialog.getByRole('combobox').fill('deployment')
  await expect(dialog.getByRole('option').first()).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(searchButton).toBeFocused()

  await page.evaluate(() => document.documentElement.setAttribute('dir', 'rtl'))
  await page.getByRole('button', { name: 'Open documentation navigation' }).click()
  const drawer = page.getByRole('dialog', { name: 'Documentation navigation' })
  await expect(drawer).toBeVisible()
  expect(await drawer.evaluate((node) => Math.abs(node.getBoundingClientRect().right - innerWidth) < 1)).toBe(true)
  await expectNoPageOverflow(page)
})
