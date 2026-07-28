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
}

function createJsonRequest(options: MockRequestOptions = {}) {
  const { body = {}, jsonError } = options

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
    nextUrl: new URL('https://pico.mutx.dev/api/pico/onboarding'),
  } as unknown as NextRequest
}

describe('pico onboarding auth route', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it('returns 401 for onboarding state reads when no auth session exists', async () => {
    hasAuthSession.mockReturnValue(false)

    const { GET } = await import('../../app/api/pico/onboarding/route')
    const request = new NextRequest(
      'https://pico.mutx.dev/api/pico/onboarding?provider=openclaw&step=auth',
    )

    const response = await GET(request)

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('returns 401 for onboarding mutations before parsing an invalid body', async () => {
    hasAuthSession.mockReturnValue(false)

    const { POST } = await import('../../app/api/pico/onboarding/route')
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

  it('propagates an invalid bearer 401 from the Pico chat backend', async () => {
    authenticatedFetch.mockResolvedValue({
      response: new Response(JSON.stringify({ detail: 'Invalid or expired token' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
      tokenRefreshed: false,
    })

    const { POST } = await import('../../app/api/pico/onboarding/route')
    const request = new NextRequest('https://pico.mutx.dev/api/pico/onboarding', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer supplied-but-invalid',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        action: 'coach_message',
        message: 'Do not downgrade this request',
      }),
    })

    const response = await POST(request)

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ detail: 'Invalid or expired token' })
    expect(authenticatedFetch).toHaveBeenCalledTimes(1)
    expect(applyAuthCookies).not.toHaveBeenCalled()
  })

  it('applies refreshed cookies when a stale Pico session is retried upstream', async () => {
    const refreshedTokens = {
      access_token: 'fresh-access-token',
      refresh_token: 'rotated-refresh-token',
      expires_in: 1800,
    }
    authenticatedFetch.mockResolvedValue({
      response: new Response(JSON.stringify({ session_id: 'fresh-session' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
      tokenRefreshed: true,
      refreshedTokens,
    })

    const { GET } = await import('../../app/api/pico/onboarding/route')
    const request = new NextRequest(
      'https://pico.mutx.dev/api/pico/onboarding?view=coach_session',
      {
        headers: {
          Cookie: 'access_token=stale-access-token; refresh_token=usable-refresh-token',
        },
      },
    )

    const response = await GET(request)

    expect(response.status).toBe(200)
    expect(authenticatedFetch).toHaveBeenCalledTimes(1)
    expect(applyAuthCookies).toHaveBeenCalledWith(response, request, refreshedTokens)
  })
})
