import { test, expect } from '@playwright/test';

const mockAgents = [
  {
    id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    name: 'test-agent-1',
    status: 'running',
    description: 'A test agent for e2e testing',
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-16T14:30:00Z',
  },
  {
    id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
    name: 'test-agent-2',
    status: 'stopped',
    description: 'Another test agent',
    created_at: '2024-01-14T09:00:00Z',
    updated_at: '2024-01-15T18:00:00Z',
  },
  {
    id: 'c3d4e5f6-a7b8-9012-cdef-123456789012',
    name: 'test-agent-3',
    status: 'failed',
    description: 'A failed agent',
    created_at: '2024-01-10T08:00:00Z',
    updated_at: '2024-01-12T12:00:00Z',
  },
];

async function openAgentsPage(page: import('@playwright/test').Page) {
  await page.goto('/dashboard/agents', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: /agents/i })).toBeVisible({ timeout: 10000 });
}

test.describe('Dashboard Agents List', () => {
  test.beforeEach(async ({ page }) => {
    // Mock Turnstile for any pages that might check it
    await page.route('https://challenges.cloudflare.com/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/javascript',
        body: 'window.turnstile={render:(el,opts)=>{setTimeout(()=>opts?.callback?.("ci-test-token"),0);return "widget-id";},reset:()=>{},remove:()=>{}};',
      });
    });

    // Mock Next.js image optimization
    await page.route('**/_next/image**', async (route) => {
      await route.fallback();
    });

    // Mock the dashboard agents API with default data
    await page.route('**/api/dashboard/agents**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: mockAgents,
          total: mockAgents.length,
          skip: 0,
          limit: 20,
          has_more: false,
        }),
      });
    });

    await page.route('/api/auth/me', async (route) => {
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
  });

  test('page loads and displays agent list', async ({ page }) => {
    await openAgentsPage(page);

    // Check page title
    await expect(page.getByRole('heading', { name: /agents/i })).toBeVisible();

    // Check agent cards are displayed
    await expect(page.getByRole('heading', { name: 'test-agent-1' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'test-agent-2' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'test-agent-3' })).toBeVisible();
  });

  test('search filters agents correctly', async ({ page }) => {
    await openAgentsPage(page);

    // Wait for agents to load
    await expect(page.getByRole('heading', { name: 'test-agent-1' })).toBeVisible();

    // Search for a specific agent
    const searchInput = page.getByPlaceholder(/search agents/i);
    await searchInput.fill('test-agent-1');

    // Should show only matching agent
    await expect(page.getByRole('heading', { name: 'test-agent-1' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'test-agent-2' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'test-agent-3' })).toHaveCount(0);

    // Should show "No matching agents" when no results
    await searchInput.fill('nonexistent');
    await expect(page.getByText(/no matching agents/i)).toBeVisible();
  });

  test('keeps the global command palette shortcut and uses slash for local search', async ({ page }) => {
    await openAgentsPage(page);

    await page.keyboard.press('Control+K');
    await expect(page.getByRole('dialog', { name: 'Go anywhere' })).toBeVisible();

    await page.keyboard.press('Escape');
    await page.keyboard.press('/');
    await expect(page.getByPlaceholder(/search agents/i)).toBeFocused();
  });

  test('provides keyboard-focusable inspect navigation to agent details', async ({ page }) => {
    await openAgentsPage(page);

    const inspectLink = page.getByRole('link', { name: 'Inspect test-agent-1' });
    await expect(inspectLink).toHaveAttribute(
      'href',
      `/dashboard/agents/${mockAgents[0].id}`,
    );
    await inspectLink.focus();
    await expect(inspectLink).toBeFocused();
    await inspectLink.press('Enter');
    await expect(page).toHaveURL(`/dashboard/agents/${mockAgents[0].id}`);
  });

  test('associates create-agent labels and submission errors with the form', async ({ page }) => {
    await page.route('**/api/dashboard/agents**', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Agent registry unavailable' }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: mockAgents,
          total: mockAgents.length,
          skip: 0,
          limit: 20,
          has_more: false,
        }),
      });
    });

    await openAgentsPage(page);
    await page.getByRole('button', { name: 'Create Agent' }).click();

    await expect(page.getByLabel('Name *')).toBeVisible();
    await expect(page.getByLabel('Description')).toBeVisible();
    await expect(page.getByLabel('Type')).toBeVisible();
    await page.getByLabel('Name *').fill('unavailable-agent');
    await page.getByRole('button', { name: 'Create Agent' }).last().click();

    await expect(page.getByRole('alert')).toHaveText('Agent registry unavailable');
    await expect(page.locator('#create-agent-form')).toHaveAttribute(
      'aria-describedby',
      'create-agent-form-error',
    );
  });

  test('loads subsequent pages from the authoritative pagination envelope', async ({ page }) => {
    const firstPage = mockAgents.slice(0, 2);
    const secondPage = mockAgents.slice(2);
    const requestedSkips: string[] = [];

    await page.route('**/api/dashboard/agents**', async (route) => {
      const url = new URL(route.request().url());
      const skip = url.searchParams.get('skip') ?? '0';
      requestedSkips.push(skip);
      const items = skip === '0' ? firstPage : secondPage;

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items,
          total: mockAgents.length,
          skip: Number(skip),
          limit: 2,
          has_more: skip === '0',
        }),
      });
    });

    await openAgentsPage(page);

    await expect(page.getByRole('heading', { name: 'test-agent-3' })).toHaveCount(0);
    const loadMore = page.getByRole('button', { name: 'Load more (2 of 3)' });
    await expect(loadMore).toBeVisible();
    await loadMore.click();

    await expect(page.getByRole('heading', { name: 'test-agent-3' })).toBeVisible();
    expect(requestedSkips).toEqual(['0', '2']);
    await expect(page.getByRole('button', { name: /load more/i })).toHaveCount(0);
  });

  test('refresh button works', async ({ page }) => {
    await openAgentsPage(page);

    // Wait for initial load
    await expect(page.getByRole('heading', { name: 'test-agent-1' })).toBeVisible();

    // Track API calls
    let apiCallCount = 0;
    await page.route('**/api/dashboard/agents**', async (route) => {
      apiCallCount++;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: mockAgents,
          total: mockAgents.length,
          skip: 0,
          limit: 20,
          has_more: false,
        }),
      });
    });

    // Click refresh button
    const refreshButton = page.getByRole('button', { name: /refresh/i });
    await refreshButton.click();

    // Should have made another API call
    expect(apiCallCount).toBeGreaterThan(0);
  });

  test('displays agent status correctly', async ({ page }) => {
    await openAgentsPage(page);

    // Check that agent statuses are displayed
    const runningCard = page.locator('article').filter({ hasText: 'test-agent-1' }).first();
    const stoppedCard = page.locator('article').filter({ hasText: 'test-agent-2' }).first();
    const failedCard = page.locator('article').filter({ hasText: 'test-agent-3' }).first();

    await expect(runningCard).toContainText('running');
    await expect(stoppedCard).toContainText('stopped');
    await expect(failedCard).toContainText('failed');
  });

  test('displays empty state when no agents', async ({ page }) => {
    // Mock the API to return empty array - must come BEFORE goto
    await page.route('**/api/dashboard/agents**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, skip: 0, limit: 20, has_more: false }),
      });
    });

    await openAgentsPage(page);

    // Should show empty state
    await expect(page.getByText('No agents found')).toBeVisible({ timeout: 10000 });
  });

  test('search by agent ID works', async ({ page }) => {
    await openAgentsPage(page);

    // Search by partial ID
    const searchInput = page.getByPlaceholder(/search agents/i);
    await searchInput.fill('a1b2c3d4');

    // Should show matching agent
    await expect(page.getByRole('heading', { name: 'test-agent-1' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'test-agent-2' })).toHaveCount(0);
  });

  test('search by description works', async ({ page }) => {
    await openAgentsPage(page);

    // Search by description text
    const searchInput = page.getByPlaceholder(/search agents/i);
    await searchInput.fill('e2e testing');

    // Should show matching agent
    await expect(page.getByRole('heading', { name: 'test-agent-1' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'test-agent-2' })).toHaveCount(0);
  });
});
