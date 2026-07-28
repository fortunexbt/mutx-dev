import { expect, test } from '@playwright/test';

const publicRoutes = [
  '/',
  '/ai-agent-approvals',
  '/ai-agent-audit-logs',
  '/ai-agent-control-plane',
  '/ai-agent-cost',
  '/ai-agent-deployment',
  '/ai-agent-governance',
  '/ai-agent-guardrails',
  '/ai-agent-infrastructure',
  '/ai-agent-monitoring',
  '/ai-agent-reliability',
  '/contact',
  '/infrastructure',
  '/manifesto',
  '/privacy-policy',
  '/releases',
  '/roadmap',
  '/sdk',
  '/security',
  '/support',
  '/whitepaper',
] as const;

const authRoutes = [
  '/login',
  '/register',
  '/forgot-password',
  '/reset-password',
  '/verify-email',
] as const;

const representativeRoutes = [
  '/',
  '/ai-agent-control-plane',
  '/contact',
  '/privacy-policy',
  '/login',
  '/forgot-password',
] as const;

test.describe('Public and authentication product QA', () => {
  test('every owned route has a reachable, named main landmark', async ({ page }) => {
    test.setTimeout(180_000);

    for (const route of [...publicRoutes, ...authRoutes]) {
      const response = await page.goto(route, { waitUntil: 'domcontentloaded' });
      expect(response?.status(), `${route} should return a successful response`).toBeLessThan(400);

      const main = page.locator('#main-content');
      await expect(main, `${route} should expose the skip-link target`).toBeVisible();
      await expect(main.getByRole('heading', { level: 1 }).first(), `${route} should have an h1`).toBeVisible();
    }
  });

  for (const viewport of [
    { name: 'desktop', width: 1440, height: 1000 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'mobile', width: 390, height: 844 },
  ] as const) {
    test(`representative routes do not overflow at ${viewport.name} width`, async ({ page }) => {
      test.setTimeout(120_000);
      await page.setViewportSize({ width: viewport.width, height: viewport.height });

      for (const route of representativeRoutes) {
        await page.goto(route, { waitUntil: 'domcontentloaded' });
        const overflow = await page.evaluate(() => ({
          documentWidth: document.documentElement.scrollWidth,
          viewportWidth: window.innerWidth,
        }));

        expect(
          overflow.documentWidth,
          `${route} should fit inside the ${viewport.width}px viewport`,
        ).toBeLessThanOrEqual(overflow.viewportWidth + 1);
      }
    });
  }

  test('visible interactive controls have accessible names', async ({ page }) => {
    for (const route of representativeRoutes) {
      await page.goto(route, { waitUntil: 'domcontentloaded' });
      const unnamedControls = await page
        .locator('a:visible, button:visible, input:visible, select:visible, textarea:visible')
        .evaluateAll((elements) => elements.flatMap((element) => {
          const htmlElement = element as HTMLElement;
          const labelledBy = htmlElement.getAttribute('aria-labelledby');
          const labelledByText = labelledBy
            ?.split(/\s+/)
            .map((id) => document.getElementById(id)?.textContent ?? '')
            .join(' ')
            .trim();
          const labels = 'labels' in element
            ? Array.from((element as HTMLInputElement).labels ?? []).map((label) => label.textContent ?? '').join(' ').trim()
            : '';
          const name = htmlElement.getAttribute('aria-label')
            || labelledByText
            || labels
            || htmlElement.getAttribute('title')
            || htmlElement.textContent?.trim();

          return name ? [] : [htmlElement.outerHTML];
        }));

      expect(unnamedControls, `${route} has unnamed interactive controls`).toEqual([]);
    }
  });

  test('skip link moves keyboard focus to main content', async ({ page }) => {
    await page.goto('/login');
    await page.keyboard.press('Tab');

    const skipLink = page.getByRole('link', { name: 'Skip to main content' });
    await expect(skipLink).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.locator('#main-content')).toBeFocused();
  });

  test('product group styling does not misreport the current page', async ({ page }) => {
    await page.goto('/ai-agent-monitoring');
    const productLink = page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'Product' });
    await expect(productLink).not.toHaveAttribute('aria-current');

    await page.goto('/ai-agent-control-plane');
    await expect(productLink).toHaveAttribute('aria-current', 'page');
  });

  test('reduced-motion preference collapses public page animation durations', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');

    const motion = await page.evaluate(() => ({
      scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
      durations: document.getAnimations().map((animation) => {
        const duration = animation.effect?.getTiming().duration;
        return typeof duration === 'number' ? duration : 0;
      }),
    }));

    expect(motion.scrollBehavior).toBe('auto');
    expect(motion.durations.every((duration) => duration <= 1)).toBe(true);
  });

  test('contact form handles validation, failure, and success without a dead end', async ({ page }) => {
    let requestCount = 0;
    let shouldSucceed = false;
    await page.route('**/api/leads', async (route) => {
      requestCount += 1;
      await route.fulfill({
        status: shouldSucceed ? 201 : 503,
        contentType: 'application/json',
        body: JSON.stringify(shouldSucceed
          ? { persisted: true, message_to_submitter: 'Your inquiry was saved.' }
          : { detail: 'Contact intake is temporarily unavailable.' }),
      });
    });

    await page.goto('/contact');
    const email = page.getByRole('textbox', { name: 'Work email (required)' });
    const message = page.getByRole('textbox', { name: 'Message (required)' });
    await email.fill('operator@example.com');
    await message.fill('   ');
    await page.getByRole('button', { name: 'Send inquiry' }).click();

    expect(requestCount).toBe(0);
    await expect(message).toBeFocused();
    await expect(message).toHaveAttribute('aria-invalid', 'true');

    await message.fill('We need to validate a governed agent deployment.');
    await page.getByRole('button', { name: 'Send inquiry' }).click();
    await expect(page.getByRole('alert')).toContainText('Contact intake is temporarily unavailable.');

    shouldSucceed = true;
    await page.getByRole('button', { name: 'Send inquiry' }).click();
    await expect(page.getByRole('status')).toContainText('Your inquiry was saved.');
    await expect(page.getByRole('link', { name: 'Email hello@mutx.dev' })).toHaveAttribute('href', 'mailto:hello@mutx.dev');

    await page.getByRole('button', { name: 'Send another inquiry' }).click();
    await expect(page.getByRole('button', { name: 'Send inquiry' })).toBeVisible();
  });
});
