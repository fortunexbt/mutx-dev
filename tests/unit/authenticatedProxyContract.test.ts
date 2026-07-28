import { NextRequest } from 'next/server'

import { proxyJson } from '../../app/api/_lib/proxy'

const API_BASE_URL = 'http://control-plane.test'
const UPSTREAM_URL = `${API_BASE_URL}/v1/agents/agent-123`

type ProxyCase = {
  name: string
  headers: Record<string, string>
  responses: Response[]
  expectedStatus: number
  expectedBody: string
  expectedAuthorizations: Array<string | null>
  refreshedCookies?: boolean
}

function jsonResponse(body: unknown, status: number) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('shared authenticated proxy contract', () => {
  const originalFetch = global.fetch
  const originalApiUrl = process.env.INTERNAL_API_URL

  beforeEach(() => {
    process.env.INTERNAL_API_URL = API_BASE_URL
  })

  afterEach(() => {
    global.fetch = originalFetch
    if (originalApiUrl === undefined) {
      delete process.env.INTERNAL_API_URL
    } else {
      process.env.INTERNAL_API_URL = originalApiUrl
    }
  })

  it.each<ProxyCase>([
    {
      name: 'retries an expired access cookie with a valid refresh cookie',
      headers: { cookie: 'access_token=expired-access; refresh_token=valid-refresh-204' },
      responses: [
        jsonResponse({ detail: 'Token expired' }, 401),
        jsonResponse(
          {
            access_token: 'fresh-access',
            refresh_token: 'fresh-refresh',
            expires_in: 1800,
          },
          200,
        ),
        jsonResponse({ id: 'agent-123', status: 'stopped' }, 200),
      ],
      expectedStatus: 200,
      expectedBody: JSON.stringify({ id: 'agent-123', status: 'stopped' }),
      expectedAuthorizations: ['Bearer expired-access', 'Bearer fresh-access'],
      refreshedCookies: true,
    },
    {
      name: 'returns the original unauthorized response when refresh is invalid',
      headers: { cookie: 'access_token=expired-access; refresh_token=invalid-refresh' },
      responses: [
        jsonResponse({ detail: 'Token expired' }, 401),
        jsonResponse({ detail: 'Invalid refresh token' }, 401),
      ],
      expectedStatus: 401,
      expectedBody: JSON.stringify({ detail: 'Token expired' }),
      expectedAuthorizations: ['Bearer expired-access'],
    },
    {
      name: 'supports bearer-only authentication without attempting refresh',
      headers: { authorization: 'Bearer api-token' },
      responses: [jsonResponse({ id: 'agent-123' }, 200)],
      expectedStatus: 200,
      expectedBody: JSON.stringify({ id: 'agent-123' }),
      expectedAuthorizations: ['Bearer api-token'],
    },
    {
      name: 'returns an empty 204 response without parsing JSON',
      headers: { cookie: 'access_token=current-access' },
      responses: [new Response(null, { status: 204 })],
      expectedStatus: 204,
      expectedBody: '',
      expectedAuthorizations: ['Bearer current-access'],
    },
    {
      name: 'propagates refreshed cookies on a retried 204 response',
      headers: { cookie: 'access_token=expired-access; refresh_token=valid-refresh' },
      responses: [
        jsonResponse({ detail: 'Token expired' }, 401),
        jsonResponse(
          {
            access_token: 'fresh-access',
            refresh_token: 'fresh-refresh',
            expires_in: 1800,
          },
          200,
        ),
        new Response(null, { status: 204 }),
      ],
      expectedStatus: 204,
      expectedBody: '',
      expectedAuthorizations: ['Bearer expired-access', 'Bearer fresh-access'],
      refreshedCookies: true,
    },
    {
      name: 'preserves non-success upstream statuses and payloads',
      headers: { cookie: 'access_token=current-access' },
      responses: [jsonResponse({ detail: 'Agent is busy' }, 409)],
      expectedStatus: 409,
      expectedBody: JSON.stringify({ detail: 'Agent is busy' }),
      expectedAuthorizations: ['Bearer current-access'],
    },
  ])('$name', async ({
    headers,
    responses,
    expectedStatus,
    expectedBody,
    expectedAuthorizations,
    refreshedCookies,
  }) => {
    const fetchMock = jest.fn()
    for (const response of responses) {
      fetchMock.mockResolvedValueOnce(response)
    }
    global.fetch = fetchMock

    const request = new NextRequest('http://localhost:3000/api/agents/agent-123', {
      headers,
    })
    const response = await proxyJson(request, UPSTREAM_URL, {
      method: 'DELETE',
      fallbackMessage: 'Failed to delete agent',
    })

    const upstreamAuthorizations = fetchMock.mock.calls
      .filter(([url]) => String(url) === UPSTREAM_URL)
      .map(([, init]) => new Headers(init?.headers).get('authorization'))

    expect(upstreamAuthorizations).toEqual(expectedAuthorizations)
    expect(response.status).toBe(expectedStatus)
    await expect(response.text()).resolves.toBe(expectedBody)

    const setCookie = response.headers.get('set-cookie')
    if (refreshedCookies) {
      expect(setCookie).toContain('access_token=fresh-access')
      expect(setCookie).toContain('refresh_token=fresh-refresh')
    } else {
      expect(setCookie).toBeNull()
    }
  })
})
