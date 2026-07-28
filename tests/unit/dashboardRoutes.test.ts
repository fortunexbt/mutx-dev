import { NextRequest } from 'next/server'

const applyAuthCookies = jest.fn()
const authenticatedFetch = jest.fn()
const getAuthToken = jest.fn()
const hasAuthSession = jest.fn()
const proxyJson = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
  applyAuthCookies,
  authenticatedFetch,
  getAuthToken,
  hasAuthSession,
}))

jest.mock('../../app/api/_lib/proxy', () => ({
  proxyJson,
}))

function mockRequest(url = 'http://localhost:3000/api/test') {
  return {
    url,
    nextUrl: new URL(url),
  } as NextRequest
}

describe('dashboard route proxies', () => {
  beforeEach(() => {
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    getAuthToken.mockReset()
    hasAuthSession.mockReset()
    proxyJson.mockReset()
    global.fetch = jest.fn()
  })

  it('returns 401 from dashboard agents proxy when no auth token exists', async () => {
    hasAuthSession.mockReturnValue(false)
    const { GET } = await import('../../app/api/dashboard/agents/route')

    const response = await GET(mockRequest())

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ status: 'error', error: { code: 'UNAUTHORIZED', message: 'Unauthorized' } })
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('returns 401 from dashboard agents proxy when auth fails', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 401,
        json: async () => ({ detail: 'Session expired' }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/dashboard/agents/route')

    const response = await GET(mockRequest())

    expect(authenticatedFetch).toHaveBeenCalledWith(mockRequest(), 'http://localhost:8000/v1/agents?skip=0&limit=20', {
      cache: 'no-store',
    })
    expect(response.status).toBe(401)
  })

  it('preserves upstream forbidden responses for dashboard agents proxy', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 403,
        json: async () => ({ detail: 'Forbidden' }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/dashboard/agents/route')

    const response = await GET(mockRequest())

    expect(authenticatedFetch).toHaveBeenCalledWith(mockRequest(), 'http://localhost:8000/v1/agents?skip=0&limit=20', {
      cache: 'no-store',
    })
    expect(response.status).toBe(403)
    await expect(response.json()).resolves.toEqual({ detail: 'Forbidden' })
  })

  it('preserves successful list responses for dashboard agents proxy', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        json: async () => ({
          items: [
            {
              id: 'agent_123',
              name: 'runtime-agent',
              status: 'running',
            },
          ],
          total: 1,
          skip: 0,
          limit: 20,
          has_more: false,
        }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/dashboard/agents/route')

    const response = await GET(mockRequest())

    expect(authenticatedFetch).toHaveBeenCalledWith(mockRequest(), 'http://localhost:8000/v1/agents?skip=0&limit=20', {
      cache: 'no-store',
    })
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      items: [
        {
          id: 'agent_123',
          name: 'runtime-agent',
          status: 'running',
        },
      ],
      total: 1,
      skip: 0,
      limit: 20,
      has_more: false,
    })
  })

  it('forwards agents pagination and preserves the authoritative envelope', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        json: async () => ({
          items: [{ id: 'agent_21', name: 'next-page', status: 'stopped' }],
          total: 41,
          skip: 20,
          limit: 20,
          has_more: true,
        }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/dashboard/agents/route')
    const request = mockRequest('http://localhost:3000/api/dashboard/agents?skip=20&limit=20')

    const response = await GET(request)

    expect(authenticatedFetch).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/agents?skip=20&limit=20',
      { cache: 'no-store' },
    )
    await expect(response.json()).resolves.toEqual({
      items: [{ id: 'agent_21', name: 'next-page', status: 'stopped' }],
      total: 41,
      skip: 20,
      limit: 20,
      has_more: true,
    })
  })

  it('preserves upstream server errors for dashboard agents proxy', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 503,
        json: async () => ({ detail: 'Agent registry unavailable' }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/dashboard/agents/route')

    const response = await GET(mockRequest())

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toEqual({ detail: 'Agent registry unavailable' })
  })

  it('returns 401 from dashboard deployments proxy when no auth token exists', async () => {
    hasAuthSession.mockReturnValue(false)
    const { GET } = await import('../../app/api/dashboard/deployments/route')

    const response = await GET(mockRequest())

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ status: 'error', error: { code: 'UNAUTHORIZED', message: 'Unauthorized' } })
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('returns 401 from dashboard deployments proxy when auth fails', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 401,
        json: async () => ({ detail: 'Session expired' }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/dashboard/deployments/route')

    const response = await GET(mockRequest())

    expect(authenticatedFetch).toHaveBeenCalledWith(mockRequest(), 'http://localhost:8000/v1/deployments?limit=20', {
      cache: 'no-store',
    })
    expect(response.status).toBe(401)
  })

  it('preserves upstream forbidden responses for dashboard deployments proxy', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 403,
        json: async () => ({ detail: 'Forbidden' }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/dashboard/deployments/route')

    const response = await GET(mockRequest())

    expect(authenticatedFetch).toHaveBeenCalledWith(mockRequest(), 'http://localhost:8000/v1/deployments?limit=20', {
      cache: 'no-store',
    })
    expect(response.status).toBe(403)
    await expect(response.json()).resolves.toEqual({ detail: 'Forbidden' })
  })

  it('preserves successful list responses for dashboard deployments proxy', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        json: async () => ({
          items: [
            {
              id: 'dep_123',
              agent_id: 'agent_123',
              status: 'running',
            },
          ],
          total: 1,
          skip: 0,
          limit: 20,
          has_more: false,
        }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/dashboard/deployments/route')

    const response = await GET(mockRequest())

    expect(authenticatedFetch).toHaveBeenCalledWith(mockRequest(), 'http://localhost:8000/v1/deployments?limit=20', {
      cache: 'no-store',
    })
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual([
      {
        id: 'dep_123',
        agent_id: 'agent_123',
        status: 'running',
      },
    ])
  })

  it('proxies deployment creation requests', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 201,
        json: async () => ({ id: 'dep_123', status: 'pending' }),
      },
      tokenRefreshed: false,
    })
    const { POST } = await import('../../app/api/dashboard/deployments/route')

    const response = await POST({
      json: async () => ({ agent_id: '123e4567-e89b-12d3-a456-426614174000' }),
    } as NextRequest)

    expect(authenticatedFetch).toHaveBeenCalledWith(expect.anything(), 'http://localhost:8000/v1/deployments', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ agent_id: '123e4567-e89b-12d3-a456-426614174000' }),
      cache: 'no-store',
    })
    expect(response.status).toBe(201)
    await expect(response.json()).resolves.toEqual({ id: 'dep_123', status: 'pending' })
  })

  it('applies refreshed auth cookies when dashboard agents refreshes the session', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        json: async () => [],
      },
      tokenRefreshed: true,
      refreshedTokens: {
        access_token: 'new_access_token',
        refresh_token: 'new_refresh_token',
        expires_in: 1800,
      },
    })
    const { GET } = await import('../../app/api/dashboard/agents/route')

    const request = mockRequest()
    const response = await GET(request)

    expect(response.status).toBe(200)
    expect(applyAuthCookies).toHaveBeenCalledWith(
      expect.anything(),
      request,
      expect.objectContaining({
        access_token: 'new_access_token',
        refresh_token: 'new_refresh_token',
      })
    )
  })

  it('proxies deployment restart actions', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ id: 'dep_123', status: 'pending' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )
    const { POST } = await import('../../app/api/dashboard/deployments/[id]/route')

    const request = { url: 'http://localhost:3000/api/dashboard/v1/deployments/dep_123?action=restart' } as NextRequest
    const response = await POST(
      request,
      { params: Promise.resolve({ id: 'dep_123' }) }
    )

    expect(proxyJson).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/deployments/dep_123/restart', {
      method: 'POST',
      fallbackMessage: 'Failed to restart deployment',
    })
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ id: 'dep_123', status: 'pending' })
  })

  it('proxies deployment version history requests', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ deployment_id: 'dep_123', items: [], total: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )
    const { GET } = await import('../../app/api/dashboard/deployments/[id]/route')

    const request = {
      url: 'http://localhost:3000/api/dashboard/deployments/dep_123?path=versions',
    } as NextRequest
    const response = await GET(
      request,
      { params: Promise.resolve({ id: 'dep_123' }) }
    )

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/deployments/dep_123/versions',
      {
        fallbackMessage: 'Failed to fetch deployment versions',
      }
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ deployment_id: 'dep_123', items: [], total: 0 })
  })

  it('proxies deployment rollback actions', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ id: 'dep_123', status: 'running', version: 'v1.1.0' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )
    const { POST } = await import('../../app/api/dashboard/deployments/[id]/route')

    const request = {
      url: 'http://localhost:3000/api/dashboard/deployments/dep_123?action=rollback',
      json: async () => ({ version: 1 }),
    } as NextRequest
    const response = await POST(
      request,
      { params: Promise.resolve({ id: 'dep_123' }) }
    )

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/deployments/dep_123/rollback',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version: 1 }),
        fallbackMessage: 'Failed to rollback deployment',
      }
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ id: 'dep_123', status: 'running', version: 'v1.1.0' })
  })

  it('proxies deployment delete actions', async () => {
    proxyJson.mockResolvedValue(new Response(null, { status: 204 }))
    const { DELETE } = await import('../../app/api/dashboard/deployments/[id]/route')

    const request = mockRequest()
    const response = await DELETE(
      request,
      { params: Promise.resolve({ id: 'dep_123' }) }
    )

    expect(proxyJson).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/deployments/dep_123', {
      method: 'DELETE',
      fallbackMessage: 'Failed to delete deployment',
    })
    expect(response.status).toBe(204)
  })

  it('forwards starter-template deploy bodies to the backend', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ agent: { id: 'agent_123' }, deployment: { id: 'dep_123' } }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    )
    const { POST } = await import('../../app/api/dashboard/templates/[templateId]/deploy/route')

    const request = {
      json: async () => ({ name: 'Pico Starter Assistant', workspace: 'pico-starter' }),
    } as NextRequest
    const response = await POST(request, {
      params: Promise.resolve({ templateId: 'personal_assistant' }),
    })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/templates/personal_assistant/deploy',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: 'Pico Starter Assistant', workspace: 'pico-starter' }),
        fallbackMessage: 'Failed to deploy starter template',
      }
    )
    expect(response.status).toBe(201)
  })

  it('preserves upstream unauthorized responses for auth me proxy', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 401,
        json: async () => ({ detail: 'Session expired' }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/auth/me/route')

    const response = await GET(mockRequest())

    expect(authenticatedFetch).toHaveBeenCalledWith(mockRequest(), 'http://localhost:8000/v1/auth/me', {
      cache: 'no-store',
    })
    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ detail: 'Session expired' })
  })

  it('returns 401 from auth me proxy when no auth token exists', async () => {
    hasAuthSession.mockReturnValue(false)
    const { GET } = await import('../../app/api/auth/me/route')

    const response = await GET(mockRequest())

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ detail: 'Unauthorized' })
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('preserves successful auth me payloads', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        json: async () => ({
          id: 'user_123',
          email: 'operator@mutx.dev',
          name: 'Operator',
        }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/auth/me/route')

    const response = await GET(mockRequest())

    expect(authenticatedFetch).toHaveBeenCalledWith(mockRequest(), 'http://localhost:8000/v1/auth/me', {
      cache: 'no-store',
    })
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      id: 'user_123',
      email: 'operator@mutx.dev',
      name: 'Operator',
    })
  })

  it('preserves upstream health payloads and statuses', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      status: 503,
      json: async () => ({ status: 'degraded', detail: 'database unavailable' }),
    })
    const { GET } = await import('../../app/api/dashboard/health/route')

    const response = await GET()

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/health',
      expect.objectContaining({
        cache: 'no-store',
      })
    )
    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toEqual({
      status: 'degraded',
      detail: 'database unavailable',
    })
  })

  it('returns a degraded status on health timeout', async () => {
    const timeoutError = new DOMException('The operation was aborted.', 'AbortError')
    ;(global.fetch as jest.Mock).mockRejectedValue(timeoutError)
    const { GET } = await import('../../app/api/dashboard/health/route')

    const response = await GET()

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/health',
      expect.objectContaining({
        cache: 'no-store',
      })
    )
    expect(response.status).toBe(504)
    await expect(response.json()).resolves.toEqual(
      expect.objectContaining({
        status: 'degraded',
        error: 'Health check timed out',
      })
    )
  })

  it('preserves upstream unauthorized responses for api keys proxy', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 401,
        json: async () => ({ detail: 'Session expired' }),
      },
      tokenRefreshed: false,
    })
    const { GET } = await import('../../app/api/api-keys/route')

    const response = await GET(mockRequest())

    expect(authenticatedFetch).toHaveBeenCalledWith(mockRequest(), 'http://localhost:8000/v1/api-keys', {
      cache: 'no-store',
    })
    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ detail: 'Session expired' })
  })

  it('preserves upstream conflict responses for api key creation', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 409,
        json: async () => ({ detail: 'Active API key limit reached' }),
      },
      tokenRefreshed: false,
    })
    const { POST } = await import('../../app/api/api-keys/route')

    const request = {
      json: async () => ({ name: 'Demo key' }),
    } as NextRequest
    const response = await POST(request)

    expect(authenticatedFetch).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/api-keys', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name: 'Demo key' }),
      cache: 'no-store',
    })
    expect(response.status).toBe(409)
    await expect(response.json()).resolves.toEqual({ detail: 'Active API key limit reached' })
  })

  it('returns a fallback health payload when the health proxy throws', async () => {
    ;(global.fetch as jest.Mock).mockRejectedValue(new Error('socket hang up'))
    const { GET } = await import('../../app/api/dashboard/health/route')

    const response = await GET()

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toEqual(
      expect.objectContaining({
        status: 'degraded',
        error: 'Connection failed',
      })
    )
  })

  it('proxies dashboard runs with default limit and forwarded filters', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { GET } = await import('../../app/api/dashboard/runs/route')

    const request = mockRequest('http://localhost:3000/api/dashboard/runs?status=failed')
    const response = await GET(request)

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/runs?status=failed&limit=24',
      {
        method: 'GET',
        fallbackMessage: 'Failed to fetch runs',
      },
    )
    expect(response.status).toBe(200)
  })

  it('proxies dashboard run traces for the selected run', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { GET } = await import('../../app/api/dashboard/runs/[runId]/traces/route')

    const request = mockRequest('http://localhost:3000/api/dashboard/runs/run_123/traces?limit=64')
    const response = await GET(request, {
      params: Promise.resolve({ runId: 'run_123' }),
    })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/runs/run_123/traces?limit=64',
      {
        method: 'GET',
        fallbackMessage: 'Failed to fetch run traces',
      },
    )
    expect(response.status).toBe(200)
  })

  it('proxies document template fetches', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify([{ id: 'document_analysis' }]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { GET } = await import('../../app/api/dashboard/documents/templates/route')

    const request = mockRequest('http://localhost:3000/api/dashboard/documents/templates')
    const response = await GET(request)

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/documents/templates',
      {
        method: 'GET',
        fallbackMessage: 'Failed to fetch document templates',
      },
    )
    expect(response.status).toBe(200)
  })

  it('proxies document job listing with a default page size', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { GET } = await import('../../app/api/dashboard/documents/jobs/route')

    const request = mockRequest('http://localhost:3000/api/dashboard/documents/jobs')
    const response = await GET(request)

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/documents/jobs?limit=24',
      {
        method: 'GET',
        fallbackMessage: 'Failed to fetch document jobs',
      },
    )
    expect(response.status).toBe(200)
  })

  it('forwards document job creation bodies to the backend', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ id: 'job_123', template_id: 'document_analysis' }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { POST } = await import('../../app/api/dashboard/documents/jobs/route')

    const request = {
      json: async () => ({
        template_id: 'document_analysis',
        execution_mode: 'managed',
        parameters: { instructions: 'Summarize' },
      }),
    } as NextRequest
    const response = await POST(request)

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/documents/jobs',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_id: 'document_analysis',
          execution_mode: 'managed',
          parameters: { instructions: 'Summarize' },
        }),
        fallbackMessage: 'Failed to create document job',
      },
    )
    expect(response.status).toBe(201)
  })

  it('forwards document dispatch bodies to the backend', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ id: 'job_123', status: 'queued' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { POST } = await import('../../app/api/dashboard/documents/jobs/[jobId]/dispatch/route')

    const request = {
      json: async () => ({ mode: 'managed' }),
    } as NextRequest
    const response = await POST(request, {
      params: Promise.resolve({ jobId: 'job_123' }),
    })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/documents/jobs/job_123/dispatch',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'managed' }),
        fallbackMessage: 'Failed to dispatch document job',
      },
    )
    expect(response.status).toBe(200)
  })

  it('proxies reasoning template fetches', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify([{ id: 'autoreason_refine' }]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { GET } = await import('../../app/api/dashboard/reasoning/templates/route')

    const request = mockRequest('http://localhost:3000/api/dashboard/reasoning/templates')
    const response = await GET(request)

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/reasoning/templates',
      {
        method: 'GET',
        fallbackMessage: 'Failed to fetch reasoning templates',
      },
    )
    expect(response.status).toBe(200)
  })

  it('proxies reasoning job listing with a default page size', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { GET } = await import('../../app/api/dashboard/reasoning/jobs/route')

    const request = mockRequest('http://localhost:3000/api/dashboard/reasoning/jobs')
    const response = await GET(request)

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/reasoning/jobs?limit=24',
      {
        method: 'GET',
        fallbackMessage: 'Failed to fetch reasoning jobs',
      },
    )
    expect(response.status).toBe(200)
  })

  it('forwards reasoning job creation bodies to the backend', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ id: 'job_abc', template_id: 'autoreason_refine' }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { POST } = await import('../../app/api/dashboard/reasoning/jobs/route')

    const request = {
      json: async () => ({
        template_id: 'autoreason_refine',
        execution_mode: 'managed',
        parameters: { task_prompt: 'Refine this memo' },
      }),
    } as NextRequest
    const response = await POST(request)

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/reasoning/jobs',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_id: 'autoreason_refine',
          execution_mode: 'managed',
          parameters: { task_prompt: 'Refine this memo' },
        }),
        fallbackMessage: 'Failed to create reasoning job',
      },
    )
    expect(response.status).toBe(201)
  })

  it('forwards reasoning dispatch bodies to the backend', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ id: 'job_abc', status: 'queued' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { POST } = await import('../../app/api/dashboard/reasoning/jobs/[jobId]/dispatch/route')

    const request = {
      json: async () => ({ mode: 'managed' }),
    } as NextRequest
    const response = await POST(request, {
      params: Promise.resolve({ jobId: 'job_abc' }),
    })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/reasoning/jobs/job_abc/dispatch',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'managed' }),
        fallbackMessage: 'Failed to dispatch reasoning job',
      },
    )
    expect(response.status).toBe(200)
  })

  it('proxies dashboard monitoring alerts with a default page size', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0, unresolved_count: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { GET } = await import('../../app/api/dashboard/monitoring/alerts/route')

    const request = mockRequest('http://localhost:3000/api/dashboard/monitoring/alerts')
    const response = await GET(request)

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/monitoring/alerts?limit=12',
      {
        method: 'GET',
        fallbackMessage: 'Failed to fetch alerts',
      },
    )
    expect(response.status).toBe(200)
  })

  it('returns 401 from dashboard observability proxy when no auth session exists', async () => {
    hasAuthSession.mockReturnValue(false)
    const { GET } = await import('../../app/api/dashboard/observability/route')

    const response = await GET(mockRequest('http://localhost:3000/api/dashboard/observability'))

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })
  })

  it('aggregates telemetry and session summary into dashboard observability responses', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({
          items: [{ id: 'run_123', agent_id: 'agent_123', status: 'running' }],
          total: 1,
          skip: 0,
          limit: 25,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({
          otel_enabled: true,
          exporter_type: 'otlp',
          endpoint: 'http://collector:4318',
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({
          configured: true,
          endpoint_reachable: true,
          using_grpc: false,
          endpoint: 'http://collector:4318',
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({
          sessions: [
            {
              id: 'sess_1',
              active: true,
              channel: 'web',
              source: 'gateway',
              last_activity: '2026-04-14T10:00:00Z',
            },
            {
              id: 'sess_2',
              active: false,
              channel: 'cli',
              source: 'desktop',
              last_activity: '2026-04-14T11:00:00Z',
            },
          ],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })

    const { GET } = await import('../../app/api/dashboard/observability/route')
    const request = mockRequest('http://localhost:3000/api/dashboard/observability?limit=25')
    const response = await GET(request)

    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      1,
      request,
      'http://localhost:8000/v1/observability/runs?limit=25',
      { cache: 'no-store' },
    )
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      2,
      request,
      'http://localhost:8000/v1/telemetry/config',
      { cache: 'no-store' },
    )
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      3,
      request,
      'http://localhost:8000/v1/telemetry/health',
      { cache: 'no-store' },
    )
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      4,
      request,
      'http://localhost:8000/v1/sessions?limit=100',
      { cache: 'no-store' },
    )

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      items: [{ id: 'run_123', agent_id: 'agent_123', status: 'running' }],
      total: 1,
      skip: 0,
      limit: 25,
      telemetry: {
        config: {
          otel_enabled: true,
          exporter_type: 'otlp',
          endpoint: 'http://collector:4318',
        },
        health: {
          configured: true,
          endpoint_reachable: true,
          using_grpc: false,
          endpoint: 'http://collector:4318',
        },
        errors: null,
      },
      sessionSummary: {
        total: 2,
        active: 1,
        channels: 2,
        sources: 2,
        latestActivityAt: '2026-04-14T11:00:00.000Z',
      },
      sessionSummaryError: null,
    })
  })

  it('reuses the refreshed access token for follow-up observability summary calls', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({
          items: [],
          total: 0,
          skip: 0,
          limit: 50,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: true,
        refreshedTokens: {
          access_token: 'fresh_access_token',
          refresh_token: 'fresh_refresh_token',
          expires_in: 1800,
        },
      })
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({
          otel_enabled: true,
          exporter_type: 'otlp',
          endpoint: 'http://collector:4318',
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({
          configured: true,
          endpoint_reachable: true,
          using_grpc: false,
          endpoint: 'http://collector:4318',
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({ sessions: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })

    const { GET } = await import('../../app/api/dashboard/observability/route')
    const request = new NextRequest('http://localhost:3000/api/dashboard/observability', {
      headers: {
        cookie: 'access_token=stale_access_token; refresh_token=stale_refresh_token; theme=dark',
      },
    })

    const response = await GET(request)

    expect(response.status).toBe(200)
    expect(authenticatedFetch).toHaveBeenCalledTimes(4)
    expect(authenticatedFetch.mock.calls[0][0]).toBe(request)

    const followupRequest = authenticatedFetch.mock.calls[1][0] as NextRequest
    expect(followupRequest).not.toBe(request)
    expect(followupRequest.headers.get('authorization')).toBe('Bearer fresh_access_token')
    expect(followupRequest.cookies.get('access_token')?.value).toBe('fresh_access_token')
    expect(followupRequest.cookies.get('refresh_token')?.value).toBe('fresh_refresh_token')
    expect(followupRequest.cookies.get('theme')?.value).toBe('dark')
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      2,
      followupRequest,
      'http://localhost:8000/v1/telemetry/config',
      { cache: 'no-store' },
    )
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      3,
      followupRequest,
      'http://localhost:8000/v1/telemetry/health',
      { cache: 'no-store' },
    )
    expect(authenticatedFetch).toHaveBeenNthCalledWith(
      4,
      followupRequest,
      'http://localhost:8000/v1/sessions?limit=100',
      { cache: 'no-store' },
    )
  })

  it('keeps observability runs available when telemetry summary calls fail', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({
          items: [],
          total: 0,
          skip: 0,
          limit: 50,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({ detail: 'telemetry unavailable' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({
          configured: false,
          endpoint_reachable: false,
          using_grpc: true,
          endpoint: null,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })
      .mockResolvedValueOnce({
        response: new Response(JSON.stringify({ sessions: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
        tokenRefreshed: false,
      })

    const { GET } = await import('../../app/api/dashboard/observability/route')
    const response = await GET(mockRequest('http://localhost:3000/api/dashboard/observability'))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      items: [],
      total: 0,
      skip: 0,
      limit: 50,
      telemetry: {
        config: null,
        health: {
          configured: false,
          endpoint_reachable: false,
          using_grpc: true,
          endpoint: null,
        },
        errors: {
          config: 'telemetry unavailable',
        },
      },
      sessionSummary: {
        total: 0,
        active: 0,
        channels: 0,
        sources: 0,
        latestActivityAt: null,
      },
      sessionSummaryError: null,
    })
  })

  it('proxies dashboard budget usage with forwarded query params', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ usage_by_agent: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { GET } = await import('../../app/api/dashboard/budgets/usage/route')

    const request = mockRequest('http://localhost:3000/api/dashboard/budgets/usage?period_start=30d')
    const response = await GET(request)

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/budgets/usage?period_start=30d',
      {
        method: 'GET',
        fallbackMessage: 'Failed to fetch usage breakdown',
      },
    )
    expect(response.status).toBe(200)
  })

  it('proxies dashboard analytics summary', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ total_runs: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { GET } = await import('../../app/api/dashboard/analytics/summary/route')

    const request = mockRequest('http://localhost:3000/api/dashboard/analytics/summary?period_start=30d')
    const response = await GET(request)

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/analytics/summary?period_start=30d',
      {
        method: 'GET',
        fallbackMessage: 'Failed to fetch analytics summary',
      },
    )
    expect(response.status).toBe(200)
  })

  it('proxies dashboard swarms scale actions', async () => {
    proxyJson.mockResolvedValue(
      new Response(JSON.stringify({ id: 'swarm_123' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { POST } = await import('../../app/api/dashboard/swarms/[swarmId]/scale/route')

    const request = {
      json: async () => ({ replicas: 3 }),
    } as NextRequest
    const response = await POST(request, {
      params: Promise.resolve({ swarmId: 'swarm_123' }),
    })

    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/swarms/swarm_123/scale',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ replicas: 3 }),
        fallbackMessage: 'Failed to scale swarm',
      },
    )
    expect(response.status).toBe(200)
  })
})
