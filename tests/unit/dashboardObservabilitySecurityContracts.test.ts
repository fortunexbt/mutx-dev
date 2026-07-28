import { readFileSync } from 'node:fs'
import { join } from 'node:path'

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

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

function mockRequest(runId = 'run_123') {
  return new NextRequest(
    `http://localhost:3000/api/dashboard/observability/runs/${encodeURIComponent(runId)}`,
  )
}

function upstreamResponse(payload: unknown, status: number) {
  return {
    response: new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
    tokenRefreshed: false,
  }
}

const runDetail = {
  id: 'run_123',
  agent_id: 'agent_123',
  status: 'completed',
  started_at: '2026-07-28T09:00:00Z',
  ended_at: '2026-07-28T09:00:01Z',
  duration_ms: 1000,
  step_count: 1,
  tools_available: ['web.search'],
  tags: ['production'],
  run_metadata: {},
  created_at: '2026-07-28T09:00:00Z',
  steps: [
    {
      id: 'step_1',
      type: 'tool_call',
      tool_name: 'web.search',
      input_preview: 'Find the current incident status',
      success: true,
      started_at: '2026-07-28T09:00:00Z',
      duration_ms: 0,
      step_metadata: {},
    },
  ],
}

describe('dashboard observability detail proxy', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
  })

  it('returns the backend run-detail contract, including real steps', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue(upstreamResponse(runDetail, 200))

    const request = mockRequest()
    const { GET } = await import('../../app/api/dashboard/observability/runs/[runId]/route')
    const response = await GET(request, { params: Promise.resolve({ runId: 'run_123' }) })

    expect(authenticatedFetch).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/observability/runs/run_123',
      {
        method: 'GET',
        cache: 'no-store',
      },
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual(runDetail)
  })

  it('returns 401 without an operator session', async () => {
    hasAuthSession.mockReturnValue(false)

    const { GET } = await import('../../app/api/dashboard/observability/runs/[runId]/route')
    const response = await GET(mockRequest(), {
      params: Promise.resolve({ runId: 'run_123' }),
    })

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it.each([
    [403, 'Not authorized to access this run'],
    [404, 'Run not found'],
    [500, 'Observability storage unavailable'],
  ])('preserves backend %i responses', async (status, detail) => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue(upstreamResponse({ detail }, status))

    const { GET } = await import('../../app/api/dashboard/observability/runs/[runId]/route')
    const response = await GET(mockRequest(), {
      params: Promise.resolve({ runId: 'run_123' }),
    })

    expect(response.status).toBe(status)
    await expect(response.json()).resolves.toEqual({ detail })
  })

  it('encodes the selected run ID before building the upstream URL', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue(upstreamResponse(runDetail, 200))

    const request = mockRequest('run/with spaces')
    const { GET } = await import('../../app/api/dashboard/observability/runs/[runId]/route')
    await GET(request, { params: Promise.resolve({ runId: 'run/with spaces' }) })

    expect(authenticatedFetch).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/observability/runs/run%2Fwith%20spaces',
      expect.objectContaining({ method: 'GET' }),
    )
  })
})

describe('dashboard observability and security client contracts', () => {
  it('loads selected observability details independently and renders backend steps', () => {
    const source = readSource('components/dashboard/ObservabilityPageClient.tsx')

    expect(source).toContain('components["schemas"]["MutxRunDetailResponse"]')
    expect(source).toContain('/api/dashboard/observability/runs/${encodeURIComponent(activeRunId)}')
    expect(source).toContain('setDetailLoading(true)')
    expect(source).toContain('setDetailError(')
    expect(source).toContain('selectedRun.steps.map((step, i)')
    expect(source).toContain('title="No steps recorded"')
  })

  it('uses only fields from the generated APIKeyResponse contract', () => {
    const source = readSource('components/dashboard/SecurityPageClient.tsx')

    expect(source).toContain('components["schemas"]["APIKeyResponse"]')
    expect(source).toContain('key.is_active')
    expect(source).toContain('key.last_used')
    expect(source).not.toContain('key.status')
    expect(source).not.toContain('key.scopes')
    expect(source).not.toContain('key.key_prefix')
    expect(source).not.toContain('key.last_used_at')
  })

  it('does not render trace failures as empty or retain stale trace rows', () => {
    const source = readSource('components/dashboard/TracesPageClient.tsx')
    const errorBranch = source.indexOf(') : traceError ? (')
    const emptyBranch = source.indexOf(') : traces.length === 0 ? (')

    expect(source).toContain('setTraces([])')
    expect(source).toContain('setTraceError(')
    expect(errorBranch).toBeGreaterThan(-1)
    expect(emptyBranch).toBeGreaterThan(errorBranch)
  })
})
