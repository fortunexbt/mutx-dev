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

function request(path: string, body: Record<string, string>) {
  return new NextRequest(`http://localhost:3000${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function upstream(payload: unknown, status = 200) {
  return {
    response: {
      ok: status >= 200 && status < 300,
      status,
      json: async () => payload,
    },
    tokenRefreshed: false,
  }
}

describe('dashboard ClawHub mutation proxies', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it('preserves the configured install envelope and request body', async () => {
    const envelope = {
      status: 'configured',
      operation: 'configure',
      skill_id: 'browser_control',
      runtime_ready: false,
      reconciliation_required: true,
      skills: [{ id: 'browser_control', status: 'configured', configured: true }],
    }
    authenticatedFetch.mockResolvedValueOnce(upstream(envelope))
    const { POST } = await import('../../app/api/dashboard/clawhub/install/route')

    const response = await POST(
      request('/api/dashboard/clawhub/install', {
        agent_id: 'agent-1',
        skill_id: 'browser_control',
      }),
    )

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual(envelope)
    expect(authenticatedFetch).toHaveBeenCalledWith(
      expect.any(NextRequest),
      'http://localhost:8000/v1/clawhub/install',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ agent_id: 'agent-1', skill_id: 'browser_control' }),
      }),
    )
  })

  it('preserves remove and bundle lifecycle envelopes', async () => {
    const removeEnvelope = {
      status: 'removed',
      operation: 'remove',
      skill_id: 'browser_control',
      skills: [{ id: 'browser_control', status: 'available', configured: false }],
    }
    authenticatedFetch.mockResolvedValueOnce(upstream(removeEnvelope))
    const uninstallRoute = await import('../../app/api/dashboard/clawhub/uninstall/route')
    const removeResponse = await uninstallRoute.POST(
      request('/api/dashboard/clawhub/uninstall', {
        agent_id: 'agent-1',
        skill_id: 'browser_control',
      }),
    )
    expect(removeResponse.status).toBe(200)
    await expect(removeResponse.json()).resolves.toEqual(removeEnvelope)

    const bundleEnvelope = {
      status: 'configured',
      operation: 'configure_bundle',
      bundle_id: 'orchestra-research-foundation',
      configured_skill_ids: ['langchain'],
      runtime_ready_skill_ids: [],
      reconciliation_required: true,
      skills: [{ id: 'langchain', status: 'configured', configured: true }],
    }
    authenticatedFetch.mockResolvedValueOnce(upstream(bundleEnvelope))
    const bundleRoute = await import('../../app/api/dashboard/clawhub/install-bundle/route')
    const bundleResponse = await bundleRoute.POST(
      request('/api/dashboard/clawhub/install-bundle', {
        agent_id: 'agent-1',
        bundle_id: 'orchestra-research-foundation',
      }),
    )
    expect(bundleResponse.status).toBe(200)
    await expect(bundleResponse.json()).resolves.toEqual(bundleEnvelope)
  })

  it('preserves failed lifecycle envelopes and upstream status codes', async () => {
    const envelope = {
      status: 'failed',
      operation: 'configure',
      detail: 'Skill files unavailable to this control plane.',
      skill_id: 'missing-skill',
    }
    authenticatedFetch.mockResolvedValueOnce(upstream(envelope, 409))
    const { POST } = await import('../../app/api/dashboard/clawhub/install/route')

    const response = await POST(
      request('/api/dashboard/clawhub/install', {
        agent_id: 'agent-1',
        skill_id: 'missing-skill',
      }),
    )

    expect(response.status).toBe(409)
    await expect(response.json()).resolves.toEqual(envelope)
  })
})
