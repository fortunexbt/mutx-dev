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

jest.mock('../../app/api/_lib/errors', () => ({
  unauthorized: () =>
    new Response(JSON.stringify({ detail: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    }),
  withErrorHandling:
    (handler: (request: NextRequest) => Promise<Response>) => async (request: NextRequest) =>
      handler(request),
}))

function mockRequest(url = 'http://localhost:3000/api/dashboard/settings') {
  return {
    url,
    nextUrl: new URL(url),
  } as NextRequest
}

describe('dashboard settings route', () => {
  beforeEach(() => {
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
  })

  it('returns unauthorized when the dashboard session is missing', async () => {
    hasAuthSession.mockReturnValue(false)
    const { GET } = await import('../../app/api/dashboard/settings/route')

    const response = await GET(mockRequest())

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ detail: 'Unauthorized' })
  })

  it('derives essential mode from the authenticated operator plan', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce({
        response: {
          ok: true,
          status: 200,
          json: async () => ({
            id: 'user_123',
            email: 'ops@mutx.dev',
            name: 'Ops Team',
            plan: 'free',
          }),
        },
        tokenRefreshed: false,
      })
      .mockResolvedValueOnce({
        response: {
          ok: true,
          status: 200,
          json: async () => ({ plan: 'free' }),
        },
        tokenRefreshed: false,
      })

    const { GET } = await import('../../app/api/dashboard/settings/route')
    const response = await GET(mockRequest())

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      interfaceMode: 'essential',
      orgName: 'Ops Team',
      subscription: 'free',
      user: {
        id: 'user_123',
        email: 'ops@mutx.dev',
        name: 'Ops Team',
        plan: 'free',
      },
    })
  })

  it('falls back to the auth payload when the payments contract is unavailable', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce({
        response: {
          ok: true,
          status: 200,
          json: async () => ({
            id: 'user_456',
            email: 'platform@mutx.dev',
            name: 'Platform',
            plan: 'enterprise',
          }),
        },
        tokenRefreshed: false,
      })
      .mockRejectedValueOnce(new Error('payments offline'))

    const { GET } = await import('../../app/api/dashboard/settings/route')
    const response = await GET(mockRequest())

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      interfaceMode: 'full',
      orgName: 'Platform',
      subscription: 'enterprise',
      user: {
        id: 'user_456',
        email: 'platform@mutx.dev',
        name: 'Platform',
        plan: 'enterprise',
      },
    })
  })

  it('keeps the plan unknown and the interface essential when no entitlement can be verified', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce({
        response: {
          ok: true,
          status: 200,
          json: async () => ({
            id: 'user_789',
            email: 'unknown@mutx.dev',
            name: 'Unknown Plan',
          }),
        },
        tokenRefreshed: false,
      })
      .mockResolvedValueOnce({
        response: {
          ok: false,
          status: 503,
          json: async () => ({ detail: 'Payments unavailable' }),
        },
        tokenRefreshed: false,
      })

    const { GET } = await import('../../app/api/dashboard/settings/route')
    const response = await GET(mockRequest())

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      interfaceMode: 'essential',
      orgName: 'Unknown Plan',
      subscription: null,
      user: {
        id: 'user_789',
        email: 'unknown@mutx.dev',
        name: 'Unknown Plan',
      },
    })
  })
})
