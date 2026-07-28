import { createHash } from 'node:crypto'

const mockSql = jest.fn()

const submissionKey = '12345678-1234-4123-8123-123456789abc'

function makeRequest(body: unknown, key: string | undefined = submissionKey) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (key) headers['Idempotency-Key'] = key
  return new Request('http://localhost/api/leads', {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
}

function canonicalHash(overrides: Record<string, unknown> = {}) {
  const content = {
    company: null,
    email: 'lead@example.com',
    interest: null,
    locale: null,
    message: 'Need help shipping agents',
    name: null,
    product_updates_consent: false,
    source: 'contact-page',
    tier: null,
    ...overrides,
  }
  return createHash('sha256').update(JSON.stringify(content), 'utf8').digest('hex')
}

async function loadRoute(sqlValue: unknown = mockSql) {
  jest.doMock('../../app/api/_lib/controlPlane', () => ({
    getApiBaseUrl: () => 'http://localhost:8000',
  }))
  jest.doMock('../../lib/db', () => ({
    __esModule: true,
    default: sqlValue,
  }))
  return import('../../app/api/leads/route')
}

describe('durable lead browser routes', () => {
  let fetchSpy: jest.SpyInstance
  let consoleWarnSpy: jest.SpyInstance
  let consoleErrorSpy: jest.SpyInstance

  beforeEach(() => {
    jest.resetModules()
    mockSql.mockReset()
    fetchSpy = jest.spyOn(global as typeof globalThis, 'fetch').mockImplementation(jest.fn())
    consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    fetchSpy.mockRestore()
    consoleWarnSpy.mockRestore()
    consoleErrorSpy.mockRestore()
    jest.restoreAllMocks()
  })

  it('returns success only for an explicit durable persistence acknowledgement', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'lead_123',
          success: true,
          status: 'accepted',
          persisted: true,
          notification_scheduled: false,
        }),
        { status: 201 },
      ),
    )

    const { POST } = await loadRoute()
    const response = await POST(
      makeRequest({
        email: ' LEAD@example.com ',
        message: ' Need help shipping agents ',
        source: ' contact-page ',
      }),
    )

    expect(response.status).toBe(201)
    await expect(response.json()).resolves.toMatchObject({ persisted: true })
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/v1/leads',
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': submissionKey,
        },
        body: JSON.stringify({
          email: 'lead@example.com',
          name: undefined,
          company: undefined,
          message: 'Need help shipping agents',
          source: 'contact-page',
          tier: undefined,
          interest: undefined,
          locale: undefined,
          product_updates_consent: false,
        }),
        cache: 'no-store',
        signal: expect.any(AbortSignal),
      }),
    )
    expect(mockSql).not.toHaveBeenCalled()
  })

  it('rejects a success-shaped upstream response without persisted truth', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue(
      new Response(JSON.stringify({ success: true, notified: true }), { status: 200 }),
    )
    const { POST } = await loadRoute()
    const response = await POST(
      makeRequest({ email: 'lead@example.com', message: 'Need help shipping agents' }),
    )

    expect(response.status).toBe(502)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: 'INVALID_PERSISTENCE_ACKNOWLEDGEMENT' },
    })
    expect(mockSql).not.toHaveBeenCalled()
  })

  it('falls back to one migrated-schema insert on upstream 5xx without runtime DDL', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'backend unavailable' }), { status: 503 }),
    )
    mockSql.mockResolvedValueOnce([
      {
        id: '11111111-1111-1111-1111-111111111111',
        email: 'lead@example.com',
        name: null,
        company: null,
        message: 'Need help shipping agents',
        source: 'contact-page',
        tier: null,
        interest: null,
        locale: null,
        product_updates_consent: false,
        content_hash: canonicalHash(),
        notification_scheduled_at: null,
        created_at: '2026-07-28T10:00:00.000Z',
      },
    ])

    const { POST } = await loadRoute()
    const response = await POST(
      makeRequest({
        email: 'lead@example.com',
        message: 'Need help shipping agents',
        source: 'contact-page',
      }),
    )

    expect(response.status).toBe(201)
    await expect(response.json()).resolves.toMatchObject({
      persisted: true,
      replayed: false,
      notification_scheduled: false,
      follow_up: 'unavailable',
      fallback: 'local-db',
    })
    expect(mockSql).toHaveBeenCalledTimes(1)
    const query = mockSql.mock.calls[0][0].join(' ')
    expect(query).toContain('INSERT INTO leads')
    expect(query).not.toMatch(/CREATE\s+(TABLE|INDEX)/i)
  })

  it('returns the existing local row for a lost-response replay', async () => {
    ;(global.fetch as jest.Mock).mockRejectedValue(new TypeError('network failed'))
    mockSql.mockResolvedValueOnce([]).mockResolvedValueOnce([
      {
        id: '11111111-1111-1111-1111-111111111111',
        email: 'lead@example.com',
        name: null,
        company: null,
        message: 'Need help shipping agents',
        source: 'contact-page',
        tier: null,
        interest: null,
        locale: null,
        product_updates_consent: false,
        content_hash: canonicalHash(),
        notification_scheduled_at: null,
        created_at: '2026-07-28T10:00:00.000Z',
      },
    ])

    const { POST } = await loadRoute()
    const response = await POST(
      makeRequest({
        email: 'lead@example.com',
        message: 'Need help shipping agents',
        source: 'contact-page',
      }),
    )

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      id: '11111111-1111-1111-1111-111111111111',
      persisted: true,
      replayed: true,
    })
    expect(mockSql).toHaveBeenCalledTimes(2)
  })

  it('returns 409 when a local key is reused with different canonical content', async () => {
    ;(global.fetch as jest.Mock).mockRejectedValue(new TypeError('network failed'))
    mockSql.mockResolvedValueOnce([]).mockResolvedValueOnce([
      {
        id: '11111111-1111-1111-1111-111111111111',
        content_hash: 'different-content-hash',
      },
    ])

    const { POST } = await loadRoute()
    const response = await POST(
      makeRequest({ email: 'lead@example.com', message: 'Need help shipping agents' }),
    )

    expect(response.status).toBe(409)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: 'IDEMPOTENCY_CONFLICT' },
    })
  })

  it('preserves upstream 4xx responses without local fallback', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Message is too long' }), { status: 422 }),
    )
    const { POST } = await loadRoute()
    const response = await POST(
      makeRequest({ email: 'lead@example.com', message: 'Need help shipping agents' }),
    )

    expect(response.status).toBe(422)
    await expect(response.json()).resolves.toEqual({ detail: 'Message is too long' })
    expect(mockSql).not.toHaveBeenCalled()
  })

  it('uses the deterministic control-plane timeout and treats timeout as a network fallback', async () => {
    const timeoutSignal = new AbortController().signal
    const timeoutSpy = jest.spyOn(AbortSignal, 'timeout').mockReturnValue(timeoutSignal)
    ;(global.fetch as jest.Mock).mockRejectedValue(new DOMException('timed out', 'TimeoutError'))

    const { POST } = await loadRoute(null)
    const response = await POST(
      makeRequest({ email: 'lead@example.com', message: 'Need help shipping agents' }),
    )

    expect(timeoutSpy).toHaveBeenCalledWith(5_000)
    expect(response.status).toBe(503)
  })

  it('keeps the /api/v1/leads alias on the same persisted contract', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue(
      new Response(JSON.stringify({ success: true, status: 'accepted', persisted: true }), {
        status: 201,
      }),
    )
    await loadRoute()
    const { POST } = await import('../../app/api/v1/leads/route')
    const response = await POST(makeRequest({ email: 'lead@example.com' }, undefined))

    expect(response.status).toBe(201)
    await expect(response.json()).resolves.toMatchObject({ persisted: true })
  })

  it('rejects malformed idempotency keys before any capture attempt', async () => {
    const { POST } = await loadRoute()
    const response = await POST(makeRequest({ email: 'lead@example.com' }, 'short'))

    expect(response.status).toBe(400)
    expect(global.fetch).not.toHaveBeenCalled()
    expect(mockSql).not.toHaveBeenCalled()
  })
})
