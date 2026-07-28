export {}

const mockSql = jest.fn()

function makeContactRequest(overrides: Record<string, unknown> = {}) {
  const body: Record<string, unknown> = {
    email: 'operator@example.com',
    name: 'Pico Operator',
    company: 'MUTX Lab',
    message: 'Help us deploy PicoMUTX.',
    tier: 'build',
    interest: 'build',
    locale: 'en',
    source: 'pico-landing',
    productUpdatesConsent: false,
    ...overrides,
  }
  if ('productUpdatesConsent' in overrides && overrides.productUpdatesConsent === undefined) {
    delete body.productUpdatesConsent
  }
  return new Request('http://localhost/api/contact', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': 'contact-12345678-1234-4123-8123-123456789abc',
    },
    body: JSON.stringify(body),
  })
}

async function loadContactRoute() {
  jest.doMock('../../app/api/_lib/controlPlane', () => ({
    getApiBaseUrl: () => 'http://localhost:8000',
  }))
  jest.doMock('../../lib/db', () => ({ __esModule: true, default: mockSql }))
  return import('../../app/api/contact/route')
}

describe('durable contact route', () => {
  let fetchSpy: jest.SpyInstance

  beforeEach(() => {
    jest.resetModules()
    mockSql.mockReset()
    fetchSpy = jest.spyOn(global as typeof globalThis, 'fetch').mockImplementation(jest.fn())
  })

  afterEach(() => {
    fetchSpy.mockRestore()
  })

  it('accepts durable capture even when no notification channel was scheduled', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          status: 'accepted',
          persisted: true,
          notification_scheduled: false,
          follow_up: 'unavailable',
        }),
        { status: 201 },
      ),
    )
    const { POST } = await loadContactRoute()
    const response = await POST(makeContactRequest())

    expect(response.status).toBe(201)
    await expect(response.json()).resolves.toMatchObject({
      persisted: true,
      notification_scheduled: false,
    })
    expect(mockSql).not.toHaveBeenCalled()
  })

  it.each([
    ['omitted', undefined],
    ['false', false],
    ['true', true],
  ])('forwards explicit product-update consent when %s', async (_label, consent) => {
    ;(global.fetch as jest.Mock).mockResolvedValue(
      new Response(JSON.stringify({ success: true, status: 'accepted', persisted: true }), {
        status: 201,
      }),
    )
    const body = consent === undefined ? {} : { productUpdatesConsent: consent }
    const { POST } = await loadContactRoute()
    await POST(makeContactRequest(body))

    const forwarded = JSON.parse((global.fetch as jest.Mock).mock.calls[0][1].body)
    expect(forwarded.product_updates_consent).toBe(consent === true)
  })

  it('preserves tier, interest, locale, and source in the canonical capture payload', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue(
      new Response(JSON.stringify({ success: true, status: 'accepted', persisted: true }), {
        status: 201,
      }),
    )
    const { POST } = await loadContactRoute()
    await POST(makeContactRequest({ locale: 'ES-es', source: ' pico-support ' }))

    const forwarded = JSON.parse((global.fetch as jest.Mock).mock.calls[0][1].body)
    expect(forwarded).toMatchObject({
      tier: 'build',
      interest: 'build',
      locale: 'es-es',
      source: 'pico-support',
    })
  })

  it('rejects malformed consent and honeypot submissions before persistence', async () => {
    const { POST } = await loadContactRoute()
    const malformed = await POST(makeContactRequest({ productUpdatesConsent: 'yes' }))
    const honeypot = await POST(makeContactRequest({ honeypot: 'https://spam.example' }))

    expect(malformed.status).toBe(400)
    expect(honeypot.status).toBe(400)
    expect(global.fetch).not.toHaveBeenCalled()
    expect(mockSql).not.toHaveBeenCalled()
  })
})
