import type { NextRequest } from 'next/server'

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

function mockRequest(options: MockRequestOptions = {}) {
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
      get: () => ({ value: 'token' }),
    },
  } as unknown as NextRequest
}

describe('pico package route', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
  })

  it('rejects package generation when no auth session exists', async () => {
    hasAuthSession.mockReturnValue(false)

    const { POST } = await import('../../app/api/pico/package/route')
    const request = mockRequest({ body: { session_id: 'sess_123' } })

    const response = await POST(request)

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toMatchObject({
      status: 'error',
      error: {
        code: 'UNAUTHORIZED',
        message: 'Unauthorized',
      },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('forwards the exact session and sanitizes upstream download headers', async () => {
    hasAuthSession.mockReturnValue(true)
    const zipBytes = Uint8Array.from([80, 75, 3, 4])
    authenticatedFetch.mockResolvedValue({
      response: new Response(zipBytes, {
        status: 200,
        headers: {
          'content-type': 'application/octet-stream',
          'content-disposition': 'attachment; filename="../../starter agent.zip"',
        },
      }),
      tokenRefreshed: false,
    })

    const { POST } = await import('../../app/api/pico/package/route')
    const request = mockRequest({ body: { session_id: 'sess_123', include_readme: true } })

    const response = await POST(request)

    expect(authenticatedFetch).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/pico/generate-package',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: 'sess_123' }),
        cache: 'no-store',
      },
    )
    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toBe('application/octet-stream')
    expect(response.headers.get('content-disposition')).toBe('attachment; filename="starter-agent.zip"')
    expect(response.headers.get('cache-control')).toBe('no-store')
    expect(response.headers.get('x-content-type-options')).toBe('nosniff')
    expect(Array.from(new Uint8Array(await response.arrayBuffer()))).toEqual(Array.from(zipBytes))
    expect(applyAuthCookies).not.toHaveBeenCalled()
  })

  it('rejects invalid JSON before calling the package service', async () => {
    hasAuthSession.mockReturnValue(true)

    const { POST } = await import('../../app/api/pico/package/route')
    const request = mockRequest({ jsonError: new SyntaxError('Unexpected end of JSON input') })

    const response = await POST(request)

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toMatchObject({
      error: {
        message: 'Invalid JSON in request body',
      },
    })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('preserves upstream JSON failures instead of turning them into downloads', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: Response.json(
        { detail: 'This onboarding session has expired. Start a new session to continue.' },
        { status: 410 },
      ),
      tokenRefreshed: false,
    })

    const { POST } = await import('../../app/api/pico/package/route')
    const response = await POST(mockRequest({ body: { session_id: 'sess_123' } }))

    expect(response.status).toBe(410)
    expect(response.headers.get('content-disposition')).toBeNull()
    await expect(response.json()).resolves.toEqual({
      detail: 'This onboarding session has expired. Start a new session to continue.',
    })
  })

  it('rejects a successful response whose body is not a ZIP archive', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: new Response(Uint8Array.from([1, 2, 3]), {
        status: 200,
        headers: { 'content-type': 'application/zip' },
      }),
      tokenRefreshed: false,
    })

    const { POST } = await import('../../app/api/pico/package/route')
    const response = await POST(mockRequest({ body: { session_id: 'sess_123' } }))

    expect(response.status).toBe(502)
    expect(response.headers.get('content-disposition')).toBeNull()
    await expect(response.json()).resolves.toEqual({
      detail: 'Package service returned an invalid ZIP archive',
    })
  })
})
