import { expect, test, type Locator } from '@playwright/test';

async function contrastRatio(foreground: Locator, background: Locator) {
  return foreground.evaluate((node, backgroundNode) => {
    if (!(backgroundNode instanceof Element)) {
      throw new Error('Expected an element for the contrast background.');
    }

    function channels(color: string) {
      const values = color.match(/\d+(?:\.\d+)?/g)?.slice(0, 3).map(Number);
      if (!values || values.length !== 3) throw new Error(`Could not parse ${color}`);
      return values;
    }

    function luminance(color: string) {
      const [red, green, blue] = channels(color).map((value) => {
        const channel = value / 255;
        return channel <= 0.04045
          ? channel / 12.92
          : ((channel + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
    }

    const foregroundLuminance = luminance(getComputedStyle(node).color);
    const backgroundLuminance = luminance(getComputedStyle(backgroundNode).backgroundColor);
    return (
      (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
      (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
    );
  }, await background.elementHandle());
}

for (const { route, heading } of [
  { route: '/manifesto', heading: 'MUTX Manifesto' },
  { route: '/roadmap', heading: 'Roadmap' },
  { route: '/whitepaper', heading: 'MUTX Technical Architecture Reference' },
]) {
  test(`${route} exposes one document H1`, async ({ page }) => {
    await page.goto(route);

    await expect(page.locator('main h1')).toHaveCount(1);
    await expect(page.locator('main h1')).toHaveText(heading);
  });
}

test('docs search contains focus, closes on Escape, and restores scrolling', async ({ page }) => {
  await page.goto('/whitepaper');
  await page.evaluate(() => window.scrollTo(0, Math.min(420, document.documentElement.scrollHeight - innerHeight)));

  const trigger = page.getByRole('button', { name: 'Search docs (Cmd+K)' });
  const scrollBefore = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
  expect(scrollBefore.y).toBeGreaterThan(0);
  await trigger.focus();
  await trigger.click();

  const dialog = page.getByRole('dialog', { name: 'Search documentation' });
  const input = dialog.getByRole('combobox', { name: 'Search documentation' });
  const close = dialog.getByRole('button', { name: 'Close search' });
  await expect(dialog).toBeVisible();
  await expect(input).toBeFocused();
  expect(await page.locator('main').evaluate((node) => Boolean(node.closest('[inert]')))).toBe(true);
  await expect(page.locator('body')).toHaveCSS('overflow', 'hidden');

  await page.keyboard.press('Shift+Tab');
  await expect(close).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(input).toBeFocused();

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  await expect.poll(() => page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }))).toEqual(scrollBefore);
});

test('docs search input, results, and trigger retain readable contrast', async ({ page }) => {
  await page.goto('/docs');

  const trigger = page.getByRole('button', { name: 'Search docs (Cmd+K)' });
  expect(await contrastRatio(trigger, trigger)).toBeGreaterThanOrEqual(4.5);
  await trigger.click();

  const dialog = page.getByRole('dialog', { name: 'Search documentation' });
  const input = dialog.getByRole('combobox', { name: 'Search documentation' });
  await input.fill('migration');
  const resultTitle = dialog.locator('.docs-search-result-title').first();
  await expect(resultTitle).toBeVisible();

  expect(await contrastRatio(input, dialog)).toBeGreaterThanOrEqual(4.5);
  expect(await contrastRatio(resultTitle, dialog)).toBeGreaterThanOrEqual(4.5);
});
