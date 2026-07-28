import { expect, test, type Page, type Route } from '@playwright/test';

async function stubPicoSession(page: Page, plan = 'FREE') {
  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        email: 'operator@mutx.dev',
        name: 'Pico Operator',
        role: 'USER',
        plan,
        is_email_verified: true,
      }),
    });
  });
}

async function fulfillSubscription(route: Route, plan: 'FREE' | 'STARTER' | 'PRO') {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      plan,
      status: plan === 'FREE' ? null : 'active',
      current_period_end: null,
      cancel_at_period_end: false,
      trial_end: null,
    }),
  });
}

test.describe('Pico paid checkout', () => {
  test('submits a stable plan id and confirms a valid checkout_url response', async ({ page }) => {
    await stubPicoSession(page);
    let checkoutBody: unknown = null;
    let activePlan: 'FREE' | 'STARTER' = 'FREE';

    await page.route('**/api/pico/checkout', async (route) => {
      if (route.request().method() === 'GET') {
        await fulfillSubscription(route, activePlan);
        return;
      }

      checkoutBody = route.request().postDataJSON();
      activePlan = 'STARTER';
      const origin = new URL(route.request().url()).origin;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          checkout_url: `${origin}/pico/pricing?checkout=success&plan=starter&session_id=cs_test`,
          session_id: 'cs_test',
        }),
      });
    });

    await page.goto('/pico/pricing');
    await page.getByRole('button', { name: /choose starter/i }).click();

    await expect(page.getByTestId('pico-checkout-notice')).toContainText(
      /your starter plan is active/i,
    );
    const starterPlan = page.locator('article').filter({
      has: page.getByRole('heading', { name: /^starter$/i }),
    });
    await expect(starterPlan.getByText(/^current$/i)).toBeVisible();
    await expect(page.getByText(/checkout failed/i)).toHaveCount(0);
    expect(checkoutBody).toEqual({ planId: 'starter' });
    expect(JSON.stringify(checkoutBody)).not.toContain('price_');
    await expect.poll(() => new URL(page.url()).searchParams.has('checkout')).toBe(false);
    expect(new URL(page.url()).searchParams.has('session_id')).toBe(false);
  });

  test('reports cancellation truthfully and removes transient return parameters', async ({ page }) => {
    await stubPicoSession(page);
    await page.route('**/api/pico/checkout', async (route) => {
      await fulfillSubscription(route, 'FREE');
    });

    await page.goto('/pico/pricing?checkout=canceled&plan=pro&session_id=cs_unused');

    await expect(page.getByTestId('pico-checkout-notice')).toContainText(
      /checkout was canceled.*current plan has not changed/i,
    );
    await expect.poll(() => new URL(page.url()).searchParams.has('checkout')).toBe(false);
    expect(new URL(page.url()).searchParams.has('session_id')).toBe(false);
    expect(new URL(page.url()).searchParams.get('plan')).toBe('pro');
  });

  test('surfaces unavailable checkout and retries the same stable plan', async ({ page }) => {
    await stubPicoSession(page);
    let postCount = 0;
    let activePlan: 'FREE' | 'PRO' = 'FREE';

    await page.route('**/api/pico/checkout', async (route) => {
      if (route.request().method() === 'GET') {
        await fulfillSubscription(route, activePlan);
        return;
      }

      postCount += 1;
      if (postCount === 1) {
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: "Stripe price for plan 'pro' is not configured" }),
        });
        return;
      }

      expect(route.request().postDataJSON()).toEqual({ planId: 'pro' });
      activePlan = 'PRO';
      const origin = new URL(route.request().url()).origin;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          checkout_url: `${origin}/pico/pricing?checkout=success&plan=pro&session_id=cs_retry`,
          session_id: 'cs_retry',
        }),
      });
    });

    await page.goto('/pico/pricing');
    await page.getByRole('button', { name: /choose pro/i }).click();
    await expect(page.getByRole('alert')).toContainText(/temporarily unavailable/i);

    await page.getByRole('button', { name: /retry checkout/i }).click();

    await expect(page.getByTestId('pico-checkout-notice')).toContainText(
      /your pro plan is active/i,
    );
    expect(postCount).toBe(2);
  });

  test('redirects an expired checkout session to sign-in with a safe return path', async ({ page }) => {
    await stubPicoSession(page);
    await page.route('**/api/pico/checkout', async (route) => {
      if (route.request().method() === 'GET') {
        await fulfillSubscription(route, 'FREE');
        return;
      }
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'error',
          error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
        }),
      });
    });

    await page.goto('/pico/pricing');
    await page.getByRole('button', { name: /choose starter/i }).click();
    await page.waitForURL('**/login?next=*');

    const next = new URL(page.url()).searchParams.get('next');
    expect(next).toBe('/pico/pricing?plan=starter');
  });

  test('explains an entitlement denial without redirecting or leaking backend detail', async ({
    page,
  }) => {
    await stubPicoSession(page);
    await page.route('**/api/pico/checkout', async (route) => {
      if (route.request().method() === 'GET') {
        await fulfillSubscription(route, 'FREE');
        return;
      }
      await route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'internal-rbac-policy-name' }),
      });
    });

    await page.goto('/pico/pricing');
    await page.getByRole('button', { name: /choose starter/i }).click();

    await expect(page.getByRole('alert')).toContainText(/does not have access to checkout/i);
    await expect(page.getByRole('alert')).not.toContainText(/internal-rbac-policy-name/i);
    expect(new URL(page.url()).pathname).toBe('/pico/pricing');
  });
});
