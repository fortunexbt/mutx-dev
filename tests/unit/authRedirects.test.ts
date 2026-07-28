import {
  getDefaultRedirectPathForHost,
  isPicoHost,
  mergeRedirectPathWithSearch,
  resolveRedirectPath,
} from '../../lib/auth/redirects'

describe('auth redirect helpers', () => {
  it('detects pico hosts correctly', () => {
    expect(isPicoHost('pico.mutx.dev')).toBe(true)
    expect(isPicoHost('pico.localhost')).toBe(true)
    expect(isPicoHost('app.mutx.dev')).toBe(false)
  })

  it('defaults pico hosts to the pico root', () => {
    expect(getDefaultRedirectPathForHost('pico.mutx.dev')).toBe('/')
    expect(getDefaultRedirectPathForHost('pico.localhost')).toBe('/')
  })

  it('keeps non-pico hosts on the dashboard fallback', () => {
    expect(getDefaultRedirectPathForHost('app.mutx.dev')).toBe('/dashboard')
    expect(getDefaultRedirectPathForHost(undefined)).toBe('/dashboard')
  })

  it('resolves explicit next paths over the host fallback', () => {
    expect(resolveRedirectPath('/onboarding', getDefaultRedirectPathForHost('pico.mutx.dev'))).toBe('/onboarding')
  })

  it('falls back to the host-specific default when next is missing', () => {
    expect(resolveRedirectPath(undefined, getDefaultRedirectPathForHost('pico.mutx.dev'))).toBe('/')
  })

  it('preserves tutor lesson query when the banner only knows the pathname', () => {
    expect(mergeRedirectPathWithSearch('/tutor', 'lesson=install-hermes-locally')).toBe(
      '/tutor?lesson=install-hermes-locally',
    )
    expect(
      resolveRedirectPath(
        mergeRedirectPathWithSearch('/tutor', 'lesson=install-hermes-locally'),
        getDefaultRedirectPathForHost('pico.mutx.dev'),
      ),
    ).toBe('/tutor?lesson=install-hermes-locally')
  })

  it('does not duplicate a query that is already present on the redirect path', () => {
    expect(
      mergeRedirectPathWithSearch('/tutor?lesson=install-hermes-locally', 'lesson=other-lesson'),
    ).toBe('/tutor?lesson=install-hermes-locally')
  })

  it.each([
    'https://evil.example/steal',
    '//evil.example/steal',
    '/\\evil.example/steal',
    '/%5cevil.example/steal',
    '/%2f%2fevil.example/steal',
    '/%255cevil.example/steal',
    '/dashboard\u0000?next=/safe',
    '/l%6fgin?next=/dashboard',
    '/api/auth/%6fauth/github',
    '/dashboard?filter=100%',
  ])('rejects hostile or malformed redirect path %s', (nextPath) => {
    expect(resolveRedirectPath(nextPath, '/safe')).toBe('/safe')
  })
})
