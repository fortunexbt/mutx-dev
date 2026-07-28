import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { NextRequest } from 'next/server'

const applyAuthCookies = jest.fn()
const authenticatedFetch = jest.fn()
const hasAuthSession = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl: () => 'http://localhost:8000',
  hasAuthSession,
}))

type MockRequestOptions = {
  body?: unknown
  jsonError?: Error
  url?: string
}

function createJsonRequest(options: MockRequestOptions = {}) {
  const {
    body = {},
    jsonError,
    url = 'http://localhost:3000/api/dashboard/approvals/approval_1/approve',
  } = options

  return {
    json: async () => {
      if (jsonError) throw jsonError
      return body
    },
    headers: new Headers(),
    cookies: { get: () => undefined },
    nextUrl: new URL(url),
    url,
  } as unknown as NextRequest
}

function mockUpstream(payload: unknown, status: number) {
  return {
    response: {
      status,
      json: async () => payload,
    },
    tokenRefreshed: false,
  }
}

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('dashboard approval operator actions', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it('preserves upstream approval and rejection statuses and payloads', async () => {
    authenticatedFetch
      .mockResolvedValueOnce(
        mockUpstream({ detail: 'Approval request is no longer pending' }, 409),
      )
      .mockResolvedValueOnce(
        mockUpstream({ id: 'approval_1', status: 'REJECTED' }, 200),
      )

    const { POST: approve } = await import(
      '../../app/api/dashboard/approvals/[requestId]/approve/route'
    )
    const approveResponse = await approve(
      createJsonRequest({ body: { comment: 'ship it' } }),
      { params: Promise.resolve({ requestId: 'approval_1' }) },
    )

    expect(approveResponse.status).toBe(409)
    await expect(approveResponse.json()).resolves.toEqual({
      detail: 'Approval request is no longer pending',
    })
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      1,
      expect.anything(),
      'http://localhost:8000/v1/approvals/approval_1/approve',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ comment: 'ship it' }),
      }),
    )

    const { POST: reject } = await import(
      '../../app/api/dashboard/approvals/[requestId]/reject/route'
    )
    const rejectResponse = await reject(
      createJsonRequest({
        body: {},
        url: 'http://localhost:3000/api/dashboard/approvals/approval_1/reject',
      }),
      { params: Promise.resolve({ requestId: 'approval_1' }) },
    )

    expect(rejectResponse.status).toBe(200)
    await expect(rejectResponse.json()).resolves.toEqual({
      id: 'approval_1',
      status: 'REJECTED',
    })
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      2,
      expect.anything(),
      'http://localhost:8000/v1/approvals/approval_1/reject',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({}),
      }),
    )
  })

  it('requires an authenticated operator before parsing an action request', async () => {
    hasAuthSession.mockReturnValue(false)
    const syntaxError = new SyntaxError('Unexpected end of JSON input')
    const { POST } = await import(
      '../../app/api/dashboard/approvals/[requestId]/approve/route'
    )

    const response = await POST(
      createJsonRequest({ jsonError: syntaxError }),
      { params: Promise.resolve({ requestId: 'approval_1' }) },
    )

    expect(response.status).toBe(401)
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('keeps action feedback and safe destination controls in the dashboard clients', () => {
    const orchestration = readSource(
      'components/dashboard/OrchestrationPageClient.tsx',
    )
    const approvals = readSource(
      'components/dashboard/ApprovalsPageClient.tsx',
    )
    const notifications = readSource(
      'components/dashboard/NotificationsPageClient.tsx',
    )

    expect(orchestration).toContain('aria-busy={actionState?.pending === "approve"}')
    expect(orchestration).toContain('"Retry approve"')
    expect(orchestration).toContain('"Retry reject"')
    expect(orchestration).toContain('Retry refresh')
    expect(orchestration).toContain('role="alert"')
    expect(orchestration).toContain('{approval.canResolve ? (')
    expect(orchestration).toContain('You are no longer eligible to resolve this approval request')
    expect(approvals).toContain('!selectedApproval.can_resolve')
    expect(approvals).toContain('selectedApproval.can_resolve ? (')
    expect(approvals).toContain('setActionError(message)')
    expect(orchestration).toContain('href={item.href}')
    expect(notifications).toContain('safeNotificationHref(item.href)')
    expect(notifications).toContain('href={destination}')
  })
})
