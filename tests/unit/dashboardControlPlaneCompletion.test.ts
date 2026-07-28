import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { NextRequest } from 'next/server'

import { resolveAnalyticsResources } from '../../components/dashboard/AnalyticsPageClient'
import { resolveBudgetResources } from '../../components/dashboard/BudgetsPageClient'

const applyAuthCookies = jest.fn()
const authenticatedFetch = jest.fn()
const hasAuthSession = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  applyAuthCookies,
  authenticatedFetch,
  getApiBaseUrl: () => 'http://localhost:8000',
  hasAuthSession,
}))

function request(url: string, init?: ConstructorParameters<typeof NextRequest>[1]) {
  return new NextRequest(url, init)
}

function upstream(payload: unknown, status = 200) {
  return {
    response: status === 204
      ? new Response(null, { status })
      : new Response(JSON.stringify(payload), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
    tokenRefreshed: false,
  }
}

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

const swarm = {
  id: '2a35c9c0-5552-43c6-84cb-7d7c453a7c6e',
  name: 'Incident response',
  description: 'Coordinated operators',
  agent_ids: ['ab0b46d6-6d0f-42ee-aa32-f4236b720614'],
  min_replicas: 1,
  max_replicas: 5,
  created_at: '2026-07-28T09:00:00Z',
  updated_at: '2026-07-28T09:00:00Z',
  agents: [],
}

const alert = {
  id: 'b59d7c93-a08e-43cf-bc90-4fdf30a531f8',
  agent_id: 'ab0b46d6-6d0f-42ee-aa32-f4236b720614',
  type: 'agent_down',
  message: 'Agent stopped reporting',
  resolved: false,
  created_at: '2026-07-28T09:00:00Z',
  resolved_at: null,
}

describe('completed control-plane mutation proxies', () => {
  beforeEach(() => {
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it('forwards session transcript and control requests with encoded gateway keys', async () => {
    authenticatedFetch
      .mockResolvedValueOnce(upstream({ session_key: 'agent/main', messages: [], total_count: 0 }))
      .mockResolvedValueOnce(upstream({ session_key: 'agent/main', action: 'pause', current_state: 'paused' }))

    const transcriptRequest = request('http://localhost:3000/api/dashboard/sessions/agent%2Fmain/transcript')
    const { GET } = await import('../../app/api/dashboard/sessions/[sessionKey]/transcript/route')
    const transcriptResponse = await GET(transcriptRequest, {
      params: Promise.resolve({ sessionKey: 'agent/main' }),
    })

    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      1,
      transcriptRequest,
      'http://localhost:8000/v1/sessions/agent%2Fmain/transcript',
      { method: 'GET', cache: 'no-store' },
    )
    expect(transcriptResponse.status).toBe(200)

    const controlRequest = request('http://localhost:3000/api/dashboard/sessions/agent%2Fmain/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'pause' }),
    })
    const { POST } = await import('../../app/api/dashboard/sessions/[sessionKey]/control/route')
    const controlResponse = await POST(controlRequest, {
      params: Promise.resolve({ sessionKey: 'agent/main' }),
    })

    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      2,
      controlRequest,
      'http://localhost:8000/v1/sessions/agent%2Fmain/control',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'pause' }),
        cache: 'no-store',
      },
    )
    expect(controlResponse.status).toBe(200)
  })

  it('forwards session deletion using the backend request-body contract', async () => {
    authenticatedFetch.mockResolvedValue(upstream({
      session_key: 'session-1',
      action: 'delete',
      applied: true,
    }))
    const deleteRequest = request('http://localhost:3000/api/dashboard/sessions', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_key: 'session-1' }),
    })
    const { DELETE } = await import('../../app/api/dashboard/sessions/route')
    const response = await DELETE(deleteRequest)

    expect(authenticatedFetch).toHaveBeenCalledWith(
      deleteRequest,
      'http://localhost:8000/v1/sessions',
      {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_key: 'session-1' }),
        cache: 'no-store',
      },
    )
    expect(response.status).toBe(200)
  })

  it('forwards swarm creation and preserves the backend 201 response', async () => {
    authenticatedFetch.mockResolvedValue(upstream(swarm, 201))
    const payload = {
      name: swarm.name,
      description: swarm.description,
      agent_ids: swarm.agent_ids,
      min_replicas: 1,
      max_replicas: 5,
    }
    const createRequest = request('http://localhost:3000/api/dashboard/swarms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const { POST } = await import('../../app/api/dashboard/swarms/route')
    const response = await POST(createRequest)

    expect(authenticatedFetch).toHaveBeenCalledWith(
      createRequest,
      'http://localhost:8000/v1/swarms',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        cache: 'no-store',
      },
    )
    expect(response.status).toBe(201)
    await expect(response.json()).resolves.toEqual(swarm)
  })

  it('forwards swarm update, scale, and delete mutations', async () => {
    authenticatedFetch
      .mockResolvedValueOnce(upstream({ ...swarm, name: 'Updated swarm' }))
      .mockResolvedValueOnce(upstream(swarm))
      .mockResolvedValueOnce(upstream(null, 204))

    const updateRequest = request(`http://localhost:3000/api/dashboard/swarms/${swarm.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Updated swarm', min_replicas: 2, max_replicas: 5 }),
    })
    const detailRoute = await import('../../app/api/dashboard/swarms/[swarmId]/route')
    const updateResponse = await detailRoute.PATCH(updateRequest, {
      params: Promise.resolve({ swarmId: swarm.id }),
    })
    expect(updateResponse.status).toBe(200)
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      1,
      updateRequest,
      `http://localhost:8000/v1/swarms/${swarm.id}`,
      expect.objectContaining({ method: 'PATCH', cache: 'no-store' }),
    )

    const scaleRequest = request(`http://localhost:3000/api/dashboard/swarms/${swarm.id}/scale`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ replicas: 3 }),
    })
    const scaleRoute = await import('../../app/api/dashboard/swarms/[swarmId]/scale/route')
    const scaleResponse = await scaleRoute.POST(scaleRequest, {
      params: Promise.resolve({ swarmId: swarm.id }),
    })
    expect(scaleResponse.status).toBe(200)
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      2,
      scaleRequest,
      `http://localhost:8000/v1/swarms/${swarm.id}/scale`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ replicas: 3 }), cache: 'no-store' }),
    )

    const deleteRequest = request(`http://localhost:3000/api/dashboard/swarms/${swarm.id}`, {
      method: 'DELETE',
    })
    const deleteResponse = await detailRoute.DELETE(deleteRequest, {
      params: Promise.resolve({ swarmId: swarm.id }),
    })
    expect(deleteResponse.status).toBe(204)
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      3,
      deleteRequest,
      `http://localhost:8000/v1/swarms/${swarm.id}`,
      { method: 'DELETE', cache: 'no-store' },
    )
  })

  it('forwards monitoring resolve controls', async () => {
    authenticatedFetch.mockResolvedValue(upstream({ ...alert, resolved: true }))
    const resolveRequest = request(`http://localhost:3000/api/dashboard/monitoring/alerts/${alert.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolved: true }),
    })
    const { PATCH } = await import('../../app/api/dashboard/monitoring/alerts/[alertId]/route')
    const response = await PATCH(resolveRequest, {
      params: Promise.resolve({ alertId: alert.id }),
    })

    expect(authenticatedFetch).toHaveBeenCalledWith(
      resolveRequest,
      `http://localhost:8000/v1/monitoring/alerts/${alert.id}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved: true }),
        cache: 'no-store',
      },
    )
    expect(response.status).toBe(200)
  })

  it('returns 401 locally when no operator session exists', async () => {
    hasAuthSession.mockReturnValue(false)
    const { GET } = await import('../../app/api/dashboard/sessions/[sessionKey]/transcript/route')
    const response = await GET(
      request('http://localhost:3000/api/dashboard/sessions/session-1/transcript'),
      { params: Promise.resolve({ sessionKey: 'session-1' }) },
    )

    expect(response.status).toBe(401)
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it.each([
    ['control', 403, 'Session control forbidden'],
    ['transcript', 404, 'Session not found'],
    ['swarm', 409, 'Swarm update conflict'],
    ['alert', 503, 'Monitoring store unavailable'],
    ['delete', 500, 'Gateway deletion failed'],
  ])('preserves %s upstream %i responses', async (routeName, status, detail) => {
    authenticatedFetch.mockResolvedValue(upstream({ detail }, status))

    let response: Response
    if (routeName === 'control') {
      const route = await import('../../app/api/dashboard/sessions/[sessionKey]/control/route')
      response = await route.POST(request('http://localhost/control', {
        method: 'POST',
        body: JSON.stringify({ action: 'kill' }),
      }), { params: Promise.resolve({ sessionKey: 'session-1' }) })
    } else if (routeName === 'transcript') {
      const route = await import('../../app/api/dashboard/sessions/[sessionKey]/transcript/route')
      response = await route.GET(request('http://localhost/transcript'), {
        params: Promise.resolve({ sessionKey: 'missing' }),
      })
    } else if (routeName === 'swarm') {
      const route = await import('../../app/api/dashboard/swarms/[swarmId]/route')
      response = await route.PATCH(request('http://localhost/swarm', {
        method: 'PATCH',
        body: JSON.stringify({ name: 'Conflict' }),
      }), { params: Promise.resolve({ swarmId: swarm.id }) })
    } else if (routeName === 'alert') {
      const route = await import('../../app/api/dashboard/monitoring/alerts/[alertId]/route')
      response = await route.PATCH(request('http://localhost/alert', {
        method: 'PATCH',
        body: JSON.stringify({ resolved: true }),
      }), { params: Promise.resolve({ alertId: alert.id }) })
    } else {
      const route = await import('../../app/api/dashboard/sessions/route')
      response = await route.DELETE(request('http://localhost/sessions', {
        method: 'DELETE',
        body: JSON.stringify({ session_key: 'session-1' }),
      }))
    }

    expect(response.status).toBe(status)
    await expect(response.json()).resolves.toEqual({ detail })
  })
})

