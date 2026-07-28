import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { PICO_AUTH_CROSS_HOST_LINKS } from '@/components/AuthNav'
import { classifyPicoSessionRuntime } from '@/components/pico/PicoSessionBanner'

function readSource(relativePath: string) {
  return readFileSync(join(process.cwd(), relativePath), 'utf8')
}

describe('Pico frontend recovery and runtime truth contracts', () => {
  it('uses absolute HTTPS destinations for every cross-host auth navigation link', () => {
    expect(PICO_AUTH_CROSS_HOST_LINKS).toHaveLength(3)

    for (const link of PICO_AUTH_CROSS_HOST_LINKS) {
      const url = new URL(link.href)
      expect(url.protocol).toBe('https:')
      expect(['mutx.dev', 'app.mutx.dev']).toContain(url.hostname)
    }
  })

  it('classifies runtime state only from an observed runtime response', () => {
    expect(classifyPicoSessionRuntime({ loading: true })).toBe('loading')
    expect(classifyPicoSessionRuntime({ loading: false })).toBe('unavailable')
    expect(classifyPicoSessionRuntime({ loading: false, status: 'healthy' })).toBe('available')
    expect(classifyPicoSessionRuntime({ loading: false, status: 'degraded' })).toBe('degraded')
    expect(classifyPicoSessionRuntime({ loading: false, status: 'healthy', stale: true })).toBe('stale')
    expect(classifyPicoSessionRuntime({ loading: false, status: 'healthy', error: 'timeout' })).toBe('unavailable')
  })

  it('renders session truth from progress sync and runtime state, never webhook counts', () => {
    const source = readSource('components/pico/PicoSessionBanner.tsx')

    expect(source).toContain('progressSyncState')
    expect(source).toContain('runtimeSignal')
    expect(source).not.toContain('/api/webhooks')
    expect(source).not.toContain("productTruth.live")
  })

  it('focuses assertive error summaries and associates invalid auth fields', () => {
    const sources = [
      'components/pico/PicoAuthPage.tsx',
      'components/pico/PicoForgotPasswordPageClient.tsx',
      'components/pico/PicoResetPasswordPageClient.tsx',
    ].map(readSource)

    for (const source of sources) {
      expect(source).toContain('role="alert"')
      expect(source).toContain('aria-live="assertive"')
      expect(source).toContain('tabIndex={-1}')
      expect(source).toContain('aria-invalid=')
      expect(source).toContain('aria-describedby=')
      expect(source).toMatch(/\.current\?\.focus\(\)/)
    }
  })

  it('keeps recovery pages localized and derives Pico host presentation on the server', () => {
    for (const relativePath of [
      'components/pico/PicoForgotPasswordPageClient.tsx',
      'components/pico/PicoResetPasswordPageClient.tsx',
      'components/pico/PicoVerifyEmailPageClient.tsx',
    ]) {
      const source = readSource(relativePath)
      expect(source).toContain("useTranslations('pico.authRecovery.")
      expect(source).toContain('hostVariant={hostVariant}')
    }

    for (const relativePath of [
      'app/forgot-password/page.tsx',
      'app/reset-password/page.tsx',
      'app/verify-email/page.tsx',
    ]) {
      const source = readSource(relativePath)
      expect(source).toContain('isPicoHost(host)')
      expect(source).toContain("? 'pico' : 'default'")
    }

    for (const relativePath of [
      'app/forgot-password/layout.tsx',
      'app/reset-password/layout.tsx',
      'app/verify-email/layout.tsx',
    ]) {
      const source = readSource(relativePath)
      expect(source).toContain('getTranslations(')
      expect(source).toContain('authRecovery.')
    }

    expect(readSource('app/verify-email/page.tsx')).toContain(
      'getDefaultRedirectPathForHost(host)',
    )
    expect(readSource('app/forgot-password/page.tsx')).toContain(
      'getDefaultRedirectPathForHost(host)',
    )
    expect(readSource('app/reset-password/page.tsx')).toContain(
      'getDefaultRedirectPathForHost(host)',
    )
  })

  it('uses only the signed backend return path after verification or reset', () => {
    const verification = readSource('components/pico/PicoVerifyEmailPageClient.tsx')
    const reset = readSource('components/pico/PicoResetPasswordPageClient.tsx')
    const forgot = readSource('components/pico/PicoForgotPasswordPageClient.tsx')

    expect(verification).toContain('payload?.return_path')
    expect(verification).toContain('token\n    ? verifiedReturnPath ?? fallbackPath')
    expect(verification).toContain('return_path: nextPath')
    expect(reset).toContain('payload?.return_path')
    expect(reset).toContain('resolveRedirectPath(')
    expect(forgot).toContain('return_path: returnPath')
    expect(readSource('components/pico/PicoAuthPage.tsx')).toContain(
      '`/forgot-password?next=${encodeURIComponent(redirectPath)}`',
    )
    expect(reset).toContain('<Link href={loginHref} className={styles.inlineLink}>')
    expect(readSource('app/forgot-password/page.tsx')).toContain(
      'resolveRedirectPath(requestedPath, getDefaultRedirectPathForHost(host))',
    )
  })

  it('defaults onboarding runtime truth to client-required and clears stale setup state on load failure', () => {
    const onboarding = readSource('components/pico/PicoOnboardingPageClient.tsx')
    const setupState = readSource('components/pico/usePicoSetupState.ts')

    expect(onboarding).toContain("status: 'client_required'")
    expect(onboarding).not.toContain("status: 'healthy'")
    expect(setupState).toMatch(
      /catch \(loadError\)[\s\S]*setOnboarding\(null\)[\s\S]*setRuntime\(null\)/,
    )
  })

  it('never awards the retired enforcement milestone from local Autopilot actions', () => {
    const source = readSource('components/pico/PicoAutopilotPageClient.tsx')

    expect(source).not.toContain("unlockMilestone('first_approval_gate_enabled')")
    expect(source).not.toContain('setAutopilot({ approvalGateEnabled: true })')
    expect(source).not.toContain("t('hero.gateState.armed')")
  })
})
