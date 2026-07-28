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

function mockJsonRequest(body: unknown) {
  return {
    json: async () => body,
    headers: {
      get: () => null,
    },
    cookies: {
      get: () => ({ value: 'token' }),
    },
  } as unknown as NextRequest
}

const starterEntitlement = {
  authenticated: true,
  plan: 'starter',
  tutorAccess: true,
  minimumPlan: 'starter',
  byokAccess: false,
  byokMinimumPlan: 'pro',
}

const proEntitlement = {
  ...starterEntitlement,
  plan: 'pro',
  byokAccess: true,
}

const disconnectedStatus = {
  provider: 'openai',
  status: 'disconnected',
  source: 'none',
  connected: false,
  model: 'gpt-5-mini',
  message: 'No platform model provider is available.',
  providerAvailable: false,
  canConnect: false,
  entitlement: starterEntitlement,
}

describe('pico tutor openai route', () => {
  beforeEach(() => {
    jest.resetModules()
    applyAuthCookies.mockReset()
    authenticatedFetch.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it('loads the current connection status', async () => {
    const { GET } = await import('../../app/api/pico/tutor/openai/route')
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        ok: true,
        json: async () => disconnectedStatus,
      },
      tokenRefreshed: false,
    })

    const response = await GET(mockJsonRequest({}) as never)

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      provider: 'openai',
      status: 'disconnected',
      connected: false,
    })
  })

  it('connects an OpenAI key', async () => {
    const { PUT } = await import('../../app/api/pico/tutor/openai/route')
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        ok: true,
        json: async () => ({
          provider: 'openai',
          status: 'connected',
          source: 'user',
          connected: true,
          model: 'gpt-5-mini',
          maskedKey: '••••1234',
          validatedAt: '2026-07-28T12:00:00Z',
          message: 'Your validated OpenAI key is active.',
          providerAvailable: true,
          canConnect: true,
          entitlement: proEntitlement,
          proof: {
            kind: 'validated_user_key',
            checkedAt: '2026-07-28T12:00:01Z',
            validatedAt: '2026-07-28T12:00:00Z',
          },
        }),
      },
      tokenRefreshed: false,
    })

    const response = await PUT(
      mockJsonRequest({ apiKey: 'sk-proj-test-openai-connection-1234' }) as never,
    )

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      status: 'connected',
      maskedKey: '••••1234',
    })
  })

  it('rejects empty connection payloads', async () => {
    const { PUT } = await import('../../app/api/pico/tutor/openai/route')

    const response = await PUT(mockJsonRequest({ apiKey: '   ' }) as never)

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toMatchObject({
      status: 'error',
      error: {
        code: 'BAD_REQUEST',
        message: 'OpenAI API key is required',
      },
    })
  })

  it('disconnects the saved key', async () => {
    const { DELETE } = await import('../../app/api/pico/tutor/openai/route')
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        ok: true,
        json: async () => ({
          ...disconnectedStatus,
          canConnect: true,
          entitlement: proEntitlement,
        }),
      },
      tokenRefreshed: false,
    })

    const response = await DELETE(mockJsonRequest({}) as never)

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      status: 'disconnected',
      connected: false,
    })
  })

  it('returns authenticated BYOK plan denial without claiming provider state', async () => {
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 403,
        ok: false,
        json: async () => ({
          detail: {
            code: 'TUTOR_BYOK_PLAN_REQUIRED',
            message: 'Connecting a personal OpenAI key requires Pro.',
          },
        }),
      },
      tokenRefreshed: false,
    })

    const { PUT } = await import('../../app/api/pico/tutor/openai/route')
    const response = await PUT(mockJsonRequest({ apiKey: 'sk-proj-valid-shape-1234' }) as never)

    expect(response.status).toBe(403)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: 'TUTOR_BYOK_PLAN_REQUIRED' },
    })
  })

  it('returns 502 for a contradictory connected status', async () => {
    authenticatedFetch.mockResolvedValue({
      response: {
        status: 200,
        ok: true,
        json: async () => ({
          ...disconnectedStatus,
          status: 'connected',
          source: 'user',
          connected: true,
        }),
      },
      tokenRefreshed: false,
    })

    const { GET } = await import('../../app/api/pico/tutor/openai/route')
    const response = await GET(mockJsonRequest({}) as never)

    expect(response.status).toBe(502)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: 'TUTOR_MALFORMED_RESPONSE' },
    })
  })

  it('checks authentication before accepting a key body', async () => {
    hasAuthSession.mockReturnValue(false)
    const { PUT } = await import('../../app/api/pico/tutor/openai/route')

    const response = await PUT(mockJsonRequest({ apiKey: 'sk-proj-valid-shape-1234' }) as never)

    expect(response.status).toBe(401)
    expect(authenticatedFetch).not.toHaveBeenCalled()
  })
})
