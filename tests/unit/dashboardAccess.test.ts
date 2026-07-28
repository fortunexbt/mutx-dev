import {
  DASHBOARD_ACCESS_ROUTE,
  DashboardAccessError,
  getDashboardAccessLinks,
  resolveDashboardAccess,
} from '../../components/dashboard/dashboardAccess'

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('dashboard browser access resolution', () => {
  it('uses one quiet access request for an unauthenticated visitor', async () => {
    const fetcher = jest.fn(async () =>
      jsonResponse({ authenticated: false, reason: 'missing_session' }),
    )

    await expect(resolveDashboardAccess(fetcher)).resolves.toEqual({
      authenticated: false,
      reason: 'missing_session',
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(fetcher).toHaveBeenCalledWith(DASHBOARD_ACCESS_ROUTE, {
      cache: 'no-store',
      signal: undefined,
    })
  })

  it('keeps a forbidden account distinct without making follow-up requests', async () => {
    const fetcher = jest.fn(async () =>
      jsonResponse({ authenticated: false, reason: 'access_denied' }),
    )

    await expect(resolveDashboardAccess(fetcher)).resolves.toEqual({
      authenticated: false,
      reason: 'access_denied',
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('maps only a verified user into authenticated dashboard state', async () => {
    const fetcher = jest.fn(async () =>
      jsonResponse({
        authenticated: true,
        user: {
          id: 'user_123',
          email: 'operator@mutx.dev',
          name: 'Runtime Operator',
          roles: ['DEVELOPER', 'VIEWER'],
        },
      }),
    )

    await expect(resolveDashboardAccess(fetcher)).resolves.toEqual({
      authenticated: true,
      user: {
        id: 'user_123',
        email: 'operator@mutx.dev',
        username: 'operator',
        display_name: 'Runtime Operator',
        role: 'operator',
      },
    })
  })

  it('maps the backend role hierarchy without granting unknown roles', async () => {
    const adminFetcher = jest.fn(async () =>
      jsonResponse({
        authenticated: true,
        user: { id: 'admin_1', name: 'Admin', roles: ['VIEWER', 'ADMIN'] },
      }),
    )
    const unknownFetcher = jest.fn(async () =>
      jsonResponse({
        authenticated: true,
        user: { id: 'member_1', name: 'Member', roles: ['EXPERIMENTAL'] },
      }),
    )

    await expect(resolveDashboardAccess(adminFetcher)).resolves.toMatchObject({
      authenticated: true,
      user: { role: 'admin' },
    })
    await expect(resolveDashboardAccess(unknownFetcher)).resolves.toMatchObject({
      authenticated: true,
      user: { role: 'viewer' },
    })
  })

  it('keeps service failures distinct from unauthenticated state', async () => {
    const fetcher = jest.fn(async () =>
      jsonResponse({ detail: 'Auth service unavailable' }, 503),
    )

    await expect(resolveDashboardAccess(fetcher)).rejects.toEqual(
      expect.objectContaining<Partial<DashboardAccessError>>({
        name: 'DashboardAccessError',
        message: 'Auth service unavailable',
        status: 503,
      }),
    )
  })

  it('rejects a successful response that does not identify an operator', async () => {
    const fetcher = jest.fn(async () =>
      jsonResponse({ authenticated: true, user: { email: 'operator@mutx.dev' } }),
    )

    await expect(resolveDashboardAccess(fetcher)).rejects.toMatchObject({
      status: 502,
      message: 'Dashboard access did not identify an operator.',
    })
  })

  it('keeps sign-in and registration on the requested dashboard route and exposes recovery', () => {
    expect(getDashboardAccessLinks('/dashboard/agents')).toEqual({
      login: '/login?next=%2Fdashboard%2Fagents',
      register: '/register?next=%2Fdashboard%2Fagents',
      recovery: '/forgot-password?next=%2Fdashboard%2Fagents',
    })
    expect(getDashboardAccessLinks('https://example.com')).toEqual({
      login: '/login?next=%2Fdashboard',
      register: '/register?next=%2Fdashboard',
      recovery: '/forgot-password?next=%2Fdashboard',
    })
    expect(getDashboardAccessLinks('/agents?status=running&owner=me')).toEqual({
      login: '/login?next=%2Fdashboard%2Fagents%3Fstatus%3Drunning%26owner%3Dme',
      register: '/register?next=%2Fdashboard%2Fagents%3Fstatus%3Drunning%26owner%3Dme',
      recovery: '/forgot-password?next=%2Fdashboard%2Fagents%3Fstatus%3Drunning%26owner%3Dme',
    })
    expect(getDashboardAccessLinks('//evil.example/dashboard?token=secret')).toEqual({
      login: '/login?next=%2Fdashboard',
      register: '/register?next=%2Fdashboard',
      recovery: '/forgot-password?next=%2Fdashboard',
    })
  })
})
