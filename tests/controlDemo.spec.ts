import { expect, test } from '@playwright/test';

const CONTROL_ROUTES = [
  '/control',
  '/control/agents',
  '/control/deployments',
  '/control/runs',
  '/control/environments',
  '/control/access',
  '/control/connectors',
  '/control/audit',
  '/control/usage',
  '/control/settings',
];

test.describe('simulated control demo', () => {
  test('labels the simulation, uses the flight-recorder system, and keeps links internal', async ({ page }) => {
    await page.goto('/control', { waitUntil: 'domcontentloaded' });

    const root = page.getByTestId('control-demo-root');
    await expect(page.getByTestId('control-demo-label')).toHaveText(
      /simulated interactive demo · sample data · actions stay local/i,
    );
    await expect(root).toHaveAttribute('aria-label', /simulated control plane demo/i);
    await expect(root).toHaveAttribute('data-control-visual-system', 'flight-recorder');
    await expect(root).toHaveAttribute('data-no-live-writes', 'true');
    await expect(root).toHaveCSS('background-color', 'rgb(9, 10, 8)');
    await expect(page.getByRole('dialog', { name: /demo script/i })).toHaveCount(0);
    await expect(page.getByText(/demo script · talk track/i)).toHaveCount(0);

    const hrefs = await root.locator('a[href]').evaluateAll((links) =>
      links.map((link) => link.getAttribute('href')).filter((href): href is string => Boolean(href)),
    );
    expect(hrefs.length).toBeGreaterThan(0);
    expect(hrefs.every((href) => href === '/control' || href.startsWith('/control/'))).toBe(true);
  });

  test('opens presenter mode from the keyboard, traps focus, announces state, and restores focus', async ({ page }) => {
    await page.goto('/control', { waitUntil: 'domcontentloaded' });

    const presenter = page.getByRole('button', { name: 'Presenter' });
    await presenter.focus();
    await page.keyboard.press('Enter');

    const dialog = page.getByRole('dialog', { name: /demo script/i });
    const close = dialog.getByRole('button', { name: /close presenter mode/i });
    await expect(dialog).toBeVisible();
    await expect(close).toBeFocused();
    await expect(page.getByRole('status')).toHaveText(/presenter mode on/i);
    await page.keyboard.press('Tab');
    await expect(close).toBeFocused();

    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(presenter).toBeFocused();
    await expect(page.getByRole('status')).toHaveText(/presenter mode off/i);
  });

  test('supports keyboard-only local interventions and route search', async ({ page }) => {
    await page.goto('/control', { waitUntil: 'domcontentloaded' });

    const quickAction = page.locator('button:visible', { hasText: 'Deploy new version' }).first();
    await quickAction.focus();
    await expect(quickAction).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(quickAction).toContainText(/simulated locally/i);
    await expect(page.getByTestId('control-demo-action-status').filter({ hasText: /no live system was changed/i }).first()).toBeAttached();

    const search = page.locator('input[aria-label="Search simulated control plane"]:visible');
    await search.focus();
    await page.keyboard.type('settings');

    const results = page.locator('[data-testid="control-demo-search-results"]:visible');
    await expect(results).toContainText(/sample routes · no live data/i);
    const settingsResult = results.getByRole('link', { name: /settings/i });
    await page.keyboard.press('Tab');
    await expect(settingsResult).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/control\/settings$/);
    await expect(page.getByTestId('control-demo-label')).toBeVisible();
  });

  test('freezes the ticker when reduced motion is requested', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/control', { waitUntil: 'domcontentloaded' });

    const root = page.getByTestId('control-demo-root');
    await expect(root).toHaveAttribute('data-motion', 'reduced');
    await expect(page.getByTestId('control-demo-stage')).toHaveCSS('transform', 'none');

    const initialTick = await root.getAttribute('data-demo-tick');
    await page.waitForTimeout(2500);
    await expect(root).toHaveAttribute('data-demo-tick', initialTick ?? '0');
  });

  for (const width of [320, 768, 1280, 1600]) {
    test(`keeps the ${width}px flight deck contained and touch targets usable`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 320 ? 720 : 900 });
      await page.goto('/control', { waitUntil: 'domcontentloaded' });

      await expect(page.getByTestId('control-demo-label')).toBeVisible();
      await expect(page.locator('input[aria-label="Search simulated control plane"]:visible')).toBeVisible();
      await expect(page.getByRole('link', { name: /open simulated settings/i })).toHaveAttribute('href', '/control/settings');

      const presenterBox = await page.getByRole('button', { name: 'Presenter' }).boundingBox();
      const settingsBox = await page.getByRole('link', { name: /open simulated settings/i }).boundingBox();
      expect(presenterBox?.height).toBeGreaterThanOrEqual(44);
      expect(settingsBox?.height).toBeGreaterThanOrEqual(44);

      const layout = await page.evaluate(() => ({
        bodyWidth: document.body.scrollWidth,
        viewportWidth: window.innerWidth,
        rootRight: document.querySelector('[data-testid="control-demo-root"]')?.getBoundingClientRect().right,
      }));
      expect(layout.bodyWidth).toBeLessThanOrEqual(layout.viewportWidth);
      expect(layout.rootRight).toBeLessThanOrEqual(layout.viewportWidth);

      if (width === 320) {
        await page.getByRole('button', { name: 'Presenter' }).click();
        const dialogBox = await page.getByRole('dialog', { name: /demo script/i }).boundingBox();
        expect(dialogBox?.width).toBeLessThanOrEqual(320);
        await page.keyboard.press('Escape');
      }
    });
  }

  test('renders every internal control route without browser console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', (error) => errors.push(error.message));

    for (const route of CONTROL_ROUTES) {
      await page.goto(route, { waitUntil: 'domcontentloaded' });
      await expect(page.getByTestId('control-demo-root')).toBeVisible();
      await expect(page.getByTestId('control-demo-label')).toBeVisible();
    }

    expect(errors).toEqual([]);
  });
});
