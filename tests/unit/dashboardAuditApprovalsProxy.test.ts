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

function mockRequest(url: string) {
  return {
    url,
    nextUrl: new URL(url),
    headers: new Headers(),
    cookies: { get: () => undefined },
  } as unknown as NextRequest
}

function mockUpstream(payload: unknown, status = 200) {
  return {
    response: {
      status,
      json: async () => payload,
    },
    tokenRefreshed: false,
  }
}

describe('dashboard audit and approval proxies', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it('requires authentication before querying the audit control plane', async () => {
    hasAuthSession.mockReturnValue(false)
    const { GET } = await import('../../app/api/dashboard/audit/events/route')

    const response = await GET(
      mockRequest('http://localhost:3000/api/dashboard/audit/events?limit=26'),
    )

    expect(response.status).toBe(401)
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('forwards supported audit filters and preserves a forbidden response', async () => {
    authenticatedFetch.mockResolvedValue(
      mockUpstream({ detail: 'Audit role required' }, 403),
    )
    const { GET } = await import('../../app/api/dashboard/audit/events/route')

    const response = await GET(
      mockRequest(
        'http://localhost:3000/api/dashboard/audit/events?agent_id=agent-1&session_id=session-2&run_id=run-3&event_type=TOOL_CALL&time_range_start=2026-07-01T00%3A00%3A00Z&time_range_end=2026-07-02T00%3A00%3A00Z&skip=25&limit=26&untrusted=drop-me',
      ),
    )

    expect(response.status).toBe(403)
    await expect(response.json()).resolves.toEqual({ detail: 'Audit role required' })
    const upstreamUrl = new URL(authenticatedFetch.mock.calls[0][1] as string)
    expect(upstreamUrl.pathname).toBe('/v1/audit/events')
    expect(Object.fromEntries(upstreamUrl.searchParams)).toEqual({
      agent_id: 'agent-1',
      session_id: 'session-2',
      run_id: 'run-3',
      time_range_start: '2026-07-01T00:00:00Z',
      time_range_end: '2026-07-02T00:00:00Z',
      event_type: 'TOOL_CALL',
      limit: '26',
      skip: '25',
    })
    expect(upstreamUrl.searchParams.has('untrusted')).toBe(false)
  })

  it('requires exactly one bounded audit export context', async () => {
    const { GET } = await import('../../app/api/dashboard/audit/export/route')

    const missingContext = await GET(
      mockRequest('http://localhost:3000/api/dashboard/audit/export'),
    )
    const ambiguousContext = await GET(
      mockRequest(
        'http://localhost:3000/api/dashboard/audit/export?run_id=run-1&session_id=session-1',
      ),
    )
    const oversizedContext = await GET(
      mockRequest(
        `http://localhost:3000/api/dashboard/audit/export?run_id=${'x'.repeat(256)}`,
      ),
    )

    expect(missingContext.status).toBe(400)
    expect(ambiguousContext.status).toBe(400)
    expect(oversizedContext.status).toBe(400)
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('proxies a scoped evidence export without broadening its context', async () => {
    authenticatedFetch.mockResolvedValue(
      mockUpstream({
        schema_version: '1.0',
        algorithm: 'sha256',
        run_id: 'run-1',
        event_count: 2,
        chain_root: 'abc123',
        verified: true,
        errors: [],
        events: [],
      }),
    )
    const { GET } = await import('../../app/api/dashboard/audit/export/route')

    const response = await GET(
      mockRequest(
        'http://localhost:3000/api/dashboard/audit/export?run_id=%20run-1%20&event_type=TOOL_CALL',
      ),
    )

    expect(response.status).toBe(200)
    const upstreamUrl = new URL(authenticatedFetch.mock.calls[0][1] as string)
    expect(upstreamUrl.pathname).toBe('/v1/audit/export')
    expect(Object.fromEntries(upstreamUrl.searchParams)).toEqual({ run_id: 'run-1' })
    await expect(response.json()).resolves.toMatchObject({
      run_id: 'run-1',
      verified: true,
      event_count: 2,
    })
  })

  it('preserves the real approval list envelope and pagination filters', async () => {
    authenticatedFetch.mockResolvedValue(
      mockUpstream({
        items: [
          {
            id: 'approval-1',
            agent_id: 'agent-1',
            session_id: 'session-1',
            action_type: 'deploy',
            payload: { environment: 'production' },
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
      }),
    )
    const { GET } = await import('../../app/api/dashboard/approvals/route')

    const response = await GET(
      mockRequest(
        'http://localhost:3000/api/dashboard/approvals?status=PENDING&agent_id=agent-1&skip=20&limit=20&extra=ignored',
      ),
    )

    expect(response.status).toBe(200)
    const payload = await response.json()
    expect(payload).toMatchObject({
      total: 31,
      skip: 20,
      limit: 20,
      status: 'PENDING',
      agent_id: 'agent-1',
    })
    expect(payload.items[0]).toMatchObject({
      requester: 'operator@mutx.dev',
      action_type: 'deploy',
      payload: { environment: 'production' },
    })
    const upstreamUrl = new URL(authenticatedFetch.mock.calls[0][1] as string)
    expect(upstreamUrl.pathname).toBe('/v1/approvals')
    expect(Object.fromEntries(upstreamUrl.searchParams)).toEqual({
      status: 'PENDING',
      agent_id: 'agent-1',
      skip: '20',
      limit: '20',
    })
  })
})