describe('paginated dashboard proxy contracts', () => {
  beforeEach(() => {
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it.each([
    {
      name: 'swarms',
      url: 'http://localhost:3000/api/dashboard/swarms?skip=16&limit=16',
      upstreamUrl: 'http://localhost:8000/v1/swarms?skip=16&limit=16',
      payload: { items: [swarm], total: 33, skip: 16, limit: 16, has_more: true },
      load: () => import('../../app/api/dashboard/swarms/route'),
    },
    {
      name: 'alerts',
      url: 'http://localhost:3000/api/dashboard/monitoring/alerts?skip=16&limit=16',
      upstreamUrl: 'http://localhost:8000/v1/monitoring/alerts?skip=16&limit=16',
      payload: { items: [alert], total: 28, unresolved_count: 7, skip: 16, limit: 16, has_more: true },
      load: () => import('../../app/api/dashboard/monitoring/alerts/route'),
    },
    {
      name: 'usage events',
      url: 'http://localhost:3000/api/dashboard/usage/events?skip=12&limit=12',
      upstreamUrl: 'http://localhost:8000/v1/usage/events?skip=12&limit=12',
      payload: { items: [], total: 25, skip: 12, limit: 12, has_more: true },
      load: () => import('../../app/api/dashboard/usage/events/route'),
    },
  ])('preserves the $name envelope and query', async ({ url, upstreamUrl, payload, load }) => {
    authenticatedFetch.mockResolvedValue(upstream(payload))
    const route = await load()
    const listRequest = request(url)
    const response = await route.GET(listRequest)

    expect(authenticatedFetch).toHaveBeenCalledWith(
      listRequest,
      upstreamUrl,
      { method: 'GET', cache: 'no-store' },
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual(payload)
  })
})

describe('partial resource resolution', () => {
  it('keeps budget core data and a real event envelope when optional resources fail', () => {
    const budget = {
      user_id: 'ce934445-3cdf-423a-a662-0611acf277cf',
      plan: 'pro',
      credits_total: 1000,
      credits_used: 125,
      credits_remaining: 875,
      reset_date: '2026-08-01T00:00:00Z',
      usage_percentage: 12.5,
    }
    const events = { items: [], total: 21, skip: 0, limit: 12, has_more: true }
    const snapshot = resolveBudgetResources([
      { status: 'fulfilled', value: budget },
      { status: 'rejected', reason: new Error('Usage database unavailable') },
      { status: 'rejected', reason: new Error('Analytics timed out') },
      { status: 'fulfilled', value: events },
    ])

    expect(snapshot.budget.data).toEqual(budget)
    expect(snapshot.usage.error).toBe('Usage database unavailable')
    expect(snapshot.summary.error).toBe('Analytics timed out')
    expect(snapshot.events.data).toEqual(events)
    expect(snapshot.events.data?.total).toBe(21)
    expect(snapshot.events.data?.has_more).toBe(true)
  })

  it('keeps valid analytics trends and costs when the summary and latency resources fail', () => {
    const runTrend = {
      metric: 'runs',
      interval: 'day',
      data: [{ timestamp: '2026-07-28T00:00:00Z', value: 7, label: null }],
      period_start: '2026-06-28T00:00:00Z',
      period_end: '2026-07-28T00:00:00Z',
    }
    const costs = {
      total_credits_used: 48,
      credits_remaining: 952,
      credits_total: 1000,
      usage_by_event_type: { api_call: 48 },
      usage_by_agent: { agent_1: 48 },
      period_start: '2026-06-28T00:00:00Z',
      period_end: '2026-07-28T00:00:00Z',
    }
    const snapshot = resolveAnalyticsResources([
      { status: 'rejected', reason: new Error('Summary unavailable') },
      { status: 'fulfilled', value: runTrend },
      { status: 'rejected', reason: new Error('Latency query failed') },
      { status: 'fulfilled', value: costs },
    ])

    expect(snapshot.summary.error).toBe('Summary unavailable')
    expect(snapshot.runTrend.data).toEqual(runTrend)
    expect(snapshot.latencyTrend.error).toBe('Latency query failed')
    expect(snapshot.costs.data).toEqual(costs)
  })

  it('accepts truthful unavailable numeric samples without rejecting the analytics payload', () => {
    const summary = {
      total_agents: 1,
      active_agents: 1,
      total_deployments: 1,
      active_deployments: 1,
      total_runs: 0,
      successful_runs: 0,
      failed_runs: 0,
      total_api_calls: 0,
      avg_latency_ms: null,
      period_start: '2026-06-28T00:00:00Z',
      period_end: '2026-07-28T00:00:00Z',
      incomplete: true,
    }
    const trend = {
      metric: 'latency',
      interval: 'day',
      data: [{ timestamp: '2026-07-28T00:00:00Z', value: null, label: null }],
      period_start: '2026-06-28T00:00:00Z',
      period_end: '2026-07-28T00:00:00Z',
      incomplete: true,
    }
    const snapshot = resolveAnalyticsResources([
      { status: 'fulfilled', value: summary },
      { status: 'fulfilled', value: trend },
      { status: 'fulfilled', value: trend },
      { status: 'rejected', reason: new Error('Costs unavailable') },
    ])

    expect(snapshot.summary.data).toEqual(summary)
    expect(snapshot.runTrend.data).toEqual(trend)
    expect(snapshot.latencyTrend.data).toEqual(trend)
  })

  it('keeps dialog confirmation, canonical reload, allSettled, stale, and unavailable UI contracts visible', () => {
    const sessions = readSource('components/dashboard/SessionsPageClient.tsx')
    const swarms = readSource('components/dashboard/SwarmsPageClient.tsx')
    const monitoring = readSource('components/dashboard/MonitoringPageClient.tsx')
    const budgets = readSource('components/dashboard/BudgetsPageClient.tsx')
    const analytics = readSource('components/dashboard/AnalyticsPageClient.tsx')

    expect(sessions).toContain('<DashboardDialog')
    expect(sessions).not.toMatch(/\bconfirm\s*\(/)
    expect(sessions).toContain('await loadSessions(false)')
    expect(sessions).toContain('/transcript`')
    expect(swarms).toContain('await canonicalReload()')
    expect(swarms).toContain('Load more (${swarms.length} of ${total})')
    expect(monitoring).toContain('Last updated')
    expect(monitoring).toContain('Resolve alert')
    expect(budgets).toContain('Promise.allSettled')
    expect(budgets).toContain('showing previously loaded data (stale)')
    expect(budgets).toContain('"Unavailable"')
    expect(analytics).toContain('Promise.allSettled')
    expect(analytics).toContain('Partial analytics data')
    expect(analytics).toContain('"Unavailable"')
  })
})
