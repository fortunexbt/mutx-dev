import {
  picoApiErrorMessage,
  picoPackageFilename,
  resolvePicoCoachRetryRequest,
} from '../../components/pico/usePicoSetupState'
import { hasPicoPackagePlan } from '../../components/pico/usePicoSession'

describe('Pico onboarding continuity helpers', () => {
  it.each(['starter', 'PRO', 'Enterprise'])('allows package generation for %s', (plan) => {
    expect(hasPicoPackagePlan(plan)).toBe(true)
  })

  it.each([null, undefined, '', 'free', 'unknown'])('blocks package generation for %p', (plan) => {
    expect(hasPicoPackagePlan(plan)).toBe(false)
  })

  it('uses structured proxy and backend errors', () => {
    expect(picoApiErrorMessage({ detail: 'Session expired' }, 'fallback')).toBe('Session expired')
    expect(
      picoApiErrorMessage({ error: { message: 'Sign in again' } }, 'fallback'),
    ).toBe('Sign in again')
    expect(picoApiErrorMessage(null, 'fallback')).toBe('fallback')
  })

  it('prevents path traversal and unsafe characters in downloaded filenames', () => {
    expect(picoPackageFilename('attachment; filename="../../Hermes setup.zip"')).toBe(
      'Hermes-setup.zip',
    )
    expect(picoPackageFilename("attachment; filename*=UTF-8''..%2F..%2Fpico%20agent.zip")).toBe(
      'pico-agent.zip',
    )
    expect(picoPackageFilename(null)).toBe('pico-agent-package.zip')
  })

  it('reuses the original request and session identity for an exact retry', () => {
    const pending = {
      message: 'Install Hermes',
      requestId: 'request-original',
      sessionId: '11111111-1111-4111-a111-111111111111',
    }
    const createRequestId = jest.fn(() => 'request-new')

    expect(
      resolvePicoCoachRetryRequest(
        pending,
        'Install Hermes',
        '22222222-2222-4222-a222-222222222222',
        createRequestId,
      ),
    ).toEqual(pending)
    expect(createRequestId).not.toHaveBeenCalled()
  })

  it('rotates retry identity when the user changes the message', () => {
    const createRequestId = jest.fn(() => 'request-new')

    expect(
      resolvePicoCoachRetryRequest(
        {
          message: 'Install Hermes',
          requestId: 'request-original',
          sessionId: null,
        },
        'Install OpenClaw',
        '22222222-2222-4222-a222-222222222222',
        createRequestId,
      ),
    ).toEqual({
      message: 'Install OpenClaw',
      requestId: 'request-new',
      sessionId: '22222222-2222-4222-a222-222222222222',
    })
    expect(createRequestId).toHaveBeenCalledTimes(1)
  })
})
