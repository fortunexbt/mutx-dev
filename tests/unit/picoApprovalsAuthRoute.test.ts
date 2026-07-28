import { NextRequest } from 'next/server'

const applyAuthCookies = jest.fn()
const authenticatedFetch = jest.fn()
const hasAuthSession = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
  applyAuthCookies,
  authenticatedFetch,
  hasAuthSession,
}))

type MockRequestOptions = {
  body?: unknown
  jsonError?: Error
  url?: string
}

function createJsonRequest(options: MockRequestOptions = {}) {
  const { body = {}, jsonError, url = 'https://pico.mutx.dev/api/pico/approvals' } = options

  return {
    json: async () => {
      if (jsonError) {
        throw jsonError
      }
      return body
    },
    headers: {
      get: () => null,
    },
    cookies: {
      get: () => undefined,
    },
    nextUrl: new URL(url),
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

describe('pico approvals auth routes', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it('returns 401 for approval creation before parsing an invalid body', async () => {
    hasAuthSession.mockReturnValue(false)

    const { POST } = await import('../../app/api/pico/approvals/route')
    const syntaxError = Object.assign(new SyntaxError('Unexpected end of JSON input'), {
      status: 400,
    })

    const response = await POST(
      createJsonRequest({
        jsonError: syntaxError,
      }),
    )

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('requires and forwards an explicit reviewer assignment on creation', async () => {
    const reviewerId = '00000000-0000-4000-8000-000000000002'
    authenticatedFetch.mockResolvedValue(
      mockUpstream(
        {
          id: 'approval-1',
          owner_id: 'owner-1',
          reviewer_id: reviewerId,
          can_resolve: false,
          status: 'PENDING',
        },
        201,
      ),
    )
    const request = createJsonRequest({
      body: {
        agent_id: 'agent-1',
        session_id: 'session-1',
        action_type: 'OUTBOUND_SEND',
        reviewer_id: reviewerId,
        payload: { summary: 'Review the send' },
      },
    })

    const { POST } = await import('../../app/api/pico/approvals/route')
    const response = await POST(request)

    expect(response.status).toBe(201)
    expect(authenticatedFetch).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/approvals',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          agent_id: 'agent-1',
          session_id: 'session-1',
          action_type: 'OUTBOUND_SEND',
          reviewer_id: reviewerId,
          payload: { summary: 'Review the send' },
        }),
      }),
    )
  })

  it('preserves the real approval envelope and forwards only pagination filters', async () => {
    authenticatedFetch.mockResolvedValue(
      mockUpstream(
        {
          items: [
            {
              id: 'approval-1',
              owner_id: 'owner-1',
              reviewer_id: 'reviewer-1',
              can_resolve: true,
              agent_id: 'agent-1',
              session_id: 'session-1',
              action_type: 'deploy',
              payload: { target: 'production' },
              status: 'PENDING',
              requester: 'operator@mutx.dev',
              created_at: '2026-07-28T09:00:00Z',
            },
          ],
          total: 31,
          skip: 20,
          limit: 20,
          status: 'PENDING',
          agent_id: 'agent-1',
        },
        200,
      ),
    )

    const { GET } = await import('../../app/api/pico/approvals/route')
    const request = createJsonRequest({
      url: 'https://pico.mutx.dev/api/pico/approvals?status=PENDING&agent_id=agent-1&skip=20&limit=20&extra=ignored',
    })
    const response = await GET(request)

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      total: 31,
      skip: 20,
      limit: 20,
      status: 'PENDING',
    })
    const upstreamUrl = new URL(authenticatedFetch.mock.calls[0][1] as string)
    expect(Object.fromEntries(upstreamUrl.searchParams)).toEqual({
      status: 'PENDING',
      agent_id: 'agent-1',
      skip: '20',
      limit: '20',
    })
  })

  it('proxies discoverable eligible reviewers for truthful assignment', async () => {
    authenticatedFetch.mockResolvedValue(
      mockUpstream(
        [
          {
            id: '00000000-0000-4000-8000-000000000002',
            email: 'reviewer@mutx.dev',
            name: 'Reviewer',
            roles: ['DEVELOPER'],
          },
        ],
        200,
      ),
    )

    const { GET } = await import('../../app/api/pico/approvals/reviewers/route')
    const request = createJsonRequest({
      url: 'https://pico.mutx.dev/api/pico/approvals/reviewers',
    })
    const response = await GET(request)

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual([
      expect.objectContaining({ id: '00000000-0000-4000-8000-000000000002' }),
    ])
    expect(authenticatedFetch).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/approvals/reviewers',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('returns 401 for approval actions before parsing an invalid body', async () => {
    hasAuthSession.mockReturnValue(false)
    const syntaxError = Object.assign(new SyntaxError('Unexpected end of JSON input'), {
      status: 400,
    })

    const { POST: approvePost } = await import('../../app/api/pico/approvals/[requestId]/approve/route')
    const approveResponse = await approvePost(
      createJsonRequest({
        jsonError: syntaxError,
        url: 'https://pico.mutx.dev/api/pico/approvals/req_123/approve',
      }),
      { params: Promise.resolve({ requestId: 'req_123' }) },
    )

    expect(approveResponse.status).toBe(401)
    await expect(approveResponse.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })

    const { POST: rejectPost } = await import('../../app/api/pico/approvals/[requestId]/reject/route')
    const rejectResponse = await rejectPost(
      createJsonRequest({
        jsonError: syntaxError,
        url: 'https://pico.mutx.dev/api/pico/approvals/req_123/reject',
      }),
      { params: Promise.resolve({ requestId: 'req_123' }) },
    )

    expect(rejectResponse.status).toBe(401)
    await expect(rejectResponse.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it.each([
    [402, { detail: 'This feature requires the starter plan or higher' }, 402],
    [403, { detail: 'Approver role required' }, 403],
    [404, { detail: 'Approval request not found' }, 404],
    [409, { detail: 'Approval request is no longer pending' }, 409],
    [503, { detail: 'Approval service unavailable' }, 503],
    [400, { detail: "Cannot approve request in 'APPROVED' state" }, 409],
  ] as const)(
    'preserves or normalizes upstream approval mutation status %s',
    async (upstreamStatus, payload, expectedStatus) => {
      authenticatedFetch.mockResolvedValue(mockUpstream(payload, upstreamStatus))
      const { POST } = await import('../../app/api/pico/approvals/[requestId]/approve/route')
      const request = createJsonRequest({
        body: { comment: 'reviewed from Pico' },
        url: 'https://pico.mutx.dev/api/pico/approvals/approval_1/approve',
      })

      const response = await POST(request, {
        params: Promise.resolve({ requestId: 'approval_1' }),
      })

      expect(response.status).toBe(expectedStatus)
      await expect(response.json()).resolves.toEqual(payload)
      expect(authenticatedFetch).toHaveBeenCalledWith(
        request,
        'http://localhost:8000/v1/approvals/approval_1/approve',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ comment: 'reviewed from Pico' }),
        }),
      )
    },
  )
})
