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

type MockCheckoutRequestOptions = {
  body?: Record<string, unknown>
  jsonError?: Error
}

function createCheckoutRequest(url: string, body: Record<string, unknown>) {
  return new NextRequest(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
}

function createJsonRequest(
  url: string,
  { body = {}, jsonError }: MockCheckoutRequestOptions = {},
) {
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
    nextUrl: new URL(url),
    url,
  } as unknown as NextRequest
}

describe('pico checkout route', () => {
  beforeEach(() => {
    jest.resetModules()
    proxyJson.mockReset()
    hasAuthSession.mockReset()
    hasAuthSession.mockReturnValue(true)
  })

  it('returns 401 for anonymous checkout requests before parsing an invalid body', async () => {
    hasAuthSession.mockReturnValue(false)

    const { POST } = await import('../../app/api/pico/checkout/route')
    const request = createJsonRequest('https://pico.mutx.dev/api/pico/checkout', {
      jsonError: new SyntaxError('Unexpected end of JSON input'),
    })

    const response = await POST(request)

    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
    })
    expect(proxyJson).not.toHaveBeenCalled()
  })

  it('uses stable plan ids and /pico return paths on non-pico hosts', async () => {
    const proxiedResponse = new Response(JSON.stringify({
      checkout_url: 'https://checkout.stripe.com/test',
      session_id: 'cs_test',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    proxyJson.mockResolvedValue(proxiedResponse)

    const { POST } = await import('../../app/api/pico/checkout/route')
    const request = createCheckoutRequest('http://localhost:3000/api/pico/checkout', {
      planId: 'starter',
    })

    const response = await POST(request)

    expect(response).toBe(proxiedResponse)
    expect(proxyJson).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/payments/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plan_id: 'starter',
        success_url: 'http://localhost:3000/pico/pricing?checkout=success&plan=starter&session_id={CHECKOUT_SESSION_ID}',
        cancel_url: 'http://localhost:3000/pico/pricing?checkout=canceled&plan=starter',
      }),
      fallbackMessage: 'Failed to create checkout session',
    })
  })

  it('keeps canonical pico-host return paths without an extra /pico prefix', async () => {
    const proxiedResponse = new Response(JSON.stringify({
      checkout_url: 'https://checkout.stripe.com/test',
      session_id: 'cs_test',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    proxyJson.mockResolvedValue(proxiedResponse)

    const { POST } = await import('../../app/api/pico/checkout/route')
    const request = createCheckoutRequest('https://pico.mutx.dev/api/pico/checkout', {
      planId: 'pro',
    })

    await POST(request)

    expect(proxyJson).toHaveBeenCalledWith(request, 'http://localhost:8000/v1/payments/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plan_id: 'pro',
        success_url: 'https://pico.mutx.dev/pricing?checkout=success&plan=pro&session_id={CHECKOUT_SESSION_ID}',
        cancel_url: 'https://pico.mutx.dev/pricing?checkout=canceled&plan=pro',
      }),
      fallbackMessage: 'Failed to create checkout session',
    })
  })

  it.each([
    [{ planId: 'enterprise' }],
    [{ priceId: 'price_starter' }],
    [{}],
  ])('rejects a malformed or unsupported checkout payload %#', async (body) => {
    const { POST } = await import('../../app/api/pico/checkout/route')
    const request = createCheckoutRequest('http://localhost:3000/api/pico/checkout', body)

    const response = await POST(request)

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'BAD_REQUEST', message: 'A supported planId is required' },
    })
    expect(proxyJson).not.toHaveBeenCalled()
  })

  it('returns 400 for invalid JSON instead of surfacing an internal error', async () => {
    const { POST } = await import('../../app/api/pico/checkout/route')
    const request = createJsonRequest('http://localhost:3000/api/pico/checkout', {
      jsonError: new SyntaxError('Unexpected end of JSON input'),
    })

    const response = await POST(request)

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toEqual({
      status: 'error',
      error: { code: 'BAD_REQUEST', message: 'Invalid JSON in request body' },
    })
    expect(proxyJson).not.toHaveBeenCalled()
  })

  it('preserves an unavailable-price response from the payment service', async () => {
    const proxiedResponse = new Response(JSON.stringify({
      detail: "Stripe price for plan 'starter' is not configured",
    }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    })
    proxyJson.mockResolvedValue(proxiedResponse)

    const { POST } = await import('../../app/api/pico/checkout/route')
    const request = createCheckoutRequest('https://pico.mutx.dev/api/pico/checkout', {
      planId: 'starter',
    })

    const response = await POST(request)

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toEqual({
      detail: "Stripe price for plan 'starter' is not configured",
    })
  })

  it('proxies the authenticated subscription contract for plan refresh', async () => {
    const proxiedResponse = new Response(JSON.stringify({
      plan: 'PRO',
      status: 'active',
      current_period_end: null,
      cancel_at_period_end: false,
      trial_end: null,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    proxyJson.mockResolvedValue(proxiedResponse)

    const { GET } = await import('../../app/api/pico/checkout/route')
    const request = createCheckoutRequest('https://pico.mutx.dev/api/pico/checkout', {})

    const response = await GET(request)

    expect(response).toBe(proxiedResponse)
    expect(proxyJson).toHaveBeenCalledWith(
      request,
      'http://localhost:8000/v1/payments/subscription',
      {
        cache: 'no-store',
        fallbackMessage: 'Failed to refresh subscription status',
      },
    )
  })
})
