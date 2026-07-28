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

function mockRequest() {
  return {} as NextRequest
}

function mockJsonRequest(body: unknown) {
  return {
    json: async () => body,
  } as NextRequest
}

describe('API key route proxies', () => {
  beforeEach(() => {
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
  })

  it('returns 401 when no auth session exists', async () => {
    hasAuthSession.mockReturnValue(false)

    const { GET } = await import('../../app/api/api-keys/route')
    const response = await GET(mockRequest())

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({ error: 'Unauthorized' })
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })

  it('preserves upstream list failures', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 403,
        json: async () => ({ detail: 'Forbidden' }),
      },
      tokenRefreshed: false,
    })

    const request = mockRequest()
    const { GET } = await import('../../app/api/api-keys/route')
    const response = await GET(request)

    expect(authenticatedFetch).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/api-keys', {
      cache: 'no-store',
    })
    expect(response.status).toBe(403)
    await expect(response.json()).resolves.toEqual({ detail: 'Forbidden' })
  })

  it('preserves upstream rotate conflicts', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 409,
        json: async () => ({ detail: 'Key rotation is already in progress' }),
      },
      tokenRefreshed: false,
    })

    const request = mockRequest()
    const { POST } = await import('../../app/api/api-keys/[id]/rotate/route')
    const response = await POST(request, {
      params: Promise.resolve({ id: 'key_123' }),
    })

    expect(response.status).toBe(409)
    await expect(response.json()).resolves.toEqual({
      detail: 'Key rotation is already in progress',
    })
  })

  it('preserves upstream revoke server errors', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        ok: false,
        status: 503,
        json: async () => ({ detail: 'Credential store unavailable' }),
      },
      tokenRefreshed: false,
    })

    const request = mockRequest()
    const { DELETE } = await import('../../app/api/api-keys/[id]/route')
    const response = await DELETE(request, {
      params: Promise.resolve({ id: 'key_123' }),
    })

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toEqual({
      detail: 'Credential store unavailable',
    })
  })

  it('preserves successful list responses', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        json: async () => [{ id: 'key_111', name: 'deploy-key', is_active: true }],
      },
      tokenRefreshed: false,
    })

    const { GET } = await import('../../app/api/api-keys/route')
    const response = await GET(mockRequest())

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual([
      { id: 'key_111', name: 'deploy-key', is_active: true },
    ])
  })

  it('preserves upstream create conflicts', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 409,
        json: async () => ({ detail: 'Active API key limit reached (10)' }),
      },
      tokenRefreshed: false,
    })

    const request = mockJsonRequest({ name: 'overflow-key' })
    const { POST } = await import('../../app/api/api-keys/route')
    const response = await POST(request)

    expect(authenticatedFetch).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/api-keys', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name: 'overflow-key' }),
      cache: 'no-store',
    })
    expect(response.status).toBe(409)
    await expect(response.json()).resolves.toEqual({
      detail: 'Active API key limit reached (10)',
    })
  })

  it('preserves successful create responses', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 201,
        json: async () => ({ id: 'key_789', name: 'build-key', key: 'mutx_live_created' }),
      },
      tokenRefreshed: false,
    })

    const { POST } = await import('../../app/api/api-keys/route')
    const response = await POST(mockJsonRequest({ name: 'build-key' }))

    expect(response.status).toBe(201)
    await expect(response.json()).resolves.toEqual({
      id: 'key_789',
      name: 'build-key',
      key: 'mutx_live_created',
    })
  })

  it('applies refreshed auth cookies when create rotates the session', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 201,
        json: async () => ({ id: 'key_999', name: 'build-key', key: 'mutx_live_created' }),
      },
      tokenRefreshed: true,
      refreshedTokens: {
        access_token: 'new_access_token',
        refresh_token: 'new_refresh_token',
        expires_in: 1800,
      },
    })

    const request = mockJsonRequest({ name: 'build-key' })
    const { POST } = await import('../../app/api/api-keys/route')
    const response = await POST(request)

    expect(response.status).toBe(201)
    expect(applyAuthCookies).toHaveBeenCalledWith(
      expect.anything(),
      request,
      expect.objectContaining({
        access_token: 'new_access_token',
        refresh_token: 'new_refresh_token',
      })
    )
  })

  it('preserves successful revoke responses', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        ok: true,
        status: 204,
      },
      tokenRefreshed: false,
    })

    const request = mockRequest()
    const { DELETE } = await import('../../app/api/api-keys/[id]/route')
    const response = await DELETE(request, {
      params: Promise.resolve({ id: 'key_123' }),
    })

    expect(authenticatedFetch).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/api-keys/key_123', {
      method: 'DELETE',
      cache: 'no-store',
    })
    expect(response.status).toBe(204)
  })

  it('preserves successful rotate responses', async () => {
    hasAuthSession.mockReturnValue(true)
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        json: async () => ({ id: 'key_456', name: 'rotated-key', key: 'mutx_live_rotated' }),
      },
      tokenRefreshed: false,
    })

    const request = mockRequest()
    const { POST } = await import('../../app/api/api-keys/[id]/rotate/route')
    const response = await POST(request, {
      params: Promise.resolve({ id: 'key_123' }),
    })

    expect(authenticatedFetch).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/api-keys/key_123/rotate', {
      method: 'POST',
      cache: 'no-store',
    })
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      id: 'key_456',
      name: 'rotated-key',
      key: 'mutx_live_rotated',
    })
  })
})
