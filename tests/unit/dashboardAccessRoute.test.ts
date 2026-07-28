import { NextRequest } from 'next/server'

const applyAuthCookies = jest.fn()
const authenticatedFetch = jest.fn()
const clearAuthCookies = jest.fn()
const hasAuthSession = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  applyAuthCookies,
  authenticatedFetch,
  clearAuthCookies,
  getApiBaseUrl: () => 'http://localhost:8000',
  hasAuthSession,
}))

function request() {
  return new NextRequest('http://localhost:3000/api/dashboard/access')
}

describe('dashboard access proxy', () => {
  beforeEach(() => {
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    clearAuthCookies.mockReset()
    hasAuthSession.mockReset()
  })

  it('resolves a missing browser session quietly without contacting the backend', async () => {
    hasAuthSession.mockReturnValue(false)
    const { GET } = await import('../../app/api/dashboard/access/route')

    const response = await GET(request())

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      authenticated: false,
      reason: 'missing_session',
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('turns an expired session into a quiet access result and clears stale cookies', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: new Response(JSON.stringify({ detail: 'Session expired' }), { status: 401 }),
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/dashboard/access/route')
    const nextRequest = request()

    const response = await GET(nextRequest)

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      authenticated: false,
      reason: 'expired_session',
    })
    expect(authenticatedFetch).toHaveBeenCalledTimes(1)
    expect(authenticatedFetch).toHaveBeenCalledWith(
      nextRequest,
      'http://localhost:8000/v1/auth/me',
      { cache: 'no-store' },
    )
    expect(clearAuthCookies).toHaveBeenCalledWith(response, nextRequest)
  })

  it('returns the verified operator and applies rotated cookies', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: new Response(
        JSON.stringify({
          id: 'user_123',
          email: 'operator@mutx.dev',
          name: 'Runtime Operator',
          roles: ['DEVELOPER'],
        }),
        { status: 200 },
      ),
      tokenRefreshed: true,
      refreshedTokens: {
        access_token: 'access-new',
        refresh_token: 'refresh-new',
        expires_in: 1800,
      },
    })
    const { GET } = await import('../../app/api/dashboard/access/route')
    const nextRequest = request()

    const response = await GET(nextRequest)

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      authenticated: true,
      user: {
        id: 'user_123',
        email: 'operator@mutx.dev',
        name: 'Runtime Operator',
        roles: ['DEVELOPER'],
      },
    })
    expect(applyAuthCookies).toHaveBeenCalledWith(
      response,
      nextRequest,
      expect.objectContaining({ access_token: 'access-new', refresh_token: 'refresh-new' }),
    )
  })

  it('preserves a real access-service failure instead of presenting a login prompt', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: new Response(JSON.stringify({ detail: 'Auth service unavailable' }), {
        status: 503,
      }),
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/dashboard/access/route')

    const response = await GET(request())

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toEqual({ detail: 'Auth service unavailable' })
  })

  it('applies rotated auth cookies when the refreshed upstream response is 503', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: new Response(JSON.stringify({ detail: 'Auth service unavailable' }), {
        status: 503,
      }),
      tokenRefreshed: true,
      refreshedTokens: {
        access_token: 'access-new',
        refresh_token: 'refresh-new',
        expires_in: 1800,
      },
    })
    const { GET } = await import('../../app/api/dashboard/access/route')
    const nextRequest = request()

    const response = await GET(nextRequest)

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toEqual({ detail: 'Auth service unavailable' })
    expect(applyAuthCookies).toHaveBeenCalledWith(
      response,
      nextRequest,
      expect.objectContaining({ access_token: 'access-new', refresh_token: 'refresh-new' }),
    )
  })
})
