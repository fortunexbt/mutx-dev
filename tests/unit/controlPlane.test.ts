import type { NextRequest } from 'next/server'

import {
  authenticatedFetch,
  getCookieDomain,
  shouldUseSecureCookies,
} from '../../app/api/_lib/controlPlane'

function mockRequest(url: string, forwardedProto?: string) {
  return {
    nextUrl: new URL(url),
    headers: {
      get(name: string) {
        return name === 'x-forwarded-proto' ? forwardedProto ?? null : null
      },
    },
  } as unknown as NextRequest
}

function mockAuthRequest(accessToken = 'access-old', refreshToken = 'refresh-old') {
  const cookies = new Map([
    ['access_token', accessToken],
    ['refresh_token', refreshToken],
  ])

  return {
    cookies: {
      get(name: string) {
        const value = cookies.get(name)
        return value ? { value } : undefined
      },
    },
    headers: new Headers(),
  } as unknown as NextRequest
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function requestAuthorization(init?: RequestInit) {
  return new Headers(init?.headers).get('authorization')
}

describe('dashboard auth cookie policy helpers', () => {
  it('does not force a shared domain for production hosts', () => {
    expect(getCookieDomain(mockRequest('https://app.mutx.dev/api/auth/login'))).toBeUndefined()
    expect(getCookieDomain(mockRequest('https://mutx.dev/api/auth/login'))).toBeUndefined()
  })

  it('does not force a domain on localhost-style environments', () => {
    expect(getCookieDomain(mockRequest('http://app.localhost:3000/api/auth/login'))).toBeUndefined()
    expect(getCookieDomain(mockRequest('http://localhost:3000/api/auth/login'))).toBeUndefined()
  })

  it('always marks auth cookies as secure', () => {
    expect(shouldUseSecureCookies(mockRequest('https://app.mutx.dev/api/auth/login'))).toBe(true)
    expect(shouldUseSecureCookies(mockRequest('http://app.mutx.dev/api/auth/login', 'https'))).toBe(true)
    expect(shouldUseSecureCookies(mockRequest('http://localhost:3000/api/auth/login'))).toBe(true)
  })
})

describe('dashboard authenticated request refresh', () => {
  const originalFetch = global.fetch

  afterEach(() => {
    global.fetch = originalFetch
  })

  it('serializes concurrent 401 refreshes and never reuses the spent token', async () => {
    const request = mockAuthRequest()
    let rotations = 0
    let familyRevoked = false
    const fetchMock = jest.fn(
      async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = input.toString()
        if (url.endsWith('/v1/auth/refresh')) {
          rotations += 1
          if (rotations > 1) {
            familyRevoked = true
            return jsonResponse({ detail: 'Refresh token reuse detected' }, 401)
          }

          return jsonResponse({
            access_token: 'access-new',
            refresh_token: 'refresh-new',
            expires_in: 1800,
          })
        }

        if (requestAuthorization(init) === 'Bearer access-old') {
          return jsonResponse({ detail: 'Access token expired' }, 401)
        }

        return jsonResponse({ url, authorized: true })
      },
    )
    global.fetch = fetchMock as typeof fetch

    const results = await Promise.all(
      ['/v1/agents', '/v1/runs', '/v1/budgets'].map((path) =>
        authenticatedFetch(request, `http://localhost:8000${path}`, { cache: 'no-store' }),
      ),
    )

    expect(rotations).toBe(1)
    expect(familyRevoked).toBe(false)
    expect(results.map(({ response }) => response.status)).toEqual([200, 200, 200])
    expect(results).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          tokenRefreshed: true,
          refreshedTokens: {
            access_token: 'access-new',
            refresh_token: 'refresh-new',
            expires_in: 1800,
          },
        }),
      ]),
    )
    const refreshCalls = fetchMock.mock.calls.filter(([input]) =>
      input.toString().endsWith('/v1/auth/refresh'),
    )
    const retryCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        !input.toString().endsWith('/v1/auth/refresh') &&
        requestAuthorization(init) === 'Bearer access-new',
    )
    expect(refreshCalls).toHaveLength(1)
    expect(retryCalls).toHaveLength(3)
  })

  it.each([401, 403, 503])(
    'preserves the original 401 when refresh fails with %i',
    async (refreshStatus) => {
      const request = mockAuthRequest('access-old', `refresh-failed-${refreshStatus}`)
      global.fetch = jest.fn(
        async (input: RequestInfo | URL): Promise<Response> =>
          input.toString().endsWith('/v1/auth/refresh')
            ? jsonResponse({ detail: 'Refresh failed' }, refreshStatus)
            : jsonResponse({ detail: 'Access token expired' }, 401),
      ) as typeof fetch

      const result = await authenticatedFetch(request, 'http://localhost:8000/v1/auth/me')

      expect(result.response.status).toBe(401)
      await expect(result.response.json()).resolves.toEqual({ detail: 'Access token expired' })
      expect(result.tokenRefreshed).toBe(false)
      expect(result.refreshedTokens).toBeUndefined()
    },
  )

  it('treats a malformed refresh payload as a failed refresh', async () => {
    const request = mockAuthRequest('access-old', 'refresh-malformed')
    global.fetch = jest.fn(
      async (input: RequestInfo | URL): Promise<Response> =>
        input.toString().endsWith('/v1/auth/refresh')
          ? jsonResponse({ access_token: 'access-new', expires_in: 1800 })
          : jsonResponse({ detail: 'Access token expired' }, 401),
    ) as typeof fetch

    const result = await authenticatedFetch(request, 'http://localhost:8000/v1/auth/me')

    expect(result.response.status).toBe(401)
    expect(result.tokenRefreshed).toBe(false)
  })

  it('does not hide a refresh network failure or retry the spent token', async () => {
    const request = mockAuthRequest('access-old', 'refresh-network-failure')
    let refreshCalls = 0
    global.fetch = jest.fn(
      async (input: RequestInfo | URL): Promise<Response> => {
        if (input.toString().endsWith('/v1/auth/refresh')) {
          refreshCalls += 1
          throw new TypeError('refresh network failed')
        }
        return jsonResponse({ detail: 'Access token expired' }, 401)
      },
    ) as typeof fetch

    const firstResult = await authenticatedFetch(request, 'http://localhost:8000/v1/auth/me')
    const secondResult = await authenticatedFetch(request, 'http://localhost:8000/v1/agents')

    expect(firstResult.response.status).toBe(401)
    expect(secondResult.response.status).toBe(401)
    expect(refreshCalls).toBe(1)
  })

  it.each([200, 403, 503])(
    'preserves an access-token response with status %i without rotating',
    async (status) => {
      const request = mockAuthRequest('access-valid')
      let refreshCalls = 0
      global.fetch = jest.fn(
        async (input: RequestInfo | URL): Promise<Response> => {
          if (input.toString().endsWith('/v1/auth/refresh')) {
            refreshCalls += 1
          }
          return jsonResponse({ status }, status)
        },
      ) as typeof fetch

      const result = await authenticatedFetch(request, 'http://localhost:8000/v1/auth/me')

      expect(result.response.status).toBe(status)
      expect(result.tokenRefreshed).toBe(false)
      expect(refreshCalls).toBe(0)
    },
  )

  it.each([403, 503])(
    'preserves a retry response with status %i after rotating once',
    async (retryStatus) => {
      const request = mockAuthRequest('access-old', `refresh-retry-${retryStatus}`)
      let refreshCalls = 0
      global.fetch = jest.fn(
        async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
          if (input.toString().endsWith('/v1/auth/refresh')) {
            refreshCalls += 1
            return jsonResponse({
              access_token: 'access-new',
              refresh_token: `refresh-new-${retryStatus}`,
              expires_in: 1800,
            })
          }
          return requestAuthorization(init) === 'Bearer access-old'
            ? jsonResponse({ detail: 'Access token expired' }, 401)
            : jsonResponse({ detail: 'Retry response' }, retryStatus)
        },
      ) as typeof fetch

      const result = await authenticatedFetch(request, 'http://localhost:8000/v1/auth/me')

      expect(result.response.status).toBe(retryStatus)
      expect(result.tokenRefreshed).toBe(true)
      expect(refreshCalls).toBe(1)
    },
  )

  it('propagates target network failures instead of fabricating a response', async () => {
    const request = mockAuthRequest('access-valid')
    global.fetch = jest.fn(async (): Promise<Response> => {
      throw new TypeError('target network failed')
    }) as typeof fetch

    await expect(
      authenticatedFetch(request, 'http://localhost:8000/v1/auth/me'),
    ).rejects.toThrow('target network failed')
  })
})
