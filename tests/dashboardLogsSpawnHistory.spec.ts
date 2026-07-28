import { expect, test, type Page } from '@playwright/test'

const runSummary = {
  id: 'run-contract-1',
  agent_id: null,
  status: 'completed',
  input_text: 'Build the release receipt',
  output_text: 'Receipt stored',
  error_message: null,
  metadata: {},
  started_at: '2026-07-28T10:00:00Z',
  completed_at: '2026-07-28T10:00:04Z',
  created_at: '2026-07-28T10:00:00Z',
  trace_count: 1,
  subject_type: 'document_job',
  subject_id: 'job-contract-1',
  subject_label: 'Release receipt',
  execution_mode: 'operator',
}

const trace = {
  id: 'trace-contract-1',
  run_id: runSummary.id,
  event_type: 'workflow.completed',
  message: 'The release receipt was stored with its provenance.',
  payload: { artifact_id: 'artifact-contract-1' },
  sequence: 0,
  timestamp: '2026-07-28T10:00:04Z',
}

async function mockWorkflowTraffic(page: Page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (url.pathname === '/api/auth/me') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'operator-contract', email: 'operator@mutx.dev' }),
      })
      return
    }

    if (url.pathname === '/api/dashboard/agents' && request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
      return
    }

    if (url.pathname === '/api/dashboard/runs' && request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [runSummary],
          total: 1,
          skip: 0,
          limit: 48,
          has_more: false,
          agent_id: null,
          status: null,
        }),
      })
      return
    }

    if (
      url.pathname === `/api/dashboard/runs/${runSummary.id}` &&
      request.method() === 'GET'
    ) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...runSummary, traces: [trace] }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    })
  })
}

test.describe('Logs, Spawn, and History contracts', () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkflowTraffic(page)
  })

  test('spawn opens agent creation from the create query contract', async ({ page }) => {
    await page.goto('/dashboard/spawn', { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(/\/dashboard\/agents\?create=1$/)
    await expect(page.getByRole('dialog', { name: 'Create Agent' })).toBeVisible()

    await page.getByRole('button', { name: 'Close dialog' }).click()
    await expect(page).toHaveURL(/\/dashboard\/agents$/)
  })

  test('history remains on history and renders nullable-agent run activity', async ({ page }) => {
    await page.goto('/dashboard/history', { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(/\/dashboard\/history$/)
    await expect(page.getByRole('heading', { name: 'History' })).toBeVisible()
    await expect(page.getByText('Execution history')).toBeVisible()
    await expect(page.getByText('Unassigned')).toBeVisible()
    await expect(page.getByText('workflow.completed')).toBeVisible()
    await expect(page.getByText(trace.message)).toBeVisible()
  })

  test('logs renders embedded run traces instead of a synthetic step sequence', async ({ page }) => {
    await page.goto('/dashboard/logs', { waitUntil: 'domcontentloaded' })

    await expect(page.getByRole('heading', { name: 'Logs' })).toBeVisible()
    await expect(page.getByText('Run traces')).toBeVisible()
    await expect(page.getByText('workflow.completed')).toBeVisible()
    await expect(page.getByText('No step data')).toHaveCount(0)
  })
})
