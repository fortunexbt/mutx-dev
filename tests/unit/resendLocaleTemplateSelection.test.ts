export {}

const sendMock = jest.fn()

const envKeys = [
  'RESEND_API_KEY',
  'RESEND_WAITLIST_TEMPLATE_ID_EN',
  'RESEND_WAITLIST_TEMPLATE_ID_ES',
  'RESEND_WAITLIST_TEMPLATE_ID_JA',
  'RESEND_WAITLIST_TEMPLATE_ID',
  'RESEND_CONTACT_TEMPLATE_ID_EN',
  'RESEND_CONTACT_TEMPLATE_ID_ES',
  'RESEND_CONTACT_TEMPLATE_ID_JA',
  'RESEND_CONTACT_TEMPLATE_ID',
  'LEAD_DISCORD_WEBHOOK_URL',
  'DISCORD_LEAD_WEBHOOK_URL',
  'TURNSTILE_SECRET_KEY',
] as const

function makeNewsletterRequest(locale?: string) {
  return new Request('http://localhost/api/newsletter', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: 'person@example.com',
      source: 'coming-soon',
      locale,
      captchaToken: 'token',
    }),
  })
}

function makeContactRequest(locale?: string) {
  return new Request('http://localhost/api/contact', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: 'person@example.com',
      name: 'Pat Example',
      message: 'Need help shipping agents',
      source: 'contact-page',
      locale,
    }),
  })
}

async function loadNewsletterRoute() {
  const sqlMock = jest
    .fn()
    .mockResolvedValueOnce([])
    .mockResolvedValueOnce([{ email: 'person@example.com' }])

  jest.doMock('../../lib/db', () => ({
    __esModule: true,
    default: sqlMock,
  }))

  return import('../../app/api/newsletter/route')
}

async function loadContactRoute() {
  jest.doMock('../../app/api/_lib/controlPlane', () => ({
    getApiBaseUrl: () => 'http://localhost:8000',
  }))
  jest.doMock('../../lib/db', () => ({ __esModule: true, default: null }))
  return import('../../app/api/contact/route')
}

describe('locale-aware Resend template selection', () => {
  const originalEnv = process.env
  let fetchSpy: jest.SpyInstance

  beforeEach(() => {
    jest.resetModules()
    sendMock.mockReset().mockResolvedValue({
      data: { id: 'email_123' },
      error: null,
      headers: null,
    })
    process.env = { ...originalEnv }
    for (const key of envKeys) {
      delete process.env[key]
    }
    process.env.RESEND_API_KEY = 'test-api-key'
    process.env.RESEND_WAITLIST_TEMPLATE_ID_EN = 'waitlist-en'
    process.env.RESEND_WAITLIST_TEMPLATE_ID_ES = 'waitlist-es'
    process.env.RESEND_CONTACT_TEMPLATE_ID_EN = 'contact-en'
    process.env.RESEND_CONTACT_TEMPLATE_ID_ES = 'contact-es'
    process.env.TURNSTILE_SECRET_KEY = 'turnstile-secret'

    fetchSpy = jest.spyOn(global as typeof globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true, action: 'waitlist' }),
    } as Response)

    jest.doMock('../../i18n/routing', () => ({
      routing: {
        locales: ['en', 'es', 'fr', 'de', 'it', 'pt', 'ja', 'ko', 'zh', 'ar'],
        defaultLocale: 'en',
      },
    }))

    jest.doMock('resend', () => ({
      Resend: jest.fn().mockImplementation(() => ({
        emails: { send: sendMock },
        contacts: { create: jest.fn() },
      })),
    }))
  })

  afterEach(() => {
    fetchSpy.mockRestore()
    process.env = originalEnv
  })

  it.each([
    ['newsletter route uses Spanish template for regional locale variants', 'es-MX', 'waitlist-es'],
    ['newsletter route falls back to English template for unsupported locales', 'pt-BR', 'waitlist-en'],
    ['newsletter route trims and normalizes mixed-case locales', 'ES', 'waitlist-es'],
  ])('%s', async (_caseName, locale, expectedTemplateId) => {
    const { POST } = await loadNewsletterRoute()

    const response = await POST(makeNewsletterRequest(locale))

    expect(response.status).toBe(200)
    expect(sendMock).toHaveBeenCalledWith(
      expect.objectContaining({
        template: expect.objectContaining({ id: expectedTemplateId }),
      }),
    )
  })

  it.each([
    ['contact route preserves a Spanish regional locale', 'es-mx', 'es-mx'],
    ['contact route preserves another valid regional locale', 'nl-be', 'nl-be'],
    ['contact route normalizes mixed-case locales', 'ES', 'es'],
  ])('%s', async (_caseName, locale, expectedLocale) => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, status: 'accepted', persisted: true }), {
        status: 201,
      }),
    )
    const { POST } = await loadContactRoute()

    const response = await POST(makeContactRequest(locale))

    expect(response.status).toBe(201)
    const forwarded = JSON.parse((fetchSpy.mock.calls.at(-1)?.[1] as RequestInit).body as string)
    expect(forwarded.locale).toBe(expectedLocale)
    expect(sendMock).not.toHaveBeenCalled()
  })
})
