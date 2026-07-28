export {}

const originalEnv = process.env

type NewsletterRoute = typeof import('../../app/api/newsletter/route')

function createSqlMock(countResult: unknown) {
  return jest.fn(async (strings: TemplateStringsArray) => {
    const query = strings.join(' ')
    return query.includes('SELECT COUNT(*)') ? countResult : []
  })
}

async function loadNewsletterRoute(sqlMock: jest.Mock | null): Promise<NewsletterRoute> {
  jest.resetModules()
  jest.doMock('../../lib/db', () => ({
    __esModule: true,
    default: sqlMock,
  }))
  jest.doMock('../../i18n/routing', () => ({
    routing: {
      locales: ['en', 'es', 'fr', 'de', 'it', 'pt', 'ja', 'ko', 'zh', 'ar'],
      defaultLocale: 'en',
    },
  }))
  jest.doMock('resend', () => ({
    Resend: jest.fn(),
  }))

  return import('../../app/api/newsletter/route')
}

async function expectUnavailable(response: Response) {
  expect(response.status).toBe(503)
  expect(response.headers.get('Cache-Control')).toBe('no-store')
  expect(await response.json()).toEqual({
    status: 'unavailable',
    error: {
      code: 'COUNT_UNAVAILABLE',
      message: 'Subscriber count is unavailable',
    },
  })
}

describe('newsletter subscriber count route', () => {
  let consoleErrorSpy: jest.SpyInstance

  beforeEach(() => {
    process.env = { ...originalEnv }
    delete process.env.RESEND_API_KEY
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    consoleErrorSpy.mockRestore()
    process.env = originalEnv
    jest.resetModules()
  })

  it('returns only the authoritative configured provider count without seed arithmetic', async () => {
    const sqlMock = createSqlMock([{ count: '7', email: 'private@example.com' }])
    const { GET } = await loadNewsletterRoute(sqlMock)

    const response = await GET()

    expect(response.status).toBe(200)
    expect(response.headers.get('Cache-Control')).toBe('no-store')
    expect(await response.json()).toEqual({ count: 7 })
  })

  it('returns an authoritative zero count', async () => {
    const sqlMock = createSqlMock([{ count: 0 }])
    const { GET } = await loadNewsletterRoute(sqlMock)

    const response = await GET()

    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ count: 0 })
  })

  it('returns a no-store unavailable response when the provider is not configured', async () => {
    const { GET } = await loadNewsletterRoute(null)

    await expectUnavailable(await GET())
  })

  it('returns a generic unavailable response when the provider fails', async () => {
    const sqlMock = jest
      .fn()
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error('provider failure for private@example.com'))
    const { GET } = await loadNewsletterRoute(sqlMock)

    const response = await GET()

    await expectUnavailable(response)
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Newsletter subscriber count provider is unavailable',
    )
  })

  it.each([
    ['missing rows', []],
    ['multiple rows', [{ count: '1' }, { count: '2' }]],
    ['missing count', [{ email: 'private@example.com' }]],
    ['null count', [{ count: null }]],
    ['negative count', [{ count: -1 }]],
    ['fractional count', [{ count: '1.5' }]],
    ['non-numeric count', [{ count: 'many' }]],
    ['unsafe count', [{ count: '9007199254740992' }]],
  ])('fails closed for a malformed provider response: %s', async (_name, result) => {
    const sqlMock = createSqlMock(result)
    const { GET } = await loadNewsletterRoute(sqlMock)

    await expectUnavailable(await GET())
  })

  it('is a public aggregate with identical privacy-safe output regardless of auth headers', async () => {
    const sqlMock = createSqlMock([{ count: '11', accountId: 'account-secret' }])
    const { GET } = await loadNewsletterRoute(sqlMock)
    const callGet = GET as unknown as (request: Request) => Promise<Response>

    const anonymousResponse = await callGet(new Request('http://localhost/api/newsletter'))
    const authenticatedResponse = await callGet(new Request('http://localhost/api/newsletter', {
      headers: { Authorization: 'Bearer private-token' },
    }))

    expect(await anonymousResponse.json()).toEqual({ count: 11 })
    expect(await authenticatedResponse.json()).toEqual({ count: 11 })
    expect(authenticatedResponse.headers.get('Cache-Control')).toBe('no-store')

    const countQueries = sqlMock.mock.calls
      .map(([strings]) => (strings as TemplateStringsArray).join(' '))
      .filter((query) => query.includes('SELECT COUNT(*)'))
    expect(countQueries).toEqual([
      'SELECT COUNT(*) as count FROM waitlist_emails',
      'SELECT COUNT(*) as count FROM waitlist_emails',
    ])
  })
})
