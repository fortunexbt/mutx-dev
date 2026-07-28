import { buildPicoContactPayload } from '../../components/pico/picoContactPayload'

describe('pico contact payload', () => {
  it('maps the selected interest into the backend tier field', () => {
    const payload = buildPicoContactPayload({
      email: 'operator@mutx.dev',
      name: 'Operator',
      company: 'MUTX',
      message: 'Need the build lane.',
      interest: 'build',
      locale: 'en',
      source: 'pico-landing',
      honeypot: '',
      productUpdatesConsent: false,
    })

    expect(payload).toEqual({
      email: 'operator@mutx.dev',
      name: 'Operator',
      company: 'MUTX',
      message: 'Need the build lane.',
      tier: 'build',
      interest: 'build',
      locale: 'en',
      source: 'pico-landing',
      honeypot: '',
      productUpdatesConsent: false,
    })
  })

  it('carries explicit product-update consent without inferring it from the request', () => {
    const payload = buildPicoContactPayload({
      email: 'operator@mutx.dev',
      name: '',
      company: '',
      message: 'Please help with setup.',
      interest: 'fix',
      locale: 'en',
      source: 'pico-support',
      honeypot: '',
      productUpdatesConsent: true,
    })

    expect(payload.productUpdatesConsent).toBe(true)
    expect(payload.source).toBe('pico-support')
  })
})
