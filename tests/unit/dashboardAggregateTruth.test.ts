import { readFileSync } from 'node:fs'

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

function request(path: string) {
  return new NextRequest(`http://localhost:3000${path}`, {
    headers: { cookie: 'access_token=access-valid' },
  })
}

function resourceResponse(payload: unknown, status = 200) {
  return {
    response: new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
    tokenRefreshed: false,
  }
}

function requestedUrls() {
  return authenticatedFetch.mock.calls.map((call) => call[1] as string)
}

function expectBoundedSignals() {
  for (const call of authenticatedFetch.mock.calls) {
    expect(call[2]).toEqual(
      expect.objectContaining({
        cache: 'no-store',
        signal: expect.any(AbortSignal),
      }),
    )
  }
}

const aggregateRouteLoaders = {
  overview: async () => (await import('../../app/api/dashboard/overview/route')).GET,
  notifications: async () => (await import('../../app/api/dashboard/notifications/route')).GET,
  standup: async () => (await import('../../app/api/dashboard/standup/route')).GET,
}

describe('dashboard aggregate source truth', () => {
  beforeEach(() => {
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it.each([
    ['overview', 401],
    ['notifications', 401],
    ['standup', 401],
    ['overview', 403],
    ['notifications', 403],
    ['standup', 403],
  ] as const)('preserves aggregate %s access status %i', async (routeName, status) => {
    authenticatedFetch.mockImplementation(
      async (_request: NextRequest, url: string) => {
        if (url.endsWith('/v1/auth/me')) {
          return resourceResponse({ id: 'user_1', email: 'operator@mutx.dev' })
        }
        if (status === 401 && !url.includes('/v1/monitoring/alerts')) {
          return resourceResponse({ items: [] })
        }
        return resourceResponse(
          { detail: status === 401 ? 'Operator session expired' : 'Workspace role required' },
          status,
        )
      },
    )

    const GET = await aggregateRouteLoaders[routeName]()
    const response = await GET(request(`/api/dashboard/${routeName}`))

    expect(response.status).toBe(status)
    await expect(response.json()).resolves.toMatchObject({
      detail: expect.stringMatching(status === 401 ? /session expired/i : /role required/i),
    })
  })

  it('keeps overview timeout and network failures in bounded partial envelopes', async () => {
    authenticatedFetch.mockImplementation(
      async (_request: NextRequest, url: string) => {
        if (url.endsWith('/v1/auth/me')) {
          return resourceResponse({ id: 'user_1', email: 'operator@mutx.dev' })
        }
        if (url.includes('/v1/agents')) {
          return resourceResponse({ items: [{ id: 'agent_1', status: 'running' }] })
        }
        if (url.includes('/v1/monitoring/alerts')) {
          throw new DOMException('The operation timed out.', 'TimeoutError')
        }
        if (url.endsWith('/v1/budgets')) {
          throw new TypeError('budget network failed')
        }
        return resourceResponse({ items: [] })
      },
    )

    const { GET } = await import('../../app/api/dashboard/overview/route')
    const response = await GET(request('/api/dashboard/overview'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.resources.agents).toMatchObject({ status: 'ok', statusCode: 200 })
    expect(payload.resources.alerts).toMatchObject({
      status: 'error',
      statusCode: 504,
      data: null,
      error: expect.stringMatching(/timed out/i),
    })
    expect(payload.resources.budget).toMatchObject({
      status: 'error',
      statusCode: 502,
      data: null,
      error: expect.stringMatching(/request failed/i),
    })
    expectBoundedSignals()
  })

  it('preserves notification partial success while failed approvals and webhooks stay unknown', async () => {
    authenticatedFetch.mockImplementation(
      async (_request: NextRequest, url: string) => {
        if (url.includes('/v1/monitoring/alerts')) {
          return resourceResponse({
            items: [
              {
                id: 'alert_1',
                message: 'Queue pressure',
                type: 'queue_depth',
                resolved: false,
              },
            ],
          })
        }
        if (url.includes('/v1/approvals')) {
          throw new TypeError('approval network failed')
        }
        if (url.endsWith('/v1/runtime/governance/status')) {
          return resourceResponse({ status: 'healthy', pending_approvals: 0 })
        }
        if (url.endsWith('/v1/runtime/governance/supervised/')) {
          return resourceResponse([])
        }
        if (url.endsWith('/v1/webhooks')) {
          return resourceResponse({ items: [{ id: 'webhook_1', is_active: true }] })
        }
        if (url.includes('/v1/webhooks/webhook_1/deliveries')) {
          throw new DOMException('The operation timed out.', 'TimeoutError')
        }
        throw new Error(`Unexpected URL: ${url}`)
      },
    )

    const { GET } = await import('../../app/api/dashboard/notifications/route')
    const response = await GET(request('/api/dashboard/notifications'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.summary).toMatchObject({
      alerts: 1,
      approvals: null,
      webhookFailures: null,
      runtimeIncidents: 0,
    })
    expect(payload.sources).toMatchObject({
      alerts: 'ok',
      approvals: 'error',
      webhooks: 'partial',
    })
    expect(payload.items).toEqual(
      expect.arrayContaining([expect.objectContaining({ id: 'alert_1', kind: 'alert' })]),
    )
    expect(payload.partials.join(' ')).toMatch(/approvals|approval/i)
    expect(payload.partials.join(' ')).toMatch(/webhook.*timed out/i)
    expect(requestedUrls()).not.toContain('http://localhost:8000/v1/auth/me')
    expectBoundedSignals()
  })

  it('omits identifier-less notification records and routes approvals to the approval queue', async () => {
    authenticatedFetch.mockImplementation(
      async (_request: NextRequest, url: string) => {
        if (url.includes('/v1/monitoring/alerts')) {
          return resourceResponse({
            items: [{ message: 'Unattributed alert', type: 'queue_depth', resolved: false }],
          })
        }
        if (url.includes('/v1/approvals')) {
          return resourceResponse({
            items: [
              {
                id: 'approval_1',
                status: 'PENDING',
                action_type: 'deploy',
                requester: 'operator',
              },
            ],
          })
        }
        if (url.endsWith('/v1/runtime/governance/status')) {
          return resourceResponse({ status: 'healthy', pending_approvals: 0 })
        }
        if (url.endsWith('/v1/runtime/governance/supervised/')) {
          return resourceResponse([{ status: 'failed', error: 'Missing runtime identity' }])
        }
        if (url.endsWith('/v1/webhooks')) {
          return resourceResponse({ items: [] })
        }
        throw new Error(`Unexpected URL: ${url}`)
      },
    )

    const { GET } = await import('../../app/api/dashboard/notifications/route')
    const response = await GET(request('/api/dashboard/notifications'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.sources).toMatchObject({ alerts: 'partial', runtime: 'partial' })
    expect(payload.summary).toMatchObject({ alerts: null, runtimeIncidents: null })
    expect(payload.items).toEqual([
      expect.objectContaining({
        id: 'approval_1',
        kind: 'approval',
        href: '/dashboard/approvals',
      }),
    ])
    expect(payload.partials.join(' ')).toMatch(/upstream identifier was missing/i)
    expect(JSON.stringify(payload)).not.toMatch(/alert-[a-z0-9]{6}|runtime-[a-z0-9]{6}/)
  })

  it('keeps identifier-less standup records out of the derived brief', async () => {
    authenticatedFetch.mockImplementation(
      async (_request: NextRequest, url: string) => {
        if (url.includes('/v1/monitoring/alerts')) {
          return resourceResponse({
            items: [{ message: 'Unattributed blocker', type: 'queue_depth', resolved: false }],
          })
        }
        if (url.includes('/v1/approvals')) {
          return resourceResponse({
            items: [{ id: 'approval_1', action_type: 'deploy', requester: 'operator' }],
          })
        }
        if (url.includes('/v1/runs')) {
          return resourceResponse({ items: [{ status: 'failed', error_message: 'No run id' }] })
        }
        if (url.endsWith('/v1/webhooks')) {
          return resourceResponse({ items: [] })
        }
        throw new Error(`Unexpected URL: ${url}`)
      },
    )

    const { GET } = await import('../../app/api/dashboard/standup/route')
    const response = await GET(request('/api/dashboard/standup'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.sources).toMatchObject({ alerts: 'partial', runs: 'partial' })
    expect(payload.metrics).toMatchObject({ openAlerts: null, failedRuns: null })
    expect(payload.blockers).toEqual([
      expect.objectContaining({ id: 'approval_1', source: 'approvals' }),
    ])
    expect(payload.watchlist).toEqual([])
    expect(payload.completions).toEqual([])
    expect(payload.partials.join(' ')).toMatch(/upstream identifier was missing/i)
  })

  it('keeps every failed standup source partial instead of reporting successful zeros', async () => {
    authenticatedFetch.mockImplementation(
      async (_request: NextRequest, url: string) => {
        if (url.includes('/v1/monitoring/alerts')) {
          throw new DOMException('The operation timed out.', 'TimeoutError')
        }
        if (url.includes('/v1/approvals')) {
          return resourceResponse({
            items: [{ id: 'approval_1', action_type: 'deploy', requester: 'operator' }],
          })
        }
        if (url.includes('/v1/runs')) {
          throw new TypeError('runs network failed')
        }
        if (url.endsWith('/v1/webhooks')) {
          return resourceResponse({ detail: 'Webhook service unavailable' }, 503)
        }
        throw new Error(`Unexpected URL: ${url}`)
      },
    )

    const { GET } = await import('../../app/api/dashboard/standup/route')
    const response = await GET(request('/api/dashboard/standup'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.metrics).toMatchObject({
      openAlerts: null,
      pendingApprovals: 1,
      failedRuns: null,
      queuedAutonomy: null,
    })
    expect(payload.sources).toEqual({
      alerts: 'error',
      approvals: 'ok',
      runs: 'error',
      webhooks: 'error',
      autonomy: 'partial',
    })
    expect(payload.blockers).toEqual(
      expect.arrayContaining([expect.objectContaining({ id: 'approval_1' })]),
    )
    expect(payload.focus).toMatch(/sources are unavailable/i)
    expect(payload.partials.join(' ')).toMatch(/timed out/i)
    expect(payload.partials.join(' ')).toMatch(/Webhook service unavailable/i)
    expect(requestedUrls()).not.toContain('http://localhost:8000/v1/auth/me')
    expectBoundedSignals()
  })

  it('renders unavailable aggregate data as unknown and keeps shell source labels neutral', () => {
    const overview = readFileSync(
      'components/dashboard/DashboardOverviewPageClient.tsx',
      'utf8',
    )
    const notifications = readFileSync(
      'components/dashboard/NotificationsPageClient.tsx',
      'utf8',
    )
    const standup = readFileSync('components/dashboard/StandupPageClient.tsx', 'utf8')
    const router = readFileSync('components/dashboard/DashboardContentRouter.tsx', 'utf8')

    expect(overview).not.toContain('budget ? formatCurrency(budget.credits_remaining) : "$0"')
    expect(overview).toContain('value={budgetKnown ? formatCurrency(budget.credits_remaining) : "Unknown"}')
    expect(notifications).toContain('title={inboxCoverageComplete ? "Inbox is clear" : "Inbox coverage is incomplete"}')
    expect(standup).toContain('"Unknown"')
    expect(router).toContain("{ label: 'Data', value: 'Aggregated sources' }")
    expect(router).toContain("{ label: 'Data', value: 'Aggregated signals' }")
    expect(router).toContain("{ label: 'Data', value: 'Derived snapshot' }")
  })
})
