import type { NextRequest } from 'next/server'

import { ApiRequestError } from '../../components/app/http'
import {
  describeDocumentRequestError,
  type DocumentTemplate,
  validateManagedDocumentSubmission,
} from '../../components/dashboard/DocumentsPageClient'

const applyAuthCookies = jest.fn()
const authenticatedFetch = jest.fn()
const hasAuthSession = jest.fn()
const proxyJson = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl: () => 'http://localhost:8000',
  hasAuthSession,
}))

jest.mock('../../app/api/_lib/proxy', () => ({
  proxyJson,
}))

const templateInputs: Record<string, DocumentTemplate['inputs']> = {
  document_analysis: [
    { name: 'documents', type: 'artifact', required: true, accepts_multiple: true },
  ],
  contract_comparison: [
    { name: 'base_document', type: 'artifact', required: true, accepts_multiple: false },
    { name: 'comparison_document', type: 'artifact', required: true, accepts_multiple: false },
  ],
  invoice_extraction: [
    { name: 'documents', type: 'artifact', required: true, accepts_multiple: true },
  ],
  document_redaction: [
    { name: 'documents', type: 'artifact', required: true, accepts_multiple: true },
    { name: 'redaction_policy', type: 'string', required: true, accepts_multiple: false },
  ],
}

function template(id: string): DocumentTemplate {
  return {
    id,
    name: id,
    summary: 'summary',
    description: 'description',
    supports_managed: true,
    supports_local: true,
    max_upload_bytes: 10,
    inputs: templateInputs[id],
  }
}

function file(name: string, size = 5) {
  return { name, size } as File
}

describe('managed document prevalidation', () => {
  it.each([
    ['document_analysis', {}, [{ role: 'documents', file: file('analysis.txt') }]],
    [
      'contract_comparison',
      {},
      [
        { role: 'base_document', file: file('base.txt') },
        { role: 'comparison_document', file: file('comparison.txt') },
      ],
    ],
    ['invoice_extraction', {}, [{ role: 'documents', file: file('invoice.pdf') }]],
    [
      'document_redaction',
      { redaction_policy: 'Remove secrets' },
      [{ role: 'documents', file: file('secret.txt') }],
    ],
  ])('accepts all required inputs for %s', (templateId, parameters, uploads) => {
    expect(
      validateManagedDocumentSubmission(template(templateId as string), parameters, uploads),
    ).toBeNull()
  })

  it.each([
    ['document_analysis', {}, [], 'documents'],
    [
      'contract_comparison',
      {},
      [{ role: 'base_document', file: file('base.txt') }],
      'comparison_document',
    ],
    ['invoice_extraction', {}, [], 'documents'],
    [
      'document_redaction',
      {},
      [{ role: 'documents', file: file('secret.txt') }],
      'redaction_policy',
    ],
  ])('rejects missing required inputs for %s', (templateId, parameters, uploads, missing) => {
    expect(
      validateManagedDocumentSubmission(template(templateId as string), parameters, uploads),
    ).toContain(missing)
  })

  it.each([
    ['document_analysis', [{ role: 'documents', file: file('analysis.txt', 11) }]],
    [
      'contract_comparison',
      [
        { role: 'base_document', file: file('base.txt', 11) },
        { role: 'comparison_document', file: file('comparison.txt') },
      ],
    ],
    ['invoice_extraction', [{ role: 'documents', file: file('invoice.pdf', 11) }]],
    ['document_redaction', [{ role: 'documents', file: file('secret.txt', 11) }]],
  ])('rejects oversized inputs for %s before submission', (templateId, uploads) => {
    const parameters = templateId === 'document_redaction'
      ? { redaction_policy: 'Remove secrets' }
      : {}
    expect(
      validateManagedDocumentSubmission(template(templateId as string), parameters, uploads),
    ).toMatch(/exceeds the .* per-file limit/i)
  })

  it('rejects empty files before submission', () => {
    expect(
      validateManagedDocumentSubmission(
        template('document_analysis'),
        {},
        [{ role: 'documents', file: file('empty.txt', 0) }],
      ),
    ).toMatch(/empty\.txt is empty/i)
  })
})

describe('document workflow error classification', () => {
  it.each([
    [401, 'Authentication required'],
    [403, 'Permission denied'],
    [404, 'not found'],
    [409, 'Submission conflict'],
    [413, 'Upload rejected'],
    [429, 'quota exceeded'],
    [503, 'service unavailable'],
    [500, 'service error'],
  ])('distinguishes HTTP %i', (status, expected) => {
    expect(describeDocumentRequestError(new ApiRequestError('upstream detail', status))).toContain(
      expected,
    )
  })

  it('does not claim execution after a network failure', () => {
    expect(describeDocumentRequestError(new TypeError('fetch failed'))).toMatch(
      /Network error.*No execution was confirmed/i,
    )
  })
})

describe('document submission and cleanup proxies', () => {
  beforeEach(() => {
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    proxyJson.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  function submissionRequest() {
    const formData = new FormData()
    formData.append('template_id', 'document_analysis')
    return {
      headers: new Headers({ 'Idempotency-Key': 'submission-key-123' }),
      formData: async () => formData,
      formDataValue: formData,
    }
  }

  it('forwards multipart submissions with their idempotency key', async () => {
    authenticatedFetch.mockResolvedValue({
      response: new Response(JSON.stringify({ id: 'job_123', status: 'queued' }), {
        status: 200,
      }),
      tokenRefreshed: false,
    })
    const { POST } = await import(
      '../../app/api/dashboard/documents/jobs/submit/route'
    )
    const requestShape = submissionRequest()
    const request = requestShape as unknown as NextRequest

    const response = await POST(request)

    expect(authenticatedFetch).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/documents/jobs/submit',
      {
        method: 'POST',
        headers: { 'Idempotency-Key': 'submission-key-123' },
        body: requestShape.formDataValue,
      },
    )
    expect(response.status).toBe(200)
  })

  it.each([401, 403, 404, 409, 413, 429, 500])(
    'preserves upstream submission status %i',
    async (status) => {
      authenticatedFetch.mockResolvedValue({
        response: new Response(JSON.stringify({ detail: `status ${status}` }), { status }),
        tokenRefreshed: false,
      })
      const { POST } = await import(
        '../../app/api/dashboard/documents/jobs/submit/route'
      )

      const response = await POST(submissionRequest() as unknown as NextRequest)

      expect(response.status).toBe(status)
      await expect(response.json()).resolves.toEqual({ detail: `status ${status}` })
    },
  )

  it('returns a distinct 503 when the document service is unreachable', async () => {
    authenticatedFetch.mockRejectedValue(new TypeError('fetch failed'))
    const { POST } = await import(
      '../../app/api/dashboard/documents/jobs/submit/route'
    )

    const response = await POST(submissionRequest() as unknown as NextRequest)

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: 'SERVICE_UNAVAILABLE' },
    })
  })

  it('encodes cleanup IDs before proxying', async () => {
    proxyJson.mockResolvedValue(new Response(JSON.stringify({ status: 'cancelled' }), {
      status: 200,
    }))
    const { POST } = await import(
      '../../app/api/dashboard/documents/jobs/[jobId]/cleanup/route'
    )
    const request = {} as NextRequest

    await POST(request, { params: Promise.resolve({ jobId: 'job/with space' }) })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/documents/jobs/job%2Fwith%20space/cleanup',
      { method: 'POST', fallbackMessage: 'Failed to clean up document job' },
    )
  })
})
