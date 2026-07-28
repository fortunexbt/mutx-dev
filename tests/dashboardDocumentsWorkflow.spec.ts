import { expect, test } from '@playwright/test'

const documentTemplate = {
  id: 'document_analysis',
  name: 'Document Analysis',
  summary: 'Analyze documents.',
  description: 'Create a report from managed document inputs.',
  supports_managed: true,
  supports_local: true,
  max_upload_bytes: 8,
  inputs: [
    {
      name: 'documents',
      type: 'artifact',
      required: true,
      accepts_multiple: true,
      description: 'Documents to analyze.',
    },
  ],
  outputs: [],
}

function failedJob(status = 'failed') {
  return {
    id: 'job-failed-123',
    run_id: 'run-failed-123',
    template_id: 'document_analysis',
    execution_mode: 'managed',
    status,
    parameters: {},
    result_summary: {},
    error_message: status === 'failed' ? 'Managed submission failed during upload' : null,
    created_at: '2026-07-28T10:00:00Z',
    completed_at: '2026-07-28T10:00:01Z',
    artifacts: status === 'failed'
      ? [{
          id: 'artifact-123',
          role: 'documents',
          kind: 'file',
          storage_backend: 'managed',
          filename: 'partial.txt',
        }]
      : [],
  }
}

test.describe('managed document workflow integrity', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'operator-documents',
          email: 'documents@mutx.dev',
          name: 'Document Operator',
        }),
      })
    })
  })

  test('rejects missing and oversized files before creating canonical history', async ({ page }) => {
    let submissions = 0
    await page.route('**/api/dashboard/documents/**', async (route) => {
      const pathname = new URL(route.request().url()).pathname
      if (pathname.endsWith('/templates')) {
        await route.fulfill({ status: 200, json: [documentTemplate] })
        return
      }
      if (pathname.endsWith('/jobs') && route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          json: { items: [], total: 0, skip: 0, limit: 20, has_more: false },
        })
        return
      }
      if (pathname.endsWith('/submit')) {
        submissions += 1
      }
      await route.fulfill({ status: 500, json: { detail: 'Unexpected submission' } })
    })

    await page.goto('/dashboard/documents')
    await expect(page.getByRole('heading', { name: 'Documents' })).toBeVisible()

    await page.getByRole('button', { name: 'Submit managed job' }).click()
    await expect(page.getByText(/missing required inputs.*documents/i)).toBeVisible()
    expect(submissions).toBe(0)

    await page.locator('input[type="file"]').setInputFiles({
      name: 'oversized.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('larger than eight bytes'),
    })
    await page.getByRole('button', { name: 'Submit managed job' }).click()
    await expect(page.getByText(/oversized\.txt exceeds.*per-file limit/i)).toBeVisible()
    expect(submissions).toBe(0)
  })

  test('shows canonical failed state and offers recoverable cleanup', async ({ page }) => {
    let jobs: ReturnType<typeof failedJob>[] = []
    let cleanupCalls = 0
    await page.route('**/api/dashboard/documents/**', async (route) => {
      const pathname = new URL(route.request().url()).pathname
      if (pathname.endsWith('/templates')) {
        await route.fulfill({ status: 200, json: [documentTemplate] })
        return
      }
      if (pathname.endsWith('/jobs') && route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          json: { items: jobs, total: jobs.length, skip: 0, limit: 20, has_more: false },
        })
        return
      }
      if (pathname.endsWith('/submit')) {
        jobs = [failedJob()]
        await route.fulfill({
          status: 500,
          json: {
            detail: 'Upload failed; job remains failed and can be retried or cleaned up.',
          },
        })
        return
      }
      if (pathname.endsWith('/cleanup')) {
        cleanupCalls += 1
        jobs = [failedJob('cancelled')]
        await route.fulfill({ status: 200, json: jobs[0] })
        return
      }
      await route.fulfill({ status: 404, json: { detail: 'Not found' } })
    })

    await page.goto('/dashboard/documents')
    await page.locator('input[type="file"]').setInputFiles({
      name: 'brief.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('brief'),
    })
    await page.getByRole('button', { name: 'Submit managed job' }).click()

    await expect(page.getByText(/document service error.*review canonical history/i)).toBeVisible()
    await expect(page.getByText(/retry with the unchanged files/i)).toBeVisible()
    await expect(page.getByText('partial.txt')).toBeVisible()

    await page.getByRole('button', { name: 'Cancel and clean up' }).click()
    expect(cleanupCalls).toBe(1)
    await expect(page.getByText(/cancelled/i).last()).toBeVisible()
    await expect(page.getByText('partial.txt')).toHaveCount(0)
  })
})
