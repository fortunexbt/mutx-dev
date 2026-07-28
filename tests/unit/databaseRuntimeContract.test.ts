import { resolveDatabaseSsl } from '../../lib/db'

describe('frontend database runtime contract', () => {
  it('requires TLS unless the private bundled database explicitly disables it', () => {
    expect(resolveDatabaseSsl('')).toBe('require')
    expect(resolveDatabaseSsl('require')).toBe('require')
    expect(resolveDatabaseSsl('verify-full')).toBe('require')
    expect(resolveDatabaseSsl('disable')).toBe(false)
    expect(resolveDatabaseSsl(' DISABLE ')).toBe(false)
  })
})
