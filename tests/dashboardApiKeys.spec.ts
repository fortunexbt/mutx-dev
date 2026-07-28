import { expect, test } from '@playwright/test';

const mockKey = {
  id: 'key_alpha',
  name: 'Production operator',
  created_at: '2025-03-18T09:00:00Z',
  expires_at: null,
  is_active: true,
  status: 'active',
  last_used_at: '2025-03-21T08:00:00Z',
};

async function openApiKeysPage(page: import('@playwright/test').Page) {
  await page.goto('/dashboard/api-keys', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'API Keys' })).toBeVisible({ timeout: 10000 });
  await expect(page.getByText('Production operator')).toBeVisible({ timeout: 10000 });
}

test.describe('Dashboard API key confirmations', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'operator_alpha',
          email: 'operator@mutx.dev',
          name: 'Operator',
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

  test('requires an accessible confirmation before rotation and exposes pending state', async ({ page }) => {
    let rotateRequests = 0;
    let releaseRotation: (() => void) | undefined;
    const rotationGate = new Promise<void>((resolve) => {
      releaseRotation = resolve;
    });

    await page.route('**/api/api-keys/key_alpha/rotate', async (route) => {
      rotateRequests += 1;
      await rotationGate;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'key_rotated',
          name: 'Production operator',
          key: 'mutx_live_rotated_once',
          created_at: '2025-03-21T09:00:00Z',
        }),
      });
    });

    await openApiKeysPage(page);
    await page.getByRole('button', { name: 'Rotate', exact: true }).click();

    const dialog = page.getByRole('dialog', { name: 'Rotate API key?' });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('invalidates its current secret immediately');
    await expect(dialog).toContainText('replacement secret is shown only once');
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();
    expect(rotateRequests).toBe(0);

    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    expect(rotateRequests).toBe(0);
    await expect(page.getByRole('button', { name: 'Rotate', exact: true })).toBeFocused();

    await page.getByRole('button', { name: 'Rotate', exact: true }).click();
    await page.getByRole('button', { name: 'Rotate and invalidate' }).click();

    await expect(page.getByRole('button', { name: 'Rotating...' })).toBeDisabled();
    await expect(page.getByRole('status')).toContainText('reloading the canonical key registry');
    expect(rotateRequests).toBe(1);

    releaseRotation?.();
    await expect(page.getByText('mutx_live_rotated_once')).toBeVisible();
    await expect(dialog).toHaveCount(0);
  });

  test('does not revoke until confirmation and canonically reloads after success', async ({ page }) => {
    let revoked = false;
    let listRequests = 0;
    let revokeRequests = 0;

    await page.route('**/api/api-keys', async (route) => {
      listRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: revoked ? [] : [mockKey] }),
      });
    });
    await page.route('**/api/api-keys/key_alpha', async (route) => {
      revokeRequests += 1;
      revoked = true;
      await route.fulfill({ status: 204 });
    });

    await openApiKeysPage(page);
    await page.getByRole('button', { name: 'Revoke', exact: true }).click();

    const dialog = page.getByRole('dialog', { name: 'Revoke API key?' });
    await expect(dialog).toContainText('invalidates it immediately');
    await expect(dialog).toContainText('Integrations using this key will stop authenticating');
    expect(revokeRequests).toBe(0);

    await dialog.getByRole('button', { name: 'Revoke and invalidate' }).click();

    await expect(page.getByText('No API keys provisioned yet')).toBeVisible();
    expect(revokeRequests).toBe(1);
    expect(listRequests).toBe(2);
  });

  test('keeps the confirmation open and announces a rotation conflict', async ({ page }) => {
    await page.route('**/api/api-keys/key_alpha/rotate', async (route) => {
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Key rotation is already in progress' }),
      });
    });

    await openApiKeysPage(page);
    await page.getByRole('button', { name: 'Rotate', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Rotate API key?' });
    await dialog.getByRole('button', { name: 'Rotate and invalidate' }).click();

    await expect(dialog.getByRole('alert')).toHaveText('Key rotation is already in progress');
    await expect(dialog).toBeVisible();
  });

  test('associates create errors with the form on a server failure', async ({ page }) => {
    await page.route('**/api/api-keys', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Credential store unavailable' }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [mockKey] }),
      });
    });

    await openApiKeysPage(page);
    await page.getByRole('button', { name: 'Create key' }).click();

    const error = page.getByRole('alert').filter({ hasText: 'Credential store unavailable' });
    await expect(error).toBeVisible();
    await expect(page.locator('form')).toHaveAttribute('aria-describedby', /api-key-create-error/);
    await expect(page.getByLabel('Key name')).toHaveAttribute('aria-describedby', 'api-key-name-help');
  });
});

test.describe('Dashboard API key authorization states', () => {
  for (const status of [401, 403]) {
    test(`renders the operator-session state for ${status}`, async ({ page }) => {
      await page.route('**/api/api-keys', async (route) => {
        await route.fulfill({
          status,
          contentType: 'application/json',
          body: JSON.stringify({ detail: status === 401 ? 'Session expired' : 'Forbidden' }),
        });
      });

      await page.goto('/dashboard/api-keys', { waitUntil: 'domcontentloaded' });

      await expect(page.getByText('Operator session required')).toBeVisible({ timeout: 10000 });
    });
  }
});
