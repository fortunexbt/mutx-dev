import { NextRequest } from 'next/server'

import { GET as getOverview } from '../../app/api/dashboard/overview/route'
import { GET as getSettings } from '../../app/api/dashboard/settings/route'

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function dashboardRequest(
  path: string,
  accessToken = 'access-old',
  refreshToken = 'refresh-old',
) {
  return new NextRequest(`http://localhost:3000${path}`, {
    headers: {
      cookie: `access_token=${accessToken}; refresh_token=${refreshToken}`,
    },
  })
}

function requestAuthorization(init?: RequestInit) {
  return new Headers(init?.headers).get('authorization')
}

describe('dashboard session refresh serialization', () => {
  const originalFetch = global.fetch
  const originalInternalApiUrl = process.env.INTERNAL_API_URL

  beforeEach(() => {
    process.env.INTERNAL_API_URL = 'http://localhost:8000'
  })

  afterEach(() => {
    global.fetch = originalFetch
    if (originalInternalApiUrl === undefined) {
      delete process.env.INTERNAL_API_URL
    } else {
      process.env.INTERNAL_API_URL = originalInternalApiUrl
    }
  })

  it('shares one rotation across concurrent overview and settings requests', async () => {
    let rotations = 0
    let familyRevoked = false
    let oldMeCalls = 0
    let releaseDelayedOldMe: (() => void) | undefined
    const firstRefreshedMeCall = new Promise<void>((resolve) => {
      releaseDelayedOldMe = resolve
    })
    const authenticatedCalls: Array<{ url: string; authorization: string | null }> = []
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

        const authorization = requestAuthorization(init)
        authenticatedCalls.push({ url, authorization })
        if (authorization === 'Bearer access-old') {
          oldMeCalls += 1
          if (oldMeCalls === 2) {
            await firstRefreshedMeCall
          }
          return jsonResponse({ detail: 'Access token expired' }, 401)
        }
        if (authorization !== 'Bearer access-new') {
          return jsonResponse({ detail: 'Forbidden' }, 403)
        }
        if (url.endsWith('/v1/auth/me')) {
          releaseDelayedOldMe?.()
          return jsonResponse({ id: 'user_1', email: 'ops@mutx.dev', plan: 'pro' })
        }
        if (url.endsWith('/v1/payments/subscription')) {
          return jsonResponse({ plan: 'pro' })
        }
        return jsonResponse({ items: [] })
      },
    )
    global.fetch = fetchMock as typeof fetch

    const [overviewResponse, settingsResponse] = await Promise.all([
      getOverview(dashboardRequest('/api/dashboard/overview')),
      getSettings(dashboardRequest('/api/dashboard/settings')),
    ])

    expect(overviewResponse.status).toBe(200)
    expect(settingsResponse.status).toBe(200)
    expect(rotations).toBe(1)
    expect(familyRevoked).toBe(false)

    const expiredCalls = authenticatedCalls.filter(
      ({ authorization }) => authorization === 'Bearer access-old',
    )
    expect(expiredCalls).toHaveLength(2)
    expect(expiredCalls.every(({ url }) => url.endsWith('/v1/auth/me'))).toBe(true)
    expect(
      authenticatedCalls
        .filter(({ url }) => !url.endsWith('/v1/auth/me'))
        .every(({ authorization }) => authorization === 'Bearer access-new'),
    ).toBe(true)

    for (const response of [overviewResponse, settingsResponse]) {
      const setCookie = response.headers.get('set-cookie')
      expect(setCookie).toContain('access_token=access-new')
      expect(setCookie).toContain('refresh_token=refresh-new')
    }
  })

  it('does not rotate or set cookies while the access token works', async () => {
    let rotations = 0
    global.fetch = jest.fn(
      async (input: RequestInfo | URL): Promise<Response> => {
        const url = input.toString()
        if (url.endsWith('/v1/auth/refresh')) {
          rotations += 1
        }
        if (url.endsWith('/v1/auth/me')) {
          return jsonResponse({ id: 'user_1', email: 'ops@mutx.dev', plan: 'free' })
        }
        return jsonResponse({ plan: 'free' })
      },
    ) as typeof fetch

    const response = await getSettings(
      dashboardRequest('/api/dashboard/settings', 'access-valid'),
    )

    expect(response.status).toBe(200)
    expect(rotations).toBe(0)
    expect(response.headers.get('set-cookie')).toBeNull()
  })

  it('accepts the durable backend successor for a request delayed past local grace', async () => {
    jest.useFakeTimers()
    try {
      let rotations = 0
      global.fetch = jest.fn(
        async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
          const url = input.toString()
          if (url.endsWith('/v1/auth/refresh')) {
            rotations += 1
            return jsonResponse({
              access_token: 'access-delayed-new',
              refresh_token: 'refresh-delayed-new',
              expires_in: 1800,
            })
          }

          const authorization = requestAuthorization(init)
          if (authorization === 'Bearer access-delayed-old') {
            return jsonResponse({ detail: 'Access token expired' }, 401)
          }
          if (authorization !== 'Bearer access-delayed-new') {
            return jsonResponse({ detail: 'Forbidden' }, 403)
          }
          if (url.endsWith('/v1/auth/me')) {
            return jsonResponse({ id: 'user_1', email: 'ops@mutx.dev', plan: 'free' })
          }
          return jsonResponse({ plan: 'free' })
        },
      ) as typeof fetch

      const first = await getSettings(
        dashboardRequest(
          '/api/dashboard/settings',
          'access-delayed-old',
          'refresh-delayed-old',
        ),
      )
      jest.advanceTimersByTime(5001)
      await Promise.resolve()
      const delayed = await getSettings(
        dashboardRequest(
          '/api/dashboard/settings',
          'access-delayed-old',
          'refresh-delayed-old',
        ),
      )

      expect(first.status).toBe(200)
      expect(delayed.status).toBe(200)
      expect(rotations).toBe(2)
      expect(delayed.headers.get('set-cookie')).toContain(
        'refresh_token=refresh-delayed-new',
      )
    } finally {
      jest.useRealTimers()
    }
  })
})
