import { expect, test, type Page } from '@playwright/test';

const longWebhookId = `wh_${'identifier'.repeat(12)}`;
const longWebhookUrl = `https://hooks.example.com/mutx/${'destination'.repeat(14)}`;
const longEventName = `agent.${'delivery'.repeat(16)}.completed`;

const webhook = {
  id: longWebhookId,
  url: longWebhookUrl,
  events: [longEventName, 'run.failed'],
  is_active: true,
  created_at: '2025-03-20T10:00:00Z',
};

const delivery = {
  id: 'whd_mobile_delivery',
  event: longEventName,
  payload: JSON.stringify({ token: 'unbroken'.repeat(40), run_id: 'run_alpha' }),
  status_code: 502,
  success: false,
  error_message: `Upstream ${'timeout'.repeat(24)}`,
  attempts: 3,
  created_at: '2025-03-21T08:12:00Z',
  delivered_at: null,
};

async function mockWebhookTraffic(page: Page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const method = request.method();

    if (pathname === '/api/auth/me' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '11111111-1111-1111-1111-111111111111',
          email: 'operator@example.com',
          name: 'Operator',
        }),
      });
      return;
    }

    if (pathname === '/api/webhooks' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ webhooks: [webhook] }),
      });
      return;
    }

    if (
      pathname.startsWith('/api/webhooks/') &&
      pathname.endsWith('/deliveries') &&
      method === 'GET'
    ) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ deliveries: [delivery] }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(method === 'GET' ? {} : { ok: true }),
    });
  });
}

async function openWebhookPage(page: Page) {
  await mockWebhookTraffic(page);
  await page.goto('/dashboard/webhooks', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Webhooks' }).first()).toBeVisible();
  await expect(page.getByText(longWebhookUrl)).toBeVisible({ timeout: 15000 });
}

async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(
    dimensions.scrollWidth,
    `document overflowed: ${dimensions.scrollWidth}px > ${dimensions.clientWidth}px`,
  ).toBeLessThanOrEqual(dimensions.clientWidth + 1);
}

test.describe('Webhook component accessibility', () => {
  test('leaves Cmd/Ctrl+K to the global palette and announces clipboard results', async ({ page }) => {
    await page.addInitScript(() => {
      let attempts = 0;
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          writeText: async () => {
            attempts += 1;
            if (attempts === 1) {
              throw new DOMException('Clipboard denied', 'NotAllowedError');
            }
          },
        },
      });
    });

    await openWebhookPage(page);

    const search = page.getByRole('searchbox', { name: 'Search webhooks' });
    await expect(search).toHaveAttribute('placeholder', 'Search webhooks by URL, ID, or event');

    await page.keyboard.press('Control+K');
    await expect(page.getByRole('dialog', { name: /go anywhere/i })).toBeVisible();
    await expect(search).not.toBeFocused();
    await page.keyboard.press('Escape');

    const copyButton = page.getByRole('button', { name: `Copy webhook ID ${longWebhookId}` });
    const copyTarget = await copyButton.boundingBox();
    expect(copyTarget).not.toBeNull();
    expect(copyTarget!.width).toBeGreaterThanOrEqual(24);
    expect(copyTarget!.height).toBeGreaterThanOrEqual(24);

    await copyButton.click();
    const copyFeedback = page.locator('[role="status"][aria-atomic="true"]');
    await expect(copyFeedback).toContainText(
      'Could not copy the webhook ID. Clipboard access was denied.',
    );

    await copyButton.click();
    await expect(copyFeedback).toContainText('Webhook ID copied to clipboard.');
  });

  test('exposes delivery rows as controlled disclosures', async ({ page }) => {
    await openWebhookPage(page);
    await page.getByRole('button', { name: 'View delivery history' }).click();

    const disclosure = page.getByRole('button', {
      name: `Expand ${longEventName} delivery details`,
    });
    await expect(disclosure).toHaveAttribute('aria-expanded', 'false');

    const detailsId = await disclosure.getAttribute('aria-controls');
    expect(detailsId).toBeTruthy();
    await expect(page.locator(`#${detailsId}`)).toBeHidden();

    await disclosure.click();
    await expect(disclosure).toHaveAttribute('aria-expanded', 'true');
    await expect(disclosure).toHaveAccessibleName(
      `Collapse ${longEventName} delivery details`,
    );
    await expect(page.locator(`#${detailsId}`)).toBeVisible();
  });
});

test.describe('Webhook component at 320px', () => {
  test.use({
    viewport: { width: 320, height: 800 },
    isMobile: true,
    hasTouch: true,
  });

  test('stacks card actions and keeps cards and expanded deliveries in the viewport', async ({ page }) => {
    await openWebhookPage(page);

    const historyButton = page.getByRole('button', { name: 'View delivery history' });
    const webhookUrl = page.getByText(longWebhookUrl);
    const [historyBox, urlBox] = await Promise.all([
      historyButton.boundingBox(),
      webhookUrl.boundingBox(),
    ]);

    expect(historyBox).not.toBeNull();
    expect(urlBox).not.toBeNull();
    expect(historyBox!.y).toBeGreaterThanOrEqual(urlBox!.y + urlBox!.height);

    for (const name of [
      'View delivery history',
      'Test webhook',
      'Edit webhook',
      'Delete webhook',
    ]) {
      const bounds = await page.getByRole('button', { name }).boundingBox();
      expect(bounds, `${name} should have a rendered target`).not.toBeNull();
      expect(bounds!.x, `${name} should stay inside the left edge`).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width, `${name} should stay inside the right edge`).toBeLessThanOrEqual(321);
    }

    await expectNoHorizontalOverflow(page);

    await historyButton.click();
    const disclosure = page.getByRole('button', {
      name: `Expand ${longEventName} delivery details`,
    });
    await disclosure.click();

    const detailsId = await disclosure.getAttribute('aria-controls');
    expect(detailsId).toBeTruthy();
    const details = page.locator(`#${detailsId}`);
    await expect(details).toBeVisible();

    const deliveryMetrics = await details.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      left: element.getBoundingClientRect().left,
      right: element.getBoundingClientRect().right,
    }));
    expect(deliveryMetrics.scrollWidth).toBeLessThanOrEqual(deliveryMetrics.clientWidth + 1);
    expect(deliveryMetrics.left).toBeGreaterThanOrEqual(0);
    expect(deliveryMetrics.right).toBeLessThanOrEqual(321);
    await expectNoHorizontalOverflow(page);
  });
});
