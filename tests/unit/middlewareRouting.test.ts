import type { NextRequest } from 'next/server'

import { proxy } from '../../proxy'

const authCookies = { access_token: 'token-123' }

function mockRequest(
  url: string,
  headers: Record<string, string> = {},
  method = 'GET',
  cookies: Record<string, string> = {},
) {
  const normalizedHeaders = Object.fromEntries(
    Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]),
  )

  return {
    url,
    method,
    nextUrl: new URL(url),
    headers: {
      get(name: string) {
        return normalizedHeaders[name.toLowerCase()] ?? null
      },
    },
    cookies: {
      get(name: string) {
        const value = cookies[name]
        return value ? { value } : undefined
      },
    },
  } as unknown as NextRequest
}

describe('host-aware UI routing proxy', () => {
  it('redirects marketing-host legacy /app traffic to canonical dashboard paths on app.mutx.dev', () => {
    const response = proxy(
      mockRequest('https://mutx.dev/app/agents?tab=live', { host: 'mutx.dev' }),
    )

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('https://app.mutx.dev/dashboard/agents?tab=live')
    expect(response.headers.get('cache-control')).toBe(
      'private, no-cache, no-store, max-age=0, must-revalidate',
    )
  })

  it.each([
    '/dashboard/documents?job=job_42',
    '/dashboard/agents/agent_42?tab=logs',
    '/dashboard/deployments/deploy_42',
    '/dashboard/control',
  ])('preserves the complete canonical dashboard path during app-host handoff: %s', (path) => {
    const response = proxy(
      mockRequest(`https://mutx.dev${path}`, { host: 'mutx.dev' }),
    )

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe(`https://app.mutx.dev${path}`)
  })

  it('redirects marketing-host auth pages to the app host', () => {
    const response = proxy(
      mockRequest('https://mutx.dev/login?next=%2Fdashboard', { host: 'mutx.dev' }),
    )

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('https://app.mutx.dev/login?next=%2Fdashboard')
  })

  it('rewrites app host root into the canonical dashboard shell without caching the HTML', () => {
    const response = proxy(
      mockRequest('https://app.mutx.dev/', { host: 'app.mutx.dev' }),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-rewrite')).toBe('https://app.mutx.dev/dashboard')
    expect(response.headers.get('cache-control')).toBe(
      'private, no-cache, no-store, max-age=0, must-revalidate',
    )
    expect(response.headers.get('x-frame-options')).toBe('DENY')
    expect(response.headers.get('x-content-type-options')).toBe('nosniff')
  })

  it('keeps /control paths on the app host so the public control demo stays indexable', () => {
    const response = proxy(
      mockRequest('https://app.mutx.dev/control/agents', { host: 'app.mutx.dev' }),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('location')).toBeNull()
    expect(response.headers.get('x-middleware-rewrite')).toBeNull()
  })

  it('redirects app host legacy /app pages to canonical dashboard routes', () => {
    const response = proxy(
      mockRequest('https://app.mutx.dev/app/health', { host: 'app.mutx.dev' }),
    )

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('https://app.mutx.dev/dashboard/monitoring')
  })

  it('maps stale legacy workflow routes onto canonical dashboard destinations', () => {
    const activityResponse = proxy(
      mockRequest('https://app.mutx.dev/app/activity', { host: 'app.mutx.dev' }),
    )

    expect(activityResponse.status).toBe(307)
    expect(activityResponse.headers.get('location')).toBe('https://app.mutx.dev/dashboard/history')

    const apiKeysResponse = proxy(
      mockRequest('https://app.mutx.dev/app/api-keys', { host: 'app.mutx.dev' }),
    )

    expect(apiKeysResponse.status).toBe(307)
    expect(apiKeysResponse.headers.get('location')).toBe('https://app.mutx.dev/dashboard/api-keys')

    const observabilityResponse = proxy(
      mockRequest('https://app.mutx.dev/app/observability', { host: 'app.mutx.dev' }),
    )

    expect(observabilityResponse.status).toBe(307)
    expect(observabilityResponse.headers.get('location')).toBe(
      'https://app.mutx.dev/dashboard/observability',
    )

    const cronResponse = proxy(
      mockRequest('https://app.mutx.dev/app/cron', { host: 'app.mutx.dev' }),
    )

    expect(cronResponse.status).toBe(307)
    expect(cronResponse.headers.get('location')).toBe('https://app.mutx.dev/dashboard/autonomy')

    const settingsResponse = proxy(
      mockRequest('https://app.mutx.dev/app/settings', { host: 'app.mutx.dev' }),
    )

    expect(settingsResponse.status).toBe(307)
    expect(settingsResponse.headers.get('location')).toBe('https://app.mutx.dev/dashboard/control')

    const logsResponse = proxy(
      mockRequest('https://app.mutx.dev/app/logs', { host: 'app.mutx.dev' }),
    )
    const historyResponse = proxy(
      mockRequest('https://app.mutx.dev/app/history', { host: 'app.mutx.dev' }),
    )

    expect(logsResponse.headers.get('location')).toBe('https://app.mutx.dev/dashboard/logs')
    expect(historyResponse.headers.get('location')).toBe('https://app.mutx.dev/dashboard/history')
  })

  it('allows canonical app-host dashboard routes to pass through unchanged', () => {
    const response = proxy(
      mockRequest('https://app.mutx.dev/dashboard/agents', { host: 'app.mutx.dev' }),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-rewrite')).toBeNull()
    expect(response.headers.get('location')).toBeNull()
    expect(response.headers.get('cache-control')).toBe(
      'private, no-cache, no-store, max-age=0, must-revalidate',
    )
  })

  it.each([
    ['/audit', '/dashboard/audit'],
    ['/approvals', '/dashboard/approvals'],
    ['/settings', '/dashboard/control'],
  ])('rewrites clean app route %s to canonical dashboard route %s', (pathname, target) => {
    const response = proxy(
      mockRequest(`https://app.mutx.dev${pathname}`, { host: 'app.mutx.dev' }),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-rewrite')).toBe(`https://app.mutx.dev${target}`)
  })

  it.each([
    [
      'https://app.mutx.dev/pico/onboarding?step=provider',
      'https://pico.mutx.dev/onboarding?step=provider',
    ],
    [
      'https://app.mutx.dev/pico/support?ref=help',
      'https://pico.mutx.dev/support?ref=help',
    ],
    [
      'https://app.mutx.dev/pico/autopilot?view=runs',
      'https://pico.mutx.dev/autopilot?view=runs',
    ],
    [
      'https://app.mutx.dev/pico/academy/install-hermes-locally?lesson=install-hermes-locally',
      'https://pico.mutx.dev/academy/install-hermes-locally?lesson=install-hermes-locally',
    ],
  ])('redirects app-host pico route %s to the canonical pico host', (url, expectedLocation) => {
    const response = proxy(mockRequest(url, { host: 'app.mutx.dev' }))

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe(expectedLocation)
    expect(response.headers.get('cache-control')).toBe(
      'private, no-cache, no-store, max-age=0, must-revalidate',
    )
  })

  it('passes through unrelated marketing routes without injecting auth-form rate-limit headers', () => {
    const response = proxy(
      mockRequest('https://mutx.dev/contact', { host: 'mutx.dev' }),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('X-RateLimit-Limit')).toBeNull()
    expect(response.headers.get('X-RateLimit-Remaining')).toBeNull()
    expect(response.headers.get('cache-control')).toBe(
      'private, no-cache, no-store, max-age=0, must-revalidate',
    )
  })

  it.each([
    [
      'root',
      'https://pico.mutx.dev/',
      'https://pico.mutx.dev/pico',
      'ja',
    ],
    [
      'academy lesson',
      'https://pico.mutx.dev/academy/install-hermes-locally',
      'https://pico.mutx.dev/pico/academy/install-hermes-locally',
      'ja',
    ],
    [
      'tutor',
      'https://pico.mutx.dev/tutor?lesson=install-hermes-locally',
      'https://pico.mutx.dev/pico/tutor?lesson=install-hermes-locally',
      'ja',
    ],
    [
      'support',
      'https://pico.mutx.dev/support?ref=help',
      'https://pico.mutx.dev/pico/support?ref=help',
      'ja',
    ],
    [
      'autopilot',
      'https://pico.mutx.dev/autopilot?view=runs',
      'https://pico.mutx.dev/pico/autopilot?view=runs',
      'ja',
    ],
    [
      'pricing',
      'https://pico.mutx.dev/pricing?locale=fr',
      'https://pico.mutx.dev/pico/pricing?locale=fr',
      'fr',
    ],
    [
      'build ledger',
      'https://pico.mutx.dev/build-ledger',
      'https://pico.mutx.dev/pico/build-ledger',
      'ja',
    ],
  ])('rewrites pico host %s route to the expected internal route', (_label, url, expectedRewrite, expectedLocale) => {
    const response = proxy(mockRequest(url, { host: 'pico.mutx.dev', 'CF-IPCountry': 'JP' }))

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-rewrite')).toBe(expectedRewrite)
    expect(response.headers.get('location')).toBeNull()
    expect(response.headers.get('set-cookie')).toContain(`NEXT_LOCALE=${expectedLocale}`)
  })

  it('redirects the legacy pico start alias into onboarding', () => {
    const response = proxy(
      mockRequest(
        'https://pico.mutx.dev/start?ref=hero',
        { host: 'pico.mutx.dev', 'CF-IPCountry': 'JP' },
        'GET',
        authCookies,
      ),
    )

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe(
      'https://pico.mutx.dev/onboarding?ref=hero',
    )
    expect(response.headers.get('x-middleware-rewrite')).toBeNull()
    expect(response.headers.get('set-cookie')).toContain('NEXT_LOCALE=ja')
  })

  it.each([
    ['login', 'https://pico.mutx.dev/login?next=%2Fonboarding'],
    ['register', 'https://pico.mutx.dev/register?next=%2Facademy'],
    ['verify email', 'https://pico.mutx.dev/verify-email?token=test-token'],
    ['forgot password', 'https://pico.mutx.dev/forgot-password'],
    ['reset password', 'https://pico.mutx.dev/reset-password?token=reset-token'],
  ])('serves the pico-hosted %s account flow', (_label, url) => {
    const response = proxy(mockRequest(url, { host: 'pico.mutx.dev', 'CF-IPCountry': 'JP' }))

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-rewrite')).toBeNull()
    expect(response.headers.get('location')).toBeNull()
    expect(response.headers.get('set-cookie')).toContain('NEXT_LOCALE=ja')
  })

  it('maps pico geolocation headers to supported locales on first pico visit', () => {
    const jpResponse = proxy(
      mockRequest(
        'https://pico.mutx.dev/',
        { host: 'pico.mutx.dev', 'CF-IPCountry': 'JP' },
        'GET',
        authCookies,
      ),
    )
    const krResponse = proxy(
      mockRequest(
        'https://pico.mutx.dev/',
        { host: 'pico.mutx.dev', 'CF-IPCountry': 'KR' },
        'GET',
        authCookies,
      ),
    )
    const cnResponse = proxy(
      mockRequest(
        'https://pico.mutx.dev/',
        { host: 'pico.mutx.dev', 'CF-IPCountry': 'CN' },
        'GET',
        authCookies,
      ),
    )

    expect(jpResponse.headers.get('set-cookie')).toContain('NEXT_LOCALE=ja')
    expect(jpResponse.headers.get('x-middleware-rewrite')).toBe('https://pico.mutx.dev/pico')
    expect(krResponse.headers.get('set-cookie')).toContain('NEXT_LOCALE=ko')
    expect(krResponse.headers.get('x-middleware-rewrite')).toBe('https://pico.mutx.dev/pico')
    expect(cnResponse.headers.get('set-cookie')).toContain('NEXT_LOCALE=zh')
    expect(cnResponse.headers.get('x-middleware-rewrite')).toBe('https://pico.mutx.dev/pico')
  })

  it('keeps cookie precedence over pico geolocation', () => {
    const response = proxy(
      mockRequest(
        'https://pico.mutx.dev/',
        { host: 'pico.mutx.dev', 'CF-IPCountry': 'JP' },
        'GET',
        { ...authCookies, NEXT_LOCALE: 'es' },
      ),
    )

    expect(response.headers.get('set-cookie')).toContain('NEXT_LOCALE=es')
  })

  it('prefers an explicit locale query over saved cookies on pico pricing', () => {
    const response = proxy(
      mockRequest(
        'https://pico.mutx.dev/pricing?locale=fr',
        { host: 'pico.mutx.dev', 'CF-IPCountry': 'JP' },
        'GET',
        { ...authCookies, NEXT_LOCALE: 'es', mutx_user_locale: 'de' },
      ),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-rewrite')).toBe(
      'https://pico.mutx.dev/pico/pricing?locale=fr',
    )
    expect(response.headers.get('set-cookie')).toContain('NEXT_LOCALE=fr')
  })

  it('prefers the saved authenticated locale over the guest locale cookie', () => {
    const response = proxy(
      mockRequest(
        'https://pico.mutx.dev/',
        { host: 'pico.mutx.dev' },
        'GET',
        { ...authCookies, NEXT_LOCALE: 'es', mutx_user_locale: 'de' },
      ),
    )

    expect(response.headers.get('set-cookie')).toContain('NEXT_LOCALE=de')
  })

  it('falls back to accept-language for pico when geo headers are missing', () => {
    const response = proxy(
      mockRequest(
        'https://pico.mutx.dev/',
        { host: 'pico.mutx.dev', 'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8' },
        'GET',
        authCookies,
      ),
    )

    expect(response.headers.get('set-cookie')).toContain('NEXT_LOCALE=es')
  })

  it('lets pico API routes hit real handlers instead of rewriting them behind a product page', () => {
    const response = proxy(
      mockRequest('https://pico.mutx.dev/api/pico/session', { host: 'pico.mutx.dev' }),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-rewrite')).toBeNull()
  })

  it('keeps the pico waitlist contact endpoint available on the pico host', () => {
    const response = proxy(
      mockRequest('https://pico.mutx.dev/api/contact', { host: 'pico.mutx.dev' }, 'POST'),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-rewrite')).toBeNull()
  })

  it.each(['google', 'github', 'discord', 'apple'])(
    'lets pico-hosted %s OAuth starts reach the auth handler',
    (provider) => {
      const response = proxy(
        mockRequest(
          `https://pico.mutx.dev/api/auth/oauth/${provider}/start?intent=login&next=%2Fonboarding`,
          { host: 'pico.mutx.dev' },
        ),
      )

      expect(response.status).toBe(200)
      expect(response.headers.get('location')).toBeNull()
      expect(response.headers.get('x-middleware-rewrite')).toBeNull()
      expect(response.headers.get('cache-control')).toBe('no-store')
    },
  )

  it('lets pico-hosted direct auth API calls reach the rate-limited handler', () => {
    const response = proxy(
      mockRequest(
        'https://pico.mutx.dev/api/auth/register',
        { host: 'pico.mutx.dev' },
        'POST',
      ),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('location')).toBeNull()
    expect(response.headers.get('x-middleware-rewrite')).toBeNull()
    expect(response.headers.get('X-RateLimit-Limit')).toBe('8')
    expect(response.headers.get('cache-control')).toBe('no-store')
  })

  it('still applies rate-limit headers on protected auth endpoints', () => {
    const response = proxy(
      mockRequest('https://app.mutx.dev/api/auth/login', { host: 'app.mutx.dev' }),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('X-RateLimit-Limit')).toBe('8')
    expect(response.headers.get('X-RateLimit-Remaining')).toBe('7')
    expect(response.headers.get('X-RateLimit-Reset')).not.toBeNull()
    expect(response.headers.get('cache-control')).toBe('no-store')
    expect(response.headers.get('referrer-policy')).toBe('strict-origin-when-cross-origin')
  })

  it('rejects cross-origin browser writes to api routes', async () => {
    const response = proxy(
      mockRequest(
        'https://app.mutx.dev/api/auth/logout',
        {
          host: 'app.mutx.dev',
          origin: 'https://evil.example',
        },
        'POST',
      ),
    )

    expect(response.status).toBe(403)
    expect(await response.json()).toEqual({
      detail: 'CSRF validation failed: origin is not allowed',
    })
    expect(response.headers.get('cache-control')).toBe('no-store')
  })

  it('lets Apple OAuth form_post callbacks reach the pico auth handler', () => {
    const response = proxy(
      mockRequest(
        'https://pico.mutx.dev/api/auth/oauth/apple/callback',
        {
          host: 'pico.mutx.dev',
          origin: 'https://appleid.apple.com',
        },
        'POST',
      ),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-rewrite')).toBeNull()
    expect(response.headers.get('location')).toBeNull()
    expect(response.headers.get('cache-control')).toBe('no-store')
  })

  it('allows same-origin browser writes to api routes when x-forwarded-proto indicates https', () => {
    const response = proxy(
      mockRequest(
        'http://app.mutx.dev/api/auth/logout',
        {
          host: 'app.mutx.dev',
          origin: 'https://app.mutx.dev',
          'x-forwarded-proto': 'https',
        },
        'POST',
      ),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('cache-control')).toBe('no-store')
  })

  describe('pico product route activation', () => {
    it.each([
      '/onboarding',
      '/academy',
      '/academy/install-hermes-locally',
      '/tutor',
      '/support',
      '/autopilot',
      '/pricing',
    ])('serves anonymous %s from its implemented pico route', (path) => {
      const response = proxy(
        mockRequest(`https://pico.mutx.dev${path}`, { host: 'pico.mutx.dev' }),
      )

      expect(response.status).toBe(200)
      expect(response.headers.get('x-middleware-rewrite')).toBe(
        `https://pico.mutx.dev/pico${path}`,
      )
      expect(response.headers.get('location')).toBeNull()
      expect(response.headers.get('cache-control')).toMatch(/no-cache|no-store/)
    })

    it.each(['/onboarding', '/academy'])('serves authenticated %s from the same product route', (path) => {
      const response = proxy(
        mockRequest(`https://pico.mutx.dev${path}`, { host: 'pico.mutx.dev' }, 'GET', authCookies),
      )

      expect(response.status).toBe(200)
      expect(response.headers.get('x-middleware-rewrite')).toBe(
        `https://pico.mutx.dev/pico${path}`,
      )
      expect(response.headers.get('location')).toBeNull()
    })

    it('canonicalizes accidental internal pico URLs on the pico host', () => {
      const response = proxy(
        mockRequest('https://pico.mutx.dev/pico/pricing?locale=fr', { host: 'pico.mutx.dev' }),
      )

      expect(response.status).toBe(307)
      expect(response.headers.get('location')).toBe('https://pico.mutx.dev/pricing?locale=fr')
      expect(response.headers.get('x-middleware-rewrite')).toBeNull()
    })

    it.each(['/not-a-product-route', '/download', '/control', '/dashboard'])(
      'rewrites pico-host collision %s into the scoped Pico not-found boundary',
      (path) => {
        const response = proxy(
          mockRequest(`https://pico.mutx.dev${path}`, { host: 'pico.mutx.dev' }),
        )

        expect(response.status).toBe(200)
        expect(response.headers.get('location')).toBeNull()
        expect(response.headers.get('x-middleware-rewrite')).toBe(
          'https://pico.mutx.dev/pico/__not-found',
        )
        expect(response.headers.get('set-cookie')).toContain('NEXT_LOCALE=')
      },
    )
  })

  describe('app-host pico route boundary enforcement', () => {
    it('blocks app-host access to /pico/onboarding by redirecting to canonical pico host', () => {
      const response = proxy(
        mockRequest('https://app.mutx.dev/pico/onboarding', { host: 'app.mutx.dev' }),
      )

      expect(response.status).toBe(307)
      expect(response.headers.get('location')).toBe('https://pico.mutx.dev/onboarding')
    })

    it('blocks app-host access to /pico/academy by redirecting to canonical pico host', () => {
      const response = proxy(
        mockRequest('https://app.mutx.dev/pico/academy', { host: 'app.mutx.dev' }),
      )

      expect(response.status).toBe(307)
      expect(response.headers.get('location')).toBe('https://pico.mutx.dev/academy')
    })

    it('blocks app-host access to /pico/tutor by redirecting to canonical pico host', () => {
      const response = proxy(
        mockRequest('https://app.mutx.dev/pico/tutor', { host: 'app.mutx.dev' }),
      )

      expect(response.status).toBe(307)
      expect(response.headers.get('location')).toBe('https://pico.mutx.dev/tutor')
    })

    it('blocks app-host access to /pico/support by redirecting to canonical pico host', () => {
      const response = proxy(
        mockRequest('https://app.mutx.dev/pico/support', { host: 'app.mutx.dev' }),
      )

      expect(response.status).toBe(307)
      expect(response.headers.get('location')).toBe('https://pico.mutx.dev/support')
    })

    it('blocks app-host access to /pico/autopilot by redirecting to canonical pico host', () => {
      const response = proxy(
        mockRequest('https://app.mutx.dev/pico/autopilot', { host: 'app.mutx.dev' }),
      )

      expect(response.status).toBe(307)
      expect(response.headers.get('location')).toBe('https://pico.mutx.dev/autopilot')
    })

    it('preserves query parameters when redirecting app-host pico routes', () => {
      const response = proxy(
        mockRequest('https://app.mutx.dev/pico/academy/install-hermes-locally?lesson=true', { host: 'app.mutx.dev' }),
      )

      expect(response.status).toBe(307)
      expect(response.headers.get('location')).toBe('https://pico.mutx.dev/academy/install-hermes-locally?lesson=true')
    })
  })
})
