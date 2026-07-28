import { NextRequest } from 'next/server'

const proxyJson = jest.fn()
const hasAuthSession = jest.fn()

jest.mock('../../app/api/_lib/controlPlane', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
  hasAuthSession,
}))

jest.mock('../../app/api/_lib/proxy', () => ({
  proxyJson,
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
  } as unknown as NextRequest
}

describe('pico onboarding route', () => {
  let consoleErrorSpy: jest.SpyInstance

  beforeEach(() => {
    jest.resetModules()
    proxyJson.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    consoleErrorSpy.mockRestore()
  })

  it('preserves onboarding query params when fetching setup state', async () => {
    const proxiedResponse = new Response(JSON.stringify({ current_step: 'auth' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    proxyJson.mockResolvedValue(proxiedResponse)

    const { GET } = await import('../../app/api/pico/onboarding/route')
    const request = new NextRequest(
      'https://pico.mutx.dev/api/pico/onboarding?provider=openclaw&step=auth',
    )

    const response = await GET(request)

    expect(response).toBe(proxiedResponse)
    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/onboarding?provider=openclaw&step=auth',
      {
        fallbackMessage: 'Failed to fetch Pico onboarding state',
      },
    )
  })

  it('loads an exact durable coach session without leaking the internal view parameter', async () => {
    const proxiedResponse = new Response(JSON.stringify({ session_id: 'sess_123' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    proxyJson.mockResolvedValue(proxiedResponse)

    const { GET } = await import('../../app/api/pico/onboarding/route')
    const request = new NextRequest(
      'https://pico.mutx.dev/api/pico/onboarding?view=coach_session&session_id=sess_123',
    )

    const response = await GET(request)

    expect(response).toBe(proxiedResponse)
    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/pico/session?session_id=sess_123',
      { fallbackMessage: 'Failed to resume Pico onboarding session' },
    )
  })

  it('forwards onboarding mutations to the backend with a JSON body', async () => {
    const proxiedResponse = new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    proxyJson.mockResolvedValue(proxiedResponse)

    const { POST } = await import('../../app/api/pico/onboarding/route')
    const request = createJsonRequest({
      body: {
        action: 'complete_step',
        provider: 'openclaw',
        step: 'auth',
        payload: { completed: true },
      },
    })

    const response = await POST(request)

    expect(response).toBe(proxiedResponse)
    expect(proxyJson).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/onboarding', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        action: 'complete_step',
        provider: 'openclaw',
        step: 'auth',
        payload: { completed: true },
      }),
      fallbackMessage: 'Failed to update Pico onboarding state',
    })
  })

  it('forwards trimmed coach turns through the durable Pico chat contract', async () => {
    const proxiedResponse = new Response(JSON.stringify({ session_id: 'sess_123' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    proxyJson.mockResolvedValue(proxiedResponse)

    const { POST } = await import('../../app/api/pico/onboarding/route')
    const request = createJsonRequest({
      body: {
        action: 'coach_message',
        message: '  Help me install Hermes.  ',
        session_id: 'sess_123',
        request_id: 'request_123',
      },
    })

    const response = await POST(request)

    expect(response).toBe(proxiedResponse)
    expect(proxyJson).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/pico/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: 'Help me install Hermes.',
        session_id: 'sess_123',
        request_id: 'request_123',
      }),
      fallbackMessage: 'Pico onboarding coach request failed',
    })
  })

  it('forwards authenticated coach start-over to the durable session reset', async () => {
    const proxiedResponse = new Response(null, { status: 204 })
    proxyJson.mockResolvedValue(proxiedResponse)
    const sessionId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

    const { DELETE } = await import('../../app/api/pico/onboarding/route')
    const request = new NextRequest(
      `https://pico.mutx.dev/api/pico/onboarding?session_id=${sessionId}`,
      { method: 'DELETE' },
    )
    const response = await DELETE(request)

    expect(response).toBe(proxiedResponse)
    expect(proxyJson).toHaveBeenCalledWith(
      request,
      `http://localhost:8000/v1/pico/session?session_id=${sessionId}`,
      {
        method: 'DELETE',
        fallbackMessage: 'Failed to reset Pico onboarding session',
      },
    )
  })

  it('rejects unauthenticated coach start-over before contacting the backend', async () => {
    hasAuthSession.mockReturnValue(false)

    const { DELETE } = await import('../../app/api/pico/onboarding/route')
    const request = new NextRequest('https://pico.mutx.dev/api/pico/onboarding', {
      method: 'DELETE',
    })
    const response = await DELETE(request)

    expect(response.status).toBe(401)
    expect(proxyJson).not.toHaveBeenCalled()
  })

  it('returns a 400 when the onboarding request body is invalid JSON', async () => {
    const { POST } = await import('../../app/api/pico/onboarding/route')
    const syntaxError = Object.assign(new SyntaxError('Unexpected end of JSON input'), {
      status: 400,
    })

    const response = await POST(
      createJsonRequest({
        jsonError: syntaxError,
      }),
    )

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: {
        code: 'BAD_REQUEST',
        message: 'Invalid JSON in request body',
      },
    })
    expect(proxyJson).not.toHaveBeenCalled()
  })
})
