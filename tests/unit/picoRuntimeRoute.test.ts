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

type MockRequestOptions = {
  body?: unknown
  jsonError?: Error
}

function createJsonRequest(options: MockRequestOptions = {}) {
  const { body = {}, jsonError } = options

  return {
    json: async () => {
      if (jsonError) {
        throw jsonError
      }
      return body
    },
    headers: {
      get: () => null,
    },
    cookies: {
      get: () => undefined,
    },
    nextUrl: new URL('https://pico.mutx.dev/api/pico/runtime/openclaw'),
  } as unknown as NextRequest
}

describe('pico runtime route', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it('returns 401 for runtime provider reads when no auth session exists', async () => {
    hasAuthSession.mockReturnValue(false)

    const { GET } = await import('../../app/api/pico/runtime/[provider]/route')
    const request = new NextRequest('https://pico.mutx.dev/api/pico/runtime/openclaw')

    const response = await GET(request, {
      params: Promise.resolve({ provider: 'openclaw' }),
    })

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('preserves fetched runtime timestamps and explicit stale state', async () => {
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        json: async () => ({
          provider: 'openclaw',
          label: 'OpenClaw',
          status: 'healthy',
          last_seen_at: '2026-07-28T08:00:00Z',
          last_synced_at: '2026-07-28T08:01:00Z',
          stale: true,
          stale_after_seconds: 900,
          binding_count: 1,
        }),
      },
      tokenRefreshed: false,
    })

    const { GET } = await import('../../app/api/pico/runtime/[provider]/route')
    const request = new NextRequest('https://pico.mutx.dev/api/pico/runtime/openclaw')
    const response = await GET(request, {
      params: Promise.resolve({ provider: 'openclaw' }),
    })

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      status: 'healthy',
      last_seen_at: '2026-07-28T08:00:00Z',
      last_synced_at: '2026-07-28T08:01:00Z',
      stale: true,
      stale_after_seconds: 900,
    })
  })

  it('preserves runtime provider failures instead of returning a healthy default', async () => {
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 503,
        json: async () => ({ detail: 'Runtime snapshot store unavailable' }),
      },
      tokenRefreshed: false,
    })

    const { GET } = await import('../../app/api/pico/runtime/[provider]/route')
    const request = new NextRequest('https://pico.mutx.dev/api/pico/runtime/openclaw')
    const response = await GET(request, {
      params: Promise.resolve({ provider: 'openclaw' }),
    })

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toEqual({
      detail: 'Runtime snapshot store unavailable',
    })
  })

  it('rejects invalid provider path values before contacting the control plane', async () => {
    const { GET } = await import('../../app/api/pico/runtime/[provider]/route')
    const request = new NextRequest('https://pico.mutx.dev/api/pico/runtime/invalid')
    const response = await GET(request, {
      params: Promise.resolve({ provider: '../governance' }),
    })

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: 'BAD_REQUEST', message: 'Invalid runtime provider' },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('returns 401 for runtime provider updates before parsing an invalid body', async () => {
    hasAuthSession.mockReturnValue(false)

    const { PUT } = await import('../../app/api/pico/runtime/[provider]/route')
    const syntaxError = Object.assign(new SyntaxError('Unexpected end of JSON input'), {
      status: 400,
    })

    const response = await PUT(
      createJsonRequest({
        jsonError: syntaxError,
      }),
      {
        params: Promise.resolve({ provider: 'openclaw' }),
      },
    )

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('returns 400 for malformed runtime JSON after authentication', async () => {
    const { PUT } = await import('../../app/api/pico/runtime/[provider]/route')
    const syntaxError = new SyntaxError('Unexpected end of JSON input')

    const response = await PUT(
      createJsonRequest({ jsonError: syntaxError }),
      { params: Promise.resolve({ provider: 'openclaw' }) },
    )

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: 'BAD_REQUEST', message: 'Invalid JSON in request body' },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('forwards runtime provider updates with a JSON body when authenticated', async () => {
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        json: async () => ({
          provider: 'openclaw',
          label: 'OpenClaw',
          status: 'healthy',
        }),
      },
      tokenRefreshed: false,
    })

    const { PUT } = await import('../../app/api/pico/runtime/[provider]/route')
    const request = createJsonRequest({
      body: {
        label: 'OpenClaw',
        status: 'healthy',
        gateway_url: 'http://localhost:8080',
      },
    })

    const response = await PUT(request, {
      params: Promise.resolve({ provider: 'openclaw' }),
    })

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      provider: 'openclaw',
      label: 'OpenClaw',
      status: 'healthy',
    })
    expect(authenticatedFetch).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/runtime/providers/openclaw',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          label: 'OpenClaw',
          status: 'healthy',
          gateway_url: 'http://localhost:8080',
        }),
        cache: 'no-store',
      },
    )
  })
})
