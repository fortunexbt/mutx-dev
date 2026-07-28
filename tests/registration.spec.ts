import { test, expect } from '@playwright/test';

test.describe('Registration Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Mock Cloudflare Turnstile
    await page.route('https://challenges.cloudflare.com/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/javascript',
        body: 'window.turnstile={render:(el,opts)=>{setTimeout(()=>opts?.callback?.("ci-test-token"),0);return "widget-id";},reset:()=>{},remove:()=>{}};',
      });
    });

    // Mock Next.js image optimization
    await page.route('**/_next/image**', async (route) => {
      const url = new URL(route.request().url());
      const originalUrl = url.searchParams.get('url');

      if (!originalUrl || originalUrl.includes('/logo.png')) {
        await route.fulfill({
          status: 200,
          contentType: 'image/png',
          body: Buffer.from(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn8nWsAAAAASUVORK5CYII=',
            'base64'
          ),
        });
        return;
      }

      await route.fallback();
    });
  });

  test('registration page loads and renders all form elements', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('domcontentloaded');

    // Check form fields (using getByPlaceholder as fallback)
    await expect(page.getByPlaceholder('Your name')).toBeVisible();
    await expect(page.getByPlaceholder('you@company.com')).toBeVisible();
    await expect(page.getByPlaceholder('••••••••').first()).toBeVisible();

    // Check submit button
    await expect(page.getByRole('button', { name: /sign up/i })).toBeVisible();

    // Check link to login
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible();
  });

  test('registration form shows error for mismatched passwords', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('domcontentloaded');

    // Fill in the form with mismatched passwords
    await page.getByPlaceholder('Your name').fill('Test User');
    await page.getByPlaceholder('you@company.com').fill('test@example.com');
    await page.getByPlaceholder('••••••••').first().fill('password123');
    await page.getByPlaceholder('••••••••').last().fill('differentpassword');

    // Submit the form
    await page.getByRole('button', { name: /sign up/i }).click();

    // Wait for error message
    await expect(page.getByText(/passwords do not match/i)).toBeVisible();
    await expect(page.getByPlaceholder('••••••••').last()).toBeFocused();
  });

  test('registration form validates password length', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('domcontentloaded');

    // Fill in with short password
    await page.getByPlaceholder('Your name').fill('Test User');
    await page.getByPlaceholder('you@company.com').fill('test@example.com');
    await page.getByPlaceholder('••••••••').first().fill('short');
    await page.getByPlaceholder('••••••••').last().fill('short');

    // Submit the form
    await page.getByRole('button', { name: /sign up/i }).click();

    // Should show validation error for password
    await expect(page.getByText(/password must be at least/i)).toBeVisible();
    await expect(page.getByPlaceholder('••••••••').first()).toBeFocused();
  });

  test('preserves the intended route through the verification handoff', async ({ page }) => {
    let registrationBody: Record<string, unknown> | undefined;

    await page.route('**/api/auth/register', async (route) => {
      registrationBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          requires_email_verification: true,
          verification_email_sent: true,
        }),
      });
    });

    await page.goto('/register?next=%2Fdashboard%2Fruns%3Fstatus%3Dheld');
    await page.getByPlaceholder('Your name').fill('Test User');
    await page.getByPlaceholder('you@company.com').fill('test@example.com');
    await page.getByPlaceholder('••••••••').first().fill('password123');
    await page.getByPlaceholder('••••••••').last().fill('password123');
    await page.getByRole('button', { name: /sign up/i }).click();

    expect(registrationBody?.return_path).toBe('/dashboard/runs?status=held');
    await expect(page).toHaveURL(/\/verify-email\?/);
    const verificationUrl = new URL(page.url());
    expect(verificationUrl.searchParams.get('next')).toBe('/dashboard/runs?status=held');
  });

  test('registration form shows error for existing email', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('domcontentloaded');

    // Mock the registration API to return an error for existing email
    await page.route('**/api/auth/register', async (route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Email already registered' }),
      });
    });

    // Fill in the form
    await page.getByPlaceholder('Your name').fill('Test User');
    await page.getByPlaceholder('you@company.com').fill('existing@example.com');
    await page.getByPlaceholder('••••••••').first().fill('password123');
    await page.getByPlaceholder('••••••••').last().fill('password123');

    // Submit the form
    await page.getByRole('button', { name: /sign up/i }).click();

    // Wait for error message
    await expect(page.getByText(/email already registered/i)).toBeVisible();
  });

  test('registration form shows loading state during submission', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('domcontentloaded');

    // Mock the registration API with a delay
    await page.route('**/api/auth/register', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock-access-token',
          refresh_token: 'mock-refresh-token',
          expires_in: 1800
        }),
      });
    });

    // Fill in the form
    await page.getByPlaceholder('Your name').fill('Test User');
    await page.getByPlaceholder('you@company.com').fill('test@example.com');
    await page.getByPlaceholder('••••••••').first().fill('password123');
    await page.getByPlaceholder('••••••••').last().fill('password123');

    // Submit the form
    await page.getByRole('button', { name: /sign up/i }).click();

    // Check loading state shows
    await expect(page.getByText(/creating account/i)).toBeVisible();

    // Button should be disabled during loading
    await expect(page.getByRole('button', { name: /creating account/i })).toBeDisabled();
  });

  test('successful registration redirects to dashboard', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('domcontentloaded');

    // Mock the registration API to return success
    await page.route('**/api/auth/register', async (route) => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock-access-token',
          refresh_token: 'mock-refresh-token',
          expires_in: 1800
        }),
      });
    });

    // Fill in the form
    await page.getByPlaceholder('Your name').fill('Test User');
    await page.getByPlaceholder('you@company.com').fill('test@example.com');
    await page.getByPlaceholder('••••••••').first().fill('password123');
    await page.getByPlaceholder('••••••••').last().fill('password123');

    // Submit the form
    await page.getByRole('button', { name: /sign up/i }).click();

    // Wait for navigation to dashboard
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test('registration page has working link to login page', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('domcontentloaded');

    // Click the sign in link
    await page.getByRole('link', { name: /sign in/i }).click();

    // Should navigate to login page
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByLabel(/email address/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();
  });

  test('registration form handles empty name input', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('domcontentloaded');

    // Submit with empty name but filled other fields
    await page.getByPlaceholder('you@company.com').fill('test@example.com');
    await page.getByPlaceholder('••••••••').first().fill('password123');
    await page.getByPlaceholder('••••••••').last().fill('password123');

    // Submit the form
    await page.getByRole('button', { name: /sign up/i }).click();

    // HTML5 validation or custom validation should handle empty name
    // Either HTML5 validation or custom error shows - just check form submission was prevented
    // The button should be back to enabled state (not loading)
    await expect(page.getByRole("button", { name: /sign up/i })).toBeEnabled();
  });
});
