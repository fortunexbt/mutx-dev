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

function mockRequest(url: string) {
  return {
    url,
    nextUrl: new URL(url),
    headers: new Headers(),
  } as NextRequest
}

function mockJsonResponse(payload: unknown, status = 200) {
  return {
    response: {
      ok: status >= 200 && status < 300,
      status,
      json: async () => payload,
    },
    tokenRefreshed: false,
  }
}

describe('dashboard operator panel routes', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
  })

  it('aggregates notification signals without inventing a governance event feed', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'alert_1',
              type: 'budget',
              message: 'Budget threshold crossed',
              resolved: false,
              created_at: '2026-04-19T09:00:00Z',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          total: 7,
          items: [
            {
              id: 'approval_1',
              agent_id: 'agent-1',
              action_type: 'deploy',
              requester: 'operator@mutx.dev',
              status: 'PENDING',
              created_at: '2026-04-19T08:30:00Z',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          status: 'warning',
          pending_approvals: 2,
          policy_name: 'strict',
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse([
          {
            agent_id: 'agent-2',
            status: 'failed',
            started_at: '2026-04-19T07:00:00Z',
          },
        ]),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'webhook_1',
              url: 'https://example.com/hook',
              is_active: true,
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'delivery_1',
              event: 'run.failed',
              success: false,
              error_message: '502 upstream',
              created_at: '2026-04-19T09:05:00Z',
            },
          ],
        }),
      )

    const { GET } = await import('../../app/api/dashboard/notifications/route')
    const response = await GET(mockRequest('http://localhost:3000/api/dashboard/notifications'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.summary).toMatchObject({
      alerts: 1,
      approvals: 7,
      webhookFailures: 1,
      runtimeIncidents: 1,
      governancePendingApprovals: 2,
    })
    expect(payload.items.map((item: { kind: string }) => item.kind)).toEqual(
      expect.arrayContaining(['alert', 'approval', 'webhook', 'governance', 'runtime']),
    )
    expect(payload.partials[0]).toMatch(/decision-by-decision event feed/i)
  })

  it('builds channel posture from assistant overview, channel bindings, and sessions', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce(mockJsonResponse({ id: 'user_1', email: 'ops@mutx.dev' }))
      .mockResolvedValueOnce(
        mockJsonResponse({
          has_assistant: true,
          assistant: {
            agent_id: 'agent-1',
            name: 'Ops Assistant',
            workspace: 'ops',
            status: 'active',
            gateway: {
              status: 'healthy',
              gateway_url: 'https://gateway.mutx.dev',
              doctor_summary: 'Gateway healthy',
            },
            wakeups: [{ enabled: true, label: 'Morning brief' }],
            channels: [],
          },
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse([
          {
            id: 'slack',
            label: 'Slack',
            enabled: true,
            mode: 'bidirectional',
            allow_from: ['workspace'],
          },
        ]),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          sessions: [
            {
              id: 'session_1',
              channel: 'slack',
              active: true,
              source: 'gateway',
              last_activity: '2026-04-19T09:10:00Z',
            },
          ],
        }),
      )

    const { GET } = await import('../../app/api/dashboard/channels/route')
    const response = await GET(mockRequest('http://localhost:3000/api/dashboard/channels'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.hasAssistant).toBe(true)
    expect(payload.summary).toMatchObject({
      configuredChannels: 1,
      enabledChannels: 1,
      liveChannels: 1,
      activeSessions: 1,
      sources: 1,
    })
    expect(payload.channels[0]).toMatchObject({
      id: 'slack',
      sessionCount: 1,
      activeSessions: 1,
    })
    expect(payload.sourceStatus).toEqual({
      overview: 'ok',
      channels: 'ok',
      sessions: 'ok',
    })
  })

  it('keeps incomplete channel contracts partial instead of inventing bindings or zeroes', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce(mockJsonResponse({ id: 'user_1', email: 'ops@mutx.dev' }))
      .mockResolvedValueOnce(
        mockJsonResponse({
          has_assistant: true,
          assistant: {
            agent_id: 'agent-1',
            name: 'Ops Assistant',
            workspace: 'ops',
            status: 'active',
            channels: [],
          },
        }),
      )
      .mockResolvedValueOnce(mockJsonResponse([{ label: 'Missing channel id', enabled: true }]))
      .mockResolvedValueOnce(mockJsonResponse({ detail: 'unexpected session envelope' }))

    const { GET } = await import('../../app/api/dashboard/channels/route')
    const response = await GET(mockRequest('http://localhost:3000/api/dashboard/channels'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.sourceStatus).toMatchObject({ channels: 'partial', sessions: 'partial' })
    expect(payload.summary).toMatchObject({
      configuredChannels: null,
      enabledChannels: null,
      liveChannels: null,
      activeSessions: null,
      sources: null,
    })
    expect(payload.channels).toEqual([])
    expect(payload.partials.join(' ')).toMatch(/identifier was missing/i)
    expect(payload.partials.join(' ')).toMatch(/invalid collection envelope/i)
    expect(JSON.stringify(payload)).not.toContain('"id":"unknown"')
  })

  it('returns a read-only memory inventory from sessions and artifact jobs', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce(mockJsonResponse({ id: 'user_1', email: 'ops@mutx.dev' }))
      .mockResolvedValueOnce(
        mockJsonResponse({
          has_assistant: true,
          assistant: {
            name: 'Ops Assistant',
            workspace: 'ops',
            status: 'active',
          },
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          sessions: [
            {
              id: 'session_1',
              source: 'gateway',
              channel: 'slack',
              active: true,
              last_activity: '2026-04-19T09:15:00Z',
              agent: 'Ops Assistant',
              model: 'gpt-5',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'doc_1',
              template_id: 'runbook',
              status: 'completed',
              execution_mode: 'managed',
              artifacts: [{ id: 'artifact_1' }],
              result_summary: { summary: 'Rendered PDF' },
              updated_at: '2026-04-19T08:00:00Z',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'reason_1',
              template_id: 'postmortem',
              status: 'completed',
              execution_mode: 'managed',
              artifacts: [{ id: 'artifact_1' }, { id: 'artifact_2' }],
              result_summary: { summary: 'Compared outputs' },
              updated_at: '2026-04-19T08:10:00Z',
            },
          ],
        }),
      )

    const { GET } = await import('../../app/api/dashboard/memory/route')
    const response = await GET(mockRequest('http://localhost:3000/api/dashboard/memory'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.summary).toMatchObject({
      sessions: 1,
      activeSessions: 1,
      sources: 1,
      documentJobs: 1,
      documentArtifacts: 1,
      reasoningJobs: 1,
      reasoningArtifacts: 2,
    })
    expect(payload.assistant).toEqual({
      name: 'Ops Assistant',
      workspace: 'ops',
      status: 'active',
    })
    expect(payload.sessions).toEqual([
      {
        id: 'session_1',
        label: 'Ops Assistant',
        source: 'gateway',
        channel: 'slack',
        active: true,
        kind: 'session',
        model: 'gpt-5',
        lastActivity: '2026-04-19T09:15:00.000Z',
        flags: [],
      },
    ])
    expect(payload.sources).toEqual([{ source: 'gateway', count: 1 }])
    expect(payload.documents).toEqual([
      expect.objectContaining({
        id: 'doc_1',
        templateId: 'runbook',
        executionMode: 'managed',
        artifacts: 1,
        resultSummary: 'Rendered PDF',
        updatedAt: '2026-04-19T08:00:00.000Z',
      }),
    ])
    expect(payload.reasoning).toEqual([
      expect.objectContaining({
        id: 'reason_1',
        templateId: 'postmortem',
        executionMode: 'managed',
        artifacts: 2,
        resultSummary: 'Compared outputs',
        updatedAt: '2026-04-19T08:10:00.000Z',
      }),
    ])
    expect(payload).not.toHaveProperty('documentJobs')
    expect(payload).not.toHaveProperty('reasoningJobs')
    expect(payload.sourceStatus).toEqual({
      assistant: 'ok',
      sessions: 'ok',
      documents: 'ok',
      reasoning: 'ok',
    })
    expect(payload.partials[0]).toMatch(/read-only/i)
  })

  it('keeps malformed memory records partial instead of manufacturing identifiers or zeroes', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce(mockJsonResponse({ id: 'user_1', email: 'ops@mutx.dev' }))
      .mockResolvedValueOnce(
        mockJsonResponse({
          has_assistant: true,
          assistant: { name: 'Ops Assistant', workspace: 'ops', status: 'active' },
        }),
      )
      .mockResolvedValueOnce(mockJsonResponse({ sessions: [{ active: true }] }))
      .mockResolvedValueOnce(mockJsonResponse({ detail: 'unexpected envelope' }))
      .mockResolvedValueOnce(mockJsonResponse({ detail: 'reasoning unavailable' }, 503))

    const { GET } = await import('../../app/api/dashboard/memory/route')
    const response = await GET(mockRequest('http://localhost:3000/api/dashboard/memory'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.sourceStatus).toMatchObject({
      sessions: 'partial',
      documents: 'partial',
      reasoning: 'error',
    })
    expect(payload.summary).toMatchObject({
      sessions: null,
      activeSessions: null,
      documentJobs: null,
      documentArtifacts: null,
      reasoningJobs: null,
      reasoningArtifacts: null,
    })
    expect(payload.sessions).toEqual([])
    expect(payload.documents).toEqual([])
    expect(payload.reasoning).toEqual([])
    expect(payload.partials.join(' ')).toMatch(/identifier was missing/i)
    expect(payload.partials.join(' ')).toMatch(/invalid collection envelope/i)
    expect(JSON.stringify(payload)).not.toContain('session-1')
  })

  it('composes orchestration truth from approvals, recovery signals, and blueprint inventory', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce(mockJsonResponse({ id: 'user_1', email: 'ops@mutx.dev' }))
      .mockResolvedValueOnce(
        mockJsonResponse({
          total: 5,
          items: [
            {
              id: 'approval_1',
              agent_id: 'agent-1',
              action_type: 'promote',
              requester: 'operator@mutx.dev',
              status: 'PENDING',
              created_at: '2026-04-19T09:00:00Z',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'run_1',
              status: 'failed',
              subject_label: 'Support agent',
              error_message: 'Tool timeout',
              completed_at: '2026-04-19T08:45:00Z',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          sessions: [
            {
              id: 'session_1',
              active: false,
              agent: 'Ops Assistant',
              source: 'gateway',
              last_activity: '2026-04-19T08:30:00Z',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse([
          {
            id: 'blueprint_1',
            name: 'Escalation Swarm',
            summary: 'Tiered triage',
            recommended_min_agents: 2,
            recommended_max_agents: 4,
            roles: [{ id: 'lead' }, { id: 'scribe' }],
            tags: ['support'],
          },
        ]),
      )

    const { GET } = await import('../../app/api/dashboard/orchestration/route')
    const response = await GET(mockRequest('http://localhost:3000/api/dashboard/orchestration'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.summary).toMatchObject({
      pendingApprovals: 5,
      recoveryWatch: 2,
      blueprints: 1,
      queuedAutonomy: null,
    })
    expect(payload.partials).toEqual(
      expect.arrayContaining([expect.stringMatching(/local-only/i)]),
    )
  })

  it('keeps malformed orchestration records partial instead of exposing actionable fake ids', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce(mockJsonResponse({ id: 'user_1', email: 'ops@mutx.dev' }))
      .mockResolvedValueOnce(
        mockJsonResponse({ items: [{ status: 'PENDING', action_type: 'deploy' }] }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({ items: [{ status: 'failed', error_message: 'Tool timeout' }] }),
      )
      .mockResolvedValueOnce(mockJsonResponse({ sessions: [{ active: false }] }))
      .mockResolvedValueOnce(mockJsonResponse([{ name: 'Unidentified blueprint' }]))

    const { GET } = await import('../../app/api/dashboard/orchestration/route')
    const response = await GET(mockRequest('http://localhost:3000/api/dashboard/orchestration'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.sourceStatus).toMatchObject({
      approvals: 'partial',
      runs: 'partial',
      sessions: 'partial',
      blueprints: 'partial',
      autonomy: 'partial',
    })
    expect(payload.summary).toMatchObject({
      pendingApprovals: null,
      recoveryWatch: null,
      blueprints: null,
      queuedAutonomy: null,
      runningAutonomy: null,
    })
    expect(payload.approvals).toEqual([])
    expect(payload.recoveries).toEqual([])
    expect(payload.blueprints).toEqual([])
    expect(payload.partials.join(' ')).toMatch(/identifier was missing/i)
    expect(JSON.stringify(payload)).not.toMatch(/approval-1|session-1|blueprint-1/)
  })

  it('derives a standup brief from live blockers, watch items, and completions', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'alert_1',
              message: 'Pager duty',
              type: 'latency',
              resolved: false,
              created_at: '2026-04-19T09:00:00Z',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'approval_1',
              agent_id: 'agent-1',
              action_type: 'deploy',
              requester: 'operator@mutx.dev',
              status: 'PENDING',
              created_at: '2026-04-19T08:40:00Z',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'run_failed',
              status: 'failed',
              subject_label: 'Support agent',
              error_message: 'Tool timeout',
              completed_at: '2026-04-19T08:20:00Z',
            },
            {
              id: 'run_done',
              status: 'completed',
              subject_label: 'Billing agent',
              output_text: 'Closed 14 invoices',
              completed_at: '2026-04-19T07:50:00Z',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'webhook_1',
              url: 'https://example.com/hook',
              is_active: true,
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          items: [
            {
              id: 'delivery_1',
              event: 'run.failed',
              success: false,
              error_message: '502 upstream',
              created_at: '2026-04-19T09:05:00Z',
            },
          ],
        }),
      )

    const { GET } = await import('../../app/api/dashboard/standup/route')
    const response = await GET(mockRequest('http://localhost:3000/api/dashboard/standup'))
    const payload = await response.json()

    expect(response.status).toBe(200)
    expect(payload.focus).toMatch(/Clear .* blocking signal/i)
    expect(payload.metrics).toMatchObject({
      openAlerts: 1,
      pendingApprovals: 1,
      failedRuns: 1,
      queuedAutonomy: null,
    })
    expect(payload.blockers).toHaveLength(3)
    expect(payload.completions).toHaveLength(1)
  })
})
