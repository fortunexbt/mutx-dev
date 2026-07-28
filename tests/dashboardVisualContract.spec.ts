import { expect, test } from '@playwright/test';

const mockKey = {
  id: 'key_visual_contract',
  name: 'Visual contract operator',
  created_at: '2026-07-28T09:00:00Z',
  expires_at: null,
  is_active: true,
  status: 'active',
  last_used_at: '2026-07-28T09:05:00Z',
};

test.describe('Dashboard visual contract', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'operator_visual',
          email: 'operator@mutx.dev',
          name: 'Visual operator',
        }),
      });
    });

    await page.route('**/api/api-keys', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [mockKey] }),
      });
    });
  });

  for (const width of [320, 768, 1280, 1600]) {
    test(`keeps records and actions available at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto('/dashboard/api-keys', { waitUntil: 'domcontentloaded' });

      await expect(page.getByRole('heading', { name: 'API Keys' })).toBeVisible();
      await expect(page.getByText('Visual contract operator')).toBeVisible();

      const contract = await page.evaluate(() => ({
        horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
        theme: document.querySelector('[data-dashboard-theme]')?.getAttribute('data-dashboard-theme'),
      }));
      expect(contract.theme).toBe('flight-recorder');
      expect(contract.horizontalOverflow).toBeLessThanOrEqual(1);

      const rotate = page.getByRole('button', { name: 'Rotate', exact: true });
      const rotateBox = await rotate.boundingBox();
      expect(rotateBox?.height).toBeGreaterThanOrEqual(44);

      const record = page
        .getByText('Visual contract operator')
        .locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]');
      await expect(record).toHaveCSS('border-radius', '6px');
    });
  }

  test('keeps the destructive confirmation reachable inside a 320px viewport', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto('/dashboard/api-keys', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('Visual contract operator')).toBeVisible();

    const rotate = page.getByRole('button', { name: 'Rotate', exact: true });
    await rotate.click();

    const dialog = page.getByRole('dialog', { name: 'Rotate API key?' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();

    const dialogBox = await dialog.boundingBox();
    expect(dialogBox?.height).toBeLessThanOrEqual(568);
    expect(dialogBox?.x).toBeGreaterThanOrEqual(0);
    expect((dialogBox?.x ?? 0) + (dialogBox?.width ?? 0)).toBeLessThanOrEqual(320);

    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(rotate).toBeFocused();
  });
});
