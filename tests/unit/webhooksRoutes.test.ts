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

describe('Webhooks route proxies', () => {
  beforeEach(() => {
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
  })

  describe('GET /api/webhooks', () => {
    it('returns 401 when no auth session exists', async () => {
      hasAuthSession.mockReturnValue(false)

      const { GET } = await import('../../app/api/webhooks/route')
      const response = await GET(mockRequest())

      expect(response.status).toBe(401)
      await expect(response.json()).resolves.toEqual({
        status: 'error',
        error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
      })
      expect(authenticatedFetch).not.toHaveBeenCalled()
    })

    it('wraps paginated responses into a webhooks collection payload', async () => {
      hasAuthSession.mockReturnValue(true)
      authenticatedFetch.mockResolvedValue({
        response: {
          ok: true,
          status: 200,
          json: async () => ({
            items: [
              { id: 'wh_456', name: 'another-webhook', url: 'https://example.com/hook', events: ['agent.stopped'], active: false },
            ],
            total: 1,
            skip: 0,
            limit: 50,
          }),
        },
        tokenRefreshed: false,
      })

      const request = mockRequest()
      const { GET } = await import('../../app/api/webhooks/route')
      const response = await GET(request)

      expect(authenticatedFetch).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/webhooks', {
        headers: {
          'Content-Type': 'application/json',
        },
        cache: 'no-store',
      })
      expect(response.status).toBe(200)
      await expect(response.json()).resolves.toEqual({
        webhooks: [
          { id: 'wh_456', name: 'another-webhook', url: 'https://example.com/hook', events: ['agent.stopped'], active: false },
        ],
        total: 1,
        skip: 0,
        limit: 50,
      })
    })

    it('preserves backend error responses', async () => {
      hasAuthSession.mockReturnValue(true)
      authenticatedFetch.mockResolvedValue({
        response: {
          ok: false,
          status: 500,
          json: async () => ({ detail: 'Internal server error' }),
        },
        tokenRefreshed: false,
      })

      const { GET } = await import('../../app/api/webhooks/route')
      const response = await GET(mockRequest())

      expect(response.status).toBe(500)
      await expect(response.json()).resolves.toEqual({ error: 'Internal server error' })
    })
  })

  describe('POST /api/webhooks', () => {
    it('returns 401 when no auth session exists', async () => {
      hasAuthSession.mockReturnValue(false)

      const { POST } = await import('../../app/api/webhooks/route')
      const response = await POST(
        mockJsonRequest({
          name: 'my-webhook',
          url: 'https://example.com/webhook',
          events: ['agent.deployed'],
        })
      )

      expect(response.status).toBe(401)
      await expect(response.json()).resolves.toEqual({
        status: 'error',
        error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
      })
    })

    it('returns validation errors for invalid payloads', async () => {
      hasAuthSession.mockReturnValue(true)

      const { POST } = await import('../../app/api/webhooks/route')
      const response = await POST(mockJsonRequest({ name: 'missing-url' }))

      expect(response.status).toBe(400)
      const json = await response.json()
      expect(json.error.code).toBe('VALIDATION_ERROR')
      expect(authenticatedFetch).not.toHaveBeenCalled()
    })

    it('proxies valid webhook creation requests', async () => {
      hasAuthSession.mockReturnValue(true)
      authenticatedFetch.mockResolvedValue({
        response: {
          ok: true,
          status: 201,
          json: async () => ({
            id: 'wh_new',
            name: 'my-webhook',
            url: 'https://example.com/webhook',
            events: ['agent.deployed'],
            active: true,
          }),
        },
        tokenRefreshed: false,
      })

      const request = mockJsonRequest({
        name: 'my-webhook',
        url: 'https://example.com/webhook',
        events: ['agent.deployed'],
      })
      const { POST } = await import('../../app/api/webhooks/route')
      const response = await POST(request)

      expect(authenticatedFetch).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/webhooks', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url: 'https://example.com/webhook',
          name: 'my-webhook',
          events: ['agent.deployed'],
        }),
        cache: 'no-store',
      })
      expect(response.status).toBe(201)
      await expect(response.json()).resolves.toEqual({
        id: 'wh_new',
        name: 'my-webhook',
        url: 'https://example.com/webhook',
        events: ['agent.deployed'],
        active: true,
      })
    })

    it('preserves backend conflict responses', async () => {
      hasAuthSession.mockReturnValue(true)
      authenticatedFetch.mockResolvedValue({
        response: {
          ok: false,
          status: 409,
          json: async () => ({ detail: 'Webhook with this name already exists' }),
        },
        tokenRefreshed: false,
      })

      const { POST } = await import('../../app/api/webhooks/route')
      const response = await POST(
        mockJsonRequest({
          name: 'duplicate-webhook',
          url: 'https://example.com/webhook',
          events: ['agent.deployed'],
        })
      )

      expect(response.status).toBe(409)
      await expect(response.json()).resolves.toEqual({ error: 'Webhook with this name already exists' })
    })

    it('applies refreshed auth cookies when webhook creation refreshes the session', async () => {
      hasAuthSession.mockReturnValue(true)
      authenticatedFetch.mockResolvedValue({
        response: {
          ok: true,
          status: 201,
          json: async () => ({
            id: 'wh_refresh',
            name: 'my-webhook',
            url: 'https://example.com/webhook',
            events: ['agent.deployed'],
            active: true,
          }),
        },
        tokenRefreshed: true,
        refreshedTokens: {
          access_token: 'new_access_token',
          refresh_token: 'new_refresh_token',
          expires_in: 1800,
        },
      })

      const request = mockJsonRequest({
        name: 'my-webhook',
        url: 'https://example.com/webhook',
        events: ['agent.deployed'],
      })
      const { POST } = await import('../../app/api/webhooks/route')
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
  })

  describe('PATCH /api/webhooks/:id', () => {
    it('forwards backend-supported name and circuit reset fields', async () => {
      hasAuthSession.mockReturnValue(true)
      authenticatedFetch.mockResolvedValue({
        response: {
          status: 200,
          json: async () => ({
            id: 'wh_123',
            name: 'renamed-webhook',
            circuit_open: false,
          }),
        },
        tokenRefreshed: false,
      })
      const request = mockJsonRequest({
        name: 'renamed-webhook',
        reset_circuit: true,
      })
      const { PATCH } = await import('../../app/api/webhooks/[id]/route')

      const response = await PATCH(request, { params: Promise.resolve({ id: 'wh_123' }) })

      expect(authenticatedFetch).toHaveBeenCalledWith(
        request,
        'http://localhost:8000/v1/webhooks/wh_123',
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: 'renamed-webhook', reset_circuit: true }),
          cache: 'no-store',
        },
      )
      expect(response.status).toBe(200)
    })

    it('rejects unsupported secret rotation before proxying', async () => {
      hasAuthSession.mockReturnValue(true)
      const request = mockJsonRequest({ secret: 'replacement-secret' })
      const { PATCH } = await import('../../app/api/webhooks/[id]/route')

      const response = await PATCH(request, { params: Promise.resolve({ id: 'wh_123' }) })

      expect(response.status).toBe(400)
      expect(authenticatedFetch).not.toHaveBeenCalled()
    })
  })
})
