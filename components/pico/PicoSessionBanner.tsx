'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { useSearchParams } from 'next/navigation'

import { buildOAuthStartHref, oauthProviders } from '@/lib/auth/oauth'
import { picoClasses, picoEmber, picoPanel, picoSoft } from '@/components/pico/picoTheme'
import { type PicoProgressSyncState } from '@/components/pico/usePicoProgress'
import { type PicoSessionState } from '@/components/pico/usePicoSession'
import { mergeRedirectPathWithSearch, resolveRedirectPath } from '@/lib/auth/redirects'

type PicoSessionBannerProps = {
  session: PicoSessionState
  nextPath: string
  progressSyncState: PicoProgressSyncState
  runtimeSignal: PicoSessionRuntimeSignal
}

export type PicoSessionRuntimeSignal = {
  label: string
  state: 'loading' | 'available' | 'degraded' | 'stale' | 'unavailable'
}

export function classifyPicoSessionRuntime(input: {
  loading: boolean
  error?: string | null
  status?: string | null
  stale?: boolean
}): PicoSessionRuntimeSignal['state'] {
  if (input.loading) return 'loading'
  if (input.error || !input.status) return 'unavailable'
  if (input.stale) return 'stale'
  if (input.status.toLowerCase() === 'healthy') return 'available'
  if (['degraded', 'warning'].includes(input.status.toLowerCase())) return 'degraded'
  return 'unavailable'
}

export function PicoSessionBanner({
  session,
  nextPath,
  progressSyncState,
  runtimeSignal,
}: PicoSessionBannerProps) {
  const t = useTranslations('pico.sessionBanner')
  const syncT = useTranslations('pico.autopilotPage.shared.syncStateLabels')
  const searchParams = useSearchParams()
  const redirectPath = resolveRedirectPath(
    mergeRedirectPathWithSearch(nextPath, searchParams.toString()),
    '/pico/onboarding',
  )
  if (session.status === 'authenticated') {
    return (
      <div className={picoPanel('p-3 sm:p-4')}>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={picoClasses.chipSuccess}>{t('authenticated.chips.sessionAttached')}</span>
              <span className={picoClasses.chipNeutral}>
                {session.user.plan ? t('authenticated.chips.plan', { plan: session.user.plan.toLowerCase() }) : t('authenticated.chips.planUnknown')}
              </span>
              <span className={session.user.isEmailVerified === false ? picoClasses.chipWarning : session.user.isEmailVerified === true ? picoClasses.chipSuccess : picoClasses.chipNeutral}>
                {session.user.isEmailVerified === false
                  ? t('authenticated.chips.verificationPending')
                  : session.user.isEmailVerified === true
                    ? t('authenticated.chips.emailVerified')
                    : t('authenticated.chips.emailStatusUnknown')}
              </span>
              <span
                className={
                  runtimeSignal.state === 'available'
                    ? picoClasses.chipSuccess
                    : runtimeSignal.state === 'loading'
                      ? picoClasses.chipNeutral
                      : picoClasses.chipWarning
                }
              >
                {runtimeSignal.label}
              </span>
            </div>
            <p className="mt-2 truncate text-sm text-[color:var(--pico-text-secondary)]">
              {session.user.email ?? session.user.name ?? t('authenticated.rails.operator')}
            </p>
          </div>

          <div className={picoSoft('grid gap-2 p-3 sm:min-w-[22rem]')}>
            <div className="grid grid-cols-3 gap-2 text-xs text-[color:var(--pico-text-secondary)]">
              <div>
                <p className="text-[color:var(--pico-text-muted)]">{t('authenticated.productTruth.progressSync')}</p>
                <p className="mt-1 font-medium text-[color:var(--pico-text)]">{syncT(progressSyncState)}</p>
              </div>
              <div>
                <p className="text-[color:var(--pico-text-muted)]">{t('authenticated.rails.emailState')}</p>
                <p className="mt-1 font-medium text-[color:var(--pico-text)]">
                  {session.user.isEmailVerified === false
                    ? t('authenticated.rails.pending')
                    : session.user.isEmailVerified === true
                      ? t('authenticated.rails.verified')
                      : t('authenticated.chips.emailStatusUnknown')}
                </p>
              </div>
              <div>
                <p className="text-[color:var(--pico-text-muted)]">{t('authenticated.productTruth.runtimeTruth')}</p>
                <p className="mt-1 font-medium text-[color:var(--pico-text)]">
                  {runtimeSignal.label}
                </p>
              </div>
            </div>
            {session.user.isEmailVerified === false && session.user.email ? (
              <Link
                href={`/verify-email?email=${encodeURIComponent(session.user.email)}&next=${encodeURIComponent(redirectPath)}`}
                className={picoClasses.secondaryButton}
              >
                {t('authenticated.finishEmailVerification')}
              </Link>
            ) : null}
          </div>
        </div>
      </div>
    )
  }

  if (session.status === 'loading') {
    return (
      <div className={picoPanel('p-4 sm:p-5')}>
        <p className={picoClasses.label}>{t('loading.label')}</p>
        <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]">
          {t('loading.body')}
        </p>
      </div>
    )
  }

  if (session.status === 'error') {
    return (
      <div className={picoEmber('p-4 sm:p-5')}>
        <p className={picoClasses.label}>{t('loading.label')}</p>
        <p className="mt-2 text-sm leading-6 text-[color:var(--pico-text-secondary)]" role="alert">
          {t('errors.sessionUnavailable')}: {session.error}
        </p>
      </div>
    )
  }

  return (
    <div className={picoEmber('p-3 sm:p-4')}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={picoClasses.chipWarning}>{t('anonymous.chips.sessionRequired')}</span>
            <span className={picoClasses.chipNeutral}>{t('anonymous.chips.picoHostAuth')}</span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--pico-text-secondary)]">
            {t('anonymous.body')}
          </p>
        </div>

        <div className={picoSoft('grid gap-3 p-3 sm:min-w-[24rem]')}>
          <div className="grid grid-cols-3 gap-2 text-xs text-[color:var(--pico-text-secondary)]">
            <div>
              <p className="text-[color:var(--pico-text-muted)]">{t('anonymous.rails.progress')}</p>
              <p className="mt-1 font-medium text-[color:var(--pico-text)]">{t('anonymous.withoutSession.localOnly')}</p>
            </div>
            <div>
              <p className="text-[color:var(--pico-text-muted)]">{t('anonymous.rails.runtimeTruth')}</p>
              <p className="mt-1 font-medium text-[color:var(--pico-text)]">{t('anonymous.rails.limited')}</p>
            </div>
            <div>
              <p className="text-[color:var(--pico-text-muted)]">{t('anonymous.rails.approvals')}</p>
              <p className="mt-1 font-medium text-[color:var(--pico-text)]">{t('anonymous.withoutSession.blocked')}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href={`/login?next=${encodeURIComponent(redirectPath)}`} className={picoClasses.primaryButton}>
              {t('anonymous.withoutSession.signIn')}
            </Link>
            <Link href={`/register?next=${encodeURIComponent(redirectPath)}`} className={picoClasses.secondaryButton}>
              {t('anonymous.withoutSession.createAccount')}
            </Link>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {oauthProviders.slice(0, 4).map((provider) => (
              <Link
                key={provider.id}
                href={buildOAuthStartHref(provider.id, 'login', redirectPath)}
                prefetch={false}
                className={picoClasses.tertiaryButton}
              >
                {t('anonymous.withoutSession.continueWithProvider', { provider: provider.label })}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
